"""Windows service lifecycle against a tiny HTTP stub, never the real ComfyUI."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.request


@unittest.skipUnless(os.name=='nt' and shutil.which('powershell.exe'),'Windows PowerShell only')
class ServiceTests(unittest.TestCase):
    def test_owned_stub_start_reuse_and_stop(self):
        with tempfile.TemporaryDirectory(prefix='vgen service ') as temp:
            folder=Path(temp)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            (folder/'main.py').write_text('''import argparse,json
from http.server import BaseHTTPRequestHandler,HTTPServer
p=argparse.ArgumentParser();p.add_argument('--listen');p.add_argument('--port',type=int);p.add_argument('--output-directory');p.add_argument('--extra-model-paths-config');a=p.parse_args()
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'{}')
 def log_message(self,*args):pass
HTTPServer((a.listen,a.port),Handler).serve_forever()
''',encoding='ascii')
            cfg=dict(root=str(folder),comfy=str(folder),python=sys.executable,server=f'http://127.0.0.1:{port}',state=str(folder/'state'),output=str(folder/'output space'))
            config=folder/'config.json';config.write_text(json.dumps(cfg),encoding='ascii')
            scripts=Path(__file__).resolve().parents[1]/'scripts'
            def invoke(name):
                return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(scripts/name),'-Config',str(config)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
            try:
                result=invoke('start_comfy.ps1')
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                record=json.loads((folder/'state/service.json').read_text())
                with urllib.request.urlopen(cfg['server']+'/system_stats',timeout=2) as response:self.assertEqual(response.status,200)
                result=invoke('start_comfy.ps1')
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(json.loads((folder/'state/service.json').read_text())['pid'],record['pid'])
                modified=dict(record,started='2000-01-01T00:00:00Z')
                (folder/'state/service.json').write_text(json.dumps(modified))
                result=invoke('stop_server.ps1');self.assertNotEqual(result.returncode,0)
                with urllib.request.urlopen(cfg['server']+'/system_stats',timeout=2) as response:self.assertEqual(response.status,200)
                (folder/'state/service.json').write_text(json.dumps(record))
                # A responding server without an ownership record is shared, never adopted/killed.
                (folder/'state/service.json').unlink()
                result=invoke('start_comfy.ps1');self.assertEqual(result.returncode,0)
                self.assertFalse((folder/'state/service.json').exists())
                result=invoke('stop_server.ps1');self.assertEqual(result.returncode,0)
                with urllib.request.urlopen(cfg['server']+'/system_stats',timeout=2) as response:self.assertEqual(response.status,200)
                (folder/'state/service.json').write_text(json.dumps(record))
            finally:
                result=invoke('stop_server.ps1')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertFalse((folder/'state/service.json').exists())
            result=invoke('stop_server.ps1');self.assertEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
