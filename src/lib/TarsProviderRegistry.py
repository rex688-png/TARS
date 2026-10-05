from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable
import urllib.request
import zipfile


@dataclass(frozen=True)
class TarsProviderSpec:
    key: str
    label: str
    kind: str
    provider_id: str
    guid: str
    version: str
    folder: str
    entrypoint: str
    url: str
    size: int
    extracted_size: int
    sha256: str
    source_revision: str


TARS_PROVIDER_SPECS = (
    TarsProviderSpec(
        key="parakeet-stt",
        label="Parakeet STT",
        kind="stt",
        provider_id="parakeet-stt",
        guid="b77dec4f-8993-4213-8d44-caf902dabc6d",
        version="0.0.10",
        folder="cn-plugin-parakett-stt",
        entrypoint="cn-plugin-parakett-stt.py",
        url="https://github.com/COVAS-Labs/plugin-parakeet-stt/releases/download/v0.0.10/cn-plugin-parakett-stt-v0-0-10-windows.zip",
        size=748_774_472,
        extracted_size=827_216_627,
        sha256="7ebe9b727471e44aa4cba1fe79c329d3fa0fd3c292f335fb2291c3a09139bbea",
        source_revision="ad9a31f8d46800b94ea371eeeeb8b377a47af951",
    ),
    TarsProviderSpec(
        key="pocket-tts",
        label="Pocket-TTS",
        kind="tts",
        provider_id="pocket-tts",
        guid="b7ddc677-0cfc-4081-af61-b2ebc2af5fe3",
        version="0.0.16",
        folder="cn-plugin-pocket-tts",
        entrypoint="cn-plugin-pocket-tts.py",
        url="https://github.com/COVAS-Labs/plugin-pocket-tts/releases/download/v0.0.16/cn-plugin-pocket-tts-v0-0-16-windows.zip",
        size=185_718_627,
        extracted_size=279_111_868,
        sha256="6929b28b56a81541502c0fc41f25076a604aac5ec4824dd1614a33e1c6707aa5",
        source_revision="ba1b2e51913967df5f09b2ec923ecaa243da8b1a",
    ),
    TarsProviderSpec(
        key="supertonic-tts",
        label="Supertonic TTS",
        kind="tts",
        provider_id="supertonic-tts",
        guid="7fd3d108-4e50-49db-8eb4-f3b4b8d53e66",
        version="0.1.5",
        folder="cn-plugin-supertonic-tts",
        entrypoint="cn-plugin-supertonic-tts.py",
        url="https://github.com/COVAS-Labs/plugin-supertonic-tts/releases/download/v0.1.5/cn-plugin-supertonic-tts-v0-1-5-windows.zip",
        size=326_321_197,
        extracted_size=374_430_217,
        sha256="c1c4645de838bf1cf14ecf278b1feabcca52ecd890af685cbc48014a221eccbb",
        source_revision="b2e2f798f5b761b7c97d4fcbee3cb749ec1a2877",
    ),
    TarsProviderSpec(
        key="gemma-embedding",
        label="Gemma Embedding",
        kind="embedding",
        provider_id="gemma-embedding",
        guid="88d3df68-d949-11f0-b7d9-e768d0e4b754",
        version="0.0.11",
        folder="cn-plugin-gemma-embedding",
        entrypoint="cn-plugin-gemma-embedding.py",
        url="https://github.com/COVAS-Labs/plugin-gemma-embedding/releases/download/v0.0.11/cn-plugin-gemma-embedding-v0-0-11-windows.zip",
        size=435_945_659,
        extracted_size=537_685_758,
        sha256="ebbc47d7e5d9d350ef9a6f9c4cf682413191ce89a97b58421be1bb27ec80a955",
        source_revision="a7b8a6f033174a46e07a164c91ebf8439d0c7e4e",
    ),
)

MARKER_NAME = ".tars-provider.json"


def provider_root() -> Path:
    return Path(os.environ.get("TARS_PROVIDER_ROOT", "providers")).resolve()


def provider_path(spec: TarsProviderSpec, root: Path | None = None) -> Path:
    return (root or provider_root()) / spec.folder


def _manifest_matches(spec: TarsProviderSpec, path: Path) -> bool:
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        marker = json.loads((path / MARKER_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return (
        manifest.get("guid") == spec.guid
        and manifest.get("version") == spec.version
        and manifest.get("entrypoint") == spec.entrypoint
        and (path / spec.entrypoint).is_file()
        and marker == {
            "key": spec.key,
            "version": spec.version,
            "sha256": spec.sha256,
            "source_revision": spec.source_revision,
        }
    )


def installed_provider_path(
    spec: TarsProviderSpec, root: Path | None = None
) -> Path | None:
    path = provider_path(spec, root)
    return path if _manifest_matches(spec, path) else None


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            target = (destination / info.filename).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError(f"provider archive contains unsafe path: {info.filename}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"provider archive contains a symbolic link: {info.filename}")
        package.extractall(destination)


def install_provider(
    spec: TarsProviderSpec,
    *,
    root: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    opener=urllib.request.urlopen,
) -> Path:
    install_root = (root or provider_root()).resolve()
    install_root.mkdir(parents=True, exist_ok=True)
    target = provider_path(spec, install_root)
    if installed_provider_path(spec, install_root):
        return target
    if target.exists():
        raise RuntimeError(
            f"Refusing to replace invalid provider directory {target}; remove it and retry"
        )

    for stale in install_root.glob(f".{spec.key}-*"):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{spec.key}-", dir=install_root))
    archive = temporary / "provider.zip"
    payload = temporary / "payload"
    try:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                digest = hashlib.sha256()
                received = 0
                with opener(spec.url, timeout=60) as response, archive.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if progress:
                            progress(received, spec.size)
                if received != spec.size:
                    raise ValueError(
                        f"download size mismatch for {spec.label}: {received} != {spec.size}"
                    )
                if digest.hexdigest() != spec.sha256:
                    raise ValueError(f"download checksum mismatch for {spec.label}")
                last_error = None
                break
            except (OSError, ValueError) as exc:
                last_error = exc
                archive.unlink(missing_ok=True)
                if attempt == 2:
                    raise
        if last_error is not None:
            raise last_error

        payload.mkdir()
        _safe_extract(archive, payload)
        manifest_path = payload / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("guid") != spec.guid
            or manifest.get("version") != spec.version
            or manifest.get("entrypoint") != spec.entrypoint
            or not (payload / spec.entrypoint).is_file()
        ):
            raise ValueError(f"official {spec.label} manifest does not match registry")
        (payload / MARKER_NAME).write_text(
            json.dumps({
                "key": spec.key,
                "version": spec.version,
                "sha256": spec.sha256,
                "source_revision": spec.source_revision,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(payload, target)
        return target
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
