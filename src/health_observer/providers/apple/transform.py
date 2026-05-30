"""Apple Health Shortcut transforms."""
from __future__ import annotations

from datetime import datetime

from ...schema import LOCAL_TZ, base_metadata, make_observation


def parse_apple_time(s: str) -> datetime | None:
    """Parse the timestamp string produced by the iOS Shortcut."""
    if not s:
        return None

    s = s.replace("\u202f", " ").replace("\xa0", " ")
    for fmt in ("%B %d, %Y at %I:%M %p", "%b %d, %Y at %I:%M %p"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=LOCAL_TZ)
        except ValueError:
            continue
    return None


def apple_step_to_observation(sample: dict, ingested_at: datetime) -> dict | None:
    """Convert one Apple Health step sample into a canonical observation."""
    dt = parse_apple_time(sample.get("time", ""))
    if dt is None:
        return None

    if "count" not in sample:
        return None
    try:
        count = int(sample["count"])
    except (TypeError, ValueError):
        return None

    timestamp = dt.isoformat()
    record_id = f"apple_health.steps:{timestamp}"
    metadata = base_metadata(
        provider="apple_health",
        scope="point",
        category="activity",
        subtype="steps",
        record_id=record_id,
        record_version=None,
        ingested_at=ingested_at,
        raw=sample,
        granularity="sample",
        units={"steps": "count"},
        metrics={"steps": {"value": count, "unit": "count"}},
        measurement_semantics="completed_step_sample",
    )
    text = (
        "Apple Health recorded a completed step-count sample of "
        f"{count:,} steps at {dt.strftime('%-I:%M %p PT on %B %-d, %Y')}."
    )
    return make_observation(source="apple_health.steps", timestamp=timestamp, text=text, metadata=metadata)
