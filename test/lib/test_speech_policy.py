"""Regression coverage for host-owned exploration speech policy.

Tests use only synthetic events, no live Commander data or external services.
"""
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.Event import GameEvent, PluginEvent
from lib.SpeechPolicy import LIVE_EXPLORATION_SPEECH_POLICY, routine_first_discovery_tally
from lib.PromptGenerator import PromptGenerator
from test_speech_trace import assistant, user
from test_speech_arbiter import arbiter, clock, finding, replay


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


@pytest.mark.parametrize('detail', ['3 terraformable bodies', 'an exceptional orbital period'])
def test_counter_notice_with_scientific_detail_is_not_suppressed(detail):
    event = _fact('New personal best: 321 first-discovered systems; ' + detail)
    assert not routine_first_discovery_tally(event)


@pytest.mark.parametrize('mode,expected', [('off', 0), ('observe', 0), ('enforce', 0)])
def test_tally_suppression_reaches_real_host_without_changing_history(mode, expected, arbiter):
    event = _fact('New personal best: 321 first-discovered systems')
    event.plugin_event_content['_guard'] = {'triggered_at': 1000.0}
    obj = replay(mode, arbiter, [[event]])
    assert obj.llmModel.calls == expected
    assert event.responded_at is None
    if not expected:
        obj.prompt_generator.generate_prompt.assert_not_called()
        obj.event_manager.short_term_memory.replied_before.assert_not_called()


@pytest.mark.parametrize('with_question', [False, True])
def test_tally_does_not_hide_science_or_direct_questions(arbiter, with_question):
    tally = _fact('New personal best: 321 first-discovered systems')
    tally.plugin_event_content['_guard'] = {'triggered_at': 1000.0}
    other = user() if with_question else finding()
    obj = replay('enforce', arbiter, [[tally, other]])
    assert obj.llmModel.calls == 1
    args = obj.prompt_generator.generate_prompt.call_args.kwargs
    assert args['pending_events'] == ([tally, other] if with_question else [other])
    assert tally in args['events'] and other in args['events']
    assert tally.responded_at is None


def test_policy_preserves_possible_codex_and_missing_observatory_information():
    assert 'possible Codex' in LIVE_EXPLORATION_SPEECH_POLICY
    assert 'withheld' in LIVE_EXPLORATION_SPEECH_POLICY
