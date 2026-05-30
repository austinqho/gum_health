"""Shared helpers for provider transforms."""
from __future__ import annotations

from ..schema import parse_datetime

METERS_PER_MILE = 1609.344
KILOJOULES_PER_KILOCALORIE = 4.184


def present(value) -> bool:
    return value is not None and value != ""


def fmt_num(value, decimals: int = 1) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.{decimals}f}"
    return str(value)


def fmt_dt(value: str) -> str:
    dt = parse_datetime(value)
    if dt is None:
        return value
    return dt.strftime("%-I:%M %p PT on %B %-d, %Y")


def maybe_text(parts: list[str]) -> str:
    return ", ".join(part for part in parts if part)


def miles(meters) -> float | None:
    if meters is None:
        return None
    return float(meters) / METERS_PER_MILE


def kilocalories(kilojoules) -> float | None:
    if kilojoules is None:
        return None
    return float(kilojoules) / KILOJOULES_PER_KILOCALORIE
