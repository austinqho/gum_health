from __future__ import annotations

from datetime import date

import health_observer.providers.whoop.api as whoop_api
from health_observer.providers.whoop.api import (
    WHOOP_ENDPOINTS,
    date_params,
    fetch_collection,
    parse_scopes,
    sources_allowed_by_scopes,
)


def test_whoop_collection_params_match_v2_pagination_contract() -> None:
    params = date_params(start_date=date(2026, 5, 1), end_date=date(2026, 5, 2))

    assert params["limit"] == "25"
    assert params["start"].startswith("2026-05-01T00:00:00")
    assert params["end"].startswith("2026-05-03T00:00:00")


def test_whoop_fetch_collection_uses_records_and_next_token(monkeypatch) -> None:
    calls = []

    def fake_get_json(access_token, path, params):
        calls.append((path, params.copy()))
        if "nextToken" not in params:
            return {"records": [{"id": 1}], "next_token": "page-2"}
        return {"records": [{"id": 2}]}

    monkeypatch.setattr(whoop_api, "get_json", fake_get_json)

    records = list(
        fetch_collection(
            "token",
            WHOOP_ENDPOINTS["whoop.sleep"],
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
        )
    )

    assert records == [{"id": 1}, {"id": 2}]
    assert calls[0][0] == "/v2/activity/sleep"
    assert "nextToken" not in calls[0][1]
    assert calls[1][1]["nextToken"] == "page-2"


def test_whoop_sources_are_gated_by_granted_scopes() -> None:
    allowed = sources_allowed_by_scopes(
        ["whoop.cycle", "whoop.sleep", "whoop.recovery"],
        config={"scopes": ["read:cycles", "read:sleep"]},
        tokens={},
    )

    assert allowed == ["whoop.cycle", "whoop.sleep"]
    assert parse_scopes("offline read:cycles,read:sleep") == {"offline", "read:cycles", "read:sleep"}
