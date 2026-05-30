from __future__ import annotations

from health_observer.providers.formatting import delta_suffix, duration_text

S = " since the previous HealthSync observation"


def test_delta_suffix_up_shows_delta_and_previous() -> None:
    assert delta_suffix(9.0, 3.9) == f", up 5.1 from 3.9{S}"


def test_delta_suffix_down_shows_delta_and_previous() -> None:
    assert delta_suffix(3.9, 9.0) == f", down 5.1 from 9.0{S}"


def test_delta_suffix_unchanged_omits_value() -> None:
    assert delta_suffix(5, 5) == f", unchanged{S}"


def test_delta_suffix_emits_nothing_without_a_pair() -> None:
    assert delta_suffix(5, None) == ""
    assert delta_suffix(None, 5) == ""


def test_delta_suffix_unit_attaches_to_the_delta() -> None:
    assert delta_suffix(5000, 4200, unit="steps") == f", up 800 steps from 4,200{S}"


def test_delta_suffix_accepts_a_duration_formatter() -> None:
    # fmt is provider-supplied; passing the wrong-unit formatter would be a bug, so this
    # locks the seconds-based path Oura uses.
    assert delta_suffix(14400, 2700, fmt=duration_text) == f", up 3h 15m from 45m{S}"
