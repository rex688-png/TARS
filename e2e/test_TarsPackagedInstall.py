"""Clean-profile smoke test for a packaged Windows TARS directory."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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
            "PYTHONUNBUFFERED": "1",
        }
        process = subprocess.Popen(
            [str(backend)], cwd=profile, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            deadline = time.monotonic() + 20
            config_path = profile / "config.json"
            while time.monotonic() < deadline and not config_path.is_file():
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    raise RuntimeError(f"backend exited before profile initialization:\n{output}")
                time.sleep(0.1)
            if not config_path.is_file():
                raise RuntimeError("backend did not initialize a clean TARS profile")
            config = json.loads(config_path.read_text(encoding="utf-8"))
            canonical = (bundled / "prompt" / "prompt.txt").read_text(encoding="utf-8")
            assert config["characters"][0]["name"] == "TARS"
            assert config["characters"][0]["character"] == canonical
            assert marker.read_text(encoding="utf-8") == "do not modify"
            time.sleep(5)
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise RuntimeError(f"backend failed during plugin initialization:\n{output}")
        finally:
            process.terminate()
            process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
