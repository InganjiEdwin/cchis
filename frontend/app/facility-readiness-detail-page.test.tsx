import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FacilityDetailPage from "@/app/(dashboard)/facility-readiness/[id]/page";
import type { FacilityDetailSnapshot } from "@/queries/use-facility-detail-query";

const mockUseFacilityDetailQuery = vi.fn();
const mockUseParams = vi.fn();
const mockNotFound = vi.fn();
const mutationMocks = vi.hoisted(() => ({
  createReviewMutate: vi.fn(),
  acknowledgeReviewMutate: vi.fn(),
  createUpdateRequestMutate: vi.fn(),
  createEscalationMutate: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => mockUseParams(),
  notFound: () => mockNotFound(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
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

vi.mock("@/components/migori-ward-map", () => ({
  MigoriWardMap: () => React.createElement("div", null, "Ward map"),
}));

vi.mock("@/queries/use-facility-detail-query", () => ({
  useFacilityDetailQuery: (...args: unknown[]) => mockUseFacilityDetailQuery(...args),
}));

vi.mock("@/queries/use-facility-readiness-actions", () => ({
  useCreateFacilityReadinessReviewMutation: () => ({
    mutate: mutationMocks.createReviewMutate,
    isPending: false,
    error: null,
  }),
  useAcknowledgeFacilityReadinessReviewMutation: () => ({
    mutate: mutationMocks.acknowledgeReviewMutate,
    isPending: false,
    error: null,
  }),
  useCreateFacilityUpdateRequestMutation: () => ({
    mutate: mutationMocks.createUpdateRequestMutate,
    isPending: false,
    error: null,
  }),
  useCreateFacilityEscalationMutation: () => ({
    mutate: mutationMocks.createEscalationMutate,
    isPending: false,
    error: null,
  }),
}));

function buildFacilityDetailData(): FacilityDetailSnapshot {
  return {
    intelligence: {
      facility: {
        id: 4,
        public_id: "facility-4",
        name: "Got Kachola Dispensary",
        facility_code: "FAC-004",
        ward: 12,
        ward_name: "Got Kachola",
        sub_county: "Nyatike",
        facility_type: "dispensary",
        ownership: "public",
        level: "LEVEL_2",
        ward_risk_level: "LOW",
        ward_risk_score: 0,
        is_active: true,
        point: null,
        contact_phone: "",
        updated_at: "2026-04-22T20:34:00Z",
      },
      contact: null,
      active_review: null,
      active_update_request: null,
      active_escalation: null,
      linked_alerts: [
        {
          id: 8,
          public_id: "alert-public-8",
          ward_id: 12,
          ward_name: "Got Kachola",
          status: "RETRY_PENDING",
          channel: "DASHBOARD",
          recipient: "dashboard",
          risk_score: 1,
          created_at: "2026-04-22T20:34:00Z",
          sent_at: null,
          api_url: "/api/v1/alerts/8/",
          intelligence_api_url: "/api/v1/alerts/8/intelligence/",
          dashboard_url: "/alerts/8",
          filtered_alerts_url: "/alerts?ward_id=12",
        },
      ],
      chv_operations: {
        available: true,
        ward_id: 12,
        ward_name: "Got Kachola",
        active_chv_count: 1,
        total_chv_count: 1,
        api_url: "/api/v1/chvs/operations/?ward_id=12",
        dashboard_url: "/chvs?ward_id=12#chv-registry",
        mode: "chv_operations_deep_link_only",
        message: "Open CHV Operations filtered to this ward.",
      },
      readiness: {
        facility_type_label: "Level 2 Dispensary",
        surge_risk: "LOW",
        surge_risk_label: "Low",
        status_banner_label: "Facility readiness currently unavailable",
        projected_cases: 1,
        predicted_cases_per_day: 5,
        ors_estimate_percent: 95,
        ors_state: "READY",
        staffing_filled: 6,
        staffing_required: 6,
        staffing_percent: 100,
        staffing_state: "OPTIMAL",
        last_reported_at: "2026-04-22T20:34:00Z",
        freshness_state: "STALE",
        mode: "unavailable_until_direct_snapshot_or_promoted_forecast",
        backing_source: "unavailable",
        dashboard_truth_state: "unavailable",
      },
      context: {
        summary:
          "Got Kachola Dispensary has no promoted facility forecast yet, so the dashboard is withholding capacity inference instead of projecting proxy readiness from ward risk alone.",
        ward_risk_score: 0,
        ward_alert_count: 1,
        map_mode: "shared_ward_geometry_contract",
        driving_ward_ids: [12],
        action_reasoning: [],
      },
      forecasting: {
        source_kind: "unavailable",
        governance_mode: "not_available",
        model_version: null,
        forecast_mode: "readiness_unavailable_without_promoted_forecast",
        projected_pressure_score: 0,
        projected_readiness_state: "not_available",
        driving_ward_ids: [12],
        dashboard_truth_state: "unavailable",
      },
      freshness: {
        updated_at: "2026-04-22T20:34:00Z",
        is_stale: true,
        stale_threshold_minutes: 120,
        mode: "derived_from_forecast_or_facility_timestamp",
      },
      decision_summary: {
        state: "DEGRADED_CONFIDENCE",
        headline: "Decision confidence is degraded for this facility.",
        body: "Use this readiness detail for review only. Inputs are stale or still rely on weak proxy readiness signals.",
        confidence: "DEGRADED",
        confidence_reason: "stale_and_weak_proxy_inputs",
        total_review_facility_count: 1,
        top_priorities: [
          {
            facility_id: 4,
            facility_name: "Got Kachola Dispensary",
            ward_id: 12,
            ward_name: "Got Kachola",
            priority_rank: 1,
            priority_label: "Current facility",
            reason_codes: ["STALE_INPUTS", "WEAK_PROXY_INPUTS"],
            reason_text: "Stale inputs, weak proxy readiness backing.",
            review_href: null,
          },
        ],
        related_surfaces: {
          has_linked_alerts: true,
          linked_alert_count: 1,
        },
      },
      timeline: [
        {
          id: "facility-record",
          title: "Facility record refreshed",
          description:
            "Got Kachola Dispensary is using its current backend facility record. Readiness figures on this page are calculated from facility identity plus ward risk data.",
          timestamp: "2026-04-22T20:34:00Z",
          tone: "success",
          category: "system",
          meta: null,
          details: [],
        },
        {
          id: "alert-1",
          title: "Dashboard alert retry pending",
          description: "Pilot alert for Got Kachola. Risk level: HIGH. Predicted cases: 18.",
          timestamp: "2026-04-22T20:34:00Z",
          tone: "warning",
          category: "alert",
          meta: "Recipient: Dashboard",
          details: [],
        },
      ],
      capabilities: {
        can_view_contacts: false,
        can_open_readiness_review: true,
        can_request_facility_update: false,
        can_escalate_county_review: false,
        can_open_linked_alert: true,
        can_open_chv_operations: true,
        can_acknowledge_review: false,
        has_verified_contact: false,
        has_active_review: false,
        has_active_update_request: false,
        has_active_escalation: false,
        has_county_review_queue: true,
        mode: "contract_backed_readiness_workflows",
      },
    },
    wardMap: {
      type: "FeatureCollection",
      metadata: {
        county: "Migori",
        geometry_source: "test",
        geometry_feature_count: 0,
        expected_ward_count: 40,
        missing_source_wards: [],
        backend_ward_match_count: 0,
        returned_feature_count: 0,
        backend_wards_without_geometry: [],
        placeholder_geometry_detected: false,
        geometry_note: null,
      },
      features: [],
    },
  };
}

describe("FacilityDetailPage", () => {
  beforeEach(() => {
    mockUseParams.mockReturnValue({ id: "4" });
    mockNotFound.mockReset();
    mutationMocks.createReviewMutate.mockReset();
    mutationMocks.acknowledgeReviewMutate.mockReset();
    mutationMocks.createUpdateRequestMutate.mockReset();
    mutationMocks.createEscalationMutate.mockReset();
    mockUseFacilityDetailQuery.mockReset();
    mockUseFacilityDetailQuery.mockReturnValue({
      data: buildFacilityDetailData(),
      isPending: false,
      error: null,
    });
  });

  it("renders a diagnostic facility detail without fake operational actions", () => {
    render(React.createElement(FacilityDetailPage));

    expect(screen.getByText("Full readiness assessment unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("Facility-level forecast data is not yet integrated. Current metrics are derived from ward-level signals."),
    ).toBeInTheDocument();
    expect(screen.getByText("Flagged for readiness review")).toBeInTheDocument();
    expect(screen.getByText("Assessment confidence: low due to stale or proxy-backed data.")).toBeInTheDocument();
    expect(screen.getByText("No facility-level forecast available. Capacity estimates are derived from ward risk only.")).toBeInTheDocument();
    expect(screen.getByText("Operational Actions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open readiness review" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open linked alert" })).toHaveAttribute("href", "/alerts/8");
    expect(screen.getByRole("link", { name: "Open CHV Operations" })).toHaveAttribute(
      "href",
      "/chvs?ward_id=12#chv-registry",
    );
    expect(screen.getByText("No operational workflow activity is recorded for this facility.")).toBeInTheDocument();
    expect(screen.getByText("No named facility contacts are available from current records.")).toBeInTheDocument();
    expect(screen.getByText("Derived from facility identity and ward risk.")).toBeInTheDocument();
    expect(screen.getByText("Risk: HIGH | Predicted: 18")).toBeInTheDocument();
    expect(screen.queryByText("Unavailable Actions")).not.toBeInTheDocument();
    expect(screen.queryByText("Facility readiness currently unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText(/backend/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/dispatch/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/facility chat/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/send stock/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/fix staffing/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /notify ward chvs/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /notify chvs/i })).not.toBeInTheDocument();
  });

  it("renders backend-capability actions for an active review with verified contact", () => {
    const data = buildFacilityDetailData();
    const intelligence = data.intelligence;
    if (!intelligence) {
      throw new Error("Expected facility intelligence fixture.");
    }
    intelligence.contact = {
      public_id: "contact-1",
      display_label: "Facility In-Charge",
      role: "Nurse in charge",
      preferred_channel: "SMS",
      phone_last4: "0001",
      has_phone: true,
      has_email: false,
      source: "trusted_facility_registry",
      is_verified: true,
      is_active: true,
      verified_at: "2026-04-22T20:34:00Z",
    };
    intelligence.active_review = {
      public_id: "review-1",
      facility: 4,
      facility_name: "Got Kachola Dispensary",
      ward: 12,
      ward_name: "Got Kachola",
      status: "OPEN",
      severity: "MEDIUM",
      reason_codes: ["STALE_INPUTS", "WEAK_PROXY_INPUTS"],
      notes: "Opened for stale inputs.",
      created_at: "2026-04-22T20:34:00Z",
      updated_at: "2026-04-22T20:34:00Z",
      acknowledged_at: null,
      resolved_at: null,
      dismissed_at: null,
    };
    intelligence.capabilities.can_open_readiness_review = false;
    intelligence.capabilities.can_request_facility_update = true;
    intelligence.capabilities.can_escalate_county_review = true;
    intelligence.capabilities.can_acknowledge_review = true;
    intelligence.capabilities.has_verified_contact = true;
    intelligence.capabilities.has_active_review = true;
    mockUseFacilityDetailQuery.mockReturnValue({
      data,
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityDetailPage));

    expect(screen.getByText("Readiness review active")).toBeInTheDocument();
    expect(screen.getByText("Reason: Stale Inputs, Weak Proxy Inputs")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark as reviewed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request facility update" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Escalate for county review" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open readiness review" })).not.toBeInTheDocument();
    expect(screen.getByText("Facility In-Charge")).toBeInTheDocument();
    expect(screen.getByText(/Verified SMS contact ending 0001/)).toBeInTheDocument();
  });

  it("shows active update request status and suppresses duplicate update actions", () => {
    const data = buildFacilityDetailData();
    const intelligence = data.intelligence;
    if (!intelligence) {
      throw new Error("Expected facility intelligence fixture.");
    }
    intelligence.contact = {
      public_id: "contact-1",
      display_label: "Facility In-Charge",
      role: "Nurse in charge",
      preferred_channel: "SMS",
      phone_last4: "0001",
      has_phone: true,
      has_email: false,
      source: "trusted_facility_registry",
      is_verified: true,
      is_active: true,
      verified_at: "2026-04-22T20:34:00Z",
    };
    intelligence.active_review = {
      public_id: "review-1",
      facility: 4,
      facility_name: "Got Kachola Dispensary",
      ward: 12,
      ward_name: "Got Kachola",
      status: "OPEN",
      severity: "MEDIUM",
      reason_codes: ["STALE_INPUTS"],
      notes: "Opened for stale inputs.",
      created_at: "2026-04-22T20:34:00Z",
      updated_at: "2026-04-22T20:34:00Z",
      acknowledged_at: null,
      resolved_at: null,
      dismissed_at: null,
    };
    intelligence.active_update_request = {
      public_id: "update-1",
      review: "review-1",
      facility: 4,
      facility_name: "Got Kachola Dispensary",
      contact: "contact-1",
      contact_display_label: "Facility In-Charge",
      requested_by: 1,
      requested_by_username: "admin",
      channel: "SMS",
      message_body: "Please update readiness status.",
      status: "QUEUED",
      failure_reason: undefined,
      requested_at: "2026-04-22T20:34:00Z",
      sent_at: null,
      acknowledged_at: null,
      created_at: "2026-04-22T20:34:00Z",
      updated_at: "2026-04-22T20:34:00Z",
    };
    intelligence.capabilities.can_open_readiness_review = false;
    intelligence.capabilities.can_request_facility_update = false;
    intelligence.capabilities.has_verified_contact = true;
    intelligence.capabilities.has_active_review = true;
    intelligence.capabilities.has_active_update_request = true;
    mockUseFacilityDetailQuery.mockReturnValue({
      data,
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityDetailPage));

    expect(screen.getByText("Facility update pending")).toBeInTheDocument();
    expect(screen.getByText(/Queued via SMS, requested/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request facility update" })).not.toBeInTheDocument();
  });

  it("requires a county review queue before rendering escalation action", () => {
    const data = buildFacilityDetailData();
    const intelligence = data.intelligence;
    if (!intelligence) {
      throw new Error("Expected facility intelligence fixture.");
    }
    intelligence.active_review = {
      public_id: "review-1",
      facility: 4,
      facility_name: "Got Kachola Dispensary",
      ward: 12,
      ward_name: "Got Kachola",
      status: "OPEN",
      severity: "MEDIUM",
      reason_codes: ["STALE_INPUTS"],
      notes: "Opened for stale inputs.",
      created_at: "2026-04-22T20:34:00Z",
      updated_at: "2026-04-22T20:34:00Z",
      acknowledged_at: null,
      resolved_at: null,
      dismissed_at: null,
    };
    intelligence.capabilities.can_open_readiness_review = false;
    intelligence.capabilities.can_escalate_county_review = true;
    intelligence.capabilities.has_county_review_queue = false;
    intelligence.capabilities.has_active_review = true;
    mockUseFacilityDetailQuery.mockReturnValue({
      data,
      isPending: false,
      error: null,
    });

    render(React.createElement(FacilityDetailPage));

    expect(screen.queryByRole("button", { name: "Escalate for county review" })).not.toBeInTheDocument();
  });
});
