"use client";

import Image from "next/image";
import { LogOut, UserCircle2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { getVisibleNav } from "@/lib/navigation";

export function DashboardSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { currentUser, logout } = useAuth();

  if (!currentUser) {
    return null;
  }

  const navItems = getVisibleNav(currentUser.role);

  return (
    <aside className="dashboard-sidebar">
      <div className="dashboard-sidebar-brand">
        <Image
          src="/brand/chis-brief-colored.svg"
          alt="CHIS logo"
          width={40}
          height={40}
          className="dashboard-brand-logo"
        />
        <div className="dashboard-brand-copy">
          <strong>Migori County</strong>
          <span>Climate Health Intelligence System</span>
        </div>
      </div>

      <nav className="dashboard-sidebar-nav" aria-label="Primary navigation">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`dashboard-nav-item${isActive ? " dashboard-nav-item-active" : ""}`}
            >
              <Icon className="section-icon" aria-hidden="true" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="dashboard-sidebar-user">
        <div className="dashboard-sidebar-user-icon" aria-hidden="true">
          <UserCircle2 />
        </div>
        <div className="dashboard-sidebar-user-copy">
          <strong>{currentUser.full_name || currentUser.username}</strong>
          <span>{currentUser.role}</span>
          <span>{currentUser.ward_name ?? "County-wide access"}</span>
        </div>
      </div>

      <button
        type="button"
        className="dashboard-signout"
        onClick={() => {
          void logout().then(() => router.replace("/login"));
        }}
      >
        <LogOut className="section-icon" aria-hidden="true" />
        Sign out
      </button>
    </aside>
  );
}
