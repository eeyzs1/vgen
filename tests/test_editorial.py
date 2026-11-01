import json
import subprocess
import sys
import tempfile
import array
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from studio_render import render_project, prepare_timeline
from studio_media import fit_image, process_audio
from studio_core import ROOT, config, probe, Store, canonical
from studio_media import file_hash


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.cfg=config();self.cfg.update(root=str(self.folder),state=str(self.folder/'.studio'),output=str(self.folder/'out'))
        self.project=dict(id='film',schema_version=1,fps=24,width=160,height=96,color_space='bt709')
        self.shots={'shots':[dict(id='red',scene_id='scene_a'),dict(id='blue',scene_id='scene_b'),dict(id='tone',scene_id='scene_a')]}
        for name in ('red','blue'):
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={name}:s=160x96:r=24:d=1','-c:v','libx264','-y',str(self.folder/(name+'.mp4'))],check=True)
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1','-y',str(self.folder/'tone.wav')],check=True)
        self.timeline=dict(schema_version=1,clips=[
            dict(shot_id='red',path='red.mp4',track='video',in_frame=0,out_frame=24,start_frame=0,fade_in=2),
            dict(shot_id='blue',path='blue.mp4',track='video',in_frame=0,out_frame=24,start_frame=24),
            dict(shot_id='tone',path='tone.wav',track='music',in_frame=0,out_frame=24,start_frame=12,fade_out=4)],
            subtitles=[dict(start_frame=0,end_frame=24,text='Local test')])

    def test_end_to_end_and_incremental(self):
        report=render_project(self.folder,self.cfg,self.project,self.shots,self.timeline)
        self.assertEqual(report['frames'],48)
        delivery=Path(self.cfg['output'])/'film/delivery'
        self.assertTrue((delivery/'timeline.otio').exists())
        self.assertTrue((delivery/'timeline.edl').exists())
        self.assertTrue((delivery/'archive.json').exists())
        info=probe(delivery/'review.mp4',self.cfg,'video')
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        self.assertEqual(int(video['nb_frames']),48)
        self.assertTrue(any(s['codec_type']=='subtitle' for s in info['streams']))
        # The audio is delayed exactly twelve frames, and all stems retain full duration.
        self.assertAlmostEqual(float(probe(delivery/'music.wav',self.cfg,'audio')['format']['duration']),2,places=3)
        raw=subprocess.run(['ffmpeg','-v','error','-i',str(delivery/'music.wav'),'-f','f32le','-ac','1','-'],capture_output=True,check=True).stdout
        samples=array.array('f');samples.frombytes(raw)
        self.assertEqual(max(abs(v) for v in samples[:23000]),0)
        self.assertGreater(max(abs(v) for v in samples[25000:40000]),0.01)
        frame_bytes=subprocess.run(['ffmpeg','-v','error','-i',str(delivery/'review.mp4'),'-vf','select=eq(n\\,12)','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
        self.assertGreater(frame_bytes[0],frame_bytes[2]+50)
        first=subprocess.run(['ffmpeg','-v','error','-i',str(delivery/'review.mp4'),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
        self.assertLess(max(first),15)
        self.timeline['clips'][0]['grade']={'saturation':0.5}
        second=render_project(self.folder,self.cfg,self.project,self.shots,self.timeline)
        self.assertFalse(second['scenes'][0]['reused'])
        self.assertTrue(second['scenes'][1]['reused'])
        sys.path.insert(0,str(ROOT/'.studio/python_packages'))
        import opentimelineio as otio
        reopened=otio.adapters.read_from_file(str(delivery/'timeline.otio'))
        self.assertEqual(reopened.duration().value,48)
        self.assertEqual(second['master']['format']['filename'],str(delivery/'master.mov'))
        previous=(delivery/'archive.json').read_bytes()
        self.timeline['clips'][2]['gain']=0.2
        import studio_render
        original_run=studio_render.run_ffmpeg
        def fail_master(cfg,arguments):
            if 'prores_ks' in arguments:raise RuntimeError('simulated disk failure')
            return original_run(cfg,arguments)
        with patch('studio_render.run_ffmpeg',side_effect=fail_master):
            with self.assertRaisesRegex(RuntimeError,'disk failure'):
                render_project(self.folder,self.cfg,self.project,self.shots,self.timeline)
        self.assertEqual((delivery/'archive.json').read_bytes(),previous)
        for entry in json.loads(previous)['files']:
            self.assertEqual(file_hash(delivery/entry['path']),entry['sha256'])
        self.assertTrue(list(delivery.parent.glob('.delivery-staging-*')))

    def test_missing_and_overlap_fail(self):
        self.timeline['clips'][1]['start_frame']=12
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            prepare_timeline(self.folder,self.cfg,self.project,self.shots,self.timeline)
        self.timeline['clips'][1]['path']='missing.mp4'
        with self.assertRaisesRegex(ValueError,'Missing media'):
            prepare_timeline(self.folder,self.cfg,self.project,self.shots,self.timeline)
    def test_subtitle_overhang_and_pinned_take_mismatch(self):
        self.timeline['subtitles'][0]['end_frame']=49
        with self.assertRaisesRegex(ValueError,'Subtitle range'):
            prepare_timeline(self.folder,self.cfg,self.project,self.shots,self.timeline)
        self.timeline['subtitles'][0]['end_frame']=24
        store=Store(self.cfg)
        take=store.prepare('red',{}, {}, {})
        store.update(take['id'],state='completed',outputs=canonical([dict(path=str(self.folder/'red.mp4'),kind='video',sha256=file_hash(self.folder/'red.mp4'))]))
        self.timeline['clips'][0]['take_id']=take['id']
        prepare_timeline(self.folder,self.cfg,self.project,self.shots,self.timeline)
        self.timeline['clips'][0]['path']='blue.mp4'
        with self.assertRaisesRegex(ValueError,'pinned take'):
            prepare_timeline(self.folder,self.cfg,self.project,self.shots,self.timeline)
        store.db.close()

    def test_audio_and_fit(self):
        from PIL import Image
        source=self.folder/'portrait.png';Image.new('RGB',(100,200),'red').save(source)
        fitted=fit_image(source,160,96,self.cfg,'pad')
        with Image.open(fitted) as image:
            self.assertEqual(image.size,(160,96));self.assertEqual(image.getpixel((0,0)),(0,0,0))
        report=process_audio(self.folder/'tone.wav',self.folder/'edited.wav',self.cfg,
                             dict(start=0.1,end=0.9,fade_in=0.1,fade_out=0.1,loop=True))
        self.assertFalse(report['loop']['seamless_verified'])
        self.assertEqual(report['after']['probe']['streams'][0]['sample_rate'],'48000')
        self.assertEqual(report['after']['probe']['streams'][0]['codec_name'],'pcm_f32le')
    def test_silence_trim(self):
        source=self.folder/'silence.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','anullsrc=r=48000:cl=mono:d=0.1','-f','lavfi','-i','sine=frequency=440:duration=0.2:sample_rate=48000','-filter_complex','[0:a][1:a][0:a]concat=n=3:v=0:a=1[out]','-map','[out]','-y',str(source)],check=True)
        report=process_audio(source,self.folder/'trimmed.wav',self.cfg,dict(trim_silence=True))
        self.assertAlmostEqual(float(report['after']['probe']['format']['duration']),0.2,delta=0.01)


if __name__=='__main__':unittest.main()
