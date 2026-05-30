# Metric Rubric (read together with observations.jsonl)

Reference scales only. Read a metric value together with the matching entry and draw the
conclusion. `direction` says which way is favorable (HRV higher is better; resting/lowest
heart rate lower is better - opposite directions, so each is stated explicitly).

## Objective scales (same for everyone)
- **WHOOP strain** (0-21 strain, cumulative_daily_total, direction: neutral): 0-9.99 light; 10-13.99 moderate; 14-17.99 strenuous; 18-21 all-out. Cumulative running total for a WHOOP cycle (wake-to-wake); take the latest value, do not sum updates. High strain is only 'bad' relative to low recovery.
- **WHOOP recovery** (0-100 percent, morning_final, direction: higher_is_better): 0-33 red / under-recovered; 34-66 yellow / moderate; 67-100 green / well-recovered. Computed once each morning and final for the cycle; already normalized to the individual.
- **WHOOP sleep performance** (0-100 percent, morning_final, direction: higher_is_better): (no fixed bands). Share of the night's sleep need that was met; higher is better.
- **WHOOP sleep efficiency** (0-100 percent, morning_final, direction: higher_is_better): 0-84.99 below typical; 85-100 good. Time asleep / time in bed.
- **Oura readiness / sleep / activity score** (0-100 score, daily_cumulative, direction: higher_is_better): 0-69 pay attention; 70-84 good; 85-100 optimal. Daily activity and stress totals are cumulative for the Oura day (take latest, not summed).

## Personal metrics - no universal range; interpret against this user's per-source baseline
- **WHOOP HRV (RMSSD)** (direction: higher_is_better): typical 58.7-72.5 ms (median 65.2, observed 41.5-86.4, n=53). HRV rises with parasympathetic (rest/recovery) activity and fitness; higher than baseline = better recovered, a drop signals stress, fatigue, or illness. Opposite direction from resting heart rate. Measured by WHOOP during sleep, so keep its baseline separate from Oura HRV.
- **WHOOP resting heart rate** (direction: lower_is_better): typical 66.0-74.0 bpm (median 69.0, observed 59.0-92.0, n=53). Lower than baseline = better recovered; an elevation signals stress, illness, or under-recovery.
- **WHOOP respiratory rate** (direction: stable_is_normal): typical 14.5-16.1 breaths/min (median 15.1, observed 13.5-17.9, n=63). Usually steady night to night; a sustained rise can indicate illness or strain.
- **WHOOP skin temperature** (direction: stable_is_normal): typical 32.9-33.9 C (median 33.4, observed 32.2-35.1, n=53). Deviations from baseline can indicate illness or (for some users) menstrual-cycle phase.
- **Oura HRV (overnight average)** (direction: higher_is_better): typical 44.0-52.0 ms (median 47.5, observed 12.0-65.0, n=80). Oura's overnight average HRV; higher than baseline = better recovered. Measured differently from WHOOP HRV, so its baseline is kept separate.
- **Oura lowest heart rate (overnight)** (direction: lower_is_better): typical 49.0-52.0 bpm (median 50.0, observed 47.0-74.0, n=80). Oura's overnight low; NOT the same metric as WHOOP resting heart rate, so its baseline is kept separate.
