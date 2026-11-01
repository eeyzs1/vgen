"""Compatibility CLI for the four original runners."""
import argparse
import hashlib
import json
from pathlib import Path
from studio_core import Client, common_args, config, execute, resolve, studio_lock

def identifier(value):
    if not value or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in value):
        raise ValueError('IDs must contain only ASCII letters, numbers, underscore or hyphen')
    return value

def run(mode, builder):
    ap = argparse.ArgumentParser()
    common_args(ap)
    ap.add_argument('--input-manifest')
    ap.add_argument('--name', default='')
    ap.add_argument('--batch', default={'image':'batch_0','music':'music_auto','sfx':'sfx_auto','video':'video_0'}[mode])
    ap.add_argument('--prompt', default='')
    ap.add_argument('--steps', type=int)
    ap.add_argument('--variants', type=int, default=3 if mode=='image' else 1)
    ap.add_argument('--base-seed', type=int, default={'image':1000,'music':2000,'sfx':3000,'video':100}[mode])
    ap.add_argument('--free-gpu', action='store_true')
    if mode=='image':
        ap.add_argument('--events', default='')
        ap.add_argument('--image-mode',choices=['text','reference','mask'],default='text')
        ap.add_argument('--source-image')
        ap.add_argument('--mask')
        ap.add_argument('--reference-image',action='append',default=[])
    if mode in ('image','video'):
        ap.add_argument('--width',type=int,default=1216 if mode=='image' else 1344)
        ap.add_argument('--height',type=int,default=832 if mode=='image' else 768)
    if mode=='music':
        ap.add_argument('--caption',required=True)
        ap.add_argument('--lyrics',default='')
        ap.add_argument('--duration',type=float,default=60)
        ap.add_argument('--cfg',type=float,default=1.7)
    if mode=='sfx':
        ap.add_argument('--negative',default='music, speech, vocals, singing')
        ap.add_argument('--seconds',type=float,default=3)
        ap.add_argument('--cfg',type=float,default=4)
        ap.add_argument('--sigma',type=float,default=5)
    if mode=='video':
        ap.add_argument('--image')
        ap.add_argument('--last-image')
        ap.add_argument('--continue-from',help='Previous video; use its last frame for same-shot continuation')
        ap.add_argument('--controls',help='JSON containing guides, references, control and audio')
        ap.add_argument('--audio',action='store_true')
        ap.add_argument('--seed',type=int,default=101)
        ap.add_argument('--frames',type=int,default=124)
        ap.add_argument('--recipe',choices=['base','turbo'],default='turbo')
    if mode in ('image','video'):
        ap.add_argument('--fit',choices=['crop','pad'],default='crop')
    args=ap.parse_args(); cfg=config(args)
    failures=0
    try:
        identifier(args.batch)
        if args.variants<1 or args.timeout<=0: raise ValueError('variants and timeout must be positive')
        if mode in ('image','video') and any(v<=0 or v%32 for v in (args.width,args.height)): raise ValueError('Dimensions must be positive multiples of 32')
        steps=args.steps if args.steps is not None else {'image':50,'music':30,'sfx':100,'video':8 if getattr(args,'recipe','')=='turbo' else 50}[mode]
        if steps<1: raise ValueError('steps must be positive')
        if mode=='sfx' and not 0.1<=args.seconds<=30: raise ValueError('seconds must be 0.1..30')
        if mode=='music' and not 0<args.duration<=300: raise ValueError('duration must be 0..300 seconds')
        if mode=='music' and not args.caption.strip():raise ValueError('caption must not be empty')
        jobs=[]
        if mode=='image' and args.events:
            if args.prompt: raise ValueError('Choose --events or --prompt')
            folder=Path(cfg['root'])/'prompts'
            for ev in args.events.split(','):
                ev=identifier(ev.strip())
                read=lambda name:(folder/name).read_text(encoding='utf-8').strip()
                jobs.append((ev,read('_style_anchor.txt')+', '+read(ev+'.txt')+'. Strictly avoid: '+read('_negative.txt')+'.'))
        else:
            jobs=[(identifier(args.name),args.prompt)]
        if mode in ('image','sfx','video') and any(not text.strip() for _,text in jobs): raise ValueError('prompt must not be empty')
        for name,text in jobs:
            for k in range(1,args.variants+1):
                try:
                    seed=args.seed+k-1 if mode=='video' else args.base_seed+k
                    if seed<0: raise ValueError('seed must be nonnegative')
                    prefix=f'{args.batch}/{name}_s{k}'
                    spec=dict(mode=mode,name=name,prompt=text,seed=seed,steps=steps)
                    if mode in ('image','video'):spec['expected']=dict(width=args.width,height=args.height)
                    if mode=='music':spec['requested_duration']=args.duration
                    if mode=='sfx':spec['expected']=dict(duration=args.seconds,sample_rate=48000,channels=1)
                    if args.input_manifest:
                        manifest=resolve(cfg['root'],args.input_manifest)
                        spec['reference_manifest_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
                    if mode=='image':
                        from studio_media import fit_image,file_hash
                        source=None;mask=None;references=[]
                        if args.image_mode!='text':
                            if not args.source_image:raise ValueError('Reference/mask edit requires --source-image')
                            source_path=resolve(cfg['root'],args.source_image)
                            source=fit_image(source_path,args.width,args.height,cfg,args.fit)
                            spec['source_sha256']=file_hash(source_path)
                            references=[str(resolve(cfg['root'],p)) for p in args.reference_image]
                            spec['references']=[file_hash(p) for p in references]
                            if args.image_mode=='mask':
                                if not args.mask:raise ValueError('Mask mode requires --mask')
                                from PIL import Image
                                original_mask=resolve(cfg['root'],args.mask)
                                with Image.open(source_path) as im,Image.open(original_mask) as mi:
                                    if im.size!=mi.size:raise ValueError('Mask and source dimensions must match')
                                mask=fit_image(original_mask,args.width,args.height,cfg,args.fit)
                                spec['mask_sha256']=file_hash(original_mask)
                        elif args.source_image or args.mask or args.reference_image:
                            raise ValueError('Use --image-mode reference or mask for edit inputs')
                        spec['image_mode']=args.image_mode
                        wf=builder(text,seed,steps,prefix,args.width,args.height,source,references,mask)
                    elif mode=='music': wf=builder(args.caption,args.lyrics,seed,args.duration,steps,args.cfg,prefix)
                    elif mode=='sfx': wf=builder(text,args.negative,args.seconds,steps,args.cfg,args.sigma,seed,prefix)
                    else:
                        frames=17*__import__('math').ceil((args.frames-5)/17)+5
                        if args.frames<1 or not 124<=frames<=362: raise ValueError('Video frames must stay within 124..362 after alignment')
                        from studio_media import fit_image,file_hash,last_frame,prepare_video
                        options=json.loads(resolve(cfg['root'],args.controls).read_text(encoding='utf-8-sig')) if args.controls else {}
                        options['audio']=bool(args.audio or options.get('audio'))
                        if args.image and args.continue_from:raise ValueError('Choose --image or --continue-from')
                        image=resolve(cfg['root'],args.image) if args.image else None
                        if args.continue_from:
                            previous=resolve(cfg['root'],args.continue_from)
                            spec['continued_from_sha256']=file_hash(previous)
                            image=last_frame(previous,cfg)
                        if image:
                            spec.update(image=str(image),image_sha256=file_hash(image))
                            image=fit_image(image,args.width,args.height,cfg,args.fit)
                        spec.update(frames=frames,recipe=args.recipe)
                        spec['expected'].update(frames=frames,fps=24)
                        if args.last_image:options['last_image']=str(resolve(cfg['root'],args.last_image))
                        if options.get('last_image'):
                            end=resolve(cfg['root'],options['last_image']);options['last_image']=str(fit_image(end,args.width,args.height,cfg,args.fit))
                        for guide in options.get('guides',[]):
                            for key in ('image','audio'):
                                if guide.get(key):
                                    path=resolve(cfg['root'],guide[key]);spec.setdefault('guide_hashes',[]).append(file_hash(path))
                                    guide[key]=str(fit_image(path,args.width,args.height,cfg,args.fit)) if key=='image' else str(path)
                        for ref in options.get('references',[]):
                            path=resolve(cfg['root'],ref['path']);ref['path']=str(path)
                            spec.setdefault('reference_hashes',[]).append(file_hash(path))
                            if ref['kind']=='video':ref['path']=str(prepare_video(path,cfg,15))
                        if options.get('control'):
                            path=resolve(cfg['root'],options['control']['path']);options['control']['path']=str(path)
                            spec['control_sha256']=file_hash(path)
                            options['control']['path']=str(prepare_video(path,cfg))
                        spec['controls']=options
                        if args.recipe=='turbo' and not (Path(cfg['models'])/'loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors').is_file(): raise ValueError('Turbo LoRA missing; use --recipe base or activate separately')
                        # Stable input name in the persisted spec, unique uploaded name only at submission.
                        wf=builder(str(image) if image else None,text,args.width,args.height,frames,seed,prefix,steps,args.recipe,options)
                    execute(cfg,args,prefix,spec,wf,'image' if mode=='image' else 'video' if mode=='video' else 'audio')
                except Exception as exc:
                    failures+=1; print('[ERROR] '+str(exc))
    except Exception as exc:
        failures+=1; print('[ERROR] '+str(exc))
    finally:
        if args.free_gpu and not args.dry_run:
            try:
                with studio_lock(cfg):
                    client=Client(cfg);queue=client.request('/queue')
                    if queue.get('queue_running') or queue.get('queue_pending'):
                        print('[cleanup] deferred while server has active or queued work')
                    else:client.request('/free',{'unload_models':True,'free_memory':True})
            except Exception as exc: failures+=1; print('[cleanup] '+str(exc))
    print(f'SUMMARY: {failures} failures')
    return int(bool(failures))
