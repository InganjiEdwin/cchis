import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FacilityReadinessPage from "@/app/(dashboard)/facility-readiness/page";

const mockUseFacilityReadinessQuery = vi.fn();

vi.mock("@/queries/use-facility-readiness-query", () => ({
  useFacilityReadinessQuery: (...args: unknown[]) => mockUseFacilityReadinessQuery(...args),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    lastUpdatedLabel,
  }: {
    title: string;
    subtitle: string;
    lastUpdatedLabel?: string;
  }) => React.createElement("div", null, `${title} | ${subtitle} | ${lastUpdatedLabel ?? "no-label"}`),
}));

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

function buildFacility(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    public_id: "facility-1",
    name: "Macalder Mission Hospital",
    facility_code: "FAC-001",
    ward: 12,
    ward_name: "North Kamagambo",
    sub_county: "Rongo",
    facility_type: "hospital",
    ownership: "public",
    level: "LEVEL_3",
    ward_risk_level: "HIGH",
    ward_risk_score: 0.82,
    is_active: true,
    point: null,
    contact_phone: "+254700000001",
    updated_at: "2026-04-28T17:00:00Z",
    ...overrides,
  };
}

function buildRisk(overrides: Record<string, unknown> = {}) {
  return {
    ward_id: 12,
    ward_name: "North Kamagambo",
    risk_level: "HIGH",
    current_risk_score: 0.82,
    predicted_cases: 9,
    generated_at: "2026-04-28T17:00:00Z",
    ...overrides,
  };
}

function buildDecisionSummary(overrides: Record<string, unknown> = {}) {
  return {
    state: "REVIEW",
    headline: "Review top readiness priorities",
    body: "Top review priority: Macalder Mission Hospital. Review detail for this facility first.",
    confidence: "NORMAL",
    confidence_reason: null,
    total_review_facility_count: 1,
    top_priorities: [
      {
        facility_id: 1,
        facility_name: "Macalder Mission Hospital",
        ward_id: 12,
        ward_name: "North Kamagambo",
        priority_rank: 1,
        priority_label: "Top review priority",
        reason_codes: ["HIGH_READINESS_DIFFERENCE", "ELEVATED_WARD_RISK"],
        reason_text: "High calculated readiness difference, elevated ward risk.",
        review_href: null,
      },
    ],
    related_surfaces: {
      has_linked_alerts: false,
      linked_alert_count: 0,
    },
    ...overrides,
  };
}

describe("FacilityReadinessPage", () => {
  beforeEach(() => {
    mockUseFacilityReadinessQuery.mockReset();
    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [buildFacility()],
        risks: [buildRisk()],
        alerts: [],
        decisionSummary: buildDecisionSummary(),
        workflowStates: [],
      },
      isPending: false,
      error: null,
    });
  });

  it("renders operator-facing recommendation summary and top priority", () => {
    render(React.createElement(FacilityReadinessPage));

    expect(screen.getByText("Facilities assessed")).toBeInTheDocument();
    expect(screen.getByText("Facility records included in this readiness view")).toBeInTheDocument();
    expect(screen.getByText("Estimated ORS coverage")).toBeInTheDocument();
    expect(screen.queryByText("Visible facilities")).not.toBeInTheDocument();
    expect(screen.getByText("System recommendation")).toBeInTheDocument();
    expect(screen.getByText("Review top readiness priorities")).toBeInTheDocument();
    expect(screen.getAllByText("Top review priority").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("High calculated readiness difference, elevated ward risk.").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Review detail" })[0]).toHaveAttribute("href", "/facility-readiness/1");
    expect(screen.getByText(/1 facilities are currently flagged for readiness review in this view./i)).toBeInTheDocument();
    expect(screen.getByText("Impact")).toBeInTheDocument();
    expect(screen.getByText("1 review signal")).toBeInTheDocument();
    expect(screen.getByText("Action")).toBeInTheDocument();
    expect(screen.getByText("Review Macalder Mission")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Filter by ward" })).not.toBeInTheDocument();
    expect(screen.queryByText(/backend/i)).not.toBeInTheDocument();
  });

  it("renders compact workflow signals without adding row execution actions", () => {
    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [buildFacility()],
        risks: [buildRisk()],
        alerts: [],
        decisionSummary: buildDecisionSummary(),
        workflowStates: [
          {
            facility_id: 1,
            has_active_review: true,
            review_public_id: "review-1",
            review_status: "OPEN",
            has_active_update_request: true,
            update_request_public_id: "update-1",
            update_request_status: "QUEUED",
            has_active_escalation: false,
            escalation_public_id: null,
            escalation_status: null,
            label: "Update pending",
            tone: "warning",
          },
        ],
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityReadinessPage));

    expect(screen.getByText("Update pending")).toBeInTheDocument();
    expect(screen.getByText("Active reviews")).toBeInTheDocument();
    expect(screen.getByText("Update requests pending")).toBeInTheDocument();
    expect(screen.getByText("County reviews escalated")).toBeInTheDocument();
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Review detail" })[0]).toHaveAttribute("href", "/facility-readiness/1");
    expect(screen.queryByRole("button", { name: /request facility update/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /escalate/i })).not.toBeInTheDocument();
  });

  it("filters the matrix by advanced operational signals from the funnel", async () => {
    const user = userEvent.setup();

    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [
          buildFacility(),
          buildFacility({
            id: 2,
            public_id: "facility-2",
            name: "Got Kachola Dispensary",
            ward: 13,
            ward_name: "Got Kachola",
            sub_county: "Nyatike",
            ward_risk_level: "LOW",
            ward_risk_score: 0.12,
          }),
        ],
        risks: [
          buildRisk(),
          buildRisk({
            ward_id: 13,
            ward_name: "Got Kachola",
            risk_level: "LOW",
            current_risk_score: 0.12,
            predicted_cases: 1,
          }),
        ],
        alerts: [],
        decisionSummary: buildDecisionSummary(),
        workflowStates: [
          {
            facility_id: 1,
            has_active_review: true,
            review_public_id: "review-1",
            review_status: "OPEN",
            has_active_update_request: true,
            update_request_public_id: "update-1",
            update_request_status: "QUEUED",
            has_active_escalation: false,
            escalation_public_id: null,
            escalation_status: null,
            label: "Update pending",
            tone: "warning",
          },
        ],
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityReadinessPage));

    expect(screen.getByText("Got Kachola Dispensary")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "More filters" }));
    await user.click(screen.getByRole("button", { name: /Update pending1/i }));

    expect(screen.getByText("Active filter:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update pending" })).toBeInTheDocument();
    expect(screen.getAllByText("Macalder Mission Hospital").length).toBeGreaterThan(0);
    expect(screen.queryByText("Got Kachola Dispensary")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 1 facilities")).toBeInTheDocument();
  });

  it("uses total review count instead of assuming top priorities length is the full count", () => {
    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [buildFacility()],
        risks: [buildRisk()],
        alerts: [],
        decisionSummary: buildDecisionSummary({
          total_review_facility_count: 4,
        }),
        workflowStates: [],
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityReadinessPage));

    expect(screen.getByText(/4 facilities are currently flagged for readiness review in this view./i)).toBeInTheDocument();
    expect(screen.getByText("4 review signals")).toBeInTheDocument();
  });

  it("fails closed when review count is missing instead of inferring it from top priorities", () => {
    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [buildFacility()],
        risks: [buildRisk()],
        alerts: [],
        decisionSummary: {
          ...buildDecisionSummary(),
          total_review_facility_count: undefined,
        },
        workflowStates: [],
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityReadinessPage));

    expect(screen.getByText("Readiness review count is unavailable in this view.")).toBeInTheDocument();
    expect(screen.getByText("Review count unavailable")).toBeInTheDocument();
    expect(
      screen.queryByText(/1 facilities are currently flagged for readiness review in this view\./i),
    ).not.toBeInTheDocument();
  });

  it("focuses a ranked facility into the matrix", async () => {
    const user = userEvent.setup();

    render(React.createElement(FacilityReadinessPage));

    await user.click(screen.getAllByRole("button", { name: "Focus in matrix" })[0]);

    expect(screen.getAllByText("Top review priority").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("Macalder Mission Hospital")).toBeInTheDocument();
    expect(screen.getByDisplayValue("North Kamagambo")).toBeInTheDocument();
  });

  it("renders calm-state summary when no priorities are present", () => {
    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [buildFacility({ ward_risk_level: "LOW", ward_risk_score: 0.1, updated_at: "2026-04-28T17:00:00Z" })],
        risks: [buildRisk({ risk_level: "LOW", predicted_cases: 2, generated_at: "2026-04-28T17:00:00Z" })],
        alerts: [],
        decisionSummary: buildDecisionSummary({
          state: "CALM",
          headline: "No immediate review required",
          body: "Based on the current derived readiness estimates, no facility is flagged for review.",
          top_priorities: [],
        }),
        workflowStates: [],
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityReadinessPage));

    expect(screen.getByText("No immediate review required")).toBeInTheDocument();
    expect(screen.getByText("Based on the current derived readiness estimates, no facility is flagged for review.")).toBeInTheDocument();
    expect(screen.getByText("No facilities are currently flagged for readiness review in this view.")).toBeInTheDocument();
    expect(screen.getByText("No review signals detected (low confidence)")).toBeInTheDocument();
    expect(screen.getByText("No facilities are currently flagged for review, but data freshness is limited.")).toBeInTheDocument();
  });

  it("renders degraded-confidence summary with operator-facing caution copy", () => {
    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [buildFacility({ updated_at: "2026-04-20T17:00:00Z" })],
        risks: [buildRisk({ generated_at: "2026-04-20T17:00:00Z" })],
        alerts: [],
        decisionSummary: buildDecisionSummary({
          state: "DEGRADED_CONFIDENCE",
          headline: "Decision confidence is degraded. Start with Macalder Mission Hospital.",
          body: "Top review priority: Macalder Mission Hospital. Use this page as review guidance while stale or weak inputs remain.",
          confidence: "DEGRADED",
          confidence_reason: "stale_inputs",
        }),
        workflowStates: [],
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityReadinessPage));

    expect(screen.getByText("Decision confidence is degraded. Start with Macalder Mission Hospital.")).toBeInTheDocument();
    expect(screen.getByText("Decision confidence degraded: stale inputs.")).toBeInTheDocument();
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
    expect(
      screen.getByText("Top review priority: Macalder Mission Hospital. Use this page as review guidance while stale or weak inputs remain."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/facilities are flagged for readiness review, but data freshness is limited./i),
    ).toBeInTheDocument();
    expect(screen.getByText("Review Macalder Mission")).toBeInTheDocument();
    expect(screen.getByText("Low (stale inputs)")).toBeInTheDocument();
    expect(screen.getByText("Top contributors")).toBeInTheDocument();
  });

  it("discloses when client-side matrix filters are narrower than the summary view", async () => {
    const user = userEvent.setup();

    render(React.createElement(FacilityReadinessPage));

    await user.type(screen.getByPlaceholderText("Search facilities..."), "Macalder");

    expect(
      screen.getByText("The matrix filters below are narrower than the readiness summary shown above."),
    ).toBeInTheDocument();
  });

  it("describes linked alert context as alert records rather than facility records", () => {
    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [buildFacility()],
        risks: [buildRisk()],
        alerts: [],
        decisionSummary: buildDecisionSummary({
          related_surfaces: {
            has_linked_alerts: true,
            linked_alert_count: 2,
          },
        }),
        workflowStates: [],
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityReadinessPage));

    expect(
      screen.getByText("Linked alert context is present for 2 alert records in the current readiness scope."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/visible facility records/i)).not.toBeInTheDocument();
  });

  it("elevates stale facility inputs into the recommendation strip when no summary is available", () => {
    mockUseFacilityReadinessQuery.mockReturnValue({
      data: {
        facilities: [buildFacility({ updated_at: "2026-04-20T17:00:00Z" })],
        risks: [buildRisk({ generated_at: "2026-04-20T17:00:00Z" })],
        alerts: [],
        decisionSummary: null,
        workflowStates: [],
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityReadinessPage));

    expect(screen.getByText("Decision confidence degraded")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Facility readiness inputs are stale. No facilities are currently flagged for review, but this assessment is based on outdated data.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("No review signals detected (low confidence)")).toBeInTheDocument();
    expect(
      screen.getByText("No facilities are currently flagged for review, but data freshness is limited."),
    ).toBeInTheDocument();
  });
});
