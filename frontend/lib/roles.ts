import type { UserRole } from "@/lib/auth";

export const DASHBOARD_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR", "ANALYST"];
export const ALERT_TRIGGER_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const CHV_DIRECTORY_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const SYSTEM_PAGE_ROLES: UserRole[] = ["ADMIN", "ANALYST"];
export const PREPAREDNESS_ACTION_MANAGER_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const SENSITIVE_EXPORT_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const MESSAGE_GOVERNANCE_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR", "ANALYST"];
export const CHV_OFFLINE_ROLES: UserRole[] = ["CHV"];

export function hasRole(role: UserRole | null | undefined, allowedRoles: UserRole[]) {
  return !!role && allowedRoles.includes(role);
}

export function isDashboardRole(role: UserRole | null | undefined) {
  return hasRole(role, DASHBOARD_ROLES);
}

export function canUseChvOffline(role: UserRole | null | undefined) {
  return hasRole(role, CHV_OFFLINE_ROLES);
}

export function canTriggerAlerts(role: UserRole | null | undefined) {
  return hasRole(role, ALERT_TRIGGER_ROLES);
}

export function canManagePreparednessActions(role: UserRole | null | undefined) {
  return hasRole(role, PREPAREDNESS_ACTION_MANAGER_ROLES);
}

export function canViewChvs(role: UserRole | null | undefined) {
  return hasRole(role, CHV_DIRECTORY_ROLES);
}

export function canViewSystem(role: UserRole | null | undefined) {
  return hasRole(role, SYSTEM_PAGE_ROLES);
}

export function canExportSensitiveReports(role: UserRole | null | undefined) {
  return hasRole(role, SENSITIVE_EXPORT_ROLES);
}

export function canApproveMessageTemplates(role: UserRole | null | undefined) {
  return role === "ADMIN";
}
