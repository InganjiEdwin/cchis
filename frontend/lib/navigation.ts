import {
  Activity,
  BarChart3,
  Bell,
  Building2,
  ClipboardList,
  LayoutGrid,
  Map,
  MessageSquareText,
  Network,
  ShieldCheck,
  Stethoscope,
  UserCircle2,
  type LucideIcon,
} from "lucide-react";

import type { UserRole } from "@/lib/auth";
import { canUseChvOffline, canViewChvs, canViewSystem, hasRole } from "@/lib/roles";

export type NavItem = {
  label: string;
  href: string;
  roles: UserRole[];
  icon: LucideIcon;
};

export const NAV_ITEMS: NavItem[] = [
  { label: "Early Warning & Action", href: "/overview", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: LayoutGrid },
  { label: "Ward Intelligence", href: "/wards", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Map },
  { label: "Alerts", href: "/alerts", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Bell },
  { label: "Action Queue", href: "/preparedness-actions", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: ClipboardList },
  { label: "Message Governance", href: "/message-governance", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: MessageSquareText },
  { label: "Model Health", href: "/model-health", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Activity },
  { label: "Operational KPIs", href: "/operational-metrics", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: BarChart3 },
  { label: "Interoperability", href: "/interoperability", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Network },
  { label: "CHV Operations", href: "/chvs", roles: ["ADMIN", "SUPERVISOR"], icon: Stethoscope },
  { label: "Facility Readiness", href: "/facility-readiness", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Building2 },
  { label: "System Summary", href: "/system", roles: ["ADMIN", "ANALYST"], icon: ShieldCheck },
  { label: "Profile", href: "/profile", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: UserCircle2 },
];

export function getVisibleNav(role: UserRole) {
  return NAV_ITEMS.filter((item) => hasRole(role, item.roles));
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
