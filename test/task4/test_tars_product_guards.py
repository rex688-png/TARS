from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_tars_ui_never_contacts_or_advertises_the_covas_update_channel():
    ui_source = REPO_ROOT / "ui" / "src" / "app"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ui_source.rglob("*.ts")
    )

    assert "RatherRude/Elite-Dangerous-AI-Integration/releases" not in source
    assert "checkForUpdates()" not in source


def test_provider_install_ui_exposes_progress_and_shutdown_guard():
    plugin_settings = (
        REPO_ROOT / "ui" / "src" / "app" / "components" / "plugin-settings"
        / "plugin-settings.component.html"
    ).read_text(encoding="utf-8")
    service = (
        REPO_ROOT / "ui" / "src" / "app" / "services" / "tauri.service.ts"
    ).read_text(encoding="utf-8")

    assert "mat-progress-bar" in plugin_settings
    assert "activeProviderInstallations" in service
    assert "Closing now will cancel it" in service


def test_action_preflight_identifies_missing_keybinds_not_missing_actions():
    component = (
        REPO_ROOT / "ui" / "src" / "app" / "components" / "general-settings"
        / "general-settings.component.ts"
    ).read_text(encoding="utf-8")

    assert "missing keybinds" in component
    assert "parts.push(`${counts.missing} missing`)" not in component
