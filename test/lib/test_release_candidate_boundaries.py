"""Exercise release safety branches from production source without audio hardware."""
import ast
import copy
import queue
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[2]


def _class(source, name):
    tree = ast.parse((ROOT / source).read_text(encoding='utf-8'))
    return next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)


def _method(source, owner, name):
    return copy.deepcopy(next(node for node in _class(source, owner).body
                              if isinstance(node, ast.FunctionDef) and node.name == name))


def test_stop_speaking_drains_queued_lines_and_sets_active_abort_without_destroying_tts():
    line_class = copy.deepcopy(_class('src/lib/TTS.py', 'TTSLine'))
    abort = _method('src/lib/TTS.py', 'TTS', 'abort')
    harness_class = ast.ClassDef(name='PlaybackHarness', bases=[], keywords=[],
                                 body=[abort], decorator_list=[])
    namespace = {'threading':threading, 'queue':queue}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[line_class,harness_class],type_ignores=[])),
                 str(ROOT/'src/lib/TTS.py'),'exec'),namespace)
    line = namespace['TTSLine']()
    instance = namespace['PlaybackHarness']()
    instance.read_queue = queue.Queue()
    instance.read_queue.put({'line':line})
    instance._normalize_queue_item = lambda item:item
    instance.is_aborted = False
    assert not line.is_completed()
    instance.abort()
    assert instance.is_aborted and line.is_completed() and line.wait_for_speaking() is False
    assert instance.read_queue.empty()
    # A later utterance gets its own line and is not marked completed by the old stop.
    next_line = namespace['TTSLine']()
    assert not next_line.is_completed()
    next_line.mark_speaking();assert next_line.wait_for_speaking()
    next_line.mark_completed();assert not next_line.is_speaking()


def test_active_playback_stops_after_abort_before_writing_next_chunk():
    playback = _method('src/lib/TTS.py', 'TTS', '_playback_one')
    playback.decorator_list = []
    playback.returns = None
    for arg in playback.args.args:
        arg.annotation = None
    namespace = {'strip_markdown':SimpleNamespace(strip_markdown=lambda text:text),
                 'normalize_spoken_quantities':lambda text:text,'time':lambda:0.0,
                 'log':lambda *args:None,'log_tts_usage':lambda *args,**kwargs:None,
                 'LatencyUsageStats':lambda **kwargs:kwargs,'AudioUsageStats':lambda **kwargs:kwargs,
                 'TextUsageStats':lambda **kwargs:kwargs}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[playback],type_ignores=[])),
                 str(ROOT/'src/lib/TTS.py'),'exec'),namespace)
    class Harness:
        is_aborted=False
        prebuffer_size=1
        sample_size=2
        tts_model=SimpleNamespace(provider_name='test',model_name='test')
        def _reset_postprocessing_state(self):pass
        def _get_effective_postprocessing_config(self,*args):return None
        def _stream_audio(self,*args):return iter([b'1',b'2',b'3'])
        def _apply_output_gain_pcm16(self,chunk):return chunk
    player=Harness();stream=Mock();stream.get_write_available.return_value=1
    stream.write.side_effect=lambda *args,**kwargs:setattr(player,'is_aborted',True)
    namespace['_playback_one'](player,'spoken text',stream)
    assert stream.write.call_count==1
    player.is_aborted=False;stream.write.side_effect=None;stream.reset_mock()
    namespace['_playback_one'](player,'next response',stream)
    assert stream.write.call_count==3


def test_empty_model_response_marks_turn_complete_without_visible_placeholder():
    method=_method('src/lib/Assistant.py','Assistant','reply_thread')
    empty=next(node for node in ast.walk(method) if isinstance(node,ast.If)
               and ast.unparse(node.test).startswith('not response_text and'))
    branch=ast.FunctionDef(name='empty_branch',args=ast.arguments(posonlyargs=[],args=[
        ast.arg(arg='self'),ast.arg(arg='response_text'),ast.arg(arg='response_actions'),
        ast.arg(arg='max_conversation_processed')],vararg=None,kwonlyargs=[],kw_defaults=[],
        kwarg=None,defaults=[]),body=[copy.deepcopy(empty)],decorator_list=[])
    namespace={'time':lambda:0.0,'log':lambda *args:None}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[branch],type_ignores=[])),
                 str(ROOT/'src/lib/Assistant.py'),'exec'),namespace)
    manager=SimpleNamespace(short_term_memory=SimpleNamespace(replied_before=Mock()),
                            add_assistant_complete_event=Mock())
    namespace['empty_branch'](SimpleNamespace(event_manager=manager),None,None,42)
    manager.short_term_memory.replied_before.assert_called_once_with(42)
    manager.add_assistant_complete_event.assert_called_once()
    assert 'response_text = "..."' not in (ROOT/'src/lib/Assistant.py').read_text()


def test_prompt_logs_exclude_prompt_and_conversation_slices():
    source=(ROOT/'src/lib/PromptGenerator.py').read_text()
    assert "log('debug', 'conversation', prompt_json)" not in source
    assert 'self.previous_prompt_json[start:end]' not in source
    assert 'prompt_json[start:end]' not in source
    assert "event_name, content)" not in source


def test_stop_speaking_wiring_reaches_shared_tts_abort():
    ui=(ROOT/'ui/src/app/main-view/main-view.component.ts').read_text()
    template=(ROOT/'ui/src/app/main-view/main-view.component.html').read_text()
    backend=(ROOT/'src/Chat.py').read_text()
    assert "send_command({type:'interrupt_tts'" in ui
    assert '(click)="interruptSpeech()"' in template
    assert 'if data.get("type") == "interrupt_tts":\n                chat.tts.abort()' in backend
