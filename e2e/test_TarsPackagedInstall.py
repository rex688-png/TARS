"""Clean-profile smoke test for a packaged Windows TARS directory."""

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time


def main() -> int:
    package_root = Path(sys.argv[1]).resolve()
    resources = package_root / "resources"
    backend = resources / "Chat" / "Chat.exe"
    bundled = resources / "tars-plugins"
    if not backend.is_file() or not bundled.is_dir():
        raise RuntimeError("packaged backend or immutable TARS resources are missing")

    with tempfile.TemporaryDirectory(prefix="tars-clean-profile-") as temp:
        profile = Path(temp) / "TARS"
        profile.mkdir()
        old_covas = Path(temp) / "com.covas-next.ui"
        marker = old_covas / "untouched.txt"
        marker.parent.mkdir()
        marker.write_text("do not modify", encoding="utf-8")
        environment = {
            **os.environ,
            "TARS_RUNTIME_PROFILE": "1",
            "TARS_BUNDLED_RESOURCES": str(bundled),
            "TARS_PROVIDER_ROOT": str(profile / "providers"),
            "PYTHONUNBUFFERED": "1",
        }
        lines = queue.Queue()
        process = subprocess.Popen(
            [str(backend)], cwd=profile, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )
        def read_output():
            if process.stdout:
                for line in process.stdout:
                    lines.put(line)
        threading.Thread(target=read_output, daemon=True).start()
        try:
            deadline = time.monotonic() + 30
            config_path = profile / "config.json"
            settings_message = None
            providers_message = None
            captured = []
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        "backend exited before provider initialization:\n" + "".join(captured)
                    )
                try:
                    line = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                captured.append(line)
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if message.get("type") == "plugin_settings_configs":
                    settings_message = message
                elif message.get("type") == "plugin_model_providers":
                    providers_message = message
                if config_path.is_file() and settings_message and providers_message:
                    break
            if not config_path.is_file() or not settings_message or not providers_message:
                raise RuntimeError(
                    "backend did not initialize profile/plugins/providers:\n" + "".join(captured)
                )
            config = json.loads(config_path.read_text(encoding="utf-8"))
            canonical = (bundled / "prompt" / "prompt.txt").read_text(encoding="utf-8")
            assert config["active_character_index"] == 0
            assert [character["name"] for character in config["characters"]] == ["TARS"]
            character = config["characters"][0]
            assert character["character"] == canonical
            reaction_states = list(character["event_reactions"].values())
            assert {
                state: reaction_states.count(state)
                for state in ("on", "off", "hidden")
            } == {"on": 85, "off": 207, "hidden": 10}
            assert config["llm_provider"] == config["agent_llm_provider"] == "openai"
            assert config["llm_model_name"] == config["agent_llm_model_name"] == "gpt-6-luna"
            assert config["vision_provider"] == "openai"
            assert config["vision_model_name"] == "gpt-6-luna"
            assert config["stt_provider"].endswith(":parakeet-stt")
            assert config["tts_provider"].endswith(":pocket-tts")
            assert config["embedding_provider"].endswith(":gemma-embedding")
            assert config["api_key"] == config["llm_api_key"] == ""
            assert marker.read_text(encoding="utf-8") == "do not modify"
            installer = settings_message["plugin_settings_configs"][
                "71be4c2e-4a49-45f7-b968-d70588bdae74"
            ]
            assert [grid["key"] for grid in installer["grids"]] == [
                "parakeet-stt", "pocket-tts", "supertonic-tts", "gemma-embedding"
            ]
            provider_kinds = {item["kind"] for item in providers_message["providers"]}
            assert {"llm", "vlm", "stt", "tts", "embedding"} <= provider_kinds
            assert (profile / "providers").resolve().is_relative_to(profile.resolve())
        finally:
            process.terminate()
            process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
