import sys
import types
from unittest.mock import MagicMock

from pydantic import BaseModel

# PluginHelper's type dependencies import the audio leaf eagerly. Callback
# registration does not use audio, so keep this focused unit test host-neutral.
sys.modules.setdefault("pyaudio", MagicMock())
assistant_stub = types.ModuleType("src.lib.Assistant")
assistant_stub.Assistant = object
sys.modules.setdefault("src.lib.Assistant", assistant_stub)

from src.lib.PluginHelper import PluginHelper


class ActionArgs(BaseModel):
    value: int


class RecordingActionManager:
    def __init__(self):
        self.registration = None

    def registerAction(self, **registration):
        self.registration = registration


def _register(callback):
    manager = RecordingActionManager()
    helper = PluginHelper.__new__(PluginHelper)
    helper._action_manager = manager
    helper.register_action("test_action", "test", ActionArgs, callback)
    assert manager.registration is not None
    return manager.registration["method"]


def test_one_argument_plugin_action_receives_model_once():
    calls = []

    def callback(model):
        calls.append(model.value)
        return "one"

    action = _register(callback)
    assert action({"value": 7}, {"state": True}) == "one"
    assert calls == [7]


def test_two_argument_plugin_action_receives_model_and_context_once():
    calls = []

    def callback(model, context):
        calls.append((model.value, context))
        return "two"

    action = _register(callback)
    context = {"state": True}
    assert action({"value": 8}, context) == "two"
    assert calls == [(8, context)]


def test_varargs_plugin_action_preserves_two_argument_contract():
    calls = []

    def callback(*args):
        calls.append(args)
        return "varargs"

    action = _register(callback)
    context = {"state": True}
    assert action({"value": 9}, context) == "varargs"
    assert len(calls) == 1
    assert calls[0][0].value == 9
    assert calls[0][1] is context


def test_internal_type_error_is_not_retried_and_keeps_error_contract():
    calls = []

    def callback(model):
        calls.append(model.value)
        raise TypeError("inside callback")

    action = _register(callback)
    assert action({"value": 10}, {}) == "Error executing action test_action: inside callback"
    assert calls == [10]


def test_unsupported_callback_signature_fails_at_registration():
    def callback():
        return "never"

    manager = RecordingActionManager()
    helper = PluginHelper.__new__(PluginHelper)
    helper._action_manager = manager

    try:
        helper.register_action("test_action", "test", ActionArgs, callback)
    except TypeError as exc:
        assert "must accept one or two positional arguments" in str(exc)
    else:
        raise AssertionError("unsupported callback signature was registered")
    assert manager.registration is None
