import React from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SystemPage from "@/app/(dashboard)/system/page";
import type { SystemSnapshot } from "@/queries/use-system-query";

const mockUseAuth = vi.fn();
const mockUseSystemQuery = vi.fn();
const mockRefetch = vi.fn();

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

describe("SystemPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-30T12:00:00Z"));
    vi.clearAllMocks();

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

  it("renders the System Status layout without pipeline or fake control sections", () => {
    renderSystemPage(buildSystemSnapshot());

    expect(screen.getByText(/System Status \| Read-only system status from dashboard records/i)).toBeInTheDocument();
    expect(screen.getByText("Current capability mode")).toBeInTheDocument();
    expect(screen.getByText("Observed Activity")).toBeInTheDocument();
    expect(screen.getByText("Latest record summaries")).toBeInTheDocument();

    expect(screen.queryByText("Pipeline Summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Unavailable Controls")).not.toBeInTheDocument();
    expect(screen.queryByText("Retry jobs unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Manual risk scoring unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Alert pause unavailable")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry jobs/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /manual risk scoring/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /alert pause/i })).not.toBeInTheDocument();

    expect(screen.getByRole("button", { name: /refresh visible records/i })).toBeInTheDocument();
    expect(screen.queryByText("Refresh view")).not.toBeInTheDocument();
    expect(screen.getByText("Refresh visible records.")).toBeInTheDocument();
    expect(screen.getByText("Background-processing retry controls.")).toBeInTheDocument();
    expect(screen.getByText("Manual risk-scoring controls.")).toBeInTheDocument();
    expect(screen.getByText("Alert delivery pause controls.")).toBeInTheDocument();
    expect(screen.getByText("No manual controls are exposed on this page.")).toBeInTheDocument();
  });

  it("renders missing timestamps as neutral data-incomplete copy with low-confidence qualifiers", () => {
    renderSystemPage(
      buildSystemSnapshot({
        wardsWithFreshRisk: 0,
        latestRiskTimestamp: null,
        latestChvTimestamp: null,
        syncPayloads24h: 0,
        ussdSessions24h: 0,
      }),
    );

    expect(screen.getByText("Data incomplete")).toBeInTheDocument();
    expect(screen.getAllByText("No visible timestamp available").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No visible timestamp").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No last visible timestamp").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Low confidence: no visible timestamp").length).toBeGreaterThan(0);
  });

  it("renders stale visible data as older visible data without using danger copy", () => {
    renderSystemPage(
      buildSystemSnapshot({
        latestRiskTimestamp: "2026-04-26T09:00:00Z",
        latestAlertTimestamp: "2026-04-26T09:10:00Z",
        latestFacilityTimestamp: "2026-04-26T08:00:00Z",
        latestChvTimestamp: "2026-04-26T09:20:00Z",
        queuedAlerts: 0,
      }),
    );

    expect(screen.getByText("Stale data")).toBeInTheDocument();
    expect(screen.getAllByText("Older visible data").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Last visible: 4d ago/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("Visible delivery failure")).not.toBeInTheDocument();
    expect(screen.queryByText("Delivery failure")).not.toBeInTheDocument();
  });

  it("renders failed alert records as a real degraded danger state", () => {
    renderSystemPage(
      buildSystemSnapshot({
        failedAlerts: 1,
        latestFailedAlertTimestamp: "2026-04-30T09:30:00Z",
      }),
    );

    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("1 failed delivery records")).toBeInTheDocument();
    expect(screen.getByText("Delivery failure")).toBeInTheDocument();
    expect(screen.getByText("Visible delivery failure")).toBeInTheDocument();
    expect(screen.getByText("ERROR")).toBeInTheDocument();
    expect(screen.getByText("1 alert deliveries are recorded as failed in visible records.")).toBeInTheDocument();
  });

  it("does not report OK when visible alert backlog needs review", () => {
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

    expect(screen.getByText("Review needed")).toBeInTheDocument();
    expect(screen.getByText(/queued or retry-pending items/i)).toBeInTheDocument();
    expect(screen.queryByText("OK")).not.toBeInTheDocument();
  });

  it("does not hide alert backlog when the page is also data incomplete", () => {
    renderSystemPage(
      buildSystemSnapshot({
        latestRiskTimestamp: null,
        latestChvTimestamp: null,
        queuedAlerts: 2,
        retryPendingAlerts: 1,
        failedAlerts: 0,
      }),
    );

    expect(screen.getByText("Data incomplete")).toBeInTheDocument();
    expect(screen.getByText(/queued or retry-pending items/i)).toBeInTheDocument();
    expect(screen.queryByText("OK")).not.toBeInTheDocument();
  });
});
