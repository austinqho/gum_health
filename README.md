## HealthSync

HealthSync turns Apple Health and Oura data into GUM/Gumbo-style observations.
The core output is an append-only observation log:

```text
id / source / timestamp / text / metadata
```

No LLM writes the observations. Provider records are normalized
deterministically, and the untouched provider payloads are kept separately.
Apple Health comes in through an iOS Shortcut the user installs; Oura is polled
from the user's own machine. Both paths keep data local; nothing is held on a
server.

## Architecture

| Layer | Files | Responsibility | How Gumbo uses it |
| --- | --- | --- | --- |
| Portable core | `src/health_observer/schema.py`, `observer.py`, `collection.py`, `observation_log.py`, `state.py`, `source_policy.py`, `daily_aggregation.py`, `providers/*` | Defines the observation schema, allowed source list, dedup state, provider transforms, derived aggregation, and log writers. | Embed and reuse as-is; call `collect_once()`. |
| Mac delivery | `HealthSync.command`, `src/health_observer/runtime/mac.py`, iCloud paths, LaunchAgent setup | Runs the core on one Mac: watches Apple iCloud snapshots, polls Oura every 30 mins, refreshes `daily_aggregation.md`, and keeps the process alive. | Replace with Gumbo's own scheduler/runtime and local storage paths. |

The important handoff boundary is the observation row. The Mac watcher is only
one way to produce and append those rows.

Start here: `from health_observer import collect_once`.

`source_policy.py` is intentionally central. It declares exactly which
Apple/Oura data types HealthSync collects by default, leaves optional, or
intentionally skips. When WHOOP or more Apple Health types are added, reviewers
should be able to inspect that one file and see exactly what is tracked.

## Provider Flows

Apple Health:

```text
iOS Shortcut exports step samples
-> iCloud Drive rolling snapshot
-> Mac watcher reads only new samples
-> apple/transform.py emits one observation per completed step sample
```

Oura:

```text
Oura OAuth token
-> Oura API polling
-> oura/api.py fetches enabled endpoints
-> oura/transform.py emits compact day/range observations
```

Current Oura observations include recovery/sleep summary, daily activity,
activity classification windows, workouts, and daily stress.

Caveats: daily activity and stress are cumulative provider-day updates, not
incremental samples. Oura workouts have exact time ranges, but daily stress does
not expose exact stress intervals. Oura activity classification gives 5-minute
low/medium/high timing context, not exact step counts.

## Output Files

Local output lives at `~/Desktop/HealthSync/`:

```text
observations.jsonl       canonical append-only observation log
raw_records.jsonl        untouched provider payload archive
observations.md          human-readable observation text
daily_aggregation.md     optional derived day view
```

`raw_records.jsonl` keeps every provider field. `observations.jsonl` keeps the
facts the proposition layer needs: timing, source, text, normalized metrics,
measurement semantics, and a `raw_ref`/`raw_hash` pointer back to raw.

When raw records become observations, HealthSync removes provider-specific bulk
from the prompt surface: long arrays, nested API objects, opaque contributor
fields, debug fields, and multiple raw records that were consolidated into one
observation. The removed detail is not deleted; it stays in `raw_records.jsonl`.

`daily_aggregation.md` is derived from `observations.jsonl`. It is an optional
daily view that groups retroactive updates into one readable place. The Mac
runtime writes it automatically; embedders can call `write_daily_aggregation()`
when they want this extra view.

## Observation Shape

Apple point sample:

```json
{
  "id": "healthsync:v1:apple_health.steps:2026-05-26T21:56:00-07:00",
  "source": "apple_health.steps",
  "timestamp": "2026-05-26T21:56:00-07:00",
  "text": "Apple Health recorded a completed step-count sample of 135 steps at 9:56 PM PT on May 26, 2026.",
  "metadata": {
    "provider": "apple_health",
    "scope": "point",
    "category": "activity",
    "subtype": "steps",
    "record_id": "apple_health.steps:2026-05-26T21:56:00-07:00",
    "record_version": null,
    "timezone": "America/Los_Angeles",
    "granularity": "sample",
    "time_range": null,
    "ingested_at": "2026-05-26T22:45:00-07:00",
    "units": {"steps": "count"},
    "metrics": {"steps": {"value": 135, "unit": "count"}},
    "raw_ref": "apple_health.steps:2026-05-26T21:56:00-07:00:sha256:...",
    "raw_hash": "sha256:...",
    "measurement_semantics": "completed_step_sample"
  }
}
```

Oura cumulative day update:

```json
{
  "id": "healthsync:v1:oura.daily_activity:activity-record-id:sha256:...",
  "source": "oura.daily_activity",
  "timestamp": "2026-05-28T00:00:00-07:00",
  "text": "Oura daily activity update for 2026-05-28, observed by HealthSync at 12:25 AM PT on May 29, 2026: daily step total is now 3,932, active calories expended are now 204, total calories expended are now 2,120, activity score is 70. Oura daily activity totals are cumulative for the Oura day, not incremental samples.",
  "metadata": {
    "provider": "oura",
    "scope": "day",
    "category": "activity",
    "subtype": "daily_activity",
    "record_id": "activity-record-id",
    "record_version": "sha256:...",
    "timezone": "America/Los_Angeles",
    "granularity": "day",
    "time_range": null,
    "ingested_at": "2026-05-29T00:25:00-07:00",
    "metrics": {
      "steps": {"value": 3932, "unit": "count"},
      "active_calories": {"value": 204, "unit": "kilocalorie"},
      "total_calories": {"value": 2120, "unit": "kilocalorie"},
      "activity_score": {"value": 70, "unit": "score"}
    },
    "raw_ref": "oura.daily_activity:activity-record-id:sha256:...",
    "raw_hash": "sha256:...",
    "measurement_semantics": "daily_activity_cumulative_update"
  }
}
```

## Embedding

Gumbo can call the portable collector directly. Calling `collect_once(...)`
runs each observer one time. Each observer reads its source, dedups against
local state, appends new rows to `observations.jsonl` and `raw_records.jsonl`,
updates `observations.md`, and returns a `CollectionResult` with collected,
skipped, and failed counts.

```python
from health_observer import collect_once
from health_observer.paths import default_paths
from health_observer.providers.apple.shortcut import AppleShortcutObserver
from health_observer.providers.oura.api import OuraObserver

paths = default_paths()
results = collect_once([AppleShortcutObserver(paths), OuraObserver(paths)], log=None)
```

The Mac watcher calls this same core API repeatedly from `runtime/mac.py`.

## Local Setup

Install for tests:

```bash
python3 -m pip install -e ".[test]"
```

Install for the Mac watcher:

```bash
python3 -m pip install -e ".[mac,oura]"
```

Apple setup:

1. Install the iOS Shortcut:
   `https://www.icloud.com/shortcuts/b8665257c33b4be59e165439d27080a6`
2. Enable `Settings -> Apps -> Shortcuts -> Advanced -> Allow Sharing Large Amounts of Data`.
3. In Shortcuts -> Automation, create automations that run the HealthSync
   Shortcut automatically. Use "Run Immediately" and turn notifications off.
   Example triggers: run at given times of day, when waking up, when opening an app, or a few
   fixed times throughout the day. Your laptop doesn't need to be on to sync, it'll do it automatically
4. Run the Shortcut once manually to create the first iCloud snapshot.
5. Double-click `HealthSync.command` on the Mac.

Oura setup:

1. Create `~/.healthsync/config.json` from `config.example.json`.
2. Run OAuth once:

```bash
PYTHONPATH=src python3 -m health_observer.providers.oura.auth
```

3. The watcher polls Oura automatically when `config.json` and
   `oura_tokens.json` exist. Manual poll:

```bash
PYTHONPATH=src python3 -m health_observer.providers.oura.api
```

Default Oura polling runs every 30 minutes and looks back 90 days.

## Optional Hosted Oura Reference

`oura-webhook-integration/` is separate from the default local pipeline. It is a
Vercel/Supabase reference for hosted OAuth/webhooks. The canonical transform is
still the Python local transform in `src/health_observer/providers/oura/transform.py`.

Use it only if Gumbo wants a central webhook deployment. The default HealthSync
path is local polling, which keeps data on the participant machine.

## Key Files

- `src/health_observer/schema.py`: canonical observation shape and validation
- `src/health_observer/collection.py`: embeddable `collect_once` API
- `src/health_observer/daily_aggregation.py`: optional derived daily markdown view
- `src/health_observer/observer.py`: Observer protocol and `CollectionResult`
- `src/health_observer/observation_log.py`: writes observations, raw records, and markdown
- `src/health_observer/state.py`: timestamp/version dedup state
- `src/health_observer/source_policy.py`: allowed source list for enabled, optional, and skipped data types
- `src/health_observer/providers/apple/*`: Apple Shortcut reader and transform
- `src/health_observer/providers/oura/*`: Oura OAuth, API polling, and transform
- `src/health_observer/providers/formatting.py`: shared provider formatting/unit helpers
- `src/health_observer/runtime/mac.py`: local Mac watch/poll loop
- `examples/`: small real output fixtures
- `docs/health_observer_api_mapping.md`: Oura mapping notes and future WHOOP notes

## Not Included

- Direct private Gumbo API calls
- Apple Health data beyond step samples
- A validated WHOOP collector

## License

MIT
