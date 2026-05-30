import crypto from "node:crypto";

// Reference-only JavaScript transform layer.
//
// Keep this aligned with the canonical Python transforms before using it in a
// production handoff. The current source of truth for local HealthSync output is
// src/health_observer/providers/oura/transform.py.
const LOCAL_TZ = "America/Los_Angeles";
const ALLOWED_SCOPES = new Set(["point", "range", "day", "system"]);

export function ouraRecordToObservation({ dataType, raw, ingestedAt = new Date() }) {
  const record = normalizeRecord(raw);
  const source = `oura.${dataType}`;
  const transform = TRANSFORMS[dataType];
  if (!transform) return null;
  return transform({ source, record, ingestedAt });
}

export function ouraRecordId(raw, fallback) {
  const record = normalizeRecord(raw);
  return String(record.id || record.timestamp || record.day || fallback);
}

function normalizeRecord(raw) {
  if (raw && raw.data && !raw.id && !Array.isArray(raw.data)) return raw.data;
  return raw || {};
}

function dailyActivity({ source, record, ingestedAt }) {
  const metrics = {
    steps: metric(record.steps, "count"),
    active_calories: metric(record.active_calories, "kilocalorie"),
    total_calories: metric(record.total_calories, "kilocalorie"),
    activity_score: metric(record.score, "score"),
  };
  return makeObservation({
    source,
    timestamp: dayStartPt(record.day),
    text: `Oura recorded ${maybeText([
      present(record.steps) ? `${fmtNum(record.steps)} steps` : "",
      present(record.active_calories) ? `${fmtNum(record.active_calories)} active calories` : "",
      present(record.total_calories) ? `${fmtNum(record.total_calories)} total calories` : "",
      present(record.score) ? `activity score ${fmtNum(record.score)}` : "",
    ])} for ${record.day}.`,
    metadata: baseMetadata({
      scope: "day",
      category: "activity",
      subtype: "daily_activity",
      record,
      ingestedAt,
      granularity: "day",
      metrics,
    }),
  });
}

function dailyReadiness({ source, record, ingestedAt }) {
  return makeObservation({
    source,
    timestamp: dayStartPt(record.day),
    text: `Oura recorded ${maybeText([
      present(record.score) ? `readiness score ${fmtNum(record.score)}` : "",
      present(record.temperature_deviation) ? `temperature deviation ${fmtNum(record.temperature_deviation)} C` : "",
    ])} for ${record.day}.`,
    metadata: baseMetadata({
      scope: "day",
      category: "readiness",
      subtype: "daily_readiness",
      record,
      ingestedAt,
      granularity: "day",
      metrics: {
        readiness_score: metric(record.score, "score"),
        temperature_deviation: metric(record.temperature_deviation, "celsius"),
      },
    }),
  });
}

function dailySleep({ source, record, ingestedAt }) {
  const text = present(record.score)
    ? `Oura recorded sleep score ${fmtNum(record.score)} for ${record.day}.`
    : `Oura recorded a daily sleep record for ${record.day}.`;
  return makeObservation({
    source,
    timestamp: dayStartPt(record.day),
    text,
    metadata: baseMetadata({
      scope: "day",
      category: "sleep",
      subtype: "daily_sleep",
      record,
      ingestedAt,
      granularity: "day",
      metrics: { sleep_score: metric(record.score, "score") },
    }),
  });
}

function sleep({ source, record, ingestedAt }) {
  const start = parseToPacificIso(record.bedtime_start);
  const end = parseToPacificIso(record.bedtime_end);
  return makeObservation({
    source,
    timestamp: start,
    text: `Oura recorded a sleep period from ${fmtDt(start)} to ${fmtDt(end)}, with ${maybeText([
      present(record.total_sleep_duration) ? `${fmtNum(record.total_sleep_duration)} seconds asleep` : "",
      present(record.time_in_bed) ? `${fmtNum(record.time_in_bed)} seconds in bed` : "",
      present(record.efficiency) ? `efficiency ${fmtNum(record.efficiency)}%` : "",
      present(record.average_hrv) ? `average HRV ${fmtNum(record.average_hrv)} ms` : "",
      present(record.lowest_heart_rate) ? `lowest heart rate ${fmtNum(record.lowest_heart_rate)} bpm` : "",
    ])}.`,
    metadata: baseMetadata({
      scope: "range",
      category: "sleep",
      subtype: record.type || "sleep",
      record,
      ingestedAt,
      granularity: "interval",
      timeRange: { start, end },
      metrics: {
        total_sleep_duration: metric(record.total_sleep_duration, "second"),
        time_in_bed: metric(record.time_in_bed, "second"),
        efficiency: metric(record.efficiency, "percent"),
        average_hrv: metric(record.average_hrv, "millisecond"),
        lowest_heart_rate: metric(record.lowest_heart_rate, "beats_per_minute"),
      },
    }),
  });
}

function dailySpo2({ source, record, ingestedAt }) {
  const spo2 = record.spo2_percentage?.average;
  const text = present(spo2)
    ? `Oura recorded average overnight SpO2 ${fmtNum(spo2)}% for ${record.day}.`
    : `Oura recorded a daily SpO2 record for ${record.day}.`;
  return makeObservation({
    source,
    timestamp: dayStartPt(record.day),
    text,
    metadata: baseMetadata({
      scope: "day",
      category: "oxygen",
      subtype: "daily_spo2",
      record,
      ingestedAt,
      granularity: "day",
      metrics: { spo2_average: metric(spo2, "percent") },
    }),
  });
}

function dailyStress({ source, record, ingestedAt }) {
  return makeObservation({
    source,
    timestamp: dayStartPt(record.day),
    text: `Oura recorded ${maybeText([
      present(record.stress_high) ? `${fmtNum(record.stress_high)} seconds in a high stress zone` : "",
      present(record.recovery_high) ? `${fmtNum(record.recovery_high)} seconds in a high recovery zone` : "",
    ])} for ${record.day}.`,
    metadata: baseMetadata({
      scope: "day",
      category: "stress",
      subtype: "daily_stress",
      record,
      ingestedAt,
      granularity: "day",
      metrics: {
        stress_high: metric(record.stress_high, "second"),
        recovery_high: metric(record.recovery_high, "second"),
      },
    }),
  });
}

function workout({ source, record, ingestedAt }) {
  const start = parseToPacificIso(record.start_datetime);
  const end = parseToPacificIso(record.end_datetime);
  const distanceMiles = miles(record.distance);
  return makeObservation({
    source,
    timestamp: start || dayStartPt(record.day),
    text: `Oura recorded a ${maybeText([
      [record.intensity, record.activity, "workout"].filter(Boolean).join(" "),
      start && end ? `from ${fmtDt(start)} to ${fmtDt(end)}` : "",
      present(record.calories) ? `${fmtNum(record.calories)} calories` : "",
      distanceMiles !== null ? `${distanceMiles.toFixed(2)} miles` : "",
    ])}.`,
    metadata: baseMetadata({
      scope: "range",
      category: "activity",
      subtype: "workout",
      record,
      ingestedAt,
      granularity: "interval",
      timeRange: { start, end },
      metrics: {
        calories: metric(record.calories, "kilocalorie"),
        distance: {
          value: record.distance,
          unit: "meter",
          normalized_value: distanceMiles,
          normalized_unit: "mile",
        },
      },
    }),
  });
}

const TRANSFORMS = {
  daily_activity: dailyActivity,
  daily_readiness: dailyReadiness,
  daily_sleep: dailySleep,
  sleep,
  daily_spo2: dailySpo2,
  daily_stress: dailyStress,
  workout,
};

function baseMetadata({
  scope,
  category,
  subtype,
  record,
  ingestedAt,
  granularity,
  timeRange = null,
  units = {},
  metrics = {},
}) {
  return {
    provider: "oura",
    scope,
    category,
    subtype,
    record_id: String(record.id),
    record_version: recordVersion(record),
    timezone: LOCAL_TZ,
    granularity,
    time_range: timeRange,
    ingested_at: toPacificIso(ingestedAt),
    units,
    metrics,
    raw_hash: recordHash(record),
    raw_ref: `oura.${subtype}:${record.id}:${record.timestamp || recordHash(record)}`,
  };
}

function makeObservation({ source, timestamp, text, metadata }) {
  const rawRefVersion = metadata.record_version || metadata.raw_hash;
  const rawRefBase = String(metadata.record_id).startsWith(`${source}:`)
    ? String(metadata.record_id)
    : `${source}:${metadata.record_id}`;
  metadata = { ...metadata, raw_ref: `${rawRefBase}:${rawRefVersion}` };
  const observation = {
    id: observationId(source, metadata.record_id, metadata.record_version),
    source,
    timestamp,
    text,
    metadata,
  };
  validateObservation(observation);
  return observation;
}

function validateObservation(observation) {
  for (const key of ["id", "source", "timestamp", "text", "metadata"]) {
    if (!(key in observation)) throw new Error(`Observation missing required key: ${key}`);
  }
  for (const key of [
    "provider",
    "scope",
    "category",
    "subtype",
    "record_id",
    "record_version",
    "timezone",
    "granularity",
    "time_range",
    "ingested_at",
    "units",
    "metrics",
    "raw_ref",
    "raw_hash",
  ]) {
    if (!(key in observation.metadata)) throw new Error(`Observation metadata missing required key: ${key}`);
  }
  if (!ALLOWED_SCOPES.has(observation.metadata.scope)) {
    throw new Error(`Observation metadata has invalid scope: ${observation.metadata.scope}`);
  }
}

function observationId(source, recordId, version) {
  const baseId = String(recordId).startsWith(`${source}:`) ? String(recordId) : `${source}:${recordId}`;
  return version ? `healthsync:v1:${baseId}:${version}` : `healthsync:v1:${baseId}`;
}

function recordVersion(record) {
  if (record.timestamp) return String(record.timestamp);
  return recordHash(record);
}

function recordHash(record) {
  return `sha256:${crypto.createHash("sha256").update(stableJson(record)).digest("hex")}`;
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function parseToPacificIso(value) {
  if (!value) return null;
  const raw = String(value);
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)) return toPacificIso(new Date(raw));
  return `${raw}${offsetForDay(raw.slice(0, 10))}`;
}

function toPacificIso(value) {
  const date = value instanceof Date ? value : new Date(value);
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: LOCAL_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}${offsetForDate(date)}`;
}

function dayStartPt(day) {
  return `${day}T00:00:00${offsetForDay(day)}`;
}

function offsetForDay(day) {
  return offsetForDate(new Date(`${day}T12:00:00Z`));
}

function offsetForDate(date) {
  const value = new Intl.DateTimeFormat("en-US", {
    timeZone: LOCAL_TZ,
    timeZoneName: "shortOffset",
  })
    .formatToParts(date)
    .find((part) => part.type === "timeZoneName")?.value;
  const match = /^GMT([+-])(\d{1,2})(?::?(\d{2}))?$/.exec(value || "");
  if (!match) return "-08:00";
  const [, sign, hour, minute = "00"] = match;
  return `${sign}${hour.padStart(2, "0")}:${minute}`;
}

function fmtDt(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: LOCAL_TZ,
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(iso));
}

function fmtNum(value) {
  if (!present(value)) return "";
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function maybeText(parts) {
  const kept = parts.filter(Boolean);
  if (!kept.length) return "a record";
  if (kept.length === 1) return kept[0];
  return `${kept.slice(0, -1).join(", ")} and ${kept.at(-1)}`;
}

function present(value) {
  return value !== null && value !== undefined && value !== "";
}

function metric(value, unit) {
  return { value, unit };
}

function miles(meters) {
  if (!present(meters)) return null;
  return Number(meters) / 1609.344;
}
