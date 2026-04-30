import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WardDetailPage from "@/app/(dashboard)/wards/[id]/page";

const mockUseAuth = vi.fn();
const mockUseWardDetailQuery = vi.fn();
const mockUseParams = vi.fn();
const mockUseSearchParams = vi.fn();

function buildWardDetailState(overrides: Record<string, unknown> = {}) {
  return {
    wardId: 12,
    name: "North Kamagambo",
    wardName: "North Kamagambo",
    wardCode: "MIG-12",
    county: "Migori",
    subCounty: "Rongo",
    riskLevel: "HIGH",
    triggerState: "REVIEW_PENDING",
    actionRequired: true,
    primaryCtaKind: "REVIEW_TRIGGER",
    riskScore: 86,
    predicted_cases: 12,
    predictedCases: 12,
    updatedAt: "2026-04-22T18:00:00Z",
    lastAlertAt: "2026-04-22T18:05:00Z",
    source: "MODEL",
    modelVersion: "v1",
    modelRunStatus: "COMPLETED",
    freshness: {
      generated_at: "2026-04-22T18:00:00Z",
      is_stale: true,
      stale_threshold_minutes: 120,
      history_count: 2,
      alert_count: 1,
      mode: "timestamp_and_record_availability",
    },
    driverSummaryMode: "derived_from_latest_record",
    guidanceSummaryMode: "static_risk_playbook",
    driverItems: [],
    guidanceItems: [],
    trend: {
      label: "+6 points vs previous run",
      direction: "up",
      delta_points: 6,
      mode: "derived_from_recent_history",
    },
    workflow: {
      public_id: "WF-100",
      status: "REVIEW_PENDING",
      status_label: "Awaiting review",
      recommended_action: "Review active alerts and confirm whether trigger action is still needed.",
      expected_operational_effect: "Clarifies whether escalation or delivery follow-up is required.",
      eligible_actions: ["REVIEW_TRIGGER", "VIEW_ALERT_HISTORY"],
      active_alert_count: 1,
      retry_pending_alert_count: 0,
      failed_alert_count: 0,
      queued_alert_count: 1,
      latest_risk_update_at: "2026-04-22T18:00:00Z",
      updated_at: "2026-04-22T18:03:00Z",
    },
    decisionSummary: {
      action_required: true,
      headline: "Action required. Review active alerts and trigger status.",
      why: "Risk spike detected",
      next_steps: ["Review trigger", "Review full alert history"],
      primary_cta_kind: "REVIEW_TRIGGER",
    },
    headerContext: {
      last_alert_at: "2026-04-22T18:05:00Z",
      latest_record_at: "2026-04-22T18:00:00Z",
      freshness_state: "STALE",
      trigger_state: "REVIEW_PENDING",
      expected_cases_7d: 12,
      risk_score: 86,
    },
    riskHistory: [
      {
        id: 1,
        ward: 12,
        ward_name: "North Kamagambo",
        model_run: 101,
        model_run_status: "COMPLETED",
        model_run_version: "v1",
        score: 86,
        risk_level: "HIGH",
        rainfall_mm: 92,
        flood_indicator: 1,
        predicted_cases: 12,
        source: "MODEL",
        model_version: "v1",
        notes: "",
        generated_at: "2026-04-22T18:00:00Z",
      },
      {
        id: 2,
        ward: 12,
        ward_name: "North Kamagambo",
        model_run: 100,
        model_run_status: "COMPLETED",
        model_run_version: "v1",
        score: 80,
        risk_level: "HIGH",
        rainfall_mm: 81,
        flood_indicator: 1,
        predicted_cases: 10,
        source: "MODEL",
        model_version: "v1",
        notes: "",
        generated_at: "2026-04-22T16:00:00Z",
      },
    ],
    relatedAlerts: [
      {
        id: 7,
        ward: 12,
        ward_name: "North Kamagambo",
        risk_score: 86,
        channel: "SMS",
        recipient: "Supervisor",
        message: "High risk alert",
        status: "QUEUED",
        delivery_backend: "twilio",
        attempt_count: 0,
        max_attempts: 3,
        last_attempted_at: null,
        next_retry_at: null,
        external_id: "",
        sent_at: null,
        created_at: "2026-04-22T18:05:00Z",
        error_message: "",
      },
    ],
    ...overrides,
  };
}

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    lastUpdatedLabel,
    lastUpdatedTone,
  }: {
    title: string;
    subtitle: string;
    lastUpdatedLabel?: string;
    lastUpdatedTone?: string;
  }) =>
    React.createElement(
      "div",
      null,
      `${title} | ${subtitle} | ${lastUpdatedLabel ?? "no-label"} | ${lastUpdatedTone ?? "no-tone"}`,
    ),
}));

vi.mock("@/components/trigger-alert-panel", () => ({
  TriggerAlertPanel: ({
    buttonLabel,
    fixedWard,
  }: {
    buttonLabel?: string;
    fixedWard?: { id: number; name: string } | null;
  }) =>
    React.createElement(
      "div",
      null,
      `Trigger alert mock | ${buttonLabel ?? "no-label"} | ${fixedWard?.id ?? "no-ward"} | ${fixedWard?.name ?? "no-name"}`,
    ),
}));

vi.mock("next/navigation", () => ({
  useParams: () => mockUseParams(),
  useSearchParams: () => mockUseSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/queries/use-ward-detail-query", () => ({
  useWardDetailQuery: (...args: unknown[]) => mockUseWardDetailQuery(...args),
}));

describe("WardDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseParams.mockReturnValue({ id: "12" });
    mockUseSearchParams.mockReturnValue(new URLSearchParams("returnTo=%2Fwards%3Frisk%3DHIGH%26page%3D2"));
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        full_name: "Admin User",
        phone_number: null,
        role: "ADMIN",
        theme_preference: "LIGHT",
        ward: null,
        ward_name: null,
        is_active: true,
      },
    });

    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState(),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("renders the operational ward detail layout with preserved back link state", async () => {
    render(React.createElement(WardDetailPage));

    await waitFor(() => {
      expect(mockUseWardDetailQuery).toHaveBeenCalledWith({
        wardId: 12,
        enabled: true,
      });
    });

    expect(await screen.findByRole("heading", { name: "North Kamagambo" })).toBeInTheDocument();
    expect(screen.getByText("Trigger alert mock | Review trigger | 12 | North Kamagambo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to wards/i })).toHaveAttribute(
      "href",
      "/wards?risk=HIGH&page=2",
    );
    expect(screen.getByText("Risk history")).toBeInTheDocument();
    expect(screen.getByText("Recent alerts")).toBeInTheDocument();
    expect(screen.getByText("Recommended action")).toBeInTheDocument();
  });

  it("shows a read-only recommendation state for non-trigger roles", async () => {
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 2,
        username: "analyst",
        email: "analyst@example.com",
        full_name: "Analyst User",
        phone_number: null,
        role: "ANALYST",
        theme_preference: "LIGHT",
        ward: null,
        ward_name: null,
        is_active: true,
      },
    });
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        relatedAlerts: [],
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(
      await screen.findByText(/recommended action is visible, but this role cannot start or review trigger work from this page/i),
    ).toBeInTheDocument();
    expect(screen.getByText("View full alert history")).toBeInTheDocument();
    expect(screen.queryByText(/Trigger alert mock/)).not.toBeInTheDocument();
  });

  it("keeps the ward summary visible when alerts fail and shows a section warning", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        relatedAlerts: [],
        workflow: {
          public_id: "WF-100",
          status: "FAILED",
          status_label: "Action in progress",
          recommended_action: "Inspect the failed alert record, confirm the recipient path, and decide whether to resend or escalate manually.",
          expected_operational_effect: "Keeps failed delivery from being mistaken for completed operational follow-up.",
          eligible_actions: ["REVIEW_TRIGGER", "VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 1,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-22T18:00:00Z",
          updated_at: "2026-04-22T18:03:00Z",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByRole("heading", { name: "North Kamagambo" })).toBeInTheDocument();
    expect(await screen.findByText("Risk history")).toBeInTheDocument();
    expect(await screen.findByText("Trigger alert mock | Review trigger | 12 | North Kamagambo")).toBeInTheDocument();
    expect(screen.getByText("Recent alerts")).toBeInTheDocument();
    expect(screen.getByText(/no recent alerts for this ward/i)).toBeInTheDocument();
  });

  it("renders explicit trigger state, stale freshness, and action-first controls without scrolling assumptions", async () => {
    render(React.createElement(WardDetailPage));

    expect(await screen.findAllByText("Awaiting review")).toHaveLength(2);
    expect(screen.getByText("Stale data")).toBeInTheDocument();
    expect(screen.getByText("Action required. Review active alerts and trigger status.")).toBeInTheDocument();
    expect(screen.getAllByText("View full alert history")).toHaveLength(2);
    expect(screen.getByText("Data status")).toBeInTheDocument();
    expect(screen.getByText("Trigger alert mock | Review trigger | 12 | North Kamagambo")).toBeInTheDocument();
  });

  it("shows compact operational empty states when signals, history, and alerts are unavailable", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        riskLevel: "LOW",
        triggerState: "NONE",
        actionRequired: false,
        primaryCtaKind: "VIEW_ALERT_HISTORY",
        driverItems: [],
        riskHistory: [],
        relatedAlerts: [],
        workflow: {
          public_id: "WF-102",
          status: "NONE",
          status_label: "No active trigger",
          recommended_action: "Continue routine monitoring and start a new trigger only if conditions change.",
          expected_operational_effect: "Keeps manual trigger initiation available without overstating it as the current primary action.",
          eligible_actions: ["OPEN_TRIGGER_FLOW", "VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 0,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-27T08:00:00Z",
          updated_at: "2026-04-27T08:02:00Z",
        },
        decisionSummary: {
          action_required: false,
          headline: "No decision required at this time.",
          why: "This ward is under routine monitoring.",
          next_steps: ["Review full alert history", "Continue routine surveillance", "Open trigger flow only if conditions change"],
          primary_cta_kind: "VIEW_ALERT_HISTORY",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("Risk signals & trend")).toBeInTheDocument();
    expect(screen.getByText("No active signals or trends detected.")).toBeInTheDocument();
    expect(screen.getByText("This ward is currently under routine monitoring.")).toBeInTheDocument();
    expect(screen.queryByText("Risk history")).not.toBeInTheDocument();
    expect(screen.getByText("No recent alerts for this ward")).toBeInTheDocument();
    expect(screen.getByText(/Latest record:/i)).toBeInTheDocument();
    expect(screen.getByText("Review alert history")).toBeInTheDocument();
    expect(screen.getByText("Continue routine surveillance")).toBeInTheDocument();
    expect(screen.getByText("No decision required at this time.")).toBeInTheDocument();
    expect(screen.getByText("Context: Routine monitoring (no active escalation)")).toBeInTheDocument();
    expect(screen.getByText("Trigger alert mock | Open trigger flow | 12 | North Kamagambo")).toBeInTheDocument();
  });

  it("uses backend freshness state instead of re-deriving staleness from timestamps", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        updatedAt: "2026-04-22T18:00:00Z",
        freshness: {
          generated_at: "2026-04-22T18:00:00Z",
          is_stale: false,
          stale_threshold_minutes: 120,
          history_count: 2,
          alert_count: 1,
          mode: "timestamp_and_record_availability",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText(/ward detail \| migori county ward decision console \| .* \| default/i)).toBeInTheDocument();
    expect(screen.getByText("Fresh data")).toBeInTheDocument();
    expect(screen.queryByText(/ \| stale$/i)).not.toBeInTheDocument();
  });

  it("shows a no-action monitoring state when the workflow is resolved", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        triggerState: "RESOLVED",
        actionRequired: false,
        primaryCtaKind: "VIEW_ALERT_HISTORY",
        freshness: {
          generated_at: "2026-04-27T08:00:00Z",
          is_stale: false,
          stale_threshold_minutes: 120,
          history_count: 2,
          alert_count: 1,
          mode: "timestamp_and_record_availability",
        },
        workflow: {
          public_id: "WF-101",
          status: "RESOLVED",
          status_label: "Resolved",
          recommended_action: "Continue routine monitoring and review recent activity for any early signal changes.",
          expected_operational_effect: "Keeps resolved workflow state explicit without elevating it into active action work.",
          eligible_actions: ["VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 0,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-27T08:00:00Z",
          updated_at: "2026-04-27T08:02:00Z",
        },
        decisionSummary: {
          action_required: false,
          headline: "No active trigger action is required right now.",
          why: "No elevated trigger condition is visible for this ward right now.",
          next_steps: ["Review full alert history", "Open Trigger Flow"],
          primary_cta_kind: "VIEW_ALERT_HISTORY",
        },
        headerContext: {
          last_alert_at: "2026-04-27T08:05:00Z",
          latest_record_at: "2026-04-27T08:00:00Z",
          freshness_state: "FRESH",
          trigger_state: "RESOLVED",
          expected_cases_7d: 12,
          risk_score: 86,
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findAllByText("Resolved")).toHaveLength(2);
    expect(screen.getByText("Fresh data")).toBeInTheDocument();
    expect(screen.getByText("No active trigger action is required right now.")).toBeInTheDocument();
    expect(screen.getByText("Review full alert history")).toBeInTheDocument();
    expect(screen.getByText(/current next step: review alert history\. open trigger flow only if conditions change\./i)).toBeInTheDocument();
    expect(screen.queryByText(/Trigger alert mock/)).not.toBeInTheDocument();
  });

  it("keeps empty recent-alerts guidance aligned with history-first CTA states", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        triggerState: "RESOLVED",
        actionRequired: false,
        primaryCtaKind: "VIEW_ALERT_HISTORY",
        relatedAlerts: [],
        workflow: {
          public_id: "WF-101",
          status: "RESOLVED",
          status_label: "Resolved",
          recommended_action: "Continue routine monitoring and review recent activity for any early signal changes.",
          expected_operational_effect: "Keeps resolved workflow state explicit without elevating it into active action work.",
          eligible_actions: ["VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 0,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-27T08:00:00Z",
          updated_at: "2026-04-27T08:02:00Z",
        },
        decisionSummary: {
          action_required: false,
          headline: "No active trigger action is required right now.",
          why: "No elevated trigger condition is visible for this ward right now.",
          next_steps: ["Review full alert history", "Open Trigger Flow"],
          primary_cta_kind: "VIEW_ALERT_HISTORY",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("No recent alerts for this ward")).toBeInTheDocument();
    expect(screen.getByText("Review full alert history if you need older ward-linked alert activity.")).toBeInTheDocument();
    expect(screen.queryByText(/open trigger flow if a guided response is still needed/i)).not.toBeInTheDocument();
  });

  it("promotes new trigger initiation when the ward is in a genuine none state", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        riskLevel: "LOW",
        triggerState: "NONE",
        actionRequired: false,
        primaryCtaKind: "OPEN_TRIGGER_FLOW",
        workflow: {
          public_id: "WF-102",
          status: "NONE",
          status_label: "No active trigger",
          recommended_action: "Continue routine monitoring and start a new trigger only if conditions change.",
          expected_operational_effect: "Keeps manual trigger initiation available without overstating it as the current primary action.",
          eligible_actions: ["OPEN_TRIGGER_FLOW", "VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 0,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-27T08:00:00Z",
          updated_at: "2026-04-27T08:02:00Z",
        },
        decisionSummary: {
          action_required: false,
          headline: "No active trigger action is required right now.",
          why: "No elevated trigger condition is visible for this ward right now.",
          next_steps: ["Open Trigger Flow", "Review full alert history"],
          primary_cta_kind: "OPEN_TRIGGER_FLOW",
        },
        headerContext: {
          last_alert_at: null,
          latest_record_at: "2026-04-27T08:00:00Z",
          freshness_state: "FRESH",
          trigger_state: "NONE",
          expected_cases_7d: 1,
          risk_score: 22,
        },
        relatedAlerts: [],
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("Trigger alert mock | Open Trigger Flow | 12 | North Kamagambo")).toBeInTheDocument();
    expect(screen.getAllByText("No active trigger").length).toBeGreaterThan(0);
    expect(screen.getByText("Trigger alert mock | Open Trigger Flow | 12 | North Kamagambo")).toBeInTheDocument();
    expect(screen.getByText("View full alert history")).toBeInTheDocument();
    expect(screen.getByText("No decision required at this time.")).toBeInTheDocument();
  });

  it("shows a routine-monitoring checkpoint instead of an unavailable decision summary in low-signal mode", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        riskLevel: "LOW",
        triggerState: "NONE",
        actionRequired: false,
        decisionSummary: {
          action_required: false,
          headline: "No decision required at this time.",
          why: "This ward is under routine monitoring.",
          next_steps: ["Review full alert history"],
          primary_cta_kind: "VIEW_ALERT_HISTORY",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("No decision required at this time.")).toBeInTheDocument();
    expect(screen.getByText("This ward is under routine monitoring.")).toBeInTheDocument();
    expect(screen.getByText("Context: Routine monitoring (no active escalation)")).toBeInTheDocument();
  });
});
