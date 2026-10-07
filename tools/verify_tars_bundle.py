#!/usr/bin/env python3
"""Verify or reproducibly record the immutable TARS plugin payload."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


PINNED_SHA = "67b1a1cab5a67d675372477dbcde061697e80bf5"
PLUGIN_NAMES = (
    "TARSExplorer",
    "TARSNavigator",
    "TARSGalaxy",
    "TARSChatter",
    "TARSExpedition",
    "TARSObservatoryBridge",
)
REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = REPO_ROOT / "vendor" / "tars-plugins"
MANIFEST_PATH = BUNDLE_ROOT / "provenance.json"


def payload_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    roots = [*(root / "plugins" / name for name in PLUGIN_NAMES), root / "prompt"]
    for payload_root in roots:
        if not payload_root.is_dir():
            raise SystemExit(f"missing bundled payload directory: {payload_root}")
        for path in sorted(
            item
            for item in payload_root.rglob("*")
            if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"
        ):
            relative = path.relative_to(root).as_posix()
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def source_payload(source: Path) -> dict[str, str]:
    """Read the exact pinned Git objects without changing a reference checkout."""
    paths = subprocess.run(
        ['git', '-C', str(source), 'ls-tree', '-r', '--name-only', PINNED_SHA,
         *(f'plugins/{name}' for name in PLUGIN_NAMES), 'prompt'],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    if not paths:
        raise ValueError('Pinned plugin source payload is missing')
    return {path: hashlib.sha256(subprocess.run(
        ['git', '-C', str(source), 'show', f'{PINNED_SHA}:{path}'],
        check=True, capture_output=True,
    ).stdout).hexdigest() for path in paths}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--bundle", type=Path, default=BUNDLE_ROOT)
    parser.add_argument("--source", type=Path, help="optional pinned TARS-Plugins checkout")
    args = parser.parse_args()

    bundle_root = args.bundle.resolve()
    manifest_path = bundle_root / "provenance.json"
    actual = {"source_revision": PINNED_SHA, "files": payload_files(bundle_root)}
    if args.write:
        manifest_path.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    else:
        expected = json.loads(manifest_path.read_text(encoding="utf-8"))
        if actual != expected:
            raise SystemExit("bundled TARS payload differs from provenance.json")

    if args.source:
        if actual["files"] != source_payload(args.source):
            raise SystemExit("bundled TARS payload differs from pinned source checkout")
    print(f"verified {len(actual['files'])} files from TARS-Plugins@{PINNED_SHA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
