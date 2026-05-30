"""Oura API collector."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from ...observation_log import (
    log_human_observation_texts,
    log_observations,
    log_raw_records,
    raw_record_for_observation,
)
from ...observer import CollectionResult
from ...paths import HealthSyncPaths, ensure_output_dirs
from ...source_policy import DEFAULT_ENABLED_SOURCES
from ...schema import LOCAL_TZ
from ...state import load_seen_versions, save_seen_versions
from .auth import get_valid_access_token, load_oura_config, load_tokens, ssl_context
from .transform import TransformStats, build_oura_observations

OURA_API_BASE = "https://api.ouraring.com"
MAX_PAGES_PER_ENDPOINT = 100


@dataclass(frozen=True)
class OuraEndpoint:
    source: str
    path: str
    time_params: str


DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_OURA_POLL_INTERVAL_SECONDS = 30 * 60

OURA_ENDPOINTS = {
    "oura.daily_activity": OuraEndpoint("oura.daily_activity", "/v2/usercollection/daily_activity", "date"),
    "oura.daily_readiness": OuraEndpoint("oura.daily_readiness", "/v2/usercollection/daily_readiness", "date"),
    "oura.daily_sleep": OuraEndpoint("oura.daily_sleep", "/v2/usercollection/daily_sleep", "date"),
    "oura.sleep": OuraEndpoint("oura.sleep", "/v2/usercollection/sleep", "date"),
    "oura.daily_spo2": OuraEndpoint("oura.daily_spo2", "/v2/usercollection/daily_spo2", "date"),
    "oura.workout": OuraEndpoint("oura.workout", "/v2/usercollection/workout", "date"),
    "oura.heartrate": OuraEndpoint("oura.heartrate", "/v2/usercollection/heartrate", "datetime"),
    "oura.session": OuraEndpoint("oura.session", "/v2/usercollection/session", "date"),
    "oura.tag": OuraEndpoint("oura.tag", "/v2/usercollection/tag", "date"),
    "oura.enhanced_tag": OuraEndpoint("oura.enhanced_tag", "/v2/usercollection/enhanced_tag", "date"),
    "oura.daily_stress": OuraEndpoint("oura.daily_stress", "/v2/usercollection/daily_stress", "date"),
    "oura.daily_resilience": OuraEndpoint("oura.daily_resilience", "/v2/usercollection/daily_resilience", "date"),
    "oura.daily_cardiovascular_age": OuraEndpoint(
        "oura.daily_cardiovascular_age",
        "/v2/usercollection/daily_cardiovascular_age",
        "date",
    ),
    "oura.vo2_max": OuraEndpoint("oura.vo2_max", "/v2/usercollection/vO2_max", "date"),
}

DEFAULT_OURA_SOURCES = {
    source for source in DEFAULT_ENABLED_SOURCES if source.startswith("oura.") and source in OURA_ENDPOINTS
}

SOURCE_SCOPE_OPTIONS = {
    "oura.daily_activity": ({"daily"},),
    "oura.daily_readiness": ({"daily"},),
    "oura.daily_sleep": ({"daily"},),
    "oura.sleep": ({"daily"},),
    "oura.daily_stress": ({"stress"}, {"daily"}),
    "oura.daily_spo2": ({"spo2"}, {"spo2Daily"}),
    "oura.workout": ({"workout"},),
    "oura.heartrate": ({"heartrate"},),
    "oura.session": ({"session"},),
    "oura.tag": ({"tag"},),
    "oura.enhanced_tag": ({"tag"},),
    "oura.daily_resilience": ({"daily"},),
    "oura.daily_cardiovascular_age": ({"daily"},),
    "oura.vo2_max": ({"workout"}, {"daily"}),
}


class OuraObserver:
    """Collect Oura observations through the configured Oura API credentials."""

    name = "oura"

    def __init__(self, paths: HealthSyncPaths) -> None:
        self.paths = paths

    def collect(self) -> CollectionResult:
        ensure_output_dirs(self.paths)
        return ingest_oura_if_configured(self.paths)

    def poll_interval_seconds(self) -> int:
        """Return the configured Oura poll interval, falling back to 30 minutes."""
        try:
            data = json.loads(self.paths.config_file.read_text())
            config = data.get("oura", data)
            value = int(config.get("oura_poll_interval_seconds") or DEFAULT_OURA_POLL_INTERVAL_SECONDS)
            return max(value, 60)
        except Exception:
            return DEFAULT_OURA_POLL_INTERVAL_SECONDS


def configured_sources(paths: HealthSyncPaths) -> list[str]:
    try:
        config = load_oura_config(paths)
    except Exception:
        return []
    sources = config.get("enabled_sources") or sorted(DEFAULT_OURA_SOURCES)
    return [
        source
        for source in sources
        if source.startswith("oura.") and source in OURA_ENDPOINTS
    ]


def ingest_oura_if_configured(paths: HealthSyncPaths) -> CollectionResult:
    if not paths.config_file.exists() or not paths.oura_tokens_file.exists():
        return CollectionResult(observer_name="oura")
    try:
        return ingest_oura(paths=paths)
    except Exception as e:
        message = f"Oura ingest skipped: {e}"
        print(f"[watcher] {message}")
        return CollectionResult(observer_name="oura", failed=1, message=message)


def ingest_oura(
    *,
    paths: HealthSyncPaths,
    start_date: date | None = None,
    end_date: date | None = None,
    sources: Iterable[str] | None = None,
) -> CollectionResult:
    token = get_valid_access_token(paths)
    if not token:
        return CollectionResult(observer_name="oura")
    config = load_oura_config(paths)
    tokens = load_tokens(paths.oura_tokens_file) or {}

    end_date = end_date or datetime.now(LOCAL_TZ).date()
    start_date = start_date or (end_date - timedelta(days=DEFAULT_LOOKBACK_DAYS))
    source_names = list(sources or configured_sources(paths))
    source_names = sources_allowed_by_scopes(source_names, config=config, tokens=tokens)
    if not source_names:
        return CollectionResult(observer_name="oura")

    seen_versions = load_seen_versions(paths.seen_versions_file)
    ingested_at = datetime.now(LOCAL_TZ)
    previous_raw = load_previous_raw_records(paths.raw_records_log)
    fetched_records: dict[str, list[dict]] = {}
    new_observations = []
    new_raw_records = []
    failed = 0

    for source in source_names:
        endpoint = OURA_ENDPOINTS[source]
        try:
            fetched_records[source] = list(fetch_collection(token, endpoint, start_date=start_date, end_date=end_date))
        except urllib.error.HTTPError as e:
            failed += 1
            print(f"[oura] skipping {source}: HTTP {e.code} from Oura")
        except Exception as e:
            failed += 1
            print(f"[oura] skipping {source}: {e}")

    transform_stats = TransformStats()
    for observation, raw in build_oura_observations(
        fetched_records,
        ingested_at,
        previous_raw,
        log=print,
        stats=transform_stats,
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
        return CollectionResult(observer_name="oura", skipped=transform_stats.skipped, failed=failed)

    logged = log_observations(paths.observations_log, new_observations)
    log_raw_records(paths.raw_records_log, new_raw_records)
    log_human_observation_texts(paths.observations_md, "oura", new_observations)
    save_seen_versions(paths.seen_versions_file, seen_versions)
    return CollectionResult(
        observer_name="oura",
        collected=logged,
        skipped=transform_stats.skipped,
        failed=failed,
    )


def fetch_collection(
    access_token: str,
    endpoint: OuraEndpoint,
    *,
    start_date: date,
    end_date: date,
) -> Iterable[dict]:
    next_token = None
    page_count = 0
    while True:
        page_count += 1
        if page_count > MAX_PAGES_PER_ENDPOINT:
            raise RuntimeError(f"Oura pagination exceeded {MAX_PAGES_PER_ENDPOINT} pages for {endpoint.source}")
        params = date_params(endpoint, start_date=start_date, end_date=end_date)
        if next_token:
            params["next_token"] = next_token
        response = get_json(access_token, endpoint.path, params)
        for record in response.get("data", []):
            yield record
        next_token = response.get("next_token")
        if not next_token:
            break


def date_params(endpoint: OuraEndpoint, *, start_date: date, end_date: date) -> dict[str, str]:
    if endpoint.time_params == "datetime":
        start = datetime.combine(start_date, datetime.min.time(), tzinfo=LOCAL_TZ)
        end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=LOCAL_TZ)
        return {"start_datetime": start.isoformat(), "end_datetime": end.isoformat()}
    return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}


def get_json(access_token: str, path: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    url = f"{OURA_API_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
        return json.loads(response.read().decode())


def observation_version(observation: dict) -> str:
    metadata = observation["metadata"]
    record_version = metadata.get("record_version")
    if record_version:
        return str(record_version)
    return str(metadata["raw_hash"])


def load_previous_raw_records(path) -> dict[tuple[str, str], dict]:
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


def sources_allowed_by_scopes(
    sources: Iterable[str],
    *,
    config: dict,
    tokens: dict,
) -> list[str]:
    scopes = granted_scopes(config=config, tokens=tokens)
    allowed = []
    for source in sources:
        if source_has_required_scope(source, scopes):
            allowed.append(source)
            continue
        options = SOURCE_SCOPE_OPTIONS.get(source) or ()
        needed = " or ".join(" + ".join(sorted(option)) for option in options) or "unknown"
        print(f"[oura] skipping {source}: missing OAuth scope ({needed})")
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
    return {scope.removeprefix("extapi:") for scope in values if scope}


def source_has_required_scope(source: str, scopes: set[str]) -> bool:
    options = SOURCE_SCOPE_OPTIONS.get(source)
    if not options:
        return True
    return any(option <= scopes for option in options)


if __name__ == "__main__":
    from ...paths import default_paths

    result = ingest_oura(paths=default_paths())
    print(
        f"[oura] appended {result.collected} observations, "
        f"skipped {result.skipped}, failed {result.failed}"
    )
