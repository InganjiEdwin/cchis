# Ward Detail UX Redesign Implementation Plan

Status date: 2026-05-06

This plan redesigns the ward detail route at `frontend/app/(dashboard)/wards/[id]/page.tsx`
from a dense evidence dump into a ward decision cockpit. The page should still
support audit, model trust, climate evidence, spatial evidence, alert review,
CHV follow-through, preparedness actions, and outcome feedback, but the first
screen must answer the operator's most urgent question:

```text
What is happening in this ward, can I trust the signal, and what should I do now?
```

The implementation direction is action-first, evidence-second, audit-third.
Every visible pixel should earn its place by helping the user decide, verify, or
act.

## Operating Decision

Keep the existing route and data contracts for the first redesign pass.

- Keep `/wards/[id]` as the canonical ward detail route.
- Keep the existing BFF response shape from `fetchWardDetailViaBff`.
- Keep `useWardDetailQuery` as the primary query orchestration layer.
- Keep the trigger alert workflow available from the ward page for authorized
  roles.
- Preserve access to every current evidence category, but move lower-priority
  evidence into tabs, accordions, or details.
- Do not add new backend requirements unless a frontend data gap blocks the
  cockpit design.
- Do not remove audit, trust, or evidence content to make the page feel clean.
  Instead, make it discoverable at the right layer.

## Product Goal

An authorized operator should be able to open a ward page and, within the first
screen, understand:

1. Ward identity and operating scope.
2. Current risk level and risk score.
3. Expected near-term case burden.
4. Whether a trigger or response workflow is active.
5. Whether the data is fresh enough to use.
6. The single recommended next action.
7. The top reasons behind the recommendation.
8. The fastest path to trigger review, alert history, or routine monitoring.

An analyst should then be able to drill into:

1. Model readiness.
2. Climate source coverage.
3. Spatial spillover and catchment pressure.
4. Prediction outcome history.
5. Alert-to-action feedback.
6. Preparedness action evidence.
7. Freshness and source diagnostics.

## Non-Goals

- Do not redesign the global dashboard shell.
- Do not redesign the wards list page except for preserving `returnTo`.
- Do not rebuild the trigger alert modal or workflow internals.
- Do not change backend policy decisions, risk thresholds, or model outputs.
- Do not hide stale-data warnings, climate caveats, or false/missed review
  items.
- Do not create a marketing-style page, large decorative hero, or ornamental
  gradient treatment.
- Do not use the ward page as the only place to complete alert, CHV, facility,
  or preparedness workflows. It remains an operating cockpit with links into
  dedicated work queues.

## Current Implementation Baseline

Current route:

```text
frontend/app/(dashboard)/wards/[id]/page.tsx
```

Current query:

```text
frontend/queries/use-ward-detail-query.ts
```

Current test:

```text
frontend/app/wards-detail-page.test.tsx
```

The page currently renders these major information groups:

- Topbar and freshness timestamp.
- Ward header with many status badges.
- Primary trigger or alert-history actions.
- Metric cards for risk score, expected cases, forecast horizon, model
  readiness, last alert, and latest record.
- Forecast horizon and evidence.
- Risk explanation.
- Risk history.
- Prediction outcomes.
- Outcome feedback loop.
- Ward context.
- Spatial context.
- Recommended action.
- Alert candidate review.
- Recent alerts.
- Preparedness actions.
- CHV action status.
- Data status.

The current page is operationally rich, but it creates overload because:

- The header has too many badges competing for attention.
- Evidence appears before the user has stabilized on the decision.
- Several sections answer similar questions with different vocabulary.
- Many repeated cards use the same visual weight.
- Deep audit details are visible by default.
- The right rail is useful but competes with the main content instead of
  anchoring the next action.
- Tables and dense evidence cards can dominate the viewport before the user
  sees the full situation.

## UX Principles

### 1. One Primary Decision

There must be one obvious primary action at any time:

- `Review trigger`
- `Open trigger flow`
- `View alert history`
- `Continue monitoring`

Secondary actions can exist, but they should not look equal to the primary
action.

### 2. Summary Before Evidence

Show the conclusion first, then evidence on demand.

Example:

```text
Action required. Review active trigger and confirm field follow-up.
Why: rainfall is elevated, one high-risk neighbor is active, and CHV response is still in progress.
```

The detailed climate source, model policy, and outcome feedback can sit behind
evidence controls.

### 3. Trust Is Always Visible

Data freshness and trust caveats must be visible in the cockpit, but they should
not become a wall of badges.

Use one compact trust cluster:

- Fresh or stale.
- Model readiness.
- Climate coverage state.

If any item is warning or danger, show the strongest caveat in one line.

### 4. Calm Density

The page should feel operational, not sparse. Use compact grouping, restrained
color, and clear hierarchy. Avoid decorative density where every card looks
important.

### 5. Progressive Disclosure

Every advanced evidence area should have a summary state and a detail state.

Default visible:

- Human label.
- State or count.
- One-sentence implication.

Hidden until expanded:

- Source refs.
- Issue times.
- Missing lead days.
- Policy version.
- Evidence arrays.
- Long caveats.
- Multi-row outcome and response tables.

### 6. No Hidden Risk

Progressive disclosure must not bury urgent warnings. If a hidden area contains
danger or warning evidence, the collapsed header must show that state.

### 7. Mobile Priority Is Identical

Mobile must keep the same order of importance:

1. Ward identity.
2. Risk and decision.
3. Primary action.
4. Trust state.
5. Situation.
6. Response.
7. Evidence.
8. History.

Do not make mobile users scroll through audit content before action content.

## Information Hierarchy

### Tier 0: Global Context

Rendered by `DashboardTopbar`.

Keep:

- Page title.
- Scope subtitle.
- Refresh action.
- Last updated label.

Change:

- Title from `Ward Detail` to `Ward Decision`.
- Subtitle should read as operational context, for example
  `Migori County ward operating view`.

### Tier 1: Cockpit Header

This is the first meaningful content after the topbar.

Visible content:

- Back link.
- Ward name.
- Sub-county, county, ward code.
- Risk level.
- Risk score.
- Expected cases.
- Trigger state.
- Data freshness.
- Decision headline.
- Decision why.
- Primary CTA.
- Secondary alert-history link where relevant.

Strict limits:

- Maximum 4 status chips in the header.
- Maximum 4 metric cells in the metric strip.
- Maximum 2 lines for `why`.
- Maximum 3 next-step bullets in the visible decision panel.
- One primary filled button.

### Tier 2: Situation

Default tab. Answers:

```text
Why is this ward in this state, and what local context changes the risk?
```

Visible content:

- Top 3 risk drivers.
- Risk trend.
- Spatial summary.
- Compact map.
- High-risk neighbors.
- Facility/catchment pressure.

### Tier 3: Response

Answers:

```text
Has the system and field team followed through?
```

Visible content:

- Alert state.
- CHV action status.
- Preparedness action summary.
- Response gaps.
- Links to dedicated queues.

### Tier 4: Evidence

Answers:

```text
Can I trust this signal and how was it generated?
```

Visible content:

- Climate coverage summary.
- Model readiness summary.
- Source confidence summary.
- Alert candidate review.
- Prediction outcome summary.
- Outcome feedback summary.

Detailed content:

- Climate source truth.
- Model evidence refs.
- Missing lead days.
- Policy version and blockers.
- Prediction label rows.
- Outcome feedback steps.
- Attribution review.

### Tier 5: History And Audit

Answers:

```text
What happened over time?
```

Visible content:

- Risk history.
- Recent alerts.
- Preparedness action lifecycle.
- Data freshness details.
- Ward metadata.

## Proposed Page Architecture

Use a two-level architecture:

```text
WardDecisionPage
  DashboardTopbar
  WardCockpitHeader
  WardDetailWorkspace
    WardDetailTabs
      SituationTab
      ResponseTab
      EvidenceTab
      HistoryTab
    WardActionRail
```

On desktop, `WardActionRail` is sticky. On mobile, it becomes a compact action
section directly below the cockpit header.

### Component Ownership

Create components near the route first to reduce churn:

```text
frontend/app/(dashboard)/wards/[id]/
  page.tsx
  ward-detail-sections.tsx
```

If components become reusable, move them later. The first implementation should
optimize for clarity and testability, not premature shared abstractions.

Candidate local components:

| Component | Responsibility |
| --- | --- |
| `WardCockpitHeader` | Ward identity, risk, decision headline, metrics, primary action |
| `WardStatusCluster` | Ordered status chips with overflow discipline |
| `WardPrimaryAction` | Primary CTA and secondary action logic |
| `WardTrustSummary` | Freshness, model readiness, climate coverage, source confidence |
| `WardDetailTabs` | Situation, Response, Evidence, History navigation |
| `SituationTab` | Drivers, trend, spatial summary, map |
| `ResponseTab` | Alerts, CHV, preparedness, response gaps |
| `EvidenceTab` | Model, climate, policy, outcomes, feedback |
| `HistoryTab` | Risk history, alert history, action lifecycle, freshness details |
| `WardActionRail` | Sticky recommended action, next steps, trust warning, work queue links |
| `EvidenceDisclosure` | Shared summary plus expandable detail pattern |

## Visual System

### Layout Grid

Use an 8 px spacing system.

Page:

- Outer vertical spacing: `24px` desktop, `16px` mobile.
- Main workspace gap: `24px` desktop, `16px` mobile.
- Max content width: use the dashboard shell width already available.
- Do not introduce a separate centered marketing container.

Desktop layout at `xl` and wider:

```text
main column: minmax(0, 1fr)
right rail: 360px to 400px
gap: 24px
```

Tablet layout:

```text
single column
tabs full width
action rail becomes inline action summary
```

Mobile layout:

```text
single column
header metrics become 2 column grid
tabs become horizontal scroll or segmented control
tables become cards or horizontally scroll only when unavoidable
```

### Radius

Target radius:

- Section containers: `8px`.
- Repeated item cards: `8px`.
- Buttons: existing pill style is acceptable where already standard, but do not
  add new oversized rounded containers.
- Status chips: pill shape is acceptable because they are status labels.

Avoid:

- Nested rounded cards inside rounded cards.
- Large 24 px to 28 px radius blocks.
- Decorative preview containers around the map unless the map needs a functional
  frame.

### Borders And Surfaces

Use subtle borders to define hierarchy:

- Primary section border: `var(--dashboard-table-line)`.
- Muted surface: `color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)`.
- Do not use ornamental radial gradients.
- Do not use multiple background effects in the same section.
- The map should sit in a functional map frame, not a decorative card-within-card.

### Typography

Use clear operational scale:

| Element | Mobile | Desktop | Weight |
| --- | --- | --- | --- |
| Ward name | 24 px | 32 px | 650 to 700 |
| Decision headline | 18 px | 22 px | 650 |
| Section title | 16 px | 18 px | 650 |
| Metric value | 20 px | 24 px | 650 |
| Body copy | 14 px | 14 px | 400 to 500 |
| Metadata label | 12 px | 12 px | 600 |

Rules:

- Letter spacing should be `0`.
- Avoid negative tracking.
- Avoid all-caps labels where sentence case is clearer.
- Keep line length for decision copy under roughly 72 characters on desktop.
- Buttons must not wrap awkwardly; allow label wrapping only on very narrow
  screens if needed.

### Color

Use color to encode state, not decoration.

Risk colors:

- High: danger token.
- Medium: warning token.
- Low or resolved: success token.
- Unknown: neutral token.

Rules:

- Do not let danger red dominate the whole page.
- Use risk color in badges, one accent border, and small signal markers.
- Trust warnings should be visible but quieter than active danger states.
- Avoid one-note palettes.
- Avoid decorative purple/blue gradients, beige-heavy panels, or dark slate
  domination.

### Icons

Use `lucide-react` icons that already exist in the page.

Rules:

- Icons support scanning but must not carry meaning alone.
- All decorative icons use `aria-hidden="true"`.
- Keep icon buttons at least 40 px on desktop and 44 px on touch surfaces.
- Use tooltips only for unfamiliar icon-only controls.

## Detailed Screen Design

### 1. Topbar

Keep `DashboardTopbar`.

Change copy:

- `title`: `Ward Decision`
- `subtitle`: `${county} County ward operating view`

Last updated:

- Keep existing refresh behavior.
- If stale, append `Stale`.
- Do not duplicate stale copy in the topbar and header unless the header trust
  cluster has a stronger warning.

### 2. Cockpit Header

Shape:

- One primary section.
- No nested cards.
- Two-column desktop layout.
- Left: ward identity and decision.
- Right: primary action and trust summary.

Desktop layout:

```text
row 1: back link
row 2: ward identity and status chips
row 3: decision headline and why
row 4: metric strip
```

Right side:

```text
primary action button
secondary action link/button
trust summary
next steps, max 3
```

Mobile layout:

```text
back link
ward identity
risk and trigger chips
decision headline
primary action
metric strip
trust summary
next steps
```

Status chip priority:

1. Risk level.
2. Trigger state.
3. Fresh or stale.
4. Strongest trust caveat, if warning or danger.

Do not show all source badges in the header.

Metric strip priority:

1. Risk score.
2. Expected cases.
3. Last alert.
4. Latest record.

Forecast horizon and model readiness move into the trust summary or Evidence
tab. They should not both appear as full metric cards and header badges.

### 3. Primary Action Logic

Inputs:

- `detail.primaryCtaKind`
- `detail.triggerState`
- `detail.actionRequired`
- `detail.workflow`
- `currentUser.role`
- `canTriggerAlerts(currentUser.role)`

Primary action mapping:

| State | Authorized operator CTA | Read-only CTA |
| --- | --- | --- |
| `REVIEW_TRIGGER` | `Review trigger` | `View alert history` |
| `OPEN_TRIGGER_FLOW` | `Open trigger flow` | `View alert history` |
| `VIEW_ALERT_HISTORY` | `View alert history` | `View alert history` |
| no active workflow and low signal | `Continue monitoring` as non-filled state plus optional `Open trigger flow` secondary | `View alert history` |

Button treatment:

- One filled primary button.
- Secondary action is outline or text link.
- Do not show two filled buttons.
- Do not show a trigger button to roles that cannot trigger.

### 4. Trust Summary

Visible in cockpit header and action rail.

Content:

- Freshness state.
- Model readiness label.
- Climate coverage status.
- Source confidence only if available.

Collapsed copy examples:

```text
Fresh data. Promoted model. Climate horizon caveated.
Stale data. Review with caution until the next ward update.
```

If any trust item is warning or danger:

- Show one warning line.
- Link or affordance to `Evidence`.
- Do not render multiple warning callouts in the first screen.

### 5. Tabs

Use four tabs:

```text
Situation
Response
Evidence
History
```

Default tab:

- `Situation`.

URL behavior:

- Optionally support `?tab=situation|response|evidence|history`.
- Preserve existing `returnTo`.
- If no tab param exists, do not add one until the user changes tabs.

Tab visual rules:

- Use segmented control style or compact tab list.
- Selected tab has clear border/background state.
- Labels must fit on mobile.
- Avoid explanatory tab subtitles inside the tab control.
- Tab panels keep semantic headings for screen readers.

### 6. Situation Tab

Purpose:

```text
Explain current ward risk and spatial context.
```

Sections:

1. Top signals.
2. Risk trend.
3. Spatial context.
4. Map.

Top signals:

- Show max 3 driver items by default.
- If more exist, show `View all evidence` link to Evidence tab.
- Use source-based icon.
- Use a small state marker, not large warning blocks.

Risk trend:

- Show current trend label.
- Show mini history of up to 6 records.
- Prefer compact visual timeline or slim table.
- If no history, use quiet empty state.

Spatial summary:

Visible metrics:

- High-risk neighbors.
- Neighboring outbreak labels.
- Facility pressure.
- Nearest facility.

Map:

- Show selected ward and relevant neighbors.
- Keep map at stable aspect ratio.
- Desktop height target: 320 to 380 px.
- Mobile height target: 260 to 320 px.
- Map must not jump as data loads.
- Map legend should be compact and not overlay critical geometry.

Spatial details behind disclosure:

- Relationship labels.
- Approximate-link notices.
- Distance values.
- Surveillance trend rows.
- Catchment method and source kind.
- Caveats.

### 7. Response Tab

Purpose:

```text
Show whether response work is happening and where gaps exist.
```

Sections:

1. Alert workflow status.
2. CHV follow-through.
3. Preparedness actions.
4. Response gaps.

Alert workflow status:

- Show active alert count, failed count, queued count, retry pending count.
- Show strongest delivery issue first.
- Link to alert history.

CHV follow-through:

- Show latest status, active requests, linked alerts.
- Show assignment counts.
- Do not list every request by default.
- Show top 3 requests, then link to CHV operations if needed.

Preparedness actions:

- Show active, overdue, blocked, completed.
- Show top 4 current actions.
- Use due time and owner.
- Lifecycle events should be collapsed unless the action is overdue, blocked, or
  escalated.

Response gaps:

- Surface `outcomeFeedback.review_items` and missing response steps here if
  present.
- If there are no gaps, show one quiet success state.

### 8. Evidence Tab

Purpose:

```text
Expose trust, model, climate, policy, and outcome evidence without overwhelming the default view.
```

Sections:

1. Evidence summary matrix.
2. Climate evidence.
3. Model readiness.
4. Alert candidate review.
5. Prediction outcomes.
6. Outcome feedback loop.

Evidence summary matrix:

- Four compact cells:
  - Data freshness.
  - Source confidence.
  - Climate coverage.
  - Model readiness.
- Each cell shows label, state, and one implication.

Climate evidence:

Collapsed header:

- Source label.
- Coverage status.
- Coverage days.
- Missing lead days count.

Expanded content:

- Provider.
- Issue time.
- Valid range.
- Coverage ratio.
- Missing lead days list.
- Fallback static rainfall warning.
- Climate caveats.

Model readiness:

Collapsed header:

- Label and state.
- One detail sentence.

Expanded content:

- Evidence chips.
- Readiness caveats.
- Model version.
- Model run status.

Alert candidate review:

Collapsed header:

- Review state.
- Automatic alert allowed or blocked.
- Active alert count.

Expanded content:

- Policy version.
- Alert decision.
- Reason codes.
- Automatic alert blockers.
- Recommended review action.

Prediction outcomes:

Collapsed header:

- Evaluated count.
- Hits.
- False alerts.
- Missed outbreaks.
- Pending labels.

Expanded content:

- Prediction label history.
- False/missed review items.
- Precision review note.

Outcome feedback loop:

Collapsed header:

- Model quality.
- Response quality.
- Observed outcome.
- Review item count.

Expanded content:

- Accountability note.
- Response steps.
- Preparedness action outcome history.
- Attribution review.
- False-alert context.

### 9. History Tab

Purpose:

```text
Keep audit and timeline information available without dominating daily operation.
```

Sections:

1. Risk history.
2. Recent alerts.
3. Preparedness lifecycle history.
4. Data status.
5. Ward metadata.

Risk history:

- Keep up to 6 recent runs by default.
- Allow horizontal scroll on narrow screens if table remains.
- Consider card list on mobile.

Recent alerts:

- Show top 4.
- Keep alert detail behind `details`.
- Fix misleading copy: do not say `Delivered` when alert status is queued,
  failed, or retry pending.

Preparedness lifecycle:

- Show latest action events only when the user expands an action.
- Keep event timestamps readable.

Data status:

- Freshness state.
- Recent runs count.
- Alert linkage count.
- Freshness window.
- Latest record.

Ward metadata:

- Sub-county.
- Ward code.
- Model status.
- Source.
- Model version.

## Data Mapping

### Cockpit Header

| UI field | Source |
| --- | --- |
| Ward name | `detail.wardName` |
| County | `detail.county` |
| Sub-county | `detail.subCounty` |
| Ward code | `detail.wardCode` |
| Risk level | `detail.riskLevel` |
| Risk score | `detail.riskScore` |
| Expected cases | `detail.predictedCases` |
| Trigger state | `detail.triggerState` |
| Freshness | `detail.freshness.is_stale` |
| Latest record | `detail.updatedAt` |
| Last alert | `detail.lastAlertAt` |
| Decision headline | `detail.decisionSummary.headline` |
| Decision why | `detail.decisionSummary.why` |
| Next steps | `detail.decisionSummary.next_steps` |
| Primary CTA | `detail.primaryCtaKind` |

### Trust Summary

| UI field | Source |
| --- | --- |
| Model readiness | `detail.operationalEvidence.model_readiness` |
| Climate coverage | `detail.operationalEvidence.climate_source` and `forecast_horizon` |
| Source confidence | `detail.operationalEvidence.source_badges` |
| Freshness detail | `detail.freshness` |

### Situation

| UI field | Source |
| --- | --- |
| Risk drivers | `detail.driverItems` |
| Guidance | `detail.guidanceItems` |
| Trend | `detail.trend` |
| Risk history | `detail.riskHistory` |
| Ward map | `detail.wardMapFeature` |
| Spatial map features | `detail.spatialMapFeatures` |
| Spatial summary | `detail.spatialEvidence.summary` |
| Neighbors | `detail.spatialEvidence.neighbors` |
| Catchments | `detail.spatialEvidence.facility_catchments` |
| Nearest facility | `detail.spatialEvidence.nearest_facility` |
| Water proximity | `detail.spatialEvidence.water_proximity` |

### Response

| UI field | Source |
| --- | --- |
| Workflow | `detail.workflow` |
| Related alerts | `detail.relatedAlerts` |
| CHV action status | `detail.operationalEvidence.chv_action_status` |
| Preparedness actions | `detail.preparednessActions` |
| Response gaps | `detail.operationalEvidence.outcome_feedback.review_items` |
| Response steps | `detail.operationalEvidence.outcome_feedback.steps` |

### Evidence

| UI field | Source |
| --- | --- |
| Forecast horizon | `detail.operationalEvidence.forecast_horizon` |
| Climate source | `detail.operationalEvidence.climate_source` |
| Model readiness | `detail.operationalEvidence.model_readiness` |
| Source badges | `detail.operationalEvidence.source_badges` |
| Alert candidate review | `detail.operationalEvidence.alert_candidate_review` |
| Outcome evaluation | `detail.operationalEvidence.outcome_evaluation` |
| Prediction label history | `detail.operationalEvidence.prediction_label_history` |
| False/missed review | `detail.operationalEvidence.false_missed_review` |
| Outcome feedback | `detail.operationalEvidence.outcome_feedback` |

### History

| UI field | Source |
| --- | --- |
| Risk history | `detail.riskHistory` |
| Recent alerts | `detail.relatedAlerts` |
| Preparedness event history | `detail.preparednessActions[].events` |
| Freshness detail | `detail.freshness` |
| Ward metadata | `detail.wardCode`, `detail.source`, `detail.modelVersion`, `detail.modelRunStatus` |

## State Design

### High Risk And Review Pending

First screen:

- Risk badge: high.
- Trigger badge: awaiting review.
- Headline: action required.
- Primary CTA: `Review trigger`.
- Trust summary visible.
- Situation tab shows top signals.

Do not:

- Make the user scroll to discover the trigger.
- Render many equal warning cards.

### High Risk But No Active Trigger

First screen:

- Risk badge: high.
- Trigger badge: no active trigger.
- Primary CTA for authorized roles: `Open trigger flow`.
- Show warning that the ward is high risk but no active trigger exists.

### Low Risk Routine Monitoring

First screen:

- Risk badge: low.
- Trigger badge: no active trigger.
- Primary action state: `Continue monitoring`.
- Secondary action: `View alert history`.
- Situation tab can show compact empty state.

Do not:

- Show a large trigger flow button as if escalation is required.

### Resolved Workflow

First screen:

- Trigger badge: resolved.
- Primary CTA: `View alert history`.
- Decision headline: no active trigger action required.
- Response tab still shows recent response history.

### Stale Data

First screen:

- Freshness chip: stale.
- Trust summary warning.
- Primary action remains visible, but copy says review with caution.
- Evidence tab climate/model/source details remain accessible.

Do not:

- Hide the primary action.
- Repeat stale warning in multiple boxes above the fold.

### Missing Operational Evidence

First screen:

- Keep ward risk and decision visible.
- Trust summary says evidence unavailable.
- Evidence tab shows quiet empty state for missing blocks.

### Non-Trigger Role

First screen:

- Show recommendation.
- Hide trigger action controls.
- Primary CTA becomes `View alert history`.
- Include a concise role limitation note only where needed.

### Loading

Use stable skeletons:

- Header skeleton height should match final header height closely.
- Metric skeleton cells keep fixed dimensions.
- Tabs can render disabled skeleton panel.

### Error

Keep current error banner behavior, but:

- Place it below topbar and above cockpit.
- Use one concise message.
- Preserve back link if possible.

## Interaction Details

### Back Link

Keep `returnTo` behavior:

- Only allow `/wards` paths.
- Preserve query state from the wards list.
- Label: `Back to wards`.

### Tabs

Keyboard:

- Left and right arrow should move tab focus if custom tabs are implemented.
- `Enter` or `Space` activates focused tab.

Semantics:

- Use `role="tablist"`, `role="tab"`, and `role="tabpanel"` if custom.
- Or use native buttons with appropriate `aria-selected` and labelled panels.

### Disclosures

Use native `details` where sufficient.

Rules:

- Summary must contain the key state and count.
- Expanded content should not cause layout shift above the current scroll
  position.
- Warning or danger evidence must be visible in collapsed summary.

### Links Into Other Workflows

Keep:

- `/alerts`
- `/preparedness-actions?ward_id={wardId}`

Consider later:

- Link to CHV operations filtered by ward.
- Link to facility readiness filtered by nearest/catchment facility.

Do not invent links that do not exist.

## Accessibility Requirements

- Use one `h1` for the ward name.
- Use section headings in a logical order.
- Ensure all button names are descriptive.
- Do not rely on color alone for risk or trust state.
- Keep contrast at least WCAG AA.
- Focus states must be visible on tabs, buttons, links, and disclosures.
- Touch targets should be at least 44 px tall on mobile.
- Map must have an accessible summary nearby.
- Tables must keep headers associated with cells.
- Loading states should not trap screen readers in repeated placeholder content.
- Dynamic refresh should not unexpectedly steal focus.

## Responsive Requirements

### Mobile

Width target: 360 px to 430 px.

Order:

1. Topbar.
2. Back link.
3. Ward identity.
4. Risk and trigger state.
5. Decision headline.
6. Primary action.
7. Metrics.
8. Trust summary.
9. Tabs.
10. Active tab panel.

Rules:

- No horizontal overflow except intentional table wrappers.
- No clipped status chip text.
- Map remains usable.
- Primary button fits full width.
- Right rail is not sticky.

### Tablet

Width target: 768 px to 1199 px.

Rules:

- Single-column content.
- Metric strip can use 4 columns if space allows, otherwise 2 columns.
- Action summary sits below header.
- Tabs remain visible without wrapping into two lines if possible.

### Desktop

Width target: 1200 px and wider.

Rules:

- Main content plus sticky rail.
- Sticky rail top offset aligns with dashboard top spacing.
- Rail width stays between 360 px and 400 px.
- Map and situation content should be visible without excessive vertical gaps.

## Copy Guidelines

Use short operational copy.

Prefer:

```text
Action required. Review active trigger and confirm field follow-up.
Fresh data. Promoted model. Climate horizon caveated.
1 response gap needs review.
```

Avoid:

```text
This page keeps the next truthful step visible without implying all execution completes here.
Current lead-time window, source quality, and model readiness for this ward.
```

The UI should not explain itself. It should label the current state and expose
the next action.

## Implementation Phases

### Phase 0: Inventory And Safety Checks

Tasks:

1. Re-read `page.tsx`, `use-ward-detail-query.ts`, and current page tests.
2. List all current user-visible evidence strings covered by tests.
3. Confirm every evidence category has a home in the new tab structure.
4. Identify any misleading existing copy to fix during migration.

Acceptance:

- No current evidence category is unassigned.
- No route or data contract change is required for Phase 1.

Phase 0 implementation status:

- Completed on 2026-05-06.
- Reviewed `frontend/app/(dashboard)/wards/[id]/page.tsx`.
- Reviewed `frontend/queries/use-ward-detail-query.ts`.
- Reviewed `frontend/app/wards-detail-page.test.tsx`.
- No current evidence category is unassigned.
- No Phase 1 route change is required.
- No Phase 1 backend or BFF contract change is required.
- Phase 1 can proceed as a frontend refactor using the existing
  `WardDetailState` contract.

### Phase 0 Source File Findings

Current route file:

```text
frontend/app/(dashboard)/wards/[id]/page.tsx
```

Key findings:

- The current page is a single client component with formatter helpers,
  decision helpers, section rendering, trigger-panel orchestration, spatial
  rendering, and evidence rendering in one file.
- The first visible content already contains the right decision inputs, but too
  many badges and metrics compete at the same visual level.
- The page currently uses repeated `Card` blocks with large radii and similar
  visual weight across operational, evidence, audit, and empty-state content.
- The page already has the data needed for the proposed cockpit header, tabs,
  and action rail.
- The current `returnTo` protection is correct and should be preserved.
- The current freshness state correctly uses `detail.freshness.is_stale` from
  the backend-facing query state instead of re-deriving staleness from the
  timestamp.

Current query file:

```text
frontend/queries/use-ward-detail-query.ts
```

Key findings:

- `useWardDetailQuery` already fetches ward detail, ward map features, and ward
  preparedness actions in parallel.
- `WardDetailState` already contains the fields needed for all proposed
  cockpit, situation, response, evidence, and history sections.
- `headerContext` and `decisionSummary` already provide safe fallbacks, so the
  redesign can keep a stable first screen even when optional evidence is
  missing.
- `spatialMapFeatures` is already narrowed to the selected ward and spatial
  neighbors, which is sufficient for the first map redesign pass.
- No new query, BFF route, backend serializer field, or model change is needed
  for Phase 1.

Current test file:

```text
frontend/app/wards-detail-page.test.tsx
```

Key findings:

- The tests cover the high-risk review-pending state, non-trigger role state,
  failed-alert workflow state, low-signal routine state, backend freshness
  behavior, resolved workflow state, empty recent-alert guidance, and genuine
  trigger-initiation state.
- Existing assertions are mostly semantic enough to migrate, but Phase 6 should
  update them to account for tabs and disclosures.
- Tests currently assert old section names such as `Forecast horizon and
  evidence`; after the redesign they should assert evidence availability inside
  the `Evidence` tab rather than requiring that section to be visible by
  default.

### Phase 0 Tested Evidence Inventory

The table below lists current user-visible strings or regex patterns covered by
`frontend/app/wards-detail-page.test.tsx` and assigns their new home.

| Tested visible string or pattern | Current meaning | Redesign home |
| --- | --- | --- |
| `North Kamagambo` | Ward identity heading | Cockpit header |
| `Back to wards` | Preserved wards-list navigation | Cockpit header |
| `/wards?risk=HIGH&page=2` | Safe `returnTo` preservation | Cockpit header |
| `Trigger alert mock \| Review trigger \| 12 \| North Kamagambo` | Authorized trigger review CTA | Cockpit header primary action |
| `Trigger alert mock \| Open trigger flow \| 12 \| North Kamagambo` | Authorized secondary trigger initiation | Cockpit header or action rail, depending primary CTA |
| `Trigger alert mock \| Open Trigger Flow \| 12 \| North Kamagambo` | Authorized primary trigger initiation | Cockpit header primary action |
| `View full alert history` | Alert-history action | Cockpit secondary action, Response tab, History tab |
| `Recommended action` | Current right-rail decision card | Action rail |
| `Action required. Review active alerts and trigger status.` | Decision headline | Cockpit header |
| `No decision required at this time.` | Routine decision headline | Cockpit header |
| `No active trigger action is required right now.` | Resolved/no-action decision headline | Cockpit header |
| `This ward is under routine monitoring.` | Routine decision why | Cockpit header and low-signal Situation state |
| `Context: Routine monitoring (no active escalation)` | Routine context label | Cockpit header, shortened or moved to trust/action metadata |
| `Review alert history` | Routine primary recommendation | Action rail |
| `Continue routine surveillance` | Routine next step | Action rail |
| `Awaiting review` | Active trigger state | Cockpit status chip and action rail |
| `No active trigger` | No-trigger state | Cockpit status chip |
| `Resolved` | Resolved workflow state | Cockpit status chip |
| `Stale data` | Backend stale freshness state | Cockpit trust cluster |
| `Fresh data` | Backend fresh freshness state | Cockpit trust cluster |
| `ward detail \| migori county ward decision console \| .* \| default` | Current topbar copy/freshness behavior | Topbar, with copy updated to `Ward Decision` |
| `Risk history` | Recent risk-score run history | History tab |
| `Risk signals & trend` | Low-signal risk checkpoint | Situation tab |
| `No active signals or trends detected.` | Low-signal empty state | Situation tab |
| `Latest record:` | Low-signal record metadata | Situation tab or History tab |
| `Forecast horizon and evidence` | Current climate/model/source evidence section | Evidence tab |
| `7 to 14 days` | Forecast horizon display value | Cockpit trust summary and Evidence tab |
| `Promoted` | Model readiness label | Cockpit trust summary and Evidence tab |
| `14-day climate horizon caveated` | Climate horizon caveat badge | Cockpit trust warning and Evidence tab |
| `Climate source truth` | Climate source detail heading | Evidence tab climate disclosure |
| `Forecast rainfall` | Climate source label | Evidence tab climate disclosure |
| `open-meteo-forecast` | Climate provider | Evidence tab climate disclosure detail |
| `3/14 days` | Forecast coverage ratio | Evidence tab climate disclosure summary/detail |
| `Missing forecast lead days: 4, 5, 6, 7, 8, 9, 10, 11 +3 more` | Climate coverage gap | Cockpit trust warning summary and Evidence tab detail |
| `Forecast rainfall is elevated at 92 mm from open-meteo-forecast` | Risk driver | Situation tab top signals |
| `High confidence` | Source confidence badge | Cockpit trust summary and Evidence tab summary matrix |
| `Prediction outcomes` | Prediction-vs-label evaluation section | Evidence tab |
| `False alerts` | Outcome evaluation metric | Evidence tab prediction outcomes |
| `False alert` | False-alert classification/review item | Evidence tab prediction outcomes |
| `Outcome feedback loop` | Alert-to-action outcome section | Evidence tab and Response tab summary |
| `Response Quality Review` | Outcome feedback attribution | Response tab gap summary and Evidence tab detail |
| `Model quality` | Outcome feedback model quality metric | Evidence tab outcome feedback disclosure |
| `Response quality` | Outcome feedback response quality metric | Response tab gap summary and Evidence tab detail |
| `Active outbreak with downstream response gap` | Attribution review item | Response tab response gaps |
| `Preparedness action outcome history` | Preparedness evidence linked to outcome | Evidence tab outcome feedback detail |
| `False-alert context` | False-alert review context | Evidence tab prediction/outcome detail |
| `Alert candidate review` | Decision-policy review evidence | Evidence tab |
| `Spatial context` | Spatial evidence section | Situation tab |
| `Neighboring high-risk wards` | Spatial high-risk neighbor metric | Situation tab |
| `North Kadem` | Neighbor ward evidence | Situation tab spatial disclosure |
| `Approximate` | Approximate catchment state | Situation tab spatial summary/disclosure |
| `Approximate link` | Approximate neighbor relationship | Situation tab spatial disclosure |
| `Kamagambo Health Centre` | Nearest/catchment facility evidence | Situation tab |
| `facility catchments are approximate` | Spatial caveat | Situation tab collapsed caveat with warning summary |
| `Recent alerts` | Ward-linked alert activity | Response tab summary and History tab detail |
| `No recent alerts for this ward` | Alert empty state | Response tab and History tab |
| `Review full alert history if you need older ward-linked alert activity.` | Empty alert guidance | History tab empty state |
| `CHV action status` | CHV follow-through section | Response tab |
| `linked alerts: alert-7` | CHV request linkage evidence | Response tab CHV detail |
| `Preparedness actions` | Ward-linked action ledger | Response tab |
| `Latest lifecycle events` | Preparedness event timeline | History tab or collapsed Response action detail |
| `Started field verification with CHV team.` | Preparedness event detail | History tab or expanded action detail |
| `Field verification` | Preparedness action type | Response tab and Evidence tab outcome detail |
| `Data status` | Freshness diagnostics | History tab and cockpit trust detail |
| `recommended action is visible, but this role cannot start or review trigger work from this page` | Non-trigger role limitation | Cockpit action area, shortened |
| `current next step: review alert history. open trigger flow only if conditions change.` | Non-primary trigger guidance | Action rail, shortened |
| `no recent alerts for this ward` | Failed/empty alert section guard | Response tab and History tab |
| `open trigger flow if a guided response is still needed` | Trigger empty-alert guidance | Cockpit secondary action or Response empty state |

### Phase 0 Evidence Category Assignment

| Current evidence category | Existing source | Assigned redesign home | Phase 0 status |
| --- | --- | --- | --- |
| Ward identity and return link | `detail.wardName`, `detail.county`, `detail.subCounty`, `detail.wardCode`, `returnTo` | Cockpit header | Assigned |
| Risk score, level, expected cases | `detail.riskLevel`, `detail.riskScore`, `detail.predictedCases` | Cockpit header metric strip | Assigned |
| Trigger/workflow state | `detail.triggerState`, `detail.workflow`, `detail.primaryCtaKind` | Cockpit header and action rail | Assigned |
| Role-gated trigger controls | `currentUser.role`, `canTriggerAlerts` | Cockpit primary action | Assigned |
| Decision summary and next steps | `detail.decisionSummary`, workflow recommendation fallback | Cockpit header and action rail | Assigned |
| Freshness and stale/fresh state | `detail.freshness`, `detail.updatedAt` | Cockpit trust summary and History tab | Assigned |
| Forecast horizon | `operationalEvidence.forecast_horizon` | Evidence tab, with summary in trust cluster | Assigned |
| Climate source and coverage caveats | `operationalEvidence.climate_source` | Evidence tab climate disclosure and trust warning | Assigned |
| Model readiness | `operationalEvidence.model_readiness` | Evidence tab and trust cluster | Assigned |
| Source badges/confidence | `operationalEvidence.source_badges` | Evidence tab summary matrix and trust cluster | Assigned |
| Risk drivers | `detail.driverItems` | Situation tab top signals | Assigned |
| Guidance items | `detail.guidanceItems` | Action rail supporting checks or Situation tab | Assigned |
| Risk trend and recent risk history | `detail.trend`, `detail.riskHistory` | Situation tab trend summary and History tab detail | Assigned |
| Spatial evidence and map | `detail.spatialEvidence`, `detail.spatialMapFeatures` | Situation tab | Assigned |
| Neighbor spillover signals | `spatialEvidence.neighbors` | Situation tab spatial disclosure | Assigned |
| Facility catchment pressure | `spatialEvidence.facility_catchments` | Situation tab | Assigned |
| Nearest facility and water proximity | `spatialEvidence.nearest_facility`, `spatialEvidence.water_proximity` | Situation tab | Assigned |
| Spatial caveats | `spatialEvidence.caveats` | Situation tab collapsed caveats with warning state | Assigned |
| Alert candidate review | `operationalEvidence.alert_candidate_review` | Evidence tab | Assigned |
| Related alerts | `detail.relatedAlerts` | Response tab summary and History tab detail | Assigned |
| CHV action status | `operationalEvidence.chv_action_status` | Response tab | Assigned |
| Preparedness action queue | `detail.preparednessActions` | Response tab | Assigned |
| Preparedness lifecycle events | `detail.preparednessActions[].events` | History tab or expanded Response action detail | Assigned |
| Prediction outcome evaluation | `operationalEvidence.outcome_evaluation` | Evidence tab | Assigned |
| Prediction label history | `operationalEvidence.prediction_label_history` | Evidence tab disclosure | Assigned |
| False/missed review workflow | `operationalEvidence.false_missed_review` | Evidence tab and Response gap summary | Assigned |
| Outcome feedback loop | `operationalEvidence.outcome_feedback` | Evidence tab detail and Response gap summary | Assigned |
| Outcome-linked preparedness evidence | `outcome_feedback.preparedness_action_evidence` | Evidence tab detail | Assigned |
| Ward metadata | `detail.wardCode`, `detail.source`, `detail.modelVersion`, `detail.modelRunStatus` | History tab | Assigned |
| Loading, error, and empty states | query status plus optional evidence null checks | Same owning tab/section as final content | Assigned |

Phase 0 assignment result:

- No current evidence category is unassigned.
- Every evidence category has a first-pass destination in Cockpit, Situation,
  Response, Evidence, or History.

### Phase 0 Misleading Or Overloaded Copy To Fix Later

These copy items should be fixed during Phase 2 through Phase 6. Phase 0 records
them so the redesign does not accidentally preserve confusing language.

| Current copy or pattern | Issue | Fix phase |
| --- | --- | --- |
| `Delivered ({toTitleCase(alert.channel)})` in recent alerts | Misleading when the alert status is `QUEUED`, `FAILED`, or `RETRY_PENDING` | Phase 3 or Phase 6 |
| `Trigger review and alert handling may continue in dedicated flows. This page keeps the next truthful step visible without implying all execution completes here.` | Too explanatory and UI-self-referential for the cockpit | Phase 2 |
| `Current lead-time window, source quality, and model readiness for this ward.` | Describes the section instead of the operator implication | Phase 4 |
| `Recommended action is visible, but this role cannot start or review trigger work from this page.` | Accurate but too long for first-screen action copy | Phase 2 |
| `Current next step: review alert history. Open trigger flow only if conditions change.` | Useful state, but should be a shorter action-rail note | Phase 2 |
| `Context: Routine monitoring (no active escalation)` | Over-formal and visually noisy for the cockpit | Phase 2 |
| `No decision summary is available for this ward.` | Can sound like a system failure when routine monitoring is enough | Phase 3 |
| Repeated `will appear when...` empty-state language | Creates noise across lower-priority sections | Phase 4 |
| Header badges for risk, trigger, freshness, model readiness, climate horizon, source confidence, and action count | Too many same-weight chips above the fold | Phase 2 |
| Six metric cards in the first section | Forecast horizon and model readiness duplicate trust/evidence content | Phase 2 |

### Phase 0 Safety Gate For Phase 1

Phase 1 can begin without backend work because the existing `WardDetailState`
already exposes:

- `wardName`, `county`, `subCounty`, and `wardCode` for identity.
- `riskLevel`, `riskScore`, and `predictedCases` for the cockpit metrics.
- `triggerState`, `workflow`, `decisionSummary`, and `primaryCtaKind` for
  decision and CTA state.
- `freshness`, `updatedAt`, and `lastAlertAt` for trust and freshness state.
- `driverItems`, `guidanceItems`, `trend`, and `riskHistory` for Situation and
  History.
- `spatialEvidence`, `spatialMapFeatures`, and `wardMapFeature` for Situation.
- `relatedAlerts`, `preparednessActions`, and
  `operationalEvidence.chv_action_status` for Response.
- `operationalEvidence.forecast_horizon`, `climate_source`,
  `model_readiness`, `source_badges`, `alert_candidate_review`,
  `outcome_evaluation`, `prediction_label_history`, `false_missed_review`, and
  `outcome_feedback` for Evidence.

Safety gate result:

- Phase 1 should be frontend-only.
- Phase 1 should preserve the existing `useWardDetailQuery` query key and
  fetches.
- Phase 1 should not alter `returnTo`, role gating, trigger modal behavior, or
  backend freshness semantics.

### Phase 1: Extract Formatters And Local Section Components

Tasks:

1. Keep existing formatter helpers or move them into the local section file.
2. Add local components for cockpit header, trust summary, tabs, and rail.
3. Keep prop types explicit and close to `WardDetailState`.
4. Avoid changing behavior while extracting.

Acceptance:

- Page still renders with existing tests before major layout changes.
- No unrelated formatting churn.

Phase 1 implementation status:

- Completed on 2026-05-06.
- Added local section component file:

  ```text
  frontend/app/(dashboard)/wards/[id]/ward-detail-sections.tsx
  ```

- Added first-pass local components:
  - `WardCockpitHeader`
  - `WardActionRail`
  - `WardTrustSummary`
  - `WardDetailTabs`
  - `WardMetricStrip`
  - `LoadingBlocks`
- Wired only behavior-neutral components into the current page:
  - Replaced the first header `Card` wrapper with `WardCockpitHeader`.
  - Replaced the inline metric-card grid with `WardMetricStrip`.
  - Replaced the right-side `aside` wrapper with `WardActionRail`.
  - Moved the existing loading skeleton rendering into `LoadingBlocks`.
- Left the current visual order, copy, CTA rules, evidence order, and section
  behavior unchanged.
- Preserved `returnTo`, role gating, trigger modal behavior, and backend
  freshness semantics.

Phase 1 verification:

```bash
cd frontend
npm test -- wards-detail-page.test.tsx
```

Result:

```text
Test Files  1 passed (1)
Tests       12 passed (12)
```

### Phase 2: Build Cockpit Header

Tasks:

1. Replace current large card header with `WardCockpitHeader`.
2. Limit visible chips to risk, trigger, freshness, and strongest trust caveat.
3. Replace six metric cards with four priority metrics.
4. Move primary CTA into the cockpit action area.
5. Move verbose next-step content into action rail.

Acceptance:

- Above-the-fold content shows ward, risk, decision, trust, and primary action.
- Only one filled primary CTA is visible.
- Header does not overflow at mobile widths.

Phase 2 implementation status:

- Completed on 2026-05-06.
- Updated the topbar copy from `Ward Detail` to `Ward Decision`.
- Updated the topbar subtitle from ward decision-console language to ward
  operating-view language.
- Reworked the cockpit header to show only the priority status chips:
  - risk level
  - trigger state
  - freshness
  - strongest warning or danger trust caveat
- Removed lower-priority success chips from the header, including model
  readiness, source confidence, and active action count.
- Added a compact cockpit trust cluster for model, climate, and source
  confidence context without treating each item as a same-weight header chip.
- Replaced the six-card metric strip with the four priority metrics:
  - risk score
  - expected cases
  - last alert
  - latest record
- Kept forecast horizon and model readiness visible in the existing evidence
  section until Phase 3 and Phase 4 move them behind tabs/disclosures.
- Kept exactly one filled primary action in the cockpit action area.
- Shortened first-screen non-primary action guidance.
- Moved longer operating guidance into the `Recommended action` rail as an
  `Operating note`.
- Reduced the ward title scale and removed negative letter spacing from the
  cockpit heading.
- Preserved `returnTo`, role gating, trigger modal behavior, and backend
  freshness semantics.

Phase 2 verification:

```bash
cd frontend
npm test -- wards-detail-page.test.tsx
```

Result:

```text
Test Files  1 passed (1)
Tests       12 passed (12)
```

### Phase 3: Add Tabs And Migrate Main Content

Tasks:

1. Add `Situation`, `Response`, `Evidence`, and `History` tabs.
2. Set `Situation` as default.
3. Move risk explanation, trend, and spatial context into `Situation`.
4. Move alerts, CHV action, preparedness actions, and response gaps into
   `Response`.
5. Move climate/model/policy/outcome evidence into `Evidence`.
6. Move risk history, recent alerts detail, data status, and ward metadata into
   `History`.

Acceptance:

- Default page is shorter and action-first.
- All current sections remain reachable.
- Tab labels fit mobile and desktop.

Phase 3 implementation status:

- Completed on 2026-05-06.
- Added stateful ward-detail tabs with `Situation` selected by default.
- Kept the cockpit header and `Recommended action` rail visible across tabs so
  the page remains action-first while deeper sections move out of the default
  viewport.
- Moved risk explanation, trend state, and spatial context into `Situation`.
- Moved recent alerts, preparedness action lifecycle, and CHV action status into
  `Response`; recent alert detail is also reachable from `History` because it is
  part of the ward record trail.
- Moved forecast horizon, climate source truth, model readiness, alert candidate
  policy review, prediction outcomes, and outcome feedback evidence into
  `Evidence`.
- Moved risk history, ward context, recent alert detail, and data status into
  `History`.
- Updated `frontend/app/wards-detail-page.test.tsx` to assert the default
  `Situation` view and tab switching for `Evidence`, `Response`, and `History`.

Phase 3 verification:

```bash
cd frontend
npx tsc --noEmit --pretty false
npm test -- wards-detail-page.test.tsx
```

Result:

```text
TypeScript completed with no errors.
Test Files  1 passed (1)
Tests       12 passed (12)
```

### Phase 4: Compress Evidence With Disclosures

Tasks:

1. Replace always-open climate source truth with an evidence disclosure.
2. Replace always-open model readiness evidence with an evidence disclosure.
3. Replace large outcome feedback step grid with collapsed summary plus detail.
4. Collapse preparedness action lifecycle events by default.
5. Collapse spatial caveats and neighbor details unless warning state requires
   summary visibility.

Acceptance:

- Warning and danger summaries remain visible while details are collapsed.
- Evidence tab can be scanned in less than one viewport on desktop for typical
  data.

Phase 4 implementation status:

- Completed on 2026-05-06.
- Added a reusable `WardDetailDisclosure` control with a visible summary,
  status badge, accessible expanded state, and click-to-open detail body.
- Collapsed climate source truth detail behind a disclosure while keeping the
  coverage badge and missing-lead-days warning summary visible.
- Collapsed model readiness evidence chips behind a disclosure while keeping the
  promoted/readiness status and readiness detail visible.
- Collapsed the outcome feedback step grid behind a `Response pathway detail`
  disclosure while keeping model quality, response quality, observed outcome,
  review count, accountability note, and attribution warnings visible.
- Collapsed response preparedness lifecycle event detail behind per-action
  disclosures while keeping action status, owner, due time, and event count
  visible.
- Collapsed spatial spillover rows, catchment records, and spatial caveat
  details behind disclosures while keeping high-risk neighbor, approximate
  catchment, and caveat summaries visible.
- Updated `frontend/app/wards-detail-page.test.tsx` to assert collapsed state and
  click-to-open access for spatial, climate, model, response pathway, and
  preparedness lifecycle details.

Phase 4 verification:

```bash
cd frontend
npx tsc --noEmit --pretty false
npm test -- wards-detail-page.test.tsx
```

Result:

```text
TypeScript completed with no errors.
Test Files  1 passed (1)
Tests       12 passed (12)
```

### Phase 5: Responsive And Pixel Polish

Tasks:

1. Audit spacing against the 8 px system.
2. Reduce oversized radii in touched sections.
3. Remove decorative gradients from the ward page.
4. Verify text wrapping in buttons, chips, metrics, and tab labels.
5. Verify sticky rail behavior on desktop.
6. Verify no nested card visual treatment remains in new sections.
7. Verify map dimensions are stable before and after data load.

Acceptance:

- No incoherent overlap.
- No unexpected horizontal page overflow.
- No clipped labels.
- No layout jump from hover, loading, or refresh states.

Phase 5 implementation status:

- Completed on 2026-05-06.
- Normalized touched ward-detail surfaces to `rounded-lg` so nested panels,
  disclosure frames, metric tiles, empty states, map containers, and alert/action
  rows no longer use oversized custom radii.
- Removed the decorative spatial-map gradient frame and replaced it with a quiet
  bordered surface.
- Stabilized the spatial map area with a fixed `h-64` map viewport so geometry,
  empty state, hover, and refresh paths do not resize the map container.
- Changed detail tabs from horizontal overflow to wrapping tabs with stable
  minimum height.
- Added wrap-safe button, chip, disclosure badge, and metric text treatment for
  long labels.
- Moved desktop sticky behavior onto the full action rail and removed the nested
  sticky data-status card.
- Audited touched classes for negative letter spacing, viewport-scaled font
  sizing, decorative gradients, oversized radii, no-wrap labels, and non-8px
  spacing leftovers.

Phase 5 verification:

```bash
cd frontend
npx tsc --noEmit --pretty false
npm test -- wards-detail-page.test.tsx
rg -n "rounded-\[1\.|rounded-2xl|tracking-\[-|radial-gradient|linear-gradient|whitespace-nowrap|text-\[clamp|min-h-\[|gap-3|space-y-3|p-3|px-3 py-3|px-4 py-3|min-h-11|px-5" app/'(dashboard)'/wards/'[id]'/page.tsx app/'(dashboard)'/wards/'[id]'/ward-detail-sections.tsx
```

Result:

```text
TypeScript completed with no errors.
Test Files  1 passed (1)
Tests       12 passed (12)
Static class scan returned no matches.
```

### Phase 6: Test Updates

Tasks:

1. Update `frontend/app/wards-detail-page.test.tsx`.
2. Preserve assertions that important evidence exists, but account for tab or
   disclosure placement.
3. Add tests for default `Situation` tab.
4. Add tests for switching to `Evidence`.
5. Add tests for switching to `Response`.
6. Add tests for low-signal routine state.
7. Add tests for non-trigger role behavior.
8. Add tests for stale data trust summary.
9. Fix existing alert copy assertion so queued alerts are not described as
   delivered.

Acceptance:

- Unit tests pass.
- Tests assert action-first behavior rather than raw section order.

Phase 6 implementation status:

- Completed on 2026-05-06.
- Updated `frontend/app/wards-detail-page.test.tsx` to assert the default
  `Situation` tab as the action-first view, including absence of hidden
  evidence/history/response sections on first render.
- Preserved important evidence assertions through tab and disclosure interaction
  checks for `Evidence`, `Response`, and `History`.
- Added explicit stale trust-summary assertions for model readiness, climate
  caveat, and source confidence chips.
- Kept low-signal routine-state and non-trigger role tests aligned with the new
  cockpit/action-rail layout.
- Fixed recent-alert copy so queued, failed, and retry-pending alerts are not
  described as delivered.
- Added a queued-alert regression assertion for `Queued for SMS • Risk 86/100`
  and negative assertions against delivered wording.

Phase 6 verification:

```bash
cd frontend
npx tsc --noEmit --pretty false
npm test -- wards-detail-page.test.tsx
```

Result:

```text
TypeScript completed with no errors.
Test Files  1 passed (1)
Tests       13 passed (13)
```

### Phase 7: Browser Verification

Tasks:

1. Start the frontend dev server.
2. Open the exact example route:

   ```text
   http://localhost:3000/wards/1?returnTo=%2Fwards%3Fscope%3DMigori%26sort%3Drisk_desc
   ```

3. Capture desktop screenshot.
4. Capture mobile screenshot.
5. Verify map renders.
6. Verify tabs are usable.
7. Verify primary action is visible without scrolling.
8. Verify no overlapping text.
9. Verify no blank or broken sections.

Acceptance:

- The page is operationally clear at first glance.
- Evidence remains available.
- Mobile and desktop both pass visual review.

Phase 7 implementation notes:

- Confirmed the frontend dev server was already running on `localhost:3000`.
- Verified the exact route with a Chrome DevTools browser pass using the local
  analyst demo session:

  ```text
  http://localhost:3000/wards/1?returnTo=%2Fwards%3Fscope%3DMigori%26sort%3Drisk_desc
  ```

- Captured screenshots:

  ```text
  frontend/test-artifacts/ward-detail-phase7/ward-detail-desktop.png
  frontend/test-artifacts/ward-detail-phase7/ward-detail-mobile.png
  ```

- Saved the verification report:

  ```text
  frontend/test-artifacts/ward-detail-phase7/ward-detail-phase7-report.json
  ```

- Browser verification covered:
  - Desktop and mobile screenshots.
  - Situation, Response, Evidence, and History tab switching.
  - Situation map render (`Migori ward map` SVG with ward paths).
  - Primary action visibility in the first viewport on desktop and mobile.
  - No document-level horizontal overflow.
  - No blank large sections.
  - No broken, authentication, or loading states after data hydration.

Phase 7 fixes from the browser pass:

- Compacted the dashboard sidebar into a short horizontal rail on narrow
  screens so mobile users reach ward identity and action content immediately
  instead of landing on a full-height navigation list.
- Tightened the mobile cockpit by hiding the longer decision explanation and
  context line under `640px`; the decision headline, action, trust state, and
  full lower-page evidence remain available.
- Reduced the cockpit mobile padding while preserving the larger desktop
  treatment.
- Allowed source-truth and prediction outcome badges to wrap, and made the
  prediction outcome table fixed-layout so long evidence labels cannot push the
  page horizontally.
- Follow-up screenshot review removed the stale two-column wrapper around the
  Situation lower section. Spatial context now spans the main content lane
  instead of leaving an empty sibling column.
- Follow-up Response tab review moved response execution content into the main
  tab lane. The tab now opens with response metrics, recent alerts,
  preparedness actions, CHV action status, and response gaps instead of leaving
  the primary lane empty while the action rail carries the work.
- Follow-up cockpit badge review separated operational status from data
  quality. Stale ward records now label risk and trigger states as last-known
  states, while freshness and climate caveats sit under a dedicated `Data
  quality` row.
- Follow-up badge affordance review made cockpit badges smaller and added
  adaptive plain-language tooltips on hover, focus, and click/tap. Tooltip copy
  is generated from the same ward status and evidence state as each badge, so it
  changes when the badge changes.

Phase 7 result:

```text
desktop-situation: overflow=false, primary=true, blank=0, broken=false, loading=false, map=2
desktop-response:  overflow=false, primary=true, blank=0, broken=false, loading=false
desktop-evidence:  overflow=false, primary=true, blank=0, broken=false, loading=false
desktop-history:   overflow=false, primary=true, blank=0, broken=false, loading=false
mobile-situation:  overflow=false, primary=true, blank=0, broken=false, loading=false, map=2
mobile-response:   overflow=false, primary=true, blank=0, broken=false, loading=false
mobile-evidence:   overflow=false, primary=true, blank=0, broken=false, loading=false
mobile-history:    overflow=false, primary=true, blank=0, broken=false, loading=false
```

## Test Plan

Run focused frontend tests:

```bash
cd frontend
npm test -- wards-detail-page.test.tsx
```

If the repo uses a different test command locally, use the established package
script from `frontend/package.json`.

Run broader dashboard tests if touched components are shared:

```bash
cd frontend
npm test -- wards-page.test.tsx dashboard-layout.test.tsx
```

Manual verification checklist:

- High-risk review-pending ward.
- Low-risk routine ward.
- Resolved workflow.
- Stale data.
- Missing operational evidence.
- Non-trigger role.
- No related alerts.
- Preparedness actions with lifecycle events.
- Climate caveat with missing lead days.
- Outcome feedback with response gap.

## Pixel Acceptance Checklist

Before completion, verify:

- The first viewport shows the ward name, risk level, decision headline, primary
  CTA, and trust state.
- There is only one filled primary action button.
- Header status chips are capped and ordered.
- No section title is larger than the context deserves.
- No text uses negative letter spacing.
- Labels use letter spacing `0`.
- Touched section radii are consistent.
- No decorative gradient or orb-like background exists on the ward page.
- No cards are visually nested inside other cards unless the inner element is a
  repeated list item or functional disclosure.
- Map dimensions are stable.
- Tables do not break the page on mobile.
- Long alert messages do not overflow.
- Long ward names wrap cleanly.
- `returnTo` remains safe and preserved.
- Freshness state comes from the backend freshness field, not re-derived.
- Queued, failed, retry-pending, and delivered alerts use accurate copy.
- Hidden evidence with warnings exposes warning state in its collapsed header.
- Empty states are quiet and specific.
- Loading skeletons do not cause major layout jump.
- Focus states are visible.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Evidence becomes too hidden | Show warning/danger summary states in collapsed headers and keep Evidence tab obvious |
| Tests become brittle due to tab movement | Assert semantic outcomes and user-visible labels, not exact old section order |
| Header still overloaded | Enforce chip and metric caps |
| Mobile becomes too long | Keep action and trust before tabs, collapse deep evidence |
| Role behavior regresses | Preserve `canTriggerAlerts` logic and add explicit tests |
| Alert status copy remains misleading | Replace hardcoded delivered copy with status-aware copy |
| Map causes visual instability | Use fixed aspect ratio and min height |
| Refactor touches too much at once | Implement in phases and keep data contracts stable |

## Final Acceptance Criteria

The redesign is complete when:

1. The first screen is decision-first and visually calm.
2. The primary action is visible without scrolling on desktop and mobile.
3. The page preserves all current evidence categories.
4. Deep evidence is available through tabs and disclosures.
5. Trust warnings are visible even when details are collapsed.
6. Mobile, tablet, and desktop layouts are intentional.
7. Existing role restrictions are preserved.
8. Tests cover the main operational states.
9. Browser verification confirms no overlap, clipping, broken map, or blank
   evidence sections.
10. The page feels like an operational cockpit for Migori ward response, not a
    database record rendered directly to screen.
