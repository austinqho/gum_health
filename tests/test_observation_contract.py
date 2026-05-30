from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from health_observer.providers.apple.transform import apple_step_to_observation
from health_observer.providers.oura.transform import (
    TransformStats,
    build_oura_observations,
    oura_daily_activity_update_to_observation,
)
from health_observer.schema import LOCAL_TZ, validate_observation

ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_examples_are_valid_gum_observations() -> None:
    observations = load_jsonl(ROOT / "examples" / "observations.jsonl")

    assert observations
    for observation in observations:
        validate_observation(observation)
        assert set(observation) == {"id", "source", "timestamp", "text", "metadata"}
        assert observation["id"].startswith(f"healthsync:v1:{observation['source']}:")
        assert observation["metadata"]["raw_ref"].startswith(f"{observation['source']}:")


def test_raw_archive_rows_match_example_observations() -> None:
    observations = load_jsonl(ROOT / "examples" / "observations.jsonl")
    raw_records = load_jsonl(ROOT / "examples" / "raw_records.jsonl")

    assert len(raw_records) == len(observations)
    for observation, raw_record in zip(observations, raw_records, strict=True):
        metadata = observation["metadata"]
        assert raw_record["raw_ref"] == metadata["raw_ref"]
        assert raw_record["raw_hash"] == metadata["raw_hash"]
        assert raw_record["source"] == observation["source"]
        assert raw_record["record_id"] == metadata["record_id"]
        assert raw_record["record_version"] == metadata["record_version"]
        assert raw_record["ingested_at"] == metadata["ingested_at"]
        assert isinstance(raw_record["raw"], dict)


def test_apple_step_transform_matches_golden_handoff_row() -> None:
    golden = load_jsonl(ROOT / "examples" / "observations.jsonl")[0]
    raw_record = load_jsonl(ROOT / "examples" / "raw_records.jsonl")[0]
    ingested_at = datetime.fromisoformat(raw_record["ingested_at"])

    observation = apple_step_to_observation(raw_record["raw"], ingested_at)

    assert observation == golden


def test_apple_step_transform_skips_unparseable_shortcut_times() -> None:
    ingested_at = datetime(2026, 5, 27, 16, 30, tzinfo=LOCAL_TZ)

    assert apple_step_to_observation({"count": 135, "time": "not a shortcut time"}, ingested_at) is None


def test_apple_step_transform_skips_missing_or_bad_counts() -> None:
    ingested_at = datetime(2026, 5, 27, 16, 30, tzinfo=LOCAL_TZ)
    valid_time = "May 27, 2026 at 4:30 PM"

    assert apple_step_to_observation({"time": valid_time}, ingested_at) is None
    assert apple_step_to_observation({"count": "not a number", "time": valid_time}, ingested_at) is None


def test_oura_daily_activity_update_documents_non_additive_daily_totals() -> None:
    ingested_at = datetime(2026, 5, 28, 12, 37, 25, tzinfo=LOCAL_TZ)
    current = {
        "id": "activity-day-1",
        "day": "2026-05-28",
        "timestamp": "2026-05-28T04:00:00.000-07:00",
        "steps": 5000,
        "active_calories": 250,
        "total_calories": 2100,
        "score": 80,
    }
    previous = {
        "id": "activity-day-1",
        "day": "2026-05-28",
        "timestamp": "2026-05-28T02:00:00.000-07:00",
        "steps": 4200,
        "active_calories": 200,
        "total_calories": 1900,
        "score": 78,
    }

    observation = oura_daily_activity_update_to_observation(current, ingested_at, previous)

    validate_observation(observation)
    metadata = observation["metadata"]
    assert observation["source"] == "oura.daily_activity"
    assert metadata["scope"] == "day"
    assert metadata["measurement_semantics"] == "daily_activity_cumulative_update"
    assert metadata["record_version"] == metadata["raw_hash"]
    assert metadata["delta_from_previous_observation"] == {
        "steps": 800,
        "active_calories": 50,
        "total_calories": 200,
        "score": 2,
    }
    assert "not incremental samples" in observation["text"]


def test_invalid_observation_shape_fails_loudly() -> None:
    with pytest.raises(ValueError, match="missing required keys"):
        validate_observation({"source": "apple_health.steps"})


def test_oura_composition_skips_malformed_records_without_dropping_batch() -> None:
    ingested_at = datetime(2026, 5, 28, 12, 37, 25, tzinfo=LOCAL_TZ)
    messages = []
    stats = TransformStats()

    observation_records = build_oura_observations(
        {
            "oura.daily_activity": [{}],
            "oura.daily_stress": [
                {
                    "id": "stress-day-1",
                    "day": "2026-05-28",
                    "stress_high": 2700,
                    "recovery_high": 0,
                }
            ],
        },
        ingested_at,
        log=messages.append,
        stats=stats,
    )

    assert len(observation_records) == 1
    observation, raw = observation_records[0]
    validate_observation(observation)
    assert observation["source"] == "oura.daily_stress"
    assert raw["id"] == "stress-day-1"
    assert stats.skipped == 1
    assert any("skipping malformed oura.daily_activity record" in message for message in messages)
