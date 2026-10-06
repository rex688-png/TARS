from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_main_view_delegates_nonvisual_lifecycle_to_coordinator():
    main_view = source("ui/src/app/main-view/main-view.component.ts")
    coordinator = source(
        "ui/src/app/services/tars-application-coordinator.service.ts"
    )

    assert "TarsApplicationCoordinator" in main_view
    assert "applicationCoordinator.initialize()" in main_view
    assert "applicationCoordinator.startAssistant()" in main_view
    assert "applicationCoordinator.returnToConfiguration()" in main_view
    for responsibility in (
        "runExe()",
        "send_start_signal()",
        "restart_process()",
        "createOverlay({",
        "destroyOverlay()",
        "cn_autostart",
    ):
        assert responsibility not in main_view
        assert responsibility in coordinator


def test_coordinator_preserves_start_and_restart_order():
    coordinator = source(
        "ui/src/app/services/tars-application-coordinator.service.ts"
    )

    assert coordinator.index("await this.createOverlay") < coordinator.index(
        "this.loggingService.clearLogs()"
    )
    assert coordinator.index("this.loggingService.clearLogs()") < coordinator.index(
        "this.chatService.clearChat()"
    )
    assert coordinator.index("this.chatService.clearChat()") < coordinator.index(
        "await this.tauriService.send_start_signal()"
    )
    assert coordinator.index("await this.destroyOverlay()") < coordinator.index(
        "await this.tauriService.restart_process()"
    )


def test_new_runtime_contract_is_secret_free_and_external_source_neutral():
    models = source("ui/src/app/services/tars-runtime-facade.models.ts")
    facade = source("ui/src/app/services/tars-runtime-facade.service.ts")

    summary = models.split("export interface TarsRuntimeConfigurationSummary", 1)[1]
    summary = summary.split("}\n", 1)[0]
    assert "api_key" not in summary.lower()
    assert "credential" not in summary.lower()
    assert "TarsExternalIntegrationState" in models
    assert "externalIntegrations$" in facade
    assert "No external integration is claimed" in facade


def test_shutdown_and_provider_install_guard_remain_connected():
    service = source("ui/src/app/services/tauri.service.ts")
    preload = source("electron/preload.js")
    electron = source("electron/index.js")

    assert "activeProviderInstallations" in service
    assert "Closing now will cancel it" in service
    assert "await window.electronAPI?.confirmWindowClose()" in service
    assert "onWindowClose" in preload
    assert "window-close-ready" in electron
    assert "this.stopProcess(mainWindow)" in electron
