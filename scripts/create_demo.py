"""Build a reproducible local editorial demo without models or GPU inference."""
import json
from pathlib import Path
from studio_core import config
from studio_media import run_ffmpeg
from studio_render import render_project


def create_demo(cfg):
    folder=Path(cfg['state'])/'offline_demo';folder.mkdir(parents=True,exist_ok=True)
    for color in ('red','blue','green'):
        run_ffmpeg(cfg,['-y','-f','lavfi','-i',f'color=c={color}:s=320x180:r=24:d=2','-c:v','libx264',folder/(color+'.mp4')])
    for name,freq in [('music',220),('dialogue',440),('sfx',880),('ambience',110)]:
        run_ffmpeg(cfg,['-y','-f','lavfi','-i',f'sine=frequency={freq}:duration=2','-c:a','pcm_f32le',folder/(name+'.wav')])
    project=dict(schema_version=1,id='offline_demo',fps=24,width=320,height=180,color_space='bt709',assets={})
    shots=dict(schema_version=1,shots=[dict(id=name,scene_id='scene_'+str(i),mode='video',prompt='Synthetic '+name) for i,name in enumerate(('red','blue','green'))]+
               [dict(id=name,scene_id='scene_0',mode='music' if name=='music' else 'sfx',prompt='Synthetic test tone') for name in ('music','dialogue','sfx','ambience')])
    timeline=dict(schema_version=1,clips=[dict(shot_id=color,path=color+'.mp4',track='video',in_frame=0,out_frame=48,start_frame=i*48,fade_in=6,fade_out=6) for i,color in enumerate(('red','blue','green'))]+
                  [dict(shot_id=name,path=name+'.wav',track=name,in_frame=0,out_frame=48,start_frame=i*24,fade_in=4,fade_out=4,gain=0.4) for i,name in enumerate(('music','dialogue','sfx','ambience'))],
                  subtitles=[dict(start_frame=i*48,end_frame=(i+1)*48,text=f'Scene {i+1} - CPU editorial test') for i in range(3)])
    for name,doc in [('project',project),('shots',shots),('timeline',timeline)]:
        (folder/(name+'.json')).write_text(json.dumps(doc,indent=2),encoding='utf-8')
    render_project(folder,cfg,project,shots,timeline)
    return Path(cfg['output'])/'offline_demo/delivery'


if __name__=='__main__':print(create_demo(config()))
