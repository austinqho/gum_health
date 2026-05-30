"""Shared OAuth2 client for provider token lifecycles (Oura, WHOOP).

Both providers run the identical authorization-code + refresh-token lifecycle. The only
genuine variation is how client credentials are presented to the token endpoint
(HTTP Basic header vs form body) plus a few config values (URLs, scopes, extra headers,
refresh scope). Collapsing that single shared invariant here means a fix to refresh or
expiry logic cannot drift between providers. Per-provider differences are expressed as an
``OAuthProvider`` config, not as branching logic.
"""
from __future__ import annotations

import base64
import json
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .oauth_callback import catch_oauth_callback

_SSL_CONTEXT: ssl.SSLContext | None = None


class OAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class OAuthProvider:
    """Per-provider OAuth2 configuration. Differences are data, not code paths."""

    name: str
    authorize_url: str
    token_url: str
    default_scopes: list[str]
    client_auth: str = "basic"  # "basic" -> Authorization header; "body" -> form fields
    extra_headers: dict[str, str] = field(default_factory=dict)
    refresh_scope: str | None = None  # some providers (WHOOP) require scope on refresh


def ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        try:
            import certifi

            _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT


def build_authorize_url(provider: OAuthProvider, config: dict[str, Any], state: str | None = None) -> tuple[str, str]:
    state = state or secrets.token_urlsafe(24)
    scopes = config.get("scopes") or provider.default_scopes
    scope_value = scopes if isinstance(scopes, str) else " ".join(scopes)
    query = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": scope_value,
        "state": state,
    }
    return f"{provider.authorize_url}?{urllib.parse.urlencode(query)}", state


def _token_request(provider: OAuthProvider, config: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        **provider.extra_headers,
    }
    body = dict(form)
    if provider.client_auth == "basic":
        credentials = f"{config['client_id']}:{config['client_secret']}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode()
    else:  # "body"
        body["client_id"] = config["client_id"]
        body["client_secret"] = config["client_secret"]

    request = urllib.request.Request(
        provider.token_url,
        data=urllib.parse.urlencode(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise OAuthError(f"{provider.name} token request failed with HTTP {e.code}: {detail}") from e


def exchange_code_for_tokens(provider: OAuthProvider, config: dict[str, Any], code: str) -> dict[str, Any]:
    return with_expiry(
        _token_request(
            provider,
            config,
            {"grant_type": "authorization_code", "code": code, "redirect_uri": config["redirect_uri"]},
        )
    )


def refresh_tokens(provider: OAuthProvider, config: dict[str, Any], refresh_token: str) -> dict[str, Any]:
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    if provider.refresh_scope:
        form["scope"] = provider.refresh_scope
    return with_expiry(_token_request(provider, config, form))


def with_expiry(tokens: dict[str, Any]) -> dict[str, Any]:
    expires_in = int(tokens.get("expires_in") or 0)
    if expires_in:
        tokens["expires_at"] = int(time.time()) + expires_in
    return tokens


def load_tokens(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def save_tokens(path: Path, tokens: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tokens, indent=2, sort_keys=True))
    try:
        path.chmod(0o600)
    except OSError:
        pass


def token_needs_refresh(tokens: dict[str, Any]) -> bool:
    expires_at = int(tokens.get("expires_at") or 0)
    return not tokens.get("access_token") or (expires_at and time.time() >= expires_at - 120)


def get_valid_access_token(provider: OAuthProvider, config: dict[str, Any], tokens_path: Path) -> str | None:
    tokens = load_tokens(tokens_path)
    if not tokens:
        return None
    if token_needs_refresh(tokens):
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return None
        refreshed = refresh_tokens(provider, config, refresh_token)
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = refresh_token
        if "scope" not in refreshed and tokens.get("scope"):
            refreshed["scope"] = tokens["scope"]
        save_tokens(tokens_path, refreshed)
        tokens = refreshed
    return tokens.get("access_token")


def _callback_timeout(config: dict[str, Any]) -> int | None:
    value = config.get("callback_timeout_seconds")
    if value is None:
        return None
    timeout = int(value)
    return timeout if timeout > 0 else None


def complete_local_authorization(provider: OAuthProvider, config: dict[str, Any], tokens_path: Path) -> None:
    authorize_url, state = build_authorize_url(provider, config)
    print(f"Open this URL and approve {provider.name} access:")
    print(authorize_url)
    callback = catch_oauth_callback(
        config["redirect_uri"],
        expected_state=state,
        provider_name=provider.name,
        bind_host=config.get("callback_bind_host"),
        bind_port=config.get("callback_bind_port"),
        timeout=_callback_timeout(config),
    )
    tokens = exchange_code_for_tokens(provider, config, callback["code"])
    if callback.get("scope"):
        tokens["scope"] = callback["scope"]
    save_tokens(tokens_path, tokens)
    print(f"Saved {provider.name} tokens to {tokens_path}")
