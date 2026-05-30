from __future__ import annotations

from health_observer.rubric import BASE_REFERENCE_PATH, build_rubric, load_base_reference, render_markdown
from health_observer.paths import write_text_if_changed


def _obs(source: str, **metrics) -> dict:
    return {
        "source": source,
        "metadata": {"metrics": {k: {"value": v, "unit": "x"} for k, v in metrics.items()}},
    }


def test_base_reference_ships_and_declares_directions() -> None:
    assert BASE_REFERENCE_PATH.exists()
    base = load_base_reference()
    # HRV and resting/lowest HR must carry explicit, opposite directions.
    assert base["personal"]["whoop.hrv_rmssd"]["direction"] == "higher_is_better"
    assert base["personal"]["whoop.resting_heart_rate"]["direction"] == "lower_is_better"
    assert base["objective"]["whoop.strain"]["direction"] == "neutral"


def test_personal_baselines_are_kept_per_source() -> None:
    # Same metric name HRV from two providers must NOT be blended into one baseline.
    observations = (
        [_obs("whoop.daily_summary", hrv_rmssd=v) for v in (60, 65, 70, 75)]
        + [_obs("oura.recovery_sleep_summary", average_hrv=v) for v in (40, 45, 50)]
    )
    rubric = build_rubric(observations)

    whoop_hrv = rubric["personal"]["whoop.hrv_rmssd"]["baseline"]
    oura_hrv = rubric["personal"]["oura.average_hrv"]["baseline"]
    assert whoop_hrv["median"] == 67.5  # from the WHOOP series only
    assert oura_hrv["median"] == 45.0   # from the Oura series only
    assert whoop_hrv["n"] == 4 and oura_hrv["n"] == 3


def test_baseline_is_none_until_enough_samples() -> None:
    rubric = build_rubric([_obs("whoop.daily_summary", hrv_rmssd=60), _obs("whoop.daily_summary", hrv_rmssd=65)])
    assert rubric["personal"]["whoop.hrv_rmssd"]["baseline"] is None


def test_full_reference_markdown_renders_bands_and_baseline() -> None:
    rubric = build_rubric([_obs("whoop.daily_summary", hrv_rmssd=v) for v in (60, 65, 70, 75)])
    md = render_markdown(rubric)
    assert "## Objective scales (same for everyone)" in md
    assert "0-9.99 light" in md  # strain bands rendered
    assert "WHOOP HRV (RMSSD)" in md
    assert "median 67.5" in md  # the per-source baseline is rendered into the markdown


def test_write_text_if_changed_is_idempotent(tmp_path) -> None:
    target = tmp_path / "full_reference.json"
    assert write_text_if_changed(target, "a") is True   # first write
    assert write_text_if_changed(target, "a") is False  # unchanged -> skipped
    assert write_text_if_changed(target, "b") is True   # changed -> rewritten
