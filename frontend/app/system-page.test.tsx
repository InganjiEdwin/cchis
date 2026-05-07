import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SystemPage from "@/app/(dashboard)/system/page";
import type { SystemSnapshot } from "@/queries/use-system-query";

const mockUseAuth = vi.fn();
const mockUseSystemQuery = vi.fn();
const mockRefetch = vi.fn();
const dashboardMocks = vi.hoisted(() => ({
  retrySystemBackgroundJobsViaBff: vi.fn(),
  runManualRiskScoringViaBff: vi.fn(),
  setAlertDeliveryPauseViaBff: vi.fn(),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    lastUpdatedLabel,
    children,
  }: {
    title: string;
    subtitle: string;
    lastUpdatedLabel?: string;
    children?: React.ReactNode;
  }) => React.createElement("div", null, `${title} | ${subtitle} | ${lastUpdatedLabel ?? "no-label"}`, children),
}));

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock("@/queries/use-system-query", () => ({
  useSystemQuery: (...args: unknown[]) => mockUseSystemQuery(...args),
}));

vi.mock("@/lib/dashboard", () => ({
  retrySystemBackgroundJobsViaBff: dashboardMocks.retrySystemBackgroundJobsViaBff,
  runManualRiskScoringViaBff: dashboardMocks.runManualRiskScoringViaBff,
  setAlertDeliveryPauseViaBff: dashboardMocks.setAlertDeliveryPauseViaBff,
}));

function buildSystemSnapshot(overrides: Partial<SystemSnapshot> = {}): SystemSnapshot {
  return {
    visibleWards: 40,
    visibleAlerts: 5,
    visibleFacilities: 4,
    highRiskWards: 0,
    wardsWithFreshRisk: 40,
    latestRiskTimestamp: "2026-04-30T09:00:00Z",
    latestAlertTimestamp: "2026-04-30T09:10:00Z",
    latestFacilityTimestamp: "2026-04-30T08:00:00Z",
    latestChvTimestamp: "2026-04-30T09:20:00Z",
    queuedAlerts: 1,
    retryPendingAlerts: 0,
    failedAlerts: 0,
    deliveredAlerts: 4,
    latestFailedAlertTimestamp: null,
    latestRetryAlertTimestamp: null,
    latestDeliveredAlertTimestamp: "2026-04-30T09:10:00Z",
    activeChvs: 6,
    onlineChvs: 6,
    delayedChvs: 0,
    offlineChvs: 0,
    triageSessions24h: 1,
    referrals24h: 0,
    syncPayloads24h: 2,
    ussdSessions24h: 1,
    deliveryBackends: [{ name: "internal-dashboard", count: 5 }],
    controlStatus: {
      mode: "control_contracts_enabled",
      can_retry_background_jobs: true,
      can_run_manual_risk_scoring: true,
      can_pause_alert_delivery: true,
      alert_delivery_paused: false,
      alert_delivery_paused_until: null,
      alert_delivery_pause_reason: "",
      alert_delivery_pause_updated_at: null,
      alert_delivery_pause_updated_by: null,
    },
    ...overrides,
  };
}

function renderSystemPage(snapshot: SystemSnapshot) {
  mockUseSystemQuery.mockReturnValue({
    data: snapshot,
    isPending: false,
    isFetching: false,
    error: null,
    refetch: mockRefetch,
  });

  render(React.createElement(SystemPage));
}

async function flushControlAction() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("SystemPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-30T12:00:00Z"));
    vi.clearAllMocks();
    mockRefetch.mockResolvedValue({});
    dashboardMocks.retrySystemBackgroundJobsViaBff.mockResolvedValue({
      detail: "Background retry request accepted.",
      queued_alert_delivery_count: 1,
      failed_sync_payload_count: 0,
      task_ids: ["delivery-task"],
      control_status: buildSystemSnapshot().controlStatus,
    });
    dashboardMocks.runManualRiskScoringViaBff.mockResolvedValue({
      detail: "Manual risk scoring request accepted.",
      task_id: "risk-task",
      control_status: buildSystemSnapshot().controlStatus,
    });
    dashboardMocks.setAlertDeliveryPauseViaBff.mockResolvedValue({
      ...buildSystemSnapshot().controlStatus,
      alert_delivery_paused: true,
      alert_delivery_paused_until: "2026-04-30T13:00:00Z",
    });

    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        full_name: "System Admin",
        phone_number: null,
        role: "ADMIN",
        theme_preference: "DARK",
        ward: null,
        ward_name: null,
        is_active: true,
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the Operations Readiness layout with plain operator language", () => {
    renderSystemPage(buildSystemSnapshot());

    expect(screen.getByText(/Operations Readiness \| Check whether dashboard information is current and safe to use/i)).toBeInTheDocument();
    expect(screen.getByText("Are updates current?")).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();
    expect(screen.getByText("Activity log")).toBeInTheDocument();
    expect(screen.getByText("Safe actions")).toBeInTheDocument();

    expect(screen.queryByText("Pipeline Summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Unavailable Controls")).not.toBeInTheDocument();
    expect(screen.queryByText("Retry jobs unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Manual risk scoring unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Alert pause unavailable")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh status/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send waiting alerts/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /update ward risk/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pause outgoing sms/i })).toBeInTheDocument();
    expect(screen.queryByText(/control contracts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/backend endpoints/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/visible records/i)).not.toBeInTheDocument();
  });

  it("wires safe action buttons to the existing service calls", async () => {
    renderSystemPage(buildSystemSnapshot());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /send waiting alerts/i }));
    });
    expect(dashboardMocks.retrySystemBackgroundJobsViaBff).toHaveBeenCalledWith({ limit: 25 });
    await flushControlAction();
    expect(screen.getByText("1 waiting alert is being sent again.")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /update ward risk/i }));
    });
    expect(dashboardMocks.runManualRiskScoringViaBff).toHaveBeenCalledWith({
      month: 4,
      trigger_alerts: false,
      send_sms: false,
    });
    await flushControlAction();
    expect(screen.getByText("Ward risk is being updated. No SMS alerts will be sent from this action.")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /pause outgoing sms/i }));
    });
    expect(dashboardMocks.setAlertDeliveryPauseViaBff).toHaveBeenCalledWith({
      paused: true,
      duration_minutes: 60,
      reason: "Paused from operations readiness page.",
    });
    await flushControlAction();
    expect(mockRefetch).toHaveBeenCalledTimes(3);
  });

  it("renders missing updates as neutral readiness copy", () => {
    renderSystemPage(
      buildSystemSnapshot({
        wardsWithFreshRisk: 0,
        latestRiskTimestamp: null,
        latestChvTimestamp: null,
        syncPayloads24h: 0,
        ussdSessions24h: 0,
      }),
    );

    expect(screen.getByText("Some information is missing")).toBeInTheDocument();
    expect(screen.getAllByText("No update received yet").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Missing").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Update not received yet").length).toBeGreaterThan(0);
    expect(screen.queryByText(/visible timestamp/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/low confidence/i)).not.toBeInTheDocument();
  });

  it("renders delayed updates without using danger copy", () => {
    renderSystemPage(
      buildSystemSnapshot({
        latestRiskTimestamp: "2026-04-26T09:00:00Z",
        latestAlertTimestamp: "2026-04-26T09:10:00Z",
        latestFacilityTimestamp: "2026-04-26T08:00:00Z",
        latestChvTimestamp: "2026-04-26T09:20:00Z",
        queuedAlerts: 0,
      }),
    );

    expect(screen.getByText("Updates are delayed")).toBeInTheDocument();
    expect(screen.getAllByText("Delayed").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Last update: 4d ago/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("Review now")).not.toBeInTheDocument();
    expect(screen.queryByText("Stale data")).not.toBeInTheDocument();
    expect(screen.queryByText("Older visible data")).not.toBeInTheDocument();
  });

  it("renders failed alerts as a real attention state", () => {
    renderSystemPage(
      buildSystemSnapshot({
        failedAlerts: 1,
        latestFailedAlertTimestamp: "2026-04-30T09:30:00Z",
      }),
    );

    expect(screen.getAllByText("Needs attention").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 alert did not send").length).toBeGreaterThan(0);
    expect(screen.getByText("Review now")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText("1 alert did not send. Review alert sending before relying on this status.")).toBeInTheDocument();
    expect(screen.queryByText("Degraded")).not.toBeInTheDocument();
    expect(screen.queryByText("ERROR")).not.toBeInTheDocument();
  });

  it("does not report ready when alerts are waiting to send", () => {
    renderSystemPage(
      buildSystemSnapshot({
        latestRiskTimestamp: "2026-04-30T11:55:00Z",
        latestAlertTimestamp: "2026-04-30T11:55:00Z",
        latestFacilityTimestamp: "2026-04-30T11:55:00Z",
        latestChvTimestamp: "2026-04-30T11:55:00Z",
        queuedAlerts: 2,
        retryPendingAlerts: 1,
        failedAlerts: 0,
      }),
    );

    expect(screen.getAllByText("Needs attention").length).toBeGreaterThan(0);
    expect(screen.getByText(/Some alerts are waiting to send/i)).toBeInTheDocument();
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
  });

  it("does not hide waiting alerts when the page is also missing updates", () => {
    renderSystemPage(
      buildSystemSnapshot({
        latestRiskTimestamp: null,
        latestChvTimestamp: null,
        queuedAlerts: 2,
        retryPendingAlerts: 1,
        failedAlerts: 0,
      }),
    );

    expect(screen.getByText("Some information is missing")).toBeInTheDocument();
    expect(screen.getByText(/some alerts are waiting to send/i)).toBeInTheDocument();
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
  });
});
