"""Real file/trace paths with synthetic events, models and audio evidence. No game inputs."""
import base64
from contextlib import contextmanager
import io
import json
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile
import pytest

from lib import SpeechTrace as trace
from lib.BlackBox import Recorder, MAX_RECORD, metadata, redact
from lib.Event import ConversationEvent, GameEvent, PluginEvent
from lib.TTS import TTSLine
from lib.TTSOutcome import TTSAttempt


def wait_for(fn, seconds=3):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if fn(): return
        time.sleep(.01)
    assert fn()


@pytest.fixture
def recorder(tmp_path,monkeypatch):
    box=Recorder(tmp_path/'blackbox')
    monkeypatch.setattr(trace,'_recorder',box)
    monkeypatch.setattr(trace,'enabled',True)
    wait_for(lambda:(box.root/box.session_id/'state.json').is_file())
    yield box
    box.close()


def rows(box, private=False):
    wait_for(lambda:box.queue.unfinished_tasks==0 or box.failed)
    return list(box._records(box.root/box.session_id,private))


def test_event_to_delivery_links_and_standard_privacy(recorder):
    from test_speech_trace import assistant
    event=ConversationEvent(kind='user',content='PRIVATE question',responded_at=None)
    trace.observe_event('conversation_submitted',event)
    host=assistant([event],['PRIVATE final output'])
    def say(*args,**kwargs):
        line=TTSLine()
        line.record_attempt(TTSAttempt('f'*32,'completed',1,2,written_bytes=64))
        line.settle('completed')
        return line
    host.tts.say.side_effect=say
    assert host.should_reply({})
    host.reply_thread({})
    events=rows(recorder)
    receipt=next(r for r in events if r['stage']=='conversation_submitted')
    reply=next(r for r in events if r['stage']=='reply_event')
    model=next(r for r in events if r['stage']=='generation_returned')
    delivery=next(r for r in events if r['stage']=='line_completed')
    assert receipt['event_id']==reply['event_id']
    assert reply['trace_id']==model['trace_id']==delivery['trace_id']
    assert model['generation_id']==delivery['generation_id']
    assert delivery['delivery_id'] and delivery['written_bytes']==64
    assert delivery['playback_success']=='unknown'
    assert 'PRIVATE' not in json.dumps(events)
    assert not list((recorder.root/recorder.session_id).glob('*.private.jsonl'))


def test_journal_and_plugin_causality(recorder):
    event=GameEvent(content={'event':'Scan','timestamp':'2000-01-01T00:00:00Z','id':'Journal.private.log.00001','PlanetClass':'Water world','BodyID':2},historic=False)
    trace.emit('journal_dispatched',component='journal',journal_id=trace.identity(event.content['id']))
    trace.observe_event('event_received',event)
    with trace.event_scope(event):
        plugin=PluginEvent(plugin_event_name='TARSExplorerTarget',plugin_event_content={'body_id':2},responded_at=None)
        trace.observe_event('plugin_dispatched',plugin)
    captured=rows(recorder)
    incoming=next(r for r in captured if r['stage']=='event_received')
    journal=next(r for r in captured if r['stage']=='journal_dispatched')
    dispatched=next(r for r in captured if r['stage']=='plugin_dispatched')
    assert journal['journal_id']==incoming['journal_id']
    assert incoming['event_id']==dispatched['parent_event_id']
    assert incoming['planet_class']=='Water world'
    assert 'Journal.private' not in json.dumps(captured)


def test_model_failure_then_retry_and_silence(recorder):
    from test_speech_trace import FakeLLM
    model=FakeLLM([RuntimeError('PRIVATE provider body'), 'SKIP'])
    with pytest.raises(RuntimeError): model.generate([])
    model.generate([])
    trace.observe_message('TARS Chatter accepted model-selected silence.')
    captured=rows(recorder)
    assert any(r['stage']=='generation_failed' and r['error_type']=='RuntimeError' for r in captured)
    assert any(r.get('reason')=='model_skip' for r in captured)
    attempts=[r['attempt_id'] for r in captured if r['stage']=='generation_started']
    assert len(set(attempts))==2
    assert 'PRIVATE' not in json.dumps(captured)


def test_combat_suppression_and_direct_user_without_controls(recorder):
    from lib.SpeechArbiter import SpeechArbiter
    arbiter=SpeechArbiter()
    arbiter.set_combat_focus('active',True)
    event=PluginEvent(plugin_event_name='TARSExplorerTarget',plugin_event_content={'callout_kind':'scan_value','_guard':{'triggered_at':time.time()}},responded_at=None)
    assert not arbiter.combat_allows(event)
    assert arbiter.combat_allows(ConversationEvent(kind='user',content='What now?'))
    captured=rows(recorder)
    assert any(r['stage']=='combat_focus_changed' and r['outcome']=='active' for r in captured)


def test_verbose_is_private_redacted_and_sanitized_export_strips_it(recorder):
    with pytest.raises(ValueError): recorder.set_mode('verbose')
    recorder.set_mode('verbose',True)
    trace.emit('generation_returned',component='model',_private={'final_output':'Żółć — 航行 🚀','prompt':'NEVER STORE','reasoning':'NEVER STORE'})
    trace.emit('tool_requested',component='tool',_private={'tool_arguments':'{"api_key":"secret-short"}'})
    captured=rows(recorder,True)
    private=[r for r in captured if r.get('private_context')]
    assert any(r['private_context'].get('final_output')=='Żółć — 航行 🚀' for r in private)
    assert 'NEVER STORE' not in json.dumps(captured)
    assert 'secret-short' not in json.dumps(captured)
    exported=recorder.export(recorder.session_id)
    payload=recorder.export_chunk(exported['token'],0)['data']
    decoded=base64.b64decode(payload).decode('utf-8')
    assert 'private_context' not in decoded and 'Żółć' not in decoded
    with pytest.raises(ValueError): recorder.export(recorder.session_id,private=True)
    exported=recorder.export(recorder.session_id,private=True,confirmed=True)
    decoded=base64.b64decode(recorder.export_chunk(exported['token'],0)['data']).decode('utf-8')
    assert 'Żółć' in decoded and 'PRIVATE' in decoded and 'secret-short' not in decoded


@pytest.mark.parametrize('secret',['sk-abcdefghijklmnopqrstuvwxyz123456','Bearer abcdef','https://user:pass@host/path','C:\\Users\\Private\\file','/home/private/file','email@example.com','password is short','api_key="short"'])
def test_private_redaction(secret):
    assert secret not in redact('context '+secret)


def test_standard_allowlist_blocks_arbitrary_strings(recorder):
    trace.emit('generation_failed',component='model',reason='MY_PRIVATE_PASSWORD',model='sk-private-secret',error_type='UserName',token='raw',path='C:\\Users\\Private')
    data=json.dumps(rows(recorder))
    assert 'MY_PRIVATE_PASSWORD' not in data and 'sk-private-secret' not in data and 'UserName' not in data
    assert 'C:\\\\Users' not in data


def test_concurrent_producers_are_ordered_and_bounded(tmp_path):
    box=Recorder(tmp_path/'logs',queue_size=4096)
    threads=[threading.Thread(target=lambda:[box.record({'stage':'event_received','count':i}) for i in range(200)]) for _ in range(6)]
    for t in threads:t.start()
    for t in threads:t.join()
    box.close()
    data=rows(box)
    seq=[r['seq'] for r in data]
    assert seq==sorted(set(seq))
    assert box.queue.maxsize==4096 and len(box.recent)<=500
    assert len(data)+box.dropped>=1200


def test_rotation_retention_and_record_size(tmp_path):
    box=Recorder(tmp_path/'logs',part_bytes=MAX_RECORD,parts=3,queue_size=4096)
    box.set_mode('verbose',True)
    wait_for(lambda:(box.root/box.session_id).is_dir())
    for _ in range(150):box.record({'stage':'generation_returned'}, {'final_output':'Żółć '*700})
    box.close()
    files=box._files(box.root/box.session_id,True)
    assert len(files)<=3
    assert all(p.stat().st_size<=MAX_RECORD for p in files)
    assert box.pruned_parts>0


def test_crash_tail_and_restart_reset_private_mode(tmp_path):
    first=Recorder(tmp_path/'logs');first.set_mode('verbose',True)
    first.close()
    folder=first.root/first.session_id
    state=json.loads((folder/'state.json').read_text(encoding='utf-8'));state['clean_shutdown']=False
    (folder/'state.json').write_text(json.dumps(state),encoding='utf-8')
    with open(first._files(folder)[-1],'ab') as stream:stream.write(b'{"truncated":')
    second=Recorder(first.root)
    try:
        wait_for(lambda:(second.root/second.session_id/'state.json').is_file())
        assert second.mode=='standard'
        old=next(s for s in second.list_sessions() if s['session_id']==first.session_id)
        assert not old['clean_shutdown']
        exported=second.export(first.session_id,text=True)
        data=base64.b64decode(second.export_chunk(exported['token'],0,text=True)['data'])
        assert b'truncated' not in data and b'session_stopped' in data
    finally: second.close()


def test_disk_failure_never_escapes_to_producer(tmp_path):
    root=tmp_path/'not-a-directory';root.write_text('blocked',encoding='utf-8')
    box=Recorder(root)
    wait_for(lambda:box.failed)
    for _ in range(3000):box.record({'stage':'event_received'})
    assert box.queue.qsize()<=2048
    box.close()


def test_trace_sink_failure_does_not_change_model_result(monkeypatch):
    from test_speech_trace import FakeLLM
    monkeypatch.setattr(trace,'enabled',True)
    monkeypatch.setattr(trace,'_recorder',SimpleNamespace(record=Mock(side_effect=OSError('disk failed'))))
    assert FakeLLM(['answer']).generate([])[0]=='answer'


def test_session_id_and_export_cursor_are_not_paths(recorder,tmp_path):
    for value in ('../secret','C:\\Users\\secret','a'*31,'a'*32+'../'):
        with pytest.raises(ValueError):recorder.export(value)
        with pytest.raises(ValueError):recorder.export_chunk(value,0)
    external=tmp_path/'outside';external.mkdir()
    try:(recorder.root/('a'*32)).symlink_to(external,target_is_directory=True)
    except OSError:pytest.skip('Symlink creation unavailable on this runner')
    with pytest.raises(ValueError):recorder.export('a'*32)


def test_support_bundle_does_not_include_blackbox_private_stream(recorder):
    from lib.SupportBundle import build_support_bundle
    recorder.set_mode('verbose',True)
    trace.emit('generation_returned',_private={'final_output':'PRIVATE_SENTENCE'})
    payload=build_support_bundle({}, {})
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload))) as archive:
        assert not any('blackbox' in n.lower() for n in archive.namelist())
        assert all(b'PRIVATE_SENTENCE' not in archive.read(n) for n in archive.namelist())


def test_explorer_reports_existing_reason_not_an_invented_explanation(recorder):
    old={'outcome':'dispatched'}
    plugin=SimpleNamespace(_callout_decisions=[old])
    marker=trace.plugin_marker(plugin)
    plugin._callout_decisions.append({'outcome':'suppressed: same-body cooldown (3.1s)','expected_callout':True,'planet_class':'Water world','full_name':'PRIVATE SYSTEM','reasons':['valuable']})
    event=GameEvent(content={'event':'Scan','timestamp':'2000-01-01T00:00:00Z'},historic=False)
    trace.plugin_decisions(plugin,event,marker)
    record=next(r for r in rows(recorder) if r['stage']=='explorer_decision')
    assert record['reason']=='same_body_cooldown' and record['expected_callout'] and not record['accepted']
    assert 'PRIVATE SYSTEM' not in json.dumps(record)


def test_real_chatter_abstention_does_not_add_model_calls(recorder, monkeypatch):
    from test_speech_trace import chatter, FakeLLM
    plugin=chatter(); model=FakeLLM(['SKIP'])
    plugin._llm_model=model; plugin._original_generate=model.generate
    monkeypatch.setattr(plugin,'_recent_situational_anchors',lambda *args:[{'event':'Touchdown'}])
    monkeypatch.setattr(plugin,'_choose_chatter_topics',lambda *a,**k:['ship','navigation'])
    assert plugin._prepare_chatter_line() is None
    assert model.calls==1
    assert any(r.get('reason')=='model_skip' for r in rows(recorder))


def test_tool_permissions_and_observed_result_without_game_controls(recorder, monkeypatch):
    from lib.ActionManager import ActionManager
    from openai.types.chat import ChatCompletionMessageFunctionToolCall
    monkeypatch.setattr('lib.ActionManager.KeyValueStore',Mock())
    manager=ActionManager(); method=Mock(return_value='{"ok":true,"mapping_recommendation":{"body":"PRIVATE BODY"}}')
    manager.set_allowed_actions({'fireWeapons':True})
    manager.configure_permissions(lambda:{'allowed_actions':{'fireWeapons':True},'action_permissions':{'fireWeapons':'block'}},Mock())
    manager.registerAction('fireWeapons','Synthetic',{},method,permission='fireWeapons')
    call=ChatCompletionMessageFunctionToolCall(id='safe',type='function',function={'name':'fireWeapons','arguments':'{}'})
    result=manager.runAction(call,{})
    assert 'Not executed' in result['content']; method.assert_not_called()
    assert any(r.get('reason')=='block' for r in rows(recorder))
    trace.observe_tool_result('tars_explorer_system_summary',method.return_value)
    assert any(r.get('mapping_recommendation_present') is True for r in rows(recorder))
    assert 'PRIVATE BODY' not in json.dumps(rows(recorder))


def test_session_retention_and_limits_persist_without_verbose(tmp_path):
    first=Recorder(tmp_path/'logs');wait_for(lambda:(first.root/first.session_id/'state.json').is_file())
    first.configure(1,1);first.set_mode('verbose',True);first.close()
    second=Recorder(first.root)
    try:
        wait_for(lambda:(second.root/second.session_id/'state.json').is_file())
        wait_for(lambda:len(second.list_sessions())==1)
        assert second.mode=='standard' and second.part_bytes==1024*1024
        assert second.sessions_limit==1
    finally: second.close()


def test_export_chunking_and_partial_write_evidence(recorder):
    for _ in range(600):recorder.record({'stage':'event_received','input_chars':100})
    rows(recorder)
    files=recorder._files(recorder.root/recorder.session_id)
    # Export deliberately damaged copied tail in a closed session.
    recorder.close()
    with open(files[-1],'ab') as stream:stream.write(b'{"partial"')
    exported=recorder.export(recorder.session_id)
    chunks=[];offset=0
    while True:
        chunk=recorder.export_chunk(exported['token'],offset)
        raw=base64.b64decode(chunk['data']); assert len(raw)<=128*1024
        chunks.append(raw);offset=chunk['next_offset']
        if chunk['done']:break
    result=[json.loads(line) for line in b''.join(chunks).decode('utf-8').splitlines()]
    assert result[-1]['export_complete'] and result[-1]['read_stats']['partial_or_oversize']==1
    assert len(chunks)>1
    recorder.export_chunk(exported['token'],0,remove=True)
    with pytest.raises(ValueError):recorder.export_chunk(exported['token'],0)


def test_counter_sampling_excludes_observatory_paths(recorder,monkeypatch):
    bridge=type('TARSObservatoryBridge',(),{})()
    bridge._status={'ignored_historical':42,'ignored_non_notification':2,'relayed':1,'malformed':0,'last_error':'C:\\PRIVATE\\data'}
    monkeypatch.setattr(trace,'_plugin_manager',SimpleNamespace(plugin_list={'bridge':bridge}))
    monkeypatch.setattr(trace,'_sampled',{})
    trace.sample_plugins();trace.sample_plugins()
    captured=rows(recorder)
    assert sum(r.get('reason')=='historical_ignored' for r in captured)==1
    assert 'PRIVATE' not in json.dumps(captured)


def test_ui_commands_are_bounded_and_do_not_export_without_confirmation(recorder):
    from lib.BlackBoxCommands import _execute
    result=_execute({'action':'status'})
    assert result['status']['session_id']==recorder.session_id
    with pytest.raises(ValueError):_execute({'action':'mode','mode':'verbose'})
    with pytest.raises(ValueError):_execute({'action':'export','session_id':recorder.session_id,'private':True})
    assert _execute({'action':'activity','session_id':recorder.session_id})['records']


def test_backpressure_is_bounded_and_does_not_create_a_loss_feedback_loop(tmp_path):
    entered=threading.Event(); release=threading.Event()
    class HeldRecorder(Recorder):
        def _state(self,clean=False):
            if not entered.is_set():
                entered.set(); release.wait(2)
            return super()._state(clean)
    box=HeldRecorder(tmp_path/'logs',queue_size=1)
    assert entered.wait(1)
    for _ in range(500):box.record({'stage':'event_received'})
    assert box.queue.qsize()==1 and box.dropped>=499
    release.set();box.close()
    assert box.written<10
    assert box.queue.qsize()==0


def test_global_disk_budget_and_export_failure_cleanup(tmp_path,monkeypatch):
    import lib.BlackBox as storage
    monkeypatch.setattr(storage,'MAX_DISK',32768)
    box=Recorder(tmp_path/'logs',part_bytes=MAX_RECORD,parts=16,queue_size=4096)
    for _ in range(800):box.record({'stage':'event_received','count':100})
    box.close()
    assert sum(p.stat().st_size for p in box._files(box.root/box.session_id,True)) <= 32768+MAX_RECORD
    monkeypatch.setattr(storage,'MAX_EXPORT',10)
    with pytest.raises(ValueError):box.export(box.session_id)
    assert not list((box.root/'exports').glob('*.jsonl'))


def test_verbose_drops_explicit_internal_reasoning_and_credentials():
    assert 'HIDDEN' not in redact('{"reasoning":"HIDDEN"}')
    assert 'HIDDEN' not in redact('<think>HIDDEN</think>')
    assert '123456' not in redact('{"token":"123456"}')


def test_chatter_reservation_correlates_candidate_and_dispatch(recorder):
    reservation='c'*32
    token=trace.current_reservation.set(reservation)
    try:
        from test_speech_trace import FakeLLM
        FakeLLM(['A grounded line.']).generate([])
        trace.observe_event('plugin_dispatched',PluginEvent(plugin_event_name='TARSChatter',plugin_event_content={'_speech_admission':reservation}))
    finally:trace.current_reservation.reset(token)
    captured=rows(recorder)
    assert {r['reservation_id'] for r in captured if r['stage'] in ('generation_started','plugin_dispatched')}=={reservation}


def test_explicit_utf8_private_files_and_export(recorder):
    recorder.set_mode('verbose',True)
    trace.emit('generation_returned',_private={'final_output':'Żółć — 航行 🚀'})
    rows(recorder)
    private=next(p for p in recorder._files(recorder.root/recorder.session_id,True) if '.private.' in p.name)
    assert 'Żółć' in private.read_bytes().decode('utf-8')
    exported=recorder.export(recorder.session_id,text=True,private=True,confirmed=True)
    data=base64.b64decode(recorder.export_chunk(exported['token'],0,text=True)['data']).decode('utf-8')
    assert 'Żółć' in data
