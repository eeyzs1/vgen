import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import studio_core as core
from run_video import build_workflow, snap_length
from studio import validate_project

class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.cfg=dict(root=str(self.root),state=str(self.root/'.studio'),output=str(self.root/'out'),models=str(self.root/'models'),comfy=str(self.root/'comfy'),server='http://127.0.0.1:8188',ffmpeg='ffmpeg',ffprobe='ffprobe')
        self.cfg['telemetry']=False
        self.args=argparse.Namespace(dry_run=False,new_take=False,retry_failed=False,timeout=1)
        self.wf={'1':{'class_type':'SaveImage','inputs':{'filename_prefix':'batch/test'}}}
    def test_relative_and_absolute_paths(self):
        self.assertEqual(core.resolve(self.root,'out/中文 space.png'),self.root/'out/中文 space.png')
        self.assertEqual(core.resolve(self.root,self.root/'absolute.png'),self.root/'absolute.png')
    def test_config_bom_overrides_and_missing_explicit_file(self):
        filename=self.root/'settings.json'
        filename.write_text(json.dumps({'root':'.','output':'media','server':'http://127.0.0.1:9999'}),encoding='utf-8-sig')
        result=core.config(argparse.Namespace(config=str(filename),output='override'))
        self.assertEqual(result['root'],str(self.root))
        self.assertEqual(result['output'],str(self.root/'override'))
        self.assertEqual(result['server'],'http://127.0.0.1:9999')
        with self.assertRaises(FileNotFoundError):core.config(argparse.Namespace(config=str(self.root/'absent.json')))
    def test_recipes(self):
        base=build_workflow('image','prompt',1344,768,124,1,'test',50,'base')
        turbo=build_workflow('image','prompt',1344,768,124,1,'test',8,'turbo')
        self.assertNotIn('turbo',base);self.assertEqual(base['shift']['inputs']['model'],['model',0]);self.assertIn('turbo',turbo)
        self.assertEqual(snap_length(125),141)
    def test_versioning_review_preserved(self):
        store=core.Store(self.cfg)
        a=store.prepare('shot',{'seed':1},self.wf,{})
        store.update(a['id'],review='approved',selected=1)
        self.assertEqual(store.prepare('shot',{'seed':1},self.wf,{})['id'],a['id'])
        self.assertNotEqual(store.prepare('shot',{'seed':2},self.wf,{})['id'],a['id'])
        self.assertEqual(store.prepare('shot',{'seed':1},self.wf,{})['selected'],1)
    def request(self,route,payload=None):
        if route=='/object_info':return {'SaveImage':{}}
        if route=='/prompt':return {'prompt_id':'pid'}
        return {}
    def execute(self):
        return core.execute(self.cfg,self.args,'shot',{},self.wf,'image')
    def test_empty_outputs_fail(self):
        with patch.object(core.Client,'request',side_effect=self.request),patch.object(core.Client,'wait',return_value={'outputs':{}}),patch.object(core,'environment',return_value={}):
            with self.assertRaises(ValueError):self.execute()
        store=core.Store(self.cfg)
        self.assertEqual(store.db.execute('SELECT state FROM tasks').fetchone()[0],'failed')
    def test_uncertain_submission_never_resubmitted(self):
        calls=[]
        def request(route,payload=None):
            calls.append(route)
            if route=='/prompt':raise OSError('response lost')
            return self.request(route,payload)
        with patch.object(core.Client,'request',side_effect=request),patch.object(core.Client,'find',return_value=None),patch.object(core,'environment',return_value={}):
            with self.assertRaises(TimeoutError):self.execute()
            with self.assertRaises(TimeoutError):self.execute()
        self.assertEqual(calls.count('/prompt'),1)
    def test_rejected_submission_is_failed_not_uncertain(self):
        from io import BytesIO
        from urllib.error import HTTPError
        def request(route,payload=None):
            if route=='/prompt':raise HTTPError('http://stub/prompt',400,'invalid',{},BytesIO(b'bad workflow'))
            return self.request(route,payload)
        with patch.object(core.Client,'request',side_effect=request),patch.object(core,'environment',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'rejected submission'):self.execute()
        store=core.Store(self.cfg)
        self.assertEqual(store.db.execute('SELECT state FROM tasks').fetchone()[0],'failed')
    def test_gpu_metrics_mocked(self):
        from studio_metrics import GpuMetrics
        import subprocess
        metrics=GpuMetrics()
        with patch('studio_metrics.subprocess.run',return_value=subprocess.CompletedProcess([],0,'100\n200\n','')):
            metrics.sample()
        result=metrics.finish()
        self.assertEqual(result['gpu_peak_mib'],300)
        self.assertEqual(result['gpu_samples'],1)
    def test_server_failure(self):
        with patch.object(core.Client,'request',side_effect=self.request),patch.object(core.Client,'wait',side_effect=RuntimeError('execution failed')),patch.object(core,'environment',return_value={}):
            with self.assertRaises(RuntimeError):self.execute()
        store=core.Store(self.cfg)
        self.assertEqual(store.db.execute('SELECT state FROM tasks').fetchone()[0],'failed')
    def test_resume_known_id_without_submit(self):
        store=core.Store(self.cfg);row=store.prepare('shot',{},self.wf,{})
        store.update(row['id'],state='unresolved',prompt_id='known')
        calls=[]
        def request(route,payload=None):calls.append(route);return self.request(route,payload)
        with patch.object(core.Client,'request',side_effect=request),patch.object(core.Client,'wait',return_value={'outputs':{}}),patch.object(core,'environment',return_value={}):
            with self.assertRaises(ValueError):self.execute()
        self.assertNotIn('/prompt',calls)
    def test_conversion_failure_is_failure(self):
        output=self.root/'out';output.mkdir();(output/'test.flac').write_bytes(b'fake')
        history={'outputs':{'1':{'audio':[{'filename':'test.flac','type':'output'}]}}}
        with patch.object(core.Client,'request',side_effect=self.request),patch.object(core.Client,'wait',return_value=history),patch.object(core,'environment',return_value={}),patch.object(core,'probe',return_value={}),patch.object(core.subprocess,'run',side_effect=RuntimeError('conversion failed')):
            with self.assertRaises(RuntimeError):core.execute(self.cfg,self.args,'shot',{},self.wf,'audio')
        store=core.Store(self.cfg)
        self.assertEqual(store.db.execute('SELECT state FROM tasks').fetchone()[0],'failed')
    def test_lock(self):
        with core.studio_lock(self.cfg):
            with self.assertRaises(RuntimeError):
                with core.studio_lock(self.cfg):pass
    def test_project_schema(self):
        root=Path(__file__).resolve().parents[1]
        validate_project(root/'examples/minimal')
    def test_missing_media(self):
        with self.assertRaises(ValueError):core.probe(self.root/'missing.wav',self.cfg,'audio')
    def test_legacy_cli_offline(self):
        import subprocess
        scripts=Path(__file__).resolve().parents[1]/'scripts'
        commands=[['run_music.py','--caption','test','--name','smoke'],['run_sfx.py','--prompt','test','--name','smoke'],['run_batch.py','--events','dog_alert','--variants','1'],['run_video.py','--prompt','test','--name','smoke','--recipe','base','--frames','120']]
        for command in commands:
            result=subprocess.run([sys.executable,str(scripts/command[0]),*command[1:],'--dry-run'],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            if command[0]=='run_video.py':self.assertEqual(json.loads(result.stdout.splitlines()[0])['spec']['frames'],124)
    def test_upload_full_location(self):
        from io import BytesIO
        path=self.root/'same.png';path.write_bytes(b'fake')
        response=BytesIO(b'{"name":"unique.png","subfolder":"nested","type":"input"}')
        with patch.object(core.urllib.request,'urlopen',return_value=response):
            self.assertEqual(core.Client(self.cfg).upload(path),'nested/unique.png [input]')
    def test_synthetic_media(self):
        import subprocess
        path=self.root/'中文 sample.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.1','-y',str(path)],check=True)
        info=core.probe(path,self.cfg,'audio')
        self.assertEqual(info['streams'][0]['codec_type'],'audio')

if __name__=='__main__':unittest.main()
