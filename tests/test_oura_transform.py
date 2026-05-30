from __future__ import annotations

from datetime import datetime

from health_observer.providers.oura.transform import (
    oura_daily_activity_update_to_observation,
    oura_daily_stress_update_to_observation,
    oura_recovery_sleep_summary_to_observation,
)
from health_observer.schema import LOCAL_TZ, validate_observation

INGESTED = datetime(2026, 5, 28, 21, 0, tzinfo=LOCAL_TZ)


def test_oura_daily_activity_delta_uses_standard_phrasing() -> None:
    current = {"id": "act-1", "day": "2026-05-28", "steps": 5000, "active_calories": 250, "total_calories": 2100, "score": 80}
    previous = {"id": "act-1", "day": "2026-05-28", "steps": 4200, "active_calories": 200, "total_calories": 1900, "score": 78}

    observation = oura_daily_activity_update_to_observation(current, INGESTED, previous)

    validate_observation(observation)
    assert observation["source"] == "oura.daily_activity"
    assert (
        "daily step total is now 5,000, up 800 steps from 4,200 since the previous HealthSync observation"
        in observation["text"]
    )
    assert observation["metadata"]["delta_from_previous_observation"]["steps"] == 800
    assert "not incremental samples" in observation["text"]


def test_oura_daily_stress_delta_renders_durations_and_unchanged() -> None:
    current = {"id": "str-1", "day": "2026-05-28", "stress_high": 14400, "recovery_high": 1800}
    previous = {"id": "str-1", "day": "2026-05-28", "stress_high": 2700, "recovery_high": 1800}

    observation = oura_daily_stress_update_to_observation(current, INGESTED, previous)

    validate_observation(observation)
    assert "high-stress total is now 4h, up 3h 15m from 45m since the previous HealthSync observation" in observation["text"]
    assert "high-recovery total is now 30m, unchanged since the previous HealthSync observation" in observation["text"]


def test_oura_recovery_sleep_summary_merges_day_metrics() -> None:
    observation = oura_recovery_sleep_summary_to_observation(
        day="2026-05-28",
        ingested_at=INGESTED,
        readiness={"score": 82, "temperature_deviation": 0.2},
        daily_sleep={"score": 88},
        sleep={
            "bedtime_start": "2026-05-27T23:00:00-07:00",
            "bedtime_end": "2026-05-28T06:00:00-07:00",
            "total_sleep_duration": 25200,
            "time_in_bed": 27000,
            "efficiency": 91,
            "average_hrv": 55,
            "lowest_heart_rate": 48,
        },
        daily_spo2={"spo2_percentage": {"average": 96.5}},
    )

    validate_observation(observation)
    assert observation["source"] == "oura.recovery_sleep_summary"
    metrics = observation["metadata"]["metrics"]
    assert metrics["readiness_score"]["value"] == 82
    assert metrics["sleep_score"]["value"] == 88
    assert metrics["average_hrv"]["value"] == 55
    assert metrics["lowest_heart_rate"]["value"] == 48
    assert "readiness score 82" in observation["text"]
    assert "sleep score 88" in observation["text"]
