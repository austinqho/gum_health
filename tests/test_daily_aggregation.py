from __future__ import annotations

from pathlib import Path

from health_observer.daily_aggregation import load_observations, render_daily_aggregation

ROOT = Path(__file__).resolve().parents[1]


def test_daily_aggregation_matches_golden() -> None:
    # The example daily_aggregation.md must be exactly what render produces from the example
    # observations - this is the only derived artifact that could otherwise drift silently
    # (e.g. a duration_text-unit change). Regenerate the fixture if rendering legitimately changes.
    observations = load_observations(ROOT / "examples" / "observations.jsonl")
    expected = (ROOT / "examples" / "daily_aggregation.md").read_text()
    assert render_daily_aggregation(observations) == expected


def test_daily_aggregation_renders_all_three_providers() -> None:
    observations = load_observations(ROOT / "examples" / "observations.jsonl")
    out = render_daily_aggregation(observations)
    assert "## Apple Health" in out
    assert "## Oura" in out
    assert "## WHOOP" in out
