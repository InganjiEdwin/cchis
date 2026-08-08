# Mobitech SMS provider

Status date: 2026-08-08

Mobitech is CCHIS’s active SMS provider route. Africa’s Talking remains in the repository, with its adapter, configuration, migrations and tests preserved, but is explicitly parked by `AFRICAS_TALKING_ENABLED=false`. It is available for later sandbox verification and is not selected by the active route.

The CCHIS adapter follows the proven Linda Mwananchi integration:

- `POST` to `MOBITECH_API_URL` using JSON and the `h_api_key` header.
- Payload fields are `serviceId`, `shortcode`, and one `messages` item containing normalized Kenyan `mobile`, `message`, and the stable CCHIS `client_ref` idempotency key.
- Acceptance parsing uses Mobitech `status_code`, `status_desc`, `schedule_details[].message_id`, `schedule_status`, and `schedule_desc` values.
- Only timeouts, connection failures and HTTP 5xx responses are retryable. Authentication, validation, invalid-number, malformed-response and provider-rejection failures are terminal.
- Provider acceptance is stored separately from final delivery. Final delivery is reconciled through `POST /api/v1/sms/mobitech/callback/`; repeated callback events are idempotent through `AlertDeliveryEvent.event_key`.

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
AFRICAS_TALKING_ENABLED
```

The callback token is an internal CCHIS route secret; it is not sent to Mobitech. `MOBITECH_DELIVERY_CALLBACK_URL` records the externally reachable callback destination configured for the provider. The local Docker callback URL is not provider-reachable and must not be presented as live delivery evidence.

Local stub delivery is recorded as `SIMULATED`, has no provider message identifier, and cannot be represented as external delivery. A configured Mobitech send is only `QUEUED` with provider acceptance until a final callback changes the provider delivery state.

No controlled live Mobitech request is recorded in this repository yet. A designated authorized test recipient and a provider-reachable callback URL or officially supported status-query path are required before updating the technical capability audit. SMS provider wiring does not make CCHIS production-ready; model truth, external source integrations, security operations and operational verification remain separate requirements.
