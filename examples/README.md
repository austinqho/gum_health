# Examples: We push all of the data to a folder in desktop called HealthSync. In that folder, you'll get:
- `raw_records.jsonl`: untouched provider payloads from Apple Health and Oura. This keeps every field the providers send so no data is lost.
- `observations.jsonl`: compact computer-readable observations for GUM/Gumbo. This is not a lossy replacement for raw records; it is the proposition-ready layer. Each row keeps the stable facts, timing, source, metrics, measurement semantics, and a `raw_ref`/`raw_hash` pointer back to the full raw payload.
- `observations.md`: the same observation text in a human-readable form for quick review or text-only proposition prompts.
- `daily_aggregation.md`: an optional derived view that groups one Apple Health day and one Oura day so retroactive observations are easier to read together.

The JSONL files intentionally have no prose header because each line must stay valid JSON. Use this README and the `.md` files for context.

The included examples cover Apple Health steps and these Oura categories: recovery/sleep summary, daily activity, activity classification, workout, and daily stress.

# Observation Structure

`observations.jsonl` is the canonical computer-readable log. Each row includes:

- `id`: HealthSync observation identity.
- `source`: provider stream such as `apple_health.steps` or `oura.daily_stress`.
- `timestamp`: the event time, range start, or local day start in Pacific Time.
- `text`: the proposition-ready factual sentence.
- `metadata`: structured context, including `scope`, `category`, `subtype`,
  `measurement_semantics`, `metrics`, `time_range`, `record_id`,
  `record_version`, `raw_hash`, and `raw_ref`.

# Difference between raw records and observations
When raw records become observations, HealthSync removes provider-specific bulk
and implementation detail from the main prompt surface: long arrays like Oura's
minute-by-minute MET data, opaque contributor/debug fields, nested API objects,
and duplicate source records that are consolidated into one observation. For
example, Oura readiness, sleep, and SpO2 raw records become one
`oura.recovery_sleep_summary` observation. The removed detail is not deleted;
it stays in `raw_records.jsonl` and can be found with `raw_ref` or `raw_hash`.
