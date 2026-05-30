"""Oura provider transforms."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ...schema import LOCAL_TZ, base_metadata, day_start_pt, hash_raw_record, make_observation, parse_datetime, to_pt
from ..formatting import delta_suffix, duration_text, fmt_dt, fmt_num, maybe_text, miles, present

ACTIVITY_CLASS_LABELS = {
    "0": "non-wear",
    "1": "rest",
    "2": "inactive",
    "3": "low activity",
    "4": "medium activity",
    "5": "high activity",
}
ACTIVE_ACTIVITY_CLASSES = {"3", "4", "5"}
LogFn = Callable[[str], None]


@dataclass
class TransformStats:
    skipped: int = 0


def oura_record_version(record: dict) -> str:
    """Return Oura's update timestamp or a stable raw-record hash."""
    timestamp = record.get("timestamp")
    if timestamp:
        return str(timestamp)
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def oura_raw_version(record: dict) -> str:
    """Return a version that changes whenever a cumulative Oura record changes."""
    return hash_raw_record(record)


def total_with_delta(label: str, current, previous, delta_unit: str, verb: str = "is") -> str:
    if not present(current):
        return ""
    return f"{label} {verb} now {fmt_num(current)}" + delta_suffix(current, previous, unit=delta_unit)


def daily_activity_delta(record: dict, previous_record: dict | None) -> dict:
    if not previous_record:
        return {}
    keys = ("steps", "active_calories", "total_calories", "score")
    return {
        key: record.get(key) - previous_record.get(key)
        for key in keys
        if present(record.get(key)) and present(previous_record.get(key))
    }


def stress_total_with_delta(label: str, current, previous) -> str:
    if not present(current):
        return ""
    return f"{label} is now {duration_text(current)}" + delta_suffix(current, previous, fmt=duration_text)


def daily_stress_delta(record: dict, previous_record: dict | None) -> dict:
    if not previous_record:
        return {}
    keys = ("stress_high", "recovery_high")
    return {
        key: record.get(key) - previous_record.get(key)
        for key in keys
        if present(record.get(key)) and present(previous_record.get(key))
    }


def active_classification_runs(classes: str) -> list[tuple[int, int, list[str]]]:
    runs = []
    start = None
    values: list[str] = []
    for index, value in enumerate(classes):
        if value in ACTIVE_ACTIVITY_CLASSES:
            if start is None:
                start = index
                values = []
            values.append(value)
            continue
        if start is not None:
            maybe_add_activity_run(runs, start, index, values)
            start = None
            values = []
    if start is not None:
        maybe_add_activity_run(runs, start, len(classes), values)
    return runs


def maybe_add_activity_run(runs: list, start: int, end: int, values: list[str]) -> None:
    has_medium_or_high = any(value in {"4", "5"} for value in values)
    duration_minutes = (end - start) * 5
    if has_medium_or_high or duration_minutes >= 15:
        runs.append((start, end, values.copy()))


def class_run_label(values: list[str]) -> str:
    unique = sorted(set(values))
    labels = [ACTIVITY_CLASS_LABELS[value] for value in unique]
    if len(labels) == 1:
        return labels[0]
    start = labels[0].replace(" activity", "")
    end = labels[-1].replace(" activity", "")
    return f"{start}-to-{end} activity"


def oura_daily_activity_update_to_observation(
    record: dict,
    ingested_at: datetime,
    previous_record: dict | None = None,
) -> dict:
    source = "oura.daily_activity"
    record_id = record["id"]
    timestamp = day_start_pt(record["day"])
    metrics = {
        "steps": {"value": record.get("steps"), "unit": "count"},
        "active_calories": {"value": record.get("active_calories"), "unit": "kilocalorie"},
        "total_calories": {"value": record.get("total_calories"), "unit": "kilocalorie"},
        "activity_score": {"value": record.get("score"), "unit": "score"},
    }
    observed_at = fmt_dt(ingested_at.isoformat())
    parts = [
        total_with_delta("daily step total", record.get("steps"), previous_record.get("steps") if previous_record else None, "steps"),
        total_with_delta(
            "active calories expended",
            record.get("active_calories"),
            previous_record.get("active_calories") if previous_record else None,
            "active calories",
            verb="are",
        ),
        total_with_delta(
            "total calories expended",
            record.get("total_calories"),
            previous_record.get("total_calories") if previous_record else None,
            "calories",
            verb="are",
        ),
        f"activity score is {fmt_num(record.get('score'))}" if present(record.get("score")) else "",
    ]
    text = (
        f"Oura daily activity update for {record['day']}, observed by HealthSync at {observed_at}: "
        f"{maybe_text(parts)}. Oura daily activity totals are cumulative for the Oura day, not incremental samples."
    )
    metadata = base_metadata(
        provider="oura",
        scope="day",
        category="activity",
        subtype="daily_activity",
        record_id=record_id,
        record_version=oura_raw_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="day",
        metrics=metrics,
        measurement_semantics="daily_activity_cumulative_update",
        extra={
            "observed_at": to_pt(ingested_at).isoformat(),
            "sync_semantics": "provider_cloud_value_observed_at_poll_time",
            "delta_from_previous_observation": daily_activity_delta(record, previous_record),
        },
    )
    return make_observation(source=source, timestamp=timestamp, text=text, metadata=metadata)


def oura_activity_classification_to_observations(record: dict, ingested_at: datetime) -> list[dict]:
    """Convert Oura's 5-minute activity classification string into interval observations."""
    return [
        observation
        for observation, _raw in oura_activity_classification_to_observation_records(record, ingested_at)
    ]


def oura_activity_classification_to_observation_records(record: dict, ingested_at: datetime) -> list[tuple[dict, dict]]:
    """Convert Oura's 5-minute activity classification string into observation/raw pairs."""
    classes = record.get("class_5_min")
    if not classes:
        return []

    observation_records = []
    day_start = datetime.fromisoformat(record["day"]).replace(tzinfo=LOCAL_TZ) + timedelta(hours=4)
    for start_index, end_index, class_values in active_classification_runs(classes):
        start = day_start + timedelta(minutes=5 * start_index)
        end = day_start + timedelta(minutes=5 * end_index)
        label = class_run_label(class_values)
        raw = {
            "daily_activity_id": record["id"],
            "day": record["day"],
            "class_5_min": classes,
            "start_index": start_index,
            "end_index": end_index,
            "class_values": class_values,
            "derived_from": "oura.daily_activity.class_5_min",
        }
        record_id = f"{record['id']}:{start.isoformat()}:{end.isoformat()}"
        text = (
            f"Oura activity classification for {record['day']}, observed by HealthSync at {fmt_dt(ingested_at.isoformat())}, "
            f"classified {fmt_dt(start.isoformat())} to {fmt_dt(end.isoformat())} as {label}. "
            "This is Oura's 5-minute activity-intensity classification, not an exact step-count interval."
        )
        metadata = base_metadata(
            provider="oura",
            scope="range",
            category="activity",
            subtype="activity_classification",
            record_id=record_id,
            record_version=hash_raw_record(raw),
            ingested_at=ingested_at,
            raw=raw,
            granularity="5_min_classification",
            time_range={"start": start.isoformat(), "end": end.isoformat()},
            metrics={
                "activity_classification": {"value": label, "unit": "classification"},
                "bucket_count": {"value": end_index - start_index, "unit": "5_min_bucket"},
            },
            measurement_semantics="provider_activity_classification_interval",
            extra={
                "observed_at": to_pt(ingested_at).isoformat(),
                "sync_semantics": "may_be_delayed_from_provider_sync",
                "source_latency_known": False,
                "derived_from": "oura.daily_activity.class_5_min",
                "daily_activity_record_id": record["id"],
            },
        )
        observation = make_observation(
            source="oura.activity_classification",
            timestamp=start.isoformat(),
            text=text,
            metadata=metadata,
        )
        observation_records.append((observation, raw))
    return observation_records


def oura_heartrate_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "oura.heartrate"
    timestamp = (parse_datetime(record["timestamp"]) or datetime.fromisoformat(record["timestamp"])).isoformat()
    record_id = record["timestamp"]
    text = f"Oura recorded heart rate at {fmt_num(record['bpm'])} bpm at {fmt_dt(timestamp)}."
    metadata = base_metadata(
        provider="oura",
        scope="point",
        category="heart_rate",
        subtype=record.get("source") or "sample",
        record_id=record_id,
        record_version=oura_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="instant",
        metrics={"heart_rate": {"value": record.get("bpm"), "unit": "beats_per_minute"}},
    )
    return make_observation(source=source, timestamp=timestamp, text=text, metadata=metadata)


def oura_recovery_sleep_summary_to_observation(
    *,
    day: str,
    ingested_at: datetime,
    readiness: dict | None = None,
    daily_sleep: dict | None = None,
    sleep: dict | None = None,
    sleep_records: list[dict] | None = None,
    daily_spo2: dict | None = None,
) -> dict | None:
    """Combine once-per-day Oura recovery, sleep, and oxygen records into one observation."""
    if not any([readiness, daily_sleep, sleep, daily_spo2]):
        return None

    raw = {
        "day": day,
        "daily_readiness": readiness,
        "daily_sleep": daily_sleep,
        "sleep": sleep,
        "sleep_records": sleep_records or ([sleep] if sleep else []),
        "daily_spo2": daily_spo2,
    }
    metrics = {}
    parts = []

    if readiness:
        if present(readiness.get("score")):
            metrics["readiness_score"] = {"value": readiness.get("score"), "unit": "score"}
            parts.append(f"readiness score {fmt_num(readiness.get('score'))}")
        if present(readiness.get("temperature_deviation")):
            metrics["temperature_deviation"] = {"value": readiness.get("temperature_deviation"), "unit": "celsius"}
            parts.append(f"temperature deviation {fmt_num(readiness.get('temperature_deviation'))} C")

    if daily_sleep and present(daily_sleep.get("score")):
        metrics["sleep_score"] = {"value": daily_sleep.get("score"), "unit": "score"}
        parts.append(f"sleep score {fmt_num(daily_sleep.get('score'))}")

    time_range = None
    if sleep:
        start = parse_datetime(sleep.get("bedtime_start", ""))
        end = parse_datetime(sleep.get("bedtime_end", ""))
        if start and end:
            time_range = {"start": start.isoformat(), "end": end.isoformat()}
            parts.append(f"main sleep from {fmt_dt(start.isoformat())} to {fmt_dt(end.isoformat())}")
        if present(sleep.get("total_sleep_duration")):
            metrics["total_sleep_duration"] = {"value": sleep.get("total_sleep_duration"), "unit": "second"}
            parts.append(f"{duration_text(sleep.get('total_sleep_duration'))} asleep")
        if present(sleep.get("time_in_bed")):
            metrics["time_in_bed"] = {"value": sleep.get("time_in_bed"), "unit": "second"}
            parts.append(f"{duration_text(sleep.get('time_in_bed'))} in bed")
        if present(sleep.get("efficiency")):
            metrics["efficiency"] = {"value": sleep.get("efficiency"), "unit": "percent"}
            parts.append(f"sleep efficiency {fmt_num(sleep.get('efficiency'))}%")
        if present(sleep.get("average_hrv")):
            metrics["average_hrv"] = {"value": sleep.get("average_hrv"), "unit": "millisecond"}
            parts.append(f"average HRV {fmt_num(sleep.get('average_hrv'))} ms")
        if present(sleep.get("lowest_heart_rate")):
            metrics["lowest_heart_rate"] = {"value": sleep.get("lowest_heart_rate"), "unit": "beats_per_minute"}
            parts.append(f"lowest heart rate {fmt_num(sleep.get('lowest_heart_rate'))} bpm")

    spo2 = ((daily_spo2 or {}).get("spo2_percentage") or {}).get("average")
    if present(spo2):
        metrics["spo2_average"] = {"value": spo2, "unit": "percent"}
        parts.append(f"average overnight SpO2 {fmt_num(spo2)}%")

    text = f"Oura morning recovery and sleep summary for {day}: {maybe_text(parts)}."
    metadata = base_metadata(
        provider="oura",
        scope="day",
        category="recovery",
        subtype="recovery_sleep_summary",
        record_id=day,
        record_version=hash_raw_record(raw),
        ingested_at=ingested_at,
        raw=raw,
        granularity="day",
        time_range=time_range,
        metrics=metrics,
        measurement_semantics="daily_recovery_sleep_summary",
        extra={
            "observed_at": to_pt(ingested_at).isoformat(),
            "included_sources": [
                source
                for source, record in [
                    ("oura.daily_readiness", readiness),
                    ("oura.daily_sleep", daily_sleep),
                    ("oura.sleep", sleep),
                    ("oura.daily_spo2", daily_spo2),
                ]
                if record
            ],
        },
    )
    return make_observation(
        source="oura.recovery_sleep_summary",
        timestamp=day_start_pt(day),
        text=text,
        metadata=metadata,
    )


def oura_workout_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "oura.workout"
    record_id = record["id"]
    start = parse_datetime(record["start_datetime"])
    end = parse_datetime(record["end_datetime"])
    distance_miles = miles(record.get("distance"))
    text_bits = [
        f"{record.get('intensity')} {record.get('activity')} workout",
        f"from {fmt_dt(start.isoformat())} to {fmt_dt(end.isoformat())}" if start and end else "",
        f"{fmt_num(record.get('calories'))} calories expended during the workout" if present(record.get("calories")) else "",
        f"{distance_miles:.2f} miles" if distance_miles is not None else "",
    ]
    text = f"Oura recorded a {maybe_text(text_bits)}."
    metadata = base_metadata(
        provider="oura",
        scope="range",
        category="activity",
        subtype="workout",
        record_id=record_id,
        record_version=oura_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="interval",
        time_range={"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        metrics={
            "calories": {"value": record.get("calories"), "unit": "kilocalorie"},
            "distance": {
                "value": record.get("distance"),
                "unit": "meter",
                "normalized_value": distance_miles,
                "normalized_unit": "mile",
            },
        },
    )
    return make_observation(
        source=source,
        timestamp=start.isoformat() if start else day_start_pt(record["day"]),
        text=text,
        metadata=metadata,
    )


def oura_session_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "oura.session"
    record_id = record["id"]
    start = parse_datetime(record["start_datetime"])
    end = parse_datetime(record["end_datetime"])
    text = f"Oura recorded a {record.get('type')} session from {fmt_dt(start.isoformat())} to {fmt_dt(end.isoformat())}."
    metadata = base_metadata(
        provider="oura",
        scope="range",
        category="activity",
        subtype="session",
        record_id=record_id,
        record_version=oura_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="interval",
        time_range={"start": start.isoformat(), "end": end.isoformat()},
        metrics={
            "motion_count": {"value": record.get("motion_count"), "unit": "count"},
        },
    )
    return make_observation(source=source, timestamp=start.isoformat(), text=text, metadata=metadata)


def oura_tag_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "oura.tag"
    timestamp = parse_datetime(record["timestamp"])
    record_id = record["id"]
    text = f"Oura recorded a user-entered tag at {fmt_dt(timestamp.isoformat())}."
    metadata = base_metadata(
        provider="oura",
        scope="point",
        category="activity",
        subtype="tag",
        record_id=record_id,
        record_version=oura_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="event",
    )
    return make_observation(source=source, timestamp=timestamp.isoformat(), text=text, metadata=metadata)


def oura_enhanced_tag_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "oura.enhanced_tag"
    start = parse_datetime(record["start_time"])
    end = parse_datetime(record.get("end_time", ""))
    record_id = record["id"]
    scope = "range" if end else "point"
    text = f"Oura recorded an enhanced user-entered tag at {fmt_dt(start.isoformat())}."
    if end:
        text = f"Oura recorded an enhanced user-entered tag from {fmt_dt(start.isoformat())} to {fmt_dt(end.isoformat())}."
    metadata = base_metadata(
        provider="oura",
        scope=scope,
        category="activity",
        subtype="enhanced_tag",
        record_id=record_id,
        record_version=oura_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="event" if not end else "interval",
        time_range={"start": start.isoformat(), "end": end.isoformat()} if end else None,
    )
    return make_observation(source=source, timestamp=start.isoformat(), text=text, metadata=metadata)


def oura_daily_stress_update_to_observation(
    record: dict,
    ingested_at: datetime,
    previous_record: dict | None = None,
) -> dict:
    source = "oura.daily_stress"
    record_id = record["id"]
    timestamp = day_start_pt(record["day"])
    parts = [
        stress_total_with_delta(
            "high-stress total",
            record.get("stress_high"),
            previous_record.get("stress_high") if previous_record else None,
        ),
        stress_total_with_delta(
            "high-recovery total",
            record.get("recovery_high"),
            previous_record.get("recovery_high") if previous_record else None,
        ),
    ]
    text = (
        f"Oura daily stress update for {record['day']}, observed by HealthSync at {fmt_dt(ingested_at.isoformat())}: "
        f"{maybe_text(parts)} across the Oura day. The Oura API does not provide exact stress intervals for this daily record."
    )
    metadata = base_metadata(
        provider="oura",
        scope="day",
        category="stress",
        subtype="daily_stress",
        record_id=record_id,
        record_version=oura_raw_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="day",
        metrics={
            "stress_high": {"value": record.get("stress_high"), "unit": "second"},
            "recovery_high": {"value": record.get("recovery_high"), "unit": "second"},
        },
        measurement_semantics="daily_stress_cumulative_update",
        extra={
            "observed_at": to_pt(ingested_at).isoformat(),
            "sync_semantics": "provider_cloud_value_observed_at_poll_time",
            "exact_intervals_available": False,
            "delta_from_previous_observation": daily_stress_delta(record, previous_record),
        },
    )
    return make_observation(source=source, timestamp=timestamp, text=text, metadata=metadata)


def oura_daily_resilience_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "oura.daily_resilience"
    record_id = record["id"]
    timestamp = day_start_pt(record["day"])
    text = f"Oura recorded resilience level {record.get('level')} for {record['day']}."
    metadata = base_metadata(
        provider="oura",
        scope="day",
        category="recovery",
        subtype="daily_resilience",
        record_id=record_id,
        record_version=oura_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="day",
        metrics={"resilience_level": {"value": record.get("level"), "unit": "level"}},
    )
    return make_observation(source=source, timestamp=timestamp, text=text, metadata=metadata)


def oura_daily_cardiovascular_age_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "oura.daily_cardiovascular_age"
    record_id = record["id"]
    timestamp = day_start_pt(record["day"])
    parts = [
        f"vascular age {fmt_num(record.get('vascular_age'))}" if present(record.get("vascular_age")) else "",
        f"pulse wave velocity {fmt_num(record.get('pulse_wave_velocity'))} m/s"
        if present(record.get("pulse_wave_velocity"))
        else "",
    ]
    text = f"Oura recorded {maybe_text(parts)} for {record['day']}."
    metadata = base_metadata(
        provider="oura",
        scope="day",
        category="recovery",
        subtype="cardiovascular_age",
        record_id=record_id,
        record_version=oura_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="day",
        metrics={
            "vascular_age": {"value": record.get("vascular_age"), "unit": "year"},
            "pulse_wave_velocity": {"value": record.get("pulse_wave_velocity"), "unit": "meter_per_second"},
        },
    )
    return make_observation(source=source, timestamp=timestamp, text=text, metadata=metadata)


def oura_vo2_max_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "oura.vo2_max"
    record_id = record["id"]
    timestamp = day_start_pt(record["day"])
    text = f"Oura recorded VO2 max {fmt_num(record.get('vo2_max'))} for {record['day']}."
    metadata = base_metadata(
        provider="oura",
        scope="day",
        category="activity",
        subtype="vo2_max",
        record_id=record_id,
        record_version=oura_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="day",
        metrics={"vo2_max": {"value": record.get("vo2_max"), "unit": "ml_per_kg_per_min"}},
    )
    return make_observation(source=source, timestamp=timestamp, text=text, metadata=metadata)


def build_oura_observations(
    records_by_source: dict[str, list[dict]],
    ingested_at: datetime,
    previous_raw: dict[tuple[str, str], dict] | None = None,
    log: LogFn | None = None,
    stats: TransformStats | None = None,
) -> list[tuple[dict, dict]]:
    """Build proposition-safe Oura observations from fetched provider records.

    This composition lives with the Oura transforms so callers can reuse Oura's
    merge-by-day rules without also taking the HTTP transport.
    """
    previous_raw = previous_raw or {}
    stats = stats or TransformStats()
    output: list[tuple[dict, dict]] = []

    for record in records_by_source.get("oura.daily_activity", []):
        append_oura_record(
            output,
            lambda record=record: (
                oura_daily_activity_update_to_observation(
                    record,
                    ingested_at,
                    previous_raw.get(("oura.daily_activity", record["id"])),
                ),
                record,
            ),
            label="oura.daily_activity",
            log=log,
            stats=stats,
        )
        for item in oura_activity_classification_to_observation_records(record, ingested_at):
            append_oura_record(
                output,
                lambda item=item: item,
                label="oura.activity_classification",
                log=log,
                stats=stats,
            )

    for record in records_by_source.get("oura.daily_stress", []):
        append_oura_record(
            output,
            lambda record=record: (
                oura_daily_stress_update_to_observation(
                    record,
                    ingested_at,
                    previous_raw.get(("oura.daily_stress", record["id"])),
                ),
                record,
            ),
            label="oura.daily_stress",
            log=log,
            stats=stats,
        )

    for day, day_records in recovery_sleep_records_by_day(records_by_source).items():
        raw = {
            "day": day,
            "daily_readiness": day_records.get("oura.daily_readiness"),
            "daily_sleep": day_records.get("oura.daily_sleep"),
            "sleep": day_records.get("oura.sleep"),
            "sleep_records": day_records.get("oura.sleep_records", []),
            "daily_spo2": day_records.get("oura.daily_spo2"),
        }
        append_oura_record(
            output,
            lambda day=day, day_records=day_records, raw=raw: recovery_sleep_observation_record(
                day,
                ingested_at,
                day_records,
                raw,
            ),
            label="oura.recovery_sleep_summary",
            log=log,
            stats=stats,
        )

    optional_transforms = {
        "oura.workout": oura_workout_to_observation,
        "oura.heartrate": oura_heartrate_to_observation,
        "oura.session": oura_session_to_observation,
        "oura.tag": oura_tag_to_observation,
        "oura.enhanced_tag": oura_enhanced_tag_to_observation,
        "oura.daily_resilience": oura_daily_resilience_to_observation,
        "oura.daily_cardiovascular_age": oura_daily_cardiovascular_age_to_observation,
        "oura.vo2_max": oura_vo2_max_to_observation,
    }
    for source, transform in optional_transforms.items():
        for record in records_by_source.get(source, []):
            append_oura_record(
                output,
                lambda record=record, transform=transform: (transform(record, ingested_at), record),
                label=source,
                log=log,
                stats=stats,
            )

    return output


def append_oura_record(
    output: list[tuple[dict, dict]],
    build_record,
    *,
    label: str,
    log: LogFn | None = None,
    stats: TransformStats | None = None,
) -> None:
    """Append one transformed Oura record, skipping malformed provider rows."""
    try:
        item = build_record()
    except Exception as e:
        if stats:
            stats.skipped += 1
        if log:
            log(f"[oura] skipping malformed {label} record: {e}")
        return
    if not item:
        return
    observation, raw = item
    if observation:
        output.append((observation, raw))


def recovery_sleep_observation_record(
    day: str,
    ingested_at: datetime,
    day_records: dict[str, dict],
    raw: dict,
) -> tuple[dict, dict] | None:
    observation = oura_recovery_sleep_summary_to_observation(
        day=day,
        ingested_at=ingested_at,
        readiness=day_records.get("oura.daily_readiness"),
        daily_sleep=day_records.get("oura.daily_sleep"),
        sleep=day_records.get("oura.sleep"),
        sleep_records=day_records.get("oura.sleep_records", []),
        daily_spo2=day_records.get("oura.daily_spo2"),
    )
    if not observation:
        return None
    return observation, raw


def recovery_sleep_records_by_day(records_by_source: dict[str, list[dict]]) -> dict[str, dict[str, dict]]:
    by_day: dict[str, dict[str, dict]] = {}
    for source in ["oura.daily_readiness", "oura.daily_sleep", "oura.daily_spo2"]:
        for record in records_by_source.get(source, []):
            day = record.get("day")
            if day:
                by_day.setdefault(day, {})[source] = record
    for record in records_by_source.get("oura.sleep", []):
        day = record.get("day")
        if not day:
            continue
        day_records = by_day.setdefault(day, {})
        day_records.setdefault("oura.sleep_records", []).append(record)
        current = day_records.get("oura.sleep")
        if current is None or sleep_duration(record) > sleep_duration(current):
            day_records["oura.sleep"] = record
    return by_day


def sleep_duration(record: dict) -> int:
    return int(record.get("total_sleep_duration") or record.get("time_in_bed") or 0)
