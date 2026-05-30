from __future__ import annotations

from health_observer.observation_log import log_human_observation_texts, log_human_observations


def test_human_markdown_writer_rewrites_header_and_preserves_body(tmp_path) -> None:
    path = tmp_path / "observations.md"
    path.write_text("Last sync: old\n\n---\n\n## Existing\nold body\n")

    log_human_observations(
        path,
        "apple_health.steps",
        [{"count": 12, "time": "May 29, 2026 at 8:00 AM"}],
    )

    text = path.read_text()
    assert text.count("Last sync:") == 1
    assert "## Update:" in text
    assert '"count": 12' in text
    assert "## Existing\nold body" in text


def test_human_markdown_writer_formats_observation_texts(tmp_path) -> None:
    path = tmp_path / "observations.md"
    observation = {
        "timestamp": "2026-05-29T08:00:00-07:00",
        "text": "Oura daily activity update.",
    }

    log_human_observation_texts(path, "oura", [observation])

    text = path.read_text()
    assert "Last sync:" in text
    assert "1 new observation" in text
    assert "- 2026-05-29T08:00:00-07:00 - Oura daily activity update." in text
