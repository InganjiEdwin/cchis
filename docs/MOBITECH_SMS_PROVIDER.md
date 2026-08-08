# Mobitech SMS provider

Status date: 2026-08-08

Mobitech is CCHIS’s active SMS provider route. Africa’s Talking remains in the repository, with its adapter, configuration, migrations and tests preserved, but is explicitly parked by `AFRICAS_TALKING_ENABLED=false`. It is available for later sandbox verification and is not selected by the active route.

The delivery-report contract is based on Mobitech’s published [developer API contract](https://mobitechtechnologies.com/developers) and the working Linda Mwananchi integration. Mobitech accepts a provider callback URL for delivery changes; CCHIS therefore uses a secret route token in the provider-reachable callback URL. CCHIS does not require a custom callback header that Mobitech does not document or send.

The CCHIS adapter follows the proven Linda Mwananchi integration:

- `POST` to `MOBITECH_API_URL` using JSON and the `h_api_key` header.
- Payload fields are `serviceId`, `shortcode`, and one `messages` item containing provider-confirmed E.164 Kenyan `mobile` (`+254…`), `message`, and a short numeric `client_ref` derived from the persisted alert ID. The UUID remains CCHIS’s internal idempotency key for retries.
- Acceptance parsing uses Mobitech `status_code`, `status_desc`, `schedule_details[].message_id`, `schedule_status`, and `schedule_desc` values.
- Only timeouts, connection failures and HTTP 5xx responses are retryable. Authentication, validation, invalid-number, malformed-response and provider-rejection failures are terminal.
- Provider acceptance is stored separately from final delivery. Final delivery is reconciled through `POST /api/v1/sms/mobitech/callback/<route-token>/`; repeated callback events are idempotent through `AlertDeliveryEvent.event_key`.
- The configured callback URL must be HTTPS in shared environments and must end with the same route token held in `MOBITECH_DELIVERY_CALLBACK_TOKEN`. Empty, missing or mismatched callback authentication rejects the callback before payload processing.
- Mobitech’s published premium API also documents bearer-authenticated `/api/messages/{id}/stats` and `/api/messages/{id}/receipts` endpoints. CCHIS supports these through `MOBITECH_STATUS_API_URL` only when the account explicitly supports polling for the IDs returned by its configured send endpoint; it does not silently assume that bulk `sendmultiple` IDs are interchangeable with premium API IDs.

Configuration names are:

```text
SMS_PROVIDER
MOBITECH_API_URL
MOBITECH_API_KEY
MOBITECH_SENDER_ID
MOBITECH_SERVICE_ID
MOBITECH_DELIVERY_CALLBACK_URL
MOBITECH_DELIVERY_CALLBACK_TOKEN
MOBITECH_HTTP_TIMEOUT_SECONDS
MOBITECH_STATUS_API_URL
MOBITECH_STATUS_AUTH_SCHEME
MOBITECH_STATUS_HTTP_TIMEOUT_SECONDS
AFRICAS_TALKING_ENABLED
```

`MOBITECH_DELIVERY_CALLBACK_URL` is the exact provider-reachable URL given to Mobitech and contains the route token as its final path segment. The token is therefore part of the callback destination, not a custom header. Application request logging redacts that path segment. The local Docker callback URL is not provider-reachable and must not be presented as live delivery evidence.

When no valid callback is available in a shared environment, startup requires an HTTPS `MOBITECH_STATUS_API_URL` ending in `/api/messages/{message_id}/receipts` or `/api/messages/{message_id}/stats`, plus the Mobitech API key and `MOBITECH_STATUS_AUTH_SCHEME=bearer`. Polling results use the same sanitized, idempotent `AlertDeliveryEvent` reconciliation path.

Local stub delivery is recorded as `SIMULATED`, has no provider message identifier, and cannot be represented as external delivery. A configured Mobitech send is only `QUEUED` with provider acceptance until a final callback changes the provider delivery state.

Sanitized controlled-run evidence (2026-08-08): the authorized single-recipient test was dispatched through `trigger_alerts_task` and the Celery `deliver_alert_task`; the alert and task execution persisted. The provider-confirmed E.164 mobile representation was implemented, but the task-driven attempts still received HTTP 200 application-level rejection (`status_code=1006`), with no provider message identifier or acceptance and no delivery event persisted. The account’s logged-in web session was not available to the connected browser, and local callback/polling reconciliation was not configured. Adapter complete; external delivery verification blocked.

This blocked attempt is not end-to-end completion, so the technical capability audit remains unchanged and the overall repository remains not production ready. A later run requires an accepted provider message, a provider-reachable callback or supported authenticated polling result, final delivery status, and an idempotent delivery event before the audit may be updated.
