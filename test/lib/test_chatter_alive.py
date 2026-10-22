"""Deterministic session opportunities, actual Session wrappers and host delivery."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_chatter_admission import integration
from test_speech_arbiter import arbiter, clock, finding
from test_speech_trace import records, user
from lib.Event import GameEvent, ConversationEvent, StatusEvent
from lib.Logger import PromptUsageStats
from lib.TTS import TTSLine
from lib.TTSOutcome import TTSAttempt

TRAVEL = 'Three arrivals recorded this session; at least the navigation log is getting some exercise.'
FIELD = 'One sampling log this session; field work does make a pleasant change from transit.'


@pytest.fixture
def alive(integration, clock, monkeypatch):
    def make(mode='enforce', responses=None, callback=None):
        run = integration(mode, responses or [TRAVEL, FIELD], callback)
        for name in ('_recent_situational_anchors', '_choose_chatter_topics', '_chatter_premises'):
            delattr(run.plugin, name)  # Use real context/topic/premise code rather than old fixture doubles.
        monkeypatch.setattr(run.plugin._fire.__func__.__globals__['random'], 'shuffle', lambda values: None)
        run.plugin._schedule_event_opportunity = Mock()
        monkeypatch.setattr(run.plugin, '_main_covas_system_index', lambda messages: 0)
        def say(*args, **kwargs):
            line = TTSLine()
            line.mark_speaking()
            line.record_attempt(TTSAttempt('fake', 'completed', 0, 1, written_bytes=4, output_drained=True))
            line.settle('completed')
            return line
        run.host.tts.say.side_effect = say
        return run
    return make


def seed(run, clock, count=3):
    for _ in range(count):
        run.plugin._observe_event(GameEvent(content={'event':'FSDJump','StarSystem':'PRIVATE OLD LOCATION'},historic=False), {})
    clock.wall += 150


def deliver(run, clock):
    event = run.host.event_manager.incoming.get_nowait()
    event.timestamp = datetime.fromtimestamp(clock.wall, timezone.utc).isoformat()
    event.responded_at = None
    run.host.on_event(event,{})
    run.host.event_manager.get_short_term_memory.return_value = [event]
    run.host.prompt_generator.generate_prompt.return_value = (
        [{'role':'system','content':'You are TARS.'},
         {'role':'user','content':'[External Event]\n'+run.plugin._chatter_prompt(event)}],PromptUsageStats())
    run.host.reply_thread({})
    text=run.host.event_manager.add_conversation_event.call_args.args[1]
    run.plugin._observe_event(ConversationEvent(kind='assistant',content=text),{})


@pytest.mark.parametrize('mode',['off','observe','enforce'])
def test_active_30_minute_exploration_has_real_conversational_opportunities(alive, clock, mode, records):
    run=alive(mode)
    settings=dict(run.plugin.settings)
    for minute in range(5,31,5):
        clock.wall=1000+minute*60-150
        run.plugin._observe_event(GameEvent(content={'event':'FSDJump','StarSystem':'PRIVATE'},historic=False),{})
        if minute==25:
            run.plugin._observe_event(GameEvent(content={'event':'ScanOrganic','ScanType':'Log','Body':'PRIVATE'},historic=False),{})
        clock.wall+=110
        run.plugin._observe_event(ConversationEvent(kind='assistant',content='Synthetic ordinary Explorer callout.'),{})
        clock.wall+=40
        run.fire()
        if not run.host.event_manager.incoming.empty():
            deliver(run,clock)
    assert run.host.llmModel.calls==2  # Candidates only; prepared host delivery makes no new model request.
    assert run.host.tts.say.call_count==2
    assert run.plugin.diagnostic_counts['dispatched']==2
    assert run.plugin.diagnostic_counts['context_missing']==2
    assert run.plugin.diagnostic_counts['cooldown']==2
    assert run.host._chatter_delivery_counts=={'completed':2}
    assert run.plugin.settings==settings
    assert 'PRIVATE' not in json.dumps(records())


def test_quiet_verified_session_facts_are_used_without_stale_location(alive, clock):
    run=alive(responses=['SKIP'])
    seed(run,clock)
    run.fire()
    assert run.host.llmModel.calls==1
    assert run.plugin.diagnostic_counts['session_context']==1
    assert run.plugin.diagnostic_counts['model_skip']==1
    run.fire()
    assert run.host.llmModel.calls==1
    assert run.plugin.diagnostic_counts['context_used']==1
    assert run.host.event_manager.incoming.empty()


@pytest.mark.parametrize('case',['empty','historic','expired'])
def test_insufficient_context_never_requests_the_model(alive,clock,case):
    run=alive()
    if case=='historic':
        for _ in range(5):
            run.plugin._observe_event(GameEvent(content={'event':'FSDJump'},historic=True),{})
    elif case=='expired':
        seed(run,clock)
        clock.wall+=901
    run.fire()
    assert run.host.llmModel.calls==0
    assert run.plugin.diagnostic_counts['context_missing']==1
    assert not run.helper._assistant.speech_arbiter()._optional


def test_fallback_prompt_contains_only_verified_session_not_old_ship_state(alive,clock):
    captured=[]
    run=alive(responses=['SKIP'])
    seed(run,clock)
    original=run.plugin._original_generate
    def generate(*args,**kwargs):
        captured.append(kwargs['messages'])
        return original(*args,**kwargs)
    run.plugin._original_generate=generate
    run.fire()
    prompt=json.dumps(captured)
    assert 'VERIFIED SESSION PROGRESS' in prompt
    assert 'PRIVATE OLD LOCATION' not in prompt
    assert 'NOT completed organisms' in prompt
    assert 'fourth-wall' in prompt


@pytest.mark.parametrize('mode',['off','observe','enforce'])
def test_busy_host_admission_precedes_even_session_generation(alive,clock,arbiter,mode):
    run=alive(mode)
    seed(run,clock)
    event=finding()
    event.plugin_event_content['_guard']['triggered_at']=clock.wall
    active=arbiter.reserve([event],{},mode)
    assert active.allowed
    run.fire()
    assert run.host.llmModel.calls==(0 if mode=='enforce' else 1)
    if mode=='enforce':
        assert run.plugin.diagnostic_counts['host_admission']==1
    arbiter.finish(active)


def test_safety_status_remains_a_guard_after_the_short_activity_cooldown(alive,clock):
    run=alive()
    seed(run,clock)
    run.plugin._observe_event(StatusEvent(status={'event':'Status','flags':{'InDanger':True}}),{})
    clock.wall+=120
    run.fire()
    assert run.host.llmModel.calls==0
    assert run.plugin.diagnostic_counts['game_activity']==1
    run.plugin._observe_event(StatusEvent(status={'event':'Status','flags':{'InDanger':False}}),{})
    run.fire()
    assert run.host.llmModel.calls==1


def test_direct_question_during_session_candidate_prevents_dispatch(alive,clock):
    def arrive(host,plugin,count):
        host.event_manager.incoming.put(user())
    run=alive(callback=arrive)
    seed(run,clock)
    run.fire()
    assert run.host.llmModel.calls==1
    assert run.plugin.diagnostic_counts['host_admission']==1
    assert run.host.event_manager.incoming.qsize()==1  # Only the direct question.


def test_repeated_premise_is_rejected_without_unbounded_creative_calls(alive,clock):
    run=alive(responses=['Another landing, another argument with gravity.'])
    seed(run,clock)
    run.plugin._chatter_premise_last['landing_premise']=clock.wall
    run.fire()
    assert run.host.llmModel.calls==1
    assert run.plugin.diagnostic_counts['quality_rejected']==1
    assert run.host.event_manager.incoming.empty()
    run.fire()
    assert run.host.llmModel.calls==1


@pytest.mark.parametrize('outcome',['interrupted','dropped','output_failed','no_audio'])
def test_host_delivery_diagnostics_distinguish_non_success(alive,clock,outcome,records):
    run=alive()
    seed(run,clock)
    run.fire()
    def say(*args,**kwargs):
        line=TTSLine()
        line.settle(outcome)
        return line
    run.host.tts.say.side_effect=say
    deliver(run,clock)
    assert run.host._chatter_delivery_counts=={outcome:1}
    assert any(r['stage']=='chatter_delivery' and r['outcome']==outcome for r in records())
    assert all(r.get('playback_success')!='success' for r in records())


def test_visible_labels_and_existing_setting_keys_survive_restart(alive,clock,tmp_path):
    run=alive()
    saved={'min_seconds':240,'max_seconds':420,'silence_chance':65,'director_enabled':False,
           'output_guard':True,'minimum_remark_gap':660}
    run.plugin.settings=dict(saved)
    run.helper.get_plugin_data_path=lambda manifest:str(tmp_path)
    seed(run,clock)
    run.plugin.on_chat_start(run.helper)
    assert run.plugin.settings==saved
    assert run.plugin._session_fact_at is None and run.plugin._session['jumps']==0
    schema=run.plugin.settings_config
    if hasattr(schema,'model_dump'): schema=schema.model_dump()
    assert schema['label']=='TARS Chatter'
    assert schema['key']=='TARSChatterPlugin'
    director=next(grid for grid in schema['grids'] if grid['key']=='director')
    assert director['label']=='Response Quality'
    assert {'director_enabled','output_guard'} <= {field['key'] for field in director['fields']}


def test_scheduling_diagnostics_do_not_change_configured_interval(alive,monkeypatch):
    run=alive()
    timers=[]
    class Timer:
        def __init__(self,delay,callback,*args,**kwargs):
            self.delay=delay;timers.append(self)
        def start(self):pass
        def cancel(self):pass
    monkeypatch.setattr(run.plugin._fire.__func__.__globals__['threading'],'Timer',Timer)
    type(run.plugin)._schedule_next(run.plugin,240)
    assert timers[0].delay==240
    assert run.plugin.diagnostic_counts['scheduled']==1


def test_diagnostic_sink_accepts_fixed_codes_only(alive,records):
    run=alive()
    run.helper.record_chatter_diagnostic('PRIVATE')
    run.helper.record_chatter_diagnostic('context_missing')
    assert all('PRIVATE' not in json.dumps(r) for r in records())
    assert any(r['stage']=='chatter_opportunity' and r['reason']=='context_missing' for r in records())
