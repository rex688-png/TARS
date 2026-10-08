import sys
from pathlib import Path

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
