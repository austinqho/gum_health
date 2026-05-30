import { ensureSchema } from "../../lib/db.js";

export default async function handler(req, res) {
  try {
    await ensureSchema();
    res.status(200).json({ ok: true, database: "connected" });
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message });
  }
}
