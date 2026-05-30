import { db, ensureSchema } from "../../lib/db.js";
import { env } from "../../lib/env.js";

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, `https://${req.headers.host}`);
    if (url.searchParams.get("token") !== env("OURA_WEBHOOK_VERIFICATION_TOKEN")) {
      return res.status(401).json({ ok: false, error: "Unauthorized" });
    }

    const ouraUserId = url.searchParams.get("user_id");
    if (!ouraUserId) return res.status(400).json({ ok: false, error: "Missing user_id" });

    await ensureSchema();
    const sourceCounts = await db().query(
      `
        select source, count(*)::int as count
        from oura_raw_records
        where oura_user_id = $1
        group by source
        order by source
      `,
      [ouraUserId],
    );

    const observationCounts = await db().query(
      `
        select source, count(*)::int as count
        from observations
        where oura_user_id = $1
        group by source
        order by source
      `,
      [ouraUserId],
    );

    const latestObservations = await db().query(
      `
        select source, id, timestamp, text, created_at
        from observations
        where oura_user_id = $1
        order by created_at desc
        limit 10
      `,
      [ouraUserId],
    );

    const latest = await db().query(
      `
        select distinct on (source) source, record_id, raw, fetched_at
        from oura_raw_records
        where oura_user_id = $1
        order by source, fetched_at desc
      `,
      [ouraUserId],
    );

    const workouts = await db().query(
      `
        select record_id, raw, fetched_at
        from oura_raw_records
        where oura_user_id = $1 and source = 'oura.workout'
        order by coalesce(raw->>'start_datetime', raw->>'day') desc nulls last
        limit 5
      `,
      [ouraUserId],
    );

    const events = await db().query(
      `
        select event_type, data_type, object_id, oura_user_id, event_time, received_at
        from oura_webhook_events
        where oura_user_id = $1
        order by received_at desc
        limit 5
      `,
      [ouraUserId],
    );

    res.status(200).json({
      ok: true,
      oura_user_id: ouraUserId,
      source_counts: sourceCounts.rows,
      observation_counts: observationCounts.rows,
      latest_observations: latestObservations.rows,
      latest_by_source: latest.rows.map((row) => summarizeRecord(row)),
      recent_workouts: workouts.rows.map((row) => summarizeWorkout(row)),
      recent_webhook_events: events.rows,
    });
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message });
  }
}

function summarizeRecord(row) {
  const raw = row.raw || {};
  const summary = {
    source: row.source,
    record_id: row.record_id,
    fetched_at: row.fetched_at,
    day: raw.day,
  };

  if (row.source === "oura.daily_activity") {
    Object.assign(summary, {
      steps: raw.steps,
      active_calories: raw.active_calories,
      total_calories: raw.total_calories,
      score: raw.score,
    });
  }
  if (row.source === "oura.daily_readiness") {
    Object.assign(summary, {
      score: raw.score,
      temperature_deviation: raw.temperature_deviation,
    });
  }
  if (row.source === "oura.daily_sleep") {
    Object.assign(summary, { score: raw.score });
  }
  if (row.source === "oura.daily_spo2") {
    Object.assign(summary, { spo2_average: raw.spo2_percentage?.average });
  }
  if (row.source === "oura.daily_stress") {
    Object.assign(summary, {
      stress_high: raw.stress_high,
      recovery_high: raw.recovery_high,
      day_summary: raw.day_summary,
    });
  }
  if (row.source === "oura.sleep") {
    Object.assign(summary, {
      type: raw.type,
      bedtime_start: raw.bedtime_start,
      bedtime_end: raw.bedtime_end,
      total_sleep_duration: raw.total_sleep_duration,
      efficiency: raw.efficiency,
    });
  }
  if (row.source === "oura.workout") {
    Object.assign(summary, workoutFields(raw));
  }

  return summary;
}

function summarizeWorkout(row) {
  return {
    record_id: row.record_id,
    fetched_at: row.fetched_at,
    ...workoutFields(row.raw || {}),
  };
}

function workoutFields(raw) {
  return {
    day: raw.day,
    activity: raw.activity,
    intensity: raw.intensity,
    start_datetime: raw.start_datetime,
    end_datetime: raw.end_datetime,
    calories: raw.calories,
    distance_meters: raw.distance,
  };
}
