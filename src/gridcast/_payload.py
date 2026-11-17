"""Checks shared by the Carbon Intensity API parsers.

Each check raises ValueError naming where the offending value sits and what it is.
"""

_MAX_SHOWN_CHARS = 80


def shown(value: object) -> str:
    text = repr(value)
    return text if len(text) <= _MAX_SHOWN_CHARS else text[:_MAX_SHOWN_CHARS] + "..."


def member(obj: object, key: str, where: str) -> object:
    if not isinstance(obj, dict):
        raise ValueError(f"{where}: expected an object, got {shown(obj)}")
    if key not in obj:
        raise ValueError(f"{where}: missing key {key!r}")
    return obj[key]


def as_list(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{where}: expected a list, got {shown(value)}")
    return value


def as_int(value: object, where: str) -> int:
    # bool is an int subclass, and true is not a count.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{where}: expected an integer, got {shown(value)}")
    return value


def forecast_value(intensity: object, where: str) -> int:
    value = as_int(member(intensity, "forecast", where), f"{where} forecast")
    if value < 0:
        raise ValueError(f"{where}: expected a non-negative forecast, got {value}")
    return value
