"""Conservative reply-only body labels. Journal data and targets are never rewritten."""
import re
from num2words import num2words

_WORDS = {num2words(i, lang='en'): str(i) for i in range(1, 100)}
_NUMBERS = '|'.join(re.escape(word) for word in sorted(_WORDS, key=len, reverse=True))
_LABEL = re.compile(r'(?<![\w/-])(?P<star>[A-D]{1,3})\s*(?P<number>[1-9]\d?|' + _NUMBERS +
                    r')(?![\w/-])(?!\s+(?:hundred|thousand|million|billion)\b)')
_BODY_CUE = re.compile(r'\b(?:body|planet|moon|world)\s+$', re.I)
_BODY_VERB = re.compile(r'\s+(?:is|has|looks|appears|offers|contains|supports)\b', re.I)


def known_body_labels(states, events):
    """Read explicit body-name fields, never infer labels from IDs or system names."""
    location = states.get('Location', {})
    if hasattr(location, 'model_dump'):
        location = location.model_dump()
    records = [location] if isinstance(location, dict) else []
    for event in events:
        data = getattr(event, 'plugin_event_content', getattr(event, 'content', None))
        if isinstance(data, dict):
            records.append(data)
    labels = set()
    for data in records:
        for key in ('Body', 'BodyName', 'body', 'body_name'):
            value = data.get(key)
            if not isinstance(value, str):
                continue
            match = re.search(r'(?:^|\s)([A-D]{1,3})\s*([1-9]\d?)$', value.strip())
            if match:
                labels.add(match[1] + str(int(match[2])))
    return labels


def format_body_identifiers(text, *, known_labels=(), spoken=False):
    """Format explicit body references; ambiguous names and designations fail open.

    Bare labels and sentence subjects additionally require a known journal body.
    Existing full/procedural names and moon suffixes are left to the model.
    """
    def replace(match):
        number = _WORDS.get(match['number'], match['number'])
        label = match['star'] + str(int(number))
        before, after = text[:match.start()], text[match.end():]
        # A satellite suffix belongs to a longer identifier, not this short label.
        if re.match(r'\s+[a-z](?:\s|$|[.,;:])', after):
            return match[0]
        explicit = bool(_BODY_CUE.search(before))
        standalone = not before.strip() and not after.strip()
        subject = (not before.strip() or bool(re.search(r'[.!?]\s*$', before))) and bool(_BODY_VERB.match(after))
        if not explicit and not (label in known_labels and (standalone or subject)):
            return match[0]
        if spoken:
            return match['star'] + ' ' + num2words(int(number), lang='en')
        return label
    return _LABEL.sub(replace, text)
