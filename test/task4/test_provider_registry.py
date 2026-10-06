import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import zipfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lib.TarsProviderRegistry import (
    MARKER_NAME,
    TARS_PROVIDER_SPECS,
    TarsProviderSpec,
    install_provider,
    installed_provider_path,
)


def _archive(spec_values: dict[str, str], extra_name: str = "provider.py") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("manifest.json", json.dumps(spec_values))
        package.writestr(extra_name, "# provider entrypoint\n")
        package.writestr("model/model.bin", b"fixture")
    return output.getvalue()


def _fixture_spec(payload: bytes, **overrides) -> TarsProviderSpec:
    values = dict(
        key="fixture-stt", label="Fixture STT", kind="stt", provider_id="fixture-stt",
        guid="fixture-guid", version="1.2.3", folder="fixture-provider",
        entrypoint="provider.py", url="https://example.invalid/provider.zip",
        size=len(payload), extracted_size=7,
        sha256=hashlib.sha256(payload).hexdigest(), source_revision="source-sha",
    )
    values.update(overrides)
    return TarsProviderSpec(**values)


def test_registry_pins_official_windows_releases():
    assert [spec.key for spec in TARS_PROVIDER_SPECS] == [
        "parakeet-stt", "pocket-tts", "supertonic-tts", "gemma-embedding"
    ]
    assert {spec.kind for spec in TARS_PROVIDER_SPECS} == {"stt", "tts", "embedding"}
    assert [spec.provider_id for spec in TARS_PROVIDER_SPECS] == [
        "parakeet-stt", "pocket-tts", "supertonic-tts", "gemma-embedding"
    ]
    assert all(spec.url.startswith("https://github.com/COVAS-Labs/") for spec in TARS_PROVIDER_SPECS)
    assert all(len(spec.sha256) == 64 and spec.size > 0 for spec in TARS_PROVIDER_SPECS)


def test_install_is_verified_atomic_and_retry_safe(tmp_path):
    manifest = {"guid": "fixture-guid", "version": "1.2.3", "entrypoint": "provider.py"}
    payload = _archive(manifest)
    spec = _fixture_spec(payload)
    progress = []
    states = []
    stale = tmp_path / ".fixture-stt-interrupted"
    stale.mkdir()
    (stale / "partial").write_bytes(b"partial")

    installed = install_provider(
        spec, root=tmp_path, progress=lambda current, total: progress.append((current, total)),
        state=states.append,
        opener=lambda _url, timeout: io.BytesIO(payload),
    )

    assert installed_provider_path(spec, tmp_path) == installed
    assert (installed / "model" / "model.bin").read_bytes() == b"fixture"
    assert json.loads((installed / MARKER_NAME).read_text(encoding="utf-8"))["sha256"] == spec.sha256
    assert progress[-1] == (len(payload), len(payload))
    assert states == ["downloading", "verifying", "extracting", "installed"]
    assert install_provider(spec, root=tmp_path, opener=lambda *_args, **_kwargs: pytest.fail()) == installed
    assert not stale.exists()
    assert not list(tmp_path.glob(".fixture-stt-*"))


def test_install_rejects_checksum_mismatch_without_partial_state(tmp_path):
    payload = _archive({"guid": "fixture-guid", "version": "1.2.3", "entrypoint": "provider.py"})
    spec = _fixture_spec(payload, sha256="0" * 64)

    with pytest.raises(ValueError, match="checksum"):
        install_provider(spec, root=tmp_path, opener=lambda _url, timeout: io.BytesIO(payload))

    assert not (tmp_path / spec.folder).exists()
    assert not list(tmp_path.glob(".fixture-stt-*"))


def test_install_rejects_zip_traversal(tmp_path):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("../outside.txt", "unsafe")
        package.writestr("manifest.json", json.dumps({
            "guid": "fixture-guid", "version": "1.2.3", "entrypoint": "provider.py"
        }))
        package.writestr("provider.py", "# provider")
    payload = output.getvalue()
    spec = _fixture_spec(payload)

    with pytest.raises(ValueError, match="unsafe path"):
        install_provider(spec, root=tmp_path, opener=lambda _url, timeout: io.BytesIO(payload))

    assert not (tmp_path.parent / "outside.txt").exists()


def test_installed_hyphenated_provider_loads_and_registers_after_restart(tmp_path):
    entrypoint = "cn-plugin-restart-fixture.py"
    manifest = {
        "guid": "restart-fixture-guid",
        "name": "Restart Fixture",
        "author": "TEST",
        "version": "1.2.3",
        "repository": "",
        "entrypoint": entrypoint,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("support.py", 'LABEL = "Restart Fixture STT"\n')
        package.writestr(entrypoint, textwrap.dedent("""
            from .support import LABEL
            from lib.PluginBase import PluginBase

            class RestartFixturePlugin(PluginBase):
                def __init__(self, plugin_manifest):
                    super().__init__(plugin_manifest)

                model_providers = [{
                    "kind": "stt",
                    "id": "restart-fixture-stt",
                    "label": LABEL,
                    "settings_config": [],
                }]
        """))
    payload = output.getvalue()
    spec = _fixture_spec(
        payload,
        key="restart-fixture",
        label="Restart Fixture",
        guid=manifest["guid"],
        folder="cn-plugin-restart-fixture",
        entrypoint=entrypoint,
        provider_id="restart-fixture-stt",
    )
    provider_root = tmp_path / "providers"
    install_provider(
        spec, root=provider_root, opener=lambda _url, timeout: io.BytesIO(payload)
    )

    verifier = tmp_path / "verify_restart.py"
    verifier.write_text(textwrap.dedent("""
        import json
        import os
        import sys

        sys.path.insert(0, sys.argv[1])
        import lib.PluginManager as plugin_manager_module
        from lib.TarsProviderRegistry import TarsProviderSpec

        spec = TarsProviderSpec(**json.loads(sys.argv[3]))
        plugin_manager_module.TARS_PROVIDER_SPECS = (spec,)
        os.environ["TARS_PROVIDER_ROOT"] = sys.argv[2]
        manager = plugin_manager_module.PluginManager(
            {}, tars_profile=True, plugin_folder=sys.argv[2]
        )
        manager.load_tars_provider_plugins()
        manager.register_settings()
        provider = manager.get_plugin_provider(spec.guid, spec.provider_id)
        assert provider is not None
        assert provider["label"] == "Restart Fixture STT"
    """), encoding="utf-8")
    spec_json = json.dumps(spec.__dict__)

    completed = subprocess.run(
        [sys.executable, str(verifier), str(REPO_ROOT / "src"), str(provider_root), spec_json],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
