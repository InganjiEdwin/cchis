import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "@/app/forgot-password/page";

const mockRequestPasswordReset = vi.fn();

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    requestPasswordReset: (...args: unknown[]) => mockRequestPasswordReset(...args),
  };
});

describe("ForgotPasswordPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("submits the entered identifier to the backend helper", async () => {
    const user = userEvent.setup();
    mockRequestPasswordReset.mockResolvedValue({
      detail: "If the account exists and is eligible for recovery, password reset instructions will be sent.",
    });

    render(React.createElement(ForgotPasswordPage));

    await user.type(screen.getByLabelText("Email address or username"), "analyst_demo");
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(mockRequestPasswordReset).toHaveBeenCalledWith("analyst_demo");
    });
  });

  it("shows the backend success message after a successful request", async () => {
    const user = userEvent.setup();
    mockRequestPasswordReset.mockResolvedValue({
      detail: "If the account exists and is eligible for recovery, password reset instructions will be sent.",
    });

    render(React.createElement(ForgotPasswordPage));

    await user.type(screen.getByLabelText("Email address or username"), "analyst@example.com");
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    expect(
      await screen.findByText(
        "If the account exists and is eligible for recovery, password reset instructions will be sent.",
      ),
    ).toBeInTheDocument();
  });

  it("surfaces backend request errors to the user", async () => {
    const user = userEvent.setup();
    mockRequestPasswordReset.mockRejectedValue(new Error("Request timed out. Please try again."));

    render(React.createElement(ForgotPasswordPage));

    await user.type(screen.getByLabelText("Email address or username"), "analyst_demo");
    await user.click(screen.getByRole("button", { name: /reset password/i }));

    expect(await screen.findByText("Request timed out. Please try again.")).toBeInTheDocument();
  });
});
