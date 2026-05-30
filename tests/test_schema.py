from __future__ import annotations

import unittest
from datetime import datetime

from health_observer.schema import base_metadata, make_observation, validate_observation


class ObservationSchemaTests(unittest.TestCase):
    def test_make_observation_emits_canonical_shape_and_raw_ref(self) -> None:
        raw = {"id": "daily-activity-1", "steps": 1234}
        metadata = base_metadata(
            provider="oura",
            scope="day",
            category="activity",
            subtype="daily_activity",
            record_id="daily-activity-1",
            record_version="2026-05-29T12:00:00Z",
            ingested_at=datetime.fromisoformat("2026-05-29T09:00:00-07:00"),
            raw=raw,
            granularity="day",
            metrics={"steps": {"value": 1234, "unit": "count"}},
        )

        self.assertNotIn("raw_ref", metadata)

        observation = make_observation(
            source="oura.daily_activity",
            timestamp="2026-05-29T00:00:00-07:00",
            text="Oura daily activity update.",
            metadata=metadata,
        )

        self.assertEqual(set(observation), {"id", "source", "timestamp", "text", "metadata"})
        self.assertEqual(observation["id"], "healthsync:v1:oura.daily_activity:daily-activity-1:2026-05-29T12:00:00Z")
        self.assertEqual(
            observation["metadata"]["raw_ref"],
            "oura.daily_activity:daily-activity-1:2026-05-29T12:00:00Z",
        )

    def test_make_observation_preserves_prefixed_record_id_raw_ref(self) -> None:
        raw = {"time": "May 29, 2026 at 8:00 AM", "count": 42}
        record_id = "apple_health.steps:2026-05-29T08:00:00-07:00"
        metadata = base_metadata(
            provider="apple_health",
            scope="point",
            category="activity",
            subtype="steps",
            record_id=record_id,
            record_version=None,
            ingested_at=datetime.fromisoformat("2026-05-29T09:00:00-07:00"),
            raw=raw,
            granularity="sample",
        )

        observation = make_observation(
            source="apple_health.steps",
            timestamp="2026-05-29T08:00:00-07:00",
            text="Apple Health recorded steps.",
            metadata=metadata,
        )

        self.assertEqual(
            observation["metadata"]["raw_ref"],
            f"{record_id}:{observation['metadata']['raw_hash']}",
        )

    def test_validate_observation_requires_metadata_contract(self) -> None:
        raw = {"id": "daily-activity-1"}
        metadata = base_metadata(
            provider="oura",
            scope="day",
            category="activity",
            subtype="daily_activity",
            record_id="daily-activity-1",
            record_version=None,
            ingested_at=datetime.fromisoformat("2026-05-29T09:00:00-07:00"),
            raw=raw,
            granularity="day",
        )
        observation = make_observation(
            source="oura.daily_activity",
            timestamp="2026-05-29T00:00:00-07:00",
            text="Oura daily activity update.",
            metadata=metadata,
        )
        del observation["metadata"]["measurement_semantics"]

        with self.assertRaisesRegex(ValueError, "measurement_semantics"):
            validate_observation(observation)


if __name__ == "__main__":
    unittest.main()
