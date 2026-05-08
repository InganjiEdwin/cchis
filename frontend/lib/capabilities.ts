import {
  buildDefaultDashboardCapabilities,
  DASHBOARD_ACTION_CAPABILITY_KEYS,
  DASHBOARD_PAGE_CAPABILITY_KEYS,
  type CurrentUser,
  type DashboardActionCapabilityKey,
  type DashboardCapabilities,
  type DashboardPageCapabilityKey,
} from "@/lib/auth";

export type DashboardCapabilityKey = DashboardPageCapabilityKey | DashboardActionCapabilityKey;

function isPageCapabilityKey(key: DashboardCapabilityKey): key is DashboardPageCapabilityKey {
  return (DASHBOARD_PAGE_CAPABILITY_KEYS as readonly string[]).includes(key);
}

function isActionCapabilityKey(key: DashboardCapabilityKey): key is DashboardActionCapabilityKey {
  return (DASHBOARD_ACTION_CAPABILITY_KEYS as readonly string[]).includes(key);
}

export function getDashboardCapabilities(user: CurrentUser | null | undefined): DashboardCapabilities | null {
  if (!user) {
    return null;
  }

  return user.dashboard_capabilities ?? buildDefaultDashboardCapabilities(user);
}

export function hasPageCapability(
  user: CurrentUser | null | undefined,
  pageKey: DashboardPageCapabilityKey,
): boolean {
  return getDashboardCapabilities(user)?.pages[pageKey] === true;
}

export function hasActionCapability(
  user: CurrentUser | null | undefined,
  actionKey: DashboardActionCapabilityKey,
): boolean {
  return getDashboardCapabilities(user)?.actions[actionKey] === true;
}

export function canViewPage(user: CurrentUser | null | undefined, pageKey: DashboardPageCapabilityKey): boolean {
  return hasPageCapability(user, pageKey);
}

export function canPerform(user: CurrentUser | null | undefined, actionKey: DashboardActionCapabilityKey): boolean {
  return hasActionCapability(user, actionKey);
}

export function requireDashboardCapability(
  user: CurrentUser | null | undefined,
  key: DashboardCapabilityKey,
): boolean {
  if (isPageCapabilityKey(key)) {
    return hasPageCapability(user, key);
  }

  if (isActionCapabilityKey(key)) {
    return hasActionCapability(user, key);
  }

  return false;
}
