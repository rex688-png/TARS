import hashlib
import json
from pathlib import Path
import sys
import copy
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import lib.Config as config_module
from lib.Config import (
    get_tars_event_reactions,
    load_config,
    reset_tars_prompt,
    set_tars_prompt,
)


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "tars_factory_profile.json").read_text(
        encoding="utf-8"
    )
)


def _state_keys(reactions, state):
    return [key for key, value in reactions.items() if value == state]


def test_exact_reference_reaction_map():
    reactions = get_tars_event_reactions()
    canonical = json.dumps(reactions, sort_keys=True, separators=(",", ":")) + "\n"

    assert hashlib.sha256(canonical.encode()).hexdigest() == FIXTURE["map_sha256"]
    assert _state_keys(reactions, "on") == FIXTURE["on"]
    assert _state_keys(reactions, "hidden") == FIXTURE["hidden"]
    assert {
        state: list(reactions.values()).count(state)
        for state in ("on", "off", "hidden")
    } == FIXTURE["reaction_counts"]


def test_clean_tars_profile_has_fixed_identity_and_reference_defaults(
    monkeypatch, tmp_path
):
    prompt = REPO_ROOT / "vendor" / "tars-plugins" / "prompt" / "prompt.txt"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TARS_RUNTIME_PROFILE", "1")
    monkeypatch.setenv("TARS_CANONICAL_PROMPT", str(prompt))
    monkeypatch.setattr(config_module, "get_default_input_device_name", lambda: "")
    monkeypatch.setattr(config_module, "get_default_output_device_name", lambda: "")

    config = load_config()

    assert config["active_character_index"] == 0
    assert [character["name"] for character in config["characters"]] == ["TARS"]
    character = config["characters"][0]
    assert character["event_reactions"] == get_tars_event_reactions()
    assert character["tts_voice"] == "en-US-AvaMultilingualNeural"
    assert character["tts_speed"] == "1.2"
    assert config["llm_provider"] == config["agent_llm_provider"] == "openai"
    assert config["llm_model_name"] == config["agent_llm_model_name"] == "gpt-6-luna"
    assert config["llm_reasoning_effort"] == config["agent_llm_reasoning_effort"] == "none"
    assert config["llm_temperature"] == config["agent_llm_temperature"] == 0.3
    assert config["agent_llm_max_tries"] == 7
    assert config["vision_provider"] == "openai"
    assert config["vision_model_name"] == "gpt-6-luna"
    assert config["stt_provider"].endswith(":parakeet-stt")
    assert config["tts_provider"].endswith(":pocket-tts")
    assert config["embedding_provider"].endswith(":gemma-embedding")
    assert config["api_key"] == config["llm_api_key"] == ""
    assert hashlib.sha256(character["character"].encode()).hexdigest() == FIXTURE["prompt_sha256"]


def test_existing_tars_profile_cannot_restore_generic_characters(monkeypatch, tmp_path):
    prompt = REPO_ROOT / "vendor" / "tars-plugins" / "prompt" / "prompt.txt"
    (tmp_path / "config.json").write_text(json.dumps({
        "config_version": 20,
        "characters": [{"name": "Default", "character": "generic"}],
        "active_character_index": 0,
    }), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TARS_RUNTIME_PROFILE", "1")
    monkeypatch.setenv("TARS_CANONICAL_PROMPT", str(prompt))
    monkeypatch.setattr(config_module, "get_default_input_device_name", lambda: "")
    monkeypatch.setattr(config_module, "get_default_output_device_name", lambda: "")

    config = load_config()

    assert [character["name"] for character in config["characters"]] == ["TARS"]
    assert config["characters"][0]["character"] == prompt.read_text(encoding="utf-8")


def _load_tars(monkeypatch, tmp_path):
    prompt = REPO_ROOT / "vendor" / "tars-plugins" / "prompt" / "prompt.txt"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TARS_RUNTIME_PROFILE", "1")
    monkeypatch.setenv("TARS_CANONICAL_PROMPT", str(prompt))
    monkeypatch.setattr(config_module, "get_default_input_device_name", lambda: "")
    monkeypatch.setattr(config_module, "get_default_output_device_name", lambda: "")
    return load_config(), prompt


def test_saved_prompt_survives_restart_and_reset_uses_canonical(monkeypatch, tmp_path):
    config, canonical_path = _load_tars(monkeypatch, tmp_path)
    set_tars_prompt(config, "Custom commander prompt")

    reloaded = load_config()
    assert reloaded["characters"][0]["character"] == "Custom commander prompt"
    assert reloaded["tars_profile_version"] == 1

    reset_tars_prompt(reloaded, str(canonical_path))
    reset_reloaded = load_config()
    assert reset_reloaded["characters"][0]["character"] == canonical_path.read_text(encoding="utf-8")


def test_provider_setting_patches_survive_switch_and_restart(monkeypatch, tmp_path):
    config, _ = _load_tars(monkeypatch, tmp_path)
    guid = "b7ddc677-0cfc-4081-af61-b2ebc2af5fe3"
    from lib.Config import update_config

    config = update_config(config, {"plugin_settings": {guid: {"onnx_threads": 1}}})
    config = update_config(config, {"plugin_settings": {"parakeet-guid": {"language": "en"}}})
    config = update_config(config, {"tts_provider": "none"})
    config = update_config(config, {"tts_provider": f"plugin:{guid}:pocket-tts"})
    reloaded = load_config()

    assert reloaded["plugin_settings"][guid]["onnx_threads"] == 1
    assert reloaded["plugin_settings"]["parakeet-guid"]["language"] == "en"
    assert config["plugin_settings"] == reloaded["plugin_settings"]


def test_provider_partial_edit_keeps_other_fields_and_inactive_provider(monkeypatch, tmp_path):
    config, _ = _load_tars(monkeypatch, tmp_path)
    pocket = "b7ddc677-0cfc-4081-af61-b2ebc2af5fe3"
    parakeet = "parakeet-guid"
    config = config_module.update_config(config, {"plugin_settings": {
        pocket: {"onnx_threads": 1, "voice": "saved-voice"},
        parakeet: {"language": "en", "beam_size": 5},
    }})
    config = config_module.update_config(config, {"plugin_settings": {
        pocket: {"onnx_threads": 2},
    }})
    config = config_module.update_config(config, {"tts_provider": "none"})
    config = config_module.update_config(config, {"plugin_settings": {
        parakeet: {"language": "de"},
    }})
    config = config_module.update_config(config, {"api_key": "edited-api-key"})
    reloaded = load_config()
    assert reloaded["plugin_settings"][pocket] == {
        "onnx_threads": 2, "voice": "saved-voice",
    }
    assert reloaded["plugin_settings"][parakeet] == {
        "language": "de", "beam_size": 5,
    }
    assert reloaded["tts_provider"] == "none"
    assert reloaded["api_key"] == "edited-api-key"


def test_legacy_tars_defaults_migrate_once_without_wiping_unrelated_settings(monkeypatch, tmp_path):
    canonical = REPO_ROOT / "vendor" / "tars-plugins" / "prompt" / "prompt.txt"
    (tmp_path / "config.json").write_text(json.dumps({
        "config_version": 20,
        "characters": [{"name": "TARS", "character": "Keep my prompt"}],
        "active_character_index": 0,
        "api_key": "preserve-main-key",
        "llm_api_key": "preserve-override-key",
        "llm_provider": "openai",
        "llm_model_name": "gpt-5.4-nano",
        "llm_reasoning_effort": "none",
        "llm_temperature": 1.0,
        "agent_llm_provider": "openai",
        "agent_llm_model_name": "gpt-5.4-mini",
        "agent_llm_reasoning_effort": "low",
        "agent_llm_temperature": 1.0,
        "agent_llm_max_tries": 7,
        "vision_provider": "openai",
        "vision_model_name": "gpt-5.4-nano",
        "input_device_name": "Commander microphone",
        "output_device_name": "Commander headset",
        "plugin_settings": {"plugin-guid": {"enabled": True}},
    }), encoding="utf-8")
    config, _ = _load_tars(monkeypatch, tmp_path)

    assert config["llm_model_name"] == config["agent_llm_model_name"] == "gpt-6-luna"
    assert config["vision_model_name"] == "gpt-6-luna"
    assert config["llm_temperature"] == config["agent_llm_temperature"] == 1.0
    assert config["agent_llm_reasoning_effort"] == "low"
    assert config["characters"][0]["character"] == "Keep my prompt"
    assert config["api_key"] == "preserve-main-key"
    assert config["llm_api_key"] == "preserve-override-key"
    assert config["input_device_name"] == "Commander microphone"
    assert config["output_device_name"] == "Commander headset"
    assert config["plugin_settings"] == {"plugin-guid": {"enabled": True}}

    persisted = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert persisted["tars_profile_version"] == 1
    assert persisted["characters"][0]["character"] != canonical.read_text(encoding="utf-8")


def test_custom_model_and_tuning_are_not_reset_by_tars_migration(monkeypatch, tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({
        "config_version": 20,
        "characters": [{"name": "TARS", "character": "Custom prompt"}],
        "active_character_index": 0,
        "llm_provider": "openrouter",
        "llm_model_name": "vendor/custom-model",
        "llm_reasoning_effort": "high",
        "llm_temperature": 0.42,
        "agent_llm_provider": "openrouter",
        "agent_llm_model_name": "vendor/custom-agent",
        "agent_llm_reasoning_effort": "medium",
        "agent_llm_temperature": 0.55,
        "vision_provider": "none",
        "vision_model_name": "custom-vision",
    }), encoding="utf-8")
    config, _ = _load_tars(monkeypatch, tmp_path)

    assert (config["llm_provider"], config["llm_model_name"]) == ("openrouter", "vendor/custom-model")
    assert (config["agent_llm_provider"], config["agent_llm_model_name"]) == ("openrouter", "vendor/custom-agent")
    assert config["vision_provider"] == "none"
    assert config["vision_model_name"] == "custom-vision"
    assert config["llm_reasoning_effort"] == "high"
    assert config["agent_llm_reasoning_effort"] == "medium"
    assert config["llm_temperature"] == 0.42
    assert config["agent_llm_temperature"] == 0.55


def test_migration_is_one_time_even_if_user_then_selects_an_old_model(monkeypatch, tmp_path):
    config, _ = _load_tars(monkeypatch, tmp_path)
    config["llm_model_name"] = "gpt-4.1-mini"
    config["agent_llm_max_tries"] = 11
    config_module.save_config(config)
    reloaded = load_config()
    assert reloaded["llm_model_name"] == "gpt-4.1-mini"
    assert reloaded["agent_llm_max_tries"] == 11


@pytest.mark.parametrize("import_version", [16, 19, 20])
def test_full_config_update_preserves_local_api_audio_and_plugin_settings(monkeypatch, tmp_path, import_version):
    config, _ = _load_tars(monkeypatch, tmp_path)
    config.update({
        "api_key": "example-main", "llm_api_key": "example-override",
        "agent_llm_max_tries": 9, "llm_model_name": "custom-openai-model",
        "llm_temperature": 0.71, "llm_reasoning_effort": "high",
        "input_device_name": "Test microphone", "output_device_name": "Test speaker",
        "plugin_settings": {"example-plugin": {"enabled": True, "voice": "test"}},
    })
    config["characters"][0]["character"] = "Saved user prompt"
    config["characters"][0]["tts_voice"] = "Saved voice"
    expected = copy.deepcopy(config)
    imported = copy.deepcopy(config)
    imported["config_version"] = import_version
    updated = config_module.update_config(config, imported)
    assert updated == expected
    assert load_config() == expected


def test_provider_switch_defaults_do_not_override_explicit_imported_values(monkeypatch, tmp_path):
    config, _ = _load_tars(monkeypatch, tmp_path)
    config["llm_provider"] = "openrouter"
    update = {"llm_provider": "openai", "llm_model_name": "chosen-model",
              "llm_api_key": "example-key", "llm_reasoning_effort": "high", "llm_temperature": 0.8}
    changed = config_module.update_config(config, update)
    assert all(changed[key] == value for key, value in update.items())


def test_reset_reactions_uses_exact_tars_factory_map(monkeypatch, tmp_path):
    config, _ = _load_tars(monkeypatch, tmp_path)
    config["characters"][0]["event_reactions"] = {"FSDJump": "off"}
    reset = config_module.reset_game_events(config)
    assert reset["characters"][0]["event_reactions"] == get_tars_event_reactions()


def test_failed_prompt_save_keeps_last_saved_config_and_reports_failure(monkeypatch, tmp_path):
    config, _ = _load_tars(monkeypatch, tmp_path)
    before = (tmp_path / "config.json").read_bytes()
    emitted = []
    monkeypatch.setattr(config_module, "emit_message", lambda kind, **payload: emitted.append((kind, payload)))
    def denied(*args):
        raise OSError("test write failure")
    monkeypatch.setattr(config_module.os, "replace", denied)
    result = config_module.handle_tars_prompt_command(config, {"type": "set_tars_prompt", "prompt": "New", "request_id": "test"})
    assert result is config
    assert (tmp_path / "config.json").read_bytes() == before
    assert emitted == [("tars_prompt_result", {"request_id": "test", "success": False, "error": "Unable to save TARS prompt: OSError"})]
    assert not list(tmp_path.glob(".config-*.tmp"))


def test_empty_prompt_cannot_destroy_saved_value(monkeypatch, tmp_path):
    config, _ = _load_tars(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="empty"):
        set_tars_prompt(config, "  ")
    assert load_config()["characters"][0]["character"] == config["characters"][0]["character"]


def test_migration_closes_read_handle_before_atomic_windows_replace(monkeypatch, tmp_path):
    config, _ = _load_tars(monkeypatch, tmp_path)
    config["tars_profile_version"] = 0
    config_module.save_config(config)
    streams = []
    original_load = config_module.json.load
    original_replace = config_module.os.replace
    def observe_load(stream, *args, **kwargs):
        streams.append(stream)
        return original_load(stream, *args, **kwargs)
    def windows_replace(source, destination):
        assert streams and all(stream.closed for stream in streams)
        return original_replace(source, destination)
    monkeypatch.setattr(config_module.json, "load", observe_load)
    monkeypatch.setattr(config_module.os, "replace", windows_replace)
    assert load_config()["tars_profile_version"] == 1
    assert json.loads((tmp_path / "config.json").read_text())["tars_profile_version"] == 1
