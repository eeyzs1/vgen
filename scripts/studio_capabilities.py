"""Read-only installed-node inventory and explicit extension contracts."""
import ast
import json
import os
from pathlib import Path

from studio_workflows import dependencies, image_graph, video_graph


def installed_nodes(comfy):
    paths=[Path(comfy)/'nodes.py']
    for directory in ('comfy_extras','custom_nodes'):
        for parent,dirs,files in os.walk(Path(comfy)/directory):
            dirs[:]=[d for d in dirs if d not in ('.venv','venv','node_modules','__pycache__','.git')]
            paths.extend(Path(parent)/name for name in files if name.endswith('.py'))
    found={}
    for path in paths:
        if any(part in ('.venv','venv','node_modules','__pycache__','.git') for part in path.parts):continue
        try:tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        except (OSError,SyntaxError,UnicodeError):continue
        for item in ast.walk(tree):
            if isinstance(item,ast.keyword) and item.arg=='node_id' and isinstance(item.value,ast.Constant):
                found[item.value.value]=str(path)
            elif isinstance(item,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NODE_CLASS_MAPPINGS' for t in item.targets) and isinstance(item.value,ast.Dict):
                for key in item.value.keys:
                    if isinstance(key,ast.Constant):found[key.value]=str(path)
    return found


def capability_report(cfg):
    installed=installed_nodes(cfg['comfy'])
    graphs={
        'text_image':image_graph('test',1,50,'test',1216,832),
        'reference_edit':image_graph('test',1,50,'test',1216,832,'source.png'),
        'mask_edit':image_graph('test',1,50,'test',1216,832,'source.png',mask='mask.png'),
        'first_last_video':video_graph('first.png','test',1344,768,124,1,'test',50,'base',{'last_image':'last.png'}),
        'guided_audio_video':video_graph(None,'test',1344,768,124,1,'test',50,'base',{'audio':True,'guides':[dict(frame=24,image='guide.png')]}),
        'reference_video':video_graph(None,'test',1344,768,124,1,'test',50,'base',{'references':[dict(kind='image',path='ref.png')]}),
        'control_video':video_graph(None,'test',1344,768,124,1,'test',50,'base',{'control':{'path':'depth.mp4','model_patch':'minimax_h3_fun_controlnet_union_2.0_pruned_bf16.safetensors'}})}
    report={}
    for key,graph in graphs.items():
        dep=dependencies(graph,cfg['models']);dep['missing_nodes']=sorted(set(dep['nodes'])-set(installed))
        dep['ready_for_live_validation']=not dep['missing_models'] and not dep['missing_nodes']
        dep['gpu_validated']=False
        report[key]=dep
    extension=Path(cfg['root'])/'workflows/extensions.json'
    report['extensions']=json.loads(extension.read_text(encoding='utf-8')) if extension.exists() else {}
    return report
