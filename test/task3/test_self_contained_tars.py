import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from lib import Config as config_module
from tools import verify_tars_bundle


def test_bundled_payload_matches_provenance():
    expected = json.loads(verify_tars_bundle.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert expected["source_revision"] == verify_tars_bundle.PINNED_SHA
    assert expected["files"] == verify_tars_bundle.payload_files(
        verify_tars_bundle.BUNDLE_ROOT
    )


def test_bundled_payload_matches_pinned_checkout_when_present():
    source = REPO_ROOT.parent / "TARS-Plugins"
    if not (source / ".git").is_dir():
        import pytest
        pytest.skip("requires the separate pinned TARS-Plugins checkout")
    assert verify_tars_bundle.source_sha(source) == verify_tars_bundle.PINNED_SHA
    assert verify_tars_bundle.payload_files(source) == verify_tars_bundle.payload_files(
        verify_tars_bundle.BUNDLE_ROOT
    )


def test_fresh_tars_profile_uses_canonical_prompt(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TARS_RUNTIME_PROFILE", "1")
    monkeypatch.setenv(
        "TARS_BUNDLED_RESOURCES", str(verify_tars_bundle.BUNDLE_ROOT)
    )
    monkeypatch.setattr(config_module, "get_default_input_device_name", lambda: "")
    monkeypatch.setattr(config_module, "get_default_output_device_name", lambda: "")

    config = config_module.load_config()

    character = config["characters"][0]
    assert character["name"] == "TARS"
    assert character["character"] == (
        verify_tars_bundle.BUNDLE_ROOT / "prompt" / "prompt.txt"
    ).read_text(encoding="utf-8")
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == config


def test_fresh_tars_profile_fails_instead_of_using_stock_prompt(monkeypatch, tmp_path):
    import pytest

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TARS_RUNTIME_PROFILE", "1")
    monkeypatch.setenv("TARS_BUNDLED_RESOURCES", str(tmp_path / "missing"))
    monkeypatch.setattr(config_module, "get_default_input_device_name", lambda: "")
    monkeypatch.setattr(config_module, "get_default_output_device_name", lambda: "")

    with pytest.raises(config_module.TarsPackagingError, match="canonical prompt"):
        config_module.load_config()
    assert not (tmp_path / "config.json").exists()


def test_existing_tars_config_is_not_overwritten(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "get_default_input_device_name", lambda: "")
    monkeypatch.setattr(config_module, "get_default_output_device_name", lambda: "")
    existing = config_module.load_config()
    existing["commander_name"] = "Existing Commander"
    existing["characters"][0]["name"] = "My Character"
    existing["characters"][0]["character"] = "Keep this prompt"
    config_module.save_config(existing)
    config_path = tmp_path / "config.json"
    before = config_path.read_bytes()
    monkeypatch.setenv("TARS_RUNTIME_PROFILE", "1")
    monkeypatch.setenv(
        "TARS_BUNDLED_RESOURCES", str(verify_tars_bundle.BUNDLE_ROOT)
    )

    config = config_module.load_config()

    assert any(character["name"] == "My Character" for character in config["characters"])
    assert any(
        character["character"] == "Keep this prompt"
        for character in config["characters"]
    )
    assert config_path.read_bytes() == before
