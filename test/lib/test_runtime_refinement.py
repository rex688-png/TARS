"""Host-neutral tests for boundaries used by the actual runtime."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest

from src.lib.ActionPolicy import (explicit_chat_intent, validate_chat_message, confirmed_send,
    wait_for_send, action_intent_allowed, spoken_activity)
from src.lib.ProviderSettings import migrate_provider_settings
from src.lib.ResponsePresentation import current_commander_facts, ExplorationCalloutDeduper


@pytest.mark.parametrize('text', ['Tell me a joke', 'Tell me about this planet', 'Say something',
    'Answer me', "Tell me what ship I'm flying", 'Maybe someone should post in chat', 'Do not send hello to local chat'])
def test_conversation_never_sends_chat(text):
    assert not explicit_chat_intent(text)
    assert not action_intent_allowed('textMessage', text)


@pytest.mark.parametrize('text', ['Send John this message: hello', 'Tell Commander X in chat: hello',
    'Post this to squadron chat: hello', "Send 'hello' to local chat"])
def test_explicit_chat_request_allowed(text):
    assert explicit_chat_intent(text)


@pytest.mark.parametrize('obj,intent', [
    ({'message':'Hi','channel':'commander'}, 'Send John this message: Hi'),
    ({'message':'Hi','channel':'commander','recipient':'Fixture Commander'}, 'Send Fixture Commander this message: Hi'),
    ({'message':'Hi','channel':'commander','recipient':'Bob'}, 'Send John this message: Hi'),
    ({'message':'/quit','channel':'local'}, 'Send /quit to local chat'),
    ({'message':'Hi\n/quit','channel':'local'}, 'Send Hi to local chat'),
    ({'message':'Hi','channel':'made-up'}, 'Send Hi to local chat'),
])
def test_invalid_chat_rejected(obj, intent):
    with pytest.raises(ValueError):
        validate_chat_message(obj, 'Fixture Commander', intent)


def send_event(**kwargs):
    return SimpleNamespace(kind='game', historic=False, content={'event':'SendText', 'Sent':True,
        'To':'local', 'Message':'hello', **kwargs})


def test_confirmation_requires_new_matching_live_sendtext():
    old = send_event()
    assert not confirmed_send([old], {id(old)}, 'hello', 'local')
    assert not confirmed_send([send_event(Message='different')], set(), 'hello', 'local')
    assert not confirmed_send([send_event(Sent=False)], set(), 'hello', 'local')
    assert not confirmed_send([send_event(To='wing')], set(), 'hello', 'local')
    assert confirmed_send([send_event()], set(), 'hello', 'local')
    assert not wait_for_send(lambda: [], set(), 'hello', 'local', timeout=0)


def send_action():
    # Compile the production function without importing desktop/model libraries.
    # Only hardware seams are replaced; validation, sequence and result are real.
    tree = ast.parse(Path('src/lib/actions/Actions.py').read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'send_message')
    scope = dict(validate_chat_message=validate_chat_message,
        latest_user_intent=lambda events: events[0].content,
        get_state_dict=lambda states, key: states[key], sleep=lambda _: None,
        setGameWindowActive=Mock(), keys=Mock(), wait_for_send=Mock(return_value=False),
        event_manager=SimpleNamespace(processed=[SimpleNamespace(content='Send hello to local chat')], pending=[]),
        chat_local_tabbed=False, chat_wing_tabbed=False, chat_system_tabbed=False,
        chat_squadron_tabbed=False, chat_direct_tabbed=False)
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'Actions.py', 'exec'), scope)
    return scope


def test_actual_send_action_validates_before_touching_elite_and_never_assumes_success():
    scope = send_action()
    states = {'Commander':{'Name':'Fixture Commander'}, 'CurrentStatus':{'flags':{'InMainShip':True}}}
    with pytest.raises(ValueError):
        scope['send_message']({'message':'Hi','channel':'commander'}, states)
    scope['setGameWindowActive'].assert_not_called()
    scope['keys'].send.assert_not_called()
    with patch.dict('sys.modules', {'pyautogui':SimpleNamespace(typewrite=Mock())}):
        assert 'not confirmed' in scope['send_message']({'message':'hello','channel':'local'}, states)
        scope['wait_for_send'].return_value = True
        assert 'Elite confirmed message sent' in scope['send_message']({'message':'hello','channel':'local'}, states)


def test_consequential_actions_require_explicit_intent_without_blocking_lights():
    assert not action_intent_allowed('fireWeapons', 'Tell me a joke')
    assert action_intent_allowed('fireWeapons', 'Stop firing')
    assert not action_intent_allowed('ejectAllCargo', 'What cargo do I have?')
    assert action_intent_allowed('ejectAllCargo', 'Jettison cargo')
    assert action_intent_allowed('headlights', 'Turn on the lights')
    assert spoken_activity('web_search_agent') == 'Searching.'
    assert spoken_activity('other_tool') == 'Checking.'


def test_provider_upgrade_defaults_do_not_overwrite_any_saved_tuning():
    saved = {'onnx_threads':1,'max_tokens':90,'generation_steps':6,'gap':320,
             'output_device':'Fixture output','api_key':'synthetic-test-value'}
    plugin = SimpleNamespace(settings=dict(saved), settings_schema_version=2, model_providers=[{'kind':'tts'}])
    def migrate(settings, version):
        settings.update(onnx_threads=4, max_tokens=30, generation_steps=2, gap=150, added_field='default')
    plugin.migrate_settings = migrate
    assert migrate_provider_settings(plugin)
    assert all(plugin.settings[key] == value for key, value in saved.items())
    assert plugin.settings['settings_version'] == 2
    assert plugin.settings['added_field'] == 'default'
    assert not migrate_provider_settings(plugin)


def test_behavior_plugin_migrations_are_not_frozen():
    plugin = SimpleNamespace(settings={'enabled':False}, settings_schema_version=1, model_providers=None,
        migrate_settings=lambda settings, version: settings.update(enabled=True))
    migrate_provider_settings(plugin)
    assert plugin.settings['enabled'] is True


def test_snapshot_precedence_keeps_zero_values_and_does_not_modify_sources():
    states = {'CurrentStatus':{'Balance':0,'Fuel':{'FuelMain':2},'Cargo':0},
        'ShipInfo':{'FuelMain':25,'Name':'eXPY','Model':'Caspian Explorer'},
        'NavInfo':{'NavRoute':[{'StarSystem':'Sol'},{'StarSystem':'Alpha Centauri'}]},
        'Cargo':{'Count':8}}
    facts = current_commander_facts(states)
    assert facts['credits'] == 0 and facts['cargo'] == 0
    assert facts['fuel']['FuelMain'] == 2
    assert facts['ship_model'] == 'Caspian Explorer' and facts['jumps_remaining'] == 1
    assert states['ShipInfo']['FuelMain'] == 25


def test_overlapping_exploration_callouts_preserve_unique_facts_and_numbers():
    dedupe = ExplorationCalloutDeduper()
    repeated = 'Sol A 1 is a terraformable water world.'
    assert dedupe.assemble(repeated + ' ' + repeated, context=('Sol','Sol A 1'), exploration=True, now=0) == repeated
    assert dedupe.assemble(repeated + ' Mapping is complete.', context=('Sol','Sol A 1'), exploration=True, now=2) == 'Mapping is complete.'
    assert dedupe.assemble('Sol A 2 is a terraformable water world.', context=('Sol','Sol A 1'), exploration=True, now=3)
    assert dedupe.assemble(repeated, context=('Other','Sol A 1'), exploration=True, now=4) == repeated
    assert dedupe.assemble(repeated, context=('Sol','Sol A 1'), exploration=True, now=20) == repeated
    assert dedupe.assemble(repeated, context=('Sol','Sol A 1'), exploration=False, now=21) == repeated


def test_log_summary_never_contains_prompt_or_memory_text():
    from src.lib.ResponsePresentation import private_text_summary
    secret = 'Synthetic private prompt and memory content'
    assert secret not in private_text_summary('TARS system prompt loaded', secret)
    assert secret not in private_text_summary('Memory updated', secret)
    assert str(len(secret)) in private_text_summary('Memory updated', secret)
    source = Path('src/Chat.py').read_text()
    assert 'Current backstory:' not in source
    assert 'show_chat_message("memory", event.content)' not in source


def test_actual_action_execution_does_not_speak_query_and_keeps_diagnostics():
    from src.lib.ActionPolicy import latest_user_intent
    tree = ast.parse(Path('src/lib/Assistant.py').read_text())
    assistant = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Assistant')
    method = next(node for node in assistant.body if isinstance(node, ast.FunctionDef) and node.name == 'execute_actions')
    method.decorator_list = []
    # Annotations are compile-time type contracts, not hardware dependencies.
    scope = dict(spoken_activity=spoken_activity, latest_user_intent=latest_user_intent,
        action_intent_allowed=action_intent_allowed, ChatCompletionMessageToolCall=object, ProjectedStates=dict, Any=object)
    exec(compile(ast.Module(body=[method],type_ignores=[]),'Assistant.py','exec'),scope)
    query = 'Searching: current live fuel level for Fixture Commander'
    model_action = SimpleNamespace(id='search-1',function=SimpleNamespace(name='web_search_agent'),model_dump=lambda: {'id':'search-1'})
    fake = SimpleNamespace(tts=SimpleNamespace(say=Mock()), _get_tts_postprocessing_layers=lambda _: [],
        action_manager=SimpleNamespace(getActionDesc=Mock(return_value=query),runAction=Mock(return_value={'content':'Fuel 24 tonnes'})),
        event_manager=SimpleNamespace(processed=[SimpleNamespace(kind='user',content='How much fuel?')], pending=[],
            add_tool_call=Mock(),add_tool_processing=Mock()))
    scope['execute_actions'](fake,[model_action],{})
    assert fake.tts.say.call_args.args[0] == 'Searching.'
    assert fake.event_manager.add_tool_call.call_args.args[2] == [query]
    fake.event_manager.processed = [SimpleNamespace(kind='user',content='Tell me a joke')]
    fake.action_manager.runAction.reset_mock()
    fake.tts.say.reset_mock()
    model_action.function.name='textMessage'
    scope['execute_actions'](fake,[model_action],{})
    fake.action_manager.runAction.assert_not_called()
    fake.tts.say.assert_not_called()
