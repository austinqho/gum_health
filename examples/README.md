# Examples

We push all the data to `~/Desktop/HealthSync/`. In that folder you'll get the following, and I put real examples from each file in this folder. 

- `raw_records.jsonl`: untouched provider payloads from Apple Health, Oura, and WHOOP. This keeps every field the providers send so no data is lost.
- `observations.jsonl`: compact computer-readable observations for GUM/Gumbo. This is not a lossy replacement for raw records; it is the proposition-ready layer. Each row keeps the stable facts, timing, source, metrics, measurement semantics, and a `raw_ref`/`raw_hash` pointer back to the full raw payload.
- `observations.md`: the same observation text in a human-readable form for quick review or text-only proposition prompts.
- `daily_aggregation.md`: an optional derived view that groups one Apple Health day, one Oura day, and one WHOOP day so retroactive observations are easier to read together.
- `base_reference.json`: the **generic** metric rubric — objective band ranges and each metric's `direction`, the same for everyone. This is the static, hand-editable source (it lives at `src/health_observer/rubric/base_reference.json`); the runtime never overwrites it.
- `full_reference.json` / `full_reference.md`: the **full** metric rubric handed off to the proposition prompt = the generic base reference **plus** this user's per-source personal baselines (HRV, resting heart rate, etc.), computed from `observations.jsonl`. It is **not** an observation; it is a reference scale loaded once as context so band/score meanings and directions live in one place instead of being recited in every observation. JSON is the canonical form; the markdown is a rendered view.

**What the proposition step reads:** just two of these — `observations.jsonl` (the facts) and `full_reference.json` (the rubric that says what each number means). The rest are support: `raw_records.jsonl` is the lossless archive, and `observations.md` / `daily_aggregation.md` are for human review only, never fed to the proposition prompt.

**Why the rubric is two files:** the runtime regenerates `full_reference.json` on every poll (to refresh the per-user baselines), so the authored bands and directions live separately in `base_reference.json` — that way hand-edits to the generic rubric are never clobbered by the refresh. `full_reference.json` = `base_reference.json` + this user's baselines.

The JSONL files intentionally have no prose header because each line must stay valid JSON. Use this README and the `.md` files for context.

The included examples cover Apple Health steps, these Oura categories (recovery/sleep summary, daily activity, activity classification, workout, daily stress), and these WHOOP streams: `whoop.daily_summary` (cycle + recovery + main sleep merged, with final strain folded in at cycle close), `whoop.cycle` (cumulative strain/HR/energy updates with delta-from-previous-poll), `whoop.sleep` (naps), and `whoop.workout`.

## Observation Structure

`observations.jsonl` is the canonical computer-readable log. Each row includes:

- `id`: HealthSync observation identity.
- `source`: provider stream such as `apple_health.steps` or `oura.daily_stress`.
- `timestamp`: the event time, range start, or local day start in Pacific Time.
- `text`: the proposition-ready factual sentence.
- `metadata`: structured context, including `scope`, `category`, `subtype`,
  `measurement_semantics`, `metrics`, `time_range`, `record_id`,
  `record_version`, `raw_hash`, and `raw_ref`.

## Difference between raw records and observations
When raw records become observations, HealthSync removes provider-specific bulk
and implementation detail from the main prompt surface: long arrays like Oura's
minute-by-minute MET data, opaque contributor/debug fields, nested API objects,
and duplicate source records that are consolidated into one observation. For
example, Oura readiness, sleep, and SpO2 raw records become one
`oura.recovery_sleep_summary` observation. The removed detail is not deleted;
it stays in `raw_records.jsonl` and can be found with `raw_ref` or `raw_hash`.

## WHOOP semantics and the rubric
WHOOP is a hybrid: recovery and sleep are absolute morning finals (one snapshot,
never changes), while strain / heart rate / energy are a *cumulative running total*
for the cycle that climbs all day and finalizes when the cycle closes at the next
wake. So per cycle there are two observations:

- `whoop.daily_summary` consolidates the day's recovery + main sleep, and folds in the
  final strain once the cycle closes. It is versioned only on the finalized parts, so
  intra-day strain changes do not churn it.
- `whoop.cycle` is the rolling strain stream: each poll re-emits the current value plus
  how much it moved since the previous observation (`delta_from_previous_observation`),
  the same shape as Oura's cumulative daily totals. Take the latest value; never sum
  the updates.

Cumulative updates (Oura daily totals and stress, WHOOP cycle strain) all use one standard
phrasing produced by `delta_suffix()` in `providers/formatting.py`: `<metric> is now X, up
DELTA from PREV since the previous HealthSync observation` — new value, computed delta, and
prior value, so the proposition maker never has to do the arithmetic. See the
`oura.daily_stress` rows in `observations.jsonl` for a worked example.

A WHOOP "cycle" is a physiological day measured wake-to-wake, not a calendar day; the
cycle id (e.g. `1388233312`) is just the join key linking recovery and sleep to the day.

Some numbers only mean something against a reference. `full_reference.json` carries those
references so they are stated once rather than in every row:
- Objective bands (same for everyone): strain 0-21 (0-9 light ... 18-21 all-out),
  recovery 0-33 red / 34-66 yellow / 67-100 green, Oura scores 0-100.
- Each metric's `direction` (`higher_is_better`, `lower_is_better`, `neutral`,
  `stable_is_normal`) — stated explicitly because conventions conflict: HRV higher is
  better, but resting heart rate lower is better.
- Per-user baselines for metrics with no universal range (HRV, resting heart rate,
  respiratory rate, skin temperature), derived from this user's own history.
