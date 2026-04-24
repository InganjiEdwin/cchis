import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TriggerAlertPanel } from "@/components/trigger-alert-panel";

const mockUseAuth = vi.fn();
const mockUseWardsQuery = vi.fn();
const mockUseTriggerAlertMutation = vi.fn();
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

    mockUseTriggerAlertMutation.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
      error: null,
      reset: vi.fn(),
    });

    mockMutateAsync.mockResolvedValue({
      message: "Alert task queued successfully.",
      risk_score_id: 42,
      task_id: "task-123",
    });
  });

  it("queues a real backend alert trigger and shows the queued response", async () => {
    const user = userEvent.setup();

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Trigger Alert" }));

    await waitFor(() => {
      expect(mockUseWardsQuery).toHaveBeenCalled();
    });

    expect(screen.getByText("Queue a real alert trigger")).toBeInTheDocument();
    expect(screen.getByText("Select one ward")).toBeInTheDocument();

    await user.click(screen.getByText("Alpha Ward").closest("button") as HTMLButtonElement);
    await user.click(screen.getByRole("button", { name: "Queue Alert" }));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ward_id: 1,
        send_sms: false,
      });
    });

    expect(screen.getByText("Alert trigger queued")).toBeInTheDocument();
    expect(screen.getByText("task-123")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("shows the narrowed contract instead of the old county-wide targeting flow", async () => {
    const user = userEvent.setup();

    render(React.createElement(TriggerAlertPanel));

    await user.click(screen.getByRole("button", { name: "Trigger Alert" }));

    await waitFor(() => {
      expect(mockUseWardsQuery).toHaveBeenCalled();
    });

    expect(screen.getByText(/richer alert-builder flow has been collapsed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Entire county/i)).not.toBeInTheDocument();
  });
});
