import hashlib
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import lib.Config as config_module
from lib.Config import get_tars_event_reactions, load_config


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
