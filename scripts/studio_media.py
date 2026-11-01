"""Local, non-destructive image preparation and audio mastering tools."""
import hashlib
import json
import re
from fractions import Fraction
import subprocess
from pathlib import Path

from studio_core import canonical, probe


def run_ffmpeg(cfg, arguments):
    return subprocess.run([cfg['ffmpeg'], '-hide_banner', '-nostdin', '-v', 'info',
                           *map(str, arguments)], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', check=True)


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def fit_image(source, width, height, cfg, fit='crop'):
    """Create an inspectable fitted input; never alter the original."""
    from PIL import Image, ImageOps
    if fit not in ('crop', 'pad'):
        raise ValueError('fit must be crop or pad')
    digest = hashlib.sha256(canonical([file_hash(source), width, height, fit]).encode()).hexdigest()
    folder = Path(cfg['state']) / 'prepared'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (digest + '.png')
    if not target.exists():
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            if fit == 'crop':
                image = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
            else:
                image = ImageOps.pad(image, (width, height), method=Image.Resampling.LANCZOS, color='black')
            image.save(target)
    return target


def last_frame(source, cfg):
    info = probe(source, cfg, 'video')
    folder = Path(cfg['state']) / 'prepared'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (file_hash(source) + '_last.png')
    if not target.exists():
        # Decode only the final second so continuation cannot buffer an entire film.
        run_ffmpeg(cfg, ['-y', '-sseof','-1','-i', source, '-an', '-vf', 'reverse', '-frames:v', '1', target])
    return target


def prepare_video(source,cfg,max_seconds=None):
    info=probe(source,cfg,'video')
    stream=next(s for s in info['streams'] if s['codec_type']=='video')
    duration=float(info['format']['duration'])
    if max_seconds and not 5/24<=duration<=max_seconds:
        raise ValueError('Reference video must contain 5 frames to 15 seconds')
    if Fraction(stream['avg_frame_rate'])==24:return Path(source)
    folder=Path(cfg['state'])/'prepared';folder.mkdir(parents=True,exist_ok=True)
    target=folder/(file_hash(source)+'_24fps.mp4')
    if not target.exists():
        run_ffmpeg(cfg,['-y','-i',source,'-vf','fps=24','-c:v','libx264','-crf','12','-c:a','aac',target])
    return target


def audio_analysis(source, cfg):
    info = probe(source, cfg, 'audio')
    result = run_ffmpeg(cfg, ['-i', source, '-af',
        'silencedetect=noise=-50dB:d=0.05,volumedetect,loudnorm=I=-23:TP=-2:LRA=7:print_format=json',
        '-f', 'null', '-'])
    log = result.stderr
    loud = re.search(r'\{\s*"input_i".*?\}', log, re.S)
    peaks = re.findall(r'max_volume:\s*([^\s]+) dB', log)
    silence = [(m.group(1), float(m.group(2))) for m in
               re.finditer(r'silence_(start|end):\s*([\d.]+)', log)]
    return dict(probe=info, peak_dbfs=peaks[-1] if peaks else None,
                silence=silence, loudness=json.loads(loud.group()) if loud else {})


def process_audio(source, target, cfg, options=None):
    options = options or {}
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError('Postprocessing must not overwrite the source')
    analysis = audio_analysis(source, cfg)
    duration = float(analysis['probe']['format']['duration'])
    start, end = float(options.get('start', 0)), float(options.get('end', duration))
    if options.get('trim_silence'):
        spans = analysis['silence']
        if spans and spans[0][0] == 'start' and spans[0][1] <= 0.01:
            ends = [value for event, value in spans if event == 'end']
            start = max(start, ends[0] if ends else duration)
        starts = [value for event, value in spans if event == 'start']
        if spans and (spans[-1][0] == 'start' or
                      (spans[-1][0] == 'end' and spans[-1][1] >= duration - 0.01)):
            end = min(end, starts[-1])
    if not 0 <= start < end <= duration + 0.001:
        raise ValueError('Invalid audio cut or all-silent source')
    filters = [f'atrim=start={start}:end={end}', 'asetpts=PTS-STARTPTS']
    length = end - start
    for key in ('fade_in', 'fade_out'):
        value = float(options.get(key, 0))
        if not 0 <= value <= length:
            raise ValueError('Fade outside cut duration')
        if value:
            filters.append(f'afade=t={"in" if key == "fade_in" else "out"}:st={0 if key == "fade_in" else length-value}:d={value}')
    if options.get('normalize'):
        filters.append('loudnorm=I=-23:TP=-2:LRA=7')
    target.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(cfg, ['-y', '-i', source, '-vn', '-af', ','.join(filters), '-ar', '48000',
                     '-c:a', 'pcm_f32le', target])
    report = dict(source=str(source), source_sha256=file_hash(source), cut=[start, end],
                  options=options, before=analysis, after=audio_analysis(target, cfg))
    if options.get('loop'):
        # Audible three-pass preview, with no unproven seamless-loop claim.
        preview = target.with_name(target.stem + '_loop_preview.wav')
        run_ffmpeg(cfg, ['-y', '-stream_loop', '2', '-i', target, '-c:a', 'pcm_f32le', preview])
        report['loop'] = dict(start_sample=0, end_sample=round(length*48000),
                              seamless_verified=False, preview=str(preview))
    target.with_suffix('.report.json').write_text(canonical(report), encoding='utf-8')
    return report
