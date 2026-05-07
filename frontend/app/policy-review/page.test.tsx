import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PolicyReviewPage from "@/app/policy-review/page";
import type { CurrentUser, PolicyAcceptanceState } from "@/lib/auth";

const mockAcceptPolicies = vi.fn();
const mockFetchPolicyAcceptanceViaBff = vi.fn();
const mockGetDefaultRoute = vi.fn();
const mockLogout = vi.fn();
const mockReplace = vi.fn();
const mockSearchParams = vi.fn();
const mockUseAuth = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
  useSearchParams: () => mockSearchParams(),
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
    fetchPolicyAcceptanceViaBff: () => mockFetchPolicyAcceptanceViaBff(),
  };
});

vi.mock("@/lib/navigation", async () => {
  const actual = await vi.importActual<typeof import("@/lib/navigation")>("@/lib/navigation");
  return {
    ...actual,
    getDefaultRoute: (...args: unknown[]) => mockGetDefaultRoute(...args),
  };
});

const missingPolicyAcceptance: PolicyAcceptanceState = {
  required: true,
  is_current: false,
  terms_version: "terms-2026-05",
  privacy_version: "privacy-2026-05",
  cookie_notice_version: "cookies-2026-05",
  accepted_terms_version: null,
  accepted_privacy_version: null,
  accepted_cookie_notice_version: null,
  missing_documents: ["TERMS", "PRIVACY", "COOKIE_NOTICE"],
  terms_url: "/terms",
  privacy_url: "/privacy",
  cookie_notice_url: "/privacy#cookies",
};

const currentPolicyAcceptance: PolicyAcceptanceState = {
  ...missingPolicyAcceptance,
  is_current: true,
  accepted_terms_version: "terms-2026-05",
  accepted_privacy_version: "privacy-2026-05",
  accepted_cookie_notice_version: "cookies-2026-05",
  missing_documents: [],
};

function buildUser(policy_acceptance: PolicyAcceptanceState = missingPolicyAcceptance): CurrentUser {
  return {
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
    policy_acceptance,
  };
}

function mockAuthenticatedPolicyReview(policyAcceptance = missingPolicyAcceptance) {
  mockUseAuth.mockReturnValue({
    acceptPolicies: mockAcceptPolicies,
    currentUser: buildUser(policyAcceptance),
    isAuthenticated: true,
    isHydrating: false,
    logout: mockLogout,
  });
}

describe("PolicyReviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAcceptPolicies.mockResolvedValue(currentPolicyAcceptance);
    mockFetchPolicyAcceptanceViaBff.mockResolvedValue(missingPolicyAcceptance);
    mockGetDefaultRoute.mockReturnValue("/overview");
    mockLogout.mockResolvedValue(undefined);
    mockSearchParams.mockReturnValue(new URLSearchParams("returnTo=/wards/12?tab=actions"));
    mockAuthenticatedPolicyReview();
  });

  it("requires all acknowledgements before accepting current policy versions", async () => {
    const user = userEvent.setup();

    render(React.createElement(PolicyReviewPage));

    expect(screen.getByRole("heading", { name: "Before you continue" })).toBeInTheDocument();
    expect(screen.getByText("terms-2026-05")).toBeInTheDocument();
    expect(screen.getByText("privacy-2026-05")).toBeInTheDocument();
    expect(screen.getByText("cookies-2026-05")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read Terms" })).toHaveAttribute("href", "/terms");
    expect(screen.getByRole("link", { name: "Read Privacy Policy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Read Cookie Notice" })).toHaveAttribute("href", "/privacy#cookies");

    const submitButton = screen.getByRole("button", { name: "Accept and continue" });
    expect(submitButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: /Terms of Service/i }));
    expect(submitButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: /Privacy Policy/i }));
    expect(submitButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: /Cookie Notice/i }));
    expect(submitButton).toBeEnabled();
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockAcceptPolicies).toHaveBeenCalledWith({
        accepted_terms: true,
        accepted_privacy: true,
        accepted_cookie_notice: true,
        terms_version: "terms-2026-05",
        privacy_version: "privacy-2026-05",
        cookie_notice_version: "cookies-2026-05",
      });
    });
    expect(mockReplace).toHaveBeenCalledWith("/wards/12?tab=actions");
  });

  it("redirects unauthenticated users to login", async () => {
    mockUseAuth.mockReturnValue({
      acceptPolicies: mockAcceptPolicies,
      currentUser: null,
      isAuthenticated: false,
      isHydrating: false,
      logout: mockLogout,
    });

    render(React.createElement(PolicyReviewPage));

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/login");
    });
  });

  it("redirects users whose policy acceptance is already current", async () => {
    mockAuthenticatedPolicyReview(currentPolicyAcceptance);

    render(React.createElement(PolicyReviewPage));

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/wards/12?tab=actions");
    });
  });

  it("signs out without recording acceptance", async () => {
    const user = userEvent.setup();

    render(React.createElement(PolicyReviewPage));

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(mockLogout).toHaveBeenCalled();
    expect(mockAcceptPolicies).not.toHaveBeenCalled();
    expect(mockReplace).toHaveBeenCalledWith("/login");
  });
});
