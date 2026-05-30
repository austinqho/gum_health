# Health Observer API Mapping

This file is the working reference for turning wearable provider records into
GUM/Gumbo-style factual observations.

Local source documents checked:

- `oura.json`: official Oura OpenAPI 3.1 document, title `Oura API Documentation`, version `2.0`.
- `whoop.pdf`: PDF rendering of WHOOP OpenAPI document, title `WHOOP API`.
- `gum.pdf`: GUM paper. The paper states that each observation includes source, timestamp, and a unique identifier, and that observations are factual records rather than inferences.

## Canonical Health Observation

Every provider record/sample should become one JSONL line:

```json
{
  "id": "stable unique string",
  "source": "provider.metric",
  "timestamp": "primary Pacific Time event timestamp in ISO 8601",
  "text": "factual natural-language observation",
  "metadata": {
    "provider": "apple_health | oura | whoop",
    "scope": "point | range | day | system",
    "category": "activity | sleep | recovery | readiness | heart_rate | oxygen | stress | device | profile",
    "subtype": "source-specific subtype",
    "record_id": "provider record identity",
    "record_version": "provider updated_at/version marker, or null",
    "timezone": "America/Los_Angeles",
    "granularity": "sample | instant | interval | day | event",
    "time_range": null,
    "ingested_at": "when HealthSync wrote the observation",
    "units": {},
    "metrics": {},
    "raw_ref": "pointer to raw_records.jsonl",
    "raw_hash": "sha256 hash of untouched provider payload"
  }
}
```

Rules:

- `id` is deterministic and stable. Prefer the provider object ID when one exists; otherwise derive from source plus timestamp/date.
- `id` is the HealthSync observation identity. It may include a version marker so changed provider records can be appended without overwriting history.
- `metadata.record_id` is the provider object identity. It can match `id` for immutable records, but remains stable across updated versions of the same provider record.
- `source` is specific enough to filter, e.g. `oura.daily_activity`, not just `oura`.
- `timestamp` is the time the health event refers to, not the time HealthSync fetched it. Translate provider timestamps to Pacific Time for this repo.
- For `metadata.scope = "point"`, `timestamp` is the sample/instant time.
- For `metadata.scope = "range"`, `timestamp` is the range start and `metadata.time_range` contains `{ "start": "...", "end": "..." }`.
- For `metadata.scope = "day"`, `timestamp` is local day start in Pacific Time and `metadata.granularity` is `day`.
- `text` must stay factual. Do not infer stress, illness, intent, discipline, habits, or causality here. GUM's Propose module can infer later.
- `metadata.raw_ref` and `metadata.raw_hash` point to the original provider
  record in `raw_records.jsonl` for grounding/debugging. Keep the observation
  compact; do not embed dense provider payloads directly in `observations.jsonl`.
- Normalize human-facing text to US-friendly units where useful, such as miles for distance, while preserving original provider units and converted values in `metadata.metrics`.

## Oura Cross-Checks

Oura auth and access:

- `oura.json` says the API is Oura API V2 and V1 has been sunset.
- `oura.json` says personal access tokens were deprecated in December 2025 and are no longer available.
- `oura.json` defines OAuth2 authorization code auth at `https://cloud.ouraring.com/oauth/authorize` and token URL `https://api.ouraring.com/oauth/token`.
- `oura.json` also defines Bearer auth for API requests.
- `oura.json` scopes: `email`, `personal`, `daily`, `heartrate`, `workout`, `tag`, `session`, `spo2Daily`.
- `oura.json` recommends webhooks: one historical request when the user connects, then webhook notifications for ongoing updates.
- `oura.json` says webhook notifications arrive approximately 30 seconds after data syncs from the mobile app.
- `oura.json` rate limit: 5000 requests per 5-minute period.
- `oura.json` says API applications are limited to 10 users before approval from Oura.

Oura collection response shape:

- Multi-document endpoints use `data` and `next_token`.
- Most multi-document endpoints accept `start_date`, `end_date`, `next_token`, and `fields`.
- Time-series endpoints `heartrate` and `ring_battery_level` accept `start_datetime`, `end_datetime`, `next_token`, `latest`, and `fields`.

### `oura.daily_activity`

Endpoint:

- `GET /v2/usercollection/daily_activity`
- `GET /v2/usercollection/daily_activity/{document_id}`

Schema checked:

- `PublicDailyActivity`
- Required fields in `oura.json`: `id`, `active_calories`, `average_met_minutes`, `contributors`, `day`, `equivalent_walking_distance`, `high_activity_met_minutes`, `high_activity_time`, `inactivity_alerts`, `low_activity_met_minutes`, `low_activity_time`, `medium_activity_met_minutes`, `medium_activity_time`, `met`, `meters_to_target`, `non_wear_time`, `resting_time`, `sedentary_met_minutes`, `sedentary_time`, `steps`, `target_calories`, `target_meters`, `timestamp`, `total_calories`.
- Optional fields in `oura.json`: `class_5_min`, `score`.
- Contributor fields checked: `meet_daily_targets`, `move_every_hour`, `recovery_time`, `stay_active`, `training_frequency`, `training_volume`.

Observation mapping:

```json
{
  "id": "healthsync:v1:oura.daily_activity:{record.id}:{record_version}",
  "source": "oura.daily_activity",
  "timestamp": "{record.day}T00:00:00-08:00",
  "text": "Oura daily activity update for {day}, observed by HealthSync at {ingested_at}: daily step total is now {steps}, active calories expended are now {active_calories}, total calories expended are now {total_calories}, activity score is {score}. Oura daily activity totals are cumulative for the Oura day, not incremental samples.",
  "metadata": {
    "provider": "oura",
    "scope": "day",
    "granularity": "day",
    "measurement_semantics": "daily_activity_cumulative_update",
    "metrics": {
      "steps": {"value": "{record.steps}", "unit": "count"},
      "active_calories": {"value": "{record.active_calories}", "unit": "kilocalorie"},
      "total_calories": {"value": "{record.total_calories}", "unit": "kilocalorie"},
      "activity_score": {"value": "{record.score}", "unit": "score"}
    },
    "contributors": "{record.contributors}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- `steps`, `active_calories`, and `total_calories` are cumulative Oura-day totals, not incremental samples. Do not sum `oura.daily_activity` observations across the log.
- `record.timestamp` is useful as the provider update/version timestamp, but the observation `timestamp` should be the local day start for day-level filtering.
- Parse `class_5_min` into separate `oura.activity_classification` range observations. Those intervals give 5-minute activity-intensity timing context, not exact step-count intervals.

### `oura.daily_readiness`

Endpoint:

- `GET /v2/usercollection/daily_readiness`
- `GET /v2/usercollection/daily_readiness/{document_id}`

Schema checked:

- `PublicDailyReadiness`
- Required fields: `id`, `contributors`, `day`, `timestamp`.
- Optional fields: `score`, `temperature_deviation`, `temperature_trend_deviation`.
- Contributor fields checked: `activity_balance`, `body_temperature`, `hrv_balance`, `previous_day_activity`, `previous_night`, `recovery_index`, `resting_heart_rate`, `sleep_balance`, `sleep_regularity`.

Observation mapping:

```json
{
  "id": "oura.daily_readiness:{record.id}",
  "source": "oura.daily_readiness",
  "timestamp": "{record.timestamp}",
  "text": "Oura recorded readiness score {score} for {day}, with temperature deviation {temperature_deviation} C and temperature trend deviation {temperature_trend_deviation} C.",
  "metadata": {
    "provider": "oura",
    "day": "{record.day}",
    "score": "{record.score}",
    "temperature_deviation_c": "{record.temperature_deviation}",
    "temperature_trend_deviation_c": "{record.temperature_trend_deviation}",
    "contributors": "{record.contributors}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- Do not turn readiness into advice in the observation text.
- If score or temperature fields are null, omit that phrase from `text`.

### `oura.daily_sleep`

Endpoint:

- `GET /v2/usercollection/daily_sleep`
- `GET /v2/usercollection/daily_sleep/{document_id}`

Schema checked:

- `PublicDailySleep`
- Required fields: `id`, `contributors`, `day`, `timestamp`.
- Optional field: `score`.
- Contributor fields checked: `deep_sleep`, `efficiency`, `latency`, `rem_sleep`, `restfulness`, `timing`, `total_sleep`.

Observation mapping:

```json
{
  "id": "oura.daily_sleep:{record.id}",
  "source": "oura.daily_sleep",
  "timestamp": "{record.timestamp}",
  "text": "Oura recorded sleep score {score} for {day}.",
  "metadata": {
    "provider": "oura",
    "day": "{record.day}",
    "score": "{record.score}",
    "contributors": "{record.contributors}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- This is a score/contributor summary. Detailed sleep intervals come from `oura.sleep`.

### `oura.sleep`

Endpoint:

- `GET /v2/usercollection/sleep`
- `GET /v2/usercollection/sleep/{document_id}`

Schema checked:

- `PublicModifiedSleepModel`
- Required fields: `id`, `bedtime_end`, `bedtime_start`, `day`, `low_battery_alert`, `period`, `time_in_bed`.
- Optional fields include `average_breath`, `average_heart_rate`, `average_hrv`, `awake_time`, `deep_sleep_duration`, `efficiency`, `heart_rate`, `hrv`, `latency`, `light_sleep_duration`, `lowest_heart_rate`, `movement_30_sec`, `readiness`, `readiness_score_delta`, `rem_sleep_duration`, `restless_periods`, `ring_id`, `sleep_algorithm_version`, `sleep_analysis_reason`, `sleep_phase_30_sec`, `sleep_phase_5_min`, `sleep_score_delta`, `total_sleep_duration`, `type`.
- Time-series samples use `PublicSample`: `interval`, `items`, `timestamp`.

Observation mapping:

```json
{
  "id": "oura.sleep:{record.id}",
  "source": "oura.sleep",
  "timestamp": "{record.bedtime_start}",
  "text": "Oura recorded a sleep period from {bedtime_start} to {bedtime_end}, with {total_sleep_duration} seconds asleep, {time_in_bed} seconds in bed, efficiency {efficiency}, average HRV {average_hrv} ms, average heart rate {average_heart_rate} bpm, and lowest heart rate {lowest_heart_rate} bpm.",
  "metadata": {
    "provider": "oura",
    "scope": "range",
    "time_range": {
      "start": "{record.bedtime_start}",
      "end": "{record.bedtime_end}"
    },
    "day": "{record.day}",
    "type": "{record.type}",
    "time_in_bed_seconds": "{record.time_in_bed}",
    "total_sleep_seconds": "{record.total_sleep_duration}",
    "efficiency": "{record.efficiency}",
    "average_hrv_ms": "{record.average_hrv}",
    "average_heart_rate_bpm": "{record.average_heart_rate}",
    "lowest_heart_rate_bpm": "{record.lowest_heart_rate}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- Use `bedtime_start`/`bedtime_end` as the event window.
- Preserve sleep phase, HR, and HRV samples in `raw_records.jsonl`; do not explode them into separate observations unless Gumbo specifically wants time-series detail.

### `oura.heartrate`

Endpoint:

- `GET /v2/usercollection/heartrate`

Schema checked:

- `PublicHeartRateRow`
- Required fields: `timestamp`, `timestamp_unix`, `bpm`, `source`.

Observation mapping:

```json
{
  "id": "oura.heartrate:{record.timestamp}",
  "source": "oura.heartrate",
  "timestamp": "{record.timestamp}",
  "text": "Oura recorded heart rate at {bpm} bpm at {timestamp}.",
  "metadata": {
    "provider": "oura",
    "bpm": "{record.bpm}",
    "measurement_source": "{record.source}",
    "timestamp_unix": "{record.timestamp_unix}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- This can be high volume. Make it opt-in or downsample unless Gumbo explicitly wants dense time series.

### `oura.daily_spo2`

Endpoint:

- `GET /v2/usercollection/daily_spo2`
- `GET /v2/usercollection/daily_spo2/{document_id}`

Schema checked:

- `PublicDailySpO2`
- Required fields: `id`, `day`.
- Optional fields: `spo2_percentage`, `breathing_disturbance_index`.
- `PublicSpo2AggregatedValues` has required field `average`.

Observation mapping:

```json
{
  "id": "oura.daily_spo2:{record.id}",
  "source": "oura.daily_spo2",
  "timestamp": "{record.day}T00:00:00",
  "text": "Oura recorded average overnight SpO2 {spo2_percentage.average}% for {day}.",
  "metadata": {
    "provider": "oura",
    "day": "{record.day}",
    "spo2_average_percentage": "{record.spo2_percentage.average}",
    "breathing_disturbance_index": "{record.breathing_disturbance_index}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- `day` is the only required time anchor in the schema, so derive `timestamp` from the day.

### `oura.workout`

Endpoint:

- `GET /v2/usercollection/workout`
- `GET /v2/usercollection/workout/{document_id}`

Schema checked:

- `PublicWorkout`
- Required fields: `id`, `activity`, `day`, `end_datetime`, `intensity`, `source`, `start_datetime`.
- Optional fields: `calories`, `distance`, `label`.

Observation mapping:

```json
{
  "id": "oura.workout:{record.id}",
  "source": "oura.workout",
  "timestamp": "{record.start_datetime}",
  "text": "Oura recorded a {intensity} {activity} workout from {start_datetime} to {end_datetime}, with {calories} calories and distance {distance_miles} miles.",
  "metadata": {
    "provider": "oura",
    "scope": "range",
    "time_range": {
      "start": "{record.start_datetime}",
      "end": "{record.end_datetime}"
    },
    "activity": "{record.activity}",
    "intensity": "{record.intensity}",
    "workout_source": "{record.source}",
    "label": "{record.label}",
    "metrics": {
      "calories": {
        "value": "{record.calories}",
        "unit": "kilocalorie"
      },
      "distance": {
        "value": "{record.distance}",
        "unit": "meter",
        "normalized_value": "{distance_miles}",
        "normalized_unit": "mile"
      }
    },
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

### `oura.session`

Endpoint:

- `GET /v2/usercollection/session`
- `GET /v2/usercollection/session/{document_id}`

Schema checked:

- `PublicSession`
- Required fields: `id`, `day`, `end_datetime`, `start_datetime`, `type`.
- Optional fields: `heart_rate`, `heart_rate_variability`, `mood`, `motion_count`.

Observation mapping:

```json
{
  "id": "oura.session:{record.id}",
  "source": "oura.session",
  "timestamp": "{record.start_datetime}",
  "text": "Oura recorded a {type} session from {start_datetime} to {end_datetime}.",
  "metadata": {
    "provider": "oura",
    "scope": "range",
    "time_range": {
      "start": "{record.start_datetime}",
      "end": "{record.end_datetime}"
    },
    "day": "{record.day}",
    "session_type": "{record.type}",
    "mood": "{record.mood}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- Optional by default. Useful if the user wants guided/unguided session context.

### `oura.tag` and `oura.enhanced_tag`

Endpoints:

- `GET /v2/usercollection/tag`
- `GET /v2/usercollection/tag/{document_id}`
- `GET /v2/usercollection/enhanced_tag`
- `GET /v2/usercollection/enhanced_tag/{document_id}`

Schemas checked:

- `TagModel` required fields: `id`, `day`, `text`, `timestamp`, `tags`.
- `EnhancedTagModel` required fields: `id`, `start_time`, `start_day`.
- `EnhancedTagModel` optional fields: `comment`, `custom_name`, `end_day`, `end_time`, `tag_type_code`.

Observation mapping:

```json
{
  "id": "oura.tag:{record.id}",
  "source": "oura.tag",
  "timestamp": "{record.timestamp or record.start_time}",
  "text": "Oura recorded user tag {tags or tag_type_code} at {timestamp}.",
  "metadata": {
    "provider": "oura",
    "scope": "point",
    "time_range": null,
    "day": "{record.day or record.start_day}",
    "tags": "{record.tags}",
    "text": "{record.text}",
    "comment": "{record.comment}",
    "custom_name": "{record.custom_name}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- Optional by default because tags/comments can be user-entered sensitive text.
- Use `scope = "range"` and populate `metadata.time_range` only for enhanced tags that include an end time.

### `oura.daily_stress`

Endpoint:

- `GET /v2/usercollection/daily_stress`
- `GET /v2/usercollection/daily_stress/{document_id}`

Schema checked:

- `PublicDailyStress`
- Required fields: `id`, `day`.
- Optional fields: `day_summary`, `recovery_high`, `stress_high`.
- Field descriptions: `recovery_high` is time spent in high recovery zone in seconds; `stress_high` is time spent in high stress zone in seconds.

Observation mapping:

```json
{
  "id": "healthsync:v1:oura.daily_stress:{record.id}:{record_version}",
  "source": "oura.daily_stress",
  "timestamp": "{record.day}T00:00:00",
  "text": "Oura daily stress update for {day}, observed by HealthSync at {ingested_at}: high-stress total is now {stress_high}, high-recovery total is now {recovery_high} across the Oura day. The Oura API does not provide exact stress intervals for this daily record.",
  "metadata": {
    "provider": "oura",
    "scope": "day",
    "granularity": "day",
    "measurement_semantics": "daily_stress_cumulative_update",
    "exact_intervals_available": false,
    "metrics": {
      "stress_high": {"value": "{record.stress_high}", "unit": "second"},
      "recovery_high": {"value": "{record.recovery_high}", "unit": "second"}
    },
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- Optional by default. Use factual wording only; do not infer cause.
- Public Oura daily stress records expose daily totals, not the exact time windows when stress occurred. Polling/webhooks can identify when HealthSync observed a changed total, but not the underlying stress interval.

### `oura.daily_resilience`

Endpoint:

- `GET /v2/usercollection/daily_resilience`
- `GET /v2/usercollection/daily_resilience/{document_id}`

Schema checked:

- `DailyResilienceModel`
- Required fields: `id`, `day`, `contributors`, `level`.
- `ResilienceContributors` required fields: `sleep_recovery`, `daytime_recovery`, `stress`.

Observation mapping:

```json
{
  "id": "oura.daily_resilience:{record.id}",
  "source": "oura.daily_resilience",
  "timestamp": "{record.day}T00:00:00",
  "text": "Oura recorded resilience level {level} for {day}.",
  "metadata": {
    "provider": "oura",
    "day": "{record.day}",
    "level": "{record.level}",
    "contributors": "{record.contributors}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

### `oura.daily_cardiovascular_age`

Endpoint:

- `GET /v2/usercollection/daily_cardiovascular_age`
- `GET /v2/usercollection/daily_cardiovascular_age/{document_id}`

Schema checked:

- `PublicDailyCardiovascularAge`
- Required fields: `id`, `day`.
- Optional fields: `pulse_wave_velocity`, `vascular_age`.
- Field descriptions: pulse wave velocity is in m/s; vascular age is predicted range `[18, 100]`.

Observation mapping:

```json
{
  "id": "oura.daily_cardiovascular_age:{record.id}",
  "source": "oura.daily_cardiovascular_age",
  "timestamp": "{record.day}T00:00:00",
  "text": "Oura recorded vascular age {vascular_age} and pulse wave velocity {pulse_wave_velocity} m/s for {day}.",
  "metadata": {
    "provider": "oura",
    "day": "{record.day}",
    "vascular_age": "{record.vascular_age}",
    "pulse_wave_velocity_mps": "{record.pulse_wave_velocity}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

### `oura.vo2_max`

Endpoint:

- `GET /v2/usercollection/vO2_max`
- `GET /v2/usercollection/vO2_max/{document_id}`

Schema checked:

- `PublicVO2Max`
- Required fields: `id`, `day`, `timestamp`, `vo2_max`.

Observation mapping:

```json
{
  "id": "oura.vo2_max:{record.id}",
  "source": "oura.vo2_max",
  "timestamp": "{record.timestamp}",
  "text": "Oura recorded VO2 max {vo2_max} for {day}.",
  "metadata": {
    "provider": "oura",
    "day": "{record.day}",
    "vo2_max": "{record.vo2_max}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

### Oura device/configuration endpoints

Endpoints checked:

- `GET /v2/usercollection/ring_battery_level`
- `GET /v2/usercollection/ring_configuration`
- `GET /v2/usercollection/ring_configuration/{document_id}`
- `GET /v2/usercollection/rest_mode_period`
- `GET /v2/usercollection/rest_mode_period/{document_id}`
- `GET /v2/usercollection/sleep_time`
- `GET /v2/usercollection/sleep_time/{document_id}`
- `GET /v2/usercollection/personal_info`

Default recommendation:

- Do not include `personal_info` in GUM observations by default. It contains `id`, optional `age`, `weight`, `height`, `biological_sex`, and `email`.
- Do not include `ring_configuration` by default. It is device metadata: color, design, firmware version, hardware type, setup time, size.
- Include `ring_battery_level` only for diagnostics, not GUM.
- Include `rest_mode_period` only if health context needs rest-mode state.
- Include `sleep_time` only if recommendations/status are wanted; it is not raw physiology.

## WHOOP Cross-Checks

WHOOP auth and access:

- `whoop.pdf` is a PDF rendering of `https://api.prod.whoop.com/developer/doc/openapi.json`.
- WHOOP API server in `whoop.pdf`: `https://api.prod.whoop.com/developer`.
- OAuth authorization URL: `https://api.prod.whoop.com/oauth/oauth2/auth`.
- OAuth token URL: `https://api.prod.whoop.com/oauth/oauth2/token`.
- OAuth scopes in `whoop.pdf`: `read:recovery`, `read:cycles`, `read:workout`, `read:sleep`, `read:profile`, `read:body_measurement`.
- Collection endpoints use `limit`, `start`, `end`, and `nextToken`.
- Collection response objects use `records` and `next_token`.
- WHOOP `score_state` enum across cycle/sleep/recovery/workout: `SCORED`, `PENDING_SCORE`, `UNSCORABLE`.
- WHOOP score objects are only present when score state is `SCORED`.
- V1 activity IDs are transitional. `v1_id` fields and `sport_id` are documented as not existing past `09/01/2025`; do not depend on them.

### `whoop.cycle`

Endpoints:

- `GET /v2/cycle`
- `GET /v2/cycle/{cycleId}`

Schema checked:

- `Cycle`
- Required fields: `created_at`, `id`, `score_state`, `start`, `timezone_offset`, `updated_at`, `user_id`.
- Optional field: `end`.
- Score schema: `CycleScore`.
- `CycleScore` required fields: `strain`, `kilojoule`, `average_heart_rate`, `max_heart_rate`.
- WHOOP describes strain as cardiovascular load on scale `0` to `21`.

Observation mapping:

```json
{
  "id": "whoop.cycle:{record.id}",
  "source": "whoop.cycle",
  "timestamp": "{record.start}",
  "text": "WHOOP recorded a physiological cycle from {start} to {end} with strain {score.strain}, average heart rate {score.average_heart_rate} bpm, and max heart rate {score.max_heart_rate} bpm.",
  "metadata": {
    "provider": "whoop",
    "scope": "range",
    "time_range": {
      "start": "{record.start}",
      "end": "{record.end}"
    },
    "cycle_id": "{record.id}",
    "score_state": "{record.score_state}",
    "timezone_offset": "{record.timezone_offset}",
    "strain": "{record.score.strain}",
    "kilojoule": "{record.score.kilojoule}",
    "average_heart_rate_bpm": "{record.score.average_heart_rate}",
    "max_heart_rate_bpm": "{record.score.max_heart_rate}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- If `end` is absent, text should say the user is currently in this cycle only if directly reflecting the API description; otherwise omit end.
- If `score_state` is not `SCORED`, do not include score values in text.

### `whoop.sleep`

Endpoints:

- `GET /v2/activity/sleep`
- `GET /v2/activity/sleep/{sleepId}`
- `GET /v2/cycle/{cycleId}/sleep`

Schema checked:

- `Sleep`
- Required fields: `created_at`, `cycle_id`, `end`, `id`, `nap`, `score_state`, `start`, `timezone_offset`, `updated_at`, `user_id`.
- Optional/transitional field: `v1_id`.
- Score schema: `SleepScore`.
- `SleepScore` required fields: `sleep_needed`, `stage_summary`.
- Sleep score optional fields: `respiratory_rate`, `sleep_performance_percentage`, `sleep_consistency_percentage`, `sleep_efficiency_percentage`.
- `SleepStageSummary` required fields: `total_in_bed_time_milli`, `total_awake_time_milli`, `total_no_data_time_milli`, `total_light_sleep_time_milli`, `total_slow_wave_sleep_time_milli`, `total_rem_sleep_time_milli`, `sleep_cycle_count`, `disturbance_count`.
- `SleepNeeded` required fields: `baseline_milli`, `need_from_sleep_debt_milli`, `need_from_recent_strain_milli`, `need_from_recent_nap_milli`.

Observation mapping:

```json
{
  "id": "whoop.sleep:{record.id}",
  "source": "whoop.sleep",
  "timestamp": "{record.start}",
  "text": "WHOOP recorded sleep from {start} to {end}, with sleep performance {score.sleep_performance_percentage}%, sleep efficiency {score.sleep_efficiency_percentage}%, sleep consistency {score.sleep_consistency_percentage}%, respiratory rate {score.respiratory_rate}, and {score.stage_summary.disturbance_count} disturbances.",
  "metadata": {
    "provider": "whoop",
    "scope": "range",
    "time_range": {
      "start": "{record.start}",
      "end": "{record.end}"
    },
    "sleep_id": "{record.id}",
    "cycle_id": "{record.cycle_id}",
    "nap": "{record.nap}",
    "score_state": "{record.score_state}",
    "timezone_offset": "{record.timezone_offset}",
    "stage_summary": "{record.score.stage_summary}",
    "sleep_needed": "{record.score.sleep_needed}",
    "respiratory_rate": "{record.score.respiratory_rate}",
    "sleep_performance_percentage": "{record.score.sleep_performance_percentage}",
    "sleep_consistency_percentage": "{record.score.sleep_consistency_percentage}",
    "sleep_efficiency_percentage": "{record.score.sleep_efficiency_percentage}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- If `score_state` is not `SCORED`, keep factual text to the sleep window and score state.

### `whoop.recovery`

Endpoints:

- `GET /v2/recovery`
- `GET /v2/cycle/{cycleId}/recovery`

Schema checked:

- `Recovery`
- Required fields: `created_at`, `cycle_id`, `score_state`, `sleep_id`, `updated_at`, `user_id`.
- Score schema: `RecoveryScore`.
- `RecoveryScore` required fields: `user_calibrating`, `recovery_score`, `resting_heart_rate`, `hrv_rmssd_milli`.
- Optional score fields: `spo2_percentage`, `skin_temp_celsius`.
- WHOOP describes recovery score as percentage `0-100%` reflecting preparedness to take on strain and return to baseline after a stressor.

Observation mapping:

```json
{
  "id": "whoop.recovery:{record.cycle_id}",
  "source": "whoop.recovery",
  "timestamp": "{record.created_at}",
  "text": "WHOOP recorded recovery score {score.recovery_score}% for cycle {cycle_id}, with resting heart rate {score.resting_heart_rate} bpm and HRV {score.hrv_rmssd_milli} ms.",
  "metadata": {
    "provider": "whoop",
    "cycle_id": "{record.cycle_id}",
    "sleep_id": "{record.sleep_id}",
    "score_state": "{record.score_state}",
    "user_calibrating": "{record.score.user_calibrating}",
    "recovery_score": "{record.score.recovery_score}",
    "resting_heart_rate_bpm": "{record.score.resting_heart_rate}",
    "hrv_rmssd_ms": "{record.score.hrv_rmssd_milli}",
    "spo2_percentage": "{record.score.spo2_percentage}",
    "skin_temp_celsius": "{record.score.skin_temp_celsius}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- WHOOP recovery lacks an explicit `start`/`end`; it is tied to `cycle_id` and `sleep_id`.
- Use `created_at` as `timestamp` unless implementation resolves the linked sleep and chooses sleep end time. If resolving linked sleep, document that the timestamp was derived from `whoop.sleep.end`.

### `whoop.workout`

Endpoints:

- `GET /v2/activity/workout`
- `GET /v2/activity/workout/{workoutId}`

Schema checked:

- `WorkoutV2`
- Required fields: `created_at`, `end`, `id`, `score_state`, `sport_name`, `start`, `timezone_offset`, `updated_at`, `user_id`.
- Optional/transitional fields: `v1_id`, `sport_id`.
- Score schema: `WorkoutScore`.
- `WorkoutScore` required fields: `strain`, `average_heart_rate`, `max_heart_rate`, `kilojoule`, `percent_recorded`, `zone_durations`.
- Optional score fields: `distance_meter`, `altitude_gain_meter`, `altitude_change_meter`.
- `ZoneDurations` required fields: `zone_zero_milli`, `zone_one_milli`, `zone_two_milli`, `zone_three_milli`, `zone_four_milli`, `zone_five_milli`.

Observation mapping:

```json
{
  "id": "whoop.workout:{record.id}",
  "source": "whoop.workout",
  "timestamp": "{record.start}",
  "text": "WHOOP recorded a {sport_name} workout from {start} to {end}, with strain {score.strain}, average heart rate {score.average_heart_rate} bpm, max heart rate {score.max_heart_rate} bpm, and distance {distance_miles} miles.",
  "metadata": {
    "provider": "whoop",
    "scope": "range",
    "time_range": {
      "start": "{record.start}",
      "end": "{record.end}"
    },
    "workout_id": "{record.id}",
    "sport_name": "{record.sport_name}",
    "score_state": "{record.score_state}",
    "timezone_offset": "{record.timezone_offset}",
    "metrics": {
      "strain": {
        "value": "{record.score.strain}",
        "unit": "whoop_strain_0_to_21"
      },
      "average_heart_rate": {
        "value": "{record.score.average_heart_rate}",
        "unit": "beats_per_minute"
      },
      "max_heart_rate": {
        "value": "{record.score.max_heart_rate}",
        "unit": "beats_per_minute"
      },
      "energy": {
        "value": "{record.score.kilojoule}",
        "unit": "kilojoule",
        "normalized_value": "{kilocalories}",
        "normalized_unit": "kilocalorie"
      },
      "percent_recorded": {
        "value": "{record.score.percent_recorded}",
        "unit": "percent"
      },
      "distance": {
        "value": "{record.score.distance_meter}",
        "unit": "meter",
        "normalized_value": "{distance_miles}",
        "normalized_unit": "mile"
      },
      "altitude_gain": {
        "value": "{record.score.altitude_gain_meter}",
        "unit": "meter"
      },
      "altitude_change": {
        "value": "{record.score.altitude_change_meter}",
        "unit": "meter"
      }
    },
    "zone_durations": "{record.score.zone_durations}",
    "raw_ref": "source:record_id:record_version",
    "raw_hash": "sha256:..."
  }
}
```

Notes:

- If optional distance/altitude fields are absent, omit them from text.
- If `score_state` is not `SCORED`, keep text to sport name, time window, and score state.

### WHOOP user endpoints

Endpoints checked:

- `GET /v2/user/measurement/body`
- `GET /v2/user/profile/basic`
- `DELETE /v2/user/access`

Schemas checked:

- `UserBodyMeasurement` required fields: `height_meter`, `weight_kilogram`, `max_heart_rate`.
- `UserBasicProfile` required fields: `user_id`, `email`, `first_name`, `last_name`.
- `/v2/user/access` revokes OAuth access.

Default recommendation:

- Do not emit profile observations by default; name/email are not needed for GUM health context.
- Do not emit body measurements by default; height/weight/max HR are sensitive and long-lived. If included, make it opt-in.

## Default Source Set

Use by default:

- `apple_health.steps`
- `oura.daily_activity`
- `oura.daily_readiness`
- `oura.daily_sleep`
- `oura.sleep`
- `oura.daily_spo2`
- `oura.workout`
- `whoop.cycle`
- `whoop.sleep`
- `whoop.recovery`
- `whoop.workout`

Optional/toggleable:

- `oura.heartrate`: high volume.
- `oura.session`: potentially useful but user-context-specific.
- `oura.tag` and `oura.enhanced_tag`: can contain user-entered sensitive text.
- `oura.daily_stress`, `oura.daily_resilience`, `oura.daily_cardiovascular_age`, `oura.vo2_max`: useful but sensitive; include behind a clear toggle.
- Oura device/configuration sources: diagnostic only.
- WHOOP body measurement/profile: sensitive; avoid by default.

## Implementation Implications

- The master machine-readable artifact should be `observations.jsonl`, not the Markdown raw log.
- Each line in `observations.jsonl` should be one atomic factual observation. A provider record can produce multiple observations when that makes the semantics clearer, and multiple provider records can be consolidated when they are one daily concept.
- Apple Health step samples should be one observation per sample, because the current iCloud sync batch is arbitrary.
- Oura readiness, daily sleep, main sleep interval, and SpO2 are consolidated into one `oura.recovery_sleep_summary` observation per day, while the raw component records remain archived in `raw_records.jsonl`.
- Oura daily activity is a cumulative update observation plus derived `oura.activity_classification` range observations from `class_5_min`.
- Oura daily stress is a cumulative update observation; exact stress intervals are not available from the public daily stress endpoint.
- Oura workout/session/rest-mode records are one observation per provider windowed record with `metadata.scope = "range"`.
- Oura heartrate and ring battery are one observation per time-series sample if enabled.
- WHOOP cycle/sleep/recovery/workout records are one observation per provider record.
- `observations.md` can remain a human debug view, but Gumbo handoff should be JSONL.
