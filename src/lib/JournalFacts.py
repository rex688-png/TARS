"""Conservative journal transaction facts; no estimates or profile changes."""
import hashlib
import json

SALE_EVENTS = frozenset(('SellExplorationData', 'MultiSellExplorationData', 'SellOrganicData'))


def sale_key(event):
    content = getattr(event, 'content', None)
    if getattr(event, 'kind', None) != 'game' or not isinstance(content, dict):
        return None
    if content.get('event') not in SALE_EVENTS or not content.get('timestamp'):
        return None  # Identical amounts without a source timestamp can be separate transactions.
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sale_facts(content):
    def amount(value):
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    organic = content.get('event') == 'SellOrganicData'
    base, bonus = amount(content.get('BaseValue')), amount(content.get('Bonus'))
    if organic:
        rows = content.get('BioData')
        if isinstance(rows, list) and rows and all(isinstance(row, dict) for row in rows):
            values = [amount(row.get('Value')) for row in rows]
            bonuses = [amount(row.get('Bonus')) for row in rows]
            base = sum(values) if all(v is not None for v in values) else None
            bonus = sum(bonuses) if all(v is not None for v in bonuses) else None
    total = amount(content.get('TotalEarnings'))
    if total is None and base is not None and bonus is not None:
        total = base + bonus  # Journal Bonus is additional credit, never multiply the base again.
    return {'service': 'Vista Genomics' if organic else 'Universal Cartographics',
            'credited_total': total, 'base': base, 'bonus': bonus}


def sale_description(content):
    facts = sale_facts(content)
    def label(value):
        return f'{value:,}' if value is not None else 'unconfirmed'
    rows = content.get('BioData')
    detail = ''
    if content.get('event') == 'SellOrganicData' and isinstance(rows, list):
        names = [str(row.get('Variant_Localised') or row.get('Species_Localised') or row.get('Species') or 'unidentified species') for row in rows if isinstance(row, dict)]
        detail = f" for {len(rows)} species ({', '.join(names)})"
    return (f"Confirmed {facts['service']} sale{detail}: credited total {label(facts['credited_total'])} credits "
            f"(base: {label(facts['base'])}, bonus: {label(facts['bonus'])}). "
            'This transaction is independent; it does not establish a sale at the other service. '
            'Bonus is already included in the credited total; do not add it twice.')
