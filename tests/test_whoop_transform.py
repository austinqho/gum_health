from __future__ import annotations

from datetime import datetime

from health_observer.providers.whoop.transform import TransformStats, build_whoop_observations
from health_observer.schema import LOCAL_TZ, validate_observation


INGESTED_AT = datetime(2026, 5, 29, 9, 0, tzinfo=LOCAL_TZ)


def cycle_record() -> dict:
    return {
        "id": 101,
        "user_id": 501,
        "created_at": "2026-05-28T15:00:00.000Z",
        "updated_at": "2026-05-29T15:00:00.000Z",
        "start": "2026-05-28T07:00:00.000-07:00",
        "end": "2026-05-29T07:00:00.000-07:00",
        "timezone_offset": "-07:00",
        "score_state": "SCORED",
        "score": {
            "strain": 12.3,
            "kilojoule": 8400,
            "average_heart_rate": 72,
            "max_heart_rate": 154,
        },
    }


def sleep_record(score_state: str = "SCORED") -> dict:
    record = {
        "id": "sleep-1",
        "user_id": 501,
        "cycle_id": 101,
        "created_at": "2026-05-29T14:00:00.000Z",
        "updated_at": "2026-05-29T15:00:00.000Z",
        "start": "2026-05-28T23:15:00.000-07:00",
        "end": "2026-05-29T07:05:00.000-07:00",
        "timezone_offset": "-07:00",
        "nap": False,
        "score_state": score_state,
    }
    if score_state == "SCORED":
        record["score"] = {
            "sleep_performance_percentage": 82,
            "sleep_efficiency_percentage": 91,
            "sleep_consistency_percentage": 78,
            "respiratory_rate": 14.8,
            "stage_summary": {
                "total_in_bed_time_milli": 28200000,
                "total_awake_time_milli": 1800000,
                "total_light_sleep_time_milli": 14400000,
                "total_slow_wave_sleep_time_milli": 5400000,
                "total_rem_sleep_time_milli": 6600000,
            },
        }
    return record


def recovery_record() -> dict:
    return {
        "user_id": 501,
        "cycle_id": 101,
        "sleep_id": "sleep-1",
        "created_at": "2026-05-29T14:30:00.000Z",
        "updated_at": "2026-05-29T15:30:00.000Z",
        "score_state": "SCORED",
        "score": {
            "user_calibrating": False,
            "recovery_score": 67,
            "resting_heart_rate": 51,
            "hrv_rmssd_milli": 62,
            "spo2_percentage": 96.5,
            "skin_temp_celsius": 35.8,
        },
    }


def workout_record() -> dict:
    return {
        "id": "workout-1",
        "user_id": 501,
        "created_at": "2026-05-28T22:00:00.000Z",
        "updated_at": "2026-05-28T23:00:00.000Z",
        "start": "2026-05-28T14:00:00.000-07:00",
        "end": "2026-05-28T14:45:00.000-07:00",
        "timezone_offset": "-07:00",
        "sport_id": 0,
        "sport_name": "Running",
        "score_state": "SCORED",
        "score": {
            "strain": 8.7,
            "average_heart_rate": 142,
            "max_heart_rate": 171,
            "kilojoule": 1255.2,
            "percent_recorded": 100,
            "distance_meter": 5000,
            "zone_durations": {"zone_one_milli": 1000, "zone_two_milli": 2000},
        },
    }


def observation_by_source(records: dict[str, list[dict]], source: str) -> dict:
    observation_records = build_whoop_observations(records, INGESTED_AT)
    observations = {observation["source"]: observation for observation, _raw in observation_records}
    observation = observations[source]
    validate_observation(observation)
    return observation


def test_whoop_daily_summary_merges_cycle_into_one_day_observation() -> None:
    observation = observation_by_source({"whoop.cycle": [cycle_record()]}, "whoop.daily_summary")

    assert observation["metadata"]["scope"] == "day"
    assert observation["metadata"]["granularity"] == "cycle"
    assert observation["metadata"]["record_id"] == "101"
    assert observation["metadata"]["metrics"]["strain"]["value"] == 12.3
    assert observation["metadata"]["included"] == {"cycle": True, "recovery": False, "main_sleep": False}
    assert "strain 12.3" in observation["text"]
    # absolute-not-incremental semantics must be carried in the text for the proposition maker
    assert "incremental samples to sum" in observation["text"]


def test_whoop_daily_summary_omits_strain_while_cycle_open() -> None:
    open_cycle = cycle_record()
    open_cycle["end"] = None  # WHOOP leaves end null until the cycle closes at next wake
    observation = observation_by_source({"whoop.cycle": [open_cycle]}, "whoop.daily_summary")

    assert observation["metadata"]["cycle_in_progress"] is True
    assert observation["metadata"]["metrics"]["strain"]["value"] is None
    assert "still accumulating" in observation["text"]


def test_whoop_cycle_update_logs_strain_delta_from_previous_poll() -> None:
    current = cycle_record()  # strain 12.3
    previous = cycle_record()
    previous["score"] = {**previous["score"], "strain": 9.3}

    observation_records = build_whoop_observations(
        {"whoop.cycle": [current]},
        INGESTED_AT,
        {("whoop.cycle", "101"): previous},
    )
    cycle_obs = next(observation for observation, _raw in observation_records if observation["source"] == "whoop.cycle")
    validate_observation(cycle_obs)

    assert cycle_obs["metadata"]["measurement_semantics"] == "cycle_strain_cumulative_update"
    assert cycle_obs["metadata"]["delta_from_previous_observation"]["strain"] == current["score"]["strain"] - 9.3
    # standardized phrasing: computed delta AND the previous value
    assert "up 3.0 from 9.3 since the previous HealthSync observation" in cycle_obs["text"]


def test_whoop_daily_summary_reflects_pending_sleep_score() -> None:
    observation = observation_by_source(
        {"whoop.cycle": [cycle_record()], "whoop.sleep": [sleep_record("PENDING_SCORE")]},
        "whoop.daily_summary",
    )

    assert observation["metadata"]["score_states"]["main_sleep"] == "PENDING_SCORE"
    assert observation["metadata"]["included"]["main_sleep"] is True
    assert observation["metadata"]["metrics"]["sleep_performance"]["value"] is None
    assert "main sleep" in observation["text"].lower()


def test_whoop_daily_summary_maps_recovery_metrics_and_zone() -> None:
    observation = observation_by_source(
        {"whoop.cycle": [cycle_record()], "whoop.recovery": [recovery_record()]},
        "whoop.daily_summary",
    )

    assert observation["metadata"]["metrics"]["recovery_score"] == {"value": 67, "unit": "percent"}
    assert observation["metadata"]["recovery_sleep_id"] == "sleep-1"
    assert "recovery 67%" in observation["text"]
    assert "green" in observation["text"]


def test_whoop_nap_is_emitted_as_standalone_sleep_event() -> None:
    nap = sleep_record()
    nap["id"] = "nap-1"
    nap["nap"] = True
    observation = observation_by_source({"whoop.sleep": [nap]}, "whoop.sleep")

    assert observation["metadata"]["subtype"] == "nap"
    assert "nap" in observation["text"].lower()


def test_whoop_workout_transform_preserves_units_and_adds_normalized_values() -> None:
    observation = observation_by_source({"whoop.workout": [workout_record()]}, "whoop.workout")

    energy = observation["metadata"]["metrics"]["energy"]
    distance = observation["metadata"]["metrics"]["distance"]
    assert energy["value"] == 1255.2
    assert energy["unit"] == "kilojoule"
    assert round(energy["normalized_value"], 1) == 300.0
    assert distance["value"] == 5000
    assert distance["unit"] == "meter"
    assert round(distance["normalized_value"], 2) == 3.11
    assert "Running workout" in observation["text"]


def test_whoop_composition_skips_malformed_records_without_dropping_batch() -> None:
    messages = []
    stats = TransformStats()

    bad_cycle = {"id": 999, "score_state": "SCORED"}  # missing "start" -> raises inside the summary transform

    observation_records = build_whoop_observations(
        {"whoop.cycle": [bad_cycle, cycle_record()], "whoop.workout": [workout_record()]},
        INGESTED_AT,
        log=messages.append,
        stats=stats,
    )

    sources = [observation["source"] for observation, _raw in observation_records]
    for observation, _raw in observation_records:
        validate_observation(observation)
    # the valid cycle (summary + strain update) and the workout survive; the malformed cycle is dropped once
    assert sources.count("whoop.daily_summary") == 1
    assert sources.count("whoop.cycle") == 1
    assert sources.count("whoop.workout") == 1
    assert stats.skipped == 1
    assert any("skipping malformed whoop.cycle record" in message for message in messages)
