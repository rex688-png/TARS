import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel


class ActionArgs(BaseModel):
    value: int


class RecordingActionManager:
    def __init__(self):
        self.registration = None

    def registerAction(self, **registration):
        self.registration = registration


@pytest.fixture(scope="module")
def plugin_helper_class():
    """Import PluginHelper with temporary leaf stubs and restore import state."""
    assistant_stub = types.ModuleType("src.lib.Assistant")
    assistant_stub.Assistant = object
    module_name = "src.lib.PluginHelper"
    previous_module = sys.modules.pop(module_name, None)
    parent = importlib.import_module("src.lib")
    missing = object()
    previous_attribute = getattr(parent, "PluginHelper", missing)
    if previous_attribute is not missing:
        delattr(parent, "PluginHelper")
    try:
        with patch.dict(
            sys.modules,
            {"pyaudio": MagicMock(), "src.lib.Assistant": assistant_stub},
        ):
            module = importlib.import_module(module_name)
            yield module.PluginHelper
    finally:
        sys.modules.pop(module_name, None)
        if previous_module is not None:
            sys.modules[module_name] = previous_module
        if previous_attribute is missing:
            if hasattr(parent, "PluginHelper"):
                delattr(parent, "PluginHelper")
        else:
            setattr(parent, "PluginHelper", previous_attribute)


def _register(callback, plugin_helper_class):
    manager = RecordingActionManager()
    helper = plugin_helper_class.__new__(plugin_helper_class)
    helper._action_manager = manager
    helper.register_action("test_action", "test", ActionArgs, callback)
    assert manager.registration is not None
    return manager.registration["method"]


def test_one_argument_plugin_action_receives_model_once(plugin_helper_class):
    calls = []

    def callback(model):
        calls.append(model.value)
        return "one"

    action = _register(callback, plugin_helper_class)
    assert action({"value": 7}, {"state": True}) == "one"
    assert calls == [7]


def test_two_argument_plugin_action_receives_model_and_context_once(plugin_helper_class):
    calls = []

    def callback(model, context):
        calls.append((model.value, context))
        return "two"

    action = _register(callback, plugin_helper_class)
    context = {"state": True}
    assert action({"value": 8}, context) == "two"
    assert calls == [(8, context)]


def test_varargs_plugin_action_preserves_two_argument_contract(plugin_helper_class):
    calls = []

    def callback(*args):
        calls.append(args)
        return "varargs"

    action = _register(callback, plugin_helper_class)
    context = {"state": True}
    assert action({"value": 9}, context) == "varargs"
    assert len(calls) == 1
    assert calls[0][0].value == 9
    assert calls[0][1] is context


def test_internal_type_error_is_not_retried_and_keeps_error_contract(plugin_helper_class):
    calls = []

    def callback(model):
        calls.append(model.value)
        raise TypeError("inside callback")

    action = _register(callback, plugin_helper_class)
    assert action({"value": 10}, {}) == "Error executing action test_action: inside callback"
    assert calls == [10]


def test_unsupported_callback_signature_fails_at_registration(plugin_helper_class):
    def callback():
        return "never"

    manager = RecordingActionManager()
    helper = plugin_helper_class.__new__(plugin_helper_class)
    helper._action_manager = manager

    try:
        helper.register_action("test_action", "test", ActionArgs, callback)
    except TypeError as exc:
        assert "must accept one or two positional arguments" in str(exc)
    else:
        raise AssertionError("unsupported callback signature was registered")
    assert manager.registration is None
