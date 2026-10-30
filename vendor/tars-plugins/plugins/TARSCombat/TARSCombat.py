"""Quiet event-driven Combat V1. Controls live behind the host's permission gate."""
import json
import threading
import time
from pydantic import BaseModel
from lib.PluginBase import PluginBase
from lib.PluginHelper import PluginEvent
from .CombatState import CombatTracker
from .Commands import parse_order


class QueryArgs(BaseModel):
    topic: str = 'situation'


class TARSCombat(PluginBase):
    settings_config = {
        'key':'TARSCombat', 'label':'TARS Combat', 'icon':'shield',
        'grids':[{'key':'combat', 'label':'Tactical assistance', 'fields':[
            {'key':k, 'label':label, 'type':'toggle', 'default_value':default}
            for k,label,default in [
                ('enabled','Enable combat awareness',True),
                ('focus','Quiet optional speech during combat',True),
                ('alerts','Critical tactical alerts',True),
                ('fast_commands','Enable explicit fast control commands',False),
                ('experimental_launch','Allow experimental fighter launch UI (requires live validation)',False),
            ]]}]}

    def __init__(self, plugin_manifest):
        super().__init__(plugin_manifest)
        self.settings = {}
        self.tracker = CombatTracker()
        self.lock = threading.RLock()
        self.helper = None
        self.states = {}
        self.sent_alerts = set()
        self.stop = threading.Event()
        self.worker = None

    def on_chat_start(self, helper):
        self.helper = helper
        self.tracker = CombatTracker()
        self.sent_alerts.clear()
        register = getattr(helper, 'register_combat_provider', None)
        if not callable(register):
            raise RuntimeError('TARS Combat requires a compatible Combat V1 host')
        register(self)
        helper.update_combat_focus('idle', enabled=self.settings.get('enabled',True) and self.settings.get('focus',True))
        self.stop.clear()
        self.worker = threading.Thread(target=self._watch, name="TARSCombatClock", daemon=True)
        self.worker.start()
        helper.register_event('TARSCombatAlert', self.should_alert,
                              lambda event: 'Deterministic combat alert; do not narrate combat.')
        helper.register_action('tarsCombatQuery',
            'Read combat facts: topic situation, target, condition, wanted, bounty, subsystem, fighter, readiness, progress, report or latency. Missing/stale telemetry must remain unknown.',
            QueryArgs, self.query, action_type='read')

    def on_chat_stop(self, helper):
        self.stop.set()
        if self.worker is not None:
            self.worker.join(timeout=2)
        if self.helper:
            self.helper.unregister_combat_provider(self)
        self.helper = None

    def _watch(self):
        while not self.stop.wait(1):
            with self.lock:
                if self.helper is None:
                    return
                self.tracker.tick(time.time())
                phase = self.tracker.phase if self.settings.get('enabled',True) and self.settings.get('focus',True) else 'idle'
                self.helper.update_combat_focus(phase, enabled=self.settings.get('enabled',True) and self.settings.get('focus',True))

    def observe(self, event, states):
        if self.helper is None:
            return
        if not self.settings.get('enabled', True):
            self.helper.update_combat_focus('idle', enabled=False)
            return
        data = getattr(event, 'content', None) if event.kind == 'game' else getattr(event, 'status', None) if event.kind == 'status' else None
        with self.lock:
            self.states = {k:(v.model_dump() if hasattr(v,'model_dump') else v) for k,v in states.items()}
            now = time.time()
            if isinstance(data, dict):
                if data.get('event') in ('InDanger','OutofDanger') and 'timestamp' not in data:
                    data = {**data, 'timestamp':event.timestamp}
                self.tracker.consume(data, now, historic=getattr(event,'historic',False))
            self.tracker.tick(now)
            phase = self.tracker.phase if self.settings.get('focus',True) else 'idle'
            self.helper.update_combat_focus(phase, enabled=self.settings.get('enabled',True) and self.settings.get('focus',True))
            if self.settings.get('alerts',True):
                for alert in self.tracker.alerts:
                    key = (alert['code'], alert['created'])
                    if key not in self.sent_alerts:
                        self.sent_alerts.add(key)
                        self.helper.dispatch_event(PluginEvent(plugin_event_name='TARSCombatAlert',
                            plugin_event_content={'code':alert['code'], 'created':alert['created']}))
                self.sent_alerts = set(sorted(self.sent_alerts, key=lambda k:k[1])[-200:])

    parse_order = staticmethod(parse_order)

    def snapshot(self):
        with self.lock:
            return self.tracker.snapshot(time.time())

    def alert(self, data):
        with self.lock:
            if not self.settings.get('enabled',True) or not self.settings.get('alerts',True):
                return None
            now = time.time()
            self.tracker.tick(now)
            for alert in self.tracker.alerts:
                if (alert['code'],alert['created']) == (data.get('code'),data.get('created')):
                    return alert['text']
        return None

    def should_alert(self, event):
        return self.alert(event.plugin_event_content) is not None

    def query(self, args, context):
        if not self.settings.get('enabled',True):
            return json.dumps({'status':'Combat awareness is disabled.'})
        topic = args.topic.casefold()
        with self.lock:
            snapshot = self.tracker.snapshot(time.time())
            states = self.states
            if topic in ('target','condition','wanted','bounty','subsystem'):
                target = snapshot['target']
                if not target:
                    result = {'status':'No current target telemetry.'}
                elif target['stale']:
                    result = {'status':'Target telemetry is stale; current condition and identity unconfirmed.',
                              'age_seconds':target['age_seconds']}
                else:
                    result = dict(target, rule='Only returned fields are known. Missing fields are unavailable; never infer wanted status or bounty.')
                    if not target['scan_complete']:
                        result = {'status':'Incomplete target scan; identity, legal status and bounty may be unknown.',
                                  **{k:v for k,v in target.items() if k in ('Ship','ScanStage','at','age_seconds','scan_complete','stale')}}
            elif topic == 'fighter':
                result = {'fighters':snapshot['fighters'], 'vehicle':snapshot['vehicle'],
                          'status':'Hull is known only when HullDamage identifies a unique fighter; orders are not observable.'}
            elif topic == 'readiness':
                result = {'mothership':snapshot['mothership'], 'fighters':snapshot['fighters'],
                          'ship':states.get('ShipInfo',{}),
                          'loadout':states.get('Loadout',{}), 'modules':states.get('ModuleInfo',{}),
                          'status':'Module/loadout snapshots may be old; timestamps are source timestamps. No DPS/accuracy or own shield percentage is available.'}
            elif topic == 'latency':
                result = self.helper.combat_latency()
            elif topic in ('report','progress'):
                def digest(record):
                    if record is None:
                        return None
                    result = {k:v for k,v in record.items() if k not in ('targets','transitions')}
                    result['targets_observed'] = list(record['targets'].values())[-8:]
                    result['important_transitions'] = record['transitions'][-10:]
                    return result
                result = {'session':snapshot['session'], 'encounter':digest(snapshot['encounter']),
                          'recent_encounters':[digest(r) for r in snapshot['recent_encounters'][-3:]],
                          'limitations':snapshot['limitations']}
                result['report_rule'] = 'Give a brief factual report on request. Intervals are not individual fights. Bounty awards are not guaranteed solo kills.'
            else:
                result = {k:v for k,v in snapshot.items() if k not in ('recent_encounters','encounter')}
                result['encounter_active'] = snapshot['encounter'] is not None
        return json.dumps(result, ensure_ascii=False)
