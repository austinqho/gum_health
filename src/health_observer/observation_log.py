"""Append-only observation log writers."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Iterable, TypeVar

from .schema import Observation

T = TypeVar("T")

HUMAN_OBSERVATIONS_INTRO = """This is the human-readable version of observations.jsonl. The observation text can be read by a proposition prompt, while observations.jsonl keeps the same facts in computer-readable form with IDs, metadata, and raw-record references.

Caveats: Oura workouts include exact ranges. Oura daily stress exposes daily totals, not exact stress intervals. Oura daily activity step counts are cumulative day totals, not per-walk samples. Oura activity classification gives 5-minute low/medium/high timing context. Apple Health step observations are completed point samples from the Shortcut."""


def log_observations(path: Path, observations: Iterable[Observation]) -> int:
    """Append observations to the canonical JSONL log."""
    observations = list(observations)
    if not observations:
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for observation in observations:
            f.write(json.dumps(observation, sort_keys=True) + "\n")
    return len(observations)


def log_raw_records(path: Path, raw_records: Iterable[dict]) -> int:
    """Append untouched provider records to the raw JSONL archive."""
    raw_records = list(raw_records)
    if not raw_records:
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for record in raw_records:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    return len(raw_records)


def raw_record_for_observation(observation: Observation, raw: dict) -> dict:
    """Build the raw archive row corresponding to a canonical observation."""
    metadata = observation["metadata"]
    return {
        "raw_ref": metadata["raw_ref"],
        "raw_hash": metadata["raw_hash"],
        "source": observation["source"],
        "record_id": metadata["record_id"],
        "record_version": metadata["record_version"],
        "ingested_at": metadata["ingested_at"],
        "raw": raw,
    }


def log_human_observations(path: Path, source_name: str, new_samples: list[dict]) -> None:
    """Prepend a human-readable Apple Shortcut update block."""
    prepend_human_update(
        path,
        source_name,
        new_samples,
        row_noun="sample",
        format_row=lambda sample: json.dumps(sample),
    )


def log_human_observation_texts(path: Path, source_name: str, observations: Iterable[Observation]) -> None:
    """Prepend human-readable observation text for non-Apple providers."""
    prepend_human_update(
        path,
        source_name,
        observations,
        row_noun="observation",
        format_row=lambda observation: f"- {observation['timestamp']} - {observation['text']}",
    )


def prepend_human_update(
    path: Path,
    source_name: str,
    rows: Iterable[T],
    *,
    row_noun: str,
    format_row: Callable[[T], str],
) -> None:
    """Prepend rows to the human-readable log while preserving prior updates."""
    rows = list(rows)
    if not rows:
        return

    now_str = datetime.now().strftime("%B %-d, %Y at %-I:%M %p")
    count = len(rows)
    block_lines = [
        f"## Update: {now_str} ({count} new {row_noun}" + ("s" if count != 1 else "") + f") - {source_name}",
        "",
    ]
    for row in reversed(rows):
        block_lines.append(format_row(row))
    block_lines.extend(["", "---", ""])
    new_block = "\n".join(block_lines)

    if path.exists():
        existing = path.read_text()
        lines = existing.splitlines()
        if lines and lines[0].startswith("Last sync:"):
            body_start = 0
            for i, line in enumerate(lines):
                if line.strip() == "---":
                    body_start = i + 1
                    break
            body = "\n".join(lines[body_start:]).lstrip("\n")
        else:
            body = existing
    else:
        body = ""

    header = f"Last sync: {now_str}\n\n{HUMAN_OBSERVATIONS_INTRO}\n\n---\n\n"
    path.write_text(header + new_block + body)
