#!/usr/bin/env python3
"""Validate release inputs and stage metadata; never create tags or GitHub releases."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-beta\.([1-9]\d*))?')


def msi_version_info(version):
    result = subprocess.run(['node', str(Path(__file__).with_name('msi-version.cjs')), version],
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Invalid MSI version: ' + result.stderr.strip())
    return json.loads(result.stdout)


def validate(root=ROOT, tag=None):
    package = json.loads((root / 'package.json').read_text())
    electron = json.loads((root / 'electron/package.json').read_text())
    lock = json.loads((root / 'package-lock.json').read_text())
    version = package['version']  # Authoritative; the other fields are checked mirrors.
    if not VERSION.fullmatch(version):
        raise ValueError('Version must be MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-beta.N')
    msi_version_info(version)  # Reject out-of-range/aliasing versions before packaging.
    if any(value != version for value in (electron['version'], lock['version'], lock['packages']['']['version'])):
        raise ValueError('Root/Electron manifests and root lockfile versions must agree')
    if package['build']['appId'] != 'com.rex688.tars' or electron['name'] != 'com.rex688.tars':
        raise ValueError('Preserve the existing TARS installation identity')
    if tag is not None and (tag != 'v' + version or version == '0.0.0'):
        raise ValueError('Release tag must equal v<package version>; 0.0.0 is not a release')
    return version


def prepare(assets, tag, source, run_url, architecture, root=ROOT):
    version = validate(root, tag)
    if architecture != 'X64':
        raise ValueError('This release path accepts only the existing Windows x64 build')
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('Expected a full source commit SHA')
    for ref in ('HEAD', f'refs/tags/{tag}^{{commit}}'):
        actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', ref], text=True).strip()
        if actual != source:
            raise ValueError('Tag, checked-out source and workflow SHA must match')
    selected = []
    for pattern, suffix in (('*.msi', '.msi'), ('TARS-portable-*.zip', '-portable.zip')):
        matches = list(assets.glob(pattern))
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one {pattern} asset, found {len(matches)}')
        selected.append((matches[0], f'TARS-{version}-windows-x64{suffix}'))
    output = assets / 'reviewed'
    output.mkdir()  # Never overwrite a previously staged asset directory.
    hashes = {}
    for source_file, name in selected:
        destination = output / name
        shutil.copyfile(source_file, destination)
        hashes[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    pin = json.loads((root / 'vendor/tars-plugins/provenance.json').read_text())['source_revision']
    msi = msi_version_info(version)
    provenance = {'msi_product_version': msi['product_version'], 'msi_upgrade_code': msi['upgrade_code'],
                  'version': version, 'tag': tag, 'source_commit': source,
                  'workflow_run': run_url, 'platform': 'windows', 'architecture': 'x64',
                  'plugin_source_revision': pin, 'assets_sha256': hashes}
    metadata = output / 'release-provenance.json'
    metadata.write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')
    hashes[metadata.name] = hashlib.sha256(metadata.read_bytes()).hexdigest()
    (output / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(hashes.items())))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag')
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--source')
    parser.add_argument('--run-url')
    parser.add_argument('--architecture')
    args = parser.parse_args()
    if args.assets:
        if not all((args.tag, args.source, args.run_url, args.architecture)):
            parser.error('Asset preparation requires tag, source, run URL and architecture')
        print(prepare(args.assets, args.tag, args.source, args.run_url, args.architecture))
    else:
        print(validate(tag=args.tag))
