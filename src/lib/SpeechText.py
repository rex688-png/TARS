"""Provider-independent text preparation for spoken quantities."""

import re

from num2words import num2words

_NUMBER = r'[+-]?(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:\.\d+)?'
_QUANTITY = re.compile(
    r'(?<![\w/.,+-])(?P<number>' + _NUMBER + r')'
    r'(?P<space>\s*)(?P<unit>credits?|cr|tonnes?|tons?|percent|%|'
    r'light[- ]years?|ly|jumps?|kilometers?|km|light[- ]seconds?|ls|'
    r'atmospheres?|atm|pascals?|Pa)(?=\W|$)', re.IGNORECASE,
)
_CREDIT_BREAKDOWN = re.compile(
    r'(?P<prefix>\bcredits?\s*\(\s*base:\s*)(?P<base>' + _NUMBER + r')'
    r'(?P<middle>\s*,\s*bonus:\s*)(?P<bonus>' + _NUMBER + r')(?P<end>\s*\))', re.I,
)
_GRAVITY = re.compile(
    r'(?P<label>\bgravity(?:\s+(?:is|of))?\s*[:=]?\s*)(?P<number>' + _NUMBER + r')\s+g\b', re.I,
)


def _spoken_number(value):
    clean = value.replace(',', '').replace(' ', '')
    sign = 'minus ' if clean.startswith('-') else 'plus ' if clean.startswith('+') else ''
    integer, dot, decimal = clean.lstrip('+-').partition('.')
    spoken = sign + num2words(int(integer), lang='en')
    if dot:
        spoken += ' point ' + ' '.join(num2words(int(digit), lang='en') for digit in decimal)
    return spoken


def normalize_spoken_quantities(text: str) -> str:
    """Speak explicit quantities while leaving names, IDs and model numbers alone."""
    text = _CREDIT_BREAKDOWN.sub(lambda m: m['prefix'] + _spoken_number(m['base']) +
                                m['middle'] + _spoken_number(m['bonus']) + m['end'], text)
    text = _GRAVITY.sub(lambda m: m['label'] + _spoken_number(m['number']) + ' standard gravities', text)

    def replace(match: re.Match[str]) -> str:
        unit = match['unit']
        if unit.lower() in ('pa', 'atm') and not match['space']:
            return match[0]  # A bare 12PA/2ATM can be a designation.
        spoken = _spoken_number(match['number'])
        unit = {'%': 'percent', 'ly': 'light-years', 'ls': 'light-seconds',
                'cr': 'credits', 'atm': 'atmospheres', 'pa': 'pascals'}.get(unit.lower(), unit)
        if match['number'].replace(',', '').replace(' ', '') in ('1', '+1'):
            unit = {'credits': 'credit', 'tonnes': 'tonne', 'tons': 'ton', 'jumps': 'jump',
                    'light-years': 'light-year', 'light-seconds': 'light-second',
                    'atmospheres': 'atmosphere', 'pascals': 'pascal'}.get(unit.lower(), unit)
        return f'{spoken} {unit}'

    return _QUANTITY.sub(replace, text)
