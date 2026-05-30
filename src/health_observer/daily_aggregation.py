"""Derived daily aggregation views for humans and proposition prompts."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .paths import HealthSyncPaths, default_paths, ensure_output_dirs, write_text_if_changed
from .providers.formatting import duration_text, fmt_num
from .schema import LOCAL_TZ, parse_datetime, to_pt


def write_daily_aggregation(paths: HealthSyncPaths | None = None) -> Path | None:
    """Regenerate the optional daily aggregation markdown from observations.jsonl."""
    paths = paths or default_paths()
    if not paths.observations_log.exists():
        return None
    ensure_output_dirs(paths)
    observations = load_observations(paths.observations_log)
    text = render_daily_aggregation(observations)
    write_text_if_changed(paths.daily_aggregation_md, text)
    return paths.daily_aggregation_md


def render_daily_aggregation(observations: list[dict[str, Any]]) -> str:
    """Render one representative Apple day, Oura day, and WHOOP day."""
    unique_observations = dedupe_observations(observations)
    apple_day = choose_apple_day(unique_observations)
    oura_day = choose_oura_day(unique_observations)
    whoop_day = choose_whoop_day(unique_observations)

    lines = [
        "# Daily Aggregation",
        "",
        "This optional file is a more organized view of observations.jsonl. It does not replace raw_records.jsonl or observations.jsonl.",
        "Provider observations can arrive retroactively, so this groups one Apple Health day, one Oura day, and one WHOOP day into a readable timeline.",
        "",
    ]
    if apple_day:
        lines.extend(render_apple_day(unique_observations, apple_day))
    else:
        lines.extend(["## Apple Health", "", "No Apple Health step observations found.", ""])
    if oura_day:
        lines.extend(render_oura_day(unique_observations, oura_day))
    else:
        lines.extend(["## Oura", "", "No Oura observations found.", ""])
    if whoop_day:
        lines.extend(render_whoop_day(unique_observations, whoop_day))
    else:
        lines.extend(["## WHOOP", "", "No WHOOP observations found.", ""])
    return "\n".join(lines).rstrip() + "\n"


def load_observations(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def dedupe_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for observation in observations:
        observation_id = observation.get("id")
        if observation_id in seen:
            continue
        seen.add(observation_id)
        output.append(observation)
    return output


def choose_apple_day(observations: list[dict[str, Any]]) -> str | None:
    counts = Counter(
        observation_day(observation)
        for observation in observations
        if observation.get("source") == "apple_health.steps"
    )
    counts.pop(None, None)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def choose_oura_day(observations: list[dict[str, Any]]) -> str | None:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        if str(observation.get("source", "")).startswith("oura."):
            day = observation_day(observation)
            if day:
                by_day[day].append(observation)
    if not by_day:
        return None

    def score(day_items: tuple[str, list[dict[str, Any]]]) -> tuple[int, str]:
        day, items = day_items
        sources = {item.get("source") for item in items}
        value = 0
        value += 40 if "oura.workout" in sources else 0
        value += 25 if "oura.recovery_sleep_summary" in sources else 0
        value += 20 if "oura.daily_activity" in sources else 0
        value += 20 if "oura.daily_stress" in sources else 0
        value += min(sum(1 for item in items if item.get("source") == "oura.activity_classification"), 12)
        return value, day

    return max(by_day.items(), key=score)[0]


def choose_whoop_day(observations: list[dict[str, Any]]) -> str | None:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        if str(observation.get("source", "")).startswith("whoop."):
            day = observation_day(observation)
            if day:
                by_day[day].append(observation)
    if not by_day:
        return None

    def score(day_items: tuple[str, list[dict[str, Any]]]) -> tuple[int, str]:
        day, items = day_items
        sources = {item.get("source") for item in items}
        value = 0
        value += 30 if "whoop.daily_summary" in sources else 0
        value += min(sum(1 for item in items if item.get("source") == "whoop.workout"), 20)
        value += 5 if "whoop.sleep" in sources else 0
        return value, day

    return max(by_day.items(), key=score)[0]


def render_whoop_day(observations: list[dict[str, Any]], day: str) -> list[str]:
    items = [
        observation
        for observation in observations
        if str(observation.get("source", "")).startswith("whoop.") and observation_day(observation) == day
    ]
    lines = [
        f"## WHOOP - {day}",
        "",
        "Identity note: these local observations do not currently carry a WHOOP user label, so this view groups by provider day.",
        "A WHOOP cycle is wake-to-wake, so a day may start the previous evening.",
        "",
    ]
    summary = latest_source(items, "whoop.daily_summary")
    if summary:
        lines.extend(["### Day summary (cycle + recovery + sleep)", "", f"- {summary['text']}", ""])

    strain = latest_source(items, "whoop.cycle")
    if strain:
        lines.extend(["### Strain (cumulative cycle total)", "", f"- {strain['text']}", ""])

    naps = [item for item in items if item.get("source") == "whoop.sleep"]
    if naps:
        lines.extend(["### Naps", ""])
        for nap in naps:
            lines.append(f"- {nap['text']}")
        lines.append("")

    workouts = unique_by(
        [item for item in items if item.get("source") == "whoop.workout"],
        key=lambda item: item.get("text", ""),
    )
    if workouts:
        lines.extend(["### Workouts", ""])
        for workout in workouts:
            lines.append(f"- {workout['text']}")
        lines.append("")

    return lines


def observation_day(observation: dict[str, Any]) -> str | None:
    timestamp = observation.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    dt = parse_datetime(timestamp)
    if dt is None:
        return timestamp[:10] if len(timestamp) >= 10 else None
    return dt.date().isoformat()


def render_apple_day(observations: list[dict[str, Any]], day: str) -> list[str]:
    samples = sorted(
        [
            observation
            for observation in observations
            if observation.get("source") == "apple_health.steps" and observation_day(observation) == day
        ],
        key=lambda observation: observation.get("timestamp", ""),
    )
    total_steps = sum(metric_value(sample, "steps") or 0 for sample in samples)
    lines = [
        f"## Apple Health - {day}",
        "",
        f"Total completed step samples: {len(samples)}",
        f"Total steps across those samples: {fmt_num(total_steps)}",
        "",
        "Step samples:",
    ]
    for sample in samples:
        lines.append(f"- {short_time(sample.get('timestamp'))}: {fmt_num(metric_value(sample, 'steps') or 0)} steps")
    lines.append("")
    return lines


def render_oura_day(observations: list[dict[str, Any]], day: str) -> list[str]:
    items = sorted(
        [
            observation
            for observation in observations
            if str(observation.get("source", "")).startswith("oura.") and observation_day(observation) == day
        ],
        key=oura_sort_key,
    )
    lines = [
        f"## Oura - {day}",
        "",
        "Identity note: these local observations do not currently carry an Oura user label, so this view groups by provider day.",
        "",
    ]
    recovery = latest_source(items, "oura.recovery_sleep_summary")
    if recovery:
        lines.extend(["### Recovery and Sleep", "", f"- {recovery['text']}", ""])

    activity_updates = [item for item in items if item.get("source") == "oura.daily_activity"]
    if activity_updates:
        lines.extend(["### Daily Activity Totals", ""])
        for item in activity_updates:
            metadata = item.get("metadata", {})
            metrics = metadata.get("metrics", {})
            deltas = metadata.get("delta_from_previous_observation") or {}
            parts = [
                metric_phrase(metrics, "steps", "steps"),
                metric_phrase(metrics, "active_calories", "active calories"),
                metric_phrase(metrics, "total_calories", "total calories"),
                metric_phrase(metrics, "activity_score", "activity score"),
            ]
            delta_text = delta_phrase(deltas)
            suffix = f" ({delta_text})" if delta_text else ""
            lines.append(
                f"- Observed by HealthSync at {short_time(metadata.get('observed_at'))}: "
                f"{'; '.join(part for part in parts if part)}{suffix}. "
                "These are cumulative Oura day totals, not per-interval step samples."
            )
        lines.append("")

    classifications = [item for item in items if item.get("source") == "oura.activity_classification"]
    if classifications:
        lines.extend(["### Activity Classification Windows", ""])
        for item in classifications:
            time_range = item.get("metadata", {}).get("time_range") or {}
            label = metric_value(item, "activity_classification") or "activity"
            lines.append(f"- {short_time(time_range.get('start'))}-{short_time(time_range.get('end'))}: {label}")
        lines.append("")

    stress_updates = [item for item in items if item.get("source") == "oura.daily_stress"]
    if stress_updates:
        lines.extend(["### Stress Totals", ""])
        for item in sorted(stress_updates, key=lambda item: item.get("metadata", {}).get("observed_at", "")):
            metadata = item.get("metadata", {})
            deltas = metadata.get("delta_from_previous_observation") or {}
            delta_text = delta_phrase(deltas, seconds=True)
            suffix = f" ({delta_text})" if delta_text else ""
            lines.append(
                f"- Observed by HealthSync at {short_time(metadata.get('observed_at'))}: "
                f"high stress {duration_text(metric_value(item, 'stress_high'))}; "
                f"high recovery {duration_text(metric_value(item, 'recovery_high'))}{suffix}. "
                "Oura exposes daily stress totals here, not exact stress intervals."
            )
        lines.append("")

    workouts = unique_by(
        [item for item in items if item.get("source") == "oura.workout"],
        key=lambda item: item.get("text", ""),
    )
    if workouts:
        lines.extend(["### Workouts", ""])
        for item in workouts:
            lines.append(f"- {item['text']}")
        lines.append("")

    return lines


def latest_source(observations: list[dict[str, Any]], source: str) -> dict[str, Any] | None:
    matches = [item for item in observations if item.get("source") == source]
    if not matches:
        return None
    return max(matches, key=lambda item: item.get("metadata", {}).get("observed_at", item.get("timestamp", "")))


def unique_by(items: list[dict[str, Any]], *, key) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for item in items:
        marker = key(item)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output


def oura_sort_key(observation: dict[str, Any]) -> tuple[str, str]:
    source_order = {
        "oura.recovery_sleep_summary": "0",
        "oura.daily_activity": "1",
        "oura.activity_classification": "2",
        "oura.daily_stress": "3",
        "oura.workout": "4",
    }
    return source_order.get(str(observation.get("source")), "9"), observation.get("timestamp", "")


def metric_value(observation: dict[str, Any], name: str) -> Any:
    metric = observation.get("metadata", {}).get("metrics", {}).get(name)
    if isinstance(metric, dict):
        return metric.get("value")
    return None


def metric_phrase(metrics: dict[str, Any], name: str, label: str) -> str:
    metric = metrics.get(name)
    if not isinstance(metric, dict) or metric.get("value") is None:
        return ""
    return f"{label} {fmt_num(metric['value'])}"


def delta_phrase(deltas: dict[str, Any], *, seconds: bool = False) -> str:
    parts = []
    for key, value in deltas.items():
        if value is None:
            continue
        if seconds:
            formatted = duration_text(abs(value))
        else:
            formatted = fmt_num(abs(value))
        if value > 0:
            parts.append(f"{key} up {formatted}")
        elif value < 0:
            parts.append(f"{key} down {formatted}")
        else:
            parts.append(f"{key} unchanged")
    return "; ".join(parts)


def short_time(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "unknown time"
    dt = parse_datetime(value)
    if dt is None:
        return value
    return to_pt(dt).strftime("%-I:%M %p PT")


def main() -> None:
    path = write_daily_aggregation()
    if path:
        print(f"Wrote {path}")
    else:
        print("No observations.jsonl found.")


if __name__ == "__main__":
    main()
