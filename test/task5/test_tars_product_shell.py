import hashlib
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PINNED_PLUGINS_SHA = "67b1a1cab5a67d675372477dbcde061697e80bf5"
PROMPT_SHA256 = "802f042ac643da3583f0e0595caefb6d5a072746a8c0c0d17f64ec9dc29af4d7"


def test_canonical_prompt_matches_reference_provenance():
    prompt = REPO_ROOT / "vendor" / "tars-plugins" / "prompt" / "prompt.txt"
    assert hashlib.sha256(prompt.read_bytes()).hexdigest() == PROMPT_SHA256

    source = REPO_ROOT.parent / "TARS-Plugins"
    if not (source / ".git").exists():
        pytest.skip("requires the separate pinned TARS-Plugins checkout")
    pinned_prompt = subprocess.run(
        ["git", "-C", str(source), "show", f"{PINNED_PLUGINS_SHA}:prompt/prompt.txt"],
        check=True,
        capture_output=True,
    ).stdout
    assert pinned_prompt == prompt.read_bytes()


def test_primary_shell_is_tars_specific_and_has_no_character_creation_tab():
    overview = (
        REPO_ROOT / "ui" / "src" / "app" / "components" / "general-settings"
        / "general-settings.component.html"
    ).read_text(encoding="utf-8")
    menu = (
        REPO_ROOT / "ui" / "src" / "app" / "components" / "settings-menu"
        / "settings-menu.component.html"
    ).read_text(encoding="utf-8")

    assert "TARS SYSTEMS" in overview
    for status in ("AI", "Speech", "Voice", "Memory", "Elite", "Actions", "PROFILE LOADED"):
        assert f">{status}<" in overview
    assert "TARS setup" in menu
    for category in ("GENERAL", "AI &amp; VOICE", "PERSONALITY", "PLUGINS", "DIAGNOSTICS"):
        assert f'label="{category}"' in menu
    assert "Welcome to COVAS:NEXT" not in menu
    assert ">Characters<" not in menu
    assert "app-character-settings" not in menu


def test_tars_shell_does_not_start_upstream_covas_telemetry():
    main_view = (
        REPO_ROOT / "ui" / "src" / "app" / "main-view"
        / "main-view.component.ts"
    ).read_text(encoding="utf-8")
    welcome = (
        REPO_ROOT / "ui" / "src" / "app" / "components" / "settings-menu"
        / "settings-menu.component.html"
    ).read_text(encoding="utf-8")

    assert "MetricsService" not in main_view
    assert "local-use notice" in welcome
    assert "MetricsService" not in welcome
