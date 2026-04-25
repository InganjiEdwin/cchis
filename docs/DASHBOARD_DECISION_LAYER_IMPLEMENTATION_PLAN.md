# Dashboard Decision Layer Implementation Plan

## Goal

Evolve the dashboard from a good monitoring UI into the decision layer of the climate-health system.

This plan covers both backend and frontend work required to make the dashboard:

- express system state clearly
- surface trigger conditions honestly
- support anticipatory decision-making
- connect ward risk, alerts, CHV response, and facility readiness
- remain aligned with the system architecture instead of becoming a decorative report page

The dashboard should answer four questions quickly:

1. Where is the problem?
2. What is happening?
3. Why does it matter now?
4. What should happen next?

---

## Current State

The dashboard already has a strong foundation:

- backend-backed Migori ward geometry
- backend-backed overview KPIs
- interactive risk hotspot map
- KPI-to-map filtering
- alert-linked hotspot markers
- a first-pass attention panel
- real run-to-run and recent-history trend labels in the hotspot tooltip

But the current dashboard is still incomplete as a decision system because:

- there is no explicit system state layer
- there is no visible trigger state
- the attention panel is informative, not yet command-oriented
- prediction is not visible in the dashboard map
- facility readiness is not represented in the overview surface
- freshness is compressed into a single timestamp, which weakens trust
- KPI, alert, and action vocabulary is not fully normalized

---

## Design Principles

### 1. Risk, Alert, and Action must remain separate concepts

- `Risk` = model output or assessed probability
- `Alert` = event or threshold crossing
- `Action` = recommended operational response

The UI should never collapse these into one ambiguous signal.

### 2. The map is a triage surface, not a full analytics workspace

The dashboard map should quickly orient the operator toward where to look now.
Deep analysis belongs in ward intelligence, alerts, CHV operations, and facility readiness.

### 3. Prediction is core product value, not a nice-to-have

The dashboard must expose both current state and anticipated state.

### 4. Trigger state must be visible

If thresholds are crossed, the dashboard must clearly show that the system has moved from monitoring into response mode.

### 5. Every visible component must either:

- show a problem
- explain why it matters
- or lead to an action

If it does none of the above, it should be removed or redesigned.

### 6. The dashboard must reflect promoted operational truth

The dashboard should not elevate experimental, seeded, benchmark-only, or unpromoted outputs into apparent operational authority.

Industry-standard practice is not to show the fanciest model output by default.
It is to show the most governable promoted output that supports the best operational decision.

---

## Scope

This plan covers:

- overview backend contracts
- BFF route expansion
- dashboard frontend interaction model
- map prediction mode
- trigger state and system state presentation
- first-class notification delivery and lifecycle management
- action panel redesign
- facility readiness summary linkage
- temporal trend and freshness improvements
- verification and final audit

This plan does not yet cover:

- interactive scenario simulation tooling
- direct dispatch or messaging execution backends
- full geospatial animation or playback history
- full incident-management workflow orchestration beyond notification and alert lifecycle basics

Those can follow after this plan is complete.

### ML roadmap dependency

Prediction work in this dashboard plan depends on a separate backend model roadmap:

- [BACKEND_ML_MODEL_ROADMAP_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_ROADMAP_PLAN.md)

That roadmap explicitly sets:

- current live baseline = `Logistic Regression`
- next model to add = `Random Forest` benchmark
- later evolution = `XGBoost / LightGBM`

The dashboard must not imply a more advanced live model family than the backend has actually implemented and promoted.

### ETL and feature-pipeline dependency

Prediction and alert trust in this dashboard plan also depend on a separate backend data-pipeline plan:

- [BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md)

That plan defines:

- which data is required to support the proposal's `7 to 14 day` ward-level cholera prediction goal
- how frequently core data domains should be ingested
- how feature lineage and freshness are tracked
- how both `Logistic Regression` and `Random Forest` can eventually operate on comparable prediction inputs

The dashboard must not overstate prediction confidence when ETL freshness, coverage, or lineage are weak.

### Facility forecasting dependency

Facility-readiness and surge-pressure outputs in this dashboard plan also depend on a separate forecasting track:

- [BACKEND_FACILITY_BURDEN_FORECASTING_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_FACILITY_BURDEN_FORECASTING_PLAN.md)

That plan covers:

- `Negative Binomial Regression` as the early facility burden forecasting baseline
- projected case-burden outputs
- projected pressure and readiness-state outputs
- promotion discipline before dashboard exposure

### Execution-order note

Implementation should follow this sequence:

1. `ETL scheduling first`
2. `daily scoring next`
3. `retraining cadence after that`
4. `dashboard consumes only promoted outputs`

The dashboard should never present seeded, benchmark-only, or unpromoted model outputs as if they were the live prediction authority.

---

## Operating Model

The intended operating model for alerts and actions is:

- `detection` = automated
- `threshold evaluation` = automated
- `alert triggering` = hybrid
- `response action` = hybrid

This dashboard should therefore present the system as:

`intelligent early warning + assisted response`

It should not present the product as a fully autonomous response engine.

### Current and target behavior

Phase 1 behavior for the dashboard decision layer should be:

- the system detects and surfaces trigger conditions automatically
- a user reviews and confirms alert triggering
- the UI makes trigger reasoning explicit
- the UI pre-fills the next best action instead of making users start from scratch

Later phases may introduce guarded automation for low-risk or high-confidence cases, but the dashboard plan should assume human confirmation unless a backend contract explicitly proves otherwise.

---

## Notification Operating Standard

Notifications must be treated as first-class operational objects, not as cosmetic top-bar badges.

The target notification model is:

- backend-owned
- websocket-delivered where possible
- query-backed as fallback
- lifecycle-managed
- auditable
- role-aware
- dismissible or acknowledgeable based on notification type

The dashboard should support notification states such as:

- `new`
- `seen`
- `acknowledged`
- `resolved`
- `dismissed`
- `expired`

Every visible notification should have:

- a source
- a severity
- a type
- a created timestamp
- a current lifecycle state
- an associated object or route when relevant

The system must not use fake unread counts, local-only mark-as-read behavior, or UI-only notification queues once this work is complete.

---

## Phase 0: Baseline Audit

### Objective

Freeze the current truth before expanding the dashboard again.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend checks

- confirm current overview route payload shape
- confirm current map route payload shape
- record which dashboard values are:
  - direct backend fields
  - frontend derivations over backend data
  - placeholder or static UI copy

### Frontend checks

- inventory current overview interactions:
  - KPI clicks
  - map filter chips
  - hotspot selection
  - attention panel behavior
- record where the current dashboard still reads as a report rather than a decision layer

### Output

Create:

- `docs/DASHBOARD_DECISION_LAYER_PHASE_0_STATUS.md`

This should explicitly state what is already real, what is derived, and what is still missing.

---

## Phase 1: Vocabulary and State Model

### Objective

Normalize the dashboard’s mental model before adding more behavior.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Define a clear overview state model that distinguishes:

- system state
- risk state
- alert state
- action state

Recommended contract additions:

- `system_state`
  - `stable | watch | action_required`
- `system_state_reason`
- `trigger_summary`
  - counts of triggered wards
  - counts of wards under watch
  - counts of wards requiring action

### Frontend work

Normalize visible language across the overview page:

- `Risk`
- `Alert`
- `Action`

Examples:

- `High risk wards` remains risk language
- `Active alerts` remains alert language
- `Immediate attention` becomes explicit action language

### Output

The dashboard should no longer mix risk and action wording casually.

---

## Phase 2: System State Layer

### Objective

Expose the platform’s trigger layer clearly.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Add an overview state summary contract that derives:

- `system_state`
- `state_reason`
- `trigger_count`
- `watch_count`
- `action_required_count`
- optional `last_triggered_at`

Derivation rule should be explicit and documented.

Example v1 rules:

- `stable`
  - no visible high-risk wards
  - no unresolved trigger conditions
- `watch`
  - medium-risk trend growth
  - alert activity present but below action threshold
- `action_required`
  - one or more wards exceed configured action threshold
  - one or more trigger rules fire

### Frontend work

Add a top-level state module above or within the map section:

- `System Stable`
- `Watch`
- `Action Required`

It should visually change tone, but not over-saturate the whole page.

### Verification

- prove the state changes under realistic seeded conditions
- ensure empty states do not appear dead or misleading

---

## Phase 2A: First-Class Notifications and Websocket Lifecycle

### Objective

Build a mature notification system that supports live operational awareness and explicit lifecycle management.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend implementation

Add a backend-owned notification domain with clear lifecycle semantics.

Recommended core model fields:

- `id`
- `public_id`
- `type`
- `severity`
  - `info`
  - `warning`
  - `critical`
- `title`
- `body`
- `source_system`
- `source_object_type`
- `source_object_id`
- `href`
- `state`
  - `new`
  - `seen`
  - `acknowledged`
  - `resolved`
  - `dismissed`
  - `expired`
- `created_at`
- `seen_at`
- `acknowledged_at`
- `resolved_at`
- `dismissed_at`
- `expires_at`
- `recipient_scope`
- `recipient_role`
- `recipient_user`
- `metadata`

Recommended backend endpoints:

- `GET /api/v1/notifications/`
- `GET /api/v1/notifications/{id}/`
- `POST /api/v1/notifications/{id}/seen/`
- `POST /api/v1/notifications/{id}/acknowledge/`
- `POST /api/v1/notifications/{id}/dismiss/`
- `POST /api/v1/notifications/mark-all-seen/`

Optional follow-on endpoints:

- `GET /api/v1/notifications/unread-count/`
- `GET /api/v1/notifications/stream-token/`

#### Websocket layer

Implement a real-time notification transport with a disciplined fallback path.

Preferred behavior:

- websocket channel for authenticated dashboard sessions
- server publishes notification create/update/delete events
- client subscribes by user and role scope
- if websocket is unavailable, fallback to polling without changing notification semantics

Recommended event types:

- `notification.created`
- `notification.updated`
- `notification.resolved`
- `notification.deleted`
- `notification.count_changed`

Recommended payload shape:

- event type
- notification object
- unread count
- changed fields when relevant

#### Lifecycle rules

The backend must define which notification types:

- require acknowledgement
- can be dismissed
- auto-resolve
- expire automatically
- remain pinned until actioned

Examples:

- critical trigger notifications may require acknowledgement
- transient sync completion notices may auto-expire
- stale data warnings may resolve automatically when freshness recovers

#### Audit and traceability

Notification lifecycle transitions must be auditable.

At minimum, record:

- user
- action
- old state
- new state
- timestamp

### Frontend implementation

Treat notifications as a real operational surface, not just a dropdown.

Required surfaces:

- top-bar notification entry point
- notification drawer or panel
- unread badge from backend truth
- real-time update handling
- item detail and lifecycle controls

Required behaviors:

- new notifications appear live without full page reload
- unread count is backend-owned
- mark-seen and acknowledge actions call the backend
- notification rows visibly reflect lifecycle state
- clicking a notification routes to the relevant operational page when applicable

#### UX rules

- critical notifications may remain pinned until acknowledged or resolved
- warning notifications may be dismissible
- informational notifications should not dominate the interface
- the UI should clearly distinguish:
  - `new`
  - `seen`
  - `acknowledged`
  - `resolved`

#### Integration with system state

Notification severity and system state should reinforce each other without collapsing into one signal.

Examples:

- `Action required` system state may coexist with one or more critical trigger notifications
- a resolved system state should downgrade or resolve related notifications where appropriate

### Verification

Prove:

- websocket event delivery works
- polling fallback works if sockets are unavailable
- lifecycle transitions persist correctly
- unread counts remain correct across multiple clients
- role-scoped visibility is enforced

### Output

Create:

- `docs/DASHBOARD_DECISION_LAYER_PHASE_2A_NOTIFICATIONS.md`

This should document:

- lifecycle model
- websocket event contract
- fallback behavior
- notification state rules

---

## Phase 3: Action Panel Upgrade

### Objective

Turn `Immediate Attention` into a real command-oriented module.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Add an overview decision summary contract for the top-priority ward or wards:

- `top_priority_ward`
- `reason_flagged`
- `recommended_action`
- `decision_mode`
  - `risk_only`
  - `triggered`
  - `alert_active`
  - `facility_capacity_concern`

Optional follow-on fields:

- `eligible_actions`
  - `view_alerts`
  - `dispatch_chvs`
  - `send_message`
  - `investigate`

### Frontend work

Redesign the panel so it always feels alive:

If a priority ward exists:

- show ward
- show why it is flagged
- show recommended action
- show one or two clear CTAs

If no priority ward exists:

- show `System stable`
- show recent activity summary
- show next likely area to monitor

### Interaction behavior

- map click updates the panel
- KPI selection can update the panel context
- selected state remains clear without collapsing the whole page into a drill-down

---

## Phase 3A: Manual Alert Request Flow V1

### Objective

Make the `Create Alert` flow feel operational and trustworthy while staying honest about the current backend contract.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Current backend contract

Current v1 backend capability is narrow:

- select one ward
- queue a trigger request
- optionally queue CHV SMS delivery
- backend uses the latest matching risk score

The dashboard must not fake:

- templates
- scheduling
- approvals
- multi-target campaigns
- rich delivery orchestration
- fake alert IDs
- fake progress timelines

### Backend implementation

#### Contract clarity

Confirm and document the existing trigger endpoint as the source of truth:

- `POST /api/v1/alerts/trigger/`

Recommended response shape for the dashboard:

- `alert_id` if created and returned
- `ward_id`
- `ward_name`
- `risk_level`
- `risk_score`
- `predicted_cases`
- `send_sms`
- `queued_at`
- `message`

If the current endpoint does not return enough detail for a trustworthy success state, extend it minimally rather than inventing frontend-only success data.

#### Optional backend additions

Where available, expose:

- `last_risk_update_at`
- `estimated_chv_recipient_count`

If recipient count is not supported, the frontend must explicitly say so.

### Frontend implementation

#### Entry point

Top-bar button remains:

- `Create Alert`

#### Drawer structure

Title:

- `Create Alert Request`

Subtitle:

- `Queue a backend alert trigger for one ward using the latest available risk score.`

#### Step 1: Select ward

Show:

- search input
- ward list
- ward risk level
- risk score
- predicted cases
- last risk update if available

Ward ordering:

- high risk first
- medium risk second
- low risk last
- wards with recent alerts visibly marked

On ward click:

- selection must be visually clear
- selected ward summary appears in a sticky summary panel

#### Step 2: Delivery

After ward selection, show:

- `Delivery`
- checkbox or toggle:
  - `Queue CHV SMS delivery`

Helper text:

- `If enabled, the backend will attempt SMS delivery to CHVs linked to this ward.`

Show:

- estimated recipients if backend returns it
- otherwise:
  - `Recipient count unavailable from current contract`

#### Step 3: Review

Before final submit, show a review block containing:

- ward
- risk level
- risk score
- predicted cases
- SMS delivery enabled/disabled
- backend endpoint reference:
  - `/api/v1/alerts/trigger/`

Warning copy:

- `This will create a real backend alert trigger request. Message templates, scheduling, approvals, and multi-ward campaigns are not part of this v1 contract.`

CTA copy:

- primary: `Queue Alert Request`
- secondary: `Back`

#### Submit behavior

On submit:

- call only the real existing mutation
- disable the button while pending
- show:
  - `Queueing request...`

#### Success state

If backend succeeds, replace the form with:

- title:
  - `Alert request queued`
- returned alert ID only if the backend actually returns it
- selected ward
- SMS queued yes/no
- timestamp

Actions:

- `View Alert Detail`
- `Go to alerts`
- `Create another`

Routing:

- if `alert_id` exists:
  - `/alerts/{id}`
- if no `alert_id` is returned:
  - `/alerts`
  - plus a success toast

#### Error state

If backend fails:

- show backend error if available
- fallback:
  - `Unable to queue alert request`
- preserve selected ward and SMS state
- allow retry

#### UX language rules

Rename technical phrasing:

- avoid `Queue a backend trigger request`
- use:
  - `Create Alert Request`

Keep the honesty notice, shortened:

- `V1 alert creation supports one ward at a time. Templates, scheduling, approvals, and multi-target campaigns will be added after backend workflow support exists.`

### Success condition

The flow should feel like a real operational request path, but every visible field must come from backend truth or be clearly labeled as unavailable.

---

## Phase 3B: Trigger Detection and Human Review Flow

### Objective

Reflect the intended hybrid model: the system detects trigger conditions automatically, but a user confirms the response.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend implementation

Add a trigger-event summary contract to overview and/or a dedicated trigger feed.

Recommended fields:

- `trigger_id`
- `ward_id`
- `ward_name`
- `risk_score`
- `risk_level`
- `trend_label`
- `trigger_reason_items`
- `confidence`
- `triggered_at`
- `recommended_action`
- `dismissible`

Support both:

- single-trigger review
- multiple-trigger queue view

If real-time push is not available yet, polling is acceptable as long as the contract is honest.

### Frontend implementation

#### Trigger notification

When a threshold is detected, show a non-blocking notification:

- `New high-risk trigger detected`
- ward
- score
- trend

Actions:

- `Review`
- `Dismiss`

Do not open a blocking modal immediately.

#### Map reaction

When a trigger arrives:

- briefly highlight or pulse the ward
- optionally adjust map focus subtly
- do not hijack the user

#### System state reaction

Update the dashboard system-state module:

- `Stable`
- `Watch`
- `Action required`

#### Review drawer

When the user clicks `Review`, open a pre-filled trigger review panel.

Header:

- `Trigger detected`
- ward
- risk level
- score
- trend

Section 1:

- `Why this triggered`
- threshold breach
- upward trend
- recent alerts
- anomaly or driver explanation where supported

Section 2:

- `Recommended action`
- confidence
- expected operational effect

Section 3:

- pre-filled alert configuration
- ward locked
- delivery toggle
- message preview only if backend supports it

Decision actions:

- `Trigger Alert`
- `Modify`
- `Dismiss`

Dismissal should be logged in the backend if a dismissal contract exists.
If not, dismissal should remain local and be labeled accordingly.

### Rules

- do not auto-trigger silently
- do not hide trigger reasoning
- do not force users to rebuild the flow manually once a trigger is detected

---

## Phase 4: Prediction Mode on the Map

### Objective

Expose the system’s anticipatory value directly on the overview map.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Add a prediction layer to the overview map contract.

#### Model alignment requirement

Prediction UI in this phase must remain aligned with the backend model roadmap.

For the current project phase, that means:

- live prediction baseline = `Logistic Regression`
- `Random Forest` is the next intended benchmark, not an already-live replacement
- `XGBoost / LightGBM` remain later evolution, not current production truth

The dashboard may expose:

- `prediction_model_version`

But it must not imply Random Forest or boosting-based production behavior until backend promotion actually happens and is documented.

Preferred contract shape:

- `current_risk_level`
- `current_risk_score`
- `prediction`
  - `horizon_days`
  - `predicted_risk_level`
  - `predicted_risk_score`
  - `predicted_cases`
  - `prediction_generated_at`
  - `prediction_model_version`

If prediction is not yet available for all wards, the contract must expose that honestly.

### Frontend work

Add a map toggle:

- `Current`
- `Predicted (7d)`

Predicted mode should remain visually related to current mode, not become a second totally different map.

Recommended visual semantics:

- predicted fills slightly lighter or patterned
- tooltip explicitly says `Predicted risk`
- attention panel updates its language to prediction context when in predicted mode

### Rules

- do not mix current and predicted semantics without a visible mode switch
- do not imply prediction freshness if backend timestamps are stale

---

## Phase 5: Temporal Trust and Freshness

### Objective

Replace vague staleness cues with explicit trust signals.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Expose multiple freshness timestamps:

- `last_model_run_at`
- `last_data_sync_at`
- `last_alert_ingestion_at`
- `prediction_generated_at`

Optional:

- `freshness_state`
  - `fresh`
  - `delayed`
  - `stale`

### Frontend work

Replace a single ambiguous `Updated X hrs ago` label with:

- `Model updated`
- `Data sync`
- `Alerts refreshed`
- `Notifications live`

The operator should know whether the issue is:

- model freshness
- data freshness
- or delivery freshness
- or notification transport freshness

---

## Phase 6: KPI Temporal Context

### Objective

Make KPIs express direction, not just state.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Extend overview metrics with comparative windows.

Examples:

- `high_risk_delta_vs_yesterday`
- `medium_risk_delta_vs_yesterday`
- `alerts_today_delta_vs_last_24h`
- `delivered_alert_rate_delta_vs_last_window`

### Frontend work

Add micro-deltas under KPI values:

- `+2 since yesterday`
- `-40% vs last week`

These should remain compact and not overload the row.

### Interaction

Hovering or clicking a KPI should continue to influence the map state.
The temporal delta should reinforce why the operator should care now.

---

## Phase 7: Map Guidance and Attention Flow

### Objective

Guide the eye instead of only offering filters.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Expose enough ranking data to identify:

- top triggered ward
- most active alert ward
- biggest recent escalation
- predicted highest-risk ward

### Frontend work

Improve spatial attention cues:

- stronger focus behavior when KPI or chip is selected
- smoother fade of irrelevant wards
- optional animated focus transition toward relevant wards
- keep movement short and meaningful

Do not add gratuitous animation.

### Success condition

An operator should be able to identify the highest-priority ward in under one second.

---

## Phase 8: Facility Readiness Linkage

### Objective

Connect risk and alert geography to response capacity.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Add a lightweight facility readiness signal to overview.

Minimum useful fields:

- `facilities_at_risk_count`
- `priority_facilities`
- per ward:
  - `facility_capacity_signal`
  - `facility_readiness_tone`

#### Dedicated facility-readiness data model requirement

This dashboard phase depends on a stable backend facility-readiness model shape rather than ad hoc summary text.

At minimum, backend readiness outputs should expose:

- `facility_id`
- `facility_name`
- `readiness_state`
  - `ready`
  - `watch`
  - `capacity_concern`
- `readiness_score`
- `projected_pressure_score`
- `projected_case_burden` where available
- `driving_ward_ids`
- `readiness_factors`
- `snapshot_at`
- `generated_at`
- `freshness_state`

If a full readiness model does not exist yet, the contract should expose a truthful derived proxy from:

- ward risk
- active facilities
- existing facility readiness data already present in the system
- catchment population exposure where available

### Frontend work

Add one lightweight readiness layer to overview:

- summary metric
- optional facility markers or readiness cue on hotspot map
- readiness-aware detail in the action panel when facility pressure is relevant

This should support the operator question:

`If this ward worsens, can the facilities cope?`

### Interaction expectations

The dashboard should be able to show, at least in lightweight form:

- which facilities are under watch
- which facilities are at capacity concern
- which wards are driving expected facility pressure
- why a facility readiness warning exists

If the facility-readiness layer is still proxy-based, the UI must keep that honest in wording and final audit notes.

---

## Phase 9: Alert and Trigger Linkage

### Objective

Make the dashboard reflect actual trigger behavior, not just alert counts.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

Add explicit trigger-state data to overview:

- `triggered_wards`
- `trigger_reason`
- `trigger_severity`
- `triggered_at`
- `recommended_response`

Where possible, connect alert delivery status to trigger state:

- triggered and delivered
- triggered but retry pending
- triggered but failed

### Frontend work

Support alert-aware map modes:

- active alerts
- delivery concern
- trigger-active wards

This is especially important for the `delivered from visible alerts` KPI so it can show more than alert location alone.

---

## Phase 9A: Alert Lifecycle, Timeline, and Feedback Loop

### Objective

Treat alerts as evolving operational processes, not one-time events.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend implementation

Add or extend alert detail contracts so each alert can expose lifecycle events and response feedback.

Recommended alert lifecycle model:

- `triggered`
- `notified`
- `field_response`
- `escalated`
- `monitoring`
- `resolved`

Recommended backend fields:

- `status`
  - `active`
  - `monitoring`
  - `escalated`
  - `resolved`
- `timeline`
  - ordered events with timestamps, actor, type, message
- `delivery_summary`
- `chv_response_summary`
- `facility_response_summary`
- `recommended_next_action`
- `last_updated_at`

Recommended timeline event categories:

- `system`
- `communication`
- `field_activity`
- `escalation`
- `resolution`

### Frontend implementation

The alert detail page should become a living workflow surface.

Header should show:

- ward
- alert classification
- score
- trend
- status
- triggered time

Main timeline should show:

- alert triggered
- CHV notification sent
- CHV responses received
- field updates
- escalation events
- stabilization or closure

Right-side status panel should show:

- current risk direction
- alert status
- response coverage
- facility pressure signal
- recommended next action

Action controls may include:

- `Dispatch additional CHVs`
- `Send follow-up SMS`
- `Escalate to facility`
- `Close alert`

These should only be live when backed by real backend contracts.
Otherwise they should be visibly blocked or absent.

### Feedback loop requirement

The system should visually support:

- alert creation
- field response
- new data coming back in
- updated risk
- resolution

This is the point where the dashboard and alert detail stop being static reporting surfaces and become a living operational loop.

---

## Phase 10: Scenario and Simulation Readiness

### Objective

Prepare the dashboard for future scenario exploration without prematurely building the full feature.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend preparation

Document what a simulation contract would need:

- rainfall adjustments
- forecast perturbation inputs
- predicted risk recomputation envelope
- safe non-production execution rules

### Frontend preparation

Reserve the interaction pattern for:

- `What if rainfall increases?`
- `What if response is delayed?`

Do not ship fake simulation controls before there is a real backend contract.

---

## Phase 11: Demo Scenario Data and Seeded Decision States

### Objective

Seed realistic non-production data so the dashboard can be verified across meaningful operational states.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

This phase is intentionally placed late in the plan.
The goal is to validate the decision layer after contracts and behaviors exist, not to use simulated data as a substitute for backend completion.

### Backend work

Add or extend seed tooling so non-production environments can create believable dashboard states for:

- `Stable`
- `Watch`
- `Action required`

Recommended seeded data types:

- recent `RiskScore` history across multiple runs
- predicted risk outputs for a 7-day horizon
- triggered alerts
- alert delivery outcomes:
  - delivered
  - retry pending
  - failed
- ward-level trigger reasons
- lightweight facility pressure or readiness signals
- visible freshness timestamps that differ by source

Preferred approach:

- seed explicit scenario bundles instead of random fake records
- keep scenario names stable and human-readable

Examples:

- `stable_baseline`
- `localized_watch_cluster`
- `escalating_triggered_hotspot`
- `delivery_failure_concern`
- `facility_capacity_pressure`

### Frontend work

Ensure the dashboard can render and remain truthful under each seeded scenario:

- state banner
- map mode
- KPI deltas
- attention panel
- trigger language
- facility linkage
- freshness cues

### Rules

- all seeded scenario data must be explicitly non-production
- seeded model outputs must not masquerade as real live model runs
- scenario seeding is for validation, demos, and QA, not for proving backend completeness

### Output

Create:

- `docs/DASHBOARD_DECISION_LAYER_PHASE_11_SCENARIO_DATA.md`

This should describe:

- seeded scenario names
- what each scenario is meant to prove
- which dashboard behaviors each scenario should exercise

---

## Phase 12: Verification and Regression

### Objective

Prove the dashboard behaves as a decision layer, not just as a prettier overview.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend verification

- overview state contract tests
- notification lifecycle tests
- websocket notification event tests
- trigger-state derivation tests
- prediction contract tests
- temporal delta tests
- facility readiness summary tests

### Frontend verification

- type checks
- interaction checks for:
  - KPI click
  - chip click
  - map click
  - attention panel update
  - prediction mode switch
  - system state rendering
  - notification seen / acknowledge / dismiss lifecycle
  - websocket reconnect behavior

### Runtime verification

In Docker or the real dev stack:

- verify overview BFF payload
- verify ward map route with prediction mode data
- verify empty-state and action-required-state renderings
- verify notifications arrive live over websocket
- verify unread count stays consistent after lifecycle transitions

### Output

Create:

- `docs/DASHBOARD_DECISION_LAYER_PHASE_12_VERIFICATION.md`

---

## Phase 13: Final Audit

### Objective

Audit the dashboard as if for the first time and ask whether it truly behaves like a deployable decision layer.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Audit questions

1. Does the dashboard clearly show current system state?
2. Can an operator identify where to look first in under a second?
3. Is trigger state visible and truthful?
4. Does the dashboard distinguish risk, alert, and action cleanly?
5. Is prediction actually visible and trustworthy?
6. Does the action panel recommend real next steps instead of passive prose?
7. Is facility readiness linked enough to support operational reasoning?
8. Are freshness cues specific enough to support trust?
9. Are KPI deltas meaningful and not decorative?
10. Does the page still feel like one coherent system instead of layered widgets?

### Required honesty checks

The final audit must explicitly call out if:

- any prediction mode is still simulated
- any trigger language is UI-authored without backend derivation
- any action recommendation is hardcoded without a rules basis
- any facility readiness signal is only a placeholder proxy

### Output

Create:

- `docs/DASHBOARD_DECISION_LAYER_PHASE_13_FINAL_AUDIT.md`

The final verdict must use one of:

- `complete`
- `complete with explicit limitations`
- `partial`
- `not yet credible as a decision layer`

---

## Recommended Build Order

To get the most value quickly, implement in this order:

1. Phase 1: Vocabulary and state model
2. Phase 2: System state layer
3. Phase 2A: First-class notifications and websocket lifecycle
4. Phase 3: Action panel upgrade
5. Phase 4: Prediction mode
6. Phase 5: Temporal trust and freshness
7. Phase 6: KPI temporal context
8. Phase 8: Facility readiness linkage
9. Phase 9: Alert and trigger linkage
10. Phase 9A: Alert lifecycle, timeline, and feedback loop
11. Phase 11: Demo scenario data and seeded decision states
12. Phase 12: Verification
13. Phase 13: Final audit

This order front-loads the dashboard’s most important product leap:

- visible trigger state
- action orientation
- predictive value

---

## Final Note

The dashboard should not become a denser reporting page.

Its purpose is to become the first screen where an operator can understand:

- whether the system is stable
- where risk is rising
- whether alerts are firing
- whether action is required
- and what to do next

That is the standard this plan is aiming for.

---

## Self-Critical Audit

Before calling this plan complete, audit it critically against the following questions:

1. Does the dashboard plan depend clearly on promoted backend truth rather than frontend invention?
2. Does it keep risk, alert, action, and readiness semantics distinct enough?
3. Does it avoid overclaiming prediction, trigger, or facility-readiness credibility before backend promotion?
4. Does it define enough interaction and notification lifecycle detail to feel operational rather than decorative?
5. Does it stay honest about seeded data, benchmark outputs, and proxy-based readiness signals?
6. Does it sequence dashboard sophistication after ETL, ML, and forecasting discipline?
7. Does every phase include explicit git commit and push closure discipline?

Any gap found in this audit must be closed in the plan before treating the plan as execution-ready.
