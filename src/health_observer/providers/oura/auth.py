"""Oura OAuth helpers.

Thin provider wrapper over the shared ``oauth_client``. Credentials are read from
~/.healthsync/config.json by default. Tokens are stored separately in
~/.healthsync/oura_tokens.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...oauth_client import (
    OAuthProvider,
    load_tokens,
    save_tokens,
    ssl_context,
    token_needs_refresh,
    with_expiry,
)
from ...oauth_client import build_authorize_url as _build_authorize_url
from ...oauth_client import complete_local_authorization as _complete_local_authorization
from ...oauth_client import exchange_code_for_tokens as _exchange_code_for_tokens
from ...oauth_client import get_valid_access_token as _get_valid_access_token
from ...oauth_client import refresh_tokens as _refresh_tokens
from ...paths import HealthSyncPaths, default_paths

OURA_PROVIDER = OAuthProvider(
    name="Oura",
    authorize_url="https://cloud.ouraring.com/oauth/authorize",
    token_url="https://api.ouraring.com/oauth/token",
    default_scopes=["daily", "workout", "spo2", "stress"],
    client_auth="basic",  # Oura authenticates the client with a Basic header
)

DEFAULT_SCOPES = OURA_PROVIDER.default_scopes

__all__ = [
    "OURA_PROVIDER",
    "OuraConfigError",
    "build_authorize_url",
    "complete_local_authorization",
    "exchange_code_for_tokens",
    "get_valid_access_token",
    "load_config",
    "load_oura_config",
    "load_tokens",
    "refresh_tokens",
    "save_tokens",
    "ssl_context",
    "token_needs_refresh",
    "with_expiry",
]


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
    return _build_authorize_url(OURA_PROVIDER, config, state)


def exchange_code_for_tokens(config: dict[str, Any], code: str) -> dict[str, Any]:
    return _exchange_code_for_tokens(OURA_PROVIDER, config, code)


def refresh_tokens(config: dict[str, Any], refresh_token: str) -> dict[str, Any]:
    return _refresh_tokens(OURA_PROVIDER, config, refresh_token)


def get_valid_access_token(paths: HealthSyncPaths) -> str | None:
    try:
        config = load_oura_config(paths)
    except OuraConfigError:
        return None
    return _get_valid_access_token(OURA_PROVIDER, config, paths.oura_tokens_file)


def complete_local_authorization(paths: HealthSyncPaths | None = None) -> None:
    paths = paths or default_paths()
    config = load_oura_config(paths)
    _complete_local_authorization(OURA_PROVIDER, config, paths.oura_tokens_file)


if __name__ == "__main__":
    complete_local_authorization()
