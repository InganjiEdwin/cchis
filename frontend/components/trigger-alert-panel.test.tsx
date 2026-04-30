import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TriggerAlertPanel } from "@/components/trigger-alert-panel";

const mockUseAuth = vi.fn();
const mockUseWardsQuery = vi.fn();
const mockUseTriggerAlertMutation = vi.fn();
const mockUseTriggerAlertContextQuery = vi.fn();
const mockUseTriggerAlertPreviewQuery = vi.fn();
const mockUseTriggerAlertRequestStatusQuery = vi.fn();
const mockMutateAsync = vi.fn();

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/queries/use-wards-query", () => ({
  useWardsQuery: (...args: unknown[]) => mockUseWardsQuery(...args),
}));

vi.mock("@/queries/use-trigger-alert-mutation", () => ({
  useTriggerAlertMutation: () => mockUseTriggerAlertMutation(),
}));

vi.mock("@/queries/use-trigger-alert-context-query", () => ({
  useTriggerAlertContextQuery: (...args: unknown[]) => mockUseTriggerAlertContextQuery(...args),
}));

vi.mock("@/queries/use-trigger-alert-preview-query", () => ({
  useTriggerAlertPreviewQuery: (...args: unknown[]) => mockUseTriggerAlertPreviewQuery(...args),
}));

vi.mock("@/queries/use-trigger-alert-request-status-query", () => ({
  useTriggerAlertRequestStatusQuery: (...args: unknown[]) => mockUseTriggerAlertRequestStatusQuery(...args),
}));

describe("TriggerAlertPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "supervisor",
        email: "supervisor@example.com",
        full_name: "Supervisor User",
        phone_number: null,
        role: "SUPERVISOR",
        ward: 2,
        ward_name: "Beta Ward",
        scope_type: "WARD",
        scope_ward_id: 2,
        is_active: true,
      },
    });

    mockUseWardsQuery.mockReturnValue({
      data: {
        items: [
          {
            id: 1,
            name: "Alpha Ward",
            county: "Nairobi",
            subCounty: "West",
            riskLevel: "HIGH",
            riskScore: 0.91,
            updatedAt: "2026-04-21T08:00:00Z",
            predictedCases: 8,
            recentAlertCount: 2,
          },
          {
            id: 2,
            name: "Beta Ward",
            county: "Kisumu",
            subCounty: "East",
            riskLevel: "MEDIUM",
            riskScore: 0.52,
            updatedAt: "2026-04-21T08:30:00Z",
            predictedCases: 4,
            recentAlertCount: 0,
          },
        ],
        wards: { count: 2, next: null, previous: null, results: [] },
        latestRisks: [
          {
            ward_id: 1,
            ward_name: "Alpha Ward",
            risk_level: "HIGH",
            risk_score: 0.91,
            predicted_cases: 8,
            generated_at: "2026-04-21T08:00:00Z",
          },
          {
            ward_id: 2,
            ward_name: "Beta Ward",
            risk_level: "MEDIUM",
            risk_score: 0.52,
            predicted_cases: 4,
            generated_at: "2026-04-21T08:30:00Z",
          },
        ],
      },
      isPending: false,
      error: null,
    });

    mockUseTriggerAlertContextQuery.mockReturnValue({
      data: {
        ward: {
          id: 1,
          name: "Alpha Ward",
          county: "Nairobi",
          sub_county: "West",
        },
        risk: {
          level: "HIGH",
          score: 0.91,
          predicted_cases: 8,
          last_risk_update_at: "2026-04-25T08:00:00Z",
        },
        workflow: {
          status: "REVIEW_PENDING",
          decision_mode: "risk_only",
          trigger_reason: "Alpha Ward crossed a review threshold.",
          recommended_action: "Review active alerts and confirm field conditions.",
          active_alert_count: 2,
          alert_delivery_state: "awaiting_review",
          alert_delivery_label: "Awaiting review",
        },
        system_context: {
          why_this_might_need_an_alert: ["2 active alerts require follow-up."],
          what_happens_if_no_action: "2 alerts remain unresolved.",
          trigger_status_label: "Awaiting review",
          recommended_trigger_type: "FOLLOW_UP_REVIEW",
          confidence_label: "Moderate confidence",
        },
        recipient_preview: {
          chv_count: 12,
        },
        supported_delivery_channels: ["DASHBOARD", "SMS_CHV"],
        supported_trigger_types: [
          "HIGH_RISK_ESCALATION",
          "FOLLOW_UP_REVIEW",
          "DELIVERY_RETRY",
          "CUSTOM",
        ],
      },
      isLoading: false,
      error: null,
    });

    mockUseTriggerAlertPreviewQuery.mockReturnValue({
      data: {
        message_preview:
          "CHVs: Please review reported conditions in Alpha Ward. Recent alerts require follow-up and confirmation from the field.",
        message_mode: "backend_generated",
        supports_editing: true,
        channel_defaults: ["DASHBOARD", "SMS_CHV"],
        recipient_preview: {
          chv_count: 12,
        },
        recommended_action: "Review active alerts and confirm field conditions.",
      },
      isLoading: false,
      error: null,
    });

    mockUseTriggerAlertMutation.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
      error: null,
      reset: vi.fn(),
    });

    mockUseTriggerAlertRequestStatusQuery.mockReturnValue({
      data: null,
      isFetching: false,
      error: null,
    });

    mockMutateAsync.mockResolvedValue({
      message: "Alert request queued successfully.",
      request_id: "request-123",
      alert_id: null,
      ward_id: 1,
      ward_name: "Alpha Ward",
      risk_level: "HIGH",
      risk_score: 0.91,
      predicted_cases: 8,
      risk_score_id: 42,
      task_id: "task-123",
      send_sms: true,
      trigger_type: "FOLLOW_UP_REVIEW",
      message_mode: "operator_edited",
      queued_at: "2026-04-25T08:15:00Z",
      last_risk_update_at: "2026-04-25T08:00:00Z",
      estimated_chv_recipient_count: 12,
      trigger_linkage_state: "linked_existing_workflow",
    });
  });

  it("starts with guided ward selection when no ward is pre-focused", async () => {
    const user = userEvent.setup();

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Create Alert" }));

    await waitFor(() => {
      expect(mockUseWardsQuery).toHaveBeenCalled();
    });

    expect(screen.getByText("Choose a ward to review")).toBeInTheDocument();
    expect(screen.getByText("Alpha Ward")).toBeInTheDocument();
    expect(screen.getByText("Beta Ward")).toBeInTheDocument();
  });

  it("moves into the context step after selecting a ward from the list", async () => {
    const user = userEvent.setup();

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Create Alert" }));
    await user.click(screen.getByRole("button", { name: /Alpha Ward/i }));

    await waitFor(() => {
      expect(screen.getAllByText("Context").length).toBeGreaterThan(0);
    });

    expect(screen.getByText("Why this matters")).toBeInTheDocument();
    expect(screen.getByText("What happens if no action is taken")).toBeInTheDocument();
  });

  it("shows the guided 4-step flow when a ward is pre-focused", async () => {
    const user = userEvent.setup();

    render(
      React.createElement(TriggerAlertPanel, {
        fixedWard: {
          id: 1,
          name: "Alpha Ward",
          county: "Nairobi",
          subCounty: "West",
          riskLevel: "HIGH",
          riskScore: 0.91,
          predictedCases: 8,
          updatedAt: "2026-04-25T08:00:00Z",
        },
      }),
    );

    await user.click(screen.getByRole("button", { name: "Create Alert" }));

    expect(screen.getByText("Create alert for Alpha Ward")).toBeInTheDocument();
    expect(screen.queryByText("What action do you want to take?")).not.toBeInTheDocument();
    expect(screen.getAllByText("Context").length).toBeGreaterThan(0);
    expect(screen.getByText("Why this matters")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("What action do you want to take?")).toBeInTheDocument();
    expect(screen.getByText("Message preview")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getAllByText("Delivery").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getAllByText("Review").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Queue Alert Request" })).toBeInTheDocument();
  });

  it("uses truthful fallback context when backend guidance is unavailable for a medium-risk ward", async () => {
    const user = userEvent.setup();

    mockUseTriggerAlertContextQuery.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("backend unavailable"),
    });

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Create Alert" }));
    await user.click(screen.getByRole("button", { name: /Beta Ward/i }));

    expect(
      screen.getByText(
        "Detailed ward guidance is temporarily unavailable. Continuing with the latest visible dashboard data for this ward.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Awaiting review")).toBeInTheDocument();
    expect(screen.queryByText("Monitoring")).not.toBeInTheDocument();
    expect(screen.getByText("Latest visible ward signals suggest review before escalation.")).toBeInTheDocument();
  });

  it("uses a no-active-trigger fallback for low-risk wards when backend guidance is unavailable", async () => {
    const user = userEvent.setup();

    mockUseTriggerAlertContextQuery.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("backend unavailable"),
    });

    render(
      React.createElement(TriggerAlertPanel, {
        fixedWard: {
          id: 99,
          name: "Gamma Ward",
          county: "Migori",
          subCounty: "Rongo",
          riskLevel: "LOW",
          riskScore: 0.18,
          predictedCases: 0,
          updatedAt: "2026-04-25T08:00:00Z",
        },
      }),
    );

    await user.click(screen.getByRole("button", { name: "Create Alert" }));

    expect(screen.getByText("No active trigger")).toBeInTheDocument();
    expect(screen.queryByText("Monitoring")).not.toBeInTheDocument();
    expect(screen.getByText("No active trigger condition is visible right now.")).toBeInTheDocument();
  });

  it("queues a guided alert request with an edited message and shows truthful success feedback", async () => {
    const user = userEvent.setup();

    render(
      React.createElement(TriggerAlertPanel, {
        fixedWard: {
          id: 1,
          name: "Alpha Ward",
          county: "Nairobi",
          subCounty: "West",
          riskLevel: "HIGH",
          riskScore: 0.91,
          predictedCases: 8,
          updatedAt: "2026-04-25T08:00:00Z",
        },
      }),
    );

    await user.click(screen.getByRole("button", { name: "Create Alert" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Edit message" }));
    await user.clear(screen.getByRole("textbox"));
    await user.type(screen.getByRole("textbox"), "Please review reported household conditions in Alpha Ward today.");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Edited by operator before queueing")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Queue Alert Request" }));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ward_id: 1,
        send_sms: true,
        trigger_type: "FOLLOW_UP_REVIEW",
        message_override: "Please review reported household conditions in Alpha Ward today.",
      });
    });

    expect(screen.getByText("Message source")).toBeInTheDocument();
    expect(screen.getByText("Edited by operator")).toBeInTheDocument();

    expect(screen.getByText("Alert request queued")).toBeInTheDocument();
    expect(screen.getByText(/12 CHVs queued for notification/i)).toBeInTheDocument();
    expect(screen.getByText(/Linked to the current trigger workflow/i)).toBeInTheDocument();
    expect(screen.getByText("Waiting for alert record")).toBeInTheDocument();
    expect(screen.getByText("Tracking alert record")).toBeInTheDocument();
    expect(screen.getByText("Go to ward")).toBeInTheDocument();
  });
});
