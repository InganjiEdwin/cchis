import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChvCoverageRequestPage from "@/app/(dashboard)/chvs/requests/[publicId]/page";

const mockUseAuth = vi.fn();
const mockUseParams = vi.fn();
const mockUseChvCoverageRequestDetailQuery = vi.fn();
const mockUseChvOperationsQuery = vi.fn();
const mockUseAssignChvCoverageRequestMutation = vi.fn();

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => mockUseParams(),
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

vi.mock("@/queries/use-chv-coverage-request-detail-query", () => ({
  useChvCoverageRequestDetailQuery: (...args: unknown[]) => mockUseChvCoverageRequestDetailQuery(...args),
}));

vi.mock("@/queries/use-chv-operations-query", () => ({
  useChvOperationsQuery: (...args: unknown[]) => mockUseChvOperationsQuery(...args),
}));

vi.mock("@/queries/use-assign-chv-coverage-request-mutation", () => ({
  useAssignChvCoverageRequestMutation: (...args: unknown[]) => mockUseAssignChvCoverageRequestMutation(...args),
}));

describe("ChvCoverageRequestPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "admin",
        role: "ADMIN",
      },
    });
    mockUseParams.mockReturnValue({ publicId: "req-1" });
    mockUseAssignChvCoverageRequestMutation.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseChvOperationsQuery.mockReturnValue({
      data: {
        chvs: [
          {
            id: 8,
            ward: 12,
            ward_name: "North Kamagambo",
            name: "Akinyi Omondi",
            phone_number: "+254700000001",
            language: "Kiswahili",
            is_active: true,
            created_at: "2026-04-28T08:00:00Z",
            last_sync_at: "2026-04-28T09:00:00Z",
            last_activity_at: "2026-04-28T08:55:00Z",
            operational_status: "ACTIVE",
            sync_health: "ONLINE",
            triage_sessions_24h: 1,
            referrals_24h: 0,
            sync_payloads_24h: 1,
            ussd_sessions_24h: 0,
            ward_alerts_total: 1,
            ward_alerts_delivered: 1,
          },
        ],
      },
      isSuccess: true,
    });
  });

  it("shows assignment controls only when the request is approved", async () => {
    mockUseChvCoverageRequestDetailQuery.mockReturnValue({
      data: {
        public_id: "req-1",
        ward: 12,
        ward_name: "North Kamagambo",
        ward_public_id: "ward-12",
        requested_by: 2,
        requested_by_username: "supervisor",
        status: "APPROVED",
        priority: "HIGH",
        trigger_source: "MANUAL",
        linked_alert_public_ids: [],
        linked_alerts_summary: [],
        reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
        requested_chv_count: 1,
        notes: "",
        assigned_to_user: null,
        assigned_to_username: null,
        assigned_to_team: "",
        reviewed_by: 1,
        reviewed_by_username: "admin",
        reviewed_at: "2026-04-28T08:10:00Z",
        review_decision_reason: "",
        expected_response_by: "2026-04-28T12:00:00Z",
        resolved_at: null,
        request_age: 300,
        is_overdue: false,
        sla_status: "ON_TRACK",
        assignments: [],
        events: [],
        created_at: "2026-04-28T08:00:00Z",
        updated_at: "2026-04-28T08:10:00Z",
      },
      isPending: false,
      isSuccess: true,
      error: null,
    });

    render(React.createElement(ChvCoverageRequestPage));

    expect(screen.getByText("Assignment controls")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assign CHV" })).toBeInTheDocument();
  }, 20000);

  it("does not show assignment controls for open requests", async () => {
    mockUseChvCoverageRequestDetailQuery.mockReturnValue({
      data: {
        public_id: "req-1",
        ward: 12,
        ward_name: "North Kamagambo",
        ward_public_id: "ward-12",
        requested_by: 2,
        requested_by_username: "supervisor",
        status: "OPEN",
        priority: "HIGH",
        trigger_source: "MANUAL",
        linked_alert_public_ids: [],
        linked_alerts_summary: [],
        reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
        requested_chv_count: 1,
        notes: "",
        assigned_to_user: null,
        assigned_to_username: null,
        assigned_to_team: "",
        reviewed_by: null,
        reviewed_by_username: null,
        reviewed_at: null,
        review_decision_reason: "",
        expected_response_by: "2026-04-28T12:00:00Z",
        resolved_at: null,
        request_age: 300,
        is_overdue: false,
        sla_status: "ON_TRACK",
        assignments: [],
        events: [],
        created_at: "2026-04-28T08:00:00Z",
        updated_at: "2026-04-28T08:00:00Z",
      },
      isPending: false,
      isSuccess: true,
      error: null,
    });

    render(React.createElement(ChvCoverageRequestPage));

    expect(screen.getByText("Assignment controls")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assign CHV" })).not.toBeInTheDocument();
    expect(screen.getByText(/Assign CHV is only available inside request detail when the workflow is approved/i)).toBeInTheDocument();
  }, 20000);

  it("keeps approved requests view-only for analysts", async () => {
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 2,
        username: "analyst",
        role: "ANALYST",
      },
    });
    mockUseChvCoverageRequestDetailQuery.mockReturnValue({
      data: {
        public_id: "req-1",
        ward: 12,
        ward_name: "North Kamagambo",
        ward_public_id: "ward-12",
        requested_by: 2,
        requested_by_username: "supervisor",
        status: "APPROVED",
        priority: "HIGH",
        trigger_source: "MANUAL",
        linked_alert_public_ids: [],
        linked_alerts_summary: [],
        reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
        requested_chv_count: 1,
        notes: "",
        assigned_to_user: null,
        assigned_to_username: null,
        assigned_to_team: "",
        reviewed_by: 1,
        reviewed_by_username: "admin",
        reviewed_at: "2026-04-28T08:10:00Z",
        review_decision_reason: "",
        expected_response_by: "2026-04-28T12:00:00Z",
        resolved_at: null,
        request_age: 300,
        is_overdue: false,
        sla_status: "ON_TRACK",
        assignments: [],
        events: [],
        created_at: "2026-04-28T08:00:00Z",
        updated_at: "2026-04-28T08:10:00Z",
      },
      isPending: false,
      isSuccess: true,
      error: null,
    });

    render(React.createElement(ChvCoverageRequestPage));

    expect(screen.getByText("Assignment controls")).toBeInTheDocument();
    expect(mockUseChvOperationsQuery).toHaveBeenCalledWith({ enabled: false });
    expect(screen.queryByRole("button", { name: "Assign CHV" })).not.toBeInTheDocument();
    expect(screen.getByText(/assignment controls are limited to Admin and Supervisor roles/i)).toBeInTheDocument();
  }, 20000);

  it("does not overstate alert origin when alert-driven linkage is missing", async () => {
    mockUseChvCoverageRequestDetailQuery.mockReturnValue({
      data: {
        public_id: "req-1",
        ward: 12,
        ward_name: "North Kamagambo",
        ward_public_id: "ward-12",
        requested_by: 2,
        requested_by_username: "supervisor",
        status: "OPEN",
        priority: "HIGH",
        trigger_source: "ALERT_DRIVEN",
        linked_alert_public_ids: [],
        linked_alerts_summary: [],
        reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
        requested_chv_count: 1,
        notes: "",
        assigned_to_user: null,
        assigned_to_username: null,
        assigned_to_team: "",
        reviewed_by: null,
        reviewed_by_username: null,
        reviewed_at: null,
        review_decision_reason: "",
        expected_response_by: "2026-04-28T12:00:00Z",
        resolved_at: null,
        request_age: 300,
        is_overdue: false,
        sla_status: "ON_TRACK",
        assignments: [],
        events: [],
        created_at: "2026-04-28T08:00:00Z",
        updated_at: "2026-04-28T08:00:00Z",
      },
      isPending: false,
      isSuccess: true,
      error: null,
    });

    render(React.createElement(ChvCoverageRequestPage));

    expect(screen.getByText("Manual request")).toBeInTheDocument();
    expect(screen.getByText("This request was opened without stored alert-linked context.")).toBeInTheDocument();
    expect(screen.queryByText("This request was opened from alert context.")).not.toBeInTheDocument();
  }, 20000);

  it("describes manual requests that were later linked to alert context truthfully", async () => {
    mockUseChvCoverageRequestDetailQuery.mockReturnValue({
      data: {
        public_id: "req-1",
        ward: 12,
        ward_name: "North Kamagambo",
        ward_public_id: "ward-12",
        requested_by: 2,
        requested_by_username: "supervisor",
        status: "OPEN",
        priority: "HIGH",
        trigger_source: "MANUAL",
        linked_alert_public_ids: ["alert-1"],
        linked_alerts_summary: [
          {
            alert_id: 22,
            alert_public_id: "alert-1",
            ward_id: 12,
            ward_name: "North Kamagambo",
            status: "DELIVERED",
            channel: "SMS",
            created_at: "2026-04-28T07:30:00Z",
            sent_at: "2026-04-28T07:31:00Z",
            risk_score: 77,
          },
        ],
        reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
        requested_chv_count: 1,
        notes: "",
        assigned_to_user: null,
        assigned_to_username: null,
        assigned_to_team: "",
        reviewed_by: null,
        reviewed_by_username: null,
        reviewed_at: null,
        review_decision_reason: "",
        expected_response_by: "2026-04-28T12:00:00Z",
        resolved_at: null,
        request_age: 300,
        is_overdue: false,
        sla_status: "ON_TRACK",
        assignments: [],
        events: [],
        created_at: "2026-04-28T08:00:00Z",
        updated_at: "2026-04-28T08:00:00Z",
      },
      isPending: false,
      isSuccess: true,
      error: null,
    });

    render(React.createElement(ChvCoverageRequestPage));

    expect(screen.getByText("Manual request")).toBeInTheDocument();
    expect(screen.getByText("This request was opened manually and later linked to alert context.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open alert" })).toHaveAttribute("href", "/alerts/22");
  }, 20000);
});
