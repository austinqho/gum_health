"""Metric rubric: load the static base reference, merge in per-user baselines, ship JSON.

HealthSync is the producer of the handoff files; the proposition maker lives downstream
and only reads them. So the rubric (objective bands + metric direction + per-user
baselines) must be materialized to disk here, refreshed as data grows, so it sits beside
observations.jsonl when the files are handed off.

  - `base_reference.json` (checked into the package): the static, generic, same-for-everyone
    rubric. Hand-editable, version-controlled, never auto-overwritten.
  - `write_rubric()`: loads the base reference, computes per-SOURCE personal baselines from
    observations.jsonl (WHOOP HRV and Oura HRV stay separate; resting HR vs lowest HR stay
    separate), and writes the merged `full_reference.json` (+ a rendered `.md`).
  - `write_rubric()` is a pure regenerate-from-current-observations function with no notion
    of time; the Mac runtime owns cadence (calls it on every poll tick, beside the daily
    aggregation refresh). The write is idempotent: if the regenerated content matches disk,
    nothing is rewritten.

The rubric classifies nothing on its own: read a metric value together with the matching
entry and draw the conclusion from there.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from ..paths import HealthSyncPaths, default_paths, write_text_if_changed

BASE_REFERENCE_PATH = Path(__file__).with_name("base_reference.json")


def load_base_reference() -> dict:
    return json.loads(BASE_REFERENCE_PATH.read_text())


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    low = int(k)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (k - low)


def values_for(observations: list[dict], source_prefix: str, metric_key: str) -> list[float]:
    """Collect one personal metric's values, scoped to a single provider's sources."""
    values: list[float] = []
    for observation in observations:
        if not str(observation.get("source", "")).startswith(source_prefix):
            continue
        metric = (observation.get("metadata") or {}).get("metrics", {}).get(metric_key)
        if isinstance(metric, dict) and isinstance(metric.get("value"), (int, float)):
            values.append(float(metric["value"]))
    return values


def baseline_for(values: list[float], *, min_samples: int = 3) -> dict | None:
    """Median + typical (p25-p75) range for one metric's values, or None if too few."""
    if len(values) < min_samples:
        return None
    ordered = sorted(values)
    return {
        "median": round(statistics.median(ordered), 1),
        "typical_low": round(_percentile(ordered, 25), 1),
        "typical_high": round(_percentile(ordered, 75), 1),
        "min": round(ordered[0], 1),
        "max": round(ordered[-1], 1),
        "n": len(ordered),
    }


def compute_personal_baselines(observations: list[dict], personal_specs: dict) -> dict[str, dict | None]:
    """Per-(source, metric) baseline so WHOOP-HRV and Oura-HRV never blend together."""
    return {
        key: baseline_for(values_for(observations, spec["source_prefix"], spec["metric_key"]))
        for key, spec in personal_specs.items()
    }


def build_rubric(observations: list[dict]) -> dict:
    """The full reference: static base with per-user baselines merged into each personal entry."""
    rubric = load_base_reference()
    baselines = compute_personal_baselines(observations, rubric.get("personal", {}))
    for key, spec in rubric.get("personal", {}).items():
        spec["baseline"] = baselines.get(key)
    return rubric


def render_markdown(rubric: dict) -> str:
    lines = [
        "# Metric Rubric (read together with observations.jsonl)",
        "",
        "Reference scales only. Read a metric value together with the matching entry and draw the",
        "conclusion. `direction` says which way is favorable (HRV higher is better; resting/lowest",
        "heart rate lower is better - opposite directions, so each is stated explicitly).",
        "",
        "## Objective scales (same for everyone)",
    ]
    for spec in rubric.get("objective", {}).values():
        bands = "; ".join(f"{lo}-{hi} {label}" for lo, hi, label in spec["bands"]) or "(no fixed bands)"
        lines.append(
            f"- **{spec['label']}** ({spec['scale']} {spec['unit']}, {spec['kind']}, direction: {spec['direction']}): "
            f"{bands}. {spec['note']}"
        )
    lines += ["", "## Personal metrics - no universal range; interpret against this user's per-source baseline"]
    for spec in rubric.get("personal", {}).values():
        baseline = spec.get("baseline")
        if baseline:
            rng = (
                f"typical {baseline['typical_low']}-{baseline['typical_high']} {spec['unit']} "
                f"(median {baseline['median']}, observed {baseline['min']}-{baseline['max']}, n={baseline['n']})"
            )
        else:
            rng = "baseline pending (not enough data yet)"
        lines.append(f"- **{spec['label']}** (direction: {spec['direction']}): {rng}. {spec['note']}")
    lines.append("")
    return "\n".join(lines)


def load_observations(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_rubric(paths: HealthSyncPaths | None = None) -> tuple[Path, Path]:
    """Regenerate full_reference.json (handoff) and full_reference.md (rendered view).

    Idempotent: only rewrites a file when its content actually changed.
    """
    paths = paths or default_paths()
    observations = load_observations(paths.observations_log)
    rubric = build_rubric(observations)
    out_dir = paths.observations_log.parent
    json_path = out_dir / "full_reference.json"
    md_path = out_dir / "full_reference.md"
    write_text_if_changed(json_path, json.dumps(rubric, indent=2))
    write_text_if_changed(md_path, render_markdown(rubric))
    return json_path, md_path


def main() -> None:
    result = write_rubric()
    print(f"Wrote {result[0]} and {result[1]}")


if __name__ == "__main__":
    main()
