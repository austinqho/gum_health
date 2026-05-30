import crypto from "node:crypto";
import { buildAuthorizeUrl } from "../../../lib/oura.js";

// Reference-only OAuth start endpoint.
//
// Swap OURA_REDIRECT_URI in the environment to Gumbo's hosted callback URL.
// This route is not used by the local Mac polling pipeline.
export default function handler(req, res) {
  const state = crypto.randomBytes(24).toString("base64url");
  const secure = req.headers["x-forwarded-proto"] === "https" ? "; Secure" : "";
  res.setHeader("Set-Cookie", `oura_oauth_state=${state}; HttpOnly${secure}; SameSite=Lax; Path=/; Max-Age=1800`);
  res.writeHead(302, { Location: buildAuthorizeUrl(state) });
  res.end();
}
