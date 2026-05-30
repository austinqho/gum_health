from __future__ import annotations

import urllib.parse

from health_observer.providers.whoop.auth import build_authorize_url


def test_whoop_authorize_url_requests_refreshable_read_scopes() -> None:
    url, state = build_authorize_url(
        {
            "client_id": "client-123",
            "client_secret": "secret",
            "redirect_uri": "https://example.com/whoop/callback",
        },
        state="state-123",
    )

    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.prod.whoop.com"
    assert parsed.path == "/oauth/oauth2/auth"
    assert state == "state-123"
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["client-123"]
    assert params["redirect_uri"] == ["https://example.com/whoop/callback"]
    assert params["state"] == ["state-123"]
    assert set(params["scope"][0].split()) == {
        "offline",
        "read:cycles",
        "read:sleep",
        "read:recovery",
        "read:workout",
    }
