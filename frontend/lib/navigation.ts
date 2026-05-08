import {
  Activity,
  BarChart3,
  Bell,
  Building2,
  ClipboardList,
  Database,
  LayoutGrid,
  Map,
  MessageSquareText,
  Network,
  ShieldCheck,
  Stethoscope,
  type LucideIcon,
} from "lucide-react";

import type { CurrentUser, DashboardPageCapabilityKey, UserRole } from "@/lib/auth";
import { hasPageCapability } from "@/lib/capabilities";
import { canUseChvOffline } from "@/lib/roles";

export type NavGroupId = "operate" | "response_capacity" | "measure" | "data_admin";

export type NavGroup = {
  id: NavGroupId;
  label: string;
  collapsible?: boolean;
};

export type NavItem = {
  label: string;
  href: string;
  pageCapability: DashboardPageCapabilityKey;
  icon: LucideIcon;
  group: NavGroupId;
};

export const NAV_GROUPS: NavGroup[] = [
  { id: "operate", label: "Operate" },
  { id: "response_capacity", label: "Response Capacity" },
  { id: "measure", label: "Measure" },
  { id: "data_admin", label: "Data & Admin", collapsible: true },
];

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/overview", pageCapability: "overview", icon: LayoutGrid, group: "operate" },
  { label: "Ward Decisions", href: "/wards", pageCapability: "wards", icon: Map, group: "operate" },
  { label: "Alerts", href: "/alerts", pageCapability: "alerts", icon: Bell, group: "operate" },
  { label: "Response Tasks", href: "/preparedness-actions", pageCapability: "preparedness_actions", icon: ClipboardList, group: "operate" },
  { label: "CHV Operations", href: "/chvs", pageCapability: "chv_operations", icon: Stethoscope, group: "response_capacity" },
  { label: "Facility Readiness", href: "/facility-readiness", pageCapability: "facility_readiness", icon: Building2, group: "response_capacity" },
  { label: "Metrics", href: "/operational-metrics", pageCapability: "operational_metrics", icon: BarChart3, group: "measure" },
  { label: "Data Readiness", href: "/source-data", pageCapability: "source_data", icon: Database, group: "data_admin" },
  { label: "Communication Review", href: "/message-governance", pageCapability: "message_governance", icon: MessageSquareText, group: "data_admin" },
  { label: "Forecast Readiness", href: "/model-health", pageCapability: "model_health", icon: Activity, group: "data_admin" },
  { label: "Data Connections", href: "/interoperability", pageCapability: "interoperability", icon: Network, group: "data_admin" },
  { label: "Operations Readiness", href: "/system", pageCapability: "system", icon: ShieldCheck, group: "data_admin" },
];

type NavSubject = CurrentUser | UserRole;

function userFromRole(role: UserRole): CurrentUser {
  return {
    id: 0,
    username: "legacy-nav-user",
    email: "",
    full_name: "",
    phone_number: null,
    role,
    theme_preference: "SYSTEM",
    ward: null,
    ward_name: null,
    is_active: true,
  };
}

function normalizeNavSubject(subject: NavSubject): CurrentUser {
  return typeof subject === "string" ? userFromRole(subject) : subject;
}

export function getVisibleNav(subject: NavSubject) {
  const user = normalizeNavSubject(subject);
  return NAV_ITEMS.filter((item) => hasPageCapability(user, item.pageCapability));
}

export function getVisibleNavGroups(subject: NavSubject) {
  const visibleNav = getVisibleNav(subject);

  return NAV_GROUPS.map((group) => ({
    ...group,
    items: visibleNav.filter((item) => item.group === group.id),
  })).filter((group) => group.items.length > 0);
}

export function getDefaultRoute(subject: NavSubject) {
  const user = normalizeNavSubject(subject);
  if (canUseChvOffline(user.role)) {
    return "/chv";
  }

  if (hasPageCapability(user, "overview")) {
    return "/overview";
  }

  return "/unauthorized";
}

export function getSafePolicyReturnTo(value: string | null | undefined, fallback = "/overview") {
  const trimmedValue = value?.trim();

  if (!trimmedValue || !trimmedValue.startsWith("/") || trimmedValue.startsWith("//")) {
    return fallback;
  }

  let parsed: URL;

  try {
    parsed = new URL(trimmedValue, "https://cchis.local");
  } catch {
    return fallback;
  }

  if (parsed.origin !== "https://cchis.local") {
    return fallback;
  }

  const safePath = `${parsed.pathname}${parsed.search}${parsed.hash}`;
  const blockedPaths = ["/login", "/policy-review", "/terms", "/privacy"];

  if (blockedPaths.some((path) => safePath === path || safePath.startsWith(`${path}?`) || safePath.startsWith(`${path}#`))) {
    return fallback;
  }

  return safePath;
}

export function buildPolicyReviewRoute(returnTo: string | null | undefined, fallback = "/overview") {
  const safeReturnTo = getSafePolicyReturnTo(returnTo, fallback);
  const params = new URLSearchParams({ returnTo: safeReturnTo });
  return `/policy-review?${params.toString()}`;
}
