import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.PluginManager import PluginManager
from lib.TarsProviderRegistry import MARKER_NAME, TARS_PROVIDER_SPECS


def _write_plugin(root: Path, folder_name: str, position: int) -> None:
    folder = root / folder_name
    folder.mkdir(parents=True)
    entrypoint = f"entry_{position}.py"
    (folder / entrypoint).write_text("# synthetic entrypoint\n", encoding="utf-8")
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "guid": f"test-guid-{position}",
                "name": folder_name,
                "author": "TEST",
                "version": "1.0.0",
                "repository": "",
                "entrypoint": entrypoint,
            }
        ),
        encoding="utf-8",
    )


def test_tars_profile_loads_only_required_plugins_in_fixed_order(monkeypatch, tmp_path):
    monkeypatch.setenv("TARS_PROVIDER_ROOT", str(tmp_path / "providers"))
    for position, name in enumerate(reversed(PluginManager.TARS_PLUGIN_ORDER)):
        _write_plugin(tmp_path, name, position)

    manager = PluginManager({}, tars_profile=True, plugin_folder=str(tmp_path))
    loaded = []

    def fake_load(manifest, entrypoint):
        loaded.append(Path(entrypoint).parent.name)
        return SimpleNamespace(plugin_manifest=manifest)

    manager.load_plugin_module = fake_load
    manager.load_default_plugins = lambda: pytest.fail("built-in plugins must not load")
    manager.load_plugins()

    assert loaded == list(PluginManager.TARS_PLUGIN_ORDER)
    assert len(manager.plugin_list) == 7
    assert len(manager.builtin_plugin_guids) == 2

    manager.register_settings()
    assert {provider["kind"] for provider in manager.plugin_model_providers} == {
        "llm", "vlm", "embedding", "stt", "tts"
    }
    installer = manager.plugin_settings_configs[
        "71be4c2e-4a49-45f7-b968-d70588bdae74"
    ]
    assert [grid["key"] for grid in installer["grids"]] == [
        "parakeet-stt", "pocket-tts", "supertonic-tts", "gemma-embedding"
    ]


def test_tars_profile_fails_clearly_when_required_plugin_is_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("TARS_PROVIDER_ROOT", str(tmp_path / "providers"))
    for position, name in enumerate(PluginManager.TARS_PLUGIN_ORDER[:-1]):
        _write_plugin(tmp_path, name, position)

    manager = PluginManager({}, tars_profile=True, plugin_folder=str(tmp_path))
    with pytest.raises(RuntimeError, match="TARSExpedition/manifest.json"):
        manager.load_plugins()


def test_tars_profile_ignores_unapproved_plugin_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("TARS_PROVIDER_ROOT", str(tmp_path / "providers"))
    for position, name in enumerate(PluginManager.TARS_PLUGIN_ORDER):
        _write_plugin(tmp_path, name, position)
    _write_plugin(tmp_path, "ArbitraryPlugin", 99)

    manager = PluginManager({}, tars_profile=True, plugin_folder=str(tmp_path))
    loaded = []
    manager.load_plugin_module = lambda manifest, entrypoint: (
        loaded.append(Path(entrypoint).parent.name)
        or SimpleNamespace(plugin_manifest=manifest)
    )
    manager.load_plugins()

    assert loaded == list(PluginManager.TARS_PLUGIN_ORDER)
    assert "ArbitraryPlugin" not in loaded


@pytest.mark.parametrize("spec", TARS_PROVIDER_SPECS)
def test_tars_profile_loads_only_explicitly_installed_provider(
    monkeypatch, tmp_path, spec
):
    behavior_root = tmp_path / "behavior"
    provider_root = tmp_path / "providers"
    monkeypatch.setenv("TARS_PROVIDER_ROOT", str(provider_root))
    for position, name in enumerate(PluginManager.TARS_PLUGIN_ORDER):
        _write_plugin(behavior_root, name, position)

    approved = provider_root / spec.folder
    approved.mkdir(parents=True)
    (approved / spec.entrypoint).write_text("# approved provider\n", encoding="utf-8")
    (approved / "manifest.json").write_text(json.dumps({
        "guid": spec.guid, "name": spec.label, "author": "COVAS Labs",
        "version": spec.version, "repository": spec.url,
        "entrypoint": spec.entrypoint,
    }), encoding="utf-8")
    (approved / MARKER_NAME).write_text(json.dumps({
        "key": spec.key, "version": spec.version, "sha256": spec.sha256,
        "source_revision": spec.source_revision,
    }), encoding="utf-8")
    arbitrary = provider_root / "arbitrary-provider"
    arbitrary.mkdir()
    (arbitrary / "manifest.json").write_text("{}", encoding="utf-8")

    manager = PluginManager({}, tars_profile=True, plugin_folder=str(behavior_root))
    loaded = []
    def fake_load(manifest, entrypoint):
        folder_name = Path(entrypoint).parent.name
        loaded.append(folder_name)
        return SimpleNamespace(
            plugin_manifest=manifest,
            settings_config=None,
            model_providers=([{
                "kind": spec.kind,
                "id": spec.provider_id,
                "label": spec.label,
                "settings_config": [],
            }] if folder_name == spec.folder else None),
        )
    manager.load_plugin_module = fake_load
    manager.load_plugins()
    manager.register_settings()

    assert loaded == [spec.folder, *PluginManager.TARS_PLUGIN_ORDER]
    assert "arbitrary-provider" not in loaded
    assert spec.guid in manager.builtin_plugin_guids
    assert any(
        provider["plugin_guid"] == spec.guid
        and provider["id"] == spec.provider_id
        for provider in manager.plugin_model_providers
    )


def test_default_profile_retains_existing_loader(monkeypatch, tmp_path):
    manager = PluginManager({}, tars_profile=False, plugin_folder=str(tmp_path))
    called = []
    monkeypatch.setattr(manager, "load_default_plugins", lambda: called.append("builtins"))

    manager.load_plugins()

    assert called == ["builtins"]


def test_tars_profile_selects_pinned_external_checkout_in_order():
    plugins_root = Path(__file__).resolve().parents[3] / "TARS-Plugins"
    if not (plugins_root / ".git").exists():
        pytest.skip("requires the separate pinned TARS-Plugins checkout")
    sha = subprocess.run(
        ["git", "-C", str(plugins_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert sha == "685e16a19d5a5cd83f16297b90ee4c58ba8e11b5"

    manager = PluginManager(
        {}, tars_profile=True, plugin_folder=str(plugins_root / "plugins")
    )
    loaded = []

    def fake_load(manifest, entrypoint):
        loaded.append((Path(entrypoint).parent.name, manifest.entrypoint))
        return SimpleNamespace(plugin_manifest=manifest)

    manager.load_plugin_module = fake_load
    manager.load_plugins()

    assert [folder for folder, _ in loaded] == list(PluginManager.TARS_PLUGIN_ORDER)
    assert all(entrypoint.endswith(".py") for _, entrypoint in loaded)
