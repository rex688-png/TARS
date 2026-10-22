"""Regression coverage for host-owned exploration speech policy.

Tests use only synthetic events, no live Commander data or external services.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.Event import GameEvent, PluginEvent
from lib.SpeechPolicy import LIVE_EXPLORATION_SPEECH_POLICY, routine_first_discovery_tally
from lib.PromptGenerator import PromptGenerator
from test_speech_trace import assistant


def _fact(text, source="Stat Scanner"):
    return PluginEvent(
        plugin_event_name="TARSObservatoryFact",
        plugin_event_content={
            "source_plugin": source,
            "fact_type": "notification:StatScanner",
            "message": text,
            "realtime": True,
            "monitor_mode": "realtime",
            "batch": False,
        },
        responded_at=None,
    )


def test_count_only_first_discovery_notifications_are_routine():
    assert routine_first_discovery_tally(_fact("New personal best: 321 first-discovered systems"))
    assert routine_first_discovery_tally(_fact("Record: 320 undiscovered systems"))


def test_scientific_records_and_unverified_payloads_fail_open():
    assert not routine_first_discovery_tally(_fact(
        "A new personal record: 322 first-discovered systems and an Earth-like world"))
    assert not routine_first_discovery_tally(_fact(
        "First discovered system contains unusual biological signals"))
    assert not routine_first_discovery_tally(_fact(
        "New personal best: 321 first-discovered systems", source="BioInsights"))
    assert not routine_first_discovery_tally(_fact("Personal best: 321"))
    assert not routine_first_discovery_tally(GameEvent(content={"event": "FSDJump"}, historic=False))


def test_high_value_observatory_facts_get_room_to_breathe():
    assert "terraformable" in LIVE_EXPLORATION_SPEECH_POLICY
    assert "One to three" in LIVE_EXPLORATION_SPEECH_POLICY
    assert "Do not invent life" in LIVE_EXPLORATION_SPEECH_POLICY
    assert "Do not turn increased personality into increased frequency" in LIVE_EXPLORATION_SPEECH_POLICY


def test_organic_sale_requires_enabled_event_and_uses_actual_bonuses():
    organic_sale = GameEvent(
        content={
            "event": "SellOrganicData",
            "BioData": [
                {"Species_Localised": "Stratum Tectonicas", "Value": 19000000, "Bonus": 76000000},
                {"Species_Localised": "Bacterium", "Value": 200000, "Bonus": 0},
            ],
        },
        historic=False,
    )
    obj = assistant([organic_sale], ["Sale acknowledged."])
    assert not obj.should_reply({})
    obj.enabled_game_events = ["SellOrganicData"]
    assert obj.should_reply({})

    generator = PromptGenerator.__new__(PromptGenerator)
    generator.commander_name = "TEST COMMANDER"
    spoken = generator.get_event_template(organic_sale)
    assert "2 species" in spoken
    assert "95,200,000" in spoken
    assert "19,200,000" in spoken
    assert "76,000,000" in spoken
    assert "SellOrganicData" in LIVE_EXPLORATION_SPEECH_POLICY


def test_prompt_generator_has_no_hidden_one_sentence_restriction():
    source = (Path(__file__).resolve().parents[2] / "src" / "lib" / "PromptGenerator.py").read_text(
        encoding="utf-8"
    )
    assert "LIVE_EXPLORATION_SPEECH_POLICY" in source
    assert "You respond only when addressed and in a single sentence" not in source
