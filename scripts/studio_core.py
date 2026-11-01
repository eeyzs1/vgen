"""Shared local studio configuration, media verification and persistent jobs."""
import argparse
import contextlib
import importlib.metadata
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.studio/python_packages'))

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

def resolve(root, value):
    path = Path(value)
    return (path if path.is_absolute() else Path(root) / path).resolve()

def config(args=None):
    values = dict(root=str(ROOT), comfy=r'E:\workflow\ComfyUI', server='http://127.0.0.1:8188', ffmpeg='ffmpeg', ffprobe='ffprobe')
    filename = getattr(args, 'config', None) or os.environ.get('VGEN_CONFIG', str(ROOT / 'studio.local.json'))
    if (getattr(args,'config',None) or os.environ.get('VGEN_CONFIG')) and not Path(filename).is_file():
        raise FileNotFoundError('Explicit configuration file is missing: '+filename)
    if Path(filename).exists():
        configured=json.loads(Path(filename).read_text(encoding='utf-8-sig'))
        if configured.get('root') and not Path(configured['root']).is_absolute():configured['root']=str(resolve(Path(filename).resolve().parent,configured['root']))
        values.update(configured)
    for key in ('root', 'server', 'comfy', 'output', 'models','state','python','ffmpeg','ffprobe'):
        if args and getattr(args, key, None):
            values[key] = getattr(args, key)
    values['root'] = str(Path(values['root']).resolve())
    for key, default in [('output', 'out'), ('models', 'models'), ('state', '.studio')]:
        values[key] = str(resolve(values['root'], values.get(key, default)))
    values.setdefault('python', str(Path(values['comfy']) / '.venv/Scripts/python.exe'))
    values['comfy']=str(resolve(values['root'],values['comfy']))
    values['python']=str(resolve(values['root'],values['python']))
    return values

def common_args(parser):
    for key in ('config', 'root', 'server', 'output', 'models', 'comfy','state','python','ffmpeg','ffprobe'):
        parser.add_argument('--' + key)
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--new-take', action='store_true')
    parser.add_argument('--timeout', type=float, default=3600)
    parser.add_argument('--dry-run', action='store_true')

def probe(path, cfg, kind=None):
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        raise ValueError('Missing or empty media: ' + str(path))
    result = subprocess.run([cfg['ffprobe'], '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    info = json.loads(result.stdout)
    expected = 'video' if kind in ('image', 'video') else kind
    streams = info.get('streams', [])
    if expected and not any(s['codec_type'] == expected for s in streams):
        raise ValueError('Missing ' + expected + ' stream: ' + str(path))
    if kind in ('audio', 'video') and float(info.get('format', {}).get('duration', 0)) <= 0:
        raise ValueError('Invalid duration: ' + str(path))
    subprocess.run([cfg['ffmpeg'], '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'], capture_output=True, check=True)
    return info

def environment(cfg):
    commits = {}
    comfy = Path(cfg['comfy'])
    for path in [comfy] + (list((comfy / 'custom_nodes').iterdir()) if (comfy / 'custom_nodes').exists() else []):
        if path.is_dir() and path.name!='__pycache__':
            top = subprocess.run(['git','-C',str(path),'rev-parse','--show-toplevel'],capture_output=True,text=True,encoding='utf-8',errors='replace')
            r = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True, encoding="utf-8", errors="replace")
            commits[str(path)] = r.stdout.strip() if r.returncode == 0 and top.returncode == 0 and Path(top.stdout.strip()).resolve()==path.resolve() else 'unversioned'
    sums = Path(cfg['models']) / 'SHA256SUMS'
    packages={}
    for distribution in importlib.metadata.distributions():packages.setdefault(distribution.metadata['Name'],distribution.version)
    return dict(packages=packages, python=sys.version, executable=sys.executable, commits=commits, model_hash_manifest=sums.read_text() if sums.exists() else '', config=cfg)

class Client:
    def __init__(self, cfg):
        self.cfg = cfg
    def request(self, route, payload=None):
        data = None if payload is None else canonical(payload).encode('utf-8')
        req = urllib.request.Request(self.cfg['server'].rstrip('/') + route, data=data, headers={'Content-Type': 'application/json'})
        for attempt in range(3 if payload is None else 1):
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    body = response.read()
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as exc:
                if payload is not None or exc.code<500 or attempt==2:raise
                time.sleep(attempt+1)
            except (OSError, TimeoutError):
                if payload is not None or attempt == 2:
                    raise
                time.sleep(attempt + 1)
    def upload(self, path):
        boundary = uuid.uuid4().hex
        filename = uuid.uuid4().hex + path.suffix.lower()
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: {mimetypes.guess_type(path)[0] or "application/octet-stream"}\r\n\r\n').encode() + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        req = urllib.request.Request(self.cfg['server'] + '/upload/image', data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        with urllib.request.urlopen(req, timeout=120) as response:
            item = json.load(response)
        return '/'.join(x for x in [item.get('subfolder', ''), item['name']] if x) + ' [' + item.get('type', 'input') + ']'
    def find(self, token):
        queue = self.request('/queue')
        for item in queue.get('queue_running', []) + queue.get('queue_pending', []):
            if len(item)>3 and isinstance(item[3],dict) and item[3].get('extra_pnginfo', {}).get('vgen_task') == token:
                return item[1]
        for pid, history in self.request('/history').items():
            original=history.get('prompt') or []
            if len(original)>3 and isinstance(original[3],dict) and original[3].get('extra_pnginfo', {}).get('vgen_task') == token:
                return pid
        return None
    def wait(self, pid, timeout):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            hist = self.request('/history/' + pid)
            if pid in hist:
                h = hist[pid]
                if h.get('status', {}).get('status_str') == 'error':
                    raise RuntimeError(canonical(h.get('status')))
                if h.get('status', {}).get('completed') or h.get('status', {}).get('status_str') == 'success':
                    return h
            time.sleep(2)
        raise TimeoutError('Task still unresolved: ' + pid)

class Store:
    def __init__(self, cfg):
        state = Path(cfg['state']); state.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(state / 'studio.sqlite', timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, fingerprint TEXT, label TEXT, state TEXT, prompt_id TEXT, spec TEXT, workflow TEXT, environment TEXT, outputs TEXT DEFAULT '[]', error TEXT, review TEXT DEFAULT 'pending', selected INTEGER DEFAULT 0, created REAL, elapsed REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS assets(path TEXT PRIMARY KEY, metadata TEXT, review TEXT DEFAULT 'pending');''')
        columns={r[1] for r in self.db.execute('PRAGMA table_info(tasks)')}
        if 'metrics' not in columns:self.db.execute("ALTER TABLE tasks ADD COLUMN metrics TEXT DEFAULT '{}'");self.db.commit()
    def __del__(self):
        if hasattr(self, "db"): self.db.close()
    def update(self, tid, **fields):
        self.db.execute('UPDATE tasks SET ' + ','.join(k+'=?' for k in fields) + ' WHERE id=?', [*fields.values(), tid]); self.db.commit()
    def prepare(self, label, spec, wf, env, new=False):
        digest = hashlib.sha256(canonical([spec, wf, env]).encode()).hexdigest()
        row = self.db.execute('SELECT * FROM tasks WHERE fingerprint=? ORDER BY created DESC LIMIT 1', (digest,)).fetchone()
        if row and not new:
            return dict(row)
        tid = uuid.uuid4().hex
        self.db.execute('INSERT INTO tasks(id,fingerprint,label,state,spec,workflow,environment,created) VALUES(?,?,?,?,?,?,?,?)', (tid,digest,label,'prepared',canonical(spec),canonical(wf),canonical(env),time.time())); self.db.commit()
        return dict(self.db.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())

def _execute(cfg, args, label, spec, wf, kind):
    if args.dry_run:
        from studio_workflows import dependencies
        print(canonical(dict(dry_run=True,generation_performed=False,label=label, spec=spec, workflow=wf,dependencies=dependencies(wf,cfg['models'])))); return
    client = Client(cfg)
    client.request('/system_stats')
    nodes = client.request('/object_info')
    from studio_validation import validate_workflow
    validate_workflow(wf,nodes)
    from studio_workflows import dependencies
    missing=dependencies(wf,cfg['models'])['missing_models']
    if missing:raise ValueError('Missing models: '+canonical(missing))
    store = Store(cfg)
    active=store.db.execute("SELECT id FROM tasks WHERE label=? AND state IN ('submitting','running','unresolved') ORDER BY created DESC LIMIT 1",(label,)).fetchone()
    row = store.prepare(label, spec, wf, environment(cfg), args.new_take)
    if active and active['id']!=row['id'] and not args.new_take:
        if row['state']=='prepared':
            store.db.execute('DELETE FROM tasks WHERE id=?',(row['id'],));store.db.commit()
        raise RuntimeError('An older take is unresolved; reconcile '+active['id']+' before changing inputs or environment')
    tid = row['id']; start = time.monotonic()
    if row['state'] == 'completed':
        from studio_media import file_hash
        for item in json.loads(row['outputs']):
            probe(item['path'], cfg, item['kind'])
            if item.get('sha256') and file_hash(item['path'])!=item['sha256']:
                raise ValueError('Completed take media changed; preserve it and create a new take')
        store.db.close()
        print('[skip] ' + tid); return
    if row['state'] == 'failed' and not args.retry_failed:
        raise RuntimeError('Use --retry-failed for ' + tid)
    if row['state']=='failed' and args.retry_failed:
        row=store.prepare(label,spec,wf,environment(cfg),new=True)
        tid=row['id']
    pid = row['prompt_id']
    from studio_metrics import GpuMetrics
    metrics=GpuMetrics()
    if cfg.get('telemetry',True):metrics.start()
    try:
        if row['state'] in ('submitting', 'unresolved') and not pid:
            try:pid = client.find(tid)
            except Exception as exc:raise TimeoutError('Could not reconcile uncertain submission: '+tid) from exc
            if not pid:
                raise TimeoutError('Submission uncertain; inspect server before using --new-take: ' + tid)
        if not pid or row['state'] == 'failed':
            actual = json.loads(canonical(wf))
            for node in actual.values():
                input_key={'LoadImage':'image','LoadImageMask':'image','LoadAudio':'audio','LoadVideo':'file'}.get(node['class_type'])
                if input_key:
                    node['inputs'][input_key] = client.upload(Path(node['inputs'][input_key]))
                if 'filename_prefix' in node['inputs']:
                    node['inputs']['filename_prefix'] += '_t' + tid[:10]
            store.update(tid, state='submitting', workflow=canonical(wf))
            store.db.execute('CREATE TABLE IF NOT EXISTS submissions(task_id TEXT, payload TEXT, created REAL)')
            store.db.execute('INSERT INTO submissions VALUES(?,?,?)',(tid,canonical(actual),time.time()))
            store.db.commit()
            try:
                response = client.request('/prompt', dict(prompt=actual, client_id=tid, extra_data={'extra_pnginfo': {'vgen_task': tid}}))
                pid = response['prompt_id']
            except urllib.error.HTTPError as exc:
                detail=exc.read().decode('utf-8',errors='replace')[:2000]
                if 400<=exc.code<500:raise RuntimeError(f'Server rejected submission ({exc.code}): {detail}') from exc
                raise TimeoutError(f'Submission outcome uncertain ({exc.code}): {tid}') from exc
            except Exception as exc:
                raise TimeoutError('Submission uncertain: ' + tid) from exc
            store.update(tid, state='running', prompt_id=pid)
        hist = client.wait(pid, args.timeout)
        paths = {}
        for node in hist.get('outputs', {}).values():
            for key in ('images', 'audio', 'gifs', 'videos'):
                for item in node.get(key, []):
                    if item.get('type', 'output') == 'output' and item.get('filename'):
                        path = resolve(cfg['output'], str(Path(item.get('subfolder','')) / item['filename']))
                        if not path.is_relative_to(Path(cfg['output'])):
                            raise ValueError('Output outside configured directory')
                        media_kind='audio' if key=='audio' else 'video' if path.suffix.lower() in ('.mp4','.mov','.mkv','.webm') else 'image'
                        paths[path]=media_kind
        if not paths:
            raise ValueError('No output media returned')
        outputs = []
        if kind not in paths.values():raise ValueError('No requested '+kind+' output returned')
        from studio_media import file_hash
        from studio_validation import validate_media_specs
        for path,media_kind in sorted(paths.items()):
            info = probe(path, cfg, media_kind)
            if media_kind==kind and spec.get('expected'):validate_media_specs(info,kind,spec['expected'])
            outputs.append(dict(path=str(path), kind=media_kind, probe=info,sha256=file_hash(path)))
            if media_kind == 'audio' and path.suffix.lower() == '.flac':
                wav = path.with_suffix('.wav')
                subprocess.run([cfg['ffmpeg'], '-v','error','-y','-i',str(path),'-c:a','pcm_s16le',str(wav)], check=True)
                outputs.append(dict(path=str(wav),kind='audio',probe=probe(wav,cfg,'audio'),sha256=file_hash(wav)))
        store.update(tid,state='completed',outputs=canonical(outputs),error=None,elapsed=time.monotonic()-start)
        print('[done] ' + tid + ' ' + canonical([o['path'] for o in outputs]))
    except (TimeoutError, OSError, KeyboardInterrupt) as exc:
        store.update(tid,state='unresolved',error=str(exc),elapsed=time.monotonic()-start)
        raise
    except Exception as exc:
        store.update(tid,state='failed',error=str(exc),elapsed=time.monotonic()-start)
        if kind == 'audio' and spec.get('mode') == 'sfx':
            print('MOSS failure: inspect worker; use owned service stop/start before retry. Shared service will not be restarted.')
        raise
    finally:
        store.update(tid,metrics=canonical(metrics.finish()))
        store.db.close()


@contextlib.contextmanager
def studio_lock(cfg):
    state=Path(cfg['state']);state.mkdir(parents=True,exist_ok=True)
    handle=open(state/'generation.lock','a+b')
    if handle.seek(0,2)==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('Another studio generator is running; retry after it finishes')
    try:yield
    finally:handle.close()

def execute(cfg, args, label, spec, wf, kind):
    if args.dry_run:return _execute(cfg,args,label,spec,wf,kind)
    with studio_lock(cfg):return _execute(cfg,args,label,spec,wf,kind)
