import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TriggerAlertPanel } from "@/components/trigger-alert-panel";

const mockUseAuth = vi.fn();
const mockFetchWardRiskDataViaBff = vi.fn();
const mockTriggerAlertViaBff = vi.fn();

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/lib/dashboard", () => ({
  fetchWardRiskDataViaBff: (...args: unknown[]) => mockFetchWardRiskDataViaBff(...args),
  triggerAlertViaBff: (...args: unknown[]) => mockTriggerAlertViaBff(...args),
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

    mockFetchWardRiskDataViaBff.mockResolvedValue({
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
    });

    mockTriggerAlertViaBff.mockResolvedValue({
      message: "Alert task queued successfully.",
      risk_score_id: 88,
      task_id: "task-123",
    });
  });

  it("loads ward context and queues an alert after explicit confirmation", async () => {
    const user = userEvent.setup();

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Trigger Alert" }));

    await waitFor(() => {
      expect(mockFetchWardRiskDataViaBff).toHaveBeenCalled();
    });

    expect(screen.getByRole("combobox", { name: "Ward" })).toHaveValue("2");
    expect(screen.getByText("Beta Ward")).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: /also request sms delivery/i }));
    await user.click(
      screen.getByRole("checkbox", {
        name: /i confirm this ward context is correct and i want to queue this alert now/i,
      }),
    );
    await user.click(screen.getByRole("button", { name: "Confirm and trigger" }));

    await waitFor(() => {
      expect(mockTriggerAlertViaBff).toHaveBeenCalledWith({
        ward_id: 2,
        send_sms: true,
      });
    });

    expect(screen.getByText(/alert task queued successfully\./i)).toBeInTheDocument();
    expect(screen.getByText(/task task-123 is queued/i)).toBeInTheDocument();
  });

  it("blocks submission until the confirmation checkbox is selected", async () => {
    const user = userEvent.setup();

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Trigger Alert" }));

    await waitFor(() => {
      expect(mockFetchWardRiskDataViaBff).toHaveBeenCalled();
    });

    expect(screen.getByRole("button", { name: "Confirm and trigger" })).toBeDisabled();
    expect(mockTriggerAlertViaBff).not.toHaveBeenCalled();
  });
});
