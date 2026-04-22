# Tailwind Migration Plan

This document defines the frontend styling migration path from the current global-CSS approach to Tailwind CSS.

It is intentionally a gradual implementation plan, not a one-shot rewrite.

It is based on:

- the current Next.js frontend in `frontend/`
- the existing route and component inventory in `docs/IMPLEMENTATION_STATUS.md`
- the current dashboard direction in `docs/NEXTJS_DASHBOARD_V1_PLAN.md`

The goal is to adopt Tailwind as the default styling system for future frontend work without destabilizing the current app.

## Decision

CCHIS should migrate to Tailwind gradually.

Do not pause feature delivery for a full visual rewrite.

Do not convert the whole frontend in one pass.

From this point onward:

- new frontend components and pages should use Tailwind by default
- existing CSS can remain temporarily where it is still serving active screens
- old CSS should be retired only after the corresponding component or route has been migrated cleanly

## Why Now

This is still an early-stage frontend:

- the styling system is not yet deeply entrenched across a large production surface
- there is no long-lived external design-system contract that would make migration unusually risky
- many frontend routes are still evolving, which makes this the cheapest period to set the long-term styling direction

That said, the frontend is already large enough that a careless rewrite would create churn, regressions, and styling drift.

The right move is:

- migrate early
- migrate carefully
- migrate incrementally

## Migration Rules

- Tailwind becomes the default styling approach for all new frontend work.
- Existing global CSS remains allowed only for legacy surfaces that have not yet been migrated.
- Do not mix large new custom class systems into `frontend/app/globals.css` for new feature work unless there is a clear exception.
- Keep design tokens, resets, and a very small set of app-wide primitives centralized.
- Do not rewrite component logic and styling at the same time unless the feature itself already requires a logic change.
- Migrate route-by-route or component-by-component with clear ownership boundaries.
- Preserve current visual quality during migration; this is a tooling change, not permission to degrade the UI.
- Remove dead CSS after each migrated slice so the old system shrinks steadily.

## Target End State

The desired long-term frontend state is:

- Tailwind for component and page styling
- minimal global CSS for:
  - CSS variables and theme tokens
  - resets
  - typography baselines where still useful
  - a very small number of truly global utility patterns
- no large page-specific styling blocks living in `frontend/app/globals.css`
- no duplicated styling systems competing for ownership

## What Should Not Happen

- do not freeze the whole frontend while migration happens
- do not attempt a full app rewrite in one branch
- do not leave migrated components still coupled to large legacy CSS blocks if that CSS can be removed safely
- do not introduce Tailwind plus a second new CSS abstraction layer at the same time
- do not use the migration as an excuse to change route behavior, auth behavior, or backend contracts

## Recommended Sequence

The migration should proceed in this order:

1. install and configure Tailwind in the Next.js app
2. preserve current visuals while validating the Tailwind build pipeline
3. migrate shared low-risk UI primitives
4. migrate public auth and legal routes
5. migrate dashboard shell components
6. migrate dashboard pages one page at a time
7. remove obsolete global CSS in small batches
8. declare the legacy CSS phase complete only when route-level dependencies are gone

## Phase 1: Tooling Setup

Add Tailwind to the frontend with the minimum required supporting config.

Expected deliverables:

- Tailwind installed in `frontend/package.json`
- Tailwind config present and scoped to the frontend app
- PostCSS config present if required by the chosen setup
- Tailwind imported into the main global stylesheet entry cleanly
- basic utility usage verified in at least one non-critical component

Rules for this phase:

- do not change the app’s visual direction yet
- do not start mass conversion before the build, dev server, and test setup are stable
- confirm the Next.js version and Tailwind version combination cleanly support the intended setup

## Phase 2: Shared Foundation

Before migrating entire pages, establish the shared Tailwind foundation.

Create or define:

- color tokens
- spacing conventions
- typography conventions
- responsive breakpoint usage guidance
- layout primitives such as container, stack, page grid, and status presentation patterns

This phase may still keep some CSS variables in `globals.css`, but the component-facing consumption should move toward Tailwind classes.

Useful first candidates:

- buttons
- status banners
- cards
- section headers
- form field wrappers
- reusable page-layout shells

## Phase 3: Public Route Migration

Migrate the public and auth-adjacent routes first.

Suggested order:

1. `/login`
2. `/request-access`
3. `/forgot-password`
4. `/verify-2fa`
5. `/privacy`
6. `/terms`
7. `/unauthorized`

Why this order:

- these routes are visually important
- they are easier to verify than data-heavy dashboard pages
- they help establish the Tailwind patterns for forms, spacing, top bars, cards, and auth states

Each migrated route should:

- preserve its current behavior
- preserve or improve accessibility
- remove now-unused CSS classes from `globals.css`

## Phase 4: Dashboard Shell Migration

After the public routes, migrate the shared dashboard shell.

Suggested scope:

- sidebar
- topbar
- footer
- protected shell
- page frame primitives
- role-gate and common status layouts

This is the highest-leverage migration slice because it affects many screens at once without forcing immediate page rewrites.

Important rule:

- stabilize shared shell patterns before converting every dashboard page

## Phase 5: Dashboard Page Migration

Migrate dashboard pages one at a time.

Suggested order:

1. `/profile`
2. `/system`
3. `/overview`
4. `/wards`
5. `/alerts`
6. `/chvs`
7. detail pages as they mature

Why this order:

- `profile` and `system` are lower-risk layout conversions
- `overview` establishes the primary operational dashboard styling patterns
- the more data-dense screens can then inherit those patterns instead of improvising their own

For each page:

- migrate layout and styling only
- keep data contracts unchanged
- delete unused legacy classes once the route is stable

## Phase 6: CSS Retirement

Legacy CSS should shrink continuously as migration progresses.

After each converted slice:

- identify unused classes
- remove dead selectors
- keep `globals.css` readable and smaller than before

Do not wait until the very end to remove unused CSS.

If cleanup is postponed too long, the codebase will drift into a dual-system maintenance problem.

## Definition Of Done For Each Slice

A route or component migration is complete when:

- its visuals are fully expressed through Tailwind and any approved shared tokens
- route behavior is unchanged unless a separate product task required otherwise
- accessibility still works
- tests still pass where tests exist
- obviously dead legacy CSS for that slice has been removed
- no new global CSS was added for styling that Tailwind should own

## Risk Areas

The main migration risks are:

- visual regressions due to layout drift
- accidental responsive regressions
- duplicated styling ownership between Tailwind and old CSS
- giant PRs that are hard to review
- delayed cleanup that leaves the app half-migrated indefinitely

Mitigations:

- keep PRs small
- migrate by route or shared component group
- compare before and after visually
- remove dead CSS continuously
- avoid mixing logic rewrites into styling migration work

## Review Checklist

For each migration PR, review for:

- visual parity or clear visual improvement
- mobile and desktop behavior
- accessibility and focus states
- removal of dead CSS
- absence of new legacy-style CSS blocks for migrated UI
- consistency with established Tailwind patterns

## Policy Going Forward

Effective immediately:

- Tailwind is the preferred styling approach for future frontend work
- new pages and components should default to Tailwind
- additions to the legacy CSS system should be treated as exceptions, not the norm

If a contributor needs to add non-Tailwind styling:

- the reason should be explicit
- the scope should be narrow
- it should not recreate another large custom class system

## First Deliverable

The first migration slice should do the following:

- install and configure Tailwind
- establish the shared token and primitive strategy
- migrate `/login` and `/request-access`
- remove the now-unused login and request-access CSS blocks that become obsolete

This is the right first slice because it proves the setup on high-visibility screens without yet touching the full dashboard shell.

## Out Of Scope For This Plan

- changing backend APIs because of styling migration
- redesigning the entire product visual language from scratch
- introducing a separate component library at the same time
- rewriting all frontend logic during the migration

Those can be decided separately if needed later.
