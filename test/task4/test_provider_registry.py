import hashlib
import io
import json
import os
from pathlib import Path
from dataclasses import replace
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


def test_registry_pins_controlled_windows_releases():
    assert [spec.key for spec in TARS_PROVIDER_SPECS] == [
        "parakeet-stt", "pocket-tts", "supertonic-tts", "gemma-embedding"
    ]
    assert {spec.kind for spec in TARS_PROVIDER_SPECS} == {"stt", "tts", "embedding"}
    assert [spec.provider_id for spec in TARS_PROVIDER_SPECS] == [
        "parakeet-stt", "pocket-tts", "supertonic-tts", "gemma-embedding"
    ]
    assert all(spec.url.startswith("https://github.com/COVAS-Labs/") for spec in TARS_PROVIDER_SPECS)
    assert all(len(spec.sha256) == 64 and spec.size > 0 for spec in TARS_PROVIDER_SPECS)

    pocket = next(spec for spec in TARS_PROVIDER_SPECS if spec.key == "pocket-tts")
    assert pocket.version == "0.0.17"
    assert pocket.base_version == "0.0.16"
    assert pocket.overlay_dir == "pocket-tts-0.0.17-tarsfix"
    assert pocket.source_revision == "65d343bd3f5f2386031fcb142dbf69add3902cdc"
    assert pocket.archive_source_revision == "ba1b2e51913967df5f09b2ec923ecaa243da8b1a"
    assert dict(pocket.overlay_files) == {
        "TARS_FIX_NOTES.txt": "a8a51bfd38836d3afebd917d097d0e89a159c7d9c3a6a193d449683e0a4c6a2c",
        "cn-plugin-pocket-tts.py": "ae9e5b64a462135c1e5430b06bce0c2e856db31f8e4251113e54cca19c59de80",
        "manifest.json": "61ecfb5ecd25bf7ef11ce3e30106ae0b8f50b52403bd1ddbfcf4201e3583fdc3",
    }


def test_pocket_tts_tarsfix_overlays_verified_base_and_upgrades_0016(tmp_path):
    registry_spec = next(spec for spec in TARS_PROVIDER_SPECS if spec.key == "pocket-tts")
    payload = _archive({
        "guid": registry_spec.guid,
        "version": registry_spec.base_version,
        "entrypoint": registry_spec.entrypoint,
    }, extra_name=registry_spec.entrypoint)
    spec = replace(
        registry_spec,
        url="https://example.invalid/pocket.zip",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        replaces_sha256=hashlib.sha256(payload).hexdigest(),
    )

    existing = tmp_path / spec.folder
    existing.mkdir()
    (existing / spec.entrypoint).write_text("# old provider\n", encoding="utf-8")
    (existing / "manifest.json").write_text(json.dumps({
        "guid": spec.guid,
        "version": spec.replaces_version,
        "entrypoint": spec.entrypoint,
    }), encoding="utf-8")
    (existing / MARKER_NAME).write_text(json.dumps({
        "key": spec.key,
        "version": spec.replaces_version,
        "sha256": spec.replaces_sha256,
        "source_revision": spec.replaces_source_revision,
    }), encoding="utf-8")

    installed = install_provider(
        spec, root=tmp_path, opener=lambda _url, timeout: io.BytesIO(payload)
    )

    manifest = json.loads((installed / "manifest.json").read_text(encoding="utf-8"))
    marker = json.loads((installed / MARKER_NAME).read_text(encoding="utf-8"))
    assert manifest["version"] == "0.0.17"
    assert "Pocket-TTS stability patch 0.0.17" in (installed / "TARS_FIX_NOTES.txt").read_text()
    assert hashlib.sha256((installed / spec.entrypoint).read_bytes()).hexdigest() == dict(
        spec.overlay_files
    )[spec.entrypoint]
    assert marker["source_revision"] == spec.source_revision
    assert marker["archive_source_revision"] == spec.archive_source_revision
    assert (installed / "model" / "model.bin").read_bytes() == b"fixture"


def test_pocket_tts_tarsfix_rejects_unverified_overlay(tmp_path):
    registry_spec = next(spec for spec in TARS_PROVIDER_SPECS if spec.key == "pocket-tts")
    payload = _archive({
        "guid": registry_spec.guid,
        "version": registry_spec.base_version,
        "entrypoint": registry_spec.entrypoint,
    }, extra_name=registry_spec.entrypoint)
    bad_files = list(registry_spec.overlay_files)
    bad_files[0] = (bad_files[0][0], "0" * 64)
    spec = replace(
        registry_spec,
        url="https://example.invalid/pocket.zip",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        overlay_files=tuple(bad_files),
    )

    with pytest.raises(ValueError, match="overlay checksum"):
        install_provider(
            spec, root=tmp_path, opener=lambda _url, timeout: io.BytesIO(payload)
        )

    assert not (tmp_path / spec.folder).exists()


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
