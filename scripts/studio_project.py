"""Serial project scheduler; only a shot's declared inputs invalidate its takes."""
import json
import subprocess
import sys
from pathlib import Path

from studio_core import canonical, resolve
from studio_media import file_hash


def generate_project(folder,cfg,args,project,shots):
    folder=Path(folder).resolve()
    assets=project.get('assets',{})
    chosen=[shot for shot in shots['shots'] if not args.shot or shot['id']==args.shot]
    if not chosen:raise ValueError('No matching shots')
    state=Path(cfg['state']);state.mkdir(parents=True,exist_ok=True)
    for shot in sorted(chosen,key=lambda item:('h3' if item['mode'] in ('image','video') else item['mode'])):
        dependencies={key:dict(metadata=assets[key],sha256=file_hash(resolve(folder,assets[key]['path']))) for key in shot.get('references',[])}
        manifest=dict(project_id=project['id'],style=project.get('style',''),shot=shot,assets=dependencies)
        manifest_path=state/(project['id']+'_'+shot['id']+'_inputs.json')
        manifest_path.write_text(canonical(manifest),encoding='utf-8')
        mode=shot['mode'];runner={'image':'batch','music':'music','sfx':'sfx','video':'video'}[mode]
        command=[sys.executable,str(Path(__file__).parent/('run_'+runner+'.py')),'--root',cfg['root'],'--models',cfg['models'],'--output',cfg['output'],'--server',cfg['server'],'--comfy',cfg['comfy'],'--name',shot['id'],'--batch',project['id'],'--variants',str(shot.get('variants',1)),'--input-manifest',str(manifest_path),'--timeout',str(args.timeout)]
        for key in ('state','python','ffmpeg','ffprobe'):command+=['--'+key,cfg[key]]
        if args.config:command+=['--config',args.config]
        for flag in ('dry_run','retry_failed','new_take'):
            if getattr(args,flag):command+=['--'+flag.replace('_','-')]
        if shot.get('steps') is not None:command+=['--steps',str(shot['steps'])]
        if 'seed' in shot:command+=['--seed' if mode=='video' else '--base-seed',str(shot['seed'] if mode=='video' else shot['seed']-1)]
        prompt=', '.join(x for x in (project.get('style',''),shot['prompt']) if x)
        if mode=='music':
            command+=['--caption',prompt,'--duration',str(shot.get('target_duration',60)),'--lyrics',shot.get('lyrics','')]
        else:command+=['--prompt',prompt]
        if mode in ('image','video'):
            command+=['--width',str(shot.get('width',1344 if mode=='video' else 1216)),
                      '--height',str(shot.get('height',768 if mode=='video' else 832)),
                      '--fit',shot.get('fit','crop')]
        if mode=='image':
            command+=['--image-mode',shot.get('image_mode','text')]
            for key in ('source_image','mask'):
                if shot.get(key):command+=['--'+key.replace('_','-'),str(resolve(folder,shot[key]))]
            for key in shot.get('references',[]):
                if assets[key].get('conditioning',True):command+=['--reference-image',str(resolve(folder,assets[key]['path']))]
        if mode=='video':
            command+=['--recipe',shot.get('recipe','base'),'--frames',str(round(shot.get('target_duration',124/24)*24))]
            for key,flag in [('first_frame','image'),('last_frame','last-image'),('continue_from','continue-from')]:
                if shot.get(key):command+=['--'+flag,str(resolve(folder,shot[key]))]
            options=dict(shot.get('controls',{}))
            options['references']=[*options.get('references',[]),*[dict(kind=assets[key].get('kind','image'),path=str(resolve(folder,assets[key]['path']))) for key in shot.get('references',[]) if assets[key].get('conditioning',True)]]
            for ref in options['references']:ref['path']=str(resolve(folder,ref['path']))
            for guide in options.get('guides',[]):
                for key in ('image','audio'):
                    if guide.get(key):guide[key]=str(resolve(folder,guide[key]))
            if options.get('control'):options['control']['path']=str(resolve(folder,options['control']['path']))
            control_file=state/(project['id']+'_'+shot['id']+'_controls.json')
            control_file.write_text(canonical(options),encoding='utf-8');command+=['--controls',str(control_file)]
        if mode=='sfx':command+=['--seconds',str(shot.get('target_duration',3))]
        subprocess.run(command,check=True)
