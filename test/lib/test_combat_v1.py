"""Real plugin/host seams, synthetic timestamped evidence and fake audio/keys."""
import json
import queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from datetime import datetime, timezone

import pytest
from test_speech_trace import assistant, user, records
from test_speech_arbiter import arbiter, clock, finding
from test_chatter_admission import integration
from test_explorer_departure import rig
from lib.Event import GameEvent, StatusEvent, PluginEvent
from lib.PluginManager import PluginManager
from lib.PluginBase import PluginManifest
from lib.PluginHelper import PluginHelper


@pytest.fixture
def combat(arbiter, clock, monkeypatch):
    # Before bundle pinning, load canonical source; final tests use vendored bytes.
    source = Path(__file__).resolve().parents[2]/'vendor/tars-plugins/plugins/TARSCombat'
    if not source.exists():
        source = Path(__file__).resolve().parents[3]/'TARS-Plugins/plugins/TARSCombat'
    manifest = PluginManifest((source/'manifest.json').read_text())
    manager = PluginManager({}, tars_profile=False)
    plugin = manager.load_plugin_module(manifest,str(source/'TARSCombat.py'))
    monkeypatch.setattr(plugin.observe.__func__.__globals__['time'], 'time', lambda: clock.wall)
    host = assistant([], ['A direct answer.']*20)
    host._speech_arbiter = arbiter
    host.disabled_game_events = []
    host.reply_pending = False
    host.event_manager.incoming = queue.Queue()
    host.event_manager.sideeffects = []
    helper = PluginHelper.__new__(PluginHelper)
    helper._assistant, helper._config = host, host.config
    helper._event_manager, helper._prompt_generator = host.event_manager,host.prompt_generator
    helper._action_manager = Mock()
    plugin.on_chat_start(helper)
    states={}
    host._combat_router.wall=lambda:clock.wall
    def feed(name, **fields):
        data=dict(event=name,timestamp=datetime.fromtimestamp(clock.wall,timezone.utc).isoformat(),**fields)
        e=StatusEvent(status=data) if name=='Status' else GameEvent(content=data,historic=False)
        if name=='Status': states['CurrentStatus']=dict(fields)
        if name=='ShipTargeted': states['Target']=dict(fields)
        plugin.observe(e,states)
        return e
    def run(*events):
        host.pending=list(events)
        host.event_manager.get_short_term_memory.return_value=list(reversed(events))
        host.reply_thread(states)
    yield SimpleNamespace(plugin=plugin,host=host,helper=helper,feed=feed,run=run,states=states)
    plugin.on_chat_stop(helper)


@pytest.mark.parametrize('mode',['off','observe','enforce'])
@pytest.mark.parametrize('name',['TARSExplorerTarget','TARSObservatoryFact','TARSChatter','TARSNavigatorTarget'])
def test_combat_focus_stops_optional_generations_in_every_rollout_mode(combat,mode,name):
    c=combat;c.host.config['speech_director_mode']=mode
    c.feed('Music',MusicTrack='Combat')
    event=finding();event.plugin_event_name=name
    c.run(event)
    assert c.host.llmModel.calls==0
    assert not c.host.speech_arbiter().combat_allows(event)
    assert event.responded_at is None
    c.run(event,user())
    assert c.host.llmModel.calls==1


@pytest.mark.parametrize('mode',['off','observe','enforce'])
def test_chatter_admission_before_generation_blocked_during_combat(integration,mode):
    run=integration(mode)
    run.host.speech_arbiter().set_combat_focus('active')
    run.fire()
    assert run.host.llmModel.calls==0
    assert run.host.event_manager.incoming.empty()


def test_focus_recovery_discards_old_optional_but_keeps_new_and_warning(combat,clock):
    c=combat
    c.feed('UnderAttack')
    old=finding()
    c.feed('Music',MusicTrack='Exploration')
    clock.wall+=21;c.feed('Status',flags={'InMainShip':True})
    clock.wall+=13;c.feed('Status',flags={'InMainShip':True})
    assert c.plugin.tracker.phase=='recovering'
    clock.wall+=16;c.feed('Status',flags={'InMainShip':True})
    assert c.plugin.tracker.phase=='idle'
    c.run(old)
    assert c.host.llmModel.calls==0
    new=finding();new.plugin_event_content['_guard']['triggered_at']=clock.wall
    c.run(new)
    assert c.host.llmModel.calls==1
    c.feed('UnderAttack')
    warning=finding();warning.plugin_event_content.update(callout_kind='early_departure_warning',warning_trigger='FsdHyperdriveCharging')
    assert c.host.speech_arbiter().combat_allows(warning)


def test_critical_alert_no_llm_revalidated_and_not_repeated(combat,clock):
    c=combat
    c.feed('Status',flags={'InMainShip':True,'InDanger':True})
    c.feed('HullDamage',Fighter=False,PlayerPilot=True,Health=.4)
    event=c.host.event_manager.incoming.get_nowait();event.responded_at=None
    c.run(event)
    assert c.host.llmModel.calls==0
    c.host.tts.say.assert_called_once()
    assert c.host.event_manager.add_conversation_event.call_args.args[1]=='Mothership hull critical. Consider disengaging.'
    c.feed('HullDamage',Fighter=False,PlayerPilot=True,Health=.4)
    assert c.host.event_manager.incoming.empty()
    clock.wall+=6
    assert c.host.tts.say.call_args.kwargs['drop_if']()
    c.host.tts.say.reset_mock();c.run(event)
    c.host.tts.say.assert_not_called()
    assert c.host.llmModel.calls==0


def test_existing_optional_inflight_result_is_cancelled(combat):
    c=combat
    original=c.host.llmModel.generate
    def generate(**kw):
        c.feed('UnderAttack')
        return original(**kw)
    c.host.llmModel.generate=generate
    c.run(finding())
    assert c.host.llmModel.calls==1
    c.host.tts.say.assert_not_called()


def test_stopping_plugin_releases_focus_without_touching_other_settings(combat):
    c=combat;c.feed('UnderAttack')
    saved=dict(c.host.config)
    c.plugin.on_chat_stop(c.helper)
    assert c.host._combat_provider is None
    assert c.host.speech_arbiter()._combat_phase=='idle'
    assert c.host.config==saved


@pytest.fixture
def controls(combat,clock):
    from lib.ActionManager import ActionManager
    c=combat
    c.plugin.settings.update(fast_commands=True)
    c.host.config.update(tools_var=True,game_actions_var=True,allowed_actions={
        'managePowerDistribution':True,'deployHeatSink':True,'npcOrder':True,'targetSubmodule':True})
    manager=ActionManager.__new__(ActionManager)
    manager.actions={}
    manager.approvals=None
    manager.configure_permissions(lambda:c.host.config,Mock())
    manager.allowed_actions=c.host.config['allowed_actions']
    calls=[]
    for name in c.host.config['allowed_actions']:
        manager.registerAction(name,'test',{'type':'object'},lambda args,states: calls.append(args) or 'Requested.',permission=name)
    c.helper._action_manager=manager
    c.host.action_manager=manager
    c.feed('Status',flags={'InMainShip':True},GuiFocus='NoFocus')
    def command(text='balance power',source='text',confidence=None):
        e=user();e.content=text;e.input_source=source;e.input_confidence=confidence
        e.input_session=c.host._combat_router.session
        e.timestamp=datetime.fromtimestamp(clock.wall,timezone.utc).isoformat()
        return e
    return SimpleNamespace(**c.__dict__,command=command,calls=calls)


@pytest.mark.parametrize('denial',['disabled','master','missing_permission','block','ask','stale','unknown_confidence','low_confidence','session'])
def test_fast_command_denials_do_not_call_model_or_controls(controls,clock,denial):
    c=controls;e=c.command()
    if denial=='disabled': c.plugin.settings['fast_commands']=False
    if denial=='master': c.host.config['game_actions_var']=False
    if denial=='missing_permission': c.host.config['allowed_actions']['managePowerDistribution']=False
    if denial in ('block','ask'): c.host.config['action_permissions']={'managePowerDistribution':denial}
    if denial=='stale': clock.wall+=11
    if denial=='unknown_confidence': e.input_source='voice'
    if denial=='low_confidence': e.input_source='voice';e.input_confidence=.4
    if denial=='session': e.input_session='previous-session'
    c.run(e)
    assert c.calls==[] and c.host.llmModel.calls==0
    assert c.host.event_manager.add_conversation_event.call_args.args[1].startswith('Not executed:')


def test_allowlisted_command_uses_action_manager_and_observed_state(controls):
    c=controls
    def wait(name,predicate,timeout):
        assert name=='CurrentStatus' and timeout==2
        state=SimpleNamespace(Pips=None)
        assert not predicate({'Pips':{'system':1,'engine':3,'weapons':2}})
        expected={'Pips':{'system':2,'engine':2,'weapons':2}}
        assert predicate(expected)
        return expected
    c.host.event_manager.wait_for_condition.side_effect=wait
    c.run(c.command())
    assert c.host.llmModel.calls==0 and c.calls==[{'balance_power':True}]
    assert c.host.event_manager.add_conversation_event.call_args.args[1]=='Requested tactical state observed.'
    c.host.prompt_generator.generate_prompt.assert_not_called()


def test_unconfirmed_result_and_repeated_command_event(controls):
    c=controls;e=c.command('deploy heat sink')
    c.run(e);c.run(e)
    assert c.calls==[{}] and c.host.llmModel.calls==0
    assert c.host.event_manager.add_conversation_event.call_args_list[0].args[1]=='Command sent; game-state outcome unconfirmed.'
    assert 'already handled' in c.host.event_manager.add_conversation_event.call_args.args[1]


def test_ambiguous_text_remains_conversation(controls):
    c=controls;c.run(c.command('Could you explain balance power?'))
    assert c.calls==[] and c.host.llmModel.calls==1


def test_subsystem_requires_fresh_scan_and_same_target_confirmation(controls):
    c=controls
    c.run(c.command('target power plant'))
    assert not c.calls
    c.feed('ShipTargeted',TargetLocked=True,Ship='anaconda',PilotName='Synthetic',ScanStage=3)
    def wait(name,predicate,timeout):
        assert not predicate({'Ship':'python','PilotName':'other','Subsystem':'Power Plant'})
        raise TimeoutError()
    c.host.event_manager.wait_for_condition.side_effect=wait
    c.run(c.command('target power plant'))
    assert c.calls==[{'subsystem':'Power Plant'}]
    assert c.host.event_manager.add_conversation_event.call_args.args[1].endswith('unconfirmed.')


@pytest.mark.parametrize('text',['fighter, attack my target.','fighter defend me.','fighter return.','launch the fighter.'])
def test_fighter_controls_are_not_inferred_or_launched_by_default(controls,text):
    c=controls;c.run(c.command(text))
    assert not c.calls
    assert c.host.llmModel.calls==0


def test_metrics_have_only_counts_and_median_p95_not_transcripts(controls):
    c=controls;c.run(c.command('deploy heat sink'))
    metrics=c.helper.combat_latency()
    assert metrics['milliseconds']['intent_ms']['samples']==1
    assert metrics['milliseconds']['dispatch_ms']['p95'] is not None
    assert metrics['milliseconds']['capture_to_stt_ms']['median'] is None
    assert 'heat sink' not in json.dumps(metrics)


def test_model_cannot_bypass_unrecognized_control_parser(controls):
    from openai.types.chat import ChatCompletionMessageFunctionToolCall
    c=controls
    c.host.event_manager.processed=[];c.host.event_manager.pending=[]
    call=ChatCompletionMessageFunctionToolCall(id='synthetic',type='function',
        function={'name':'npcOrder','arguments':'{"orders":["FocusTarget"]}'})
    c.host.execute_actions([call],c.states)
    assert c.calls==[]
    assert 'Not executed' in c.host.event_manager.add_tool_call.call_args.args[1][0]['content']


def test_absolute_four_pips_uses_reset_then_half_pip_steps(monkeypatch):
    import lib.actions.Actions as actions
    keys=Mock();monkeypatch.setattr(actions,'keys',keys)
    monkeypatch.setattr(actions,'setGameWindowActive',Mock())
    monkeypatch.setattr(actions,'checkStatus',Mock())
    states={'CurrentStatus':{'flags':{'InMainShip':True}}}
    result=actions.manage_power_distribution({'power_category':['Systems'],'pips':[4]},states)
    assert [c.args[0] for c in keys.send.call_args_list]==['ResetPowerDistribution']+['IncreaseSystemsPower']*4
    assert 'unconfirmed' in result
    keys.reset_mock()
    assert actions.manage_power_distribution({'power_category':['Systems'],'pips':[3]},states).startswith('ERROR')
    keys.send.assert_not_called()


def test_subsystem_cycle_stops_after_target_change_or_missing_update(monkeypatch):
    import lib.actions.Actions as actions
    keys=Mock();monkeypatch.setattr(actions,'keys',keys)
    manager=Mock();monkeypatch.setattr(actions,'event_manager',manager)
    target={'Ship':'anaconda','PilotName':'Synthetic','ScanStage':3,'EventID':'1','Subsystem':'Drive'}
    manager.get_current_state.side_effect=[([],{'Target':target}),([],{'Target':dict(target,Ship='python')})]
    actions.target_subsystem_thread('Drive','1','Power Plant',('anaconda','Synthetic'))
    assert keys.send.call_count==1
    keys.reset_mock();manager.get_current_state.side_effect=None
    manager.get_current_state.return_value=([],{'Target':target})
    manager.wait_for_condition.side_effect=TimeoutError()
    actions.target_subsystem_thread('Drive','1','Power Plant',('anaconda','Synthetic'))
    assert keys.send.call_count==1
    assert manager.wait_for_condition.call_args.kwargs['timeout']<=.25


@pytest.mark.parametrize('topic',['target','condition','wanted','bounty','subsystem'])
def test_queries_identify_incomplete_and_stale_targets(combat,clock,topic):
    c=combat;args=SimpleNamespace(topic=topic)
    c.feed('ShipTargeted',TargetLocked=True,Ship='anaconda',PilotName='Synthetic',ScanStage=1,Bounty=100)
    data=json.loads(c.plugin.query(args,{}))
    assert 'Incomplete' in data['status'] and 'Bounty' not in data
    clock.wall+=1
    c.feed('ShipTargeted',TargetLocked=True,Ship='anaconda',PilotName='Synthetic',ScanStage=3,Bounty=100,LegalStatus='Wanted')
    data=json.loads(c.plugin.query(args,{}))
    assert data['Bounty']==100 and data['LegalStatus']=='Wanted'
    clock.wall+=16
    assert 'stale' in json.loads(c.plugin.query(args,{}))['status']


def test_reports_separate_awards_focus_intervals_and_target_observations(combat,clock):
    c=combat;c.feed('Music',MusicTrack='Combat')
    c.feed('ShipTargeted',TargetLocked=True,Ship='anaconda',PilotName='Synthetic',ScanStage=3)
    c.feed('Bounty',Target='anaconda',TotalReward=700)
    clock.wall+=1;c.feed('Bounty',Target='python',TotalReward=300)
    c.feed('Music',MusicTrack='Exploration')
    clock.wall+=21;c.feed('Status',flags={'InMainShip':True})
    clock.wall+=13;c.feed('Status',flags={'InMainShip':True})
    result=json.loads(c.plugin.query(SimpleNamespace(topic='report'),{}))
    assert result['session']['bounty_awards']==2
    assert result['session']['bounty_credits']==1000
    assert len(result['recent_encounters'])==1
    assert len(result['recent_encounters'][0]['targets_observed'])==1
    assert 'not individual fights' in result['report_rule']
    assert 'DPS' in str(result['limitations'])
    assert c.host.event_manager.incoming.empty()  # no unsolicited summary


def test_status_parser_preserves_source_time_for_combat(combat,clock):
    from lib.StatusParser import parse_status_json
    c=combat
    at=datetime.fromtimestamp(clock.wall,timezone.utc).isoformat()
    parsed=parse_status_json({'timestamp':at,'Flags':16777216|4194304})
    c.plugin.observe(StatusEvent(status=parsed),{})
    assert c.plugin.tracker.phase=='active'
    assert c.host.event_manager.sideeffects[0]==c.plugin.observe
    stale=parse_status_json({'timestamp':'2000-01-01T00:00:00Z','Flags':16777216|4194304})
    assert stale['timestamp']=='2000-01-01T00:00:00Z'


def test_unscored_voice_records_available_stt_timing_but_never_dispatches(controls):
    c=controls;e=c.command('deploy heat sink',source='voice')
    e.input_timing={'capture_completed':10,'stt_completed':10.4}
    c.run(e)
    assert c.calls==[]
    metrics=c.helper.combat_latency()['milliseconds']
    assert metrics['capture_to_stt_ms']['samples']==1
    assert metrics['capture_to_stt_ms']['median']==pytest.approx(400)
    assert metrics['dispatch_ms']['samples']==0


def test_fighter_query_labels_old_hull_and_never_changes_mothership(combat,clock):
    c=combat
    c.feed('LaunchFighter',ID=3,PlayerControlled=False)
    c.feed('HullDamage',Fighter=True,PlayerPilot=False,Health=.1)
    clock.wall+=16
    result=json.loads(c.plugin.query(SimpleNamespace(topic='fighter'),{}))
    assert result['fighters']['3']['hull_stale']
    assert c.plugin.tracker.mothership=={}


@pytest.mark.parametrize('mode',['off','observe','enforce'])
def test_precombat_chatter_lease_never_revives_after_recovery(arbiter,clock,mode):
    lease=arbiter.begin_optional(clock.wall,mode)
    arbiter.set_combat_focus('active')
    arbiter.set_combat_focus('recovering')
    arbiter.set_combat_focus('idle')
    assert not arbiter.optional_valid(lease)


def test_read_only_combat_query_remains_available_with_game_controls_off(combat):
    from lib.ActionManager import ActionManager
    c=combat
    manager=ActionManager.__new__(ActionManager);manager.actions={};manager.approvals=None;manager.allowed_actions={}
    c.helper._action_manager=manager
    args=c.plugin.query.__func__.__globals__['QueryArgs']
    c.helper.register_action('tarsCombatQuery','read only',args,c.plugin.query,action_type='read')
    tools=manager.getToolsList('mainship',False,False,False,{})
    assert [t['function']['name'] for t in tools]==['tarsCombatQuery']
    assert manager.actions['tarsCombatQuery']['permission'] is None


def test_default_music_projection_reactions_cannot_create_combat_commentary(combat):
    from lib.Event import ProjectedEvent
    c=combat;c.host.enabled_game_events=['CombatEntered','CombatExited','Bounty','ShipTargeted']
    c.feed('Music',MusicTrack='Combat')
    c.run(ProjectedEvent(content={'event':'CombatEntered'},responded_at=None))
    assert c.host.llmModel.calls==0
    c.plugin.settings['enabled']=False
    c.feed('Status',flags={'InMainShip':True})
    assert c.host.speech_arbiter().combat_allows(ProjectedEvent(content={'event':'CombatEntered'}))


def test_direct_combat_question_gets_freshness_contract_without_changing_profile(combat):
    from lib.Logger import PromptUsageStats
    c=combat
    c.host.prompt_generator.generate_prompt.return_value=([{'role':'system','content':'You are TARS.'}],PromptUsageStats())
    c.run(user())
    content=c.host.prompt_generator.generate_prompt.return_value[0][0]['content']
    assert 'use tarsCombatQuery' in content and 'Missing or stale telemetry is unknown' in content
    assert 'character' not in c.host.config['characters'][0]


@pytest.mark.usefixtures('clock')
def test_focus_does_not_stop_real_explorer_or_observatory_ingestion(combat,rig):
    c=combat;c.feed('UnderAttack')
    x=rig.plugin;x._reset_system('Synthetic',42)
    x._consume_game_event({'event':'Scan','BodyID':2,'BodyName':'Synthetic A 2','PlanetClass':'Water world'},False)
    body=x._get_body('',2)
    assert body.planet_class=='Water world'
    while not rig.manager.incoming.empty():
        e=rig.manager.incoming.get_nowait();e.responded_at=None;c.run(e)
    root=Path(__file__).resolve().parents[2]/'vendor/tars-plugins/plugins/TARSObservatoryBridge'
    manager=PluginManager({},tars_profile=False)
    bridge=manager.load_plugin_module(PluginManifest((root/'manifest.json').read_text()),str(root/'TARSObservatoryBridge.py'))
    bridge._helper=c.helper
    fact={'event_id':'synthetic-combat-feed','realtime':True,'monitor_mode':'realtime',
          'fact_type':'notification:Evaluator','finding_type':'water_world','system':'Synthetic',
          'system_address':42,'body_id':2,'title':'Synthetic scientific finding'}
    assert bridge._process_line(json.dumps(fact).encode())
    assert bridge._status['relayed']==1
    e=c.host.event_manager.incoming.get_nowait();e.responded_at=None
    assert e.plugin_event_content==fact
    c.run(e)
    assert c.host.llmModel.calls==0


def test_disabling_combat_restores_ordinary_host_control_route(controls):
    c=controls;c.plugin.settings['enabled']=False
    assert c.host._combat_router.handle(c.command(),c.states) is None
    assert c.host._combat_router.allows_model_action('managePowerDistribution')


def test_supplied_journal_replay_is_quiet_and_keeps_fighter_damage_separate(combat,clock):
    c=combat
    rows=[json.loads(line) for line in (Path(__file__).parents[1]/'fixtures/combat/journal_combat.jsonl').read_text().splitlines()]
    alerts=[]
    for row in rows:
        clock.wall=datetime.fromisoformat(row['timestamp'].replace('Z','+00:00')).timestamp()
        event=GameEvent(content=row,historic=False)
        c.plugin.observe(event,{})
        if row['event']=='HullDamage' and row.get('Fighter') is True:
            assert c.plugin.tracker.mothership['hull']==1
        while not c.host.event_manager.incoming.empty():
            alert=c.host.event_manager.incoming.get_nowait();alert.responded_at=None
            alerts.append(alert.plugin_event_content['code'])
            c.run(alert)
        if row['event']=='Bounty':
            for name in ('TARSExplorerTarget','TARSObservatoryFact','TARSChatter'):
                optional=finding();optional.plugin_event_name=name
                optional.plugin_event_content['_guard']['triggered_at']=clock.wall
                c.run(optional)
    assert c.host.llmModel.calls==0
    assert c.plugin.tracker.totals['bounty_awards']==36
    assert c.plugin.tracker.totals['bounty_credits']==10086613
    assert c.plugin.tracker.totals['shield_losses']==3
    assert c.plugin.tracker.totals['fighter_losses']==1
    assert c.plugin.tracker.totals['fighter_rebuilds']==1
    assert alerts==['fighter_destroyed']
    assert c.host.tts.say.call_count==1
