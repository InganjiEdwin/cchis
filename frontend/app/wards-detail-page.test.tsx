import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WardDetailPage from "@/app/(dashboard)/wards/[id]/page";

const mockUseAuth = vi.fn();
const mockUseWardDetailQuery = vi.fn();
const mockUseParams = vi.fn();
const mockUseSearchParams = vi.fn();

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({ title, subtitle }: { title: string; subtitle: string }) =>
    React.createElement("div", null, `${title} | ${subtitle}`),
}));

vi.mock("@/components/trigger-alert-panel", () => ({
  TriggerAlertPanel: () => React.createElement("div", null, "Trigger alert mock"),
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
      data: {
        wardId: 12,
        name: "North Kamagambo",
        wardName: "North Kamagambo",
        wardCode: "MIG-12",
        county: "Migori",
        subCounty: "Rongo",
        riskLevel: "HIGH",
        riskScore: 86,
        predicted_cases: 12,
        predictedCases: 12,
        updatedAt: "2026-04-22T18:00:00Z",
        source: "MODEL",
        modelVersion: "v1",
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
      },
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
    expect(screen.getByText("Trigger alert mock")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to wards/i })).toHaveAttribute(
      "href",
      "/wards?risk=HIGH&page=2",
    );
    expect(screen.getByText("Recent risk history")).toBeInTheDocument();
    expect(screen.getByText("Recent alerts")).toBeInTheDocument();
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

    render(React.createElement(WardDetailPage));

    expect(
      await screen.findByText(/recommended actions are visible, but this role cannot trigger alerts/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Trigger alert mock")).not.toBeInTheDocument();
  });

  it("keeps the ward summary visible when alerts fail and shows a section warning", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: {
        wardId: 12,
        wardName: "North Kamagambo",
        wardCode: "MIG-12",
        county: "Migori",
        subCounty: "Rongo",
        riskLevel: "HIGH",
        riskScore: 86,
        predicted_cases: 12,
        predictedCases: 12,
        updatedAt: "2026-04-22T18:00:00Z",
        source: "MODEL",
        modelVersion: "v1",
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
        ],
        relatedAlerts: [],
      },
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByRole("heading", { name: "North Kamagambo" })).toBeInTheDocument();
    expect(await screen.findByText("Recent risk history")).toBeInTheDocument();
    expect(await screen.findByText("Trigger alert mock")).toBeInTheDocument();
    expect(screen.getByText("Recent alerts")).toBeInTheDocument();
  });
});
