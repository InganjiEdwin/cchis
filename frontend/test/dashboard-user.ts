import {
  buildDefaultDashboardCapabilities,
  buildDefaultProfileCapabilities,
  type CurrentUser,
  type DashboardActionCapabilityKey,
  type DashboardPageCapabilityKey,
  type UserRole,
} from "@/lib/auth";

export function buildDashboardUser(role: UserRole = "ADMIN", overrides: Partial<CurrentUser> = {}): CurrentUser {
  const broadScope = role === "ADMIN" || role === "ANALYST";
  const user: CurrentUser = {
    id: role === "ADMIN" ? 1 : role === "SUPERVISOR" ? 2 : role === "ANALYST" ? 3 : 4,
    username: `${role.toLowerCase()}-user`,
    email: `${role.toLowerCase()}@example.com`,
    full_name: `${role[0]}${role.slice(1).toLowerCase()} User`,
    phone_number: null,
    role,
    theme_preference: "SYSTEM",
    ward: role === "SUPERVISOR" || role === "CHV" ? 7 : null,
    ward_name: role === "SUPERVISOR" || role === "CHV" ? "North Kadem" : null,
    scope_type: broadScope ? "BROAD" : role === "CHV" ? "NONE" : "WARD",
    scope_ward_id: role === "SUPERVISOR" ? 7 : null,
    two_factor_policy: role === "ADMIN" || role === "SUPERVISOR" ? "REQUIRED" : role === "ANALYST" ? "OPTIONAL" : "NONE",
    is_totp_enabled: role === "ADMIN" || role === "SUPERVISOR",
    is_active: true,
    ...overrides,
  };

  return {
    ...user,
    dashboard_capabilities: overrides.dashboard_capabilities ?? buildDefaultDashboardCapabilities(user),
    profile_capabilities: overrides.profile_capabilities ?? buildDefaultProfileCapabilities(user),
  };
}

export function buildUserWithoutPageCapability(role: UserRole, pageKey: DashboardPageCapabilityKey): CurrentUser {
  const user = buildDashboardUser(role);
  return {
    ...user,
    dashboard_capabilities: {
      ...user.dashboard_capabilities!,
      pages: {
        ...user.dashboard_capabilities!.pages,
        [pageKey]: false,
      },
    },
  };
}

export function buildUserWithoutActionCapability(role: UserRole, actionKey: DashboardActionCapabilityKey): CurrentUser {
  const user = buildDashboardUser(role);
  return {
    ...user,
    dashboard_capabilities: {
      ...user.dashboard_capabilities!,
      actions: {
        ...user.dashboard_capabilities!.actions,
        [actionKey]: false,
      },
    },
  };
}
