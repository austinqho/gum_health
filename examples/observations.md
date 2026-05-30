# Example Observations

This is the human-readable version of `observations.jsonl`. These observation texts are what a proposition prompt can read to make propositions; the JSONL version carries the same facts plus IDs, metadata, and raw-record references.

This example set covers:

- Apple Health steps
- Oura recovery and sleep summary
- Oura daily activity
- Oura activity classification
- Oura workout
- Oura daily stress

HealthSync intentionally consolidates some raw provider records. For example, Oura readiness, sleep, and SpO2 are combined into one morning recovery/sleep observation because they are day-level records that usually settle once after sleep is processed. The full untouched payloads stay in `raw_records.jsonl`.

Caveats: Oura workouts include exact start/end ranges. Oura daily stress exposes daily totals, not exact stress intervals. Oura daily activity step counts are cumulative day totals, not per-walk samples. Oura's 5-minute activity classification gives useful low/medium/high timing context, but it is not an exact step-count interval. Apple Health step observations are completed point samples from the Shortcut.

## apple_health.steps

Apple Health recorded a completed step-count sample of 135 steps at 9:56 PM PT on May 26, 2026.

- `id`: `healthsync:v1:apple_health.steps:2026-05-26T21:56:00-07:00`
- `timestamp`: `2026-05-26T21:56:00-07:00`
- `scope`: `point`
- `measurement_semantics`: `completed_step_sample`
- `raw_ref`: `apple_health.steps:2026-05-26T21:56:00-07:00:sha256:c1f56acf82855cc02a306e743f9fd32c05840f2567b2cbc0978ffffe07f4e955`

## oura.recovery_sleep_summary

Oura morning recovery and sleep summary for 2026-02-27: readiness score 75, temperature deviation 0.3 C, sleep score 75, main sleep from 1:45 AM PT on February 27, 2026 to 9:56 AM PT on February 27, 2026, 7h 13m asleep, 8h 10m in bed, sleep efficiency 88%, average HRV 39 ms, lowest heart rate 51 bpm, average overnight SpO2 97.4%.

- `id`: `healthsync:v1:oura.recovery_sleep_summary:2026-02-27:sha256:07eac9e02167995ebf107fb258b6110dffad9785849284a078420d8a6fb3c57f`
- `timestamp`: `2026-02-27T00:00:00-08:00`
- `scope`: `day`
- `measurement_semantics`: `daily_recovery_sleep_summary`
- `raw_ref`: `oura.recovery_sleep_summary:2026-02-27:sha256:07eac9e02167995ebf107fb258b6110dffad9785849284a078420d8a6fb3c57f`

## oura.daily_activity

Oura daily activity update for 2026-02-28, observed by HealthSync at 12:37 PM PT on May 28, 2026: daily step total is now 5,859, active calories expended are now 260, total calories expended are now 2,233, activity score is 55. Oura daily activity totals are cumulative for the Oura day, not incremental samples.

- `id`: `healthsync:v1:oura.daily_activity:838c2e0b-5eb2-4459-9afe-df5a38b82343:sha256:96e7e823179656c954d70854d646cf0cabcbedf2b10084a5ae07b02aebd21b7f`
- `timestamp`: `2026-02-28T00:00:00-08:00`
- `scope`: `day`
- `measurement_semantics`: `daily_activity_cumulative_update`
- `raw_ref`: `oura.daily_activity:838c2e0b-5eb2-4459-9afe-df5a38b82343:sha256:96e7e823179656c954d70854d646cf0cabcbedf2b10084a5ae07b02aebd21b7f`

## oura.activity_classification

Oura activity classification for 2026-02-28, observed by HealthSync at 12:37 PM PT on May 28, 2026, classified 10:55 AM PT on February 28, 2026 to 11:20 AM PT on February 28, 2026 as low-to-medium activity. This is Oura's 5-minute activity-intensity classification, not an exact step-count interval.

- `id`: `healthsync:v1:oura.activity_classification:838c2e0b-5eb2-4459-9afe-df5a38b82343:2026-02-28T10:55:00-08:00:2026-02-28T11:20:00-08:00:sha256:951037ed7903aaa6c348dda01a16f33c22dbe3667ce5f00c687e7f6545f267df`
- `timestamp`: `2026-02-28T10:55:00-08:00`
- `scope`: `range`
- `measurement_semantics`: `provider_activity_classification_interval`
- `raw_ref`: `oura.activity_classification:838c2e0b-5eb2-4459-9afe-df5a38b82343:2026-02-28T10:55:00-08:00:2026-02-28T11:20:00-08:00:sha256:951037ed7903aaa6c348dda01a16f33c22dbe3667ce5f00c687e7f6545f267df`

## oura.workout

Oura recorded a moderate walking workout, from 2:56 PM PT on March 10, 2026 to 3:12 PM PT on March 10, 2026, 47.9 calories expended during the workout, 0.06 miles.

- `id`: `healthsync:v1:oura.workout:6dec3ca6-c66c-46ae-9257-d213426be256:sha256:e89f454a37224de63bc7e3febb6ef508632aca1fd61b0fe9ac9ef39577a1480e`
- `timestamp`: `2026-03-10T14:56:00-07:00`
- `scope`: `range`
- `measurement_semantics`: `provider_time_range_event`
- `raw_ref`: `oura.workout:6dec3ca6-c66c-46ae-9257-d213426be256:sha256:e89f454a37224de63bc7e3febb6ef508632aca1fd61b0fe9ac9ef39577a1480e`

## oura.daily_stress

Oura daily stress update for 2026-05-28, observed by HealthSync at 12:37 PM PT on May 28, 2026: high-stress total is now 45m, high-recovery total is now 0m across the Oura day. The Oura API does not provide exact stress intervals for this daily record.

- `id`: `healthsync:v1:oura.daily_stress:4a89b416-3f14-4f30-928d-e9fcc509b5b7:sha256:26f18261b0cddb8fc026674713dce93cef40dfa8b972c7a9f9e0f5808b9cfdde`
- `timestamp`: `2026-05-28T00:00:00-07:00`
- `scope`: `day`
- `measurement_semantics`: `daily_stress_cumulative_update`
- `raw_ref`: `oura.daily_stress:4a89b416-3f14-4f30-928d-e9fcc509b5b7:sha256:26f18261b0cddb8fc026674713dce93cef40dfa8b972c7a9f9e0f5808b9cfdde`

## oura.daily_stress

Oura daily stress update for 2026-05-28, observed by HealthSync at 8:52 PM PT on May 28, 2026: high-stress total is now 4h, up 3h 15m since the previous HealthSync observation, high-recovery total is now 0m, unchanged since the previous HealthSync observation across the Oura day. The Oura API does not provide exact stress intervals for this daily record.

- `id`: `healthsync:v1:oura.daily_stress:4a89b416-3f14-4f30-928d-e9fcc509b5b7:sha256:43abd946f5f46c99549b8cfbac10349bb1736183626f80c747796662a5bc94b1`
- `timestamp`: `2026-05-28T00:00:00-07:00`
- `scope`: `day`
- `measurement_semantics`: `daily_stress_cumulative_update`
- `raw_ref`: `oura.daily_stress:4a89b416-3f14-4f30-928d-e9fcc509b5b7:sha256:43abd946f5f46c99549b8cfbac10349bb1736183626f80c747796662a5bc94b1`

## oura.daily_stress

Oura daily stress update for 2026-05-28, observed by HealthSync at 9:14 PM PT on May 28, 2026: high-stress total is now 4h, up 30m since the previous HealthSync observation, high-recovery total is now 30m, up 30m since the previous HealthSync observation across the Oura day. The Oura API does not provide exact stress intervals for this daily record.

- `id`: `healthsync:v1:oura.daily_stress:4a89b416-3f14-4f30-928d-e9fcc509b5b7:sha256:a2195c671451adaa9daa8b13b712ed24a4f0447fc423ab893d3327c4e19c49af`
- `timestamp`: `2026-05-28T00:00:00-07:00`
- `scope`: `day`
- `measurement_semantics`: `daily_stress_cumulative_update`
- `raw_ref`: `oura.daily_stress:4a89b416-3f14-4f30-928d-e9fcc509b5b7:sha256:a2195c671451adaa9daa8b13b712ed24a4f0447fc423ab893d3327c4e19c49af`
