import hashlib
import io
import json
from pathlib import Path
import sys
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
    stale = tmp_path / ".fixture-stt-interrupted"
    stale.mkdir()
    (stale / "partial").write_bytes(b"partial")

    installed = install_provider(
        spec, root=tmp_path, progress=lambda current, total: progress.append((current, total)),
        opener=lambda _url, timeout: io.BytesIO(payload),
    )

    assert installed_provider_path(spec, tmp_path) == installed
    assert (installed / "model" / "model.bin").read_bytes() == b"fixture"
    assert json.loads((installed / MARKER_NAME).read_text(encoding="utf-8"))["sha256"] == spec.sha256
    assert progress[-1] == (len(payload), len(payload))
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
