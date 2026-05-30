import crypto from "node:crypto";
import { db, ensureSchema } from "../../lib/db.js";
import { env } from "../../lib/env.js";

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, `https://${req.headers.host}`);
    if (url.searchParams.get("token") !== env("OURA_WEBHOOK_VERIFICATION_TOKEN")) {
      return res.status(401).json({ ok: false, error: "Unauthorized" });
    }

    await ensureSchema();
    const { rows } = await db().query(`
      select oura_user_id, id, source, metadata
      from observations
      where metadata ? 'raw' or not (metadata ? 'raw_ref') or not (metadata ? 'raw_hash')
      order by created_at asc
    `);

    let updated = 0;
    for (const row of rows) {
      const metadata = { ...(row.metadata || {}) };
      const raw = metadata.raw;
      delete metadata.raw;

      const rawHash = metadata.raw_hash || (raw ? hashRaw(raw) : "sha256:null");
      const recordId = String(metadata.record_id || row.id);
      const recordVersion = metadata.record_version || rawHash;
      const rawRefBase = recordId.startsWith(`${row.source}:`) ? recordId : `${row.source}:${recordId}`;
      metadata.raw_hash = rawHash;
      metadata.raw_ref = metadata.raw_ref || `${rawRefBase}:${recordVersion}`;

      await db().query(
        `
          update observations
          set metadata = $3
          where oura_user_id = $1 and id = $2
        `,
        [row.oura_user_id, row.id, metadata],
      );
      updated += 1;
    }

    res.status(200).json({ ok: true, rows_seen: rows.length, rows_updated: updated });
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message });
  }
}

function hashRaw(raw) {
  return `sha256:${crypto.createHash("sha256").update(stableJson(raw)).digest("hex")}`;
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
