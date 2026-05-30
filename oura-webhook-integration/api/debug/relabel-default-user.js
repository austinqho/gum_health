import { loadTokens, relabelOuraUser } from "../../lib/db.js";
import { accessTokenForUser, fetchPersonalInfo, userIdFromPersonalInfo } from "../../lib/oura.js";

export default async function handler(req, res) {
  try {
    const existing = await loadTokens("default");
    if (!existing) return res.status(404).json({ ok: false, error: "No default Oura token found" });

    const accessToken = await accessTokenForUser("default");
    const personalInfo = await fetchPersonalInfo(accessToken);
    const newUserId = userIdFromPersonalInfo(personalInfo);
    const result = await relabelOuraUser("default", newUserId, personalInfo);

    res.status(200).json({
      ok: true,
      old_user_id: "default",
      new_user_id: newUserId,
      changed: result.changed,
    });
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message });
  }
}
