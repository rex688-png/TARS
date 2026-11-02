"""Negative traces are compressed; gameplay eligibility is never cached."""
import json
from lib.BlackBox import Recorder, RejectionWindow


def rejection(**changes):
    return {'stage':'reply_not_selected','component':'combat','reason':'combat_focus',
            'event_id':'a'*24,'journal_id':'b'*24, **changes}


def test_repeated_rejections_keep_first_and_count_without_false_parent_causality():
    window = RejectionWindow()
    initial = rejection(parent_event_id='c'*24)
    assert window.observe(initial, 1) == [initial]
    for n in range(999):
        assert window.observe(rejection(parent_event_id='d'*24), 2+n/1000) == []
    summary, = window.flush(31)
    assert summary['count'] == 999
    assert summary['event_id'] == initial['event_id']
    assert summary['journal_id'] == initial['journal_id']
    assert 'parent_event_id' not in summary
    assert summary['repeat_first_ms'] == 2000
    assert summary['repeat_last_ms'] == 2998
    assert window.flush(100) == []


def test_changed_reasons_new_events_and_positive_outcomes_are_immediate():
    window = RejectionWindow()
    for row in [rejection(), rejection(reason='reaction_disabled'),
                rejection(event_id='e'*24), rejection(stage='reply_selected'),
                rejection(stage='plugin_dispatched'), rejection(stage='event_processed')]:
        assert window.observe(row, 1) == [row]
    assert window.observe(rejection(), 2) == []
    output = window.observe(rejection(), 32)
    assert output[0]['stage'] == 'reply_rejections_coalesced'
    assert output[0]['count'] == 1
    assert output[1]['stage'] == 'reply_not_selected'


def test_cache_eviction_preserves_counts_and_bounds_memory():
    window = RejectionWindow(capacity=2)
    window.observe(rejection(), 1)
    window.observe(rejection(), 2)
    window.observe(rejection(event_id='c'*24), 3)
    rows = window.observe(rejection(event_id='d'*24), 4)
    assert len(window.entries) == 2
    assert rows[0]['stage'] == 'reply_rejections_coalesced'
    assert rows[0]['count'] == 1
    assert len(window.flush(5, force=True)) == 0
    assert not window.entries


def test_recorder_flushes_summary_on_close_and_sanitized_export(tmp_path):
    box = Recorder(tmp_path/'box', queue_size=2048)
    # Explicit lock holds no runtime state or producer thread. Feed the real
    # queue path deterministically to distinguish coalescing from saturation.
    with box.lock:
        for i in range(1000):
            for row in box.rejections.observe(rejection(), 1+i/1000):
                box._enqueue_locked(row)
        box._enqueue_locked({'stage':'event_received','component':'event','event_id':'a'*24})
        box._enqueue_locked({'stage':'event_processed','component':'event','event_id':'a'*24})
    box.close()
    rows = list(box._records(box.root/box.session_id))
    assert not box.failed and box.dropped == 0
    assert sum(r.get('stage')=='reply_not_selected' for r in rows) == 1
    assert sum(r.get('count',0) for r in rows if r.get('stage')=='reply_rejections_coalesced') == 999
    assert sum(r.get('stage')=='event_processed' for r in rows) == 1
    artifact = box.export(box.session_id)
    exported = (box.root/'exports'/(artifact['token']+'.jsonl')).read_text(encoding='utf-8')
    assert 'reply_rejections_coalesced' in exported
    assert 'repeat_first_ms' in exported
    assert box.rejections.entries == {}


def test_public_record_path_never_caches_delivery_or_private_context(tmp_path):
    box = Recorder(tmp_path/'box')
    box.record(rejection(), {'final_output':'PRIVATE'})
    box.record(rejection(), {'final_output':'PRIVATE'})
    box.record({'stage':'line_completed','delivery_id':'c'*32})
    box.record({'stage':'line_completed','delivery_id':'d'*32})
    box.close()
    rows = list(box._records(box.root/box.session_id))
    assert len([r for r in rows if r.get('stage')=='line_completed']) == 2
    assert 'PRIVATE' not in json.dumps(rows)
    assert any(r.get('stage')=='reply_rejections_coalesced' for r in rows)


def test_distinct_status_facts_with_identical_clock_samples_have_distinct_trace_ids(monkeypatch):
    from lib import SpeechTrace as trace
    from lib.Event import StatusEvent
    monkeypatch.setattr(trace, 'enabled', True)
    timestamp = '2000-01-01T00:00:00+00:00'
    first = StatusEvent(timestamp=timestamp, status={'event':'Status','flags':{'InDanger':True}})
    changed = StatusEvent(timestamp=timestamp, status={'event':'InDanger'})
    different_flags = StatusEvent(timestamp=timestamp, status={'event':'Status','flags':{'InDanger':False}})
    ids = {trace.event_fields(e)['event_id'] for e in (first,changed,different_flags)}
    assert len(ids) == 3
    previous = trace.event_fields(first)['event_id']
    first.responded_at = 10
    assert trace.event_fields(first)['event_id'] == previous
    restored = StatusEvent(timestamp=timestamp, status=dict(first.status))
    assert trace.event_fields(restored)['event_id'] == previous
    assert '_blackbox_event_id' not in vars(first)
