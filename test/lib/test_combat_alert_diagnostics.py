"""Actual canonical tracker -> host -> recorder -> fake audio; never game controls."""
from datetime import datetime, timezone
import json
import pytest

from test_combat_v1 import combat
from test_speech_arbiter import arbiter, clock
from test_blackbox import recorder, rows
from test_speech_trace import player, StopPlayback, records
from lib import SpeechTrace as trace
from lib.Event import GameEvent, ConversationEvent
from lib.TTS import TTSLine
from lib.TTSOutcome import TTSAttempt


def lose(c, clock, *, identity=15, age=0):
    # Synthetic source time aligned with the observed incident. No claim that
    # original journal identity/settings, which are unavailable, were recovered.
    event=GameEvent(content={'event':'FighterDestroyed',
        'timestamp':datetime.fromtimestamp(clock.wall-age,timezone.utc).isoformat(),
        **({'ID':identity} if identity is not None else {})},historic=False)
    with trace.event_scope(event): c.plugin.observe(event,c.states)
    return event


def test_observed_loss_scenario_has_full_alert_delivery_correlation(combat,clock,recorder):
    c=combat
    clock.wall=datetime(2026,10,30,20,25,59,tzinfo=timezone.utc).timestamp()
    c.feed('Music',MusicTrack='Combat')
    source=lose(c,clock)
    alarm=c.host.event_manager.incoming.get_nowait();alarm.responded_at=None
    c.run(alarm)
    observations=rows(recorder)
    created=next(r for r in observations if r['stage']=='combat_alert_created')
    assert created['source_event_id']==trace.safe_event_id(source)
    assert created['combat_enabled'] and created['alerts_enabled']
    for stage in ('combat_alert_dispatch_requested','plugin_dispatched','combat_alert_dispatched',
                  'combat_alert_speech_selected','combat_alert_tts_submitted','line_completed','combat_alert_delivery_observed'):
        record=next(r for r in observations if r['stage']==stage)
        assert record['alert_id']==created['alert_id']
    terminal=next(r for r in observations if r['stage']=='line_completed')
    submitted=next(r for r in observations if r['stage']=='combat_alert_tts_submitted')
    assert terminal['delivery_id']==submitted['delivery_id']
    assert terminal['playback_success']=='unknown'
    assert c.host.llmModel.calls==0


@pytest.mark.parametrize('mode,reason',[('missing','missing_fighter_identity'),
                                      ('disabled','alerts_disabled'),('late','expired')])
def test_no_dispatch_has_a_precise_observable_reason(combat,clock,recorder,mode,reason):
    c=combat;c.feed('Music',MusicTrack='Combat')
    if mode=='disabled': c.plugin.settings['alerts']=False
    lose(c,clock,identity=None if mode=='missing' else 15,age=6 if mode=='late' else 0)
    observations=rows(recorder)
    assert any(r.get('reason')==reason for r in observations)
    assert not any(r['stage']=='plugin_dispatched' for r in observations)
    assert c.host.event_manager.incoming.empty()
    if mode=='late':
        removed=next(r for r in observations if r['stage']=='combat_alert_removed')
        assert removed['dispatched'] is False
    assert c.host.llmModel.calls==0


def test_expired_revalidation_and_ticks_do_not_amplify_diagnostics(combat,clock,recorder):
    c=combat;c.feed('Music',MusicTrack='Combat');lose(c,clock)
    alarm=c.host.event_manager.incoming.get_nowait()
    clock.wall+=6
    for _ in range(100):
        assert not c.plugin.should_alert(alarm)
        c.plugin.tracker.tick(clock.wall)
    observations=rows(recorder)
    assert sum(r['stage']=='combat_alert_removed' for r in observations)==1
    assert sum(r['stage']=='combat_alert_revalidation' for r in observations)==1
    removed=next(r for r in observations if r['stage']=='combat_alert_removed')
    assert removed['dispatched'] is True
    assert removed['reason']=='expired'


def test_rapid_duplicate_input_is_one_dispatch_not_quadratic(combat,clock,recorder):
    c=combat;c.feed('Music',MusicTrack='Combat')
    for _ in range(100):lose(c,clock)
    observations=rows(recorder)
    assert sum(r['stage']=='combat_alert_created' for r in observations)==1
    assert sum(r['stage']=='plugin_dispatched' for r in observations)==1
    assert sum(r.get('reason')=='duplicate_telemetry' for r in observations)==99
    assert len(observations)<210


def test_settings_revalidation_changes_and_broken_observer_preserve_policy(combat,clock,recorder):
    c=combat;c.feed('Music',MusicTrack='Combat');lose(c,clock)
    alarm=c.host.event_manager.incoming.get_nowait()
    for value in (True,False,True):
        c.plugin.settings['alerts']=value
        assert c.plugin.should_alert(alarm) is value
    checks=[r for r in rows(recorder) if r['stage']=='combat_alert_revalidation']
    assert [r['accepted'] for r in checks]==[True,False,True]
    c.helper.record_combat_diagnostic=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('broken sink'))
    assert c.plugin.should_alert(alarm)
    c.host._combat_provider=None
    e=GameEvent(content={'event':'FighterDestroyed'},historic=False)
    c.host._process_active_quests=lambda *a:None
    c.host.on_event(e,{})
    assert any(r.get('reason')=='provider_not_registered' for r in rows(recorder))


@pytest.mark.parametrize('mode',['normal','failure','synthesis_failure','drop'])
def test_actual_audio_worker_keeps_alert_ids_and_failure_evidence(combat,clock,records,monkeypatch,mode):
    c=combat;c.feed('Music',MusicTrack='Combat');lose(c,clock)
    alarm=c.host.event_manager.incoming.get_nowait()
    obj,stream=player(monkeypatch,[b'12',b'34',b'56'])
    if mode=='failure':stream.write.side_effect=IOError('PRIVATE device path')
    if mode=='synthesis_failure':obj.tts_model.synthesize=lambda *a: (_ for _ in ()).throw(ValueError('PRIVATE provider body'))
    with trace.combat_alert_scope(alarm):line=obj.say('PRIVATE output',drop_if=lambda:mode=='drop')
    with pytest.raises(IOError if mode=='failure' else StopPlayback):obj._playback_loop()
    evidence=[r for r in records() if r['stage'] in ('tts_attempt_finished','line_completed')]
    assert evidence
    assert all(r['alert_id']==trace.alert_identity(alarm.plugin_event_content) for r in evidence)
    if mode=='failure':assert any(r.get('outcome')=='output_failed' for r in evidence)
    if mode=='synthesis_failure':assert any(r.get('outcome')=='synthesis_failed' for r in evidence)
    assert all(r.get('playback_success')!='success' for r in evidence)
    assert 'PRIVATE' not in json.dumps(records())


def test_failed_terminal_audio_is_not_reported_as_success(combat,clock,recorder):
    c=combat;c.feed('Music',MusicTrack='Combat');lose(c,clock)
    alarm=c.host.event_manager.incoming.get_nowait();alarm.responded_at=None
    def fail(*args,**kwargs):
        line=TTSLine();line.record_attempt(TTSAttempt('a'*32,'output_failed',1,2))
        line.settle('output_failed',reason='device_unavailable');return line
    c.host.tts.say.side_effect=fail;c.run(alarm)
    observations=rows(recorder)
    terminal=next(r for r in observations if r['stage']=='combat_alert_delivery_observed')
    assert terminal['outcome']=='output_failed' and terminal['playback_success']=='unknown'
    assert not c.host.event_manager.add_conversation_event.called


def test_actual_scheduling_gate_results_are_unchanged_and_logged_by_transition(combat,clock,recorder):
    c=combat;c.feed('Music',MusicTrack='Combat');lose(c,clock)
    alarm=c.host.event_manager.incoming.get_nowait();c.host.pending=[alarm]
    for _ in range(100):assert trace.reply_gate(c.host,False,'audio_busy') is False
    assert trace.reply_gate(c.host,False,'stt_capture_active') is False
    assert trace.reply_gate(c.host,True,'audio_busy') is True
    observed=[r for r in rows(recorder) if r['stage']=='combat_alert_scheduling_deferred']
    assert [r['reason'] for r in observed]==['audio_busy','stt_capture_active']


def test_direct_turn_priority_and_batch_arbitration_are_observed_not_changed(combat,clock,recorder):
    from lib.SpeechArbiter import Admission
    from unittest.mock import Mock
    c=combat;c.feed('Music',MusicTrack='Combat');lose(c,clock)
    alarm=c.host.event_manager.incoming.get_nowait();alarm.responded_at=None
    request=ConversationEvent(kind='user',content='Hello',responded_at=None)
    c.run(alarm,request)
    assert c.host.llmModel.calls==1
    assert any(r.get('reason')=='direct_turn_priority' for r in rows(recorder))
    c.host.config['speech_director_mode']='enforce'
    c.host.enabled_game_events=['Music']
    c.host._speech_arbiter.reserve=Mock(return_value=Admission(False))
    native=GameEvent(content={'event':'Music'},historic=False,responded_at=None)
    c.run(alarm,native)
    assert c.host.llmModel.calls==1
    assert any(r.get('reason')=='batch_admission_rejected' for r in rows(recorder))
