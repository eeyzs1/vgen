"""Range-checked resumable downloader; no global process termination."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def download(url,destination,expected,workers=8,expected_hash=None):
    destination=Path(destination).resolve()
    if expected<1 or not 1<=workers<=expected:raise ValueError('Invalid byte count/workers')
    if expected_hash and not re.fullmatch('[0-9a-fA-F]{64}',expected_hash):raise ValueError('Invalid SHA256')
    expected_hash=expected_hash.lower() if expected_hash else None
    if destination.exists():
        if destination.stat().st_size!=expected or expected_hash and sha256(destination)!=expected_hash:
            raise ValueError('Existing destination differs; preserve/rename it before retry')
        return destination
    destination.parent.mkdir(parents=True,exist_ok=True)
    meta=destination.with_name(destination.name+'.download.json')
    identity=dict(url=url,expected=expected,workers=workers,sha256=expected_hash)
    if meta.exists() and json.loads(meta.read_text())!=identity:raise ValueError('Partial download belongs to a different source or layout')
    meta.write_text(json.dumps(identity),encoding='ascii')
    def piece(index):
        start=expected*index//workers;end=expected*(index+1)//workers-1
        path=destination.with_name(destination.name+f'.chunk{index}')
        needed=end-start+1
        for attempt in range(4):
            have=path.stat().st_size if path.exists() else 0
            if have>needed:raise ValueError('Oversized partial chunk')
            if have==needed:return path
            request=urllib.request.Request(url,headers={'Range':f'bytes={start+have}-{end}','Accept-Encoding':'identity'})
            try:
                with urllib.request.urlopen(request,timeout=30) as response:
                    expected_range=f'bytes {start+have}-{end}/{expected}'
                    if response.status!=206 or response.headers.get('Content-Range')!=expected_range:
                        raise ValueError('Server did not honor exact requested byte range')
                    with path.open('ab') as output:
                        remaining=needed-have
                        while remaining:
                            block=response.read(min(1024*1024,remaining))
                            if not block:raise OSError('Truncated HTTP body')
                            output.write(block);remaining-=len(block)
                        if response.read(1):raise ValueError('Oversized HTTP body')
                return path
            except (OSError,TimeoutError):
                if attempt==3:raise
                time.sleep(attempt+1)
        raise RuntimeError('Download retries exhausted')
    with ThreadPoolExecutor(max_workers=workers) as pool:parts=list(pool.map(piece,range(workers)))
    temporary=destination.with_name(destination.name+'.assembling')
    with temporary.open('wb') as output:
        for part in parts:
            with part.open('rb') as handle:
                for block in iter(lambda:handle.read(1024*1024),b''):output.write(block)
    if temporary.stat().st_size!=expected or expected_hash and sha256(temporary)!=expected_hash:
        raise ValueError('Downloaded size or SHA256 mismatch; destination not published')
    temporary.replace(destination)
    for part in parts:part.unlink()
    meta.unlink()
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',required=True);parser.add_argument('--dest',required=True)
    parser.add_argument('--expected',type=int,required=True);parser.add_argument('--workers',type=int,default=8);parser.add_argument('--sha256')
    args=parser.parse_args()
    print(download(args.url,args.dest,args.expected,args.workers,args.sha256))
