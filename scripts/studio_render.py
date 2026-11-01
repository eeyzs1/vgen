"""Frame-based SDR editorial renderer, scene cache and interchange export."""
import hashlib
import json
import math
import re
import sys
import uuid
from pathlib import Path

from studio_core import ROOT, Store, canonical, probe, resolve, studio_lock
from studio_media import audio_analysis, file_hash, run_ffmpeg

AUDIO_TRACKS = ('dialogue', 'music', 'sfx', 'ambience')


def encoder_check(cfg):
    result = run_ffmpeg(cfg, ['-encoders']).stdout
    for codec in ('libx264', 'ffv1', 'prores_ks', 'pcm_f32le', 'aac', 'mov_text'):
        if not re.search(r'\b' + codec + r'\b', result):
            raise ValueError('Missing FFmpeg encoder: ' + codec)


def media_for_clip(clip, folder, cfg):
    if clip.get('path') and not clip.get('take_id'):
        return resolve(folder, clip['path']), None
    if not clip.get('take_id'):
        raise ValueError('Timeline clip requires explicit path or pinned take_id')
    store = Store(cfg)
    try:
        row = store.db.execute('SELECT * FROM tasks WHERE id=?', (clip['take_id'],)).fetchone()
        if not row or row['state'] != 'completed':
            raise ValueError('Missing or incomplete take: ' + clip['take_id'])
        kind = 'video' if clip.get('track', 'video') == 'video' else 'audio'
        outputs = [x for x in json.loads(row['outputs']) if x['kind'] in
                   (('video', 'image') if kind == 'video' else ('audio',))]
        if not outputs:
            raise ValueError('Take has no compatible media')
        path=resolve(folder,clip['path']) if clip.get('path') else Path(outputs[0]['path'])
        if not path.is_file():return path,row['id']
        actual=file_hash(path)
        expected=[item.get('sha256') or (file_hash(item['path']) if Path(item['path']).is_file() else None) for item in outputs]
        if actual not in expected:raise ValueError('Timeline media does not match pinned take content')
        return path, row['id']
    finally:
        store.db.close()


def prepare_timeline(folder, cfg, project, shots, timeline):
    folder = Path(folder)
    fps = project.get('fps', 24)
    if type(fps) is not int or not 1 <= fps <= 60:
        raise ValueError('v1 supports integer project fps 1..60')
    by_id = {s['id']: s for s in shots['shots']}
    resolved, missing = [], []
    for raw in timeline['clips']:
        clip = dict(raw)
        if clip.get('track', 'video') not in ('video', *AUDIO_TRACKS):
            raise ValueError('Unknown track')
        clip.setdefault('track', 'video')
        clip.setdefault('scene_id', by_id[clip['shot_id']]['scene_id'])
        for key in ('scene_id',):
            if not re.fullmatch(r'[A-Za-z0-9_-]+', clip[key]):
                raise ValueError('Unsafe scene id')
        for key in ('fade_in', 'fade_out'):
            value = clip.get(key, 0)
            if type(value) is not int or not 0 <= value <= clip['out_frame']-clip['in_frame']:
                raise ValueError('Fades must be integer project frames within clip')
        path, take_id = media_for_clip(clip, folder, cfg)
        if not path.is_file():
            missing.append(str(path)); continue
        still = path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
        metadata = probe(path, cfg, ('image' if still else 'video') if clip['track'] == 'video' else 'audio')
        duration = float(metadata.get('format', {}).get('duration', 'inf'))
        if not still and clip['out_frame']/fps > duration + 1/fps/2:
            raise ValueError('Source cut exceeds media: ' + str(path))
        clip.update(path=str(path), take_id=take_id, sha256=file_hash(path), still=still,
                    source_probe=metadata)
        resolved.append(clip)
    if missing:
        raise ValueError('Missing media: ' + canonical(missing))
    video = sorted([c for c in resolved if c['track'] == 'video'], key=lambda c:c['start_frame'])
    if not video:
        raise ValueError('Timeline needs video clips')
    previous_end = 0
    seen_scenes, current_scene = set(), None
    for clip in video:
        if clip['start_frame'] < previous_end:
            raise ValueError('Overlapping video cuts unsupported; use explicit fade-to-black')
        if current_scene != clip['scene_id']:
            if clip['scene_id'] in seen_scenes:
                raise ValueError('Scene must form a contiguous timeline block')
            current_scene = clip['scene_id']; seen_scenes.add(current_scene)
        previous_end = clip['start_frame'] + clip['out_frame']-clip['in_frame']
    total = max(c['start_frame']+c['out_frame']-c['in_frame'] for c in resolved)
    for cue in timeline.get('subtitles',[]):
        if any(type(cue.get(key)) is not int for key in ('start_frame','end_frame')) or not 0<=cue['start_frame']<cue['end_frame']<=total:
            raise ValueError('Subtitle range exceeds the timeline or is invalid')
    return resolved, video, total


def write_srt(cues, target, fps):
    def stamp(frame):
        ms = round(frame/fps*1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    parts=[]
    for index,cue in enumerate(cues,1):
        if any(type(cue[k]) is not int for k in ('start_frame','end_frame')) or not 0 <= cue['start_frame'] < cue['end_frame']:
            raise ValueError('Invalid subtitle range')
        parts.append(f"{index}\n{stamp(cue['start_frame'])} --> {stamp(cue['end_frame'])}\n{cue['text']}\n")
    target.write_text('\n'.join(parts), encoding='utf-8')


def scene_render(clips, start, end, project, target, cfg):
    fps, width, height = project['fps'], project.get('width',1920), project.get('height',1080)
    frames = end-start
    inputs, filters, labels = [], [], []
    cursor, input_index = start, 0
    for clip in clips:
        if clip['start_frame'] > cursor:
            gap = clip['start_frame']-cursor
            label = 'gap'+str(len(labels))
            filters.append(f'color=c=black:s={width}x{height}:r={fps},trim=end_frame={gap},setpts=PTS-STARTPTS[{label}]')
            labels.append(label)
        count = clip['out_frame']-clip['in_frame']
        if clip['still']:
            inputs += ['-loop','1','-framerate',str(fps)]
        inputs += ['-i',clip['path']]
        label='cut'+str(input_index)
        chain=f'[{input_index}:v]trim=start={clip["in_frame"]/fps}:duration={count/fps},setpts=PTS-STARTPTS,fps={fps},'
        chain+=f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,'
        space=clip.get('input_color_space','srgb' if clip['still'] else 'bt709')
        if space not in ('srgb','bt709'):
            raise ValueError('Supported input color spaces: srgb, bt709')
        chain+=('colorspace=iall=bt709:itrc=iec61966-2-1:all=bt709,' if space=='srgb' else 'colorspace=iall=bt709:all=bt709,')
        grade=clip.get('grade',{})
        brightness,contrast,saturation = [float(grade.get(k,d)) for k,d in [('brightness',0),('contrast',1),('saturation',1)]]
        if not -1<=brightness<=1 or not 0<=contrast<=3 or not 0<=saturation<=3:
            raise ValueError('Grade outside supported ranges')
        chain+=f'eq=brightness={brightness}:contrast={contrast}:saturation={saturation},format=yuv422p10le,trim=end_frame={count}'
        for key,kind in [('fade_in','in'),('fade_out','out')]:
            fade=clip.get(key,0)
            if fade:chain+=f',fade=t={kind}:s={0 if kind=="in" else count-fade}:n={fade}'
        filters.append(chain+f'[{label}]');labels.append(label)
        input_index+=1;cursor=clip['start_frame']+count
    if cursor<end:
        label='tail';filters.append(f'color=c=black:s={width}x{height}:r={fps},trim=end_frame={end-cursor},setpts=PTS-STARTPTS[{label}]');labels.append(label)
    filters.append(''.join(f'[{label}]' for label in labels)+f'concat=n={len(labels)}:v=1:a=0[out]')
    run_ffmpeg(cfg,['-y',*inputs,'-filter_complex',';'.join(filters),'-map','[out]','-an','-frames:v',frames,
                    '-c:v','ffv1','-level','3','-pix_fmt','yuv422p10le','-color_primaries','bt709',
                    '-color_trc','bt709','-colorspace','bt709',target])


def render_stem(clips, total, fps, target, cfg):
    inputs,filters,labels=[],[],[]
    for i,clip in enumerate(clips):
        inputs+=['-i',clip['path']]
        count=clip['out_frame']-clip['in_frame']
        gain=float(clip.get('gain',1))
        if not math.isfinite(gain) or not 0<=gain<=16:raise ValueError('Invalid gain')
        chain=f'[{i}:a]atrim=start={clip["in_frame"]/fps}:duration={count/fps},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume={gain}'
        for key,kind in [('fade_in','in'),('fade_out','out')]:
            fade=clip.get(key,0)/fps
            if fade:chain+=f',afade=t={kind}:st={0 if kind=="in" else count/fps-fade}:d={fade}'
        if 'segment_offset_frame' in clip:
            chain+=f',atrim=start={clip["segment_offset_frame"]/fps}:duration={clip["segment_length_frame"]/fps},asetpts=PTS-STARTPTS'
        # Sample-based delay avoids millisecond rounding at arbitrary frame rates.
        chain+=f',adelay={round(clip["start_frame"]/fps*48000)}S:all=1[a{i}]'
        filters.append(chain);labels.append(f'[a{i}]')
    if labels:
        filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0,apad,atrim=duration={total/fps}[out]')
    else:
        filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={total/fps}[out]')
    run_ffmpeg(cfg,['-y',*inputs,'-filter_complex',';'.join(filters),'-map','[out]','-c:a','pcm_f32le',target])


def export_interchange(clips, project, total, output):
    sys.path.insert(0,str(ROOT/'.studio/python_packages'))
    try:import opentimelineio as otio
    except ImportError as exc:raise RuntimeError('Install requirements-studio.txt into .studio/python_packages') from exc
    fps=project['fps']; rt=otio.opentime.RationalTime; tr=otio.opentime.TimeRange
    timeline=otio.schema.Timeline(name=project['id'])
    for track_name in ('video',*AUDIO_TRACKS):
        track=otio.schema.Track(name=track_name,kind=otio.schema.TrackKind.Video if track_name=='video' else otio.schema.TrackKind.Audio)
        # Separate layers preserve overlapping audio without forcing sequential placement.
        layers=[track]
        cursors=[0]
        for clip in sorted((c for c in clips if c['track']==track_name),key=lambda c:c['start_frame']):
            layer=next((i for i,cursor in enumerate(cursors) if cursor<=clip['start_frame']),None)
            if layer is None:
                layer=len(layers);layers.append(otio.schema.Track(name=track_name+f'_{layer}',kind=track.kind));cursors.append(0)
            dest=layers[layer]
            if clip['start_frame']>cursors[layer]:dest.append(otio.schema.Gap(source_range=tr(rt(0,fps),rt(clip['start_frame']-cursors[layer],fps))))
            duration=clip['out_frame']-clip['in_frame']
            item=otio.schema.Clip(name=clip['shot_id'],media_reference=otio.schema.ExternalReference(target_url=Path(clip['path']).as_uri()),source_range=tr(rt(clip['in_frame'],fps),rt(duration,fps)))
            item.metadata['vgen']={k:v for k,v in clip.items() if k!='source_probe'}
            dest.append(item);cursors[layer]=clip['start_frame']+duration
        for layer in layers:timeline.tracks.append(layer)
    otio.adapters.write_to_file(timeline,str(output/'timeline.otio'))
    def tc(frame):
        return f'{frame//(fps*3600):02}:{frame//(fps*60)%60:02}:{frame//fps%60:02}:{frame%fps:02}'
    edl=['TITLE: '+project['id'],'FCM: NON-DROP FRAME','* VIDEO CUTS ONLY; FADES AND AUDIO ARE IN OTIO']
    for i,c in enumerate((c for c in sorted(clips,key=lambda c:c['start_frame']) if c['track']=='video'),1):
        end=c['start_frame']+c['out_frame']-c['in_frame']
        edl.extend([f'{i:03}  AX       V     C        {tc(c["in_frame"])} {tc(c["out_frame"])} {tc(c["start_frame"])} {tc(end)}','* FROM CLIP NAME: '+c['path']])
    (output/'timeline.edl').write_text('\n'.join(edl)+'\n',encoding='utf-8')


def _render_project(folder,cfg,project,shots,timeline):
    encoder_check(cfg)
    for dimension in ('width','height'):
        value=project.get(dimension,1920 if dimension=='width' else 1080)
        if type(value) is not int or value<=0 or value%2:raise ValueError('Output dimensions must be positive even integers')
    if project.get('color_space','bt709')!='bt709':raise ValueError('v1 output is SDR bt709')
    clips,video,total=prepare_timeline(folder,cfg,project,shots,timeline)
    project_output=(Path(cfg['output'])/project['id']).resolve()
    final_output=project_output/'delivery'
    if any(Path(c['path']).resolve().is_relative_to(final_output) for c in clips):
        raise ValueError('Use immutable source/take media, not files inside the delivery being replaced')
    output=project_output/('.delivery-staging-'+uuid.uuid4().hex)
    output.mkdir(parents=True,exist_ok=False)
    cache=Path(cfg['state'])/'render'/project['id'];cache.mkdir(parents=True,exist_ok=True)
    scene_files=[];scene_reports=[];start=0
    scene_audio={track:[] for track in AUDIO_TRACKS}
    for scene in dict.fromkeys(c['scene_id'] for c in video):
        group=[c for c in video if c['scene_id']==scene]
        end=max(c['start_frame']+c['out_frame']-c['in_frame'] for c in group)
        if scene==video[-1]['scene_id']:end=total
        # Absolute location removed from cache key: later scenes can shift without re-render.
        normalized=[dict(c,start_frame=c['start_frame']-start) for c in group]
        output_spec={key:project.get(key,default) for key,default in [('fps',24),('width',1920),('height',1080),('color_space','bt709')]}
        key=hashlib.sha256(canonical([file_hash(__file__),output_spec,normalized,end-start]).encode()).hexdigest()
        target=cache/(scene+'_'+key[:16]+'.mkv')
        checksum=target.with_suffix('.sha256')
        reused=target.exists() and checksum.exists() and checksum.read_text()==file_hash(target)
        if reused:probe(target,cfg,'video')
        else:
            temporary=target.with_name(target.stem+'.partial.mkv')
            scene_render(group,start,end,project,temporary,cfg)
            probe(temporary,cfg,'video');temporary.replace(target)
            checksum.write_text(file_hash(target))
        scene_files.append(target);scene_reports.append(dict(scene_id=scene,path=str(target),sha256=file_hash(target),reused=reused,start_frame=start,end_frame=end))
        scene_reports[-1]['audio']=[]
        for track in AUDIO_TRACKS:
            chunks=[]
            for clip in clips:
                finish=clip['start_frame']+clip['out_frame']-clip['in_frame']
                begin=max(start,clip['start_frame']);stop=min(end,finish)
                if clip['track']==track and begin<stop:
                    chunks.append(dict(clip,start_frame=begin-start,segment_offset_frame=begin-clip['start_frame'],segment_length_frame=stop-begin))
            audio_key=hashlib.sha256(canonical([file_hash(__file__),project['fps'],chunks,end-start]).encode()).hexdigest()
            audio_target=cache/(scene+'_'+track+'_'+audio_key[:16]+'.wav')
            audio_checksum=audio_target.with_suffix('.sha256')
            audio_reused=audio_target.exists() and audio_checksum.exists() and audio_checksum.read_text()==file_hash(audio_target)
            if not audio_reused:
                render_stem(chunks,end-start,project['fps'],audio_target,cfg)
                audio_checksum.write_text(file_hash(audio_target))
            probe(audio_target,cfg,'audio');scene_audio[track].append(audio_target)
            scene_reports[-1]['audio'].append(dict(track=track,path=str(audio_target),reused=audio_reused,sha256=file_hash(audio_target)))
        start=end
    concat=cache/'scenes.txt'
    concat.write_text(''.join("file '"+str(p).replace('\\','/').replace("'","'\\''")+"'\n" for p in scene_files),encoding='utf-8')
    silent=cache/'picture.mkv'
    run_ffmpeg(cfg,['-y','-f','concat','-safe','0','-i',concat,'-c','copy',silent])
    stems=[]
    for track in AUDIO_TRACKS:
        listing=cache/(track+'_scenes.txt')
        listing.write_text(''.join("file '"+str(p).replace('\\','/').replace("'","'\\''")+"'\n" for p in scene_audio[track]),encoding='utf-8')
        target=output/(track+'.wav')
        run_ffmpeg(cfg,['-y','-f','concat','-safe','0','-i',listing,'-c:a','pcm_f32le',target]);stems.append(target)
    mix=output/'mix.wav'
    inputs=[arg for stem in stems for arg in ['-i',stem]]
    run_ffmpeg(cfg,['-y',*inputs,'-filter_complex',''.join(f'[{i}:a]' for i in range(4))+'amix=inputs=4:normalize=0,loudnorm=I=-23:TP=-2:LRA=7,aresample=48000[out]','-map','[out]','-c:a','pcm_f32le',mix])
    subtitles=output/'subtitles.srt';write_srt(timeline.get('subtitles',[]),subtitles,project['fps'])
    master=output/'master.mov';proxy=output/'review.mp4'
    run_ffmpeg(cfg,['-y','-i',silent,'-i',mix,'-map','0:v','-map','1:a','-c:v','prores_ks','-profile:v','3','-pix_fmt','yuv422p10le','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-c:a','pcm_s24le',master])
    args=['-y','-i',master]
    if timeline.get('subtitles'):args+=['-i',subtitles]
    args+=['-map','0:v','-map','0:a']
    if timeline.get('subtitles'):args+=['-map','1:0','-c:s','mov_text']
    run_ffmpeg(cfg,[*args,'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',proxy])
    export_interchange(clips,project,total,output)
    report=dict(schema_version=1,project_id=project['id'],frames=total,fps=project['fps'],color_space='bt709 SDR',
                upscale_is_postprocessing=True,missing_media=[],scenes=scene_reports,
                selected_takes=sorted({c['take_id'] for c in clips if c.get('take_id')}),
                sources=[{k:v for k,v in c.items() if k!='source_probe'} for c in clips],
                master=probe(master,cfg,'video'),review=probe(proxy,cfg,'video'),
                audio={p.stem:audio_analysis(p,cfg) for p in [*stems,mix]},
                mix_target=dict(integrated_lufs=-23,true_peak_dbtp=-2),
                interchange_compatibility='OTIO roundtrip tested; target editor import requires separate validation')
    def published_paths(value):
        if isinstance(value,dict):return {key:published_paths(item) for key,item in value.items()}
        if isinstance(value,list):return [published_paths(item) for item in value]
        if isinstance(value,str) and value.startswith(str(output)):
            return str(final_output)+value[len(str(output)):]
        return value
    report=published_paths(report)
    (output/'delivery.json').write_text(canonical(report),encoding='utf-8')
    artifacts=[p for p in output.iterdir() if p.is_file() and p.name!='archive.json']
    (output/'archive.json').write_text(canonical(dict(files=[dict(path=p.name,sha256=file_hash(p),bytes=p.stat().st_size) for p in artifacts],source_media=[dict(path=c['path'],sha256=c['sha256']) for c in clips])),encoding='utf-8')
    # Keep the previous complete delivery until every new artifact has passed verification.
    history=project_output/'delivery_history'/uuid.uuid4().hex
    for candidate in (output,final_output,history):
        if not candidate.resolve().is_relative_to(project_output) or candidate.resolve()==project_output:
            raise ValueError('Delivery publication path escaped project output')
    replaced=final_output.exists()
    if replaced:
        history.parent.mkdir(parents=True,exist_ok=True)
        final_output.replace(history)
    try:output.replace(final_output)
    except OSError:
        if replaced:history.replace(final_output)
        raise
    return report


def render_project(folder,cfg,project,shots,timeline):
    from studio_cli import identifier
    identifier(project['id'])
    lock_cfg=dict(cfg,state=str(Path(cfg['state'])/'render_locks'/project['id']))
    with studio_lock(lock_cfg):return _render_project(folder,cfg,project,shots,timeline)
