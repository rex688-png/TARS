"""Conservative, host-owned admission; identities and payloads never enter logs.

Recent entries are bounded generation-attempt leases, NOT spoken acknowledgements.
Unknown identities fail open. Domain interpretation remains in the plugins.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from time import monotonic, time
from uuid import uuid4
import json

from .Event import ConversationEvent, GameEvent, PluginEvent, StatusEvent, ToolEvent
from . import SpeechTrace

SOURCES = {'TARSExplorerTarget': 'explorer', 'TARSObservatoryFact': 'observatory',
           'TARSNavigatorTarget': 'navigator', 'TARSChatter': 'chatter'}
PRIORITY = {'user': 100, 'tool': 100, 'native': 80, 'explorer': 60,
            'observatory': 60, 'navigator': 40, 'chatter': 10, 'other': 50}
MODES = ('off', 'observe', 'enforce')
ALIASES = {'Earthlike body': 'earth_like_world', 'Water world': 'water_world',
           'Ammonia world': 'ammonia_world'}
KINDS = {'earth_like_world', 'water_world', 'ammonia_world', 'terraformable',
         'dss_complete', 'body_discovery', 'organic_sample', 'organic_complete',
         'biology_body_complete'}
META = {'_guard', 'timestamp', 'event_id', 'id', 'source_plugin', 'fact_type',
        'realtime', 'monitor_mode', 'batch', 'system', 'StarSystem', 'SystemAddress',
        'system_address', 'body', 'BodyName', 'BodyID', 'body_id', 'finding_type',
        'callout_kind', 'stage', 'sample', 'species', 'genus', 'variant'}


def source(event):
    if isinstance(event, ConversationEvent) and event.kind == 'user':
        return 'user'
    if isinstance(event, ToolEvent):
        return 'tool'
    if isinstance(event, PluginEvent):
        return SOURCES.get(event.plugin_event_name, 'other')
    return 'native' if isinstance(event, (GameEvent, StatusEvent)) else 'other'


def state_dict(states, name):
    value = states.get(name, {})
    value = value.model_dump() if hasattr(value, 'model_dump') else value
    return value if isinstance(value, dict) else {}


def _text(value):
    return str(value).strip().casefold() if value is not None else ''


def _scope(data, guard):
    address = data.get('system_address', data.get('SystemAddress', guard.get('system_address')))
    name = data.get('system', data.get('StarSystem', guard.get('system', guard.get('current_system'))))
    return (('address', str(address)) if isinstance(address, int) and not isinstance(address, bool) and address > 0
            else ('name', _text(name)) if isinstance(name, str) and _text(name) not in ('', 'unknown', 'none') else None)


def identity_and_facts(event):
    if not isinstance(event, PluginEvent) or source(event) not in ('explorer', 'observatory'):
        return None, frozenset()
    data = event.plugin_event_content
    if not isinstance(data, dict):
        return None, frozenset()
    guard = data.get('_guard') if isinstance(data.get('_guard'), dict) else {}
    system = _scope(data, guard)
    body_id = data.get('body_id', data.get('BodyID'))
    body = (('id', str(body_id)) if isinstance(body_id, int) and not isinstance(body_id, bool) and body_id >= 0
            else ('name', _text(data.get('body', data.get('BodyName')))))
    kind = data.get('finding_type')
    if not kind and source(event) == 'explorer':
        kind = data.get('callout_kind')
        if kind == 'scan_value':
            planet_class = data.get('planet_class')
            kind = ALIASES.get(planet_class) if isinstance(planet_class, str) else None
    if not kind and source(event) == 'observatory':
        # notification:BioInsights identifies a provider, NOT a particular finding.
        kind = str(data.get('fact_type', '')).removeprefix('notification:')
    if not system or body[1] in ('', 'unknown', 'unknown body', 'none') or not isinstance(kind, str) or kind not in KINDS:
        return None, frozenset()
    organism = tuple(_text(data.get(k)) for k in ('species', 'genus', 'variant'))
    stage = data.get('stage', data.get('sample'))
    if kind.startswith('organic') and (not (organism[0] or organism[2]) or
                                         (kind == 'organic_sample' and stage not in (1, 2, 3))):
        return None, frozenset()
    # Every non-routing field participates. Unknown/additional facts fail open.
    facts = {k: v for k, v in data.items() if k not in META}
    if isinstance(facts.get('planet_class'), str) and ALIASES.get(facts['planet_class']) == kind:
        facts.pop('planet_class')
    try:
        tokens = frozenset((k, json.dumps(v, sort_keys=True, ensure_ascii=True)) for k, v in facts.items())
    except (ValueError, TypeError, RecursionError):
        return None, frozenset()
    return (system, body, kind, organism, str(stage)), tokens


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str
    source: str
    priority: int
    optional: bool


@dataclass
class Admission:
    allowed: bool
    decisions: list[tuple[object, Decision]] = field(default_factory=list)
    token: str | None = None
    epoch: int = 0
    claims: dict = field(default_factory=dict)


class SpeechArbiter:
    def __init__(self, clock=monotonic, wall_clock=time, attempt_window=8.0):
        self.clock, self.wall_clock = clock, wall_clock
        self.attempt_window = attempt_window
        self._lock = RLock()
        self._recent = {}
        self._active = None
        self._epoch = 0
        self._mode = None
        self._location = {}
        self._scope_since = None
        self._abort_revision = None

    def note_cancellation(self, revision):
        if not isinstance(revision, int) or isinstance(revision, bool):
            return
        with self._lock:
            if self._abort_revision is not None and revision != self._abort_revision:
                self._recent.clear()
                self._epoch += 1
            self._abort_revision = revision

    def note_event(self, event):
        with self._lock:
            if isinstance(event, GameEvent) and event.content.get('event') in ('FSDJump', 'Location', 'CarrierJump'):
                self._epoch += 1
                self._location = dict(event.content)
                try:
                    stamp = event.content.get('timestamp', event.timestamp)
                    stamp = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                    self._scope_since = min(stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).timestamp(),
                                            self.wall_clock())
                except (ValueError, TypeError, AttributeError):
                    self._scope_since = self.wall_clock()
                self._recent.clear()
            if source(event) == 'user' or getattr(event, 'kind', '') == 'user_speaking':
                self._epoch += 1
                self._recent.clear()

    def _freshness(self, event, states):
        data = (event.content if isinstance(event, GameEvent) else event.status
                if isinstance(event, StatusEvent) else getattr(event, 'plugin_event_content', {}))
        data = data if isinstance(data, dict) else {}
        guard = data.get('_guard') if isinstance(data.get('_guard'), dict) else {}
        location = self._location or state_dict(states, 'Location')
        event_scope = _scope(data, guard)
        current_scope = _scope(location, {})
        if event_scope and current_scope and event_scope[0] == current_scope[0] and event_scope != current_scope:
            return 'wrong_system'
        stamp = guard.get('triggered_at')
        if not isinstance(stamp, (int, float)):
            try:
                stamp = datetime.fromisoformat(data.get('timestamp', event.timestamp).replace('Z', '+00:00'))
                stamp = stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).timestamp()
            except (ValueError, TypeError, AttributeError):
                return None  # Unknown freshness is not evidence of staleness.
        age = self.wall_clock() - stamp
        if self._scope_since is not None and stamp < self._scope_since:
            return 'before_location_change'
        return 'stale' if age > 60 or age < -5 else None

    def configure(self, mode):
        mode = mode if mode in MODES else 'observe'
        with self._lock:
            if mode != self._mode:
                self._recent.clear()
                self._mode = mode
                self._epoch += 1
        return mode

    def reserve(self, events, states, mode='observe'):
        with self._lock:
            mode = self.configure(mode)
            if mode == 'off':
                return Admission(True)
            now = self.clock()
            self._recent = {k: v for k, v in self._recent.items() if v[1] > now}
            direct = any(source(e) in ('user', 'tool') for e in events)
            claims = {}
            decisions = []
            for event in sorted(events, key=lambda e: -PRIORITY[source(e)]):
                origin = source(event)
                reason = 'direct_request' if direct else self._freshness(event, states)
                key, facts = (None, frozenset()) if direct else identity_and_facts(event)
                if not direct and not reason:
                    if self._active is not None:
                        reason = 'busy'
                    elif key is not None and key in claims and facts <= claims[key]:
                        reason = 'same_batch_duplicate'
                    elif key is not None and key in self._recent and facts <= self._recent[key][0]:
                        reason = 'recent_attempt'
                accepted = reason in (None, 'direct_request')
                reason = reason or ('unidentified' if key is None else 'new_facts')
                decision = Decision(accepted, reason, origin, PRIORITY[origin], origin == 'chatter')
                decisions.append((event, decision))
                SpeechTrace.observe_event('speech_admission', event, mode=mode, proposed=accepted,
                                          reason=reason, source=origin, priority=decision.priority,
                                          optional=decision.optional, enforced=mode == 'enforce')
                if accepted and key is not None:
                    claims[key] = claims.get(key, frozenset()) | facts
            proposed = any(d.accepted for _, d in decisions)
            token = uuid4().hex if proposed and not direct and self._active is None else None
            if token:
                self._active = token
            return Admission(mode != 'enforce' or proposed, decisions, token, self._epoch, claims)

    def finish(self, admission, evidence='unknown'):
        if admission is None or admission.token is None:
            return
        with self._lock:
            if self._active != admission.token:
                return
            self._active = None
            # A short cost-control lease; never a persisted "announced" flag.
            # Unknown completion, failure, dropped/aborted audio release the claim.
            if evidence == 'output_written' and admission.epoch == self._epoch and self._mode != 'off':
                now = self.clock()
                until = now + self.attempt_window
                for key, facts in admission.claims.items():
                    old_facts, expires = self._recent.get(key, (frozenset(), 0))
                    previous = old_facts if expires > now else frozenset()
                    self._recent[key] = (previous | facts, until)
                while len(self._recent) > 128:
                    self._recent.pop(next(iter(self._recent)))

    def preview_optional(self, states, mode='observe'):
        """Advisory pre-generation seam for PR 3; no Chatter migration/reservation."""
        with self._lock:
            accepted = self._active is None
        SpeechTrace.emit('speech_admission_preview', source='chatter', mode=mode,
                         proposed=accepted, reason='available' if accepted else 'busy')
        return mode != 'enforce' or accepted
