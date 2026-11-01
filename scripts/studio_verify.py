"""Explicit streamed model verification; never runs during dry-run."""
import argparse
import json
from pathlib import Path

from studio_core import config,resolve
from studio_media import file_hash


def verify_models(cfg):
    root=Path(cfg['models'])
    records=[]
    for line in (root/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):continue
        expected,name=line.split(None,1)
        path=resolve(root,name.strip())
        if not path.is_relative_to(root):raise ValueError('Model manifest path outside model root')
        actual=file_hash(path) if path.is_file() else None
        records.append(dict(path=str(path),expected_sha256=expected,actual_sha256=actual,verified=actual==expected))
    if not records:raise ValueError('Empty model hash manifest')
    return records


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config')
    result=verify_models(config(parser.parse_args()))
    print(json.dumps(result,indent=2))
    raise SystemExit(int(not all(item['verified'] for item in result)))
