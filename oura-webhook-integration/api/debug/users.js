import { db, ensureSchema } from "../../lib/db.js";

export default async function handler(req, res) {
  try {
    await ensureSchema();
    const { rows } = await db().query(`
      select
        t.oura_user_id,
        count(distinct (r.source, r.record_id))::int as raw_record_count,
        count(distinct o.id)::int as observation_count,
        min(r.record_id) filter (where r.source = 'oura.daily_stress') as sample_daily_stress_id,
        min(r.record_id) filter (where r.source = 'oura.daily_activity') as sample_daily_activity_id
      from oura_tokens t
      left join oura_raw_records r on r.oura_user_id = t.oura_user_id
      left join observations o on o.oura_user_id = t.oura_user_id
      group by t.oura_user_id
      order by t.updated_at asc
    `);
    res.status(200).json({ ok: true, users: rows });
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message });
  }
}
