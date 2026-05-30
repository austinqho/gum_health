import {
  accessTokenForUser,
  backfillEnabledDataTypes,
  createWebhookSubscriptions,
  exchangeCodeForTokens,
  fetchPersonalInfo,
  userIdFromPersonalInfo,
  userIdFromTokens,
} from "../../../lib/oura.js";
import { saveTokens } from "../../../lib/db.js";

// Reference-only OAuth callback endpoint.
//
// This exchanges Oura's authorization code for tokens, stores those tokens,
// performs an initial backfill, and registers webhook subscriptions. Gumbo
// should replace lib/db.js with its own token/raw-record/observation storage.
export default async function handler(req, res) {
  try {
    const url = new URL(req.url, `https://${req.headers.host}`);
    const code = url.searchParams.get("code");
    const state = url.searchParams.get("state");
    const cookieState = parseCookie(req.headers.cookie || "").oura_oauth_state;
    if (!code) return res.status(400).send("Missing Oura authorization code");
    if (!state || !cookieState || state !== cookieState) return res.status(400).send("Oura state mismatch");

    const tokens = await exchangeCodeForTokens(code);
    const fallbackUserId = userIdFromTokens(tokens);
    const personalInfo = await fetchPersonalInfo(tokens.access_token);
    const ouraUserId = userIdFromPersonalInfo(personalInfo, fallbackUserId);
    await saveTokens(ouraUserId, tokens, personalInfo);

    const accessToken = await accessTokenForUser(ouraUserId);
    const backfilled = await backfillEnabledDataTypes({ accessToken, ouraUserId });
    const subscriptions = await createWebhookSubscriptions();
    console.log(
      JSON.stringify({
        event: "oura_oauth_complete",
        oura_user_id: ouraUserId,
        backfilled_raw_records: backfilled.rawRecords,
        backfilled_observations: backfilled.observations,
        webhook_subscription_count: subscriptions.length,
      }),
    );

    res.setHeader("Set-Cookie", "oura_oauth_state=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0");
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.status(200).send(`<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Oura Connected</title>
    <style>
      body {
        align-items: center;
        background: #f7f7f4;
        color: #20201d;
        display: flex;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        justify-content: center;
        min-height: 100vh;
        margin: 0;
      }
      main {
        max-width: 440px;
        padding: 32px;
        text-align: center;
      }
      h1 {
        font-size: 28px;
        font-weight: 650;
        margin: 0 0 12px;
      }
      p {
        color: #5d5b55;
        font-size: 16px;
        line-height: 1.5;
        margin: 0;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Oura connected</h1>
      <p>Setup is complete. You can close this page now.</p>
    </main>
  </body>
</html>`);
  } catch (error) {
    res.status(500).send("Oura setup failed. Please close this page and try again.");
  }
}

function parseCookie(cookieHeader) {
  return Object.fromEntries(
    cookieHeader
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const index = part.indexOf("=");
        return index === -1 ? [part, ""] : [part.slice(0, index), decodeURIComponent(part.slice(index + 1))];
      }),
  );
}
