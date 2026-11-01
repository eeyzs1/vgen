"""Capture exact source/environment evidence without loading models."""
import json
import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from studio_core import canonical, environment
from studio_media import file_hash


def source_snapshot(cfg):
    state=Path(cfg['state']);state.mkdir(parents=True,exist_ok=True)
    folder=state/'source_archives';folder.mkdir(exist_ok=True)
    report=environment(cfg)
    report['inference_python']=subprocess.run([cfg['python'],'--version'],capture_output=True,text=True,encoding='utf-8',check=True).stdout.strip()
    report['inference_packages']=subprocess.run([cfg['python'],'-m','pip','freeze'],capture_output=True,text=True,encoding='utf-8',check=True).stdout.splitlines()
    report['sources']=[]
    for path in (Path(cfg['comfy'])/'custom_nodes').iterdir():
        if not path.is_dir() or path.name.startswith(('.','__')):continue
        files=[]
        for parent,dirs,names in os.walk(path):
            dirs[:]=[d for d in dirs if d not in ('.venv','venv','.git','__pycache__','node_modules')]
            files.extend(Path(parent)/name for name in names if Path(name).suffix.lower() in ('.py','.json','.toml','.txt','.md','.yaml','.yml') or name in ('LICENSE','COPYING'))
        hashes={str(p.relative_to(path)):file_hash(p) for p in sorted(files)}
        archive=folder/(path.name+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as out:
            for item in files:out.write(item,item.relative_to(path))
        report['sources'].append(dict(name=path.name,files=hashes,archive=str(archive),archive_sha256=file_hash(archive)))
    # Preserve modifications to the shared base as evidence, without resetting it.
    patch=subprocess.run(['git','-C',cfg['comfy'],'diff','--binary','HEAD'],capture_output=True,check=True).stdout
    patch_path=folder/'comfy.patch';patch_path.write_bytes(patch)
    report['comfy_patch']=dict(path=str(patch_path),sha256=file_hash(patch_path))
    (state/'environment.json').write_text(canonical(report),encoding='utf-8')
    return report


def license_snapshot(root):
    root=Path(root);folder=root/'licenses';folder.mkdir(exist_ok=True)
    models={'h3':'MiniMaxAI/MiniMax-H3','music3':'MiniMaxAI/MiniMax-Music3','moss':'OpenMOSS-Team/MOSS-SoundEffect-v2.0'}
    records=[]
    for name,repo in models.items():
        with urllib.request.urlopen('https://huggingface.co/api/models/'+repo,timeout=30) as response:
            metadata=json.load(response)
        revision=metadata['sha']
        names={x['rfilename'] for x in metadata.get('siblings',[])}
        filename='LICENSE' if 'LICENSE' in names else 'README.md'
        url=f'https://huggingface.co/{repo}/resolve/{revision}/{filename}'
        with urllib.request.urlopen(url,timeout=30) as response:content=response.read()
        path=folder/(name+('.LICENSE' if filename=='LICENSE' else '.model-card.md'));path.write_bytes(content)
        records.append(dict(model=repo,revision=revision,url=url,path=str(path.relative_to(root)),sha256=file_hash(path),evidence_type='license_text' if filename=='LICENSE' else 'model_card_license_declaration',commercial_authorization='not_recorded',
                            weight_revision_matches_snapshot='not_proven; historical downloaded weights only have SHA256 manifest'))
    (folder/'manifest.json').write_text(canonical(dict(captured='2026-11-01',models=records)),encoding='utf-8')
    return records
