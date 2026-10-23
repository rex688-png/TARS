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
from .SpeechPolicy import routine_first_discovery_tally
from .ExplorationSpeech import DeliveryLedger, SOURCES as EXPLORATION_SOURCES

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


@dataclass
class OptionalAdmission:
    token: str
    mode: str
    epoch: int
    deadline: float
    triggered_at: float
    allowed: bool
    state: str = 'preparing'


class SpeechArbiter:
    def __init__(self, clock=monotonic, wall_clock=time, attempt_window=8.0):
        self.clock, self.wall_clock = clock, wall_clock
        self.attempt_window = attempt_window
        self._lock = RLock()
        self._recent = {}
        self._delivery_ledger = DeliveryLedger()
        self._active = None
        self._epoch = 0
        self._mode = None
        self._location = {}
        self._scope_since = None
        self._abort_revision = None
        self._optional = {}

    def note_cancellation(self, revision):
        if not isinstance(revision, int) or isinstance(revision, bool):
            return
        with self._lock:
            if self._abort_revision is not None and revision != self._abort_revision:
                self._recent.clear()
                self._epoch += 1
                self.cancel_optional('cancelled')
            self._abort_revision = revision

    def note_event(self, event):
        with self._lock:
            if source(event) in ('user', 'tool', 'explorer', 'observatory', 'navigator') or getattr(event, 'kind', '') == 'user_speaking':
                self.cancel_optional('higher_priority')
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
                self.cancel_optional('location_changed')
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
                self.cancel_optional('mode_changed')
        return mode

    def reserve(self, events, states, mode='observe'):
        with self._lock:
            mode = self.configure(mode)
            if mode == 'off':
                return Admission(True)
            now = self.clock()
            self._recent = {k: v for k, v in self._recent.items() if v[1] > now}
            direct = any(source(e) in ('user', 'tool') for e in events)
            if direct or any(source(e) not in ('chatter', 'other') for e in events):
                self.cancel_optional('higher_priority')
            claims = {}
            decisions = []
            for event in sorted(events, key=lambda e: -PRIORITY[source(e)]):
                origin = source(event)
                reason = 'direct_request' if direct else self._freshness(event, states)
                # A distinct first-discovery tally at every jump is still
                # routine chatter, not a new scientific finding. Keep the
                # event in history, but decline standalone generation.
                if not direct and origin == 'observatory' and routine_first_discovery_tally(event):
                    reason = reason or 'routine_discovery_tally'
                key, facts = (None, frozenset()) if direct else identity_and_facts(event)
                if not direct and not reason:
                    optional_token = (event.plugin_event_content.get('_speech_admission')
                                      if isinstance(event, PluginEvent) and isinstance(event.plugin_event_content, dict) else None)
                    if origin == 'chatter' and optional_token and not self.optional_event_valid(optional_token):
                        reason = 'optional_cancelled'
                    elif self._active is not None:
                        reason = 'busy'
                    elif key is not None and key in claims and facts <= claims[key]:
                        reason = 'same_batch_duplicate'
                    elif key is not None and key in self._recent and facts <= self._recent[key][0]:
                        reason = 'recent_attempt'
                accepted = reason in (None, 'direct_request')
                reason = reason or ('unidentified' if key is None else 'new_facts')
                decision = Decision(accepted, reason, origin, PRIORITY[origin], origin == 'chatter')
                decisions.append((event, decision))
                if mode == 'enforce' and not accepted and origin == 'chatter':
                    data = event.plugin_event_content
                    if isinstance(data, dict):
                        self.discard_optional(data.get('_speech_admission'))
                SpeechTrace.observe_event('speech_admission', event, mode=mode, proposed=accepted,
                                          reason=reason, source=origin, priority=decision.priority,
                                          optional=decision.optional, enforced=mode == 'enforce')
                if accepted and key is not None:
                    claims[key] = claims.get(key, frozenset()) | facts
            proposed = any(d.accepted for _, d in decisions)
            token = uuid4().hex if proposed and not direct and self._active is None else None
            for event, decision in decisions:
                if token and decision.accepted and decision.source == 'chatter':
                    data = event.plugin_event_content
                    lease = self._optional.get(data.get('_speech_admission')) if isinstance(data, dict) else None
                    if lease is not None and lease.state == 'dispatched':
                        token = lease.token
                        lease.state = 'consumed'
            if token:
                self._active = token
            return Admission(mode != 'enforce' or proposed, decisions, token, self._epoch, claims)

    def exploration_candidates(self, events, states):
        with self._lock:
            fresh = []
            for event in events:
                if (isinstance(event, PluginEvent) and event.plugin_event_name in EXPLORATION_SOURCES
                        and self._freshness(event, states)):
                    SpeechTrace.observe_event('speech_eligibility', event, disposition='update', reason='stale_source')
                else:
                    fresh.append(event)
            selected, claims = self._delivery_ledger.select(fresh)
            return selected, claims, self._epoch

    def confirm_exploration(self, claims, epoch, terminal, events, text):
        with self._lock:
            if (epoch == self._epoch and getattr(terminal, 'outcome', None) == 'completed'
                    and getattr(terminal, 'output_written', False) is True):
                self._delivery_ledger.confirm(self._delivery_ledger.covered(claims, events, text))

    def exploration_still_current(self, events, states, epoch):
        with self._lock:
            return epoch == self._epoch and all(
                not self._freshness(event, states) for event in events
                if isinstance(event, PluginEvent) and event.plugin_event_name in EXPLORATION_SOURCES)

    def current_epoch(self):
        with self._lock:
            return self._epoch

    def finish(self, admission, evidence='unknown'):
        if admission is None or admission.token is None:
            return
        with self._lock:
            self._optional.pop(admission.token, None)
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
        """Legacy advisory preview, retained for older plugin callers."""
        with self._lock:
            accepted = self._active is None
        SpeechTrace.emit('speech_admission_preview', source='chatter', mode=mode,
                         proposed=accepted, reason='available' if accepted else 'busy')
        return mode != 'enforce' or accepted

    def cancel_optional(self, reason='cancelled'):
        with self._lock:
            if self._optional:
                SpeechTrace.emit('optional_cancelled', reason=reason, count=len(self._optional))
            self._optional.clear()

    def _optional_reason(self, lease, busy=False):
        if self._optional.get(lease.token) is not lease or lease.epoch != self._epoch:
            return 'cancelled'
        if self.clock() >= lease.deadline or not -5 <= self.wall_clock() - lease.triggered_at <= 60:
            return 'stale'
        if busy or (self._active is not None and self._active != lease.token):
            return 'higher_priority'
        return None

    def begin_optional(self, triggered_at, mode='observe', busy=False):
        with self._lock:
            mode = self.configure(mode)
            self._optional = {k: v for k, v in self._optional.items()
                              if v.deadline > self.clock() and v.epoch == self._epoch}
            reason = ('stale' if not -5 <= self.wall_clock() - triggered_at <= 60 else
                      'busy' if busy or self._active is not None or self._optional else None)
            lease = OptionalAdmission(uuid4().hex, mode, self._epoch, self.clock() + 60,
                                      triggered_at, mode != 'enforce' or reason is None)
            if lease.allowed and mode != 'off':
                self._optional[lease.token] = lease
            SpeechTrace.emit('optional_reserved', reservation_id=lease.token, mode=mode,
                             proposed=reason is None, reason=reason or 'available')
            return lease

    def optional_valid(self, lease, busy=False):
        with self._lock:
            reason = self._optional_reason(lease, busy)
            SpeechTrace.emit('optional_revalidated', reservation_id=lease.token, mode=lease.mode,
                             proposed=reason is None, reason=reason or 'available')
            return lease.mode != 'enforce' or reason is None

    def optional_event_valid(self, token):
        with self._lock:
            lease = self._optional.get(token)
            return (lease is not None and lease.state in ('dispatched', 'consumed')
                    and self._optional_reason(lease) is None)

    def discard_optional(self, token):
        with self._lock:
            self._optional.pop(token, None)

    def dispatch_optional(self, lease, busy, dispatch):
        with self._lock:
            if not self.optional_valid(lease, busy()):
                return False
            lease.state = 'dispatched'
            try:
                dispatch(lease.token if lease.mode == 'enforce' else None)
            except Exception:
                self._optional.pop(lease.token, None)
                raise
            return True

    def release_optional(self, lease):
        with self._lock:
            # A dispatched enforce ticket is owned by Assistant until completion.
            if lease.mode != 'enforce' or lease.state == 'preparing':
                self._optional.pop(lease.token, None)
            SpeechTrace.emit('optional_released', reservation_id=lease.token, mode=lease.mode)
