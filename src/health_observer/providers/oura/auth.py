"""Oura OAuth helpers.

Credentials are read from ~/.healthsync/config.json by default. Tokens are
stored separately in ~/.healthsync/oura_tokens.json.
"""
from __future__ import annotations

import base64
import json
import secrets
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ...paths import HealthSyncPaths, default_paths

AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
DEFAULT_SCOPES = ["daily", "workout", "spo2", "stress"]
_SSL_CONTEXT = None


class OuraConfigError(RuntimeError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise OuraConfigError(f"Oura config not found at {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise OuraConfigError(f"Oura config is not valid JSON: {path}") from e

    config = data.get("oura", data)
    required = ["client_id", "client_secret", "redirect_uri"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise OuraConfigError(f"Oura config missing required keys: {', '.join(missing)}")
    return config


def load_oura_config(paths: HealthSyncPaths) -> dict[str, Any]:
    return load_config(paths.config_file)


def build_authorize_url(config: dict[str, Any], state: str | None = None) -> tuple[str, str]:
    state = state or secrets.token_urlsafe(24)
    scopes = config.get("scopes") or DEFAULT_SCOPES
    if isinstance(scopes, str):
        scope_value = scopes
    else:
        scope_value = " ".join(scopes)
    query = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": scope_value,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(query)}", state


def _token_request(config: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(form).encode()
    credentials = f"{config['client_id']}:{config['client_secret']}".encode()
    request = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": "Basic " + base64.b64encode(credentials).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
        return json.loads(response.read().decode())


def ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        try:
            import certifi

            _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT


def exchange_code_for_tokens(config: dict[str, Any], code: str) -> dict[str, Any]:
    tokens = _token_request(
        config,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config["redirect_uri"],
        },
    )
    return with_expiry(tokens)


def refresh_tokens(config: dict[str, Any], refresh_token: str) -> dict[str, Any]:
    tokens = _token_request(
        config,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    return with_expiry(tokens)


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


def get_valid_access_token(paths: HealthSyncPaths) -> str | None:
    try:
        config = load_oura_config(paths)
    except OuraConfigError:
        return None
    tokens = load_tokens(paths.oura_tokens_file)
    if not tokens:
        return None
    if token_needs_refresh(tokens):
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return None
        refreshed = refresh_tokens(config, refresh_token)
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = refresh_token
        if "scope" not in refreshed and tokens.get("scope"):
            refreshed["scope"] = tokens["scope"]
        save_tokens(paths.oura_tokens_file, refreshed)
        tokens = refreshed
    return tokens.get("access_token")


def complete_local_authorization(paths: HealthSyncPaths | None = None) -> None:
    from .callback import catch_oauth_callback

    paths = paths or default_paths()
    config = load_oura_config(paths)
    authorize_url, state = build_authorize_url(config)
    print("Open this URL and approve Oura access:")
    print(authorize_url)
    callback = catch_oauth_callback(
        config["redirect_uri"],
        expected_state=state,
        bind_host=config.get("callback_bind_host"),
        bind_port=config.get("callback_bind_port"),
        timeout=_callback_timeout(config),
    )
    tokens = exchange_code_for_tokens(config, callback["code"])
    if callback.get("scope"):
        tokens["scope"] = callback["scope"]
    save_tokens(paths.oura_tokens_file, tokens)
    print(f"Saved Oura tokens to {paths.oura_tokens_file}")


def _callback_timeout(config: dict[str, Any]) -> int | None:
    value = config.get("callback_timeout_seconds")
    if value is None:
        return None
    timeout = int(value)
    return timeout if timeout > 0 else None


if __name__ == "__main__":
    complete_local_authorization()
