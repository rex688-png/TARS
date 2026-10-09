"""Response assembly preserves source facts; only exact repeated sentences are suppressed."""
import re
from time import monotonic

RESPONSE_POLICY = (
    "You are TARS; call commander information TARS data, commander data or stored data, never COVAS data. "
    "Current commander facts below take precedence over historical events and logbook memories. "
    "Each commander fact carries a freshness label: LIVE, CURRENT SNAPSHOT, or LAST KNOWN. "
    "Use LIVE only when recent nonhistoric journal activity proves it; otherwise qualify stale answers briefly. "
    "Do not repeat conflicting older credit/fuel/ship/location/route/cargo values when a current value exists. "
    "Combine overlapping Explorer and Observatory facts about the same system/body into one callout, "
    "retaining every unique finding and source detail. Do not repeat the same discovery twice. "
    "Never claim an action succeeded unless its result confirms success; unconfirmed means unconfirmed. "
    "Elite chat, weapons and cargo disposal require explicit user intent, never ordinary conversation. "
)


def current_commander_facts(states):
    def record(name):
        value = states.get(name, {})
        return value.model_dump() if hasattr(value, 'model_dump') else value
    status, ship, location, nav, cargo = (record(name) for name in
        ('CurrentStatus', 'ShipInfo', 'Location', 'NavInfo', 'Cargo'))
    facts = {}
    candidates = {
        'credits': status.get('Balance'),
        'fuel': status.get('Fuel') if status.get('Fuel') is not None else
                {'FuelMain': ship.get('FuelMain'), 'FuelMainCapacity': ship.get('FuelMainCapacity')},
        'ship_name': ship.get('Name'), 'ship_model': ship.get('Model'),
        'location': location, 'route': nav.get('NavRoute'),
        'cargo': status.get('Cargo') if status.get('Cargo') is not None else cargo,
    }
    for key, value in candidates.items():
        if value is not None and value != {}:
            facts[key] = value
    if nav.get('NavRoute'):
        facts['jumps_remaining'] = max(0, len(nav['NavRoute']) - 1)
    return facts


class ExplorationCalloutDeduper:
    def __init__(self):
        self.recent = {}

    def assemble(self, text, *, context, exploration=False, now=None):
        if not exploration or not context:
            return text
        now = monotonic() if now is None else now
        self.recent = {key: at for key, at in self.recent.items() if now - at < 12}
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        result = []
        for sentence in sentences:
            # No fuzzy matching: different numeric values or unique clauses survive.
            key = (context, re.sub(r'\s+', ' ', sentence).casefold().strip())
            if key not in self.recent:
                result.append(sentence)
            self.recent[key] = now
        return ' '.join(result)


def private_text_summary(label, text):
    """Lengths are useful diagnostics; private prompt/memory contents are not logs."""
    return f"{label} ({len(text)} chars)"


def current_fact_envelope(states, *, freshness='LAST KNOWN'):
    """One value per fact with source and session freshness, never competing old values."""
    if freshness not in ('LIVE', 'CURRENT SNAPSHOT', 'LAST KNOWN'):
        freshness = 'LAST KNOWN'
    facts = current_commander_facts(states)
    sources = {'credits':'CurrentStatus','fuel':'CurrentStatus/ShipInfo',
               'ship_name':'ShipInfo','ship_model':'ShipInfo','location':'Location',
               'route':'NavInfo','jumps_remaining':'NavInfo','cargo':'CurrentStatus/Cargo'}
    return {key:{'value':value,'source':sources[key],'freshness':freshness} for key,value in facts.items()}
