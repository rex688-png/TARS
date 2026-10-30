#!/usr/bin/env python3
"""Offline prompt experiment. Never reads a user profile, calls a model or executes tools."""
from __future__ import annotations

import argparse
import ast
from collections import deque
from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import io
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUNDLE = ROOT / 'vendor/tars-plugins'
sys.path.insert(0, str(ROOT / 'src'))
STAMP = '2000-01-01T12:00:00+00:00'
SETTINGS = {'model': 'gpt-6-luna', 'temperature': 0.3, 'reasoning_effort': 'none'}


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls.fromisoformat(STAMP)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


class SystemDB:
    def get_bodies(self, *args, **kwargs): return []
    def get_system(self, *args, **kwargs): return None
    def get_system_info(self, *args, **kwargs): return None
    def get_stations(self, *args, **kwargs): return []


def load_plugins():
    from lib.PluginManager import PluginManager
    from lib.PluginBase import PluginManifest
    manager = PluginManager({}, tars_profile=True, plugin_folder=str(BUNDLE / 'plugins'))
    loaded = {}
    for name in ('TARSExplorer', 'TARSNavigator', 'TARSExpedition', 'TARSGalaxy', 'TARSObservatoryBridge', 'TARSChatter', 'TARSCombat'):
        folder = BUNDLE / 'plugins' / name
        manifest = PluginManifest((folder / 'manifest.json').read_text(encoding='utf-8'))
        plugin = manager.load_plugin_module(manifest, str(folder / manifest.entrypoint))
        loaded[name] = plugin
    # No on_chat_start hooks: no journal imports, workers, network, profile writes or key input.
    return loaded


def plugin_tools(plugins):
    """Extract current literal descriptions + real Pydantic schemas without action startup."""
    tools = {}
    for plugin in plugins.values():
        modules = []
        for cls in reversed(type(plugin).__mro__):
            module = sys.modules.get(cls.__module__)
            if module is None or not getattr(module, '__file__', None):
                continue
            if Path(module.__file__).is_relative_to(BUNDLE) and module not in modules:
                modules.append(module)
        for module in modules:
            source = Path(module.__file__).read_text(encoding='utf-8')
            for node in ast.walk(ast.parse(source)):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != 'register_action':
                    continue
                kw = {key:value for key,value in zip(('name','description','parameters'),node.args[:3])}
                kw.update({x.arg:x.value for x in node.keywords})
                if not {'name', 'description', 'parameters'} <= kw.keys():
                    raise ValueError('Unsupported dynamic plugin registration')
                # Fail loudly on a newly dynamic schema; never silently invent a tool.
                tool_name, description = ast.literal_eval(kw['name']), ast.literal_eval(kw['description'])
                schema = getattr(module, kw['parameters'].id).model_json_schema()
                tools[tool_name] = {'type': 'function', 'function': {'name': tool_name, 'description': description, 'parameters': schema}}
    return [tools[name] for name in sorted(tools)]


def states():
    from lib.Projections import registerProjections
    from lib.projections.current_status import StatusFuel
    class Collector:
        def __init__(self): self.projections = []
        def register_projection(self, projection): self.projections.append(projection)
    collector = Collector()
    registerProjections(collector, SystemDB(), 300, 100000)
    result = {p.__class__.__name__: p.state for p in collector.projections}
    result['CurrentStatus'].flags.InMainShip = True
    result['CurrentStatus'].GuiFocus = 'NoFocus'
    result['CurrentStatus'].Fuel = StatusFuel(FuelMain=24.7, FuelReservoir=0.5)
    result['ShipInfo'].FuelMain = 24.7
    result['ShipInfo'].FuelMainCapacity = 32
    result['Location'].StarSystem = 'TEST_SYSTEM'
    result['Location'].StarPos = [1., 2., 3.]
    return result


def prepared_chatter(plugin):
    """Capture the actual preparer's request with one explicitly synthetic admitted anchor."""
    from lib.Logger import ModelUsageStats
    captured = []
    def capture(**kwargs):
        captured.append(kwargs)
        # Internal capture sentinel; this is not an inferred model answer.
        return ('SKIP', None, ModelUsageStats())
    plugin._original_generate = capture
    plugin._llm_model = SimpleNamespace()
    plugin._conversation_anchors = lambda *a, **kw: [{'kind': 'surface_operation', 'event': 'Touchdown', 'age_seconds': 5, 'fact': 'Landing completed on the far side of a ridge.'}]
    plugin._choose_chatter_topics = lambda *a, **kw: ['surface']
    plugin._host_opportunity_valid = lambda: True
    with patch.object(sys.modules[type(plugin).__module__].time, 'time', return_value=datetime.fromisoformat(STAMP).timestamp()):
        plugin._prepare_chatter_line(event_context={'event': 'Touchdown'})
    if len(captured) != 1:
        raise RuntimeError('Expected exactly one preparer request')
    return captured[0]['messages']


def assemble(personality, scenario, plugins):
    from lib.Event import ConversationEvent, GameEvent, PluginEvent, MemoryEvent, ToolEvent
    from lib.PromptGenerator import PromptGenerator
    generator = PromptGenerator('TEST_CMDR', personality, [], SystemDB())
    events = [ConversationEvent(kind=role, content=text, timestamp=STAMP) for role, text in scenario.get('history', [])]
    for plugin in plugins.values():
        for method in ('_prompt_noteworthy_target', '_prompt_journey_target', '_prompt_observatory_fact'):
            callback = getattr(plugin, method, None)
            if callback:
                # Use the production plugin handler only for its registered event type.
                event_name = {'_prompt_noteworthy_target':'TARSExplorerTarget', '_prompt_journey_target':'TARSNavigatorTarget', '_prompt_observatory_fact':'TARSObservatoryFact'}[method]
                generator.register_prompt_event_handler(lambda e, fn=callback, key=event_name:
                    fn(e) if isinstance(e, PluginEvent) and e.plugin_event_name == key else None)
    if scenario.get('event_name'):
        events.append(PluginEvent(plugin_event_name=scenario['event_name'], plugin_event_content=scenario['payload'], timestamp=STAMP))
    if scenario.get('user'):
        events.append(ConversationEvent(kind='user', content=scenario['user'], timestamp=STAMP))
    if scenario.get('tool_result'):
        tool = scenario['tool_result']
        events.append(ToolEvent(timestamp=STAMP,
            request=[{'id':'eval_call','type':'function','function':{'name':tool['name'],'arguments':json.dumps(tool['arguments'])}}],
            results=[{'tool_call_id':'eval_call','role':'tool','name':tool['name'],'content':json.dumps(tool['result'])}]))
    memories = [MemoryEvent(content=scenario['memory'], metadata={'time_until':946684800.}, embedding=[], timestamp=STAMP)] if scenario.get('memory') else []
    with patch('lib.PromptGenerator.datetime', FrozenDatetime):
        messages, _ = generator.generate_prompt(events, states(), [events[-1]], memories)
    # Preserve the exact integrated Assistant append without creating a second policy.
    combat_literals = [node.value for node in ast.walk(ast.parse((ROOT / 'src/lib/Assistant.py').read_text(encoding='utf-8')))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith('\n\nTARS Combat:')]
    if len(combat_literals) != 1:
        raise RuntimeError('Integrated Combat policy append changed; review the experiment adapter')
    messages[0]['content'] += combat_literals[0]
    director = plugins['TARSChatter']
    director._assistant_lines = deque([{'text':text} for role, text in scenario.get('history', []) if role == 'assistant'])
    index = director._main_covas_system_index(messages)
    if index is None:
        raise RuntimeError('Director failed to recognize production prompt')
    return director._inject_director(messages, index)


def prepare(output, encoding=None):
    tokenizer = None
    if encoding:
        import tiktoken
        tokenizer = tiktoken.get_encoding(encoding)
    import pysqlite3
    import sqlite_vec
    from lib.Database import set_connection_for_testing
    old_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    conn = pysqlite3.connect(':memory:')
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    set_connection_for_testing(conn)
    prompts = {'baseline': (BUNDLE / 'prompt/prompt.txt').read_text(encoding='utf-8'), 'candidate': (HERE / 'candidate.txt').read_text(encoding='utf-8')}
    scenarios = json.loads((HERE / 'scenarios.json').read_text(encoding='utf-8'))
    requests, rows = [], []
    output.mkdir(parents=True, exist_ok=True)
    try:
        with redirect_stdout(io.StringIO()):
            plugins = load_plugins()
            tools = plugin_tools(plugins)
            standalone = prepared_chatter(plugins['TARSChatter'])
            for scenario in scenarios:
                row = {'id':scenario['id'], 'path':scenario['path'], 'checks':scenario['checks'], 'quality_result':None}
                if scenario.get('journal_fixture'):
                    fixture = ROOT / scenario['journal_fixture']
                    records = [json.loads(line) for line in fixture.read_text(encoding='utf-8').splitlines() if line.strip()]
                    selected = [r for r in records if r.get('event') in scenario['select_events']]
                    row.update(fixture_sha256=digest(fixture.read_bytes()), selected_record_count=len(selected))
                    # These are runtime-only fixtures. No prompt bypasses admission.
                row['arms'] = {}
                if scenario['path'] != 'runtime_only':
                    for arm, personality in prompts.items():
                        messages = standalone if scenario['path'] == 'prepared_chatter' else assemble(personality, scenario, plugins)
                        request = {'scenario':scenario['id'], 'arm':arm, 'settings':SETTINGS,
                            'messages':messages, 'tools':tools if scenario['path']=='main' and scenario.get('user') else []}
                        request['tool_choice'] = 'auto' if request['tools'] else None
                        request['request_sha256'] = digest(request)
                        requests.append(request)
                        serialized = json.dumps({'messages':messages, 'tools':request['tools']}, ensure_ascii=False, sort_keys=True)
                        row['arms'][arm] = {'request_sha256':request['request_sha256'], 'model_input_sha256':digest({k:v for k,v in request.items() if k not in ('arm','scenario','request_sha256')}), 'input_chars':len(serialized),
                            'serialized_input_tokens':len(tokenizer.encode(serialized)) if tokenizer else None,
                            'system_chars':sum(len(m['content']) for m in messages if m['role']=='system')}
                rows.append(row)
    finally:
        conn.close()
        logging.disable(old_logging)
    manifest = {'schema_version':1, 'host_base':'98499ec4ab9ad59d42f05c47e586ac0a507bb884',
        'canonical_pin':'83caceaca39712d1c84e4337a09b020b087125ae', 'settings':SETTINGS,
        'runtime_source_sha256':{path:digest((ROOT/path).read_bytes()) for path in
            ('src/lib/PromptGenerator.py','src/lib/ResponsePresentation.py','src/lib/SpeechPolicy.py','src/lib/Assistant.py',
             'vendor/tars-plugins/plugins/TARSChatter/TARSChatter.py',
             'vendor/tars-plugins/plugins/TARSChatter/TARSChatterSession.py',
             'vendor/tars-plugins/plugins/TARSExplorer/TARSExplorerSession.py',
             'vendor/tars-plugins/plugins/TARSNavigator/TARSNavigatorSession.py')},
        'encoding':encoding, 'token_note':'Serialized JSON token counts are a fixed-encoding proxy, not provider request/billed usage.',
        'model_calls':0, 'model_quality_comparison':'NOT EXECUTED',
        'factory':{arm:{'sha256':digest(value.encode()), 'words':len(value.split()), 'logical_lines':len(value.splitlines()), 'characters':len(value),
            'text_tokens':len(tokenizer.encode(value)) if tokenizer else None} for arm,value in prompts.items()},
        'requests_sha256':digest(requests), 'scenarios':rows,
        'limitations':['Main scenarios are pre-admitted generation snapshots, not a replay of action execution/admission.',
            'Tool set is current literal plugin schemas only, not the complete native host action catalogue.',
            'Prepared Chatter anchor/topic and memory retrieval are controlled synthetic inputs; actual preparer/Director code is unchanged.',
            'Runtime-only scenarios create no model requests and rely on existing integration tests, not a simulated model silence score.']}
    (output / 'requests.json').write_text(json.dumps(requests, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output / 'comparison.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


def review(manifest_path, requests_path, responses_path, output):
    """Import externally collected outputs with exact provenance; produce unscored blind pairs."""
    from lib.ResponsePresentation import is_silence_sentinel
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    requests = json.loads(requests_path.read_text(encoding='utf-8'))
    if digest(requests) != manifest['requests_sha256']:
        raise ValueError('Request bundle does not match manifest')
    expected = {r['request_sha256']:r for r in requests}
    responses = json.loads(responses_path.read_text(encoding='utf-8'))
    grouped, seen = {}, set()
    for response in responses:
        key = response['request_sha256']
        if key not in expected or key in seen or response['settings'] != manifest['settings']:
            raise ValueError('Unknown/duplicate request or mismatched model settings')
        seen.add(key)
        request = expected[key]
        if response.get('status') not in ('completed', 'error'):
            raise ValueError('An explicit completed/error status is required')
        text = response.get('text', '')
        if not isinstance(text, str) or not isinstance(response.get('tool_calls', []), list):
            raise ValueError('Invalid output shape')
        grouped.setdefault(request['scenario'], []).append((request['arm'], response))
    if seen != expected.keys():
        raise ValueError('Complete paired outputs are required; missing results cannot count as silence')
    lines, key_rows = ['# Blind paired review\n\nNo quality scores have been assigned.\n'], []
    for scenario in manifest['scenarios']:
        if scenario['path']=='runtime_only': continue
        pair = sorted(grouped[scenario['id']], key=lambda item:digest([scenario['id'], item[0]]))
        lines.append('## '+scenario['id']+'\n\n'+'\n'.join('- '+c for c in scenario['checks'])+'\n')
        for label, (arm, response) in zip(('A','B'), pair):
            lines.append(f"\n### {label} ({response['status']})\n\n{response.get('text','')}\n\nTool calls: {json.dumps(response.get('tool_calls', []))}\n")
            key_rows.append({'scenario':scenario['id'],'label':label,'arm':arm,'intentional_abstention':response['status']=='completed' and not response.get('tool_calls') and is_silence_sentinel(response.get('text','')),
                'output_chars':len(response.get('text','')), 'provider_usage':response.get('usage'), 'quality_scores':None})
    output.mkdir(parents=True, exist_ok=True)
    (output/'blind-review.md').write_text('\n'.join(lines), encoding='utf-8')
    (output/'review-key.json').write_text(json.dumps(key_rows,indent=2)+'\n', encoding='utf-8')
    return key_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--output-dir',type=Path,required=True)
    prep.add_argument('--encoding', help='Optional tiktoken encoding, e.g. o200k_base; never a billed-token claim')
    rev = sub.add_parser('review')
    for field in ('manifest','requests','responses','output-dir'): rev.add_argument('--'+field,type=Path,required=True)
    args = parser.parse_args()
    if args.command=='prepare':
        result=prepare(args.output_dir,args.encoding)
        print(json.dumps({'model_calls':0,'scenarios':len(result['scenarios']),'factory':result['factory']}))
    else:
        result=review(args.manifest,args.requests,args.responses,args.output_dir)
        print(json.dumps({'imported_responses':len(result),'quality_scores_assigned':False}))


if __name__=='__main__': main()
