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

import type { UserRole } from "@/lib/auth";
import { canUseChvOffline, canViewChvs, canViewSystem, hasRole } from "@/lib/roles";

export type NavGroupId = "operate" | "response_capacity" | "measure" | "data_admin";

export type NavGroup = {
  id: NavGroupId;
  label: string;
  collapsible?: boolean;
};

export type NavItem = {
  label: string;
  href: string;
  roles: UserRole[];
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
  { label: "Overview", href: "/overview", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: LayoutGrid, group: "operate" },
  { label: "Ward Decisions", href: "/wards", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Map, group: "operate" },
  { label: "Alerts", href: "/alerts", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Bell, group: "operate" },
  { label: "Response Tasks", href: "/preparedness-actions", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: ClipboardList, group: "operate" },
  { label: "CHV Operations", href: "/chvs", roles: ["ADMIN", "SUPERVISOR"], icon: Stethoscope, group: "response_capacity" },
  { label: "Facility Readiness", href: "/facility-readiness", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Building2, group: "response_capacity" },
  { label: "Metrics", href: "/operational-metrics", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: BarChart3, group: "measure" },
  { label: "Data Readiness", href: "/source-data", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Database, group: "data_admin" },
  { label: "Communication Review", href: "/message-governance", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: MessageSquareText, group: "data_admin" },
  { label: "Forecast Readiness", href: "/model-health", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Activity, group: "data_admin" },
  { label: "Data Connections", href: "/interoperability", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Network, group: "data_admin" },
  { label: "Operations Readiness", href: "/system", roles: ["ADMIN", "ANALYST"], icon: ShieldCheck, group: "data_admin" },
];

export function getVisibleNav(role: UserRole) {
  return NAV_ITEMS.filter((item) => hasRole(role, item.roles));
}

export function getVisibleNavGroups(role: UserRole) {
  const visibleNav = getVisibleNav(role);

  return NAV_GROUPS.map((group) => ({
    ...group,
    items: visibleNav.filter((item) => item.group === group.id),
  })).filter((group) => group.items.length > 0);
}

export function getDefaultRoute(role: UserRole) {
  if (canUseChvOffline(role)) {
    return "/chv";
  }

  if (canViewSystem(role) && role === "ANALYST") {
    return "/overview";
  }

  if (canViewChvs(role) || role === "ANALYST") {
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
