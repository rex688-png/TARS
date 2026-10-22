"""Host-level rules for routine spontaneous speech.

Only suppress provably routine first-discovery totals. Scientific records,
biology and other noteworthy information must fail open; user questions
never pass through this optional-event filter.
"""
import re

from .Event import PluginEvent


_RECORD_FIELDS = (
    "title", "message", "text", "description", "summary", "notification",
    "detail", "details", "metric", "stat_name", "record_type", "category",
    "name", "label", "record", "value_name",
)

_DISCOVERY_TERMS = re.compile(
    r"\b(?:first[- ]discover(?:ed|y|ies)?|(?:previously\s+)?undiscovered\s+systems?"
    r"|systems?\s+first\s+discovered|discover(?:ed|y|ies)\s+systems?"
    r"|newly\s+discovered\s+systems?)\b", re.I
)
_COUNTER_TERMS = re.compile(
    r"\b(?:personal\s+(?:best|record)|record|counter|count|tally|total"
    r"|\d{1,8}(?:st|nd|rd|th)?\s+(?:first[- ]discovered|undiscovered)|\d{1,8}\s+systems?)\b", re.I
)
_SCIENTIFIC_TERMS = re.compile(
    r"\b(?:gravity|orbital|rotation|period|eccentricity|temperature|atmosphere"
    r"|pressure|mass|radius|ring|biolog(?:y|ical)|genus|species|stratum"
    r"|terraform|water\s+world|earthlike|earth-like|ammonia|codex|mapped"
    r"|dss|signals?|neutron|stellar|habitable|life|star\s+class)\b", re.I
)


def routine_first_discovery_tally(event: object) -> bool:
    """Conservatively recognize *only* Stat Scanner discovery-count notices.

    No dependency on non-contractual event IDs or message wording. In
    particular, a notice with any scientific detail fails open.
    """
    if not isinstance(event, PluginEvent) or event.plugin_event_name != "TARSObservatoryFact":
        return False
    data = event.plugin_event_content
    if not isinstance(data, dict):
        return False
    source = str(data.get("source_plugin") or "").casefold().replace(" ", "").replace("-", "")
    if source not in ("statscanner", "statsscanner"):
        return False

    fragments = [data.get(field) for field in _RECORD_FIELDS]
    text = " ".join(value.strip() for value in fragments if isinstance(value, str))
    if not text or not _DISCOVERY_TERMS.search(text) or not _COUNTER_TERMS.search(text):
        return False
    return not _SCIENTIFIC_TERMS.search(text)


# Included by host prompt generation rather than by a particular character
# preset, so existing saved custom characters receive the same safety rules.
LIVE_EXPLORATION_SPEECH_POLICY = (
    "Spontaneous exploration speech: Do not announce cumulative first-discovered "
    "or undiscovered system totals, or a new personal-best total at every jump. "
    "Store the facts as normal and answer direct questions about progress; do "
    "not recite even a round-number milestone unless asked. Scientific records, "
    "first Codex entries, meaningful biological discoveries and practical "
    "exploration targets are distinct and may still deserve a natural remark. "
    "For a terrestrial world, Landable=false means our ship cannot land there; "
    "it NEVER means the planet lacks solid terrain. Never fabricate a scientific "
    "cause for an unavailable landing, and do not assert atmospheric composition "
    "alone is the cause. Simply say we cannot land there if relevant. "
    "Maintain the fourth wall: never mention game mechanics, developers, DLCs, "
    "player interfaces, software limitations or simulations in character. "
    "An Observatory notification is evidence, not a script to recite. "
    "For a genuinely valuable find such as an Earth-like world, terraformable "
    "water world, remarkable biology or an exceptional physical observation, "
    "say what makes it worthwhile in a natural, grounded way. One to three "
    "sentences are fine, with understated humor or a dry observation when it "
    "fits. Do not invent life, habitability, economic value, visual appearance "
    "or scientific consequences absent from verified facts. "
    "Do not narrate every ordinary atmosphere, marginal record, completed scan "
    "or probe-efficiency result as a scientific achievement. When reporting "
    "precise scientific measurements aloud, round appropriately without "
    "misrepresenting the evidence. A routine fact may be acknowledged briefly "
    "or left unsaid. Do not turn increased personality into increased frequency. "
    "For an enabled SellOrganicData event, recognize the actual Vista Genomics "
    "sale once as a meaningful exploration milestone. Use only recorded species, "
    "base payout and bonus values; give the confirmed credited total when "
    "available, and let a grounded dry remark follow if it earns one. "
    "Never estimate a payout or describe unsold data as sold. "
)
