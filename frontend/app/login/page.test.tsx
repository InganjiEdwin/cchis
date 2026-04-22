import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";

const mockReplace = vi.fn();
const mockLogin = vi.fn();
const mockReadEnrollmentToken = vi.fn();
const mockGetDefaultRoute = vi.fn();
const mockIsDashboardRole = vi.fn();
const mockUseAuth = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    readEnrollmentToken: () => mockReadEnrollmentToken(),
  };
});

vi.mock("@/lib/navigation", () => ({
  getDefaultRoute: (...args: unknown[]) => mockGetDefaultRoute(...args),
}));

vi.mock("@/lib/roles", () => ({
  isDashboardRole: (...args: unknown[]) => mockIsDashboardRole(...args),
}));

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_LOGIN_TURNSTILE_THRESHOLD", "3");

    mockUseAuth.mockReturnValue({
      login: mockLogin,
      isHydrating: false,
      pendingEnrollment: null,
      pendingTwoFactor: null,
    });

    mockReadEnrollmentToken.mockReturnValue(null);
    mockGetDefaultRoute.mockReturnValue("/overview");
    mockIsDashboardRole.mockReturnValue(true);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("submits username and password, then routes authenticated users to their default page", async () => {
    const user = userEvent.setup();

    mockLogin.mockResolvedValue({
      id: 1,
      username: "analyst_demo",
      email: "analyst@example.com",
      full_name: "Demo Analyst",
      phone_number: null,
      role: "ANALYST",
      ward: 3,
      ward_name: "Macalder Kanyarwanda",
      is_active: true,
    });

    render(React.createElement(LoginPage));

    await user.type(screen.getByLabelText("Username"), "analyst_demo");
    await user.type(screen.getByLabelText("Password"), "ChangeMe123!");
    await user.click(screen.getByRole("button", { name: /access system/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        username: "analyst_demo",
        password: "ChangeMe123!",
        turnstile_token: undefined,
      });
    });

    expect(mockIsDashboardRole).toHaveBeenCalledWith("ANALYST");
    expect(mockGetDefaultRoute).toHaveBeenCalledWith("ANALYST");
    expect(mockReplace).toHaveBeenCalledWith("/overview");
  });

  it("routes to 2fa verification when the backend requires a second step", async () => {
    const user = userEvent.setup();

    mockLogin.mockResolvedValue(null);

    render(React.createElement(LoginPage));

    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "ChangeMe123!");
    await user.click(screen.getByRole("button", { name: /access system/i }));

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/verify-2fa");
    });
  });

  it("routes to 2fa setup when enrollment is pending in storage", async () => {
    const user = userEvent.setup();

    mockLogin.mockResolvedValue(null);
    mockReadEnrollmentToken.mockReturnValue("pending-enrollment-token");

    render(React.createElement(LoginPage));

    await user.type(screen.getByLabelText("Username"), "supervisor");
    await user.type(screen.getByLabelText("Password"), "ChangeMe123!");
    await user.click(screen.getByRole("button", { name: /access system/i }));

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/setup-2fa");
    });
  });

  it("surfaces backend login errors to the operator", async () => {
    const user = userEvent.setup();

    mockLogin.mockRejectedValue(new Error("Invalid credentials, please try again."));

    render(React.createElement(LoginPage));

    await user.type(screen.getByLabelText("Username"), "wrong-user");
    await user.type(screen.getByLabelText("Password"), "bad-password");
    await user.click(screen.getByRole("button", { name: /access system/i }));

    expect(await screen.findByText("Unable to sign in with those credentials.")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("briefly cools down the login form after repeated failures in the same browser session", async () => {
    const user = userEvent.setup();

    mockLogin.mockRejectedValue(new Error("Invalid credentials, please try again."));

    render(React.createElement(LoginPage));

    await user.type(screen.getByLabelText("Username"), "wrong-user");
    await user.type(screen.getByLabelText("Password"), "bad-password");
    await user.click(screen.getByRole("button", { name: /access system/i }));
    await screen.findByText("Unable to sign in with those credentials.");

    await user.click(screen.getByRole("button", { name: /access system/i }));
    await screen.findByText("Unable to sign in with those credentials.");

    await user.click(screen.getByRole("button", { name: /access system/i }));

    expect(await screen.findByText("Please wait 10 seconds before trying again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry in 10s/i })).toBeDisabled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("reveals a login challenge after repeated failures when turnstile is configured", async () => {
    const user = userEvent.setup();

    vi.stubEnv("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "site-key");
    vi.stubEnv("NEXT_PUBLIC_LOGIN_TURNSTILE_THRESHOLD", "3");
    mockLogin.mockRejectedValue(new Error("Invalid credentials, please try again."));

    render(React.createElement(LoginPage));

    await user.type(screen.getByLabelText("Username"), "wrong-user");
    await user.type(screen.getByLabelText("Password"), "bad-password");
    await user.click(screen.getByRole("button", { name: /access system/i }));
    await screen.findByText("Unable to sign in with those credentials.");

    await user.click(screen.getByRole("button", { name: /access system/i }));
    await screen.findByText("Unable to sign in with those credentials.");

    await user.click(screen.getByRole("button", { name: /access system/i }));

    expect(await screen.findByText("Complete the verification challenge to continue.")).toBeInTheDocument();
    expect(screen.getByText("Additional verification is required after repeated sign-in failures.")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
