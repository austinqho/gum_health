import { saveWebhookEvent } from "../../lib/db.js";
import {
  accessTokenForUser,
  fetchOuraObject,
  readRawBody,
  saveOuraRecord,
  verifyChallenge,
  verifyWebhookSignature,
} from "../../lib/oura.js";

// Reference-only webhook endpoint.
//
// The local HealthSync watcher does not call this file. Gumbo can copy this
// handler into its backend, replace lib/db.js with its own storage layer, and
// set OURA_WEBHOOK_URL to the production URL registered with Oura.
export default async function handler(req, res) {
  try {
    if (req.method === "GET") {
      const url = new URL(req.url, `https://${req.headers.host}`);
      const verificationToken = url.searchParams.get("verification_token");
      const challenge = url.searchParams.get("challenge");
      if (!verifyChallenge({ verificationToken, challenge })) {
        return res.status(401).send("Invalid verification token");
      }
      return res.status(200).json({ challenge });
    }

    if (req.method !== "POST") {
      res.setHeader("Allow", "GET, POST");
      return res.status(405).send("Method not allowed");
    }

    const rawBody = await readRawBody(req);
    const signature = req.headers["x-oura-signature"];
    const timestamp = req.headers["x-oura-timestamp"];
    if (!verifyWebhookSignature({ rawBody, signature, timestamp })) {
      return res.status(401).send("Invalid Oura signature");
    }

    const event = JSON.parse(rawBody);
    await saveWebhookEvent(event);

    const dataType = event.data_type;
    const objectId = event.object_id;
    const ouraUserId = event.user_id || "default";
    if (event.event_type === "delete" || !dataType || !objectId) {
      return res.status(200).json({ ok: true, stored_event: true, fetched_object: false });
    }

    const accessToken = await accessTokenForUser(ouraUserId);
    const raw = await fetchOuraObject({ accessToken, dataType, objectId });
    const result = await saveOuraRecord({ dataType, raw, ouraUserId, fallbackRecordId: objectId });
    return res.status(200).json({
      ok: true,
      stored_event: true,
      fetched_object: true,
      transformed_observation: Boolean(result.observation),
      stored_observation: result.storedObservation,
    });
  } catch (error) {
    if (!res.headersSent) {
      res.status(500).json({ ok: false, error: error.message });
    }
  }
}
