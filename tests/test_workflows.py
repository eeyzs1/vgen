import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from studio_workflows import image_graph,video_graph,dependencies
from studio_validation import validate_workflow
from studio_download import download


class WorkflowTests(unittest.TestCase):
    def test_reference_and_mask_are_real_graphs(self):
        graph=image_graph('change hat',1,50,'x',1216,832,'source',mask='mask')
        self.assertEqual(graph['prepare']['class_type'],'H3ReferenceEditPrepare')
        self.assertIn('ref2va',graph['model']['inputs']['unet_name'])
        self.assertEqual(graph['composite']['inputs']['destination'],['source',0])
        self.assertEqual(graph['mask']['inputs']['channel'],'red')
        self.assertEqual(graph['save']['inputs']['images'],['composite',0])

    def test_guides_audio_and_reference_types(self):
        graph=video_graph('first','move',1344,768,124,1,'x',50,'base',dict(last_image='last',audio=True,guides=[dict(frame=68,image='middle')]))
        self.assertEqual(graph['prepare']['inputs']['last_frame'],['last',0])
        self.assertEqual(graph['guider']['inputs']['conditioning'],['guide_0',0])
        self.assertEqual(graph['video']['inputs']['audio'],['decode_audio',0])
        self.assertEqual(graph['save_audio']['inputs']['format'],'flac')
        ref=video_graph(None,'<Picture 1>',1344,768,124,1,'x',50,'base',dict(references=[dict(kind='image',path='ref')]))
        self.assertIn('ref_images.ref_image_0',ref['prepare']['inputs'])
        with self.assertRaises(ValueError):video_graph(None,'test',1344,768,124,1,'x',8,'turbo',dict(references=[dict(kind='image',path='ref')]))
        with self.assertRaises(ValueError):video_graph(None,'test',1344,768,124,1,'x',50,'base',dict(guides=[dict(frame=124,image='x')]))

    def test_missing_weights_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            report=dependencies(image_graph('x',1,50,'x',1216,832,'source'),folder)
            self.assertTrue(any('ref2va' in item for item in report['missing_models']))

    def test_schema_links_types_and_cycles(self):
        schema={'Source':{'output':['IMAGE'],'input':{'required':{}}},'Sink':{'output':[],'input':{'required':{'image':['IMAGE']}}}}
        graph={'1':{'class_type':'Source','inputs':{}},'2':{'class_type':'Sink','inputs':{'image':['1',0]}}}
        validate_workflow(graph,schema)
        graph['2']['inputs']['image']=['1',1]
        with self.assertRaises(ValueError):validate_workflow(graph,schema)
        graph['2']['inputs']['image']=['2',0]
        with self.assertRaises(ValueError):validate_workflow(graph,schema)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.data=b'local data '*1024
        data=self.data
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                import re
                if self.path=='/ignores-range':
                    self.send_response(200);self.end_headers();self.wfile.write(data);return
                start,end=map(int,re.fullmatch(r'bytes=(\d+)-(\d+)',self.headers['Range']).groups())
                self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}');self.end_headers();self.wfile.write(data[start:end+1])
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.url=f'http://127.0.0.1:{self.server.server_port}/data'

    def test_range_resume_hash_and_idempotence(self):
        dest=self.folder/'space 中文.bin';digest=hashlib.sha256(self.data).hexdigest()
        identity=dict(url=self.url,expected=len(self.data),workers=2,sha256=digest)
        Path(str(dest)+'.download.json').write_text(json.dumps(identity))
        Path(str(dest)+'.chunk0').write_bytes(self.data[:100])
        download(self.url,dest,len(self.data),2,digest)
        self.assertEqual(dest.read_bytes(),self.data)
        download(self.url,dest,len(self.data),2,digest)
        with self.assertRaises(ValueError):download(self.url,dest,len(self.data),2,'0'*64)

    def test_ignored_range_and_hash_fail_never_publish(self):
        dest=self.folder/'bad.bin'
        with self.assertRaises(ValueError):download(self.url.replace('/data','/ignores-range'),dest,len(self.data),2)
        self.assertFalse(dest.exists())
        with self.assertRaises(ValueError):download(self.url,self.folder/'hash.bin',len(self.data),2,'0'*64)
        self.assertFalse((self.folder/'hash.bin').exists())


if __name__=='__main__':unittest.main()
