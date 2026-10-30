"""Bounded asynchronous UI bridge. Ordinary SupportBundle deliberately never imports this."""
import queue
import threading
from . import SpeechTrace as trace

_commands = queue.Queue(maxsize=4)
_worker = None
_lock = threading.Lock()


def _execute(data):
    recorder=trace._recorder
    if recorder is None: raise ValueError('Recorder unavailable')
    action=data.get('action')
    if action=='status':
        return {'status':recorder.status(),'sessions':recorder.list_sessions()}
    if action=='mode':
        recorder.set_mode(data.get('mode'),data.get('confirm_private') is True)
        return {'status':recorder.status()}
    if action=='limits':
        recorder.configure(data.get('part_mib'),data.get('sessions'))
        return {'status':recorder.status()}
    if action=='activity':
        return {'records':recorder.activity(data.get('session_id'),data.get('component',''),data.get('severity',''),data.get('decision',''))}
    if action=='export':
        return recorder.export(data.get('session_id'),text=data.get('text') is True,
            private=data.get('private') is True,confirmed=data.get('confirm_private') is True)
    if action=='chunk':
        return recorder.export_chunk(data.get('token'),data.get('offset'),data.get('text') is True,data.get('remove') is True)
    raise ValueError('Unknown Black Box command')


def _run():
    while True:
        data, emit = _commands.get()
        try:
            result=_execute(data)
            emit('blackbox_result',request_id=data.get('request_id'),success=True,**result)
        except Exception:
            # No exception text/paths, private data or payloads cross this boundary.
            try: emit('blackbox_result',request_id=data.get('request_id'),success=False)
            except Exception: pass
        finally: _commands.task_done()


def handle_blackbox_command(data,emit):
    global _worker
    try:
        with _lock:
            if _worker is None:
                _worker=threading.Thread(target=_run,name='TARSBlackBoxCommands',daemon=True)
                _worker.start()
        allowed={'action','request_id','mode','confirm_private','session_id','component','severity','decision','text','private','token','offset','remove','part_mib','sessions'}
        request={k:v for k,v in data.items() if k in allowed and type(v) in (str,int,bool) and (not isinstance(v,str) or len(v)<=128)}
        _commands.put_nowait((request,emit))
    except Exception:
        try: emit('blackbox_result',request_id=data.get('request_id'),success=False)
        except Exception: pass
