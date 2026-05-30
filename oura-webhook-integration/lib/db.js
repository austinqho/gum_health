import pg from "pg";
import { optionalEnv } from "./env.js";

// Reference-only storage layer.
//
// This file uses Postgres/Supabase for the Vercel webhook demo. The local
// HealthSync watcher writes JSONL files instead and does not import this file.
// Gumbo should replace these functions with calls into its own database while
// preserving the same conceptual operations: save tokens, save webhook events,
// save raw provider records, and save canonical observations.
let pool;

export function db() {
  if (!pool) {
    pool = new pg.Pool({
      connectionString: databaseUrl(),
      ssl: { rejectUnauthorized: false },
    });
  }
  return pool;
}

function databaseUrl() {
  const raw = optionalEnv("DATABASE_URL") || optionalEnv("POSTGRES_URL");
  if (!raw) throw new Error("Missing required env var: DATABASE_URL or POSTGRES_URL");

  const url = new URL(raw);
  url.searchParams.delete("sslmode");
  url.searchParams.delete("sslcert");
  url.searchParams.delete("sslkey");
  url.searchParams.delete("sslrootcert");
  return url.toString();
}

export async function ensureSchema() {
  await db().query(`
    create table if not exists oura_tokens (
      oura_user_id text primary key,
      access_token text not null,
      refresh_token text not null,
      expires_at bigint,
      scope text,
      personal_info jsonb,
      raw jsonb not null,
      updated_at timestamptz not null default now()
    );

    create table if not exists oura_webhook_subscriptions (
      id text primary key,
      data_type text not null,
      event_type text not null,
      callback_url text not null,
      raw jsonb not null,
      updated_at timestamptz not null default now()
    );

    create table if not exists oura_webhook_events (
      id bigserial primary key,
      event_type text,
      data_type text,
      object_id text,
      oura_user_id text,
      event_time timestamptz,
      raw jsonb not null,
      received_at timestamptz not null default now()
    );

    create table if not exists oura_raw_records (
      source text not null,
      record_id text not null,
      oura_user_id text not null,
      raw jsonb not null,
      fetched_at timestamptz not null default now(),
      primary key (source, record_id, oura_user_id)
    );

    create table if not exists observations (
      oura_user_id text not null,
      id text not null,
      source text not null,
      timestamp text not null,
      text text not null,
      metadata jsonb not null,
      created_at timestamptz not null default now(),
      primary key (oura_user_id, id)
    );

    alter table oura_tokens add column if not exists personal_info jsonb;
  `);
}

export async function saveTokens(ouraUserId, tokens, personalInfo = null) {
  await ensureSchema();
  await db().query(
    `
      insert into oura_tokens (oura_user_id, access_token, refresh_token, expires_at, scope, personal_info, raw)
      values ($1, $2, $3, $4, $5, $6, $7)
      on conflict (oura_user_id) do update set
        access_token = excluded.access_token,
        refresh_token = excluded.refresh_token,
        expires_at = excluded.expires_at,
        scope = excluded.scope,
        personal_info = excluded.personal_info,
        raw = excluded.raw,
        updated_at = now()
    `,
    [
      ouraUserId,
      tokens.access_token,
      tokens.refresh_token,
      tokens.expires_at ?? null,
      tokens.scope ?? null,
      personalInfo,
      tokens,
    ],
  );
}

export async function loadTokens(ouraUserId) {
  await ensureSchema();
  const exact = await db().query("select * from oura_tokens where oura_user_id = $1", [ouraUserId]);
  if (exact.rows[0]) return exact.rows[0];

  const fallback = await db().query("select * from oura_tokens order by updated_at desc limit 1");
  return fallback.rows[0] ?? null;
}

export async function relabelOuraUser(oldUserId, newUserId, personalInfo) {
  await ensureSchema();
  if (!oldUserId || !newUserId || oldUserId === newUserId) return { changed: false };
  await db().query("begin");
  try {
    await db().query(
      `
        update oura_tokens
        set oura_user_id = $2, personal_info = $3, updated_at = now()
        where oura_user_id = $1
      `,
      [oldUserId, newUserId, personalInfo],
    );
    await db().query("update oura_raw_records set oura_user_id = $2 where oura_user_id = $1", [oldUserId, newUserId]);
    await db().query("update oura_webhook_events set oura_user_id = $2 where oura_user_id = $1", [
      oldUserId,
      newUserId,
    ]);
    await db().query("update observations set oura_user_id = $2 where oura_user_id = $1", [oldUserId, newUserId]);
    await db().query("commit");
    return { changed: true };
  } catch (error) {
    await db().query("rollback");
    throw error;
  }
}

export async function saveWebhookSubscription(subscription, dataType, eventType, callbackUrl) {
  await ensureSchema();
  await db().query(
    `
      insert into oura_webhook_subscriptions (id, data_type, event_type, callback_url, raw)
      values ($1, $2, $3, $4, $5)
      on conflict (id) do update set
        data_type = excluded.data_type,
        event_type = excluded.event_type,
        callback_url = excluded.callback_url,
        raw = excluded.raw,
        updated_at = now()
    `,
    [subscription.id, dataType, eventType, callbackUrl, subscription],
  );
}

export async function saveWebhookEvent(event) {
  await ensureSchema();
  await db().query(
    `
      insert into oura_webhook_events (event_type, data_type, object_id, oura_user_id, event_time, raw)
      values ($1, $2, $3, $4, $5, $6)
    `,
    [
      event.event_type ?? null,
      event.data_type ?? null,
      event.object_id ?? null,
      event.user_id ?? null,
      event.event_time ?? null,
      event,
    ],
  );
}

export async function saveRawRecord({ source, recordId, ouraUserId, raw }) {
  await ensureSchema();
  await db().query(
    `
      insert into oura_raw_records (source, record_id, oura_user_id, raw)
      values ($1, $2, $3, $4)
      on conflict (source, record_id, oura_user_id) do update set
        raw = excluded.raw,
        fetched_at = now()
    `,
    [source, recordId, ouraUserId, raw],
  );
}

export async function saveObservation({ ouraUserId, observation }) {
  await ensureSchema();
  const result = await db().query(
    `
      insert into observations (oura_user_id, id, source, timestamp, text, metadata)
      values ($1, $2, $3, $4, $5, $6)
      on conflict (oura_user_id, id) do nothing
    `,
    [
      ouraUserId,
      observation.id,
      observation.source,
      observation.timestamp,
      observation.text,
      observation.metadata,
    ],
  );
  return result.rowCount === 1;
}
