"""Offline project validation, asset inventory, task review and recovery."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from studio_core import Client, Store, canonical, common_args, config, environment, probe, resolve

def validate_project(path):
    path=Path(path)
    project=json.loads((path/'project.json').read_text(encoding='utf-8-sig'))
    shots=json.loads((path/'shots.json').read_text(encoding='utf-8-sig'))
    timeline=json.loads((path/'timeline.json').read_text(encoding='utf-8-sig'))
    import jsonschema
    for name,doc in [('project',project),('shots',shots),('timeline',timeline)]:
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas'/(name+'.schema.json')).read_text(encoding='utf-8'))
        jsonschema.validate(doc,schema)
    for doc in (project,shots,timeline):
        if doc.get('schema_version')!=1: raise ValueError('schema_version must equal 1')
    from studio_cli import identifier
    identifier(project.get('id',''))
    if not project.get('id') or project.get('fps',0)<=0: raise ValueError('Project id/fps required')
    assets=project.get('assets',{})
    for asset in assets.values():
        if not resolve(path,asset['path']).is_file(): raise ValueError('Missing reference: '+asset['path'])
    ids=set()
    for shot in shots['shots']:
        identifier(shot['id'])
        if shot['id'] in ids: raise ValueError('Duplicate shot id')
        ids.add(shot['id'])
        if shot['mode'] not in ('image','video','music','sfx'): raise ValueError('Unsupported mode')
        for ref in shot.get('references',[]):
            if ref not in assets: raise ValueError('Unknown asset: '+ref)
    for clip in timeline['clips']:
        if clip['shot_id'] not in ids: raise ValueError('Unknown shot')
        for key in ('in_frame','out_frame','start_frame'):
            if type(clip[key]) is not int or clip[key]<0: raise ValueError('Timeline values must be nonnegative integer frames')
        if clip['out_frame']<=clip['in_frame']: raise ValueError('Empty clip')
    return project,shots,timeline

def main():
    ap=argparse.ArgumentParser(); common_args(ap)
    ap.add_argument('command',choices=['check','tasks','review','scan','snapshot','reconcile','contact-sheet','proxies','generate','continue','render','audio','capabilities','report'])
    ap.add_argument('--source'); ap.add_argument('--destination'); ap.add_argument('--options')
    ap.add_argument('--shot'); ap.add_argument('--project'); ap.add_argument('--task'); ap.add_argument('--status',choices=['pending','approved','rejected']); ap.add_argument('--select',action='store_true')
    args=ap.parse_args();cfg=config(args)
    if args.dry_run and args.command not in ('generate','continue','render','audio','check','capabilities','tasks','report'):
        raise ValueError('This command has no dry-run mode; no changes performed')
    if args.command=='capabilities':
        from studio_capabilities import capability_report
        report=capability_report(cfg)
        if args.destination:
            Path(args.destination).write_text(canonical(report),encoding='utf-8')
        else:print(canonical(report))
        return
    if args.command=='render':
        from studio_render import render_project
        if not args.project: raise ValueError('--project required')
        project,shots,timeline=validate_project(args.project)
        if args.dry_run:
            from studio_render import encoder_check,prepare_timeline
            encoder_check(cfg)
            clips,video,total=prepare_timeline(args.project,cfg,project,shots,timeline)
            print(canonical(dict(dry_run=True,frames=total,clips=len(clips),render_performed=False)))
            return
        report=render_project(args.project,cfg,project,shots,timeline)
        print(f"Rendered {report['frames']} frames; delivery report saved.")
        return
    if args.command=='audio':
        from studio_media import process_audio,audio_analysis
        if not args.source or not args.destination:raise ValueError('--source and --destination required')
        options=json.loads(Path(args.options).read_text(encoding='utf-8-sig')) if args.options else {}
        if args.dry_run:
            print(canonical(audio_analysis(resolve(cfg['root'],args.source),cfg)));return
        process_audio(resolve(cfg['root'],args.source),resolve(cfg['root'],args.destination),cfg,options)
        return
    if args.command=='check':
        if args.project: validate_project(args.project)
        for name in ('ffmpeg','ffprobe'):
            subprocess.run([cfg[name],'-version'],stdout=subprocess.DEVNULL,check=True)
        print('Offline checks passed; no model generation performed.');return
    if args.command in ('generate','continue'):
        if not args.project: raise ValueError('--project required')
        folder=Path(args.project).resolve()
        project,shots,timeline=validate_project(folder)
        from studio_project import generate_project
        generate_project(folder,cfg,args,project,shots)
        return
    store=Store(cfg)
    if args.command=='report':
        rows=[dict(row) for row in store.db.execute('SELECT id,label,state,review,selected,elapsed,metrics,error FROM tasks ORDER BY created')]
        failed=sum(row['state']=='failed' for row in rows)
        completed=sum(row['state']=='completed' for row in rows)
        result=dict(tasks=rows,completed=completed,failed=failed,unresolved=sum(row['state'] in ('running','submitting','unresolved') for row in rows),failure_rate=failed/(failed+completed) if failed+completed else None)
        if args.destination:Path(args.destination).write_text(canonical(result),encoding='utf-8')
        else:print(canonical(result))
    elif args.command=='tasks':
        for row in store.db.execute('SELECT id,label,state,review,selected,error FROM tasks ORDER BY created'): print(canonical(dict(row)))
    elif args.command=='review':
        row=store.db.execute('SELECT * FROM tasks WHERE id=?',(args.task,)).fetchone()
        if not row: raise ValueError('Unknown take')
        if not args.status: raise ValueError('--status required')
        if args.select and (row['state']!='completed' or args.status!='approved'): raise ValueError('Only approved completed takes may be selected')
        with store.db:
            if args.select: store.db.execute('UPDATE tasks SET selected=0 WHERE label=?',(row['label'],))
            store.db.execute('UPDATE tasks SET review=?,selected=? WHERE id=?',(args.status,int(args.select),args.task))
    elif args.command=='scan':
        for folder in (Path(cfg['output']),Path(cfg['root'])/'approved'):
            for path in folder.rglob('*'):
                if path.suffix.lower() not in ('.png','.jpg','.wav','.flac','.mp4','.mov'):continue
                try: metadata=probe(path,cfg)
                except Exception as exc: metadata={'error':str(exc)}
                store.db.execute('INSERT OR IGNORE INTO assets(path,metadata) VALUES(?,?)',(str(path),canonical(metadata)))
        store.db.commit();print('Historical files indexed as pending; source media unchanged.')
    elif args.command=='snapshot':
        from studio_provenance import source_snapshot
        source_snapshot(cfg)
        print(Path(cfg['state'])/'environment.json')
    elif args.command=='reconcile':
        row=store.db.execute('SELECT * FROM tasks WHERE id=?',(args.task,)).fetchone()
        if not row:raise ValueError('Unknown task')
        pid=row['prompt_id'] or Client(cfg).find(row['id'])
        if pid:store.update(row['id'],prompt_id=pid,state='running');print('Found '+pid+'; rerun the original command to resume verification.')
        else:print('No matching server task found; state remains unresolved. Inspect server before --new-take.')
    elif args.command=='proxies':
        folder=Path(cfg['state'])/'review';folder.mkdir(exist_ok=True)
        for row in store.db.execute("SELECT id,outputs FROM tasks WHERE state='completed'"):
            for item in json.loads(row['outputs']):
                if item['kind']!='video':continue
                source=item['path']; stem=folder/row['id']
                subprocess.run([cfg['ffmpeg'],'-v','error','-y','-i',source,'-frames:v','1',str(stem)+'.png'],check=True)
                subprocess.run([cfg['ffmpeg'],'-v','error','-y','-i',source,'-vf','scale=960:-2','-c:v','libx264','-crf','25','-c:a','aac',str(stem)+'.mp4'],check=True)
        print(folder)
    elif args.command=='contact-sheet':
        from PIL import Image, ImageDraw
        images=[]
        for row in store.db.execute("SELECT id,outputs FROM tasks WHERE state='completed'"):
            for item in json.loads(row['outputs']):
                if item['kind']!='image':continue
                with Image.open(item['path']) as im:
                    im.thumbnail((240,160)); tile=Image.new('RGB',(260,190),'white');tile.paste(im,(10,0));ImageDraw.Draw(tile).text((10,165),row['id'][:12],fill='black');images.append(tile)
        if not images:raise ValueError('No indexed image takes')
        sheet=Image.new('RGB',(1040,190*((len(images)+3)//4)),'#cccccc')
        for i,im in enumerate(images):sheet.paste(im,((i%4)*260,(i//4)*190))
        dest=Path(cfg['state'])/'contact_sheet.jpg';sheet.save(dest);print(dest)

if __name__=='__main__':
    try:main()
    except Exception as exc:print('[ERROR] '+str(exc));sys.exit(1)
