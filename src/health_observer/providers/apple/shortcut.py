"""Apple Health ingestion via the iOS Shortcut's iCloud snapshot."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from ...observation_log import log_human_observations, log_observations, log_raw_records, raw_record_for_observation
from ...observer import CollectionResult
from ...paths import HealthSyncPaths, ensure_output_dirs
from ...schema import LOCAL_TZ
from ...state import save_seen_timestamps
from .transform import apple_step_to_observation

SOURCE_NAME = "apple_health.steps"
SOURCE_FILENAME = "steps.txt"
LogFn = Callable[[str], None]


class AppleShortcutObserver:
    """Collect Apple Health step observations from the Shortcut export file."""

    name = SOURCE_NAME
    source_filenames = (SOURCE_FILENAME,)

    def __init__(self, paths: HealthSyncPaths) -> None:
        self.paths = paths

    def collect(self) -> CollectionResult:
        ensure_output_dirs(self.paths)
        from ...state import load_seen_timestamps

        seen = load_seen_timestamps(self.paths.seen_timestamps_file)
        return ingest_steps(paths=self.paths, seen=seen, log=print)


def read_source_file(path: Path) -> List[dict]:
    """Read a JSON-lines source file written by the iOS Shortcut."""
    if not path.exists():
        return []
    samples = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            samples.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return samples


def ingest_steps(
    *,
    paths: HealthSyncPaths,
    seen: Dict[str, Set[str]],
    log: LogFn | None = None,
) -> CollectionResult:
    """Find new Apple step samples and append canonical observations."""
    samples = read_source_file(paths.icloud_dir / SOURCE_FILENAME)
    if not samples:
        return CollectionResult(observer_name=SOURCE_NAME)

    seen_for_source = seen.get(SOURCE_NAME, set())
    new_samples = []
    observations = []
    raw_records = []
    skipped = 0
    ingested_at = datetime.now(LOCAL_TZ)
    for sample in samples:
        timestamp = sample.get("time")
        if timestamp is None:
            skipped += 1
            if log:
                log("[apple] skipping malformed step sample without time")
            continue
        if timestamp in seen_for_source:
            continue
        observation = apple_step_to_observation(sample, ingested_at)
        if observation is None:
            skipped += 1
            if log:
                log(f"[apple] skipping malformed step sample at {timestamp}")
            seen_for_source.add(timestamp)
            continue
        new_samples.append(sample)
        observations.append(observation)
        raw_records.append(raw_record_for_observation(observation, sample))
        seen_for_source.add(timestamp)

    seen[SOURCE_NAME] = seen_for_source
    if not observations:
        if skipped:
            save_seen_timestamps(paths.seen_timestamps_file, seen)
        return CollectionResult(observer_name=SOURCE_NAME, skipped=skipped)

    logged = log_observations(paths.observations_log, observations)
    log_raw_records(paths.raw_records_log, raw_records)
    log_human_observations(paths.observations_md, SOURCE_NAME, new_samples)
    save_seen_timestamps(paths.seen_timestamps_file, seen)
    return CollectionResult(observer_name=SOURCE_NAME, collected=logged, skipped=skipped)
