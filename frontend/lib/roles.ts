import type { UserRole } from "@/lib/auth";

export const DASHBOARD_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR", "ANALYST"];
export const ALERT_TRIGGER_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const CHV_DIRECTORY_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const SYSTEM_PAGE_ROLES: UserRole[] = ["ADMIN", "ANALYST"];

export function hasRole(role: UserRole | null | undefined, allowedRoles: UserRole[]) {
  return !!role && allowedRoles.includes(role);
}

export function isDashboardRole(role: UserRole | null | undefined) {
  return hasRole(role, DASHBOARD_ROLES);
}

export function canTriggerAlerts(role: UserRole | null | undefined) {
  return hasRole(role, ALERT_TRIGGER_ROLES);
}

export function canViewChvs(role: UserRole | null | undefined) {
  return hasRole(role, CHV_DIRECTORY_ROLES);
}

export function canViewSystem(role: UserRole | null | undefined) {
  return hasRole(role, SYSTEM_PAGE_ROLES);
}
