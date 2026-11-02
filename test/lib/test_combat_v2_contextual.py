"""Optional contextual assistance through real Combat and shared speech leases."""
import pytest
from test_combat_v1 import combat
from test_speech_arbiter import arbiter,clock
from lib.Event import ConversationEvent, GameEvent
from lib.TTS import TTSLine


def history(c,clock,enabled=True):
    c.plugin.settings['commentary']=enabled
    c.feed('Music',MusicTrack='Combat')
    start=clock.wall
    for t in range(0,46,5):
        clock.wall=start+t;clock.tick=t
        c.feed('ShipTargeted',TargetLocked=True,ScanStage=3,Ship='anaconda',PilotName='Synthetic',
               ShieldHealth=0 if t in (10,25) else 30,HullHealth=100)


@pytest.mark.parametrize('mode',['off','observe','enforce'])
def test_optional_context_is_deterministic_and_strict_in_every_rollout_mode(combat,clock,mode):
    c=combat;c.host.config['speech_director_mode']=mode
    history(c,clock)
    event=c.host.event_manager.incoming.get_nowait();event.responded_at=None
    assert event.plugin_event_name=='TARSCombatObservation'
    assert event.plugin_event_content.get('_speech_admission')
    c.host.pending=[event]
    assert c.host.should_reply(c.states)
    c.run(event)
    assert c.host.llmModel.calls==0
    assert c.host.tts.say.call_count==1
    assert 'at least twice' in c.host.tts.say.call_args.args[0]
    assert c.host.event_manager.add_conversation_event.call_args.kwargs['reasons']==['combat_contextual_observation']


def test_default_off_preserves_silence_and_controls(combat,clock):
    c=combat;history(c,clock,False)
    assert c.host.event_manager.incoming.empty()
    assert c.host.llmModel.calls==0 and not c.host.tts.say.called
    assert c.plugin.settings.get('fast_commands',False) is False
    assert c.plugin.observations.scope is None


def test_sustained_mothership_damage_uses_the_same_zero_model_delivery_path(combat,clock):
    c=combat;c.plugin.settings['commentary']=True
    c.feed('Music',MusicTrack='Combat');start=clock.wall
    for t in range(31):
        clock.wall=start+t;clock.tick=t
        c.feed('Status',flags={'InMainShip':True,'ShieldsUp':False,'InDanger':True})
        if t in (1,20,30):c.feed('HullDamage',Fighter=False,Health={1:.95,20:.9,30:.8}[t])
    event=c.host.event_manager.incoming.get_nowait();event.responded_at=None
    c.run(event)
    assert 'half a minute unshielded' in c.host.tts.say.call_args.args[0]
    assert c.host.llmModel.calls==0


@pytest.mark.parametrize('change',['expiry','target_switch','disabled','combat_exit'])
def test_expiry_target_change_and_feature_disable_drop_without_generation(combat,clock,change):
    c=combat;history(c,clock)
    event=c.host.event_manager.incoming.get_nowait();event.responded_at=None
    if change=='expiry':clock.wall+=5;clock.tick+=5
    elif change=='disabled':c.plugin.settings['commentary']=False
    elif change=='combat_exit':c.feed('FSDJump')
    else:c.feed('ShipTargeted',TargetLocked=True,ScanStage=3,Ship='anaconda',PilotName='Other',ShieldHealth=100,HullHealth=100)
    c.run(event)
    assert c.host.llmModel.calls==0 and not c.host.tts.say.called
    c.plugin.settings['commentary']=False
    assert c.plugin.observation(event.plugin_event_content) is None


def test_direct_request_discards_optional_speech_and_uses_existing_conversation(combat,clock):
    c=combat;history(c,clock)
    event=c.host.event_manager.incoming.get_nowait();event.responded_at=None
    direct=ConversationEvent(kind='user',content='Explain the target scan.',responded_at=None)
    c.run(event,direct)
    assert c.host.llmModel.calls==1
    assert c.host.tts.say.call_args.args[0]=='A direct answer.'
    assert not c.host.speech_arbiter().optional_event_valid(event.plugin_event_content['_speech_admission'])


def test_critical_alert_interrupts_active_observation_and_keeps_original_warning(combat,clock):
    c=combat;history(c,clock)
    event=c.host.event_manager.incoming.get_nowait();event.responded_at=None
    ordinary_say=c.host.tts.say.side_effect
    critical=[]
    def during_observation(*args,**kwargs):
        line=TTSLine()
        c.host.tts.abort.side_effect=lambda:line.settle('interrupted')
        c.feed('FighterDestroyed',ID=15)
        alert=c.host.event_manager.incoming.get_nowait();alert.responded_at=None
        critical.append(alert);c.host.on_event(alert,c.states)
        assert line.result.outcome=='interrupted'
        return line
    c.host.tts.say.side_effect=during_observation
    c.run(event)
    c.host.tts.abort.assert_called_once()
    assert c.host.llmModel.calls==0
    c.host.tts.say.side_effect=ordinary_say
    c.run(critical[0])
    assert c.host.tts.say.call_args.args[0]=='Fighter destroyed.'


def test_target_change_interrupts_only_the_optional_remark(combat,clock):
    c=combat;history(c,clock)
    event=c.host.event_manager.incoming.get_nowait();event.responded_at=None
    def switch(*args,**kwargs):
        line=TTSLine();c.host.tts.abort.side_effect=lambda:line.settle('interrupted')
        change=c.feed('ShipTargeted',TargetLocked=False)
        c.host.on_event(change,c.states)
        return line
    c.host.tts.say.side_effect=switch;c.run(event)
    c.host.tts.abort.assert_called_once()
    assert c.host.llmModel.calls==0


def test_optional_event_never_consumes_existing_enabled_native_work(combat,clock):
    c=combat;history(c,clock)
    event=c.host.event_manager.incoming.get_nowait();event.responded_at=None
    c.host.enabled_game_events=['Music']
    native=GameEvent(content={'event':'Music'},historic=False,responded_at=None)
    c.run(event,native)
    assert c.host.llmModel.calls==1
    assert c.host.tts.say.call_args.args[0]=='A direct answer.'


@pytest.mark.parametrize('mode',['off','observe','enforce'])
def test_existing_busy_priority_prevents_preparation_in_every_mode(combat,clock,mode):
    c=combat;c.host.config['speech_director_mode']=mode
    c.host.reply_pending=True
    history(c,clock)
    assert c.host.event_manager.incoming.empty()
    assert not c.host.tts.say.called and c.host.llmModel.calls==0
