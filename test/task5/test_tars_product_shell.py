import hashlib
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PINNED_PLUGINS_SHA = "685e16a19d5a5cd83f16297b90ee4c58ba8e11b5"
PROMPT_SHA256 = "802f042ac643da3583f0e0595caefb6d5a072746a8c0c0d17f64ec9dc29af4d7"


def test_canonical_prompt_matches_reference_provenance():
    prompt = REPO_ROOT / "vendor" / "tars-plugins" / "prompt" / "prompt.txt"
    assert hashlib.sha256(prompt.read_bytes()).hexdigest() == PROMPT_SHA256

    source = REPO_ROOT.parent / "TARS-Plugins"
    if not (source / ".git").exists():
        pytest.skip("requires the separate pinned TARS-Plugins checkout")
    sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert sha == PINNED_PLUGINS_SHA
    assert (source / "prompt" / "prompt.txt").read_bytes() == prompt.read_bytes()


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
    for status in ("AI", "Speech", "Voice", "Memory", "Elite", "Actions", "ONLINE"):
        assert f">{status}<" in overview
    assert "Welcome to TARS" in menu
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
    assert "does not send diagnostics to the upstream COVAS service" in welcome
