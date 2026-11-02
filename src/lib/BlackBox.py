"""Bounded local storage/export sink for SpeechTrace. No speech or action decisions."""
from __future__ import annotations
import base64
from collections import deque, OrderedDict
from datetime import datetime, timezone
import hashlib
import heapq
from itertools import groupby
import json
import math
import os
from pathlib import Path
import queue
import re
import threading
from time import monotonic
from uuid import uuid4

from .BlackBoxCodes import LABELS

LABELS = LABELS | {'reply_rejections_coalesced'}

MAX_RECORD = 16384
MAX_DISK = 256 * 1024 * 1024
MAX_EXPORT = 2 * MAX_DISK
ID = re.compile(r'^[a-f0-9]{32}$')
PART = re.compile(r'^\d{8}\.(?:standard|private)\.jsonl$')
IDENTIFIERS = {'trace_id','event_id','parent_event_id','source_event_id','alert_id','line_id','delivery_id','generation_id','attempt_id','reservation_id','operation_id','model_id','provider_id','tool_id','journal_id','parent_session_id','plugin_revision','build_id'}
LABEL_FIELDS = {'stage','reason','source','trigger','component','category','outcome','error_type','mode','path','evidence','playback_success','disposition','code','model','provider','tool','event_type','planet_class','severity','recording_mode','freshness','input_source'}
NUMBER_FIELDS = {'priority','count','message_count','input_chars','output_chars','system_chars','status_chars','memory_chars','conversation_chars','input_tokens','output_tokens','total_tokens','cached_tokens','retry_attempts','duration_ms','response_ms','written_bytes','audio_bytes','queue_depth','dropped','probe_count','body_count','signal_count','scan_stage','sequence','monotonic_ms','hull_health','total_reward','alert_count','status','input_confidence','capture_completed_ms','stt_completed_ms','repeat_first_ms','repeat_last_ms'}
BOOL_FIELDS = {'selected','proposed','optional','enforced','accepted','historic','requeued','output_drained','direct','terraformable','body_identity_known','fighter','player_pilot','shields_up','in_danger','in_fighter','in_main_ship','alerts_enabled','focus_enabled','controls_enabled','expected_callout','reported_ok','mapping_recommendation_present','usage_available','context_truncated','combat_enabled','dispatched','fighter_identity_known'}
PRIVATE_KEYS = {'user_input','final_output','tool_arguments','tool_result','input_evidence'}
SECRET = re.compile(r'(?i)(?:\b(?:sk|pk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{6,}|\bBearer\s+\S+|\b(?:authorization|api[-_ ]?key|password|secret|token|credential)\b\s*["\x27]?\s*[:=]\s*["\x27]?[^\s,;"\x27}]+|https?://[^\s]+|\b[A-Z]:[\\/][^\s"\x27]*|(?<!\w)/(?:home|Users|tmp|workspace|mnt|var)/[^\s"\x27]*|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})')
LONG_SECRET = re.compile(r'\b[A-Za-z0-9_+/=-]{32,}\b')


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def redact(value):
    """Private context is bounded and scrubbed again at export. No prompt/reasoning fields."""
    if not isinstance(value, str):
        # Do not stringify arbitrary objects or nested credentials.
        return '[unsupported context]'
    value = value[:4096]
    if re.search(r'(?i)\b(?:api[-_ ]?key|password|secret|authorization|bearer|credential|access[-_ ]?token|token|cookie)\b',value):
        return '[redacted sensitive context]'
    if re.search(r'''(?i)(?:["'](?:analysis|reasoning|chain_of_thought|prompt|system_prompt|messages|headers)["']\s*:|<(?:think|analysis|reasoning)>|^\s*(?:analysis|reasoning):)''',value):
        return '[redacted internal context]'
    return LONG_SECRET.sub('[redacted]', SECRET.sub('[redacted]', value))


def metadata(fields):
    safe = {}
    for key, value in fields.items():
        if key in IDENTIFIERS and isinstance(value,str) and re.fullmatch(r'[a-f0-9]{12,64}',value):
            safe[key] = value
        elif key in LABEL_FIELDS and isinstance(value,str):
            safe[key] = value if value in LABELS else 'not_reported'
        elif key in NUMBER_FIELDS and type(value) in (int,float) and math.isfinite(value):
            safe[key] = max(0,min(value,10**15))
        elif key in ('source_age_ms','source_time') and type(value) in (int,float) and math.isfinite(value):
            safe[key] = max(-10**15,min(value,10**15))
        elif key in BOOL_FIELDS and (type(value) is bool or value is None):
            safe[key] = value
    return safe


class RejectionWindow:
    """Bound repeated negative observations only, never eligibility decisions.

    Caller owns synchronization. Changed reasons/components have separate keys.
    Summaries describe observation counts, not duplicate processing or deliveries.
    """
    def __init__(self, seconds=30, capacity=1024):
        self.seconds = seconds
        self.capacity = capacity
        self.entries = OrderedDict()

    @staticmethod
    def summary(entry):
        if not entry['count']: return []
        fields = {k:v for k,v in entry['sample'].items()
                  if k in {'component','reason','event_id','journal_id','event_type','trigger','source','historic'}}
        return [{**fields, 'stage':'reply_rejections_coalesced', 'count':entry['count'],
                 'repeat_first_ms':entry['first']*1000, 'repeat_last_ms':entry['last']*1000}]

    def observe(self, fields, now):
        if fields.get('stage') != 'reply_not_selected': return [fields]
        key = tuple(fields.get(k) for k in ('event_id','reason','component','recording_mode'))
        entry = self.entries.get(key)
        output = []
        if entry is not None and now-entry['started'] >= self.seconds:
            output.extend(self.summary(self.entries.pop(key)))
            entry = None
        if entry is None:
            if len(self.entries) >= self.capacity:
                output.extend(self.summary(self.entries.popitem(last=False)[1]))
            self.entries[key] = dict(sample=dict(fields), started=now, count=0)
            output.append(fields)
        else:
            if not entry['count']: entry['first'] = now
            entry['count'] += 1
            entry['last'] = now
        return output

    def flush(self, now, force=False):
        output = []
        for key, entry in list(self.entries.items()):
            if force or now-entry['started'] >= self.seconds:
                output.extend(self.summary(self.entries.pop(key)))
        return output


class Recorder:
    def __init__(self, root, *, part_bytes=8*1024*1024, parts=16, sessions=8, queue_size=2048):
        self.root = Path(root)
        self.session_id = uuid4().hex
        self.started = utc()
        self.mode = 'standard'
        self.part_bytes = max(MAX_RECORD,min(int(part_bytes),16*1024*1024))
        self.parts = max(2,min(int(parts),32))
        self.sessions_limit = max(1,min(int(sessions),20))
        self.queue = queue.Queue(maxsize=max(1,min(queue_size,4096)))
        self.recent = deque(maxlen=500)
        self.lock = threading.Lock()
        self.retention_lock = threading.RLock()
        self.drop_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.sequence = 0
        self.dropped = 0
        self.failed = False
        self.closed = False
        self.written = 0
        self.pruned_parts = 0
        self.salt = os.urandom(16)
        self.sampler = None
        self.open_files = set()
        self.rejections = RejectionWindow()
        self.worker = threading.Thread(target=self._run, name='TARSBlackBox',daemon=True)
        self.worker.start()
        self.record({'stage':'session_started','component':'application'})

    def identity(self, value):
        return hashlib.blake2s(str(value)[:512].encode('utf-8'),key=self.salt,digest_size=12).hexdigest()

    def _drop(self):
        with self.drop_lock: self.dropped += 1

    def record(self, fields, private=None):
        try:
            safe = metadata(fields)
            if not self.lock.acquire(blocking=False):
                if fields.get('stage')!='records_dropped': self._drop()
                return
            try:
                if self.closed: return
                safe['recording_mode'] = self.mode
                for observation in self.rejections.observe(safe, monotonic()):
                    self._enqueue_locked(observation, private if observation is safe else None)
            finally:
                self.lock.release()
        except Exception:
            self._drop()

    def _enqueue_locked(self, safe, private=None):
        self.sequence += 1
        row = {'schema_version':1,'session_id':self.session_id,'seq':self.sequence,
            'timestamp':utc(),'monotonic_ms':round(monotonic()*1000,3),
            'component':safe.get('component','speech'),'severity':safe.get('severity','info'),'recording_mode':self.mode, **safe}
        context={}
        truncated=False
        if self.mode=='verbose':
            budget=8192
            for key,value in (private or {}).items():
                if key not in PRIVATE_KEYS: continue
                encoded=redact(value).encode('utf-8')
                truncated |= isinstance(value,str) and len(value)>4096 or len(encoded)>budget
                context[key]=encoded[:budget].decode('utf-8',errors='ignore')
                budget=max(0,budget-len(encoded))
        if context: row['context_truncated']=truncated
        try:
            self.queue.put_nowait((row,context))
            self.recent.append(row)
        except queue.Full:
            if safe.get('stage')!='records_dropped': self._drop()

    def _flush_rejections(self):
        # Maintenance must not hold up producers; contention remains a counted drop.
        with self.lock:
            if not self.closed:
                for row in self.rejections.flush(monotonic()): self._enqueue_locked(row)

    def set_mode(self, mode, confirmed=False):
        if mode not in ('standard','verbose') or (mode=='verbose' and confirmed is not True):
            raise ValueError('Explicit private recording confirmation required')
        with self.lock: self.mode = mode
        self.record({'stage':'recording_mode_changed','component':'application','mode':mode})

    def configure(self, part_mib, sessions):
        if type(part_mib) is not int or not 1<=part_mib<=16 or type(sessions) is not int or not 1<=sessions<=20:
            raise ValueError('Limits out of range')
        with self.lock:
            self.part_bytes = part_mib*1024*1024
            self.sessions_limit = sessions
        # Only storage limits persist. Every backend starts in Standard.
        target=self.root/'limits.json'
        tmp=self.root/'limits.tmp'
        tmp.write_text(json.dumps({'part_mib':part_mib,'sessions':sessions}),encoding='utf-8')
        os.replace(tmp,target)
        self.record({'stage':'recording_limits_changed','component':'application'})

    def status(self):
        with self.lock:
            return {'session_id':self.session_id,'mode':self.mode,'recording':not self.closed and not self.failed,
                'dropped':self.dropped,'written':self.written,'queue_depth':self.queue.qsize(),
                'part_mib':self.part_bytes//(1024*1024),'sessions_limit':self.sessions_limit,
                'pruned_parts':self.pruned_parts, 'parts_limit':self.parts,'disk_limit_mib':MAX_DISK//(1024*1024),'recent':list(self.recent)}

    def close(self):
        with self.lock:
            if self.closed: return
            for row in self.rejections.flush(monotonic(),force=True): self._enqueue_locked(row)
            self._enqueue_locked({'stage':'session_stopped','component':'application'})
            self.closed=True
        self.stop_event.set()
        if threading.current_thread() is not self.worker: self.worker.join(timeout=2)

    def _session(self, session_id):
        if not isinstance(session_id,str) or not ID.fullmatch(session_id): raise ValueError('Invalid session')
        path=self.root/session_id
        if path.is_symlink() or not path.is_dir(): raise ValueError('Session unavailable')
        return path

    def _files(self, path, private=False):
        return sorted(p for p in path.iterdir() if PART.fullmatch(p.name) and not p.is_symlink() and p.is_file()
                      and (private or '.standard.' in p.name))

    def _prune(self):
        with self.retention_lock:
            self._prune_locked()

    def _prune_locked(self):
        directories=sorted((p for p in self.root.iterdir() if ID.fullmatch(p.name) and p.is_dir() and not p.is_symlink()),key=lambda p:p.stat().st_mtime)
        for path in directories:
            files=self._files(path,True)
            excess=max(0,len(files)-self.parts)
            for file in files:
                if excess<=0: break
                if file not in self.open_files:
                    try:
                        file.unlink(missing_ok=True)
                        excess-=1
                        if path.name==self.session_id: self.pruned_parts+=1
                    except OSError: pass
        # Never touch files outside the exact UUID/session/part naming contract.
        allfiles=[p for d in directories for p in self._files(d,True)]
        total=sum(p.stat().st_size for p in allfiles)
        for path in list(directories):
            remove = len(directories)>self.sessions_limit and path.name!=self.session_id
            if remove:
                for p in self._files(path,True):
                    total-=p.stat().st_size; p.unlink(missing_ok=True)
                for name in ('state.json','state.tmp'):
                    p=path/name
                    if not p.is_symlink(): p.unlink(missing_ok=True)
                try: path.rmdir(); directories.remove(path)
                except OSError: pass
        for file in allfiles:
            if total<=MAX_DISK: break
            if file.exists() and file not in self.open_files:
                try: total-=file.stat().st_size; file.unlink(missing_ok=True)
                except OSError: pass
        exports=self.root/'exports'
        if exports.is_dir() and not exports.is_symlink():
            items=sorted((p for p in exports.iterdir() if re.fullmatch(r'[a-f0-9]{32}\.(?:jsonl|txt)',p.name) and not p.is_symlink()),key=lambda p:p.stat().st_mtime)
            for p in items[:-2]: p.unlink(missing_ok=True)
            for p in items[-2:]:
                if datetime.now().timestamp()-p.stat().st_mtime>900: p.unlink(missing_ok=True)

    def _state(self, clean=False):
        path=self.root/self.session_id
        tmp=path/'state.tmp'
        tmp.write_text(json.dumps({'session_id':self.session_id,'started':self.started,'clean_shutdown':clean,
            'written':self.written,'dropped':self.dropped,'pruned_parts':self.pruned_parts,'last_seq':getattr(self,'last_seq',0)}),encoding='utf-8')
        os.replace(tmp,path/'state.json')

    def _run(self):
        handles={}
        handle_paths={}
        number=0
        last_maintenance=0
        last_dropped=0
        last_loss_report=monotonic()
        try:
            self.root.mkdir(parents=True,exist_ok=True)
            limits=self.root/'limits.json'
            if limits.is_file() and not limits.is_symlink():
                try:
                    settings=json.loads(limits.read_text(encoding='utf-8'))
                    if type(settings.get('part_mib')) is int and 1<=settings['part_mib']<=16: self.part_bytes=settings['part_mib']*1024*1024
                    if type(settings.get('sessions')) is int and 1<=settings['sessions']<=20: self.sessions_limit=settings['sessions']
                except (ValueError,OSError): pass
            path=self.root/self.session_id
            path.mkdir(mode=0o700)
            self._state()
            previous=[item for item in self.list_sessions() if item['session_id']!=self.session_id]
            if previous:
                self.record({'stage':'session_previous','component':'application','parent_session_id':previous[0]['session_id']})
            if any(not item['clean_shutdown'] for item in previous):
                self.record({'stage':'previous_session_unclean','component':'application','count':sum(not item['clean_shutdown'] for item in previous),'severity':'warning'})
            self._prune()
            while not self.stop_event.is_set() or not self.queue.empty():
                try: row,context=self.queue.get(timeout=.2)
                except queue.Empty:
                    if monotonic()-last_maintenance>10:
                        self._flush_rejections()
                        self._state(); self._prune(); last_maintenance=monotonic()
                        if callable(self.sampler):
                            try: self.sampler()
                            except Exception: pass
                    continue
                try:
                    entries=[('standard',row)]
                    if context: entries.append(('private',{**row,'private_context':context}))
                    for kind,entry in entries:
                        data=(json.dumps(entry,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
                        if len(data)>MAX_RECORD: self._drop(); continue
                        handle=handles.get(kind)
                        if handle is None or handle.tell()+len(data)>self.part_bytes:
                            if handle:
                                handle.close(); self.open_files.discard(handle_paths.pop(kind,None))
                            number+=1
                            handle=os.fdopen(os.open(path/f'{number:08d}.{kind}.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_APPEND,0o600),'ab',buffering=0)
                            self._handle_path=path/f'{number:08d}.{kind}.jsonl'
                            handles[kind]=handle
                            handle_paths[kind]=self._handle_path
                            self.open_files.add(self._handle_path)
                            self._prune()
                            if len(self._files(path,True))>self.parts:
                                # A reader/Windows file lock may temporarily prevent retention.
                                # Drop this new part instead of allowing disk growth.
                                handle.close(); self.open_files.discard(handle_paths.pop(kind,None))
                                self._handle_path.unlink(missing_ok=True); handles.pop(kind,None)
                                self._drop()
                                continue
                        handle.write(data)
                    self.written+=1
                    self.last_seq=row['seq']
                    if monotonic()-last_maintenance>10:
                        self._flush_rejections()
                        self._state(); self._prune(); last_maintenance=monotonic()
                        if callable(self.sampler):
                            try: self.sampler()
                            except Exception: pass
                    if self.dropped!=last_dropped and monotonic()-last_loss_report>=1:
                        last_dropped=self.dropped
                        last_loss_report=monotonic()
                        self.record({'stage':'records_dropped','component':'application','dropped':last_dropped,'severity':'warning'})
                finally: self.queue.task_done()
            self._state(clean=True)
        except Exception:
            self.failed=True
            # Do not log recursively or let disk failure escape into gameplay.
        finally:
            for kind,handle in handles.items():
                try:
                    handle.close(); self.open_files.discard(handle_paths.get(kind))
                except Exception: pass

    def list_sessions(self):
        result=[]
        if not self.root.is_dir(): return result
        for path in self.root.iterdir():
            if not ID.fullmatch(path.name) or path.is_symlink() or not path.is_dir(): continue
            try:
                state=json.loads((path/'state.json').read_text(encoding='utf-8'))
                files=self._files(path,True)
                result.append({'session_id':path.name,'started':state.get('started'),
                    'clean_shutdown':state.get('clean_shutdown') is True,'active':path.name==self.session_id and not self.closed,
                    'dropped':state.get('dropped',0),'bytes':sum(p.stat().st_size for p in files),
                    'private_available':any('.private.' in p.name for p in files),'segments':len(files)})
            except (OSError,ValueError): continue
        return sorted(result,key=lambda r:r['started'] or '',reverse=True)[:20]

    def _records(self, path, private=False, stats=None):
        # Merge bounded file streams by sequence. Partial final lines are not evidence.
        stats = stats if stats is not None else {}
        def read(file, end):
            try:
                with open(file,'rb') as stream:
                    while True:
                        remaining=end-stream.tell()
                        if remaining<=0: break
                        line=stream.readline(min(MAX_RECORD+1,remaining))
                        if not line: break
                        if len(line)>MAX_RECORD or not line.endswith(b'\n'):
                            stats['partial_or_oversize']=stats.get('partial_or_oversize',0)+1
                            break
                        try:
                            row=json.loads(line.decode('utf-8'))
                            if isinstance(row,dict) and type(row.get('seq')) is int: yield row
                            else: stats['malformed']=stats.get('malformed',0)+1
                        except (ValueError,UnicodeError,AttributeError):
                            stats['malformed']=stats.get('malformed',0)+1
            except OSError:
                stats['unavailable_segments']=stats.get('unavailable_segments',0)+1
        plan=[]
        for p in self._files(path,private):
            try: plan.append((p,p.stat().st_size))
            except OSError: stats['unavailable_segments']=stats.get('unavailable_segments',0)+1
        return heapq.merge(*(read(p,end) for p,end in plan),key=lambda r:r['seq'])

    def activity(self, session_id, component='', severity='', decision=''):
        if session_id==self.session_id:
            with self.lock: records=list(self.recent)
        else:
            path=self._session(session_id)
            records=[]
            # Read at most 128 KiB per segment from the end, never replay a long session in the GUI.
            for file in self._files(path)[-2:]:
                with open(file,'rb') as stream:
                    size=stream.seek(0,2); stream.seek(max(0,size-131072))
                    if size>131072: stream.readline(MAX_RECORD+1)
                    for line in stream.read(131072).splitlines(keepends=True):
                        if not line.endswith(b'\n'): continue
                        try: records.append(json.loads(line.decode('utf-8')))
                        except (ValueError,UnicodeError): pass
        records=[r for r in records if isinstance(r,dict) and (not component or r.get('component')==component)
                 and (not severity or r.get('severity')==severity) and (not decision or r.get('reason')==decision)]
        return [{**metadata(r),'seq':r.get('seq'),'timestamp':r.get('timestamp') if isinstance(r.get('timestamp'),str) and re.fullmatch(r'[0-9TZ:.+\-]{10,40}',r['timestamp']) else None} for r in records[-200:]]

    def export(self, session_id, *, text=False, private=False, confirmed=False):
        if private and confirmed is not True: raise ValueError('Private export confirmation required')
        path=self._session(session_id)
        exports=self.root/'exports'
        exports.mkdir(mode=0o700,exist_ok=True)
        if exports.is_symlink(): raise ValueError('Invalid export directory')
        self._prune()
        token=uuid4().hex
        target=exports/(token+('.txt' if text else '.jsonl'))
        # Reserve an export slot before writing a potentially large artifact.
        old=sorted((p for p in exports.iterdir() if re.fullmatch(r'[a-f0-9]{32}\.(?:jsonl|txt)',p.name) and not p.is_symlink()),key=lambda p:p.stat().st_mtime)
        for p in old[:-1]: p.unlink(missing_ok=True)
        size=0
        try:
            with open(target,'xb') as stream:
                try:
                    checkpoint=json.loads((path/'state.json').read_text(encoding='utf-8'))
                except (OSError,ValueError): checkpoint={}
                header={'schema_version':1,'export':'PRIVATE' if private else 'SANITIZED', 'session_id':session_id,
                    'checkpoint_dropped':checkpoint.get('dropped') if type(checkpoint.get('dropped')) is int else None,
                    'checkpoint_pruned_parts':checkpoint.get('pruned_parts') if type(checkpoint.get('pruned_parts')) is int else None,
                    'note':'Observed software evidence only. Missing records, sequence gaps and abrupt tails are not proof of silence. Audio writes do not prove audibility.'}
                stream.write((json.dumps(header)+'\n').encode('utf-8'))
                read_stats={}
                first_seq=None; last_seq=None
                records=self._records(path,private,read_stats)
                def combine(records):
                    for seq, group in groupby(records,key=lambda r:r['seq']):
                        combined={}
                        for item in group: combined.update(item)
                        yield combined
                for row in combine(records):
                    if first_seq is None: first_seq=row['seq']
                    last_seq=row['seq']
                    clean={'schema_version':1,'session_id':session_id,'seq':row['seq'],'timestamp':row.get('timestamp') if isinstance(row.get('timestamp'),str) and re.fullmatch(r'[0-9TZ:.+\-]{10,40}',row['timestamp']) else None,**metadata(row)}
                    if private and isinstance(row.get('private_context'),dict):
                        clean['private_context']={k:redact(v) for k,v in row['private_context'].items() if k in PRIVATE_KEYS}
                    if text:
                        data=f"{clean.get('timestamp')} #{row['seq']} {clean.get('component','speech')} {clean.get('stage','not_reported')} "+json.dumps({k:v for k,v in clean.items() if k not in ('timestamp','schema_version','session_id')},ensure_ascii=False)+'\n'
                    else: data=json.dumps(clean,ensure_ascii=False,separators=(',',':'))+'\n'
                    encoded=data.encode('utf-8'); size+=len(encoded)
                    if size>MAX_EXPORT: raise ValueError('Export exceeds bounded size')
                    stream.write(encoded)
                stream.write((json.dumps({'export_complete':True,'first_seq':first_seq,'last_seq':last_seq,'read_stats':read_stats})+'\n').encode('utf-8'))
            self._prune()
            return {'token':token,'text':text,'private':private,'bytes':target.stat().st_size}
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def export_chunk(self, token, offset, text=False, remove=False):
        if not isinstance(token,str) or not ID.fullmatch(token) or type(offset) is not int or not 0<=offset<=MAX_EXPORT:
            raise ValueError('Invalid export cursor')
        path=self.root/'exports'/(token+('.txt' if text else '.jsonl'))
        if path.is_symlink() or not path.is_file(): raise ValueError('Export expired')
        if remove: path.unlink(); return {}
        with open(path,'rb') as stream:
            stream.seek(offset); data=stream.read(128*1024)
        return {'data':base64.b64encode(data).decode('ascii'),'next_offset':offset+len(data),'done':offset+len(data)>=path.stat().st_size}
