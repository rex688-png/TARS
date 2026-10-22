"""Offline release checks: synthetic assets and fake gh, never real publication."""
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('release_metadata', ROOT / 'tools/release_metadata.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
SOURCE = 'a' * 40
PIN = '6f85f5b8dee4f8ea399df4e86d7cb0a5df03bcc2'


@pytest.fixture
def packages(tmp_path):
    (tmp_path / 'electron').mkdir()
    (tmp_path / 'vendor/tars-plugins').mkdir(parents=True)
    (tmp_path / 'package.json').write_text(json.dumps({'version':'0.5.0-beta.1','build':{'appId':'com.rex688.tars'}}))
    (tmp_path / 'electron/package.json').write_text(json.dumps({'name':'com.rex688.tars','version':'0.5.0-beta.1'}))
    (tmp_path / 'package-lock.json').write_text(json.dumps({'version':'0.5.0-beta.1','packages':{'':{'version':'0.5.0-beta.1'}}}))
    (tmp_path / 'vendor/tars-plugins/provenance.json').write_text(json.dumps({'source_revision':PIN}))
    return tmp_path


def workflow():
    return yaml.load((ROOT / '.github/workflows/build-executable.yml').read_text(), Loader=yaml.BaseLoader)


def test_current_package_and_lock_versions_are_consistent():
    assert release.validate() == json.loads((ROOT / 'package.json').read_text())['version']


def test_placeholder_is_never_a_release(packages):
    for name in ('package.json', 'electron/package.json', 'package-lock.json'):
        p=packages/name;data=json.loads(p.read_text());data['version']='0.0.0'
        if name=='package-lock.json':data['packages']['']['version']='0.0.0'
        p.write_text(json.dumps(data))
    assert release.validate(packages)=='0.0.0'
    with pytest.raises(ValueError):release.validate(packages,'v0.0.0')


@pytest.mark.parametrize('tag',['0.5.0-beta.1','v0.5.0-beta.2','v0.5.0','v0.0.0'])
def test_mismatched_tag_is_rejected(packages,tag):
    with pytest.raises(ValueError): release.validate(packages,tag)


@pytest.mark.parametrize('path',['electron/package.json','package-lock.json'])
def test_diverging_mirrors_are_rejected(packages,path):
    p=packages/path;d=json.loads(p.read_text());d['version']='0.4.0';p.write_text(json.dumps(d))
    with pytest.raises(ValueError): release.validate(packages)


def test_versioned_asset_hashes_and_source_provenance(packages,monkeypatch):
    assets=packages/'assets';assets.mkdir()
    (assets/'old-name.msi').write_bytes(b'synthetic msi, not an installer')
    (assets/'TARS-portable-abcdef0.zip').write_bytes(b'synthetic zip, not a production archive')
    monkeypatch.setattr(release.subprocess,'check_output',lambda *a,**k:SOURCE+'\n')
    output=release.prepare(assets,'v0.5.0-beta.1',SOURCE,'https://example.invalid/run/1','X64',packages)
    metadata=json.loads((output/'release-provenance.json').read_text())
    assert metadata['source_commit']==SOURCE and metadata['plugin_source_revision']==PIN
    assert metadata['architecture']=='x64' and metadata['version']=='0.5.0-beta.1'
    assert set(metadata['assets_sha256'])=={'TARS-0.5.0-beta.1-windows-x64.msi','TARS-0.5.0-beta.1-windows-x64-portable.zip'}
    for line in (output/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ');assert hashlib.sha256((output/name).read_bytes()).hexdigest()==digest
    assert (assets/'old-name.msi').exists()
    with pytest.raises(FileExistsError):
        release.prepare(assets,'v0.5.0-beta.1',SOURCE,'https://example.invalid/run/1','X64',packages)


@pytest.mark.parametrize('case',['wrong_source','wrong_tag_source','wrong_arch','ambiguous_msi','missing_zip'])
def test_unsafe_release_inputs_fail_before_staging(packages,monkeypatch,case):
    assets=packages/'assets';assets.mkdir();(assets/'one.msi').write_bytes(b'fake');(assets/'TARS-portable-a.zip').write_bytes(b'fake')
    def git(args,**kwargs):return ('b'*40 if case=='wrong_source' or (case=='wrong_tag_source' and args[-1]!='HEAD') else SOURCE)+'\n'
    monkeypatch.setattr(release.subprocess,'check_output',git)
    if case=='ambiguous_msi':(assets/'two.msi').write_bytes(b'fake')
    if case=='missing_zip':(assets/'TARS-portable-a.zip').unlink()
    with pytest.raises(ValueError):
        release.prepare(assets,'v0.5.0-beta.1',SOURCE,'https://example.invalid/run/1','ARM64' if case=='wrong_arch' else 'X64',packages)
    assert not (assets/'reviewed').exists()


def test_release_workflow_preserves_safety_gates():
    w=workflow();job=w['jobs']['draft-release']
    assert w['permissions']=={'contents':'read'}
    assert job['permissions']=={'contents':'write'}
    assert job['needs']==['electron-build','e2e']
    assert job['if']=="github.event_name == 'push' && startsWith(github.ref, 'refs/tags/')"
    run=job['steps'][-1]['run']
    assert '--clobber' not in run and '--verify-tag' in run and '--draft' in run
    assert 'release-assets/reviewed/*' in run
    assert all('contents' not in j.get('permissions',{}) for n,j in w['jobs'].items() if n!='draft-release')


@pytest.mark.parametrize('mode',['missing','draft','published','publish_during_run','asset_collision'])
def test_draft_release_shell_against_fake_gh_only(tmp_path,mode):
    fake=tmp_path/'fake gh.py'
    fake.write_text(r'''
import json,os,sys
from pathlib import Path
args=sys.argv[1:];root=Path(os.environ['FAKE_ROOT']);mode=os.environ['FAKE_MODE']
with (root/'calls.jsonl').open('a') as f:f.write(json.dumps(args)+'\n')
if args[:2]==['release','view']:
    if mode=='missing' and not (root/'created').exists():sys.exit(1)
    if '--json' in args:
        late=mode=='publish_during_run' and (root/'checked').exists()
        print('false' if mode=='published' or late else 'true');(root/'checked').touch()
elif args[:2]==['release','create']:(root/'created').touch()
elif args[:2]==['release','upload']:
    if mode=='asset_collision':sys.exit(1)
else:sys.exit(90)
''')
    assets=tmp_path/'release-assets/reviewed';assets.mkdir(parents=True);(assets/'synthetic.txt').write_text('not a release asset')
    script=workflow()['jobs']['draft-release']['steps'][-1]['run']
    if os.name == 'nt':
        # Windows' bare bash can resolve to WSL; use the Bash shipped with Git.
        git = shutil.which('git')
        assert git, 'Git for Windows is required to exercise the Ubuntu release shell'
        bash = Path(git).parent.parent / 'bin/bash.exe'
        assert bash.is_file(), f'Git Bash not found beside Git: {bash}'
    else:
        bash = shutil.which('bash')
        assert bash, 'Bash is required to exercise the Ubuntu release shell'
    env = dict(os.environ, RELEASE_TAG='v0.5.0-beta.1', FAKE_ROOT=str(tmp_path), FAKE_MODE=mode,
               FAKE_GH_PYTHON=sys.executable, FAKE_GH_SCRIPT=str(fake))
    if os.name == 'nt' and mode == 'missing':
        # Diagnostic only: run the former native-shebang launcher directly, never real gh.
        legacy = tmp_path / 'legacy-gh'
        legacy.write_text('#!' + sys.executable + '\n' + fake.read_text())
        probe_root = tmp_path / 'legacy probe'; probe_root.mkdir()
        probe = subprocess.run(['bash', '-c', shlex.quote(legacy.as_posix()) + ' release view probe'],
                               env=dict(env, FAKE_ROOT=str(probe_root), FAKE_MODE='draft'),
                               capture_output=True, text=True)
        detail = json.dumps({'legacy_bash': shutil.which('bash'), 'selected_bash': str(bash),
                             'exit_code': probe.returncode, 'stdout': probe.stdout, 'stderr': probe.stderr})
        print('Legacy Windows launcher diagnostic: ' + detail)
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            print('::notice title=Legacy fake-gh launcher diagnostic::' + detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A'))
    launcher = r"""
set -euo pipefail
if command -v cygpath >/dev/null 2>&1; then
  FAKE_GH_PYTHON=$(cygpath -u "$FAKE_GH_PYTHON")
  FAKE_GH_SCRIPT=$(cygpath -u "$FAKE_GH_SCRIPT")
fi
gh() { "$FAKE_GH_PYTHON" "$FAKE_GH_SCRIPT" "$@"; }
"""
    result=subprocess.run([str(bash),'--noprofile','--norc','-c',launcher+script],cwd=tmp_path,
                          env=env,capture_output=True,text=True)
    diagnostic = f'bash={bash}; exit={result.returncode}; stdout={result.stdout!r}; stderr={result.stderr!r}'
    calls_path = tmp_path/'calls.jsonl'
    assert calls_path.is_file(), diagnostic
    calls=[json.loads(s) for s in calls_path.read_text().splitlines()]
    assert (result.returncode==0)==(mode in ['missing','draft']), diagnostic
    if mode in ['published','publish_during_run']:
        assert not any(c[:2]==['release','upload'] for c in calls)
    if mode=='draft':assert not any(c[:2]==['release','create'] for c in calls)
    if mode=='missing':
        created=next(c for c in calls if c[:2]==['release','create'])
        assert '--draft' in created and '--prerelease' in created and '--verify-tag' in created
