import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PreparednessActionsPage from "@/app/(dashboard)/preparedness-actions/page";

const mockUseAuth = vi.fn();
const mockUseSearchParams = vi.fn();
const mockUsePreparednessActionsQuery = vi.fn();
const mockUseUpdatePreparednessActionMutation = vi.fn();

function buildPreparednessAction(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    public_id: "00000000-0000-0000-0000-000000000101",
    action_type: "field_verification",
    source_trigger_type: "alert_workflow",
    source_trigger_ref: "alert_workflow:00000000-0000-0000-0000-000000000201",
    ward: 12,
    ward_name: "North Kamagambo",
    ward_public_id: "00000000-0000-0000-0000-000000000012",
    facility: null,
    facility_name: null,
    chv: null,
    chv_name: null,
    alert: 19,
    alert_public_id: "00000000-0000-0000-0000-000000000019",
    alert_workflow: 4,
    alert_workflow_public_id: "00000000-0000-0000-0000-000000000201",
    risk_score: 31,
    model_run: 8,
    model_run_version: "ward-risk-v1",
    facility_readiness_review: null,
    facility_readiness_review_public_id: null,
    facility_update_request: null,
    facility_update_request_public_id: null,
    facility_escalation: null,
    facility_escalation_public_id: null,
    chv_coverage_request: null,
    chv_coverage_request_public_id: null,
    status: "IN_PROGRESS",
    priority: "HIGH",
    created_by: 1,
    created_by_username: "admin",
    assigned_to: 1,
    assigned_to_username: "admin",
    assigned_to_team: "",
    decision_policy_version: "ward-risk-policy-v1",
    due_at: "2026-05-03T09:00:00Z",
    sla_target_at: "2026-05-03T09:00:00Z",
    acknowledged_at: "2026-05-03T07:00:00Z",
    completed_at: null,
    cancelled_at: null,
    escalated_at: null,
    completion_evidence: {},
    cancellation_reason: "",
    escalation_metadata: {},
    lineage_metadata: {
      risk_score_id: 31,
    },
    notes: "Confirm field conditions.",
    is_overdue: true,
    sla_status: "OVERDUE",
    created_at: "2026-05-03T06:00:00Z",
    updated_at: "2026-05-03T07:00:00Z",
    events: [
      {
        public_id: "00000000-0000-0000-0000-000000000301",
        event_type: "CREATED",
        actor: 1,
        actor_username: "admin",
        old_status: "",
        new_status: "QUEUED",
        detail: "Preparedness action created.",
        metadata: {},
        created_at: "2026-05-03T06:00:00Z",
      },
    ],
    ...overrides,
  };
}

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({ title, subtitle }: { title: string; subtitle: string }) =>
    React.createElement("div", null, `${title} | ${subtitle}`),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockUseSearchParams(),
}));

vi.mock("@/queries/use-preparedness-actions-query", () => ({
  usePreparednessActionsQuery: (...args: unknown[]) => mockUsePreparednessActionsQuery(...args),
  useUpdatePreparednessActionMutation: () => mockUseUpdatePreparednessActionMutation(),
}));

describe("PreparednessActionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSearchParams.mockReturnValue(new URLSearchParams());
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "admin",
        role: "ADMIN",
      },
    });
    mockUsePreparednessActionsQuery.mockReturnValue({
      data: {
        count: 2,
        next: null,
        previous: null,
        results: [
          buildPreparednessAction(),
          buildPreparednessAction({
            public_id: "00000000-0000-0000-0000-000000000102",
            action_type: "facility_ors_review",
            source_trigger_type: "facility_readiness_review",
            ward: 13,
            ward_name: "Got Kachola",
            status: "BLOCKED",
            priority: "URGENT",
            chv: 7,
            chv_name: "Achieng CHV",
            assigned_to: null,
            assigned_to_username: null,
            assigned_to_team: "County operations",
            is_overdue: false,
            due_at: "2026-05-04T09:00:00Z",
          }),
        ],
      },
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseUpdatePreparednessActionMutation.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(buildPreparednessAction({ status: "COMPLETED" })),
      isPending: false,
      error: null,
    });
  });

  it("shows the operational queue with overdue and blocked filters", () => {
    render(<PreparednessActionsPage />);

    expect(screen.getByText("Action Queue | Preparedness tasks across visible wards")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Preparedness task ledger" })).toBeInTheDocument();
    expect(screen.getByText("North Kamagambo")).toBeInTheDocument();
    expect(screen.getByText("Facility ORS review")).toBeInTheDocument();
    expect(screen.getByText("Achieng CHV")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Overdue" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Blocked" })).toBeInTheDocument();
  });

  it("passes ward, facility, and CHV scope filters from the route", () => {
    mockUseSearchParams.mockReturnValue(new URLSearchParams("ward_id=12&facility_id=44&chv_id=7"));

    render(<PreparednessActionsPage />);

    expect(screen.getByText("Action Queue | Preparedness tasks for ward 12, facility 44, CHV 7")).toBeInTheDocument();
    expect(mockUsePreparednessActionsQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        filters: expect.objectContaining({
          ward_id: 12,
          facility_id: 44,
          chv_id: 7,
          page_size: 200,
        }),
      }),
    );
  });

  it("backs operational queue filters with API query parameters", async () => {
    render(<PreparednessActionsPage />);

    expect(mockUsePreparednessActionsQuery).toHaveBeenLastCalledWith(
      expect.objectContaining({
        filters: expect.objectContaining({
          statuses: expect.arrayContaining(["QUEUED", "ASSIGNED", "IN_PROGRESS", "BLOCKED"]),
          page_size: 200,
        }),
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Blocked" }));
    await waitFor(() => {
      expect(mockUsePreparednessActionsQuery).toHaveBeenLastCalledWith(
        expect.objectContaining({
          filters: expect.objectContaining({
            status: "BLOCKED",
            page_size: 200,
          }),
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Overdue" }));
    await waitFor(() => {
      expect(mockUsePreparednessActionsQuery).toHaveBeenLastCalledWith(
        expect.objectContaining({
          filters: expect.objectContaining({
            overdue: true,
            page_size: 200,
          }),
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Mine" }));
    await waitFor(() => {
      expect(mockUsePreparednessActionsQuery).toHaveBeenLastCalledWith(
        expect.objectContaining({
          filters: expect.objectContaining({
            assigned: "mine",
            page_size: 200,
          }),
        }),
      );
    });
  });

  it("submits completion evidence through the lifecycle drawer", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(buildPreparednessAction({ status: "COMPLETED" }));
    mockUseUpdatePreparednessActionMutation.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });

    render(<PreparednessActionsPage />);

    fireEvent.click(screen.getAllByRole("button", { name: "Open action" })[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Update status"), {
      target: { value: "COMPLETED" },
    });
    fireEvent.change(screen.getByLabelText("Evidence summary"), {
      target: { value: "Field verification completed with CHV report." },
    });
    fireEvent.change(screen.getByLabelText("Evidence reference"), {
      target: { value: "call-log-77" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Update action" }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          publicId: "00000000-0000-0000-0000-000000000101",
          payload: expect.objectContaining({
            status: "COMPLETED",
            completion_evidence: expect.objectContaining({
              summary: "Field verification completed with CHV report.",
              reference: "call-log-77",
              captured_via: "frontend_action_queue",
            }),
          }),
        }),
      );
    });
  });

  it("allows queued actions to be assigned to an owner team", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(buildPreparednessAction({ status: "ASSIGNED" }));
    mockUsePreparednessActionsQuery.mockReturnValue({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [
          buildPreparednessAction({
            status: "QUEUED",
            assigned_to: null,
            assigned_to_username: null,
            assigned_to_team: "",
            is_overdue: false,
          }),
        ],
      },
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseUpdatePreparednessActionMutation.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });

    render(<PreparednessActionsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Open action" }));
    expect(screen.getByLabelText("Update status")).toHaveValue("ASSIGNED");
    fireEvent.change(screen.getByLabelText("Assigned team"), {
      target: { value: "Ward response desk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Update action" }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          publicId: "00000000-0000-0000-0000-000000000101",
          payload: expect.objectContaining({
            status: "ASSIGNED",
            assigned_to_team: "Ward response desk",
          }),
        }),
      );
    });
  });
});
