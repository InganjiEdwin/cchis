"use client";

import Image from "next/image";
import { LogOut, UserCircle2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { CurrentUser } from "@/lib/auth";
import { getVisibleNav } from "@/lib/navigation";

function getSidebarScopeLabel(user: CurrentUser) {
  if (user.scope_type === "BROAD") {
    return "Migori County";
  }

  if (user.scope_type === "WARD") {
    return user.ward_name || "Ward-scoped access";
  }

  return user.ward_name || "No scope assigned";
}

export function DashboardSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { currentUser, logout } = useAuth();

  if (!currentUser) {
    return null;
  }

  const navItems = getVisibleNav(currentUser.role);

  return (
    <aside className="sticky top-0 grid h-screen grid-rows-[auto_1fr_auto_auto] gap-5 border-r border-[var(--dashboard-sidebar-border)] bg-[var(--dashboard-sidebar-surface)] px-4 pb-4 pt-5 backdrop-blur md:px-[0.9rem] md:pt-[1.15rem] max-[960px]:static max-[960px]:h-auto max-[960px]:border-b max-[960px]:border-r-0">
      <div className="flex items-center gap-4 px-2 py-1">
        <Image
          src="/brand/chis-brief-colored.svg"
          alt="CHIS logo"
          width={40}
          height={40}
          className="h-[2.9rem] w-[2.9rem] shrink-0"
        />
        <div className="grid gap-0.5">
          <strong className="text-[1.2rem] font-semibold leading-[1.05] tracking-[-0.04em] text-[var(--dashboard-sidebar-title)]">
            Migori County
          </strong>
          <span className="text-[0.68rem] font-bold uppercase tracking-[0.06em] text-[var(--dashboard-sidebar-subtitle)]">
            Climate Health Intelligence System
          </span>
        </div>
      </div>

      <nav className="grid content-start gap-1.5" aria-label="Primary navigation">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition",
                isActive
                  ? "bg-[var(--dashboard-nav-active-surface)] text-[var(--dashboard-sidebar-title)] shadow-[var(--dashboard-nav-active-shadow)]"
                  : "text-[var(--dashboard-sidebar-text)] hover:bg-[var(--dashboard-nav-hover)] hover:text-[var(--dashboard-sidebar-title)]",
              )}
            >
              <Icon className="size-4 shrink-0" aria-hidden="true" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <Link
        href="/profile"
        className="group flex cursor-pointer items-center gap-3 rounded-2xl border-t border-[var(--dashboard-sidebar-border)] px-2 pb-0 pt-4 transition hover:bg-[var(--dashboard-nav-hover)]"
        aria-label="Open profile summary"
      >
        <div
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-[var(--dashboard-sidebar-icon-surface)] text-[var(--dashboard-sidebar-icon-ink)] transition group-hover:text-[var(--dashboard-sidebar-title)]"
          aria-hidden="true"
        >
          <UserCircle2 className="size-5" />
        </div>
        <div className="grid gap-0.5">
          <strong className="text-sm font-semibold text-[var(--dashboard-sidebar-text-strong)]">
            {currentUser.full_name || currentUser.username}
          </strong>
          <span className="text-xs text-[var(--dashboard-sidebar-muted)]">{currentUser.role}</span>
          <span className="text-xs text-[var(--dashboard-sidebar-muted)]">{getSidebarScopeLabel(currentUser)}</span>
        </div>
      </Link>

      <Button
        variant="secondary"
        size="md"
        className="w-full justify-center gap-2 rounded-2xl border-[var(--dashboard-sidebar-border)] bg-[var(--dashboard-nav-active-surface)] font-bold text-[var(--dashboard-sidebar-text)] hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-sidebar-title)]"
        onClick={() => {
          void logout().then(() => router.replace("/login"));
        }}
      >
        <LogOut className="size-4" aria-hidden="true" />
        Sign out
      </Button>
    </aside>
  );
}
