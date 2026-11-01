"""Detached Windows launcher with closed inherited handles."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse

from studio_core import config


def launch(cfg):
    state=Path(cfg['state']);state.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    port=urlparse(cfg['server']).port or 8188
    mounts=state/'model_paths.yaml'
    # JSON is valid YAML; keeping this file in state avoids editing shared ComfyUI files.
    mounts.write_text(json.dumps({'vgen':dict(base_path=cfg['models'],is_default=True,
                    diffusion_models='diffusion_models',text_encoders='text_encoders',vae='vae',
                    loras='loras',model_patches='model_patches',**{'moss-soundeffect-v2':'moss-sfx'})}),encoding='utf-8')
    flags=(subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else 0
    with (state/'comfy.out.log').open('ab') as out,(state/'comfy.err.log').open('ab') as err:
        process=subprocess.Popen([cfg['python'],'main.py','--listen','127.0.0.1','--port',str(port),'--output-directory',cfg['output'],'--extra-model-paths-config',str(mounts)],
                                 cwd=cfg['comfy'],env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                                 close_fds=True,creationflags=flags,start_new_session=os.name!='nt')
    return process.pid


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config')
    print(launch(config(parser.parse_args())))
