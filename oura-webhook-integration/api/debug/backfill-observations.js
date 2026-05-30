import { db, ensureSchema, saveObservation } from "../../lib/db.js";
import { env } from "../../lib/env.js";
import { ouraRecordToObservation } from "../../lib/ouraTransform.js";

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, `https://${req.headers.host}`);
    if (url.searchParams.get("token") !== env("OURA_WEBHOOK_VERIFICATION_TOKEN")) {
      return res.status(401).json({ ok: false, error: "Unauthorized" });
    }

    await ensureSchema();
    const ouraUserId = url.searchParams.get("user_id");
    const params = [];
    let where = "";
    if (ouraUserId) {
      params.push(ouraUserId);
      where = "where oura_user_id = $1";
    }

    const { rows } = await db().query(
      `
        select source, record_id, oura_user_id, raw
        from oura_raw_records
        ${where}
        order by fetched_at asc
      `,
      params,
    );

    let transformed = 0;
    let inserted = 0;
    for (const row of rows) {
      const dataType = row.source.replace(/^oura\./, "");
      const observation = ouraRecordToObservation({
        dataType,
        raw: row.raw,
      });
      if (!observation) continue;
      transformed += 1;
      if (await saveObservation({ ouraUserId: row.oura_user_id, observation })) inserted += 1;
    }

    res.status(200).json({
      ok: true,
      raw_records_seen: rows.length,
      observations_transformed: transformed,
      observations_inserted: inserted,
    });
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message });
  }
}
