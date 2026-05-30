import crypto from "node:crypto";
import { csvEnv, env, optionalEnv } from "./env.js";
import { loadTokens, saveObservation, saveRawRecord, saveTokens, saveWebhookSubscription } from "./db.js";
import { ouraRecordId, ouraRecordToObservation } from "./ouraTransform.js";

// Reference-only Oura integration helpers.
//
// This module contains the hosted backend pieces: OAuth URL construction, token
// exchange/refresh, initial backfill, webhook subscription setup, signature
// verification, and object fetch by webhook object_id. The local Mac watcher
// uses src/health_observer/providers/oura/*.py instead.
const AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize";
const TOKEN_URL = "https://api.ouraring.com/oauth/token";
const API_BASE = "https://api.ouraring.com";

const COLLECTION_PATHS = {
  daily_activity: "/v2/usercollection/daily_activity",
  daily_readiness: "/v2/usercollection/daily_readiness",
  daily_sleep: "/v2/usercollection/daily_sleep",
  sleep: "/v2/usercollection/sleep",
  daily_spo2: "/v2/usercollection/daily_spo2",
  daily_stress: "/v2/usercollection/daily_stress",
  workout: "/v2/usercollection/workout",
};

export function enabledDataTypes() {
  const explicit = csvEnv("OURA_WEBHOOK_DATA_TYPES");
  if (explicit.length) return explicit;

  return csvEnv(
    "OURA_ENABLED_SOURCES",
    "oura.daily_activity,oura.daily_readiness,oura.daily_sleep,oura.sleep,oura.daily_spo2,oura.daily_stress,oura.workout",
  ).map((source) => source.replace(/^oura\./, ""));
}

export function buildAuthorizeUrl(state) {
  const url = new URL(AUTHORIZE_URL);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", env("OURA_CLIENT_ID"));
  url.searchParams.set("redirect_uri", env("OURA_REDIRECT_URI"));
  url.searchParams.set("scope", optionalEnv("OURA_SCOPES", "daily workout spo2 stress"));
  url.searchParams.set("state", state);
  return url.toString();
}

export async function exchangeCodeForTokens(code) {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: env("OURA_REDIRECT_URI"),
  });
  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: {
      Authorization: basicAuth(),
      "Content-Type": "application/x-www-form-urlencoded",
      Accept: "application/json",
    },
    body,
  });
  if (!response.ok) {
    throw new Error(`Oura token exchange failed: ${response.status} ${await response.text()}`);
  }
  return withExpiry(await response.json());
}

export async function refreshTokens(tokenRow) {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: tokenRow.refresh_token,
  });
  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: {
      Authorization: basicAuth(),
      "Content-Type": "application/x-www-form-urlencoded",
      Accept: "application/json",
    },
    body,
  });
  if (!response.ok) {
    throw new Error(`Oura token refresh failed: ${response.status} ${await response.text()}`);
  }
  const tokens = withExpiry(await response.json());
  if (!tokens.refresh_token) tokens.refresh_token = tokenRow.refresh_token;
  await saveTokens(tokenRow.oura_user_id, tokens, tokenRow.personal_info ?? null);
  return tokens.access_token;
}

export async function accessTokenForUser(ouraUserId) {
  const tokenRow = await loadTokens(ouraUserId);
  if (!tokenRow) {
    throw new Error(`No Oura tokens found for user ${ouraUserId}`);
  }
  const expiresAt = Number(tokenRow.expires_at || 0);
  if (!tokenRow.access_token || (expiresAt && Date.now() / 1000 >= expiresAt - 120)) {
    return refreshTokens(tokenRow);
  }
  return tokenRow.access_token;
}

export function userIdFromTokens(tokens) {
  const payload = decodeJwtPayload(tokens.id_token);
  return payload?.sub || payload?.user_id || "default";
}

export async function fetchPersonalInfo(accessToken) {
  return getJson(`${API_BASE}/v2/usercollection/personal_info`, accessToken);
}

export function userIdFromPersonalInfo(personalInfo, fallback = "default") {
  return personalInfo?.id || fallback;
}

export async function fetchOuraObject({ accessToken, dataType, objectId }) {
  const base = COLLECTION_PATHS[dataType];
  if (!base) throw new Error(`Unsupported Oura data_type: ${dataType}`);
  return getJson(`${API_BASE}${base}/${encodeURIComponent(objectId)}`, accessToken);
}

export async function backfillEnabledDataTypes({ accessToken, ouraUserId }) {
  const backfillDays = Number(optionalEnv("OURA_BACKFILL_DAYS", "90"));
  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - backfillDays * 24 * 60 * 60 * 1000);
  const start = startDate.toISOString().slice(0, 10);
  const end = endDate.toISOString().slice(0, 10);
  const saved = { rawRecords: 0, observations: 0 };

  for (const dataType of enabledDataTypes()) {
    const base = COLLECTION_PATHS[dataType];
    if (!base) continue;
    const url = new URL(`${API_BASE}${base}`);
    url.searchParams.set("start_date", start);
    url.searchParams.set("end_date", end);
    let nextToken = "";
    do {
      if (nextToken) url.searchParams.set("next_token", nextToken);
      const page = await getJson(url.toString(), accessToken);
      for (const record of page.data || []) {
        const result = await saveOuraRecord({ dataType, raw: record, ouraUserId, fallbackRecordId: crypto.randomUUID() });
        saved.rawRecords += 1;
        if (result.storedObservation) saved.observations += 1;
      }
      nextToken = page.next_token || "";
    } while (nextToken);
  }

  return saved;
}

export async function saveOuraRecord({ dataType, raw, ouraUserId, fallbackRecordId }) {
  const source = `oura.${dataType}`;
  const recordId = ouraRecordId(raw, fallbackRecordId);
  await saveRawRecord({ source, recordId, ouraUserId, raw });

  const observation = ouraRecordToObservation({ dataType, raw });
  let storedObservation = false;
  if (observation) {
    storedObservation = await saveObservation({ ouraUserId, observation });
  }

  return { source, recordId, observation, storedObservation };
}

export async function createWebhookSubscriptions() {
  const callbackUrl = env("OURA_WEBHOOK_URL");
  const verificationToken = env("OURA_WEBHOOK_VERIFICATION_TOKEN");
  const created = [];
  const existing = await listWebhookSubscriptions();

  for (const dataType of enabledDataTypes()) {
    for (const eventType of ["create", "update"]) {
      const existingSubscription = existing.find(
        (subscription) => subscription.data_type === dataType && subscription.event_type === eventType,
      );
      if (existingSubscription) {
        await saveWebhookSubscription(existingSubscription, dataType, eventType, existingSubscription.callback_url);
        created.push({
          dataType,
          eventType,
          ok: true,
          already_exists: true,
          id: existingSubscription.id,
        });
        continue;
      }

      const response = await fetch(`${API_BASE}/v2/webhook/subscription`, {
        method: "POST",
        headers: {
          "x-client-id": env("OURA_CLIENT_ID"),
          "x-client-secret": env("OURA_CLIENT_SECRET"),
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          callback_url: callbackUrl,
          verification_token: verificationToken,
          event_type: eventType,
          data_type: dataType,
        }),
      });
      if (!response.ok) {
        if (response.status === 409) {
          created.push({ dataType, eventType, ok: true, already_exists: true, id: null });
          continue;
        }
        created.push({ dataType, eventType, ok: false, status: response.status, body: await response.text() });
        continue;
      }
      const subscription = await response.json();
      await saveWebhookSubscription(subscription, dataType, eventType, callbackUrl);
      created.push({ dataType, eventType, ok: true, id: subscription.id });
    }
  }

  return created;
}

export async function listWebhookSubscriptions() {
  const response = await fetch(`${API_BASE}/v2/webhook/subscription`, {
    headers: {
      "x-client-id": env("OURA_CLIENT_ID"),
      "x-client-secret": env("OURA_CLIENT_SECRET"),
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`Oura webhook subscription list failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

export function verifyWebhookSignature({ rawBody, signature, timestamp }) {
  if (!signature || !timestamp) return false;
  const expected = crypto
    .createHmac("sha256", env("OURA_CLIENT_SECRET"))
    .update(`${timestamp}${rawBody}`)
    .digest("hex")
    .toUpperCase();
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature.toUpperCase()));
}

export function verifyChallenge({ verificationToken, challenge }) {
  return verificationToken === env("OURA_WEBHOOK_VERIFICATION_TOKEN") && Boolean(challenge);
}

export async function readRawBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

async function getJson(url, accessToken) {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`Oura GET failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

function basicAuth() {
  return `Basic ${Buffer.from(`${env("OURA_CLIENT_ID")}:${env("OURA_CLIENT_SECRET")}`).toString("base64")}`;
}

function withExpiry(tokens) {
  if (tokens.expires_in) {
    tokens.expires_at = Math.floor(Date.now() / 1000) + Number(tokens.expires_in);
  }
  return tokens;
}

function decodeJwtPayload(jwt) {
  if (!jwt || !jwt.includes(".")) return null;
  const payload = jwt.split(".")[1];
  const padded = payload.padEnd(payload.length + ((4 - (payload.length % 4)) % 4), "=");
  return JSON.parse(Buffer.from(padded, "base64url").toString("utf8"));
}
