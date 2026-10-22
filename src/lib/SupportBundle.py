"""Allowlisted support export: no raw config, free-text logs, prompt or memory."""
import base64
import io
import json
import platform
import os
import re
from pathlib import Path
import zipfile
from .TarsProviderRegistry import TARS_PROVIDER_SPECS

COMPONENTS = {'backend','models','stt','tts','audio','memory','vision','plugins','provider-installation','elite-journal','elite-status'}
STATES = {'ready','available','busy','unavailable','error','unknown'}

def provider_summary(config):
    result = {}
    for kind in ('llm','agent_llm','vision','stt','tts','embedding'):
        selected = config.get(kind+'_provider', '')
        spec = next((s for s in TARS_PROVIDER_SPECS if selected == f'plugin:{s.guid}:{s.provider_id}'), None)
        label = spec.label if spec else {'openai':'OpenAI','openrouter':'OpenRouter','edge-tts':'Edge TTS','none':'Disabled'}.get(selected,'Custom provider')
        result[kind] = {'name':label,'approved_package_version':spec.version if spec else None}
    return result

BEHAVIOR_DIRS=('TARSExplorer','TARSNavigator','TARSGalaxy','TARSChatter','TARSExpedition','TARSObservatoryBridge')
def behavior_summary():
    root=Path(os.environ.get('TARS_BUNDLED_RESOURCES') or Path(__file__).resolve().parents[2]/'vendor'/'tars-plugins')
    result=[]
    for folder in BEHAVIOR_DIRS:
        try:
            manifest=json.loads((root/'plugins'/folder/'manifest.json').read_text(encoding='utf-8'))
            version=manifest.get('version')
            if not isinstance(version,str) or not re.fullmatch(r'[0-9A-Za-z.+-]{1,32}',version):version='not reported'
        except (OSError,ValueError):version='not reported'
        result.append({'name':folder,'bundled_version':version})
    return result

def build_support_bundle(config, snapshot):
    # Treat the renderer as untrusted; copy only enums/counts, never arbitrary text.
    health = [{'component':h['component'],'status':h['status']} for h in snapshot.get('health',[])[:32]
              if isinstance(h,dict) and h.get('component') in COMPONENTS and h.get('status') in STATES]
    build = snapshot.get('commit','')
    build = build if isinstance(build,str) and len(build) in (7,40) and all(c in '0123456789abcdef' for c in build.lower()) else 'not reported'
    count = snapshot.get('missing_keybinds')
    count = count if type(count) is int and 0 <= count <= 10000 else None
    config_schema = config.get('config_version')
    config_schema = config_schema if type(config_schema) is int and 0 <= config_schema <= 10000 else None
    profile_version = config.get('tars_profile_version')
    profile_version = profile_version if type(profile_version) is int and 0 <= profile_version <= 10000 else None
    info = {'format_version':1,'frontend_commit':build,'os':platform.system(),'os_release':platform.release(),
            'python':platform.python_version(),'config_schema':config_schema,
            'profile_version':profile_version,'providers':provider_summary(config),
            'behavior_plugins':behavior_summary(),
            'health':health,'missing_keybinds':count,
            'observatory':'Feed diagnostics not exported; optional availability requires local inspection.',
            'self_check':'FAILED' if any(h['status']=='error' and h['component'] in {'backend','models','stt','tts','memory'} for h in health) else 'WARNING' if not health or count or any(h['status']!='ready' for h in health) else 'READY'}
    # No log text crosses this boundary. Preserve severity counts only.
    counts = {level: min(max(snapshot.get('log_counts',{}).get(level,0),0),1000000)
              if type(snapshot.get('log_counts',{}).get(level,0)) is int else 0
              for level in ('debug','info','warn','error')}
    recent=[]
    for entry in snapshot.get('log_entries',[])[:100]:
        if not isinstance(entry,dict) or entry.get('level') not in ('debug','info','warn','error'):
            continue
        stamp=entry.get('timestamp','')
        if not isinstance(stamp,str) or not re.fullmatch(r'[0-9TZ:.+\-]{10,40}',stamp):
            continue
        recent.append({'timestamp':stamp,'level':entry['level'],'message':'[redacted]'})
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('runtime.json',json.dumps(info,indent=2))
        archive.writestr('log-summary.json',json.dumps(counts,indent=2))
        archive.writestr('recent-logs.jsonl',''.join(json.dumps(entry)+'\n' for entry in recent))
        archive.writestr('README.txt','TARS support snapshot. No raw log text, config, prompt, memory, conversations, paths or credentials are included. Provider versions are approved package versions, not proof of installation. Health reflects reported state, not physical device validation. Observatory file/cursor details are intentionally omitted.\n')
    return base64.b64encode(data.getvalue()).decode('ascii')

def handle_support_command(config, data, emit):
    try:
        payload=build_support_bundle(config,data.get('snapshot') if isinstance(data.get('snapshot'),dict) else {})
        emit('export_diagnostics_result',request_id=data.get('request_id'),success=True,data=payload)
    except Exception:
        emit('export_diagnostics_result',request_id=data.get('request_id'),success=False)
