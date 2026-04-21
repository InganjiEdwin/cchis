# Alert Delivery Architecture

## Purpose

This document defines the v1 alert-delivery boundary so future channels, retries, and audit requirements can evolve without tearing through the risk-rule path.

## Current v1 Flow

1. A risk event is selected for alerting.
2. `create_alerts_for_riskscore(...)` creates durable `Alert` records.
3. Rule decisions end at alert creation.
4. Delivery work begins after alert records already exist.
5. `deliver_alert_task` processes queued SMS alerts and updates delivery state per alert.

## Separation of Concerns

### Rule Layer

- decides whether alerts should exist
- decides which channels should be used
- builds the alert message payload
- persists alert records before transport begins

### Delivery Layer

- takes an existing `Alert`
- attempts transport for that alert only
- updates status, attempt counters, retry timing, provider metadata, and failure state
- resolves a transport adapter instead of embedding one provider implementation in the alert workflow

## Provider Adapter Boundary

- SMS delivery is resolved through `get_sms_provider(...)`
- provider implementations live outside the alert-rule flow
- v1 currently supports:
  - `stub`
  - `africastalking`
- future providers should implement the same `send(phone_number, message)` contract and return a delivery result without changing alert-rule code

## Lifecycle States

- `QUEUED`: alert exists and is waiting for delivery work
- `RETRY_PENDING`: a delivery attempt failed, but another attempt is allowed
- `DELIVERED`: delivery completed successfully
- `FAILED`: delivery exhausted retries or hit a terminal error

Dashboard alerts are treated as internal-delivery records and are marked `DELIVERED` immediately. SMS alerts are created first, then delivered through the transport path.

## Retry Policy

- retries are tracked on the `Alert` row
- `attempt_count` records how many tries have happened
- `max_attempts` defines the terminal boundary
- `next_retry_at` records when the next retry was scheduled
- failed-but-retryable alerts use `RETRY_PENDING`
- terminal failures use `FAILED`

## Why This Matters

This boundary keeps v1 ready for later work:

- provider adapters in a future phase
- admin audit views over delivery attempts
- dead-letter handling or operator requeue flows
- additional channels such as WhatsApp or email
