# Oura Webhook Integration Reference

This folder is a reference deployment for teams that want Oura OAuth and
webhooks on a hosted backend. It is intentionally separate from the local
HealthSync watcher.

The active local pipeline is:

```text
src/health_observer/collection.py
  -> src/health_observer/providers/oura/api.py
  -> ~/Desktop/HealthSync/observations.jsonl
```

Nothing in this folder is imported by that pipeline.

The canonical observation transform is the Python local polling transform at
`../src/health_observer/providers/oura/transform.py`. The JavaScript transform
in `lib/ouraTransform.js` is reference-only and is not currently parity-tested
against Python output.

## What This Proves

- OAuth redirect handling through `/api/oura/oauth/start` and
  `/api/oura/oauth/callback`.
- Token storage and refresh through the storage functions in `lib/db.js`.
- Oura webhook verification and challenge handling through
  `/api/oura/webhook`.
- Webhook event handling: receive Oura's notification, fetch the full provider
  object by `object_id`, store the raw record, and write an observation row.

## What Gumbo Should Swap

- Replace `lib/db.js` with Gumbo's database/storage layer.
- Replace `.env` values with Gumbo's Oura app credentials:
  - `OURA_CLIENT_ID`
  - `OURA_CLIENT_SECRET`
  - `OURA_REDIRECT_URI`
  - `OURA_WEBHOOK_URL`
  - `OURA_WEBHOOK_VERIFICATION_TOKEN`
- Point `OURA_REDIRECT_URI` to Gumbo's OAuth callback endpoint.
- Point `OURA_WEBHOOK_URL` to Gumbo's Oura webhook endpoint.
- Keep the OAuth, webhook verification, object fetch, and user routing logic.
- Before using `lib/ouraTransform.js` in production, add golden fixture tests
  proving its output matches the canonical Python observation contract,
  including required metadata such as `measurement_semantics`, `sync_semantics`,
  and raw references.

## Important Boundary

This is not the default HealthSync path. The default path is local polling, which
keeps participant data on the Mac and does not require a server. This folder is
for a hosted deployment where Gumbo chooses to receive Oura webhooks centrally.
The OAuth/webhook/storage scaffolding is the reusable part; the JavaScript
transform should be treated as reference code until parity tests exist.

The `api/debug/*` routes are development-only inspection helpers. Do not expose
them in a production app without authentication.
