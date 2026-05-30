"""WHOOP API collector."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ...observation_log import (
    log_human_observation_texts,
    log_observations,
    log_raw_records,
    raw_record_for_observation,
)
from ...observer import CollectionResult
from ...paths import HealthSyncPaths, ensure_output_dirs
from ...schema import LOCAL_TZ
from ...source_policy import DEFAULT_ENABLED_SOURCES
from ...state import load_seen_versions, save_seen_versions
from .auth import USER_AGENT, get_valid_access_token, load_tokens, load_whoop_config, ssl_context
from .transform import TransformStats, build_whoop_observations

WHOOP_API_BASE = "https://api.prod.whoop.com/developer"
MAX_PAGES_PER_ENDPOINT = 100
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_WHOOP_POLL_INTERVAL_SECONDS = 30 * 60


@dataclass(frozen=True)
class WhoopEndpoint:
    source: str
    path: str
    scope: str


WHOOP_ENDPOINTS = {
    "whoop.cycle": WhoopEndpoint("whoop.cycle", "/v2/cycle", "read:cycles"),
    "whoop.sleep": WhoopEndpoint("whoop.sleep", "/v2/activity/sleep", "read:sleep"),
    "whoop.recovery": WhoopEndpoint("whoop.recovery", "/v2/recovery", "read:recovery"),
    "whoop.workout": WhoopEndpoint("whoop.workout", "/v2/activity/workout", "read:workout"),
}

DEFAULT_WHOOP_SOURCES = {
    source for source in DEFAULT_ENABLED_SOURCES if source.startswith("whoop.") and source in WHOOP_ENDPOINTS
}


class WhoopObserver:
    """Collect WHOOP observations through the configured WHOOP API credentials."""

    name = "whoop"

    def __init__(self, paths: HealthSyncPaths) -> None:
        self.paths = paths

    def collect(self) -> CollectionResult:
        ensure_output_dirs(self.paths)
        return ingest_whoop_if_configured(self.paths)

    def poll_interval_seconds(self) -> int:
        """Return the configured WHOOP poll interval, falling back to 30 minutes."""
        try:
            data = json.loads(self.paths.config_file.read_text())
            config = data.get("whoop", data)
            value = int(config.get("whoop_poll_interval_seconds") or DEFAULT_WHOOP_POLL_INTERVAL_SECONDS)
            return max(value, 60)
        except Exception:
            return DEFAULT_WHOOP_POLL_INTERVAL_SECONDS


def configured_sources(paths: HealthSyncPaths) -> list[str]:
    try:
        config = load_whoop_config(paths)
    except Exception:
        return []
    sources = config.get("enabled_sources") or sorted(DEFAULT_WHOOP_SOURCES)
    return [
        source
        for source in sources
        if source.startswith("whoop.") and source in WHOOP_ENDPOINTS
    ]


def ingest_whoop_if_configured(paths: HealthSyncPaths) -> CollectionResult:
    if not paths.config_file.exists() or not paths.whoop_tokens_file.exists():
        return CollectionResult(observer_name="whoop")
    try:
        return ingest_whoop(paths=paths)
    except Exception as e:
        message = f"WHOOP ingest skipped: {e}"
        print(f"[watcher] {message}")
        return CollectionResult(observer_name="whoop", failed=1, message=message)


def ingest_whoop(
    *,
    paths: HealthSyncPaths,
    start_date: date | None = None,
    end_date: date | None = None,
    sources: Iterable[str] | None = None,
) -> CollectionResult:
    token = get_valid_access_token(paths)
    if not token:
        return CollectionResult(observer_name="whoop")
    config = load_whoop_config(paths)
    tokens = load_tokens(paths.whoop_tokens_file) or {}

    end_date = end_date or datetime.now(LOCAL_TZ).date()
    start_date = start_date or (end_date - timedelta(days=DEFAULT_LOOKBACK_DAYS))
    source_names = list(sources or configured_sources(paths))
    source_names = sources_allowed_by_scopes(source_names, config=config, tokens=tokens)
    if not source_names:
        return CollectionResult(observer_name="whoop")

    seen_versions = load_seen_versions(paths.seen_versions_file)
    ingested_at = datetime.now(LOCAL_TZ)
    previous_raw = load_previous_raw_records(paths.raw_records_log)
    fetched_records: dict[str, list[dict]] = {}
    new_observations = []
    new_raw_records = []
    failed = 0

    for source in source_names:
        endpoint = WHOOP_ENDPOINTS[source]
        try:
            fetched_records[source] = list(fetch_collection(token, endpoint, start_date=start_date, end_date=end_date))
        except urllib.error.HTTPError as e:
            failed += 1
            print(f"[whoop] skipping {source}: HTTP {e.code} from WHOOP")
        except Exception as e:
            failed += 1
            print(f"[whoop] skipping {source}: {e}")

    transform_stats = TransformStats()
    for observation, raw in build_whoop_observations(
        fetched_records, ingested_at, previous_raw, log=print, stats=transform_stats
    ):
        version = observation_version(observation)
        record_id = observation["metadata"]["record_id"]
        source = observation["source"]
        seen_for_source = seen_versions.setdefault(source, {})
        seen_for_record = seen_for_source.setdefault(record_id, set())
        if isinstance(seen_for_record, str):
            seen_for_record = {seen_for_record}
            seen_for_source[record_id] = seen_for_record
        if version in seen_for_record:
            continue
        seen_for_record.add(version)
        new_observations.append(observation)
        new_raw_records.append(raw_record_for_observation(observation, raw))

    if not new_observations:
        save_seen_versions(paths.seen_versions_file, seen_versions)
        return CollectionResult(observer_name="whoop", skipped=transform_stats.skipped, failed=failed)

    logged = log_observations(paths.observations_log, new_observations)
    log_raw_records(paths.raw_records_log, new_raw_records)
    log_human_observation_texts(paths.observations_md, "whoop", new_observations)
    save_seen_versions(paths.seen_versions_file, seen_versions)
    return CollectionResult(
        observer_name="whoop",
        collected=logged,
        skipped=transform_stats.skipped,
        failed=failed,
    )


def fetch_collection(
    access_token: str,
    endpoint: WhoopEndpoint,
    *,
    start_date: date,
    end_date: date,
) -> Iterable[dict]:
    next_token = None
    page_count = 0
    while True:
        page_count += 1
        if page_count > MAX_PAGES_PER_ENDPOINT:
            raise RuntimeError(f"WHOOP pagination exceeded {MAX_PAGES_PER_ENDPOINT} pages for {endpoint.source}")
        params = date_params(start_date=start_date, end_date=end_date)
        if next_token:
            params["nextToken"] = next_token
        response = get_json(access_token, endpoint.path, params)
        for record in response.get("records", []):
            yield record
        next_token = response.get("next_token")
        if not next_token:
            break


def date_params(*, start_date: date, end_date: date) -> dict[str, str]:
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=LOCAL_TZ)
    end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=LOCAL_TZ)
    return {
        "limit": "25",
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def get_json(access_token: str, path: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    url = f"{WHOOP_API_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
        return json.loads(response.read().decode())


def load_previous_raw_records(path) -> dict[tuple[str, str], dict]:
    """Map (source, record_id) -> last raw payload, for computing cumulative deltas."""
    previous: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return previous
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        source = item.get("source")
        record_id = item.get("record_id")
        raw = item.get("raw")
        if source and record_id and isinstance(raw, dict):
            previous[(source, record_id)] = raw
    return previous


def observation_version(observation: dict) -> str:
    metadata = observation["metadata"]
    record_version = metadata.get("record_version")
    if record_version:
        return str(record_version)
    return str(metadata["raw_hash"])


def sources_allowed_by_scopes(
    sources: Iterable[str],
    *,
    config: dict,
    tokens: dict,
) -> list[str]:
    scopes = granted_scopes(config=config, tokens=tokens)
    allowed = []
    for source in sources:
        endpoint = WHOOP_ENDPOINTS[source]
        if endpoint.scope in scopes:
            allowed.append(source)
            continue
        print(f"[whoop] skipping {source}: missing OAuth scope ({endpoint.scope})")
    return allowed


def granted_scopes(*, config: dict, tokens: dict) -> set[str]:
    token_scope = tokens.get("scope")
    if token_scope:
        return parse_scopes(token_scope)
    return parse_scopes(config.get("scopes") or [])


def parse_scopes(scopes) -> set[str]:
    if isinstance(scopes, str):
        values = scopes.replace(",", " ").split()
    else:
        values = [str(scope) for scope in scopes]
    return {scope for scope in values if scope}


if __name__ == "__main__":
    from ...paths import default_paths

    result = ingest_whoop(paths=default_paths())
    print(
        f"[whoop] appended {result.collected} observations, "
        f"skipped {result.skipped}, failed {result.failed}"
    )
