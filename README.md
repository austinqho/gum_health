# HealthSync

A wearables module for [GUM](https://generalusermodels.github.io/gum/docs/). It turns Apple
Health, Oura, and WHOOP data into GUM-style **observations** — an append-only log of
`id / source / timestamp / text / metadata` rows, normalized deterministically (no LLM), with the
untouched provider payloads archived alongside. Apple arrives via an iOS Shortcut; Oura and WHOOP
are polled locally. Nothing leaves the machine.

The handoff boundary is the observation row: embed the portable core and call `collect_once()`,
or run the bundled Mac watcher.

Each pipeline is proven against real data: the Apple Health and Oura pipelines (including the
optional Oura webhook integration) have been validated with real user data, and so has the WHOOP
collector end-to-end through a real-user OAuth flow.

One observation row (Apple step sample; `metadata` abbreviated):

```json
{
  "id": "healthsync:v1:apple_health.steps:2026-05-26T21:56:00-07:00",
  "source": "apple_health.steps",
  "timestamp": "2026-05-26T21:56:00-07:00",
  "text": "Apple Health recorded a completed step-count sample of 135 steps at 9:56 PM PT on May 26, 2026.",
  "metadata": {"scope": "point", "metrics": {"steps": {"value": 135, "unit": "count"}}, "measurement_semantics": "completed_step_sample", "raw_ref": "...", "raw_hash": "..."}
}
```

## Use

```bash
python3 -m pip install -e ".[mac,oura,whoop]"
```

```python
from health_observer import collect_once
from health_observer.paths import default_paths
from health_observer.providers.apple.shortcut import AppleShortcutObserver
from health_observer.providers.oura.api import OuraObserver
from health_observer.providers.whoop.api import WhoopObserver

p = default_paths()
collect_once([AppleShortcutObserver(p), OuraObserver(p), WhoopObserver(p)])
```

Each observer reads its source, dedups against local state, and appends to
`~/Desktop/HealthSync/`: `observations.jsonl`, `raw_records.jsonl`, and `observations.md`. The
Mac watcher additionally derives `daily_aggregation.md` and `full_reference.json` after each
poll; embedders call `write_daily_aggregation()` / `write_rubric()` to refresh those.

## Setup

- **Apple** — install the [iOS Shortcut](https://www.icloud.com/shortcuts/b8665257c33b4be59e165439d27080a6),
  allow large-data sharing (in Settings -> Shortcuts), add an Automation that runs it (either whenever you open a given app like iMessage, or set to run at a specific time), run once, then double-click `HealthSync.command`.
- **Oura / WHOOP** — copy `config.example.json` → `~/.healthsync/config.json`, fill in credentials,
  then authorize each provider: `python3 -m health_observer.providers.oura.auth` and
  `python3 -m health_observer.providers.whoop.auth`. The watcher then polls every 30 min.
- **Hosted Oura (optional)** — if you prefer webhooks to local polling, `oura-webhook-integration/` is a
  Vercel/Supabase reference for hosted Oura OAuth/webhooks. 

## Layout

**Port map** — portable core (lift as-is): `schema` / `observer` / `collection` /
`observation_log` / `state` / `source_policy` / `rubric` / `providers`. Mac-specific delivery
(replace with your own scheduler/storage): `runtime/mac.py` + `HealthSync.command`.

- `providers/*` — per-provider OAuth, polling, and transforms (Apple, Oura, WHOOP)
- `oauth_client.py` — the one OAuth2 lifecycle both Oura and WHOOP wrap
- `rubric/` — the metric rubric: generic `base_reference.json` → per-user `full_reference.json`
- `source_policy.py` — the single file declaring what's collected / optional / skipped
- `examples/` — real output rows for every stream, with notes on provider semantics
- `docs/health_observer_api_mapping.md` — provider field mapping
- `oura-webhook-integration/` — optional, separate Vercel/Supabase reference for hosted Oura OAuth/webhooks (not part of the local pipeline)

## Tests

```bash
python3 -m pip install -e ".[test]" && python3 -m pytest
```

Every transform and derived artifact has a golden/render assertion, so a formatting change fails
a test instead of silently shipping.

## License

MIT
