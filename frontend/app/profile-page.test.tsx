import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProfilePage from "@/app/(dashboard)/profile/page";
import type { CurrentUser, ProfileActivityResponse } from "@/lib/auth";
import { isStrongPassword } from "@/lib/password-policy";

const mockUseAuth = vi.fn();
const mockRouterReplace = vi.fn();
const mockFetchProfileActivityViaBff = vi.fn();
const mockChangePasswordViaBff = vi.fn();
const mockVerifyProfileIdentityTwoFactorViaBff = vi.fn();
const mockFetchRecoveryCodeStatusViaBff = vi.fn();
const mockRegenerateRecoveryCodesViaBff = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockRouterReplace,
  }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    lastUpdatedLabel,
  }: {
    title: string;
    subtitle: string;
    lastUpdatedLabel?: string;
  }) => React.createElement("div", null, `${title} | ${subtitle} | ${lastUpdatedLabel ?? "no-label"}`),
}));

vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");

  return {
    ...actual,
    fetchProfileActivityViaBff: (...args: unknown[]) => mockFetchProfileActivityViaBff(...args),
    fetchRecoveryCodeStatusViaBff: (...args: unknown[]) => mockFetchRecoveryCodeStatusViaBff(...args),
    regenerateRecoveryCodesViaBff: (...args: unknown[]) => mockRegenerateRecoveryCodesViaBff(...args),
    changePasswordViaBff: (...args: unknown[]) => mockChangePasswordViaBff(...args),
    verifyProfileIdentityTwoFactorViaBff: (...args: unknown[]) => mockVerifyProfileIdentityTwoFactorViaBff(...args),
  };
});

function buildUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: 1,
    username: "admin",
    email: "admin@example.com",
    full_name: "System Admin",
    phone_number: "+254700000001",
    role: "ADMIN",
    theme_preference: "SYSTEM",
    ward: null,
    ward_name: null,
    scope_type: "BROAD",
    scope_ward_id: null,
    two_factor_policy: "REQUIRED",
    is_totp_enabled: false,
    is_active: true,
    account_created_at: "2026-04-20T08:00:00Z",
    last_login_at: "2026-04-30T09:30:00Z",
    profile_capabilities: {
      can_change_password: true,
      can_update_appearance: true,
      can_manage_totp: true,
      can_view_own_activity: true,
      can_update_identity: false,
      can_review_sessions: false,
      can_generate_profile_report: false,
      identity_update_mode: "admin_managed",
      mode: "auth_contract_backed_profile",
    },
    ...overrides,
  };
}

function buildActivityResponse(overrides: Partial<ProfileActivityResponse> = {}): ProfileActivityResponse {
  return {
    count: 1,
    next: null,
    previous: null,
    results: [
      {
        id: 1,
        event_type: "PASSWORD_CHANGED",
        status: "SUCCESS",
        title: "Password changed",
        description: "Your account password was changed.",
        created_at: "2026-04-30T09:40:00Z",
      },
    ],
    filters: {
      event_type: "",
      status: "",
      date_from: "",
      date_to: "",
      security_only: true,
      include_refresh_events: false,
      page: 1,
      page_size: 10,
    },
    capabilities: {
      can_view_own_activity: true,
      mode: "self_scoped_auth_activity",
    },
    ...overrides,
  };
}

function renderProfilePage(userOverrides: Partial<CurrentUser> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const updateAppearance = vi.fn().mockResolvedValue(buildUser(userOverrides));
  const updateProfile = vi.fn().mockImplementation((payload: Partial<CurrentUser>) =>
    Promise.resolve(buildUser({ ...userOverrides, ...payload })),
  );
  const logout = vi.fn().mockResolvedValue(undefined);
  const currentUser = buildUser(userOverrides);

  mockUseAuth.mockReturnValue({
    currentUser,
    logout,
    updateAppearance,
    updateProfile,
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ProfilePage />
    </QueryClientProvider>,
  );

  return { updateAppearance, updateProfile, logout, currentUser };
}

describe("ProfilePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchProfileActivityViaBff.mockResolvedValue(buildActivityResponse());
    mockFetchRecoveryCodeStatusViaBff.mockResolvedValue({
      remaining_count: 8,
      total_count: 10,
      last_generated_at: "2026-04-30T09:45:00Z",
      last_used_at: null,
      can_regenerate: true,
    });
    mockRegenerateRecoveryCodesViaBff.mockResolvedValue({
      recovery_codes: ["CCHIS-AAAA-BBBB-CCCC"],
      recovery_codes_generated: true,
      remaining_count: 10,
      total_count: 10,
      last_generated_at: "2026-05-02T09:45:00Z",
      last_used_at: null,
      can_regenerate: true,
    });
    mockChangePasswordViaBff.mockResolvedValue({ detail: "Password changed." });
    mockVerifyProfileIdentityTwoFactorViaBff.mockResolvedValue({ detail: "Personal details unlocked for editing." });
  });

  it("renders account identity and metadata without fake profile copy", async () => {
    renderProfilePage();

    expect(screen.getByText(/Profile \| Account, security, and preferences/i)).toBeInTheDocument();
    expect(screen.getAllByText("System Admin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ADMIN").length).toBeGreaterThan(0);
    expect(screen.getByText("admin@example.com")).toBeInTheDocument();
    expect(screen.getByText("+254700000001")).toBeInTheDocument();
    expect(screen.getAllByText("Migori County").length).toBeGreaterThan(0);
    expect(screen.getByText("Account created")).toBeInTheDocument();
    expect(screen.getByText("Last login")).toBeInTheDocument();
    expect((await screen.findAllByText("Password changed")).length).toBeGreaterThan(0);

    expect(screen.queryByText(/No organization record exposed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/No account-created timestamp/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Report generation unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Update unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Alert notifications")).not.toBeInTheDocument();
    expect(screen.queryByText("Password change unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Session review unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Audit trail unavailable")).not.toBeInTheDocument();
  });

  it("renders the TOTP setup link only when account policy and capability require setup", () => {
    renderProfilePage({
      two_factor_policy: "REQUIRED",
      is_totp_enabled: false,
    });

    expect(screen.getAllByRole("link", { name: /set up totp|open totp setup/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /set up totp|open totp setup/i })[0]).toHaveAttribute(
      "href",
      "/setup-2fa",
    );
  });

  it("renders enabled TOTP state without a setup call-to-action", () => {
    renderProfilePage({
      is_totp_enabled: true,
    });

    expect(screen.getAllByText("Enabled").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /set up totp|open totp setup/i })).not.toBeInTheDocument();
  });

  it("shows recovery-code status without exposing old plaintext codes", async () => {
    const user = userEvent.setup();
    mockFetchRecoveryCodeStatusViaBff.mockResolvedValue({
      remaining_count: 3,
      total_count: 10,
      last_generated_at: "2026-05-01T10:00:00Z",
      last_used_at: "2026-05-02T08:30:00Z",
      can_regenerate: true,
    });
    renderProfilePage({
      is_totp_enabled: true,
    });

    expect(await screen.findByText("3 of 10 remaining")).toBeInTheDocument();
    expect(screen.getByText(/Last generated/i)).toBeInTheDocument();
    expect(screen.getByText(/Last used/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Recovery codes" }));

    expect(screen.getByRole("heading", { name: "Manage recovery codes" })).toBeInTheDocument();
    expect(screen.getByText("3 of 10 codes")).toBeInTheDocument();
    expect(screen.getByText(/You cannot view existing recovery codes again/i)).toBeInTheDocument();
    expect(screen.queryByText("CCHIS-AAAA-BBBB-CCCC")).not.toBeInTheDocument();
  });

  it("regenerates recovery codes and requires save acknowledgement before closing", async () => {
    const user = userEvent.setup();
    renderProfilePage({
      is_totp_enabled: true,
    });

    await screen.findByText("8 of 10 remaining");
    await user.click(screen.getByRole("button", { name: "Regenerate codes" }));
    await user.type(screen.getByLabelText("Current password"), "ChangeMe123!");
    await user.type(screen.getByLabelText("Authenticator or recovery code"), "123456");
    await user.click(screen.getAllByRole("button", { name: "Regenerate codes" })[1]!);

    await waitFor(() => {
      expect(mockRegenerateRecoveryCodesViaBff).toHaveBeenCalledWith({
        current_password: "ChangeMe123!",
        code: "123456",
      });
    });
    expect(await screen.findByText("CCHIS-AAAA-BBBB-CCCC")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Close recovery codes modal"));

    expect(await screen.findByText("Save these recovery codes before closing this window.")).toBeInTheDocument();
    expect(screen.getByText("CCHIS-AAAA-BBBB-CCCC")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeDisabled();

    await user.click(screen.getByLabelText("I have saved these recovery codes."));
    await user.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => {
      expect(screen.queryByText("CCHIS-AAAA-BBBB-CCCC")).not.toBeInTheDocument();
    });
  });

  it("saves appearance changes through the auth provider", async () => {
    const user = userEvent.setup();
    const { updateAppearance } = renderProfilePage();

    await user.click(screen.getByRole("button", { name: "Dark" }));

    expect(updateAppearance).toHaveBeenCalledWith("DARK");
  });

  it("does not get stuck refreshing permissions for legacy cached users without capability fields", async () => {
    const user = userEvent.setup();
    const { updateAppearance } = renderProfilePage({
      profile_capabilities: undefined,
    });

    expect(screen.queryByText("Refreshing account permissions...")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "System" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Light" })).not.toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Light" }));

    expect(updateAppearance).toHaveBeenCalledWith("LIGHT");
    expect((await screen.findAllByText("Password changed")).length).toBeGreaterThan(0);
  });

  it("does not infer profile actions when profile capability fields deny them", () => {
    renderProfilePage({
      two_factor_policy: "REQUIRED",
      is_totp_enabled: false,
      profile_capabilities: {
        can_change_password: false,
        can_update_appearance: false,
        can_manage_totp: false,
        can_view_own_activity: false,
        can_update_identity: false,
        can_review_sessions: false,
        can_generate_profile_report: false,
        identity_update_mode: "admin_managed",
        mode: "auth_contract_backed_profile",
      },
    });

    expect(screen.queryByRole("button", { name: "Change password" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /set up totp|open totp setup/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Light" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "System" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Dark" })).toBeDisabled();
    expect(screen.getByText("Password changes are not available for this account state.")).toBeInTheDocument();
    expect(screen.getByText("Appearance changes are not available for this account state.")).toBeInTheDocument();
    expect(mockFetchProfileActivityViaBff).not.toHaveBeenCalled();
  });

  it("auto-submits and unlocks personal detail editing after a successful 2FA modal verification", async () => {
    const user = userEvent.setup();
    const { updateProfile } = renderProfilePage({
      is_totp_enabled: true,
      profile_capabilities: {
        can_change_password: true,
        can_update_appearance: true,
        can_manage_totp: true,
        can_view_own_activity: true,
        can_update_identity: true,
        can_review_sessions: false,
        can_generate_profile_report: false,
        identity_update_mode: "totp_step_up",
        mode: "auth_contract_backed_profile",
      },
    });

    await user.click(screen.getByRole("button", { name: "Edit details" }));
    await user.type(screen.getByLabelText("Authentication code"), "123456");

    await waitFor(() => {
      expect(mockVerifyProfileIdentityTwoFactorViaBff).toHaveBeenCalledWith("123456");
    });
    expect(mockVerifyProfileIdentityTwoFactorViaBff).toHaveBeenCalledTimes(1);

    await user.clear(screen.getByLabelText("Phone number"));
    await user.type(screen.getByLabelText("Phone number"), "+254711000002");
    await user.click(screen.getByRole("button", { name: "Save details" }));

    await waitFor(() => {
      expect(updateProfile).toHaveBeenCalledWith({
        username: "admin",
        full_name: "System Admin",
        email: "admin@example.com",
        phone_number: "+254711000002",
      });
    });
    expect(await screen.findByText("Personal details updated successfully.")).toBeInTheDocument();
  });

  it("keeps personal detail fields locked when 2FA verification fails", async () => {
    const user = userEvent.setup();
    mockVerifyProfileIdentityTwoFactorViaBff.mockRejectedValue(new Error("Invalid or expired code. Please try again."));
    renderProfilePage({
      is_totp_enabled: true,
      profile_capabilities: {
        can_change_password: true,
        can_update_appearance: true,
        can_manage_totp: true,
        can_view_own_activity: true,
        can_update_identity: true,
        can_review_sessions: false,
        can_generate_profile_report: false,
        identity_update_mode: "totp_step_up",
        mode: "auth_contract_backed_profile",
      },
    });

    await user.click(screen.getByRole("button", { name: "Edit details" }));
    await user.type(screen.getByLabelText("Authentication code"), "000000");

    expect(await screen.findByText("Invalid or expired code. Please try again.")).toBeInTheDocument();
    expect(mockVerifyProfileIdentityTwoFactorViaBff).toHaveBeenCalledWith("000000");
    expect(screen.queryByRole("button", { name: "Save details" })).not.toBeInTheDocument();
  });

  it("shows a local username validation message before saving personal details", async () => {
    const user = userEvent.setup();
    const { updateProfile } = renderProfilePage({
      is_totp_enabled: true,
      profile_capabilities: {
        can_change_password: true,
        can_update_appearance: true,
        can_manage_totp: true,
        can_view_own_activity: true,
        can_update_identity: true,
        can_review_sessions: false,
        can_generate_profile_report: false,
        identity_update_mode: "totp_step_up",
        mode: "auth_contract_backed_profile",
      },
    });

    await user.click(screen.getByRole("button", { name: "Edit details" }));
    await user.type(screen.getByLabelText("Authentication code"), "123456");
    await screen.findByRole("button", { name: "Save details" });
    await user.clear(screen.getByLabelText("Login username"));
    await user.type(screen.getByLabelText("Login username"), "Edwin Admin");
    await user.click(screen.getByRole("button", { name: "Save details" }));

    expect(screen.getByText("Login username can only use letters, numbers, and @ . + - _ characters.")).toBeInTheDocument();
    expect(updateProfile).not.toHaveBeenCalled();
  });

  it("posts password changes through the BFF modal and shows success", async () => {
    const user = userEvent.setup();
    renderProfilePage();

    await user.click(screen.getByRole("button", { name: "Change password" }));
    await user.type(screen.getByLabelText("Current password"), "ChangeMe123!");
    await user.type(screen.getByLabelText("New password"), "NewStrongPass123!");
    await user.type(screen.getByLabelText("Confirm new password"), "NewStrongPass123!");
    await user.click(screen.getAllByRole("button", { name: "Change password" })[1]!);

    await waitFor(() => {
      expect(mockChangePasswordViaBff).toHaveBeenCalledWith({
        current_password: "ChangeMe123!",
        new_password: "NewStrongPass123!",
      });
    });
    expect(await screen.findByText(/Password changed. You may be asked to sign in again/i)).toBeInTheDocument();
  });

  it("blocks weak password changes before calling the BFF", async () => {
    const user = userEvent.setup();
    renderProfilePage();

    await user.click(screen.getByRole("button", { name: "Change password" }));
    await user.type(screen.getByLabelText("Current password"), "ChangeMe123!");
    await user.type(screen.getByLabelText("New password"), "longpasswordonly");
    await user.type(screen.getByLabelText("Confirm new password"), "longpasswordonly");
    await user.click(screen.getAllByRole("button", { name: "Change password" })[1]!);

    expect(screen.getByText(/Use at least 12 characters with uppercase, lowercase, a number, and a symbol/i)).toBeInTheDocument();
    expect(mockChangePasswordViaBff).not.toHaveBeenCalled();
  });

  it("generates and fills a strong password before password change submit", async () => {
    const user = userEvent.setup();
    renderProfilePage();

    await user.click(screen.getByRole("button", { name: "Change password" }));
    await user.type(screen.getByLabelText("Current password"), "ChangeMe123!");
    await user.click(screen.getByRole("button", { name: "Generate strong password" }));

    const newPasswordInput = screen.getByLabelText("New password") as HTMLInputElement;
    const confirmPasswordInput = screen.getByLabelText("Confirm new password") as HTMLInputElement;
    const generatedPassword = newPasswordInput.value;

    expect(isStrongPassword(generatedPassword)).toBe(true);
    expect(confirmPasswordInput.value).toBe(generatedPassword);
    expect(screen.getByText(/Generated and filled a strong password/i)).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Change password" })[1]!);

    await waitFor(() => {
      expect(mockChangePasswordViaBff).toHaveBeenCalledWith({
        current_password: "ChangeMe123!",
        new_password: generatedPassword,
      });
    });
  });

  it("reveals and hides password values in the change password modal", async () => {
    const user = userEvent.setup();
    renderProfilePage();

    await user.click(screen.getByRole("button", { name: "Change password" }));
    await user.type(screen.getByLabelText("Current password"), "ChangeMe123!");
    await user.click(screen.getByRole("button", { name: "Generate strong password" }));

    const currentPasswordInput = screen.getByLabelText("Current password") as HTMLInputElement;
    const newPasswordInput = screen.getByLabelText("New password") as HTMLInputElement;
    const confirmPasswordInput = screen.getByLabelText("Confirm new password") as HTMLInputElement;

    expect(currentPasswordInput.type).toBe("password");
    expect(newPasswordInput.type).toBe("password");
    expect(confirmPasswordInput.type).toBe("password");

    await user.click(screen.getByRole("button", { name: "Show New password" }));
    expect(newPasswordInput.type).toBe("text");
    expect(screen.getByRole("button", { name: "Hide New password" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide New password" }));
    expect(newPasswordInput.type).toBe("password");
  });

  it("shows password-change errors without closing the modal", async () => {
    const user = userEvent.setup();
    mockChangePasswordViaBff.mockRejectedValue(new Error("Current password is incorrect."));
    renderProfilePage();

    await user.click(screen.getByRole("button", { name: "Change password" }));
    await user.type(screen.getByLabelText("Current password"), "bad-password");
    await user.type(screen.getByLabelText("New password"), "NewStrongPass123!");
    await user.type(screen.getByLabelText("Confirm new password"), "NewStrongPass123!");
    await user.click(screen.getAllByRole("button", { name: "Change password" })[1]!);

    expect(await screen.findByText("Current password is incorrect.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("renders truthful empty activity state from the account activity endpoint", async () => {
    mockFetchProfileActivityViaBff.mockResolvedValue(buildActivityResponse({ count: 0, results: [] }));
    renderProfilePage();

    expect(await screen.findByText("No account activity has been recorded yet.")).toBeInTheDocument();
  });

  it("sends activity filters through the profile activity query", async () => {
    const user = userEvent.setup();
    renderProfilePage();

    await screen.findAllByText("Password changed");

    expect(mockFetchProfileActivityViaBff).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
      event_type: "",
      status: "",
      date_from: "",
      date_to: "",
      security_only: true,
      include_refresh_events: false,
    });

    await user.selectOptions(screen.getByLabelText("Activity event type"), "LOGIN_FAILED");
    await waitFor(() => {
      expect(mockFetchProfileActivityViaBff).toHaveBeenLastCalledWith(
        expect.objectContaining({ event_type: "LOGIN_FAILED", page: 1 }),
      );
    });

    await user.selectOptions(screen.getByLabelText("Activity status"), "FAILED");
    await waitFor(() => {
      expect(mockFetchProfileActivityViaBff).toHaveBeenLastCalledWith(
        expect.objectContaining({ event_type: "LOGIN_FAILED", status: "FAILED", page: 1 }),
      );
    });

    await user.click(screen.getByLabelText("Show session refreshes"));
    await waitFor(() => {
      expect(mockFetchProfileActivityViaBff).toHaveBeenLastCalledWith(
        expect.objectContaining({ include_refresh_events: true, page: 1 }),
      );
    });
  });

  it("keeps session refresh activity hidden until the refresh toggle is enabled", async () => {
    const user = userEvent.setup();
    mockFetchProfileActivityViaBff.mockImplementation((filters) =>
      Promise.resolve(
        buildActivityResponse({
          count: filters.include_refresh_events ? 2 : 1,
          results: filters.include_refresh_events
            ? [
                {
                  id: 2,
                  event_type: "REFRESH_SUCCESS",
                  status: "SUCCESS",
                  title: "Session refreshed",
                  description: "Your dashboard session was refreshed.",
                  created_at: "2026-05-02T10:00:00Z",
                },
                {
                  id: 1,
                  event_type: "PASSWORD_CHANGED",
                  status: "SUCCESS",
                  title: "Password changed",
                  description: "Your account password was changed.",
                  created_at: "2026-04-30T09:40:00Z",
                },
              ]
            : [
                {
                  id: 1,
                  event_type: "PASSWORD_CHANGED",
                  status: "SUCCESS",
                  title: "Password changed",
                  description: "Your account password was changed.",
                  created_at: "2026-04-30T09:40:00Z",
                },
              ],
          filters: {
            event_type: "",
            status: "",
            date_from: "",
            date_to: "",
            security_only: true,
            include_refresh_events: filters.include_refresh_events ?? false,
            page: filters.page ?? 1,
            page_size: filters.page_size ?? 10,
          },
        }),
      ),
    );
    renderProfilePage();

    await screen.findAllByText("Password changed");
    expect(screen.queryByText("Session refreshed", { selector: "span" })).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Show session refreshes"));

    expect(await screen.findByText("Session refreshed", { selector: "span" })).toBeInTheDocument();
  });

  it("uses backend pagination controls for account activity", async () => {
    const user = userEvent.setup();
    mockFetchProfileActivityViaBff.mockImplementation((filters) =>
      Promise.resolve(
        buildActivityResponse({
          count: 11,
          next: filters.page === 1 ? "http://backend/activity?page=2" : null,
          previous: filters.page === 2 ? "http://backend/activity?page=1" : null,
          filters: {
            event_type: "",
            status: "",
            date_from: "",
            date_to: "",
            security_only: true,
            include_refresh_events: false,
            page: filters.page ?? 1,
            page_size: filters.page_size ?? 10,
          },
        }),
      ),
    );
    renderProfilePage();

    expect(await screen.findByText(/Page 1 of 2/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(mockFetchProfileActivityViaBff).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
    });
  });
});
