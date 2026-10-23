"""Synthetic journal/feed sequences through real host/model/plugin contracts.

No API calls, user profiles, recordings or live-game claims. Completion evidence
is deliberately supplied by fake TTS attempts, not inferred from wait completion.
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import BadRequestError
from openai.types.responses import Response

from test_speech_trace import assistant, user, records
from test_speech_arbiter import arbiter, clock
from test_explorer_departure import rig
from test_chatter_admission import integration
from lib.Event import PluginEvent, GameEvent
from lib.ExplorationSpeech import DeliveryLedger, eligibility
from lib.Models import OpenAIResponsesLLMModel, OpenAILLMModel, LLMError, _single_response_text
from lib.TTS import TTSLine
from lib.TTSOutcome import TTSAttempt

MODES = ['observe', 'enforce']


def fact(source='explorer', kind='scan_value', body=2, **values):
    data = dict(system='Synthetic', system_address=42, body_id=body,
                planet_class='Water world', terraformable=True,
                _guard={'triggered_at':1000.0})
    data.update(values)
    data['callout_kind' if source=='explorer' else 'finding_type'] = kind
    return PluginEvent(plugin_event_name='TARSExplorerTarget' if source=='explorer' else 'TARSObservatoryFact',
                       plugin_event_content=data, responded_at=None)


@pytest.fixture
def pipeline(arbiter):
    def make(mode, outcome='completed'):
        host = assistant([], ['Terraformable water world.'] * 30)
        host.config['speech_director_mode'] = mode
        host._speech_arbiter = arbiter
        host.reply_pending = False
        host.disabled_game_events = []
        def say(*args, **kwargs):
            line = TTSLine()
            line.mark_speaking()
            line.record_attempt(TTSAttempt('synthetic', outcome, 0, 1, written_bytes=16 if outcome=='completed' else 0))
            line.settle(outcome)
            return line
        host.tts.say.side_effect = say
        def run(*events):
            host.pending = list(events)
            host.event_manager.get_short_term_memory.return_value = list(reversed(events))
            host.reply_thread(getattr(host, 'test_states', {}))
        return host, run
    return make


@pytest.mark.parametrize('mode', MODES)
def test_same_terraformable_water_world_across_sources_even_after_attempt_ttl(pipeline, clock, mode):
    host, run = pipeline(mode)
    first, second = fact(), fact('observatory', kind='water_world', source_plugin='Evaluator')
    run(first)
    clock.tick += 20
    clock.wall += 20
    second.plugin_event_content['_guard']['triggered_at'] = clock.wall
    run(second)
    assert host.llmModel.calls == host.tts.say.call_count == 1
    assert first.responded_at is None and second.responded_at is None


@pytest.mark.parametrize('mode', MODES)
def test_two_sources_dss_once_and_new_genus_independent(pipeline, mode):
    host, run = pipeline(mode)
    host.llmModel.responses=iter(['Terraformable water world, mapping complete.', 'Stratum confirmed.', 'Stratum tectonicas sampling complete.', 'Bacterium aurasus sampling complete.'])
    run(fact(kind='dss_complete'))
    run(fact('observatory', kind='dss_complete', source_plugin='BioInsights'))
    assert host.llmModel.calls == 1
    run(fact('observatory', kind='biology', confirmed_genuses=['Stratum']))
    assert host.llmModel.calls == 2
    run(fact('observatory', kind='biology', confirmed_genuses=['Stratum'], message='Different wording'))
    assert host.llmModel.calls == 2
    run(fact(kind='organic_complete', species='Stratum tectonicas'))
    run(fact(kind='organic_complete', species='Bacterium aurasus'))
    assert host.llmModel.calls == 4


@pytest.mark.parametrize('mode', MODES)
def test_routine_mapping_is_update_but_distinct_body_is_new(pipeline, mode):
    host, run = pipeline(mode)
    run(fact())
    run(fact(kind='dss_complete'))
    assert host.llmModel.calls == 1
    run(fact(body=3))
    assert host.llmModel.calls == 2


@pytest.mark.parametrize('mode', MODES)
def test_routine_temperature_record_silent_exceptional_with_evidence_allowed(pipeline, mode):
    host, run = pipeline(mode)
    routine = fact('observatory', kind='personal_record', planet_class=None, terraformable=False,
                   title='Personal minimum temperature record', metric='temperature', value=91)
    run(routine)
    assert host.llmModel.calls == 0
    exceptional = fact('observatory', kind='scientific_exception', planet_class=None, terraformable=False,
                       exceptional=True, significance_reason='Verified exceptional measurement for this body class',
                       metric='temperature', value=2500)
    run(exceptional)
    assert host.llmModel.calls == 1
    assert routine.responded_at is None


@pytest.mark.parametrize('mode', MODES)
def test_incomplete_identifiers_fail_open_not_current_body_guessed(pipeline, mode):
    host, run = pipeline(mode)
    event = fact()
    del event.plugin_event_content['body_id']
    run(event); run(event)
    assert host.llmModel.calls == 2
    assert not host.speech_arbiter()._delivery_ledger.delivered


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('outcome', ['output_failed', 'synthesis_failed', 'interrupted', 'cancelled_before_start', 'unknown'])
def test_failed_or_cancelled_delivery_never_commits_fact(pipeline, mode, outcome):
    host, run = pipeline(mode, outcome)
    run(fact()); run(fact('observatory', kind='water_world'))
    assert host.llmModel.calls == 2
    assert not host.speech_arbiter()._delivery_ledger.delivered


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('text', [
    'No final output. Routine record notification does not merit unsolicited cumulative counts; temperature record ordinarily factual but not explicitly important?',
    'We already acknowledged AB5’s mapping; no new facts.',
    'Alternative 1: Mapping is complete.\nAlternative 2: The body is mapped.',
    'SKIP', '',
])
def test_internal_alternative_and_silent_output_never_reaches_ui_or_tts(pipeline, records, mode, text):
    host, run = pipeline(mode)
    host.llmModel.responses = iter([text])
    run(fact())
    host.tts.say.assert_not_called()
    host.event_manager.add_conversation_event.assert_not_called()
    assert 'AB5' not in json.dumps(records())


def test_user_technical_answer_not_subject_to_unsolicited_screen(pipeline):
    host, run = pipeline('observe')
    host.llmModel.responses = iter(['Analysis: alternative 1 is relevant to your diagnostic question.'])
    run(fact(), user())
    host.tts.say.assert_called_once()


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('interrupt', ['question', 'system'])
def test_slow_generation_invalidated_before_ui_and_tts(pipeline, mode, interrupt):
    host, run = pipeline(mode)
    generate = host.llmModel.generate
    def slow(*args, **kwargs):
        event = user() if interrupt=='question' else GameEvent(content={'event':'FSDJump','SystemAddress':99}, historic=False)
        host.speech_arbiter().note_event(event)
        host.pending.append(event)
        return generate(*args, **kwargs)
    host.llmModel.generate = slow
    run(fact())
    host.tts.say.assert_not_called()
    host.event_manager.add_conversation_event.assert_not_called()


@pytest.mark.parametrize('mode', MODES)
def test_direct_question_keeps_all_routine_context_and_bypasses_ledger(pipeline, mode):
    host, run = pipeline(mode)
    event = fact('observatory', kind='personal_record', title='Personal temperature record')
    run(fact())
    run(event, user())
    assert host.llmModel.calls == 2
    prompt_args = host.prompt_generator.generate_prompt.call_args.kwargs
    assert event in prompt_args['events']


def response_message(text, phase=None):
    data={'id':'msg_synthetic','type':'message','role':'assistant','status':'completed',
          'content':[{'type':'output_text','text':text,'annotations':[]}]}
    if phase: data['phase']=phase
    return data


def sdk_response(messages):
    return Response.model_validate({'id':'resp_synthetic','object':'response','created_at':0,
        'model':'gpt-6-luna','output':messages,'parallel_tool_calls':True,'tool_choice':'auto','tools':[]})


def test_real_sdk_aggregation_reproduced_and_explicit_final_only_selected():
    response=sdk_response([response_message('Rejected draft.', 'commentary'),
                           response_message('One coherent final answer.', 'final_answer')])
    assert response.output_text == 'Rejected draft.One coherent final answer.'
    assert _single_response_text(response) == 'One coherent final answer.'


def test_multiple_unlabelled_sdk_alternatives_rejected_not_joined():
    response=sdk_response([response_message('First answer.'), response_message('Second answer.')])
    with pytest.raises(LLMError, match='unambiguous final answer'):
        _single_response_text(response)


@pytest.mark.parametrize('cls, attr', [(OpenAILLMModel,'chat'),(OpenAIResponsesLLMModel,'responses')])
def test_real_provider_rejection_metadata_never_logs_request_or_error_text(cls, attr, records, caplog):
    model=cls(base_url='https://api.openai.com/v1',api_key='synthetic',model_name='gpt-6-luna',temperature=0.3)
    request=httpx.Request('POST','https://api.openai.com/v1/responses',
                          headers={'authorization':'Bearer PRIVATE_CREDENTIAL'},content=b'PRIVATE_PROMPT')
    error=BadRequestError('PRIVATE_PROVIDER_TEXT',response=httpx.Response(400,request=request),
                          body={'error':{'code':'invalid_prompt','message':'PRIVATE_PROMPT'}})
    endpoint=model.client.chat.completions if attr=='chat' else model.client.responses
    endpoint.with_raw_response.create=Mock(side_effect=error)
    with pytest.raises(LLMError, match='invalid_prompt'):
        model.generate([{'role':'user','content':'PRIVATE_MEMORY'}])
    assert 'PRIVATE' not in caplog.text
    assert 'PRIVATE' not in json.dumps(records())
    assert any(r.get('code')=='invalid_prompt' and r.get('status')==400 for r in records())


@pytest.mark.parametrize('mode', MODES)
def test_rejection_and_empty_direct_requests_have_error_indication_not_speech(pipeline, mode, monkeypatch):
    host, run=pipeline(mode)
    error=Mock()
    monkeypatch.setattr('lib.Assistant.show_chat_message', error)
    host.llmModel.responses=iter([LLMError('PRIVATE rejection'), None])
    run(user()); run(user())
    host.tts.say.assert_not_called()
    assert error.call_count==2
    assert 'PRIVATE' not in str(error.call_args_list)


def test_ordinary_scans_remain_known_no_reaction_plugin_receives_data(rig):
    host,x,manager=rig.host,rig.plugin,rig.manager
    host.enabled_game_events=[];host.disabled_game_events=[]
    for identity in (7,8,9):
        manager.add_game_event({'event':'Scan','BodyID':identity,'BodyName':f'Test A {identity}',
                                'PlanetClass':'Icy body','SurfaceTemperature':91})
    manager.process()
    assert all(x._get_body('',identity).surface_temp_k==91 for identity in (7,8,9))
    assert any(isinstance(e, GameEvent) for e in manager.processed)
    assert not host.should_reply({})
    assert host.enabled_game_events==[] and host.disabled_game_events==[]


def test_chatter_without_worthwhile_anchor_spends_no_generation(integration):
    run=integration('observe')
    run.plugin._recent_situational_anchors=lambda *args: []
    run.fire()
    assert run.host.llmModel.calls==0


@pytest.mark.parametrize('mode', MODES)
def test_generation_age_rechecked_after_slow_model(pipeline, clock, mode):
    host, run = pipeline(mode)
    generate = host.llmModel.generate
    def slow(*args, **kwargs):
        clock.wall += 61
        return generate(*args, **kwargs)
    host.llmModel.generate = slow
    run(fact())
    host.tts.say.assert_not_called()
    host.event_manager.add_conversation_event.assert_not_called()


@pytest.mark.parametrize('mode', MODES)
def test_all_compatible_producers_preserve_facts_but_share_known_finding(pipeline, mode):
    host, run = pipeline(mode)
    events = [fact('observatory', kind='water_world', source_plugin=name)
              for name in ('BioInsights', 'Evaluator', 'Stat Scanner', 'AstroAnalytica')]
    for event in events:
        run(event)
        assert event.responded_at is None
    assert host.llmModel.calls == 1


@pytest.mark.parametrize('mode', MODES)
def test_single_coherent_multisentence_answer_is_preserved(pipeline, mode):
    host, run=pipeline(mode)
    text="Water world on 3, terraformable too. I would map that before we leave."
    host.llmModel.responses=iter([text])
    run(fact())
    assert host.event_manager.add_conversation_event.call_args.args[1] == text
    assert host.tts.say.call_count == 1


def test_high_value_plugin_still_announces_while_raw_scan_is_no_reaction(rig):
    host,x,manager=rig.host,rig.plugin,rig.manager
    host.config['speech_director_mode']='observe'
    settings={'Scan':'off','SAAScanComplete':'off','FSSBodySignals':'off'}
    host.config['characters'][0]['event_reactions']=dict(settings)
    host.enabled_game_events=[];host.disabled_game_events=[]
    manager.add_game_event({'event':'Scan','BodyID':7,'BodyName':'Test A 7',
                            'PlanetClass':'Water world','TerraformState':'Terraformable'})
    manager.process()
    events=list(manager.processed)
    for event in events: event.responded_at=None
    assert any(getattr(e,'plugin_event_name',None)=='TARSExplorerTarget' for e in events)
    host.event_manager.get_short_term_memory.return_value=list(reversed(events))
    host.reply_thread({})
    assert host.llmModel.calls==1
    assert host.config['characters'][0]['event_reactions']==settings


def test_director_retry_returns_only_replacement(integration):
    run=integration('observe', ['Rejected repetitive draft.', 'One fresh contextual remark.'])
    plugin=run.plugin
    plugin._main_covas_system_index=lambda messages:0
    plugin._explicit_visual_request=lambda messages:None
    plugin._prepared_chatter_line=lambda messages:None
    plugin._is_spontaneous_turn=lambda messages:True
    plugin._routine_flight_trigger=lambda messages:None
    plugin._routine_noise_kind=lambda messages:None
    plugin._repetition_reason=lambda text:None
    plugin._chatter_quality_reason=lambda text:'repeated_premise' if text.startswith('Rejected') else None
    text, actions, _=run.host.llmModel.generate([{'role':'system','content':'PRIVATE_PROMPT'},
                                               {'role':'user','content':'optional context'}])
    assert text=='One fresh contextual remark.' and actions is None
    assert run.host.llmModel.calls==2
    run.host.tts.say.assert_not_called()  # Generation itself does not dispatch candidates.


def test_completed_audio_does_not_claim_unmentioned_prompt_facts(pipeline):
    host, run=pipeline('observe')
    host.llmModel.responses=iter(['A pleasant sight.', 'Terraformable water world.'])
    run(fact())
    assert not host.speech_arbiter()._delivery_ledger.delivered
    run(fact('observatory', kind='water_world'))
    assert host.llmModel.calls==2


def test_explicit_alias_evidence_can_link_id_and_name_but_conflicts_fail_open(pipeline):
    host, run=pipeline('observe')
    run(fact(body=2, body_name='Synthetic A 2', BodyName='A2'))
    named=fact('observatory',kind='water_world',body_name='A2')
    del named.plugin_event_content['body_id']
    del named.plugin_event_content['system_address']
    run(named)
    assert host.llmModel.calls==1
    run(fact(body=3,body_name='Synthetic A 2',BodyName='A2'))
    run(named)
    assert host.llmModel.calls==3  # ambiguous alias never collapses bodies


def test_return_to_system_keeps_session_delivery_evidence(pipeline):
    host, run=pipeline('observe')
    run(fact())
    for address in (99,42):
        host.speech_arbiter().note_event(GameEvent(content={'event':'FSDJump','SystemAddress':address},historic=False))
    run(fact('observatory',kind='water_world'))
    assert host.llmModel.calls==1


def test_real_bridge_feed_and_event_manager_keep_silent_facts_and_announce_findings(rig):
    import importlib.util
    import sys
    from pathlib import Path
    from lib.PluginBase import PluginManifest
    from lib.PluginHelper import PluginHelper
    path=Path(__file__).resolve().parents[2]/'vendor/tars-plugins/plugins/TARSObservatoryBridge/TARSObservatoryBridge.py'
    spec=importlib.util.spec_from_file_location('_gameplay_real_bridge',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    bridge=module.TARSObservatoryBridge(PluginManifest(json.dumps(module.TARS_OBSERVATORY_BRIDGE_MANIFEST)))
    host,manager=rig.host,rig.manager
    host.config['speech_director_mode']='observe'
    host.enabled_game_events=[];host.disabled_game_events=[]
    helper=PluginHelper.__new__(PluginHelper)
    helper._assistant,helper._event_manager=host,manager
    helper._config,helper._prompt_generator=host.config,host.prompt_generator
    bridge._helper=helper
    helper.register_event('TARSObservatoryFact',bridge._should_reply_fact,bridge._prompt_observatory_fact)
    common={'realtime':True,'monitor_mode':'realtime','batch':False,'system_address':42,'body_id':2,
            '_guard':{'triggered_at':1000.0}}
    routine=dict(common,event_id='synthetic-routine',fact_type='notification:StatScanner',
                 source_plugin='Stat Scanner',title='Personal minimum temperature record')
    assert bridge._process_line(json.dumps(routine).encode())
    manager.process()
    # Mock persistence does not hydrate responded_at=0 as None like the store.
    for event in manager.processed:event.responded_at=None
    host.event_manager.get_short_term_memory.return_value=list(reversed(manager.processed))
    assert not host.reply_pending
    host.reply_thread({})
    assert host.llmModel.calls==0
    useful=dict(common,event_id='synthetic-important',fact_type='notification:BioInsights',
                source_plugin='BioInsights',finding_type='water_world',planet_class='Water world',terraformable=True)
    assert bridge._process_line(json.dumps(useful).encode())
    manager.process()
    for event in manager.processed:event.responded_at=None
    host.event_manager.get_short_term_memory.return_value=list(reversed(manager.processed))
    assert host.reply_pending
    host.reply_thread({})
    assert host.llmModel.calls==1
    context=host.prompt_generator.generate_prompt.call_args.kwargs['events']
    assert any(getattr(e,'plugin_event_content',{})==routine for e in context)
    assert bridge._status['relayed']==2


def test_distinct_bodies_not_suppressed_by_identical_sentence_in_commander_location(pipeline):
    host,run=pipeline('observe')
    host.test_states={'Location':{'StarSystem':'Synthetic','Body':'Synthetic A 2'}}
    host.llmModel.responses=iter(['Water world.', 'Water world.'])
    run(fact(body=2));run(fact(body=3))
    assert host.llmModel.calls==host.tts.say.call_count==2


def test_incomplete_provider_message_is_not_recovered_through_sdk_aggregate():
    message=response_message('Incomplete draft.')
    message['status']='incomplete'
    response=sdk_response([message])
    assert response.output_text=='Incomplete draft.'
    assert _single_response_text(response) is None


def test_commentary_with_tool_request_is_not_a_spoken_final():
    response=sdk_response([response_message('Checking.', 'commentary'),
        {'id':'fc_synthetic','type':'function_call','call_id':'call_synthetic',
         'name':'synthetic_lookup','arguments':'{}','status':'completed'}])
    assert _single_response_text(response) is None


@pytest.mark.parametrize('mode', MODES)
def test_direct_question_preempts_blocked_optional_generation(pipeline, mode, monkeypatch):
    import threading
    from lib.Logger import ModelUsageStats
    host,run=pipeline(mode)
    waiting, release=threading.Event(), threading.Event()
    calls=[]
    def generate(messages, tools=None, tool_choice=None):
        calls.append(True)
        if len(calls)==1:
            waiting.set()
            assert release.wait(3)
            return 'Old automatic finding.',None,ModelUsageStats()
        return 'Direct commander answer.',None,ModelUsageStats()
    host.llmModel.generate=generate
    first=fact()
    host.event_manager.get_short_term_memory.return_value=[first]
    worker=threading.Thread(target=host.reply_thread,args=({},))
    worker.start()
    try:
        assert waiting.wait(2)
        question=user()
        host.speech_arbiter().note_event(question)
        host.event_manager.get_short_term_memory.return_value=[question,first]
        host.pending.append(question)
        assert host.can_start_reply()  # production Chat-loop scheduling gate
        import importlib
        started=[]
        def start_thread(*args, **kwargs):
            thread=threading.Thread(*args, **kwargs)
            started.append(thread)
            return thread
        monkeypatch.setattr(importlib.import_module('lib.Assistant'), 'Thread', start_thread)
        host.reply({})
        assert len(started)==1
        started[0].join(2)
        assert not started[0].is_alive()
        assert host.tts.say.call_count==1  # answer delivered before optional call unblocks
        assert host.tts.say.call_args.args[0]=='Direct commander answer.'
    finally:
        release.set();worker.join(3)
    assert not worker.is_alive() and not host.is_replying
    assert host.tts.say.call_count==1


def test_distinct_organism_variants_and_duplicate_rewording(pipeline):
    host,run=pipeline('observe')
    host.llmModel.responses=iter(['Stratum tectonicas Emerald sampling complete.',
                                  'Stratum tectonicas Gold sampling complete.'])
    run(fact(kind='organic_complete',species='Stratum tectonicas',variant='Emerald'))
    run(fact(kind='organic_complete',species='Stratum tectonicas',variant='Gold'))
    run(fact('observatory',kind='organic_complete',species='Stratum tectonicas',variant='Gold'))
    assert host.llmModel.calls==2


def test_malformed_optional_schema_fields_fail_open_without_crashing():
    event=fact()
    event.plugin_event_content.update(planet_class=[],callout_kind={},_guard=[])
    assert eligibility(event).disposition=='announce'
    assert DeliveryLedger().entity(event) is not None
