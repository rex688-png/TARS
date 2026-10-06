from __future__ import annotations

import threading

from lib.Logger import log, show_chat_message
from lib.PluginBase import PluginBase, PluginManifest
from lib.PluginSettingDefinitions import ButtonSetting, ParagraphSetting, PluginSettings, SettingsGrid
from lib.TarsProviderRegistry import (
    TARS_PROVIDER_SPECS,
    install_provider,
    installed_provider_path,
    provider_root,
)
from lib.UI import emit_message


TARS_PROVIDER_INSTALLER_GUID = "71be4c2e-4a49-45f7-b968-d70588bdae74"


class TarsProviderInstallerPlugin(PluginBase):
    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)
        self._installing: set[str] = set()
        self._lock = threading.Lock()
        self.settings_config = self._settings_config()

    def _settings_config(self) -> PluginSettings:
        grids = []
        for spec in TARS_PROVIDER_SPECS:
            installed = installed_provider_path(spec) is not None
            download_mib = spec.size / (1024 * 1024)
            disk_mib = spec.extracted_size / (1024 * 1024)
            status = "Installed; restart TARS after an update." if installed else (
                f"Not installed. Downloads {download_mib:.0f} MiB and uses approximately "
                f"{disk_mib:.0f} MiB below {provider_root()}."
            )
            fields = [ParagraphSetting(
                key=f"status:{spec.key}", label=spec.label, type="paragraph",
                readonly=True, placeholder=None, content=status,
            )]
            if not installed:
                fields.append(ButtonSetting(
                    key=f"install:{spec.key}", label=f"Install {spec.label}",
                    type="button", readonly=False, placeholder=None,
                ))
            grids.append(SettingsGrid(
                key=spec.key, label=spec.label, fields=fields,
            ))
        return PluginSettings(
            key="TARS Provider Setup", label="TARS Provider Setup",
            icon="download", grids=grids,
        )

    def on_settings_button(self, key: str):
        if not key.startswith("install:"):
            return
        provider_key = key.removeprefix("install:")
        spec = next((item for item in TARS_PROVIDER_SPECS if item.key == provider_key), None)
        if spec is None:
            show_chat_message("error", f"Unknown TARS provider: {provider_key}")
            return
        with self._lock:
            if provider_key in self._installing:
                show_chat_message("info", f"{spec.label} installation is already running.")
                return
            self._installing.add(provider_key)
        self._publish_status(spec, "downloading", 0, spec.size)
        threading.Thread(
            target=self._install, args=(spec,),
            name=f"install-{provider_key}", daemon=True,
        ).start()

    def _install(self, spec):
        last_percent = -1

        def state(value: str) -> None:
            self._publish_status(spec, value)

        def progress(received: int, total: int) -> None:
            nonlocal last_percent
            percent = min(100, int(received * 100 / max(1, total)))
            self._publish_status(spec, "downloading", received, total)
            if percent >= last_percent + 10 or percent == 100:
                last_percent = percent
                log("info", f"Downloading {spec.label}: {percent}%")

        try:
            show_chat_message(
                "info", f"Installing {spec.label}. Keep TARS open during the download."
            )
            install_provider(spec, progress=progress, state=state)
            self.settings_config = self._settings_config()
            show_chat_message(
                "info", f"{spec.label} installed successfully. Restart TARS to enable it."
            )
        except Exception as exc:
            log("error", f"Failed to install {spec.label}: {exc}")
            self._publish_status(spec, "failed", error=str(exc))
            show_chat_message(
                "error", f"{spec.label} installation failed: {exc}. Check the TARS log and retry."
            )
        finally:
            with self._lock:
                self._installing.discard(spec.key)

    @staticmethod
    def _publish_status(
        spec,
        state: str,
        received: int = 0,
        total: int | None = None,
        error: str | None = None,
    ) -> None:
        total_bytes = total if total is not None else spec.size
        percent = min(100, int(received * 100 / max(1, total_bytes)))
        emit_message(
            "provider_install_status",
            provider_key=spec.key,
            label=spec.label,
            state=state,
            downloaded_bytes=received,
            total_bytes=total_bytes,
            percent=100 if state == "installed" else percent,
            restart_required=(state == "installed"),
            error=error,
        )
