import { db, ensureSchema } from "../../lib/db.js";

export default async function handler(req, res) {
  try {
    await ensureSchema();
    const tables = ["oura_tokens", "oura_raw_records", "observations", "oura_webhook_events", "oura_webhook_subscriptions"];
    const counts = {};
    for (const table of tables) {
      const { rows } = await db().query(`select count(*)::int as count from ${table}`);
      counts[table] = rows[0].count;
    }
    res.status(200).json({ ok: true, counts });
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message });
  }
}
