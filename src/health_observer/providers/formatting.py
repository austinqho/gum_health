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


def duration_text(seconds) -> str:
    """Human h/m duration from a SECONDS value.

    Returns "unknown" for a missing value - honest rather than fabricating a "0m" zero for
    absent data. The unit is in the name so the milliseconds variant can't be confused for it.
    """
    if not present(seconds):
        return "unknown"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def duration_text_millis(milliseconds) -> str:
    """Human h/m duration from a MILLISECONDS value (e.g. WHOOP sleep stages)."""
    if not present(milliseconds):
        return "unknown"
    return duration_text(int(milliseconds) // 1000)


def delta_suffix(current, previous, *, fmt=fmt_num, unit: str = "") -> str:
    """Standard cumulative-update clause, shared by Oura and WHOOP so the wording can't drift.

    Returns e.g. ", up 5.1 from 3.9 since the previous HealthSync observation" (or "" when
    there is nothing to compare). Always shows BOTH the computed delta and the previous value,
    so the proposition maker never has to do the arithmetic. ``fmt`` formats values - ``fmt_num``
    for counts/scores/strain, a duration formatter for time totals.
    """
    if not present(current) or not present(previous):
        return ""
    delta = current - previous
    if delta == 0:
        return ", unchanged since the previous HealthSync observation"
    unit_suffix = f" {unit}".rstrip()
    direction = "up" if delta > 0 else "down"
    return (
        f", {direction} {fmt(abs(delta))}{unit_suffix} from {fmt(previous)} "
        "since the previous HealthSync observation"
    )
