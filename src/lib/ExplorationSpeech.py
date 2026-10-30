"""Deterministic eligibility and evidence identities, independent of rollout mode.

Record/update means context remains stored; only an announcement spends a model
call. Unknown producers/identities fail open unless positively routine. No text,
body names, measurements or private prompts are emitted by this module.
"""
from dataclasses import dataclass
import re
import json

from .Event import PluginEvent

SOURCES = {'TARSExplorerTarget', 'TARSObservatoryFact'}
WORLD = {'Earthlike body': 'earth_like_world', 'Earth-like world': 'earth_like_world',
         'Water world': 'water_world', 'Ammonia world': 'ammonia_world'}
KINDS = set(WORLD.values()) | {'terraformable', 'dss_complete', 'organic_complete',
                             'organic_sample', 'biology_body_complete', 'biology'}
ROUTINE = re.compile(r'\b(?:personal (?:best|record|minimum|maximum)|(?:temperature|rotational?|orbital?) record|discovery (?:count|total)|\d+ (?:discoveries|systems discovered)|atmospheric composition|landability|probe efficiency)\b', re.I)
IMPORTANT = re.compile(r'\b(?:earth[- ]?like|water world|terraformable|ammonia world|biolog\w*|genus|species|codex|rare|exceptional|galactic record|safety|danger)\b', re.I)

@dataclass(frozen=True)
class Eligibility:
    disposition: str
    reason: str
    facts: frozenset = frozenset()


def evidence(data):
    """Known significant facts only; unrelated or uncertain IDs are never inferred."""
    facts = set()
    kind = data.get('finding_type', data.get('callout_kind'))
    kind = kind if isinstance(kind, str) else None
    if kind == 'system_complete':
        # Completion belongs to the system, not a fictitious body. Counts carry
        # their actual values so a revised census is new evidence.
        facts.add(('fss_complete', True))
        count = data.get('body_count')
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            facts.add(('body_count', count))
        for field in ('earth_like_worlds', 'water_worlds', 'ammonia_worlds',
                      'terraformable_bodies', 'bodies_with_biology', 'total_biological_signals'):
            value = data.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                facts.add((field, value))
        composition = data.get('system_composition')
        if isinstance(composition, dict) and composition.get('composition_confirmed') is True:
            for field in ('stars', 'planets', 'moons', 'belt_clusters'):
                value = composition.get(field)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    facts.add(('composition_' + field, value))
    planet_class = data.get('planet_class')
    world = WORLD.get(planet_class) if isinstance(planet_class, str) else None
    if world:
        facts.add(('world', world))
    if kind in set(WORLD.values()):
        facts.add(('world', kind))
    if data.get('terraformable') is True or kind == 'terraformable':
        facts.add(('terraformable', True))
    if kind == 'dss_complete' or data.get('dss_mapped') is True:
        facts.add(('dss', True))
    genera = data.get('confirmed_genuses', [])
    if isinstance(genera, list):
        facts.update(('genus', g.strip().casefold()) for g in genera if isinstance(g, str) and g.strip())
    if kind in ('organic_complete', 'organic_sample'):
        species = data.get('species') or data.get('variant')
        stage = data.get('stage', data.get('sample'))
        if isinstance(species, str) and species and (kind == 'organic_complete' or stage in (1, 2, 3)):
            facts.add(('organism', (species.casefold(), str(data.get('variant') or '').casefold(), 'complete' if kind == 'organic_complete' else stage)))
    completions = data.get('organic_completions', [])
    if isinstance(completions, list):
        for item in completions:
            if isinstance(item, dict) and isinstance(item.get('species'), str) and item['species']:
                facts.add(('organism', (item['species'].casefold(), str(item.get('variant') or '').casefold(), 'complete')))
    if kind == 'biology_body_complete' and facts:
        facts.add(('biology_complete', True))
    if data.get('landable') is True and isinstance(data.get('biological_signals'), int) and data['biological_signals'] >= 2:
        facts.add(('bio_signals', data['biological_signals']))
    if (data.get('exceptional') is True and isinstance(data.get('significance_reason'), str) and data['significance_reason'].strip()
            and isinstance(data.get('value'), (int, float)) and not isinstance(data['value'], bool)):
        facts.add(('science', (str(data.get('metric', '')), data['value'], data['significance_reason'])))
    # Unrecognized structured evidence must not be mistaken for a duplicate.
    # Ignore only known routing, descriptive and already-normalized fields.
    known = {'_guard','_speech_admission','timestamp','event_id','id','source_plugin','fact_type',
             'realtime','monitor_mode','batch','system','StarSystem','SystemAddress','system_address',
             'body','BodyName','BodyID','body_id','body_name','finding_type','callout_kind',
             'planet_class','terraformable','landable','dss_mapped','biological_signals',
             'confirmed_genuses','organic_completions','species','genus','variant','stage','sample',
             'reasons','exceptional_properties','distance_from_arrival_ls','title','message','text',
             'description','summary','notification','probes_used','efficiency_target','efficiency_bonus_met'}
    if kind == 'system_complete':
        known |= {'fss_complete', 'body_count', 'body_count_source', 'discovery_body_count',
                  'count_changed_since_discovery', 'system_composition', 'dss_mapped_bodies',
                  'all_planetary_bodies_dss_mapped', 'earth_like_worlds', 'water_worlds',
                  'ammonia_worlds', 'terraformable_bodies', 'bodies_with_biology',
                  'total_biological_signals'}
        # Empty recommendations carry no new discovery. Nonempty/unrecognized
        # details stay fail-open; completion alone cannot acknowledge them.
        known |= {k for k in ('remaining_noteworthy_targets', 'mapping_recommendation') if not data.get(k)}
        recommendation = data.get('mapping_recommendation')
        if isinstance(recommendation, dict) and recommendation.get('body') is None and not recommendation.get('reasons'):
            known.add('mapping_recommendation')
    if facts:
        for key, value in data.items():
            if key not in known:
                try:
                    facts.add(('additional:' + key, json.dumps(value, sort_keys=True)))
                except (ValueError, TypeError, RecursionError):
                    return frozenset()  # Cannot prove equivalence.
    return frozenset(facts)


def eligibility(event):
    if not isinstance(event, PluginEvent) or event.plugin_event_name not in SOURCES:
        return Eligibility('announce', 'outside_exploration_policy')
    data = event.plugin_event_content
    if not isinstance(data, dict):
        return Eligibility('announce', 'unknown_payload')
    facts = evidence(data)
    kind = data.get('finding_type', data.get('callout_kind'))
    kind = kind if isinstance(kind, str) else None
    if data.get('test') or data.get('warning_trigger') or kind == 'early_departure_warning':
        return Eligibility('announce', 'explicit_test_or_warning', facts)
    text = ' '.join(data.get(key, '') for key in ('title','message','text','description','summary','metric','record_type') if isinstance(data.get(key), str))
    exceptional = any(f[0] == 'science' for f in facts)
    if not exceptional and (kind in ('atmosphere', 'landability', 'personal_record', 'discovery_count') or ROUTINE.search(text) and not IMPORTANT.search(text)):
        return Eligibility('record', 'routine_observatory_record', facts)
    if facts - {('dss', True)}:
        return Eligibility('announce', 'significant_finding', facts)
    if kind == 'dss_complete':
        if data.get('planet_class') and data.get('terraformable') is False and data.get('efficiency_bonus_met') is not False:
            return Eligibility('record', 'routine_mapping', facts)
        # Ambiguous/legacy DSS observations still fail open: they may be important.
        # Known routine records below are positively identified, never guessed.
        return Eligibility('announce', 'mapping_milestone', facts)
    if kind == 'system_complete':
        return Eligibility('announce', 'system_milestone')
    if kind in ('organic_complete', 'organic_sample', 'biology_body_complete'):
        return Eligibility('announce', 'biology_identity_incomplete', facts)
    return Eligibility('announce', 'unclassified_fail_open', facts)


class DeliveryLedger:
    """Session-local, bounded evidence of completed audio output, not generation.

    No persistence, TTL-based "heard" claims or guessed body aliasing. Aliases are
    learned only when one event explicitly supplies both system and body IDs/names.
    """
    def __init__(self):
        self.delivered = {}
        self.aliases = {}

    def clear(self):
        self.delivered.clear()
        self.aliases.clear()

    def _remember_alias(self, alias, key):
        self.aliases[alias] = key
        while len(self.aliases) > 2048:
            self.aliases.pop(next(iter(self.aliases)))

    def entity(self, event):
        if not isinstance(event, PluginEvent) or event.plugin_event_name not in SOURCES:
            return None
        data = event.plugin_event_content
        if not isinstance(data, dict):
            return None
        guard = data.get('_guard')
        guard = guard if isinstance(guard, dict) else {}
        address = data.get('SystemAddress', data.get('system_address', guard.get('system_address')))
        system = data.get('system', data.get('StarSystem', guard.get('system')))
        system_name = system.strip().casefold() if isinstance(system, str) else ''
        if isinstance(address, int) and not isinstance(address, bool) and address > 0:
            scope = ('address', address)
            if system_name and system_name not in ('unknown', 'none'):
                alias = ('system', system_name)
                previous = self.aliases.get(alias, scope)
                self._remember_alias(alias, scope if previous == scope else None)
        elif isinstance(system, str) and system.strip().casefold() not in ('', 'unknown', 'none'):
            scope = self.aliases.get(('system', system_name), ('name', system_name))
            if scope is None:
                return None
        else:
            return None
        if data.get('finding_type', data.get('callout_kind')) == 'system_complete':
            return (scope, ('system', 'fss_complete'))
        body_id = data.get('BodyID', data.get('body_id'))
        names = [data.get(k) for k in ('body', 'BodyName', 'body_name')]
        names = [n.strip().casefold() for n in names if isinstance(n, str) and n.strip().casefold() not in ('', 'unknown', 'none', 'unknown body')]
        if isinstance(body_id, int) and not isinstance(body_id, bool) and body_id >= 0:
            key = (scope, ('id', body_id))
            for name in names:
                alias = (scope, name)
                # Conflicting explicit IDs invalidate an alias; never combine bodies.
                previous = self.aliases.get(alias, key)
                self._remember_alias(alias, key if previous == key else None)
        elif names:
            alias = (scope, names[0])
            if alias in self.aliases:
                return self.aliases[alias]
            key = (scope, ('name', names[0]))
        else:
            return None
        return key

    def select(self, events):
        allowed, claims = [], {}
        from . import SpeechTrace
        for event in events:
            result = eligibility(event)
            key = self.entity(event)
            reason, disposition = result.reason, result.disposition
            topic_facts = result.facts
            data = getattr(event, 'plugin_event_content', {})
            kind = data.get('finding_type', data.get('callout_kind')) if isinstance(data, dict) else None
            if isinstance(kind, str) and kind in ('organic_complete', 'organic_sample', 'biology_body_complete'):
                topic_facts = frozenset(f for f in result.facts if f[0] in ('organism', 'biology_complete'))
                if not topic_facts:
                    key = None  # World metadata cannot identify an unknown organism.
            elif kind == 'biology':
                topic_facts = frozenset(f for f in result.facts if f[0] in ('genus', 'bio_signals'))
                if not topic_facts:
                    key = None
            known = self.delivered.get(key, frozenset()) | claims.get(key, frozenset()) if key else frozenset()
            if key and topic_facts and topic_facts <= known:
                disposition, reason = 'update', 'equivalent_facts'
            elif key and known and topic_facts - known == {('dss', True)}:
                disposition, reason = 'update', 'routine_mapping_update'
            SpeechTrace.observe_event('speech_eligibility', event, disposition=disposition, reason=reason,
                                      identified=key is not None, fact_count=len(result.facts))
            if disposition == 'announce':
                allowed.append(event)
                if key and result.facts:
                    claims[key] = claims.get(key, frozenset()) | result.facts
        return allowed, claims

    def covered(self, claims, events, text):
        """Commit only explicit facts in the final output, not every prompt fact.

        Conservative lexical evidence is used only *after* semantic event identity
        is established. Unknown fields/ambiguous multi-body prose stay fail-open.
        Text is inspected in memory, never persisted or logged here.
        """
        covered = {}
        paragraphs = re.split(r'(?<=[.!?])\s+|\n+', text.casefold())
        for key, facts in claims.items():
            if len(claims) == 1:
                passage = text.casefold()
            else:
                labels = []
                for event in events:
                    if self.entity(event) == key:
                        data = event.plugin_event_content
                        fields = ('system', 'StarSystem') if key[1] == ('system', 'fss_complete') else ('body', 'body_name', 'BodyName')
                        labels.extend(data.get(k) for k in fields if isinstance(data.get(k), str))
                passages = [p for p in paragraphs if any(re.search(r'(?<!\w)' + re.escape(label.casefold()).replace(r'\ ', r'\s*') + r'(?!\w)', p) for label in labels)]
                passage = ' '.join(passages)
            if not passage or re.search(r"\b(?:not|isn't|unconfirmed|possibly|maybe|might)\b", passage):
                continue
            heard = set()
            for kind, value in facts:
                matched = False
                if kind == 'fss_complete':
                    matched = bool(re.search(r'\b(?:fss|system|survey|scan)\b.{0,45}\b(?:complete|completed|finished)\b|\ball bodies (?:found|discovered|scanned)\b', passage))
                elif kind.startswith('composition_'):
                    label = {'composition_stars': r'stars?', 'composition_planets': r'planets?',
                             'composition_moons': r'moons?', 'composition_belt_clusters': r'belt clusters?'}[kind]
                    quantity = r'(?:0|zero|no)' if value == 0 else str(value)
                    matched = bool(re.search(r'\b' + quantity + r' ' + label + r'\b', passage))
                elif kind == 'body_count':
                    matched = bool(re.search(r'\b' + str(value) + r' bodies\b', passage))
                elif kind in ('earth_like_worlds', 'water_worlds', 'ammonia_worlds',
                              'terraformable_bodies', 'bodies_with_biology', 'total_biological_signals'):
                    label = {'earth_like_worlds': r'earth[- ]?like (?:worlds?|bodies)',
                             'water_worlds': r'water worlds?', 'ammonia_worlds': r'ammonia worlds?',
                             'terraformable_bodies': r'terraformable (?:bodies|worlds?)',
                             'bodies_with_biology': r'bodies with biolog(?:y|ical signals)',
                             'total_biological_signals': r'biological signals?'}[kind]
                    matched = bool(re.search(r'\b' + str(value) + r' ' + label + r'\b', passage))
                elif kind == 'world':
                    patterns = {'water_world':r'\bwater[- ]world\b', 'earth_like_world':r'\bearth[- ]?like\b', 'ammonia_world':r'\bammonia[- ]world\b'}
                    matched = bool(re.search(patterns[value], passage))
                elif kind == 'terraformable':
                    matched = bool(re.search(r'\bterraformable\b', passage))
                elif kind == 'dss':
                    matched = bool(re.search(r'\bmapped\b|\bmapping (?:is )?(?:complete|done)\b', passage))
                elif kind == 'genus':
                    matched = value in passage
                elif kind == 'organism':
                    matched = value[0] in passage and (not value[1] or value[1] in passage) and bool(re.search(r'\b(?:complete|completed|finished|analysed|analyzed)\b', passage))
                elif kind == 'bio_signals':
                    matched = bool(re.search(r'\b'+str(value)+r' biological signals?\b', passage))
                elif kind == 'biology_complete':
                    matched = 'biology' in passage and 'complete' in passage
                if matched:
                    heard.add((kind, value))
            if heard:
                covered[key] = frozenset(heard)
        return covered

    def confirm(self, claims):
        for key, facts in claims.items():
            self.delivered[key] = self.delivered.get(key, frozenset()) | facts
        while len(self.delivered) > 512:
            self.delivered.pop(next(iter(self.delivered)))
        # Bound ambiguous alias evidence as well, including events with no claims.
        while len(self.aliases) > 2048:
            self.aliases.pop(next(iter(self.aliases)))
