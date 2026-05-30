"""WHOOP OAuth helpers.

Thin provider wrapper over the shared ``oauth_client``. Credentials are read from the
"whoop" section of ~/.healthsync/config.json. Tokens are stored separately in
~/.healthsync/whoop_tokens.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...oauth_client import (
    OAuthError,
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

# WHOOP's API is fronted by Cloudflare, which blocks the default "Python-urllib/x.y"
# User-Agent with a 403 (error 1010). Send an explicit UA so requests reach WHOOP.
USER_AGENT = "healthsync/1.0"

WHOOP_PROVIDER = OAuthProvider(
    name="WHOOP",
    authorize_url="https://api.prod.whoop.com/oauth/oauth2/auth",
    token_url="https://api.prod.whoop.com/oauth/oauth2/token",
    default_scopes=["offline", "read:cycles", "read:sleep", "read:recovery", "read:workout"],
    client_auth="body",  # WHOOP wants client creds in the form body, not a Basic header
    extra_headers={"User-Agent": USER_AGENT},
    refresh_scope="offline",
)

DEFAULT_SCOPES = WHOOP_PROVIDER.default_scopes

# Back-compat aliases: WHOOP previously had its own error types.
WhoopTokenError = OAuthError

__all__ = [
    "USER_AGENT",
    "WHOOP_PROVIDER",
    "WhoopConfigError",
    "WhoopTokenError",
    "build_authorize_url",
    "complete_local_authorization",
    "exchange_code_for_tokens",
    "get_valid_access_token",
    "load_config",
    "load_tokens",
    "load_whoop_config",
    "refresh_tokens",
    "save_tokens",
    "ssl_context",
    "token_needs_refresh",
    "with_expiry",
]


class WhoopConfigError(RuntimeError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise WhoopConfigError(f"WHOOP config not found at {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise WhoopConfigError(f"WHOOP config is not valid JSON: {path}") from e

    config = data.get("whoop", data)
    required = ["client_id", "client_secret", "redirect_uri"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise WhoopConfigError(f"WHOOP config missing required keys: {', '.join(missing)}")
    return config


def load_whoop_config(paths: HealthSyncPaths) -> dict[str, Any]:
    return load_config(paths.config_file)


def build_authorize_url(config: dict[str, Any], state: str | None = None) -> tuple[str, str]:
    return _build_authorize_url(WHOOP_PROVIDER, config, state)


def exchange_code_for_tokens(config: dict[str, Any], code: str) -> dict[str, Any]:
    return _exchange_code_for_tokens(WHOOP_PROVIDER, config, code)


def refresh_tokens(config: dict[str, Any], refresh_token: str) -> dict[str, Any]:
    return _refresh_tokens(WHOOP_PROVIDER, config, refresh_token)


def get_valid_access_token(paths: HealthSyncPaths) -> str | None:
    try:
        config = load_whoop_config(paths)
    except WhoopConfigError:
        return None
    return _get_valid_access_token(WHOOP_PROVIDER, config, paths.whoop_tokens_file)


def complete_local_authorization(paths: HealthSyncPaths | None = None) -> None:
    paths = paths or default_paths()
    config = load_whoop_config(paths)
    _complete_local_authorization(WHOOP_PROVIDER, config, paths.whoop_tokens_file)


if __name__ == "__main__":
    complete_local_authorization()
