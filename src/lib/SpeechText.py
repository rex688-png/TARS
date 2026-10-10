"""Provider-independent text preparation for spoken quantities."""

import re

from num2words import num2words


_QUANTITY = re.compile(
    r"(?<![\w/-])(?P<number>\d{1,3}(?:[ ,]\d{3})+|\d+)(?:\.(?P<decimal>\d+))?"
    r"(?P<space>\s*)(?P<unit>credits?|cr|tonnes?|tons?|percent|%|"
    r"light[- ]years?|ly|jumps?|kilometers?|km|light[- ]seconds?|ls)(?=\W|$)",
    re.IGNORECASE,
)


def normalize_spoken_quantities(text: str) -> str:
    """Speak explicit quantities while leaving names, IDs and model numbers alone."""

    def replace(match: re.Match[str]) -> str:
        number = int(match.group("number").replace(",", "").replace(" ", ""))
        spoken = num2words(number, lang="en")
        decimal = match.group("decimal")
        if decimal is not None:
            spoken += " point " + " ".join(num2words(int(digit), lang="en") for digit in decimal)
        unit = match.group("unit")
        if unit == "%":
            unit = "percent"
        elif unit.lower() == "ly":
            unit = "light-years"
        elif unit.lower() == "ls":
            unit = "light-seconds"
        elif unit.lower() == "cr":
            unit = "credits"
        if number == 1 and decimal is None:
            unit = {
                "credits": "credit",
                "tonnes": "tonne",
                "tons": "ton",
                "jumps": "jump",
                "light-years": "light-year",
                "light-seconds": "light-second",
            }.get(unit.lower(), unit)
        return f"{spoken} {unit}"

    return _QUANTITY.sub(replace, text)
