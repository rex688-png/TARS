import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.SpeechText import normalize_spoken_quantities


def test_large_credit_quantity_and_decimal_distance():
    spoken = normalize_spoken_quantities("4,123,456,789 credits, 12.5 ly, 3 jumps, 75%")
    assert "four billion" in spoken
    assert "one hundred and twenty-three million" in spoken
    assert "twelve point five light-years" in spoken
    assert "three jumps" in spoken
    assert "seventy-five percent" in spoken


def test_system_names_and_model_identifiers_remain_unchanged():
    text = "Col 285 Sector AB 12-3, ship eXPY, GPT-6 Luna; 2,400 tonnes"
    spoken = normalize_spoken_quantities(text)
    assert "Col 285 Sector AB 12-3" in spoken
    assert "GPT-6 Luna" in spoken
    assert "two thousand" in spoken


@pytest.mark.parametrize("source, expected", [
    ("100 credits", "one hundred credits"),
    ("1,000 tonnes", "one thousand tonnes"),
    ("2,000,000 credits", "two million credits"),
    ("4,000,000,000 credits", "four billion credits"),
    ("13 107 kilometers", "thirteen thousand, one hundred and seven kilometers"),
    ("12.5 ly", "twelve point five light-years"),
    ("75%", "seventy-five percent"),
])
def test_spoken_quantity_ranges(source, expected):
    assert normalize_spoken_quantities(source) == expected


@pytest.mark.parametrize("source, expected", [
    ("0 Cr", "zero credits"),
    ("1 Cr", "one credit"),
    ("1,000 Cr", "one thousand credits"),
    ("1,000,000 Cr", "one million credits"),
    ("4,123,456,789 Cr", "four billion, one hundred and twenty-three million, four hundred and fifty-six thousand, seven hundred and eighty-nine credits"),
    ("0.3 light-years", "zero point three light-years"),
    ("125.3 ly", "one hundred and twenty-five point three light-years"),
    ("1,250 ly", "one thousand, two hundred and fifty light-years"),
    ("1%", "one percent"),
    ("80%", "eighty percent"),
    ("99.5%", "ninety-nine point five percent"),
    ("1 tonne", "one tonne"),
    ("2 tonnes", "two tonnes"),
    ("1 jump", "one jump"),
    ("25 jumps", "twenty-five jumps"),
])
def test_elite_spoken_quantity_fixtures(source, expected):
    assert normalize_spoken_quantities(source) == expected


@pytest.mark.parametrize("identifier", [
    "Col 285 Sector AB 12-3", "HIP 22460 A 1", "S171 6", "eXPY 2",
    "FIX-01", "GPT-6 Luna", "Parakeet STT 0.0.10",
    "HIP 13 107", "Col 285 Sector 13 107",
])
def test_spoken_quantities_do_not_expand_identifiers(identifier):
    assert normalize_spoken_quantities(identifier) == identifier
