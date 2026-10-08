"""Public stabilization asset and product-boundary regressions."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AVATAR = "Obraz ChatGPT 28 wrz 2026, 21_39_52.png"


def test_canonical_avatar_bytes_and_original_filename_are_preserved():
    asset = ROOT / "ui/src/assets" / AVATAR
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == "4e0103a45a548ef7e700b1c015b42039250d4aad470c4d5d0826b59be5e29143"
    assert AVATAR in (ROOT / "ui/src/app/services/character.service.ts").read_text()
    assert not list((ROOT / "ui/src/assets").glob("cn_avatar_default*"))


def test_canonical_avatar_displays_one_state_in_settings_and_overlay():
    general = ROOT / "ui/src/app/components/general-settings"
    overlay = ROOT / "ui/src/app/overlay-view"
    for directory, component in ((general, "general-settings"), (overlay, "overlay-view")):
        assert '[class.canonical-tars-avatar]="isCanonicalTarsAvatar"' in (directory / f"{component}.component.html").read_text()
    settings_css = (general / "general-settings.component.css").read_text()
    overlay_css = (overlay / "overlay-view.component.css").read_text()
    # The original PNG is a 2x2 state sheet. The UI selects one state with CSS;
    # it must not show all four portraits at once or create derived image files.
    assert "width: 200%" in settings_css
    assert "transform: translate(-50%, -50%)" in settings_css
    assert "background-size: 200%" in overlay_css
    assert "background-position: 100% 100%" in overlay_css
    assert ".minimal-avatar-image.canonical-tars-avatar" not in settings_css
    assert ".overlay-pngtuber.canonical-tars-avatar" not in overlay_css


def test_prompt_editor_has_save_reload_reset_and_backend_acknowledgement():
    template = (ROOT / "ui/src/app/components/tars-prompt-settings/tars-prompt-settings.component.ts").read_text()
    assert '(click)="save()"' in template
    assert '(click)="editor.reload()"' in template
    assert '(click)="reset()"' in template
    assert "configService.setTarsPrompt" in template
    assert "configService.resetTarsPrompt" in template
    service = (ROOT / "ui/src/app/services/config.service.ts").read_text()
    assert "tars_prompt_result" in service
    assert "request_id" in service
