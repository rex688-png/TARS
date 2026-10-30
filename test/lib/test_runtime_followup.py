"""Resource ownership and concurrent diagnostics tests; no physical audio/gameplay."""
from unittest.mock import Mock
import threading
import queue
import pytest

from lib.STT import STT
from lib.BlackBox import Recorder


@pytest.mark.parametrize('failure', [None, 'enumerate', 'open', 'close'])
def test_microphone_owner_terminated_exactly_once(monkeypatch, failure):
    import lib.STT as module
    stream = Mock()
    owner = Mock()
    owner.get_default_host_api_info.return_value = {'deviceCount': 0}
    owner.open.return_value = stream
    if failure == 'enumerate': owner.get_default_host_api_info.side_effect = OSError('device lost')
    if failure == 'open': owner.open.side_effect = OSError('device lost')
    if failure == 'close': stream.close.side_effect = OSError('device lost')
    monkeypatch.setattr(module.pyaudio, 'PyAudio', lambda: owner)
    stt = STT.__new__(STT)
    stt.input_device_name = 'synthetic'
    stt.rate = 16000
    stt.frames_per_buffer = 512
    if failure in ('enumerate', 'open'):
        with pytest.raises(OSError): stt._get_microphone()
    else:
        source = stt._get_microphone()
        if failure == 'close':
            with pytest.raises(OSError): source.close()
        else: source.close()
        source.close()  # Idempotent even after a driver close error.
        stream.close.assert_called_once()
    owner.terminate.assert_called_once()


def test_diagnostics_saturation_does_not_block_concurrent_event_callbacks(tmp_path, monkeypatch):
    # Saturate using real producer calls while the writer cannot consume.
    entered = threading.Event()
    release = threading.Event()
    original = Recorder._prune
    def blocked_maintenance(self):
        entered.set()
        release.wait(3)
        original(self)
    monkeypatch.setattr(Recorder, '_prune', blocked_maintenance)
    box = Recorder(tmp_path / 'blackbox', queue_size=8)
    assert entered.wait(2)
    completed = []
    def events():
        for _ in range(2000):
            box.record({'component': 'event', 'stage': 'event_received'})
            completed.append(1)  # Stands for an application callback, not game input.
    threads = [threading.Thread(target=events) for _ in range(4)]
    try:
        for worker in threads: worker.start()
        for worker in threads: worker.join(2)
        assert all(not worker.is_alive() for worker in threads)
        assert len(completed) == 8000
        assert box.queue.qsize() <= 8
        assert box.dropped > 0
    finally:
        release.set()
        box.close()


def test_concurrent_processing_serializes_callbacks_and_preserves_events():
    from lib.EventManager import EventManager
    from lib.Event import GameEvent
    manager = EventManager.__new__(EventManager)
    manager._processing_lock = threading.Lock()
    manager.incoming = queue.Queue()
    manager.pending, manager.processed, manager.projections = [], [], []
    manager.short_term_memory = Mock()
    manager.save_projections = Mock()
    manager.update_projections = Mock(return_value=[])
    delivered = []
    manager.sideeffects = [lambda event, state: delivered.append(event.content['number'])]
    for number in range(2000):
        manager.incoming.put(GameEvent(content={'event': 'Scan', 'number': number}, historic=False))
    workers = [threading.Thread(target=manager.process) for _ in range(4)]
    for worker in workers: worker.start()
    for worker in workers: worker.join(5)
    assert all(not worker.is_alive() for worker in workers)
    assert delivered == list(range(2000))
    assert len(manager.processed) == 2000
    assert not manager.pending and manager.incoming.empty()
    manager.short_term_memory.commit.assert_called_once()


def test_plugin_stop_failure_does_not_skip_other_plugins():
    from lib.PluginManager import PluginManager
    from types import SimpleNamespace
    manager = PluginManager.__new__(PluginManager)
    broken, healthy = Mock(), Mock()
    broken.plugin_manifest = SimpleNamespace(name='synthetic failed plugin')
    healthy.plugin_manifest = SimpleNamespace(name='synthetic healthy plugin')
    broken.on_chat_stop.side_effect = RuntimeError('synthetic stop failure')
    manager.plugin_list = {'a': broken, 'b': healthy}
    helper = Mock()
    manager.on_chat_stop(helper)
    healthy.on_chat_stop.assert_called_once_with(helper)
