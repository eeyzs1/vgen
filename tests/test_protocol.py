"""Real HTTP protocol integration, with deterministic CPU-only ComfyUI stub."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from studio_core import config,execute,Store


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.cfg=config();self.cfg.update(root=str(self.folder),state=str(self.folder/'state'),output=str(self.folder/'out'),models=str(self.folder/'models'),telemetry=False)
        self.folder.joinpath('out').mkdir()
        self.hist={};self.posts=[];self.lose_response=False
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send_json(self,value):
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
            def do_GET(self):
                if self.path=='/system_stats':return self.send_json({})
                if self.path=='/object_info':return self.send_json({'SaveImage':{'input':{'required':{'filename_prefix':['STRING']}},'output':[]}})
                if self.path=='/queue':return self.send_json({'queue_pending':[],'queue_running':[]})
                if self.path=='/history':return self.send_json(owner.hist)
                pid=self.path.split('/')[-1]
                return self.send_json({pid:owner.hist[pid]} if pid in owner.hist else {})
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.posts.append(payload)
                from PIL import Image
                Image.new('RGB',(32,32),'red').save(owner.folder/'out/result.png')
                pid='job'+str(len(owner.posts))
                owner.hist[pid]={'prompt':[0,pid,payload['prompt'],payload['extra_data']],
                    'status':{'completed':True,'status_str':'success'},'outputs':{'save':{'images':[dict(filename='result.png',subfolder='',type='output')]}}}
                if owner.lose_response:self.close_connection=True;return
                self.send_json({'prompt_id':pid})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.cfg['server']=f'http://127.0.0.1:{self.server.server_port}'
        self.args=argparse.Namespace(dry_run=False,new_take=False,retry_failed=False,timeout=2)
        self.graph={'save':dict(class_type='SaveImage',inputs={'filename_prefix':'shot'})}

    def test_real_submit_validate_skip_and_tamper(self):
        with patch('studio_core.environment',return_value={}):
            execute(self.cfg,self.args,'shot',{'expected':dict(width=32,height=32)},self.graph,'image')
            execute(self.cfg,self.args,'shot',{'expected':dict(width=32,height=32)},self.graph,'image')
            self.assertEqual(len(self.posts),1)
            from PIL import Image
            Image.new('RGB',(32,32),'blue').save(self.folder/'out/result.png')
            with self.assertRaisesRegex(ValueError,'media changed'):
                execute(self.cfg,self.args,'shot',{'expected':dict(width=32,height=32)},self.graph,'image')
            self.assertEqual(len(self.posts),1)

    def test_lost_response_recovers_via_actual_history_without_resubmit(self):
        self.lose_response=True
        with patch('studio_core.environment',return_value={}):
            with self.assertRaises(TimeoutError):execute(self.cfg,self.args,'shot',{},self.graph,'image')
            execute(self.cfg,self.args,'shot',{},self.graph,'image')
        self.assertEqual(len(self.posts),1)
        store=Store(self.cfg)
        self.assertEqual(store.db.execute('SELECT state FROM tasks').fetchone()[0],'completed')


if __name__=='__main__':unittest.main()
