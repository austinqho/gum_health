"""WHOOP provider transforms."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ...schema import base_metadata, hash_raw_record, make_observation, parse_datetime, to_pt
from ..formatting import delta_suffix, duration_text_millis, fmt_dt, fmt_num, kilocalories, maybe_text, miles, present

LogFn = Callable[[str], None]


@dataclass
class TransformStats:
    skipped: int = 0


def whoop_record_version(record: dict) -> str:
    """Return WHOOP's update timestamp or a stable raw-record hash."""
    return str(record.get("updated_at") or hash_raw_record(record))


def percent_text(value) -> str:
    if not present(value):
        return ""
    return f"{fmt_num(value)}%"


def strain_band(value) -> str:
    """WHOOP strain runs 0-21 on a logarithmic cardiovascular-load scale."""
    if not present(value):
        return ""
    v = float(value)
    if v < 10:
        return "light"
    if v < 14:
        return "moderate"
    if v < 18:
        return "strenuous"
    return "all-out"


def recovery_band(value) -> str:
    """WHOOP recovery percentage maps to red/yellow/green zones."""
    if not present(value):
        return ""
    v = float(value)
    if v < 34:
        return "red / low"
    if v < 67:
        return "yellow / moderate"
    return "green / high"


def asleep_milli(stage_summary: dict):
    """Time actually asleep = light + REM + slow-wave (excludes awake time)."""
    keys = (
        "total_light_sleep_time_milli",
        "total_rem_sleep_time_milli",
        "total_slow_wave_sleep_time_milli",
    )
    total = 0
    seen = False
    for key in keys:
        value = stage_summary.get(key)
        if present(value):
            total += int(value)
            seen = True
    return total if seen else None


def main_sleep_in_bed(record: dict) -> int:
    stages = score(record).get("stage_summary") or {}
    return int(stages.get("total_in_bed_time_milli") or 0)


def sentence(parts: list[str]) -> str:
    """Join non-empty parts into a capitalized sentence, or '' if all empty."""
    body = maybe_text(parts)
    if not body:
        return ""
    return body[0].upper() + body[1:] + "."


def article_for(phrase: str) -> str:
    return "an" if phrase[:1].lower() in "aeiou" else "a"


def sport_label(record: dict) -> str:
    """Human-readable workout label; WHOOP uses 'activity' for unlabeled sport."""
    name = record.get("sport_name")
    if not present(name) or str(name).lower() == "activity":
        return "workout"
    return f"{str(name).replace('-', ' ')} workout"


def score(record: dict) -> dict:
    if record.get("score_state") != "SCORED":
        return {}
    value = record.get("score")
    return value if isinstance(value, dict) else {}


def score_state_text(record: dict) -> str:
    state = record.get("score_state")
    if state and state != "SCORED":
        return f"score state is {state}"
    return ""


def whoop_cycle_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "whoop.cycle"
    start = parse_datetime(record["start"])
    end = parse_datetime(record.get("end", ""))
    cycle_score = score(record)
    parts = [
        f"from {fmt_dt(start.isoformat())}" if start and not end else "",
        f"from {fmt_dt(start.isoformat())} to {fmt_dt(end.isoformat())}" if start and end else "",
        f"strain {fmt_num(cycle_score.get('strain'))}" if present(cycle_score.get("strain")) else "",
        f"average heart rate {fmt_num(cycle_score.get('average_heart_rate'))} bpm"
        if present(cycle_score.get("average_heart_rate"))
        else "",
        f"max heart rate {fmt_num(cycle_score.get('max_heart_rate'))} bpm"
        if present(cycle_score.get("max_heart_rate"))
        else "",
        score_state_text(record),
    ]
    text = f"WHOOP recorded a physiological cycle {maybe_text(parts)}."
    metadata = base_metadata(
        provider="whoop",
        scope="range" if end else "point",
        category="activity",
        subtype="cycle",
        record_id=str(record["id"]),
        record_version=whoop_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="cycle",
        time_range={"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        metrics={
            "strain": {"value": cycle_score.get("strain"), "unit": "strain"},
            "energy": {
                "value": cycle_score.get("kilojoule"),
                "unit": "kilojoule",
                "normalized_value": kilocalories(cycle_score.get("kilojoule")),
                "normalized_unit": "kilocalorie",
            },
            "average_heart_rate": {"value": cycle_score.get("average_heart_rate"), "unit": "beats_per_minute"},
            "max_heart_rate": {"value": cycle_score.get("max_heart_rate"), "unit": "beats_per_minute"},
        },
        measurement_semantics="provider_cycle_summary",
        extra=whoop_common_extra(record, ingested_at),
    )
    return make_observation(
        source=source,
        timestamp=start.isoformat() if start else to_pt(ingested_at).isoformat(),
        text=text,
        metadata=metadata,
    )


def whoop_sleep_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "whoop.sleep"
    start = parse_datetime(record["start"])
    end = parse_datetime(record["end"])
    sleep_score = score(record)
    stage_summary = sleep_score.get("stage_summary") or {}
    sleep_needed = sleep_score.get("sleep_needed") or {}
    is_nap = bool(record.get("nap"))
    parts = [
        "nap" if is_nap else "sleep",
        f"from {fmt_dt(start.isoformat())} to {fmt_dt(end.isoformat())}" if start and end else "",
        f"performance {percent_text(sleep_score.get('sleep_performance_percentage'))}"
        if present(sleep_score.get("sleep_performance_percentage"))
        else "",
        f"efficiency {percent_text(sleep_score.get('sleep_efficiency_percentage'))}"
        if present(sleep_score.get("sleep_efficiency_percentage"))
        else "",
        f"consistency {percent_text(sleep_score.get('sleep_consistency_percentage'))}"
        if present(sleep_score.get("sleep_consistency_percentage"))
        else "",
        f"respiratory rate {fmt_num(sleep_score.get('respiratory_rate'))} breaths/min"
        if present(sleep_score.get("respiratory_rate"))
        else "",
        score_state_text(record),
    ]
    text = f"WHOOP recorded {maybe_text(parts)}."
    metadata = base_metadata(
        provider="whoop",
        scope="range",
        category="sleep",
        subtype="nap" if is_nap else "sleep",
        record_id=str(record["id"]),
        record_version=whoop_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="interval",
        time_range={"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        metrics={
            "sleep_performance": {"value": sleep_score.get("sleep_performance_percentage"), "unit": "percent"},
            "sleep_efficiency": {"value": sleep_score.get("sleep_efficiency_percentage"), "unit": "percent"},
            "sleep_consistency": {"value": sleep_score.get("sleep_consistency_percentage"), "unit": "percent"},
            "respiratory_rate": {"value": sleep_score.get("respiratory_rate"), "unit": "breaths_per_minute"},
            "disturbance_count": {"value": sleep_score.get("disturbance_count"), "unit": "count"},
            "total_in_bed_time": {"value": stage_summary.get("total_in_bed_time_milli"), "unit": "millisecond"},
            "total_awake_time": {"value": stage_summary.get("total_awake_time_milli"), "unit": "millisecond"},
            "total_light_sleep_time": {"value": stage_summary.get("total_light_sleep_time_milli"), "unit": "millisecond"},
            "total_slow_wave_sleep_time": {
                "value": stage_summary.get("total_slow_wave_sleep_time_milli"),
                "unit": "millisecond",
            },
            "total_rem_sleep_time": {"value": stage_summary.get("total_rem_sleep_time_milli"), "unit": "millisecond"},
            "baseline_sleep_needed": {
                "value": sleep_needed.get("baseline_milli") if isinstance(sleep_needed, dict) else None,
                "unit": "millisecond",
            },
        },
        measurement_semantics="provider_sleep_interval_summary",
        extra={
            **whoop_common_extra(record, ingested_at),
            "cycle_id": record.get("cycle_id"),
            "is_nap": is_nap,
        },
    )
    return make_observation(
        source=source,
        timestamp=start.isoformat() if start else to_pt(ingested_at).isoformat(),
        text=text,
        metadata=metadata,
    )


def whoop_recovery_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "whoop.recovery"
    recovery_score = score(record)
    timestamp = parse_datetime(record.get("created_at", "")) or parse_datetime(record.get("updated_at", ""))
    parts = [
        f"recovery score {fmt_num(recovery_score.get('recovery_score'))}%"
        if present(recovery_score.get("recovery_score"))
        else "",
        f"resting heart rate {fmt_num(recovery_score.get('resting_heart_rate'))} bpm"
        if present(recovery_score.get("resting_heart_rate"))
        else "",
        f"HRV {fmt_num(recovery_score.get('hrv_rmssd_milli'))} ms"
        if present(recovery_score.get("hrv_rmssd_milli"))
        else "",
        f"SpO2 {fmt_num(recovery_score.get('spo2_percentage'))}%"
        if present(recovery_score.get("spo2_percentage"))
        else "",
        f"skin temperature {fmt_num(recovery_score.get('skin_temp_celsius'))} C"
        if present(recovery_score.get("skin_temp_celsius"))
        else "",
        score_state_text(record),
    ]
    text = f"WHOOP recorded recovery for cycle {record.get('cycle_id')}: {maybe_text(parts)}."
    metadata = base_metadata(
        provider="whoop",
        scope="point",
        category="recovery",
        subtype="recovery",
        record_id=str(record.get("sleep_id") or record["cycle_id"]),
        record_version=whoop_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="event",
        metrics={
            "recovery_score": {"value": recovery_score.get("recovery_score"), "unit": "percent"},
            "resting_heart_rate": {"value": recovery_score.get("resting_heart_rate"), "unit": "beats_per_minute"},
            "hrv_rmssd": {"value": recovery_score.get("hrv_rmssd_milli"), "unit": "millisecond"},
            "spo2_percentage": {"value": recovery_score.get("spo2_percentage"), "unit": "percent"},
            "skin_temp_celsius": {"value": recovery_score.get("skin_temp_celsius"), "unit": "celsius"},
        },
        measurement_semantics="provider_recovery_score",
        extra={
            **whoop_common_extra(record, ingested_at),
            "cycle_id": record.get("cycle_id"),
            "sleep_id": record.get("sleep_id"),
        },
    )
    return make_observation(
        source=source,
        timestamp=timestamp.isoformat() if timestamp else to_pt(ingested_at).isoformat(),
        text=text,
        metadata=metadata,
    )


def whoop_workout_to_observation(record: dict, ingested_at: datetime) -> dict:
    source = "whoop.workout"
    start = parse_datetime(record["start"])
    end = parse_datetime(record["end"])
    workout_score = score(record)
    calories = kilocalories(workout_score.get("kilojoule"))
    distance_miles = miles(workout_score.get("distance_meter"))
    label = sport_label(record)
    parts = [
        label,
        f"from {fmt_dt(start.isoformat())} to {fmt_dt(end.isoformat())}" if start and end else "",
        f"strain {fmt_num(workout_score.get('strain'))}" if present(workout_score.get("strain")) else "",
        f"average heart rate {fmt_num(workout_score.get('average_heart_rate'))} bpm"
        if present(workout_score.get("average_heart_rate"))
        else "",
        f"max heart rate {fmt_num(workout_score.get('max_heart_rate'))} bpm"
        if present(workout_score.get("max_heart_rate"))
        else "",
        f"{fmt_num(calories)} calories expended" if calories is not None else "",
        f"{distance_miles:.2f} miles" if distance_miles is not None else "",
        score_state_text(record),
    ]
    text = f"WHOOP recorded {article_for(label)} {maybe_text(parts)}."
    metadata = base_metadata(
        provider="whoop",
        scope="range",
        category="activity",
        subtype="workout",
        record_id=str(record["id"]),
        record_version=whoop_record_version(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="interval",
        time_range={"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        metrics={
            "strain": {"value": workout_score.get("strain"), "unit": "strain"},
            "energy": {
                "value": workout_score.get("kilojoule"),
                "unit": "kilojoule",
                "normalized_value": calories,
                "normalized_unit": "kilocalorie",
            },
            "distance": {
                "value": workout_score.get("distance_meter"),
                "unit": "meter",
                "normalized_value": distance_miles,
                "normalized_unit": "mile",
            },
            "average_heart_rate": {"value": workout_score.get("average_heart_rate"), "unit": "beats_per_minute"},
            "max_heart_rate": {"value": workout_score.get("max_heart_rate"), "unit": "beats_per_minute"},
            "percent_recorded": {"value": workout_score.get("percent_recorded"), "unit": "percent"},
            "zone_durations": {"value": workout_score.get("zone_durations"), "unit": "millisecond"},
        },
        measurement_semantics="provider_workout_interval_summary",
        extra={
            **whoop_common_extra(record, ingested_at),
            "sport_id": record.get("sport_id"),
            "sport_name": record.get("sport_name"),
        },
    )
    return make_observation(
        source=source,
        timestamp=start.isoformat() if start else to_pt(ingested_at).isoformat(),
        text=text,
        metadata=metadata,
    )


def whoop_cycle_update_to_observation(
    record: dict,
    ingested_at: datetime,
    previous_record: dict | None = None,
) -> dict:
    """Cumulative strain/HR/energy for a cycle, logged with delta-from-previous-poll.

    WHOOP strain is a running total that climbs all day, so this mirrors Oura's
    cumulative daily-total updates: each poll emits the current value plus how much it
    moved since the last HealthSync observation. ``record_version`` hashes the raw record
    so every changed poll is a new, non-duplicate observation.
    """
    source = "whoop.cycle"
    start = parse_datetime(record["start"])
    end = parse_datetime(record.get("end") or "")
    closed = present(record.get("end"))
    day_label = to_pt(start).date().isoformat() if start else "an unknown date"
    cycle_id = record.get("id")
    observed = fmt_dt(to_pt(ingested_at).isoformat())

    cur = score(record)
    prev = score(previous_record) if previous_record else {}
    strain = cur.get("strain")
    kcal = kilocalories(cur.get("kilojoule"))

    delta = {}
    for key in ("strain", "average_heart_rate", "max_heart_rate", "kilojoule"):
        if present(cur.get(key)) and previous_record is not None and present(prev.get(key)):
            delta[key] = cur.get(key) - prev.get(key)

    strain_part = ""
    if present(strain):
        strain_part = (
            f"day strain is now {fmt_num(strain)} of 21 ({strain_band(strain)})"
            f"{delta_suffix(strain, prev.get('strain') if previous_record else None)}"
        )

    status = (
        "the cycle has closed, so these are final"
        if closed
        else "the cycle is still open, so these are still accumulating"
    )
    parts = [
        strain_part,
        f"average heart rate {fmt_num(cur.get('average_heart_rate'))} bpm"
        if present(cur.get("average_heart_rate")) else "",
        f"max heart rate {fmt_num(cur.get('max_heart_rate'))} bpm"
        if present(cur.get("max_heart_rate")) else "",
        f"{fmt_num(kcal)} kcal burned" if kcal is not None else "",
    ]
    text = (
        f"WHOOP cycle strain update for {day_label} (cycle {cycle_id}), observed by HealthSync "
        f"at {observed}: {maybe_text(parts)}. WHOOP cycle strain is a cumulative running total "
        f"for the physiological cycle (wake-to-wake), a take-latest value rather than increments "
        f"to sum; {status}."
    )
    metadata = base_metadata(
        provider="whoop",
        scope="day",
        category="activity",
        subtype="cycle_strain",
        record_id=str(cycle_id),
        record_version=hash_raw_record(record),
        ingested_at=ingested_at,
        raw=record,
        granularity="cycle",
        time_range={"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        metrics={
            "strain": {"value": strain, "unit": "strain_0_21"},
            "energy": {
                "value": cur.get("kilojoule"),
                "unit": "kilojoule",
                "normalized_value": kcal,
                "normalized_unit": "kilocalorie",
            },
            "average_heart_rate": {"value": cur.get("average_heart_rate"), "unit": "beats_per_minute"},
            "max_heart_rate": {"value": cur.get("max_heart_rate"), "unit": "beats_per_minute"},
        },
        measurement_semantics="cycle_strain_cumulative_update",
        extra={
            "observed_at": to_pt(ingested_at).isoformat(),
            "sync_semantics": "provider_cloud_value_observed_at_poll_time",
            "cycle_id": cycle_id,
            "cycle_in_progress": not closed,
            "delta_from_previous_observation": delta,
            "whoop_user_id": record.get("user_id"),
        },
    )
    return make_observation(
        source=source,
        timestamp=start.isoformat() if start else to_pt(ingested_at).isoformat(),
        text=text,
        metadata=metadata,
    )


def whoop_daily_summary_to_observation(
    cycle: dict,
    recovery: dict | None,
    main_sleep: dict | None,
    ingested_at: datetime,
) -> dict:
    """Merge one cycle + its recovery + its main sleep into a single daily observation.

    Recovery and sleep are WHOOP's morning finals and are always rendered. The cycle's
    strain/heart-rate/energy are a running total, so they are only folded in once the
    cycle has CLOSED (``end`` present); while the cycle is open they live in the
    ``whoop.cycle`` delta stream and are omitted here. ``record_version`` is derived
    only from the finalized parts so intra-day strain changes do not re-emit the summary.
    """
    source = "whoop.daily_summary"
    start = parse_datetime(cycle["start"])
    end = parse_datetime(cycle.get("end") or "")
    closed = present(cycle.get("end"))
    day_label = to_pt(start).date().isoformat() if start else "an unknown date"
    cycle_id = cycle.get("id")

    cyc = score(cycle)
    rec = score(recovery) if recovery else {}
    slp = score(main_sleep) if main_sleep else {}
    stages = slp.get("stage_summary") or {}

    strain = cyc.get("strain")
    recovery_score = rec.get("recovery_score")
    kcal = kilocalories(cyc.get("kilojoule"))
    asleep = asleep_milli(stages)

    header = (
        f"WHOOP physiological cycle for {day_label} (cycle {cycle_id}; wake-to-wake, "
        "not a calendar day)."
    )

    if closed:
        cycle_sentence = sentence([
            f"final day strain {fmt_num(strain)} of 21 ({strain_band(strain)})" if present(strain) else "",
            f"average heart rate {fmt_num(cyc.get('average_heart_rate'))} bpm"
            if present(cyc.get("average_heart_rate")) else "",
            f"max heart rate {fmt_num(cyc.get('max_heart_rate'))} bpm"
            if present(cyc.get("max_heart_rate")) else "",
            f"{fmt_num(kcal)} kcal burned" if kcal is not None else "",
        ])
    else:
        cycle_sentence = (
            "Day strain, heart rate, and energy are still accumulating and are tracked "
            "in the whoop.cycle strain updates."
        )

    if recovery is None:
        recovery_sentence = "No recovery score has posted for this cycle yet."
    else:
        recovery_sentence = sentence([
            f"morning recovery {fmt_num(recovery_score)}% ({recovery_band(recovery_score)})"
            if present(recovery_score) else "",
            f"HRV {fmt_num(rec.get('hrv_rmssd_milli'))} ms" if present(rec.get("hrv_rmssd_milli")) else "",
            f"resting heart rate {fmt_num(rec.get('resting_heart_rate'))} bpm"
            if present(rec.get("resting_heart_rate")) else "",
            f"SpO2 {fmt_num(rec.get('spo2_percentage'))}%" if present(rec.get("spo2_percentage")) else "",
            f"skin temperature {fmt_num(rec.get('skin_temp_celsius'))} C"
            if present(rec.get("skin_temp_celsius")) else "",
        ])

    if main_sleep is None:
        sleep_sentence = "No main sleep was recorded for this cycle."
    else:
        s_start = parse_datetime(main_sleep.get("start", ""))
        s_end = parse_datetime(main_sleep.get("end", ""))
        sleep_sentence = sentence([
            f"main sleep {fmt_dt(s_start.isoformat())} to {fmt_dt(s_end.isoformat())}"
            if s_start and s_end else "main sleep recorded",
            f"{duration_text_millis(asleep)} asleep" if asleep is not None else "",
            f"of {duration_text_millis(stages.get('total_in_bed_time_milli'))} in bed"
            if present(stages.get("total_in_bed_time_milli")) else "",
            f"sleep performance {percent_text(slp.get('sleep_performance_percentage'))} (share of sleep need met)"
            if present(slp.get("sleep_performance_percentage")) else "",
            f"efficiency {percent_text(slp.get('sleep_efficiency_percentage'))}"
            if present(slp.get("sleep_efficiency_percentage")) else "",
            f"{duration_text_millis(stages.get('total_rem_sleep_time_milli'))} REM"
            if present(stages.get("total_rem_sleep_time_milli")) else "",
            f"{duration_text_millis(stages.get('total_slow_wave_sleep_time_milli'))} deep"
            if present(stages.get("total_slow_wave_sleep_time_milli")) else "",
            f"respiratory rate {fmt_num(slp.get('respiratory_rate'))} breaths/min"
            if present(slp.get("respiratory_rate")) else "",
        ])

    disclaimer = (
        "Recovery and sleep are WHOOP's finalized morning values; cycle strain is a "
        "cumulative daily total. None are incremental samples to sum. See the WHOOP "
        "rubric for what each band and score means."
    )
    text = " ".join(part for part in [header, cycle_sentence, recovery_sentence, sleep_sentence, disclaimer] if part)

    raw = {"cycle": cycle, "recovery": recovery, "main_sleep": main_sleep}
    # Version only on finalized parts so intra-day strain changes do not churn the summary.
    version_payload = {
        "recovery": recovery,
        "main_sleep": main_sleep,
        "closed": closed,
        "final_strain": strain if closed else None,
    }
    metadata = base_metadata(
        provider="whoop",
        scope="day",
        category="daily_summary",
        subtype="cycle_summary",
        record_id=str(cycle_id),
        record_version=hash_raw_record(version_payload),
        ingested_at=ingested_at,
        raw=raw,
        granularity="cycle",
        time_range={"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        metrics={
            "strain": {"value": strain if closed else None, "unit": "strain_0_21"},
            "energy": {
                "value": cyc.get("kilojoule") if closed else None,
                "unit": "kilojoule",
                "normalized_value": kcal if closed else None,
                "normalized_unit": "kilocalorie",
            },
            "average_heart_rate": {"value": cyc.get("average_heart_rate") if closed else None, "unit": "beats_per_minute"},
            "max_heart_rate": {"value": cyc.get("max_heart_rate") if closed else None, "unit": "beats_per_minute"},
            "recovery_score": {"value": recovery_score, "unit": "percent"},
            "hrv_rmssd": {"value": rec.get("hrv_rmssd_milli"), "unit": "millisecond"},
            "resting_heart_rate": {"value": rec.get("resting_heart_rate"), "unit": "beats_per_minute"},
            "spo2_percentage": {"value": rec.get("spo2_percentage"), "unit": "percent"},
            "skin_temp_celsius": {"value": rec.get("skin_temp_celsius"), "unit": "celsius"},
            "sleep_performance": {"value": slp.get("sleep_performance_percentage"), "unit": "percent"},
            "sleep_efficiency": {"value": slp.get("sleep_efficiency_percentage"), "unit": "percent"},
            "total_sleep_time": {"value": asleep, "unit": "millisecond"},
            "total_in_bed_time": {"value": stages.get("total_in_bed_time_milli"), "unit": "millisecond"},
            "total_rem_sleep_time": {"value": stages.get("total_rem_sleep_time_milli"), "unit": "millisecond"},
            "total_slow_wave_sleep_time": {"value": stages.get("total_slow_wave_sleep_time_milli"), "unit": "millisecond"},
            "respiratory_rate": {"value": slp.get("respiratory_rate"), "unit": "breaths_per_minute"},
        },
        measurement_semantics="daily_cycle_recovery_sleep_summary",
        extra={
            "observed_at": to_pt(ingested_at).isoformat(),
            "sync_semantics": "provider_record_updated_at",
            "cycle_id": cycle_id,
            "cycle_in_progress": not closed,
            "strain_final": closed,
            "recovery_sleep_id": (recovery or {}).get("sleep_id"),
            "included": {
                "cycle": True,
                "recovery": recovery is not None,
                "main_sleep": main_sleep is not None,
            },
            "score_states": {
                "cycle": cycle.get("score_state"),
                "recovery": (recovery or {}).get("score_state"),
                "main_sleep": (main_sleep or {}).get("score_state"),
            },
            "whoop_user_id": cycle.get("user_id"),
        },
    )
    return make_observation(
        source=source,
        timestamp=start.isoformat() if start else to_pt(ingested_at).isoformat(),
        text=text,
        metadata=metadata,
    )


def whoop_common_extra(record: dict, ingested_at: datetime) -> dict:
    return {
        "observed_at": to_pt(ingested_at).isoformat(),
        "sync_semantics": "provider_record_updated_at",
        "score_state": record.get("score_state"),
        "whoop_user_id": record.get("user_id"),
        "timezone_offset": record.get("timezone_offset"),
    }


WHOOP_TRANSFORMS = {
    "whoop.cycle": whoop_cycle_to_observation,
    "whoop.sleep": whoop_sleep_to_observation,
    "whoop.recovery": whoop_recovery_to_observation,
    "whoop.workout": whoop_workout_to_observation,
}


def build_whoop_observations(
    records_by_source: dict[str, list[dict]],
    ingested_at: datetime,
    previous_raw: dict[tuple[str, str], dict] | None = None,
    *,
    log: LogFn | None = None,
    stats: TransformStats | None = None,
) -> list[tuple[dict, dict]]:
    """Build proposition-safe WHOOP observations from fetched provider records.

    Per cycle we emit a ``whoop.cycle`` cumulative strain update (with delta from the
    previous poll, like Oura's daily totals) and a ``whoop.daily_summary`` merging
    recovery + sleep (+ final strain once the cycle closes). Naps and workouts stay as
    standalone events. ``previous_raw`` maps ``(source, record_id) -> raw`` from the
    raw-records log so strain deltas can be computed.
    """
    previous_raw = previous_raw or {}
    stats = stats or TransformStats()
    output: list[tuple[dict, dict]] = []

    cycles: dict = {}
    for cycle in records_by_source.get("whoop.cycle", []):
        if cycle.get("id") is None or not present(cycle.get("start")):
            stats.skipped += 1
            if log:
                log("[whoop] skipping malformed whoop.cycle record: missing id/start")
            continue
        cycles[cycle["id"]] = cycle

    recoveries_by_cycle: dict = {}
    for record in records_by_source.get("whoop.recovery", []):
        cycle_id = record.get("cycle_id")
        if cycle_id is not None:
            recoveries_by_cycle[cycle_id] = record

    main_sleep_by_cycle: dict = {}
    naps: list[dict] = []
    for record in records_by_source.get("whoop.sleep", []):
        if record.get("nap"):
            naps.append(record)
            continue
        cycle_id = record.get("cycle_id")
        current = main_sleep_by_cycle.get(cycle_id)
        if current is None or main_sleep_in_bed(record) > main_sleep_in_bed(current):
            main_sleep_by_cycle[cycle_id] = record

    for cycle_id, cycle in cycles.items():
        previous_cycle = previous_raw.get(("whoop.cycle", str(cycle_id)))
        append_whoop_record(
            output,
            lambda cycle=cycle, previous_cycle=previous_cycle: (
                whoop_cycle_update_to_observation(cycle, ingested_at, previous_cycle),
                cycle,
            ),
            label="whoop.cycle",
            log=log,
            stats=stats,
        )

    for cycle_id, cycle in cycles.items():
        recovery = recoveries_by_cycle.get(cycle_id)
        main_sleep = main_sleep_by_cycle.get(cycle_id)
        append_whoop_record(
            output,
            lambda cycle=cycle, recovery=recovery, main_sleep=main_sleep: (
                whoop_daily_summary_to_observation(cycle, recovery, main_sleep, ingested_at),
                {"cycle": cycle, "recovery": recovery, "main_sleep": main_sleep},
            ),
            label="whoop.daily_summary",
            log=log,
            stats=stats,
        )

    for record in naps:
        append_whoop_record(
            output,
            lambda record=record: (whoop_sleep_to_observation(record, ingested_at), record),
            label="whoop.sleep",
            log=log,
            stats=stats,
        )

    for record in records_by_source.get("whoop.workout", []):
        append_whoop_record(
            output,
            lambda record=record: (whoop_workout_to_observation(record, ingested_at), record),
            label="whoop.workout",
            log=log,
            stats=stats,
        )

    return output


def append_whoop_record(
    output: list[tuple[dict, dict]],
    build_record,
    *,
    label: str,
    log: LogFn | None = None,
    stats: TransformStats | None = None,
) -> None:
    """Append one transformed WHOOP record, skipping malformed provider rows."""
    try:
        item = build_record()
    except Exception as e:
        if stats:
            stats.skipped += 1
        if log:
            log(f"[whoop] skipping malformed {label} record: {e}")
        return
    if not item:
        return
    observation, raw = item
    if observation:
        output.append((observation, raw))
