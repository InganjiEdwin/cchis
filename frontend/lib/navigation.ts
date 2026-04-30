import {
  Activity,
  Bell,
  Building2,
  LayoutGrid,
  Map,
  ShieldCheck,
  Stethoscope,
  UserCircle2,
  type LucideIcon,
} from "lucide-react";

import type { UserRole } from "@/lib/auth";
import { canViewChvs, canViewSystem, hasRole } from "@/lib/roles";

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
  { label: "CHV Operations", href: "/chvs", roles: ["ADMIN", "SUPERVISOR"], icon: Stethoscope },
  { label: "Facility Readiness", href: "/facility-readiness", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: Building2 },
  { label: "System Summary", href: "/system", roles: ["ADMIN", "ANALYST"], icon: ShieldCheck },
  { label: "Profile", href: "/profile", roles: ["ADMIN", "SUPERVISOR", "ANALYST"], icon: UserCircle2 },
];

export function getVisibleNav(role: UserRole) {
  return NAV_ITEMS.filter((item) => hasRole(role, item.roles));
}

export function getDefaultRoute(role: UserRole) {
  if (canViewSystem(role) && role === "ANALYST") {
    return "/overview";
  }

  if (canViewChvs(role) || role === "ANALYST") {
    return "/overview";
  }

  return "/unauthorized";
}
