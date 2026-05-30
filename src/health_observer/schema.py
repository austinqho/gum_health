"""Canonical observation schema helpers."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping, NotRequired, TypedDict, cast
from zoneinfo import ZoneInfo

LOCAL_TZ_NAME = "America/Los_Angeles"
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)


class ObservationMetadata(TypedDict):
    """Metadata required on every serialized GUM observation."""

    provider: str
    scope: str
    category: str
    subtype: str
    record_id: str
    record_version: str | None
    timezone: str
    granularity: str
    time_range: dict[str, Any] | None
    ingested_at: str
    units: dict[str, Any]
    metrics: dict[str, Any]
    raw_ref: str
    raw_hash: str
    measurement_semantics: str
    observed_at: NotRequired[str]
    sync_semantics: NotRequired[str]
    delta_from_previous_observation: NotRequired[dict[str, Any]]
    source_latency_known: NotRequired[bool]
    derived_from: NotRequired[str]
    daily_activity_record_id: NotRequired[str]


class ObservationMetadataDraft(TypedDict):
    """Metadata before make_observation adds the canonical raw_ref."""

    provider: str
    scope: str
    category: str
    subtype: str
    record_id: str
    record_version: str | None
    timezone: str
    granularity: str
    time_range: dict[str, Any] | None
    ingested_at: str
    units: dict[str, Any]
    metrics: dict[str, Any]
    raw_hash: str
    measurement_semantics: str
    observed_at: NotRequired[str]
    sync_semantics: NotRequired[str]
    delta_from_previous_observation: NotRequired[dict[str, Any]]
    source_latency_known: NotRequired[bool]
    derived_from: NotRequired[str]
    daily_activity_record_id: NotRequired[str]


class Observation(TypedDict):
    """Serialized GUM observation contract."""

    id: str
    source: str
    timestamp: str
    text: str
    metadata: ObservationMetadata


REQUIRED_OBSERVATION_KEYS = {"id", "source", "timestamp", "text", "metadata"}
REQUIRED_METADATA_KEYS = {
    "provider",
    "scope",
    "category",
    "subtype",
    "record_id",
    "record_version",
    "timezone",
    "granularity",
    "time_range",
    "ingested_at",
    "units",
    "metrics",
    "raw_ref",
    "raw_hash",
    "measurement_semantics",
}
ALLOWED_SCOPES = {"point", "range", "day", "system"}


def to_pt(dt: datetime) -> datetime:
    """Return a timezone-aware datetime in Pacific Time."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def parse_datetime(value: str) -> datetime | None:
    """Parse an ISO-ish provider datetime and normalize to Pacific Time."""
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return to_pt(datetime.fromisoformat(normalized))
    except ValueError:
        return None


def day_start_pt(day: str) -> str:
    """Return the start of a provider day in Pacific Time."""
    return datetime.fromisoformat(day).replace(tzinfo=LOCAL_TZ).isoformat()


def observation_id(source: str, record_id: str, record_version: str | None = None) -> str:
    """Build the HealthSync observation ID."""
    base_id = record_id if record_id.startswith(f"{source}:") else f"{source}:{record_id}"
    if record_version:
        return f"healthsync:v1:{base_id}:{record_version}"
    return f"healthsync:v1:{base_id}"


def base_metadata(
    *,
    provider: str,
    scope: str,
    category: str,
    subtype: str,
    record_id: str,
    record_version: str | None,
    ingested_at: datetime,
    raw: dict,
    granularity: str,
    time_range: dict | None = None,
    units: dict | None = None,
    metrics: dict | None = None,
    measurement_semantics: str | None = None,
    extra: dict | None = None,
) -> ObservationMetadataDraft:
    """Build the common metadata block every observation carries."""
    raw_hash = hash_raw_record(raw)
    if measurement_semantics is None:
        measurement_semantics = default_measurement_semantics(scope, granularity)
    metadata: dict[str, Any] = {
        "provider": provider,
        "scope": scope,
        "category": category,
        "subtype": subtype,
        "record_id": record_id,
        "record_version": record_version,
        "timezone": LOCAL_TZ_NAME,
        "granularity": granularity,
        "time_range": time_range,
        "ingested_at": to_pt(ingested_at).isoformat(),
        "units": units or {},
        "metrics": metrics or {},
        "raw_hash": raw_hash,
        "measurement_semantics": measurement_semantics,
    }
    if extra:
        metadata.update(extra)
    return cast(ObservationMetadataDraft, metadata)


def make_observation(
    *,
    source: str,
    timestamp: str,
    text: str,
    metadata: Mapping[str, Any],
) -> Observation:
    """Create and validate a canonical HealthSync observation dict."""
    record_id = str(metadata["record_id"])
    record_version = metadata.get("record_version")
    raw_ref_version = record_version or metadata["raw_hash"]
    raw_ref_base = record_id if record_id.startswith(f"{source}:") else f"{source}:{record_id}"
    observation_metadata = cast(
        ObservationMetadata,
        {**metadata, "raw_ref": f"{raw_ref_base}:{raw_ref_version}"},
    )
    observation: Observation = {
        "id": observation_id(source, record_id, record_version),
        "source": source,
        "timestamp": timestamp,
        "text": text,
        "metadata": observation_metadata,
    }
    validate_observation(observation)
    return observation


def validate_observation(observation: Mapping[str, Any]) -> None:
    """Raise ValueError if an observation does not match the required shape."""
    missing = REQUIRED_OBSERVATION_KEYS - observation.keys()
    if missing:
        raise ValueError(f"Observation missing required keys: {sorted(missing)}")
    metadata = observation.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Observation metadata must be a dict")
    missing_metadata = REQUIRED_METADATA_KEYS - metadata.keys()
    if missing_metadata:
        raise ValueError(f"Observation metadata missing required keys: {sorted(missing_metadata)}")
    scope = metadata.get("scope")
    if scope not in ALLOWED_SCOPES:
        raise ValueError(f"Observation metadata scope must be one of {sorted(ALLOWED_SCOPES)}; got {scope!r}")


def hash_raw_record(raw: dict) -> str:
    """Return a stable hash for an untouched provider payload."""
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def default_measurement_semantics(scope: str, granularity: str) -> str:
    if scope == "day":
        return "provider_daily_summary"
    if scope == "range":
        return "provider_time_range_event"
    if granularity == "sample":
        return "provider_sample"
    return "provider_point_event"
