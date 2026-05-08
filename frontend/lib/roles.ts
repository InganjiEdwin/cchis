import {
  buildDefaultDashboardCapabilities,
  type CurrentUser,
  type DashboardActionCapabilityKey,
  type DashboardPageCapabilityKey,
  type UserRole,
} from "@/lib/auth";
import { hasActionCapability, hasPageCapability } from "@/lib/capabilities";

export const DASHBOARD_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR", "ANALYST"];
export const ALERT_TRIGGER_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const CHV_DIRECTORY_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const SYSTEM_PAGE_ROLES: UserRole[] = ["ADMIN", "ANALYST"];
export const PREPAREDNESS_ACTION_MANAGER_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const SENSITIVE_EXPORT_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR"];
export const MESSAGE_GOVERNANCE_ROLES: UserRole[] = ["ADMIN", "SUPERVISOR", "ANALYST"];
export const CHV_OFFLINE_ROLES: UserRole[] = ["CHV"];

type RoleSubject = CurrentUser | UserRole | null | undefined;

function isCurrentUser(subject: RoleSubject): subject is CurrentUser {
  return Boolean(subject && typeof subject === "object" && "role" in subject);
}

function roleForSubject(subject: RoleSubject): UserRole | null {
  if (!subject) {
    return null;
  }

  return isCurrentUser(subject) ? subject.role : subject;
}

function fallbackUserForRole(role: UserRole): CurrentUser {
  return {
    id: 0,
    username: "legacy-capability-user",
    email: "",
    full_name: "",
    phone_number: null,
    role,
    theme_preference: "SYSTEM",
    ward: null,
    ward_name: null,
    is_active: true,
    dashboard_capabilities: buildDefaultDashboardCapabilities({
      role,
      ward: null,
      scope_type: role === "ADMIN" || role === "ANALYST" ? "BROAD" : "NONE",
      scope_ward_id: null,
      two_factor_policy: undefined,
    }),
  };
}

function subjectHasPageCapability(subject: RoleSubject, pageKey: DashboardPageCapabilityKey) {
  if (isCurrentUser(subject)) {
    return hasPageCapability(subject, pageKey);
  }

  const role = roleForSubject(subject);
  return role ? hasPageCapability(fallbackUserForRole(role), pageKey) : false;
}

function subjectHasActionCapability(subject: RoleSubject, actionKey: DashboardActionCapabilityKey) {
  if (isCurrentUser(subject)) {
    return hasActionCapability(subject, actionKey);
  }

  const role = roleForSubject(subject);
  return role ? hasActionCapability(fallbackUserForRole(role), actionKey) : false;
}

export function hasRole(role: UserRole | null | undefined, allowedRoles: UserRole[]) {
  return !!role && allowedRoles.includes(role);
}

export function isDashboardRole(subject: RoleSubject) {
  return subjectHasPageCapability(subject, "dashboard");
}

export function canUseChvOffline(role: UserRole | null | undefined) {
  return hasRole(role, CHV_OFFLINE_ROLES);
}

export function canTriggerAlerts(subject: RoleSubject) {
  return subjectHasActionCapability(subject, "trigger_alerts");
}

export function canManagePreparednessActions(subject: RoleSubject) {
  return subjectHasActionCapability(subject, "manage_preparedness_actions");
}

export function canViewChvs(subject: RoleSubject) {
  return subjectHasPageCapability(subject, "chv_operations");
}

export function canViewSystem(subject: RoleSubject) {
  return subjectHasPageCapability(subject, "system");
}

export function canExportSensitiveReports(subject: RoleSubject) {
  return subjectHasActionCapability(subject, "request_sensitive_exports");
}

export function canApproveMessageTemplates(subject: RoleSubject) {
  return subjectHasActionCapability(subject, "approve_message_governance");
}
