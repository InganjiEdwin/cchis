import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TriggerAlertPanel } from "@/components/trigger-alert-panel";

const mockUseAuth = vi.fn();
const mockUseWardsQuery = vi.fn();

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/queries/use-wards-query", () => ({
  useWardsQuery: (...args: unknown[]) => mockUseWardsQuery(...args),
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
        wards: {
          count: 2,
          next: null,
          previous: null,
          results: [
            {
              id: 1,
              public_id: "ward-1",
              name: "Alpha Ward",
              county: "Nairobi",
              sub_county: "West",
              ward_code: "A1",
              current_risk_level: "HIGH",
              current_risk_score: 0.91,
              is_active: true,
              updated_at: "2026-04-21T08:00:00Z",
            },
            {
              id: 2,
              public_id: "ward-2",
              name: "Beta Ward",
              county: "Kisumu",
              sub_county: "East",
              ward_code: "B2",
              current_risk_level: "MEDIUM",
              current_risk_score: 0.52,
              is_active: true,
              updated_at: "2026-04-21T08:30:00Z",
            },
          ],
        },
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
  });

  it("opens a structured multi-step workflow and completes the UI-only success state", async () => {
    const user = userEvent.setup();

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Trigger Alert" }));

    await waitFor(() => {
      expect(mockUseWardsQuery).toHaveBeenCalled();
    });

    expect(screen.getByText("Structured alert workflow")).toBeInTheDocument();
    expect(screen.getByText("Step 1")).toBeInTheDocument();
    expect(screen.getByText("Select Target")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Define Alert")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Delivery")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Review")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Send Alert" }));

    expect(screen.getByText("Alert sent successfully")).toBeInTheDocument();
    expect(screen.getByText("ALT-0042")).toBeInTheDocument();
    expect(screen.getByText("Dispatch Timeline")).toBeInTheDocument();
  });

  it("marks county-wide targeting as restricted for non-admin users", async () => {
    const user = userEvent.setup();

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Trigger Alert" }));

    await waitFor(() => {
      expect(mockUseWardsQuery).toHaveBeenCalled();
    });

    const countyOption = screen.getByRole("button", { name: /Entire county/i });
    expect(countyOption.className).toContain("cursor-not-allowed");
    expect(countyOption.className).toContain("opacity-60");
  });
});
