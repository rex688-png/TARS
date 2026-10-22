"""Synthetic source facts through real plugin/host selection; no profile writes."""
import json
from unittest.mock import Mock

import pytest
from test_speech_trace import assistant, user
from lib.Event import GameEvent
from lib.JournalFacts import sale_facts, sale_key, sale_description
from lib.PromptGenerator import PromptGenerator
from lib.SpeechText import normalize_spoken_quantities
from test_speech_trace import assistant, user
from test_explorer_departure import rig
from test_speech_arbiter import arbiter, clock


def sale(name='SellOrganicData', minute=0, **values):
    content={'event':name,'timestamp':f'2026-10-01T12:{minute:02}:00Z'}
    content.update(values or ({'BioData':[{'Value':19000000,'Bonus':76000000}]} if name=='SellOrganicData'
                              else {'BaseValue':90000000,'Bonus':5000000,'TotalEarnings':95000000}))
    return GameEvent(content=content,historic=False,responded_at=None)


@pytest.mark.parametrize('name',['SellExplorationData','MultiSellExplorationData','SellOrganicData'])
@pytest.mark.parametrize('enabled',[False,True])
def test_independent_reaction_obeys_opt_in_and_deduplicates_real_host(name,enabled):
    event=sale(name);host=assistant([event],['Confirmed transaction.'])
    host.enabled_game_events=[name] if enabled else []
    assert host.should_reply({}) is enabled
    host.reply_thread({})
    assert host.llmModel.calls==int(enabled)
    assert host.tts.say.call_count==int(enabled)
    if enabled:
        duplicate=GameEvent(content=dict(event.content),historic=False,responded_at=None)
        host.pending=[duplicate]
        host.event_manager.get_short_term_memory.return_value=[duplicate]
        assert not host.should_reply({})
        host.reply_thread({})
        assert host.llmModel.calls==1


def test_uc_then_vista_minutes_later_and_separate_equal_transactions():
    host=assistant([],['UC transaction.','Vista transaction.','Another UC transaction.'])
    host.enabled_game_events=['SellExplorationData','SellOrganicData']
    for event in [sale('SellExplorationData'),sale(minute=5),sale('SellExplorationData',minute=6)]:
        host.pending=[event];host.event_manager.get_short_term_memory.return_value=[event]
        assert host.should_reply({});host.reply_thread({})
    assert host.llmModel.calls==3 and host.tts.say.call_count==3


def test_duplicate_batch_and_historic_replay_do_not_repeat_sales():
    first=sale();duplicate=sale();host=assistant([first,duplicate],['One sale.'])
    host.enabled_game_events=['SellOrganicData'];host.reply_thread({})
    pending=host.prompt_generator.generate_prompt.call_args.kwargs['pending_events']
    assert len(pending)==1
    historic=sale(minute=5);historic.historic=True
    host.pending=[historic];host.event_manager.get_short_term_memory.return_value=[historic]
    assert not host.should_reply({});host.reply_thread({});assert host.llmModel.calls==1


def test_direct_question_survives_duplicate_and_disabled_sale():
    event=sale();question=user();host=assistant([event],['Sale.','Current scan status.'])
    host.enabled_game_events=['SellOrganicData'];host.reply_thread({})
    host.enabled_game_events=[];host.pending=[event,question]
    host.event_manager.get_short_term_memory.return_value=[question,event]
    assert host.should_reply({});host.reply_thread({})
    assert host.prompt_generator.generate_prompt.call_args.kwargs['pending_events']==[question]
    assert host.llmModel.calls==2


@pytest.mark.parametrize('name',['SellExplorationData','MultiSellExplorationData','SellOrganicData'])
def test_confirmed_exact_payout_and_display_speech_separation(name):
    event=sale(name);facts=sale_facts(event.content)
    assert facts['credited_total']==95000000
    generator=PromptGenerator.__new__(PromptGenerator);generator.commander_name='Synthetic'
    text=generator.get_event_template(event)
    assert '95,000,000' in text
    spoken=normalize_spoken_quantities('95,000,000 credits')
    assert 'ninety' in spoken.lower() and 'million' in spoken.lower()
    assert ('Vista Genomics' if name=='SellOrganicData' else 'Universal Cartographics') in text
    assert facts['base']+facts['bonus']==facts['credited_total']


def test_authoritative_total_zero_missing_amount_and_no_timestamp_uncertainty():
    event=sale(TotalEarnings=0,BioData=[{'Value':19,'Bonus':76}])
    assert sale_facts(event.content)['credited_total']==0
    assert sale_facts({'event':'SellOrganicData','BioData':[{'Value':19}]})['credited_total'] is None
    del event.content['timestamp'];assert sale_key(event) is None
    assert 'unconfirmed' in sale_description({'event':'SellExplorationData'})


def test_native_count_and_unknown_body_prompt_preserve_source_uncertainty():
    g=PromptGenerator.__new__(PromptGenerator);g.commander_name='Synthetic'
    def render(content):
        return g.get_event_template(GameEvent(content=content,historic=False))
    before=render({'event':'FSSDiscoveryScan','BodyCount':24,'Progress':0.5,'SystemName':'First'})
    after=render({'event':'FSSAllBodiesFound','Count':27,'SystemName':'First'})
    assert 'Provisional' in before and '24' in before and 'First' in before
    assert '27' in after and 'First' in after
    assert 'current body' not in render({'event':'SAAScanComplete'})
    assert 'source BodyID 2' in render({'event':'SAAScanComplete','BodyID':2})


def test_delayed_dss_keeps_full_source_identity_after_moving_body(rig):
    x=rig.plugin;x._reset_system('Synthetic',11)
    a=x._get_body('Synthetic A 2',2);a.planet_class='Water world';a.body_type='planet'
    x._consume_game_event({'event':'SAAScanComplete','BodyID':2,'SystemAddress':11})
    event=rig.manager.incoming.get_nowait()
    x._consume_game_event({'event':'ApproachBody','BodyID':4,'Body':'Synthetic B 4 a'},True)
    assert event.plugin_event_content['body_name']=='Synthetic A 2'
    assert event.plugin_event_content['body_id']==2 and event.plugin_event_content['system_address']==11
    prompt=x._prompt_noteworthy_target(event)
    assert 'Synthetic A 2' in prompt and 'never the commander current body' in prompt
    host=rig.host;host.event_manager.get_short_term_memory.return_value=[event]
    host.reply_thread({'Location':{'StarSystem':'Synthetic','Body':'Synthetic B 4 a'}})
    assert host.tts.say.call_count==1
