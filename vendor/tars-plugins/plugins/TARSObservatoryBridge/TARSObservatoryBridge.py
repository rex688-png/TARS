from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from lib.PluginBase import PluginBase, PluginManifest
from lib.PluginHelper import PluginHelper, PluginEvent
from lib.Logger import log


TARS_OBSERVATORY_BRIDGE_GUID = "5a80ff76-201c-49c7-a632-6f00d671a99a"
TARS_OBSERVATORY_BRIDGE_VERSION = "0.1.0"
TARS_OBSERVATORY_BRIDGE_MANIFEST = {
    "guid": TARS_OBSERVATORY_BRIDGE_GUID,
    "name": "TARS Observatory Bridge",
    "version": TARS_OBSERVATORY_BRIDGE_VERSION,
    "author": "TARS / COVAS:NEXT",
    "description": (
        "Relays live Elite Observatory facts to TARS with persistent cursor and "
        "historical-event protection."
    ),
    "entrypoint": "TARSObservatoryBridge.py",
    "repository": "",
}


class EmptyArgs(BaseModel):
    pass


class TARSObservatoryBridge(PluginBase):
    """Relay live Elite Observatory facts into TARS without replaying history."""

    settings_config = {
        "key": "TARSObservatoryBridge",
        "label": "TARS Observatory Bridge",
        "icon": "wrench",
        "grids": [{
            "key": "bridge",
            "label": "Observatory Bridge",
            "fields": [
                {
                    "key": "about_text",
                    "label": "Live Observatory relay",
                    "type": "paragraph",
                    "readonly": True,
                    "placeholder": None,
                    "content": (
                        "Reads live facts written by the Elite Observatory TARS Bridge and relays them "
                        "to TARS. Historical Read All records never trigger speech."
                    ),
                },
                {
                    "key": "enabled",
                    "label": "Enable Observatory integration",
                    "type": "toggle",
                    "readonly": False,
                    "placeholder": None,
                    "default_value": True,
                },
                {
                    "key": "events_path",
                    "label": "Override events.jsonl path (blank uses Local AppData)",
                    "type": "text",
                    "readonly": False,
                    "placeholder": r"C:\Users\name\AppData\Local\TARS\observatory\events.jsonl",
                    "default_value": "",
                },
            ],
        }],
    }

    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)
        self._manifest = plugin_manifest
        self._helper: PluginHelper | None = None
        self._state_path: Path | None = None
        self._events_path: Path | None = None
        self._offset = 0
        self._file_identity: dict[str, Any] = {}
        self._seen_ids: list[str] = []
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._status: dict[str, Any] = {
            "state": "stopped", "relayed": 0, "ignored_historical": 0,
            "ignored_non_notification": 0, "malformed": 0, "last_error": None,
            "last_event_id": None, "last_source": None, "last_fact_type": None,
        }

    def on_chat_start(self, helper: PluginHelper):
        self._helper = helper
        data_dir = Path(helper.get_plugin_data_path(self._manifest))
        data_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = data_dir / "observatory_cursor.json"
        self._events_path = self._configured_events_path()
        self._load_cursor()

        helper.register_event(
            name="TARSObservatoryFact",
            should_reply_check=lambda event: True,
            prompt_generator=self._prompt_observatory_fact,
        )
        helper.register_action(
            name="tars_observatory_diagnostics",
            description=(
                "Diagnose the local Elite Observatory to TARS connection, including file path, cursor, "
                "relayed count, ignored historical records and the latest error. Use when the commander "
                "asks whether Observatory, BioInsights, Evaluator, Stat Scanner or AstroAnalytica reached TARS."
            ),
            parameters=EmptyArgs,
            method=self._diagnostics,
            action_type="global",
        )

        self._running.set()
        self._status["state"] = "watching"
        self._thread = threading.Thread(target=self._watch, name="TARSObservatoryBridge", daemon=True)
        self._thread.start()
        log("info", f"TARS Observatory Bridge {TARS_OBSERVATORY_BRIDGE_VERSION} watching {self._events_path}")

    def on_chat_stop(self, helper: PluginHelper):
        self._running.clear()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        with self._lock:
            self._status["state"] = "stopped"
            self._save_cursor()
        self._helper = None

    @staticmethod
    def _prompt_observatory_fact(event: PluginEvent) -> str:
        fact = event.plugin_event_content if isinstance(event.plugin_event_content, dict) else {}
        return (
            "Live Elite Observatory notification for TARS. Treat the supplied fields as external "
            "observation data, make a short natural exploration callout, and do not invent missing "
            "values or claim a source plugin emitted something not present in the fact. Fact: "
            + json.dumps(fact, ensure_ascii=False, separators=(",", ":"))
        )

    def _configured_events_path(self) -> Path:
        configured = str(self.settings.get("events_path", "") or "").strip()
        if configured:
            return Path(os.path.expandvars(configured)).expanduser()
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "TARS" / "observatory" / "events.jsonl"
        return Path.home() / "AppData" / "Local" / "TARS" / "observatory" / "events.jsonl"

    @staticmethod
    def _identity(path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {"path": str(path.resolve()), "device": stat.st_dev, "inode": stat.st_ino}

    def _load_cursor(self):
        path = self._events_path
        if path is None:
            return
        saved: dict[str, Any] = {}
        if self._state_path is not None and self._state_path.exists():
            try:
                raw = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("schema") == 1:
                    saved = raw
                    saved_status = raw.get("status")
                    if isinstance(saved_status, dict):
                        for key in self._status:
                            if key in saved_status:
                                self._status[key] = saved_status[key]
            except Exception as exc:
                self._status["last_error"] = f"cursor load: {type(exc).__name__}: {exc}"

        if not path.exists():
            self._offset = 0
            self._file_identity = {"path": str(path), "missing": True}
            return

        identity = self._identity(path)
        same_file = all(saved.get("file", {}).get(k) == identity.get(k) for k in ("path", "device", "inode"))
        saved_offset = int(saved.get("offset") or 0)
        size = path.stat().st_size
        if same_file and 0 <= saved_offset <= size:
            self._offset = saved_offset
            self._seen_ids = [str(x) for x in saved.get("seen_event_ids", []) if x][-500:]
        else:
            # First installation or replaced log: begin at EOF. Old Observatory history
            # remains queryable in its files but must not become surprise live speech.
            self._offset = size
            self._seen_ids = []
        self._file_identity = identity
        self._save_cursor()

    def _save_cursor(self):
        if self._state_path is None:
            return
        payload = {
            "schema": 1,
            "events_path": str(self._events_path) if self._events_path else None,
            "file": self._file_identity,
            "offset": self._offset,
            "seen_event_ids": self._seen_ids[-500:],
            "status": self._status,
            "updated_at": time.time(),
        }
        try:
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._state_path)
        except Exception as exc:
            self._status["last_error"] = f"cursor save: {type(exc).__name__}: {exc}"
            log("warning", f"TARS Observatory Bridge could not save cursor: {exc}")

    def _watch(self):
        while self._running.is_set():
            try:
                if bool(self.settings.get("enabled", True)):
                    self._poll_once()
            except Exception as exc:
                with self._lock:
                    self._status["state"] = "degraded"
                    self._status["last_error"] = f"watch: {type(exc).__name__}: {exc}"
                    self._save_cursor()
                log("warning", f"TARS Observatory Bridge watch failed: {exc}")
            time.sleep(0.5)

    def _poll_once(self):
        path = self._events_path
        if path is None or not path.exists():
            return
        identity = self._identity(path)
        size = path.stat().st_size
        if self._file_identity.get("missing") is True:
            # The log did not exist when the relay started. Its first contents are
            # new for this session and must not be skipped.
            self._offset = 0
        elif self._file_identity and any(self._file_identity.get(k) != identity.get(k) for k in ("path", "device", "inode")):
            # A replaced/rotated log may contain copied history. Attach at EOF and
            # wait for genuinely new appends instead of replaying it as live speech.
            self._offset = size
            self._seen_ids = []
            self._file_identity = identity
            self._save_cursor()
            return
        elif size < self._offset:
            self._offset = 0
        self._file_identity = identity

        with path.open("rb") as stream:
            stream.seek(self._offset)
            while self._running.is_set():
                start = stream.tell()
                line = stream.readline()
                if not line or not line.endswith(b"\n"):
                    break
                end = stream.tell()
                if self._process_line(line):
                    self._offset = end
                    self._save_cursor()
                else:
                    # Dispatch failures are retryable. Parse/filter failures are marked
                    # consumed by _process_line so they cannot jam the tail forever.
                    stream.seek(start)
                    break

    def _process_line(self, raw_line: bytes) -> bool:
        try:
            fact = json.loads(raw_line.decode("utf-8-sig"))
        except Exception as exc:
            self._status["malformed"] += 1
            self._status["last_error"] = f"malformed JSONL: {type(exc).__name__}: {exc}"
            return True
        if not isinstance(fact, dict):
            self._status["malformed"] += 1
            return True

        event_id = str(fact.get("event_id") or fact.get("id") or "").strip()
        if event_id and event_id in self._seen_ids:
            return True
        if fact.get("batch") is True or fact.get("realtime") is not True or fact.get("monitor_mode") != "realtime":
            self._status["ignored_historical"] += 1
            return True
        if not str(fact.get("fact_type") or "").startswith("notification:"):
            self._status["ignored_non_notification"] += 1
            return True

        helper = self._helper
        if helper is None:
            return False
        try:
            helper.dispatch_event(PluginEvent(
                plugin_event_name="TARSObservatoryFact",
                plugin_event_content=fact,
            ))
        except Exception as exc:
            self._status["state"] = "degraded"
            self._status["last_error"] = f"dispatch: {type(exc).__name__}: {exc}"
            log("warning", f"TARS Observatory Bridge dispatch failed: {exc}")
            return False

        if event_id:
            self._seen_ids.append(event_id)
            self._seen_ids = self._seen_ids[-500:]
        self._status.update({
            "state": "watching", "relayed": int(self._status["relayed"]) + 1,
            "last_error": None, "last_event_id": event_id or None,
            "last_source": fact.get("source_plugin"), "last_fact_type": fact.get("fact_type"),
        })
        return True

    def _diagnostics(self, args=None, context=None) -> str:
        with self._lock:
            path = self._events_path
            return json.dumps({
                "ok": self._status.get("state") != "degraded",
                "plugin": "TARS Observatory Bridge",
                "version": TARS_OBSERVATORY_BRIDGE_VERSION,
                "enabled": bool(self.settings.get("enabled", True)),
                "events_path": str(path) if path else None,
                "events_file_exists": bool(path and path.exists()),
                "cursor_offset": self._offset,
                **self._status,
                "assistant_instruction": (
                    "Report whether the file exists, whether the relay is watching, the relayed count, "
                    "ignored historical count and latest error. Do not infer that a source plugin emitted "
                    "an event unless last_source or the relayed count proves it."
                ),
            }, ensure_ascii=False)
