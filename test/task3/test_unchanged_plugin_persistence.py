"""Persist real Navigator/Expedition state changes, not duplicate callbacks."""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2] / "vendor" / "tars-plugins"


def load_plugin(name):
    modules = {}
    for key in ("lib", "lib.PluginBase", "lib.PluginHelper", "lib.Logger"):
        modules[key] = types.ModuleType(key)
    class PluginBase:
        def __init__(self, manifest):
            pass
    modules["lib.PluginBase"].PluginBase = PluginBase
    modules["lib.PluginBase"].PluginManifest = type("PluginManifest", (), {})
    modules["lib.PluginHelper"].PluginHelper = type("PluginHelper", (), {})
    modules["lib.PluginHelper"].PluginEvent = type("PluginEvent", (), {})
    modules["lib.Logger"].log = lambda *args: None
    path = ROOT / "plugins" / name / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"persistence_{name}", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return getattr(module, name)


class PersistenceTests(unittest.TestCase):
    def test_duplicate_live_event_does_not_replace_state(self):
        event = types.SimpleNamespace(
            kind="game", historic=False,
            content={"timestamp": "2026-10-21T12:00:00Z", "event": "Location", "StarSystem": "Sol"},
        )
        for name in ("TARSNavigator", "TARSExpedition"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                plugin = load_plugin(name)(None)
                plugin._state_path = Path(directory) / "state.json"
                plugin._observe_event(event, {})
                first = plugin._state_path.read_bytes()
                with patch.object(Path, "replace", wraps=Path.replace) as replace:
                    plugin._observe_event(event, {})
                    self.assertEqual(replace.call_count, 0)
                self.assertEqual(plugin._state_path.read_bytes(), first)

    def test_unchanged_state_skips_replacement_and_changes_survive_restart(self):
        for name in ("TARSNavigator", "TARSExpedition"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                cls = load_plugin(name)
                state_path = Path(directory) / "state.json"
                plugin = cls(None)
                plugin._state_path = state_path
                plugin._save()
                initial = state_path.read_bytes()
                with patch.object(Path, "replace", wraps=Path.replace) as replace:
                    plugin._save()
                    plugin.on_chat_stop(None)
                    self.assertEqual(replace.call_count, 0)
                self.assertEqual(state_path.read_bytes(), initial)

                plugin._state["last_event_key"] = "changed"
                plugin._save()
                self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["last_event_key"], "changed")
                reloaded = cls(None)
                reloaded._state_path = state_path
                reloaded._load()
                with patch.object(Path, "replace", wraps=Path.replace) as replace:
                    reloaded._save()
                    self.assertEqual(replace.call_count, 0)

    def test_failed_replace_retries_same_state(self):
        for name in ("TARSNavigator", "TARSExpedition"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                plugin = load_plugin(name)(None)
                plugin._state_path = Path(directory) / "state.json"
                plugin._save()
                plugin._state["last_event_key"] = "changed"
                with patch.object(Path, "replace", side_effect=OSError("replace failed")):
                    plugin._save()
                self.assertIsNone(json.loads(plugin._state_path.read_text(encoding="utf-8"))["last_event_key"])
                plugin._save()
                self.assertEqual(json.loads(plugin._state_path.read_text(encoding="utf-8"))["last_event_key"], "changed")


if __name__ == "__main__":
    unittest.main()
