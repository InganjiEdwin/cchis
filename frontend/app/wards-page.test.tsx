import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import WardsPage from "@/app/(dashboard)/wards/page";

const mockUseAuth = vi.fn();
const mockUseWardsQuery = vi.fn();
const mockReplace = vi.fn();
const mockRefetch = vi.fn();
const mockUseSearchParams = vi.fn();

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({ title, subtitle }: { title: string; subtitle: string }) =>
    React.createElement("div", null, `${title} | ${subtitle}`),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => "/wards",
  useSearchParams: () => mockUseSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/queries/use-wards-query", () => ({
  useWardsQuery: (...args: unknown[]) => mockUseWardsQuery(...args),
}));

describe("WardsPage", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
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

    mockUseSearchParams.mockReturnValue(new URLSearchParams("scope=Migori&sort=risk_desc"));

    mockUseWardsQuery.mockReturnValue({
      data: {
        items: [
          {
            id: 1,
            publicId: "WRD-0001",
            name: "North Kamagambo",
            county: "Migori",
            subCounty: "Rongo",
            riskLevel: "HIGH",
            riskScore: 82,
            updatedAt: "2026-04-27T08:00:00Z",
            predictedCases: 6,
            recentAlertCount: 2,
            triggerState: "REVIEW_PENDING",
            requiresAction: true,
            deliveryConcernCount: 1,
            workflowPublicId: "WF-001",
            recommendedAction: "Review trigger and verify ward conditions",
          },
          {
            id: 2,
            publicId: "WRD-0003",
            name: "West Asembo",
            county: "Migori",
            subCounty: "Rongo",
            riskLevel: "MEDIUM",
            riskScore: 61,
            updatedAt: "2026-04-27T08:03:00Z",
            predictedCases: 4,
            recentAlertCount: 1,
            triggerState: "ACTION_IN_PROGRESS",
            requiresAction: true,
            deliveryConcernCount: 1,
            workflowPublicId: "WF-003",
            recommendedAction: "Follow up on delivery issue",
          },
          {
            id: 3,
            publicId: "WRD-0002",
            name: "South Kadem",
            county: "Migori",
            subCounty: "Nyatike",
            riskLevel: "LOW",
            riskScore: 18,
            updatedAt: "2026-04-27T08:05:00Z",
            predictedCases: 1,
            recentAlertCount: 0,
            triggerState: "NONE",
            requiresAction: false,
            deliveryConcernCount: 0,
            workflowPublicId: null,
            recommendedAction: null,
          },
        ],
        wards: {
          count: 2,
          next: null,
          previous: null,
          results: [
            {
              id: 1,
              public_id: "WRD-0001",
              name: "North Kamagambo",
              county: "Migori",
              sub_county: "Rongo",
              ward_code: "MIG-01",
              current_risk_level: "HIGH",
              current_risk_score: 0.82,
              is_active: true,
              updated_at: "2026-04-27T08:00:00Z",
            },
            {
              id: 2,
              public_id: "WRD-0002",
              name: "South Kadem",
              county: "Migori",
              sub_county: "Nyatike",
              ward_code: "MIG-02",
              current_risk_level: "LOW",
              current_risk_score: 0.18,
              is_active: true,
              updated_at: "2026-04-27T08:05:00Z",
            },
          ],
        },
        latestRisks: [
          {
            ward_id: 1,
            ward_name: "North Kamagambo",
            risk_level: "HIGH",
            risk_score: 0.82,
            predicted_cases: 6,
            generated_at: "2026-04-27T08:00:00Z",
          },
          {
            ward_id: 2,
            ward_name: "South Kadem",
            risk_level: "LOW",
            risk_score: 0.18,
            predicted_cases: 1,
            generated_at: "2026-04-27T08:05:00Z",
          },
        ],
        wardQueueSummary: {
          wards_requiring_action: 1,
          workflow_active_wards: 1,
          alerts_pending: 1,
        },
        wardQueueUrgency: {
          has_actionable_wards: true,
          requires_action_count: 1,
        },
      },
      isPending: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });
  });

  it("renders the ward action queue framing and queue columns", () => {
    render(<WardsPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Ward Action Queue" })).toBeInTheDocument();
    expect(screen.getByText(/Identify wards requiring attention/i)).toBeInTheDocument();
    expect(screen.getAllByText("Trigger state").length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: "Expected cases (7d)" })).toBeInTheDocument();
    expect(screen.getByText("Wards requiring action")).toBeInTheDocument();
    expect(screen.getByText("Workflow-active wards")).toBeInTheDocument();
    expect(screen.getByText("Alerts pending")).toBeInTheDocument();
    expect(screen.getAllByText("Awaiting review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Action in progress").length).toBeGreaterThan(0);
  });

  it("renders normalized workflow labels instead of raw delivery-state vocabulary", () => {
    render(<WardsPage />);

    expect(screen.getAllByText("Awaiting review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Action in progress").length).toBeGreaterThan(0);
    expect(screen.queryByText("Queued")).not.toBeInTheDocument();
    expect(screen.queryByText("Retry pending")).not.toBeInTheDocument();
    expect(screen.queryByText("Failed")).not.toBeInTheDocument();
    expect(screen.queryByText("Delivered")).not.toBeInTheDocument();
  });

  it("shows the urgency banner and can focus the queue on actionable wards", async () => {
    const user = userEvent.setup();

    render(<WardsPage />);

    expect(screen.getByText(/2 wards require action now/i)).toBeInTheDocument();
    expect(screen.getByText("South Kadem")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /review queue/i }));

    expect(screen.getByText("North Kamagambo")).toBeInTheDocument();
    expect(screen.queryByText("South Kadem")).not.toBeInTheDocument();
    expect(screen.getAllByText("Review").length).toBeGreaterThan(0);
  });

  it("does not rewrite the URL when restoring an existing filtered queue from search params", async () => {
    vi.useFakeTimers();

    mockUseSearchParams.mockReturnValue(
      new URLSearchParams("scope=Migori&sort=risk_desc&q=North&sub_county=Rongo&trigger=awaiting_action&page=2"),
    );

    render(<WardsPage />);

    vi.advanceTimersByTime(350);

    expect(mockReplace).not.toHaveBeenCalled();
  });
});
