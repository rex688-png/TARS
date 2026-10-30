"""Factory-only experiment contracts; no model calls, profile writes or gameplay input."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'experiments/prompt-architecture'
BASELINE = ROOT / 'vendor/tars-plugins/prompt/prompt.txt'


def load_evaluator():
    spec = importlib.util.spec_from_file_location('prompt_experiment', HERE / 'evaluate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_retains_every_declared_technical_contract_verbatim():
    baseline, candidate = BASELINE.read_text(encoding='utf-8'), (HERE/'candidate.txt').read_text(encoding='utf-8')
    contract = json.loads((HERE/'retained-contracts.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(baseline.encode()).hexdigest() == contract['baseline_sha256']
    # Section boundaries are the factory's all-caps headings, not hand-copied rule snippets.
    import re
    starts = list(re.finditer(r'^([A-Z][A-Z +]+)\n', baseline, re.M))
    sections = {m[1]:baseline[m.start():starts[i+1].start() if i+1<len(starts) else len(baseline)].strip()
                for i,m in enumerate(starts)}
    for name in contract['verbatim_sections']:
        assert sections[name] in candidate, name
    assert '{commander_name}' in candidate
    assert 'TEST_CMDR' in candidate.format(commander_name='TEST_CMDR')


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    target = tmp_path_factory.mktemp('prompt-experiment')
    command = [sys.executable, str(HERE/'evaluate.py'), 'prepare', '--output-dir', str(target)]
    result = subprocess.run(command, cwd=ROOT, env={**os.environ, 'PYTHONIOENCODING':'utf-8'}, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stderr[-3000:] + result.stdout[-3000:]
    return target, json.loads((target/'comparison.json').read_text(encoding='utf-8')), json.loads((target/'requests.json').read_text(encoding='utf-8'))


def test_pair_changes_only_the_factory_text_in_main_generation(prepared):
    _, manifest, requests = prepared
    baseline, candidate = BASELINE.read_text(encoding='utf-8').format(commander_name='TEST_CMDR'), (HERE/'candidate.txt').read_text(encoding='utf-8').format(commander_name='TEST_CMDR')
    pairs = {}
    for request in requests:
        pairs.setdefault(request['scenario'], {})[request['arm']] = request
    for scenario in manifest['scenarios']:
        if scenario['path']=='runtime_only':
            assert scenario['id'] not in pairs
            continue
        a,b = copy.deepcopy(pairs[scenario['id']]['baseline']), copy.deepcopy(pairs[scenario['id']]['candidate'])
        for request in (a,b):
            request.pop('arm'); request.pop('request_sha256')
        if scenario['path']=='main':
            assert a['messages'][0]['content'].count(baseline)==1
            a['messages'][0]['content'] = a['messages'][0]['content'].replace(baseline,candidate)
            assert 'TARS Combat: use tarsCombatQuery' in b['messages'][0]['content']
            assert 'TARS DIRECTOR — HIGH PRIORITY CONTINUITY' in b['messages'][0]['content']
        else:
            assert scenario['arms']['baseline']['model_input_sha256']==scenario['arms']['candidate']['model_input_sha256']
        assert a==b, scenario['id']
    assert manifest['model_calls']==0
    assert manifest['model_quality_comparison']=='NOT EXECUTED'
    assert all(s['quality_result'] is None for s in manifest['scenarios'])


def test_runtime_fixtures_and_tools_are_current_and_nonempty(prepared):
    _, manifest, requests = prepared
    scenarios = {s['id']:s for s in manifest['scenarios']}
    assert scenarios['historical_replay']['selected_record_count'] > 0
    assert scenarios['routine_scan_gate']['selected_record_count'] > 0
    expedition = next(r for r in requests if r['scenario']=='expedition_full_tool')
    tools = {t['function']['name']:t['function'] for t in expedition['tools']}
    assert {'tars_explorer_system_summary','tars_navigator_status','tarsCombatQuery'} <= tools.keys()
    assert 'CURRENT-EXPEDITION' in tools['tars_expedition_status']['description']
    assert 'full' in json.dumps(tools['tars_expedition_status']['parameters'])
    automatic = next(r for r in requests if r['scenario']=='fss_not_mapped')
    assert automatic['tools']==[] and automatic['tool_choice'] is None


def fake_responses(requests, settings):
    # Harness fixtures only. Never saved as experiment/model-quality evidence.
    return [{'request_sha256':r['request_sha256'],'settings':settings,'status':'completed',
             'text':'Synthetic fixture answer.','tool_calls':[]} for r in requests]


def test_blind_review_keeps_quality_and_usage_unscored(prepared, tmp_path):
    folder, manifest, requests = prepared
    evaluator = load_evaluator()
    responses = tmp_path/'responses.json'
    responses.write_text(json.dumps(fake_responses(requests, manifest['settings'])), encoding='utf-8')
    rows = evaluator.review(folder/'comparison.json',folder/'requests.json',responses,tmp_path/'review')
    assert len(rows)==len(requests)
    assert all(r['quality_scores'] is None and r['provider_usage'] is None for r in rows)
    assert 'baseline' not in (tmp_path/'review/blind-review.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('problem', ['missing','duplicate','settings','hash','status'])
def test_review_rejects_unpaired_or_untraceable_outputs(prepared, tmp_path, problem):
    folder, manifest, requests = prepared
    responses = fake_responses(requests, manifest['settings'])
    if problem=='missing': responses.pop()
    if problem=='duplicate': responses.append(responses[0])
    if problem=='settings': responses[0]['settings']={'model':'different'}
    if problem=='hash': responses[0]['request_sha256']='unknown'
    if problem=='status': responses[0].pop('status')
    path=tmp_path/'responses.json'; path.write_text(json.dumps(responses), encoding='utf-8')
    with pytest.raises(ValueError):
        load_evaluator().review(folder/'comparison.json',folder/'requests.json',path,tmp_path/'review')


def test_review_distinguishes_error_and_action_from_abstention(prepared, tmp_path):
    folder, manifest, requests = prepared
    responses = fake_responses(requests, manifest['settings'])
    for response in responses[:3]: response['text']='SKIP'
    responses[0]['status']='error'
    responses[1]['tool_calls']=[{'name':'synthetic'}]
    path=tmp_path/'responses.json'; path.write_text(json.dumps(responses), encoding='utf-8')
    rows=load_evaluator().review(folder/'comparison.json',folder/'requests.json',path,tmp_path/'review')
    assert sum(r['intentional_abstention'] for r in rows)==1


def test_review_preserves_unicode_with_cp1252_locale_default(prepared, tmp_path, monkeypatch):
    folder, manifest, requests = prepared
    responses = fake_responses(requests, manifest['settings'])
    text = 'Żółć — 航行 🚀'
    responses[0]['text'] = text
    path = tmp_path/'unicode-responses.json'
    path.write_text(json.dumps(responses, ensure_ascii=False), encoding='utf-8')

    original_open = Path.open
    def windows_default_open(self, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
        if 'b' not in mode and encoding in (None, 'locale'):
            encoding = 'cp1252'
        return original_open(self, mode, buffering, encoding, errors, newline)
    monkeypatch.setattr(Path, 'open', windows_default_open)
    with path.open() as stream:
        assert text not in stream.read()  # The simulated default really is not UTF-8.

    rows = load_evaluator().review(folder/'comparison.json', folder/'requests.json', path, tmp_path/'review')
    assert text in (tmp_path/'review/blind-review.md').read_text(encoding='utf-8')
    assert any(row['output_chars'] == len(text) for row in rows)
    assert json.loads((tmp_path/'review/review-key.json').read_text(encoding='utf-8')) == rows


def test_experiment_text_io_declares_utf8():
    # Cover preparation, plugin source/fixture reads and test subprocess capture,
    # including paths that are not reached by the review round-trip above.
    import ast
    for path in (HERE/'evaluate.py', Path(__file__)):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in ('read_text', 'write_text') or (
                node.func.attr == 'run' and any(kw.arg == 'text' for kw in node.keywords)
            ):
                encoding = next((kw.value for kw in node.keywords if kw.arg == 'encoding'), None)
                assert isinstance(encoding, ast.Constant) and encoding.value == 'utf-8', (path.name, node.lineno)
