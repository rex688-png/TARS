"""Behavioral contracts for safe product boundaries; all use disposable profiles."""
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.lib.ActionPermissions import ActionApprovals, permission_mode
from src.lib.ConfigPersistence import (save_profile, read_valid, recover_profile,
                                       create_manual_backup, restore_manual_backup)
from src.lib.ResponsePresentation import current_fact_envelope
from src.lib.SupportBundle import build_support_bundle


def profile():
    return {'config_version':20,'tars_profile_version':1,'characters':[{'name':'TARS','prompt':'PRIVATE PROMPT'}],
            'plugin_settings':{'pocket':{'cpu_threads':1,'token':'PRIVATE TOKEN'}},
            'llm_api_key':'PRIVATE KEY','commander_name':'TEST','tts_provider':'none'}


def call(name='textMessage',args='{"channel":"local","message":"Hello"}'):
    return SimpleNamespace(id='call-1', function=SimpleNamespace(name=name,arguments=args))


def test_permission_modes_and_one_shot_approval_never_execute_without_confirmation():
    state={'allowed_actions':{'textMessage':True,'shipSpotLightToggle':True},'action_permissions':{}}
    emitted=[]; clock=[0]
    approvals=ActionApprovals(lambda:state,lambda name,**kw:emitted.append((name,kw)),lambda:clock[0])
    assert permission_mode(state,'textMessage')=='ask'
    assert permission_mode(state,'shipSpotLightToggle')=='allow'
    message=approvals.request(call(),'textMessage')
    assert 'Not executed' in message
    token=emitted[0][1]['request_id']
    assert approvals.resolve(token,False) is None
    assert approvals.resolve(token,True) is None
    approvals.request(call(),'textMessage'); token=emitted[-1][1]['request_id']
    state['action_permissions']['textMessage']='block'
    assert approvals.resolve(token,True) is None
    state['action_permissions']['textMessage']='ask'
    approvals.request(call(),'textMessage'); token=emitted[-1][1]['request_id'];clock[0]=61
    assert approvals.resolve(token,True) is None
    clock[0]=62; approvals.request(call(),'textMessage'); token=emitted[-1][1]['request_id']
    approved=approvals.resolve(token,True)
    assert approved.function.name=='textMessage'
    assert approvals.resolve(token,True) is None


def test_atomic_profile_and_manual_backup_preserve_saved_provider_tuning(tmp_path,monkeypatch):
    path=tmp_path/'config.json'; initial=profile();save_profile(initial,path)
    changed=profile();changed['plugin_settings']['pocket']['cpu_threads']=2
    save_profile(changed,path)
    assert read_valid(tmp_path/'config.backup.json')['plugin_settings']['pocket']['cpu_threads']==1
    assert read_valid(path)['plugin_settings']['pocket']['cpu_threads']==2
    create_manual_backup(path)
    newer=profile();newer['plugin_settings']['pocket']['cpu_threads']=3;save_profile(newer,path)
    assert restore_manual_backup(path)['plugin_settings']['pocket']['cpu_threads']==2
    assert read_valid(path)['plugin_settings']['pocket']['cpu_threads']==2
    old=path.read_bytes()
    def fail_replace(*args): raise OSError('simulated interrupted replace')
    monkeypatch.setattr('src.lib.ConfigPersistence.os.replace',fail_replace)
    with pytest.raises(OSError): save_profile(newer,path)
    assert path.read_bytes()==old


def test_corrupt_config_recovers_last_known_good(tmp_path):
    path=tmp_path/'config.json';safe=profile();save_profile(safe,path)
    saved=profile();saved['plugin_settings']['pocket']['cpu_threads']=2;save_profile(saved,path)
    path.write_text('{bad json',encoding='utf-8')
    assert recover_profile(path)==safe
    assert read_valid(path)==safe
    assert (tmp_path/'config.corrupt.json').read_text()=='{bad json'


@pytest.mark.parametrize('damage', [
    {'characters':[123]},
    {'characters':[{}]},
    {'characters':[]},
    {'plugin_settings':{'provider':['invalid settings']}},
    {'action_permissions':['allow']},
    {'action_permissions':{'textMessage':'invalid'}},
    {'active_character_index':10},
    {'config_version':'invalid'},
])
def test_invalid_manual_backup_cannot_replace_current_profile(tmp_path, damage):
    path=tmp_path/'config.json'; current=profile(); save_profile(current,path)
    invalid=profile(); invalid.update(damage)
    (tmp_path/'config.manual-backup.json').write_text(json.dumps(invalid),encoding='utf-8')
    previous=path.read_bytes()
    with pytest.raises(ValueError): restore_manual_backup(path)
    assert path.read_bytes()==previous


def test_manual_backup_restores_whole_local_profile_without_other_files(tmp_path):
    path=tmp_path/'config.json'; current=profile()
    current.update({'input_device_name':'Mic A','output_device_name':'Speaker B',
                    'llm_model_name':'gpt-6-luna','llm_reasoning_effort':'none',
                    'action_permissions':{'textMessage':'block'},'tars_setup_complete':True,
                    'characters':[{'name':'TARS','prompt':'PRIVATE PROMPT','react_to_text_local_var':False}]})
    save_profile(current,path); create_manual_backup(path)
    changed=profile();save_profile(changed,path)
    assert restore_manual_backup(path)==current
    assert read_valid(path)==current
    assert sorted(item.name for item in tmp_path.iterdir())==[
        'config.backup.json','config.json','config.manual-backup.json']


def test_support_zip_rejects_secrets_and_untrusted_free_text():
    config=profile();config.update({'llm_provider':'openai','embedding_provider':'none',
                                    'config_version':'PRIVATE KEY','tars_profile_version':'PRIVATE TOKEN'})
    bundle=build_support_bundle(config,{'commit':'a'*40,'health':[{'component':'backend','status':'ready','detail':'PRIVATE KEY'},
             {'component':'untrusted secret','status':'error'}], 'log_counts':{'info':3,'SECRET':'PRIVATE TOKEN'},
             'log_entries':[{'level':'info','timestamp':'2026-10-09T00:00:00Z','message':'PRIVATE KEY'}], 'conversation':'PRIVATE CONVERSATION', 'prompt':'PRIVATE PROMPT'})
    with zipfile.ZipFile(io.BytesIO(__import__('base64').b64decode(bundle))) as archive:
        names=archive.namelist(); payload=b''.join(archive.read(name) for name in names)
    assert {'runtime.json','log-summary.json','recent-logs.jsonl','README.txt'}==set(names)
    for value in (b'PRIVATE KEY',b'PRIVATE TOKEN',b'PRIVATE PROMPT',b'PRIVATE CONVERSATION',b'untrusted secret'):
        assert value not in payload
    assert b'OpenAI' in payload and b'a'*40 in payload and b'"backend"' in payload
    assert b'TARSObservatoryBridge' in payload


def test_support_zip_contains_only_allowlisted_member_names_and_no_private_paths():
    config=profile();config['ed_journal_path']='C:/Users/PRIVATE USER/Elite/Journals'
    secret='PRIVATE USER'
    bundle=build_support_bundle(config,{'commit':'b'*40,
        'health':[{'component':'backend','status':'error','detail':secret}],
        'log_entries':[{'level':'error','timestamp':'2026-10-09T12:00:00Z','message':secret}],
        'conversation':secret,'prompt':secret,'path':secret})
    with zipfile.ZipFile(io.BytesIO(__import__('base64').b64decode(bundle))) as archive:
        assert set(archive.namelist())=={'runtime.json','log-summary.json','recent-logs.jsonl','README.txt'}
        assert secret.encode() not in b''.join(archive.read(name) for name in archive.namelist())


def test_fact_envelope_labels_snapshot_without_repeating_conflicting_history():
    states={'CurrentStatus':{'Balance':0,'Fuel':96.168,'Cargo':0},
            'ShipInfo':{'Name':'eXPY','Model':'Caspian Explorer'},
            'Location':{'StarSystem':'Test System','Docked':False},
            'NavInfo':{'NavRoute':[{'StarSystem':'A'},{'StarSystem':'B'}]}}
    facts=current_fact_envelope(states,freshness='LAST KNOWN')
    assert facts['fuel']=={'value':96.168,'source':'CurrentStatus/ShipInfo','freshness':'LAST KNOWN'}
    assert facts['credits']['value']==0 and facts['jumps_remaining']['value']==1
    assert facts['ship_model']['value']=='Caspian Explorer'
    assert current_fact_envelope(states,freshness='LIVE')['location']['freshness']=='LIVE'

def test_real_action_dispatch_never_reaches_input_before_approval(monkeypatch):
    from src.lib import ActionManager as module
    monkeypatch.setattr(module,'KeyValueStore',lambda *_:object())
    manager=module.ActionManager(); physical=Mock(return_value='Elite confirmed')
    manager.actions={'textMessage':{'permission':'textMessage','method':physical}}
    config={'allowed_actions':{'textMessage':True},'action_permissions':{}}
    notices=[];manager.configure_permissions(lambda:config,lambda name,**kw:notices.append((name,kw)))
    request=call()
    assert 'Not executed' in manager.runAction(request,{})['content']
    physical.assert_not_called();token=notices[-1][1]['request_id']
    manager.confirm_action(token,False,{})
    physical.assert_not_called()
    assert 'Not executed' in manager.runAction(request,{})['content']
    token=notices[-1][1]['request_id'];result=manager.confirm_action(token,True,{})
    assert result['content']=='Elite confirmed';physical.assert_called_once()
    assert manager.confirm_action(token,True,{}) is None
    config['action_permissions']['textMessage']='block'
    assert 'blocked' in manager.runAction(request,{})['content'];physical.assert_called_once()
    config['action_permissions']['textMessage']='allow'
    assert manager.runAction(request,{})['content']=='Elite confirmed';assert physical.call_count==2


def test_real_action_dispatch_expired_approval_never_reaches_game_input(monkeypatch):
    from src.lib import ActionManager as module
    monkeypatch.setattr(module,'KeyValueStore',lambda *_:object())
    manager=module.ActionManager();physical=Mock(return_value='Elite confirmed')
    manager.actions={'textMessage':{'permission':'textMessage','method':physical}}
    notices=[];manager.configure_permissions(lambda:{'allowed_actions':{'textMessage':True},'action_permissions':{'textMessage':'ask'}},
                                              lambda name,**kw:notices.append((name,kw)))
    clock=[0]; manager.approvals.clock=lambda:clock[0]
    assert 'Not executed' in manager.runAction(call(),{})['content']
    clock[0]=60
    assert manager.confirm_action(notices[-1][1]['request_id'],True,{}) is None
    physical.assert_not_called()

def test_tars_config_upgrade_preserves_setup_permissions_keys_and_provider_settings(monkeypatch,tmp_path):
    import src.lib.Config as config_module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('TARS_RUNTIME_PROFILE','1')
    monkeypatch.setenv('TARS_CANONICAL_PROMPT',str(Path(__file__).resolve().parents[2]/'vendor'/'tars-plugins'/'prompt'/'prompt.txt'))
    monkeypatch.setattr(config_module,'get_default_input_device_name',lambda:'')
    monkeypatch.setattr(config_module,'get_default_output_device_name',lambda:'')
    current=config_module.load_config()
    current['commander_name']='TEST';current['api_key']='EXAMPLE ONLY'
    current['tars_setup_step']=4;current['action_permissions']={'textMessage':'block'}
    current['plugin_settings']={'provider':{'cpu_threads':1,'voice':'existing'}}
    current.update({'llm_model_name':'custom-user-model','llm_reasoning_effort':'none',
                    'llm_temperature':0.3,'tts_provider':'edge-tts',
                    'stt_provider':'openai','input_device_name':'MIC TEST',
                    'output_device_name':'SPEAKER TEST','cn_autostart':True,
                    'overlay_position':'left','ptt_key':'KeyboardKey:Test'})
    current['characters'][0]['character']='TARS custom saved personality for {commander_name}'
    config_module.save_config(current)
    reloaded=config_module.load_config()
    assert reloaded['tars_setup_step']==4
    assert reloaded['action_permissions']['textMessage']=='block'
    assert reloaded['plugin_settings']['provider']=={'cpu_threads':1,'voice':'existing'}
    assert reloaded['api_key']=='EXAMPLE ONLY'
    for field in ('llm_model_name','llm_reasoning_effort','llm_temperature','tts_provider',
                  'stt_provider','input_device_name','output_device_name','cn_autostart',
                  'overlay_position','ptt_key'):
        assert reloaded[field]==current[field],field
    assert reloaded['characters'][0]['character']==current['characters'][0]['character']
    reloaded['tars_setup_complete']=True
    config_module.save_config(reloaded)
    assert config_module.load_config()['tars_setup_complete'] is True

def test_startup_provider_diagnostics_name_selected_plugin_not_generic_voice():
    from src.lib.SupportBundle import provider_summary
    from src.lib.TarsProviderRegistry import TARS_PROVIDER_SPECS
    pocket=next(spec for spec in TARS_PROVIDER_SPECS if spec.key=='pocket-tts')
    choices=provider_summary({'tts_provider':f'plugin:{pocket.guid}:{pocket.provider_id}',
                              'llm_provider':'openai'})
    assert choices['tts']['name']==pocket.label
    assert choices['tts']['approved_package_version']==pocket.version
    assert 'Ava' not in str(choices)
