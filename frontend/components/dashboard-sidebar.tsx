"use client";

import Image from "next/image";
import { ChevronDown, LogOut, UserCircle2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { CurrentUser } from "@/lib/auth";
import { getVisibleNavGroups, type NavItem } from "@/lib/navigation";

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

  const navGroups = getVisibleNavGroups(currentUser.role);

  function isItemActive(item: NavItem) {
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  }

  function renderNavLink(item: NavItem) {
    const Icon = item.icon;
    const isActive = isItemActive(item);

    return (
      <Link
        key={item.href}
        href={item.href}
        className={cn(
          "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition max-[960px]:shrink-0 max-[960px]:rounded-full max-[960px]:px-3 max-[960px]:py-2 max-[960px]:text-xs",
          isActive
            ? "bg-[var(--dashboard-nav-active-surface)] text-[var(--dashboard-sidebar-title)] shadow-[var(--dashboard-nav-active-shadow)]"
            : "text-[var(--dashboard-sidebar-text)] hover:bg-[var(--dashboard-nav-hover)] hover:text-[var(--dashboard-sidebar-title)]",
        )}
      >
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        <span>{item.label}</span>
      </Link>
    );
  }

  return (
    <aside className="sticky top-0 grid h-screen grid-rows-[auto_minmax(0,1fr)] overflow-hidden border-r border-[var(--dashboard-sidebar-border)] bg-[var(--dashboard-sidebar-surface)] px-4 pt-5 backdrop-blur md:px-[0.9rem] md:pt-[1.15rem] max-[960px]:static max-[960px]:flex max-[960px]:h-auto max-[960px]:w-full max-[960px]:min-w-0 max-[960px]:flex-col max-[960px]:gap-3 max-[960px]:overflow-hidden max-[960px]:border-b max-[960px]:border-r-0 max-[960px]:px-4 max-[960px]:pb-3 max-[960px]:pt-4">
      <div className="col-start-1 row-start-1 flex items-center gap-4 px-2 py-1 max-[960px]:px-0 max-[960px]:py-0">
        <Image
          src="/brand/chis-brief-colored.svg"
          alt="CHIS logo"
          width={40}
          height={40}
          className="h-[2.9rem] w-[2.9rem] shrink-0 max-[960px]:h-10 max-[960px]:w-10"
        />
        <div className="grid gap-0.5">
          <strong className="text-[1.2rem] font-semibold leading-[1.05] tracking-[-0.04em] text-[var(--dashboard-sidebar-title)] max-[960px]:text-base max-[960px]:tracking-[0]">
            Migori County
          </strong>
          <span className="text-[0.68rem] font-bold uppercase tracking-[0.06em] text-[var(--dashboard-sidebar-subtitle)] max-[960px]:text-[0.58rem]">
            Climate Health Intelligence System
          </span>
        </div>
      </div>

      <div className="col-start-1 row-start-2 min-h-0 overflow-y-auto overscroll-contain pb-44 pr-1 pt-5 [scrollbar-color:color-mix(in_srgb,var(--dashboard-sidebar-border)_82%,transparent)_transparent] [scrollbar-width:thin] max-[960px]:w-full max-[960px]:min-w-0 max-[960px]:overflow-x-auto max-[960px]:overflow-y-hidden max-[960px]:pb-1 max-[960px]:pr-0 max-[960px]:pt-0">
        <nav className="grid content-start gap-4 max-[960px]:flex max-[960px]:w-max max-[960px]:items-center max-[960px]:gap-2" aria-label="Primary navigation">
          {navGroups.map((group) => {
            const isGroupActive = group.items.some((item) => isItemActive(item));

            if (group.collapsible) {
              return (
                <details
                  key={group.id}
                  className="group/sidebar grid gap-1.5 max-[960px]:grid-flow-col max-[960px]:items-center max-[960px]:gap-2"
                  open={isGroupActive ? true : undefined}
                >
                  <summary
                    className={cn(
                      "flex cursor-pointer list-none items-center justify-between gap-3 rounded-2xl px-4 py-2 text-xs font-bold uppercase tracking-[0.12em] transition marker:hidden max-[960px]:rounded-full max-[960px]:px-3 max-[960px]:py-2",
                      isGroupActive
                        ? "bg-[var(--dashboard-nav-active-surface)] text-[var(--dashboard-sidebar-title)]"
                        : "text-[var(--dashboard-sidebar-muted)] hover:bg-[var(--dashboard-nav-hover)] hover:text-[var(--dashboard-sidebar-title)]",
                    )}
                  >
                    <span>{group.label}</span>
                    <ChevronDown className="size-3.5 transition group-open/sidebar:rotate-180" aria-hidden="true" />
                  </summary>
                  <div className="grid gap-1.5 max-[960px]:contents">
                    {group.items.map((item) => renderNavLink(item))}
                  </div>
                </details>
              );
            }

            return (
              <section key={group.id} className="grid gap-1.5 max-[960px]:contents" aria-label={group.label}>
                <h2 className="px-4 text-xs font-bold uppercase tracking-[0.12em] text-[var(--dashboard-sidebar-muted)] max-[960px]:hidden">
                  {group.label}
                </h2>
                {group.items.map((item) => renderNavLink(item))}
              </section>
            );
          })}
        </nav>
      </div>

      <div className="sticky bottom-0 z-20 col-start-1 row-start-2 self-end -mx-4 grid gap-3 border-t border-[var(--dashboard-sidebar-border)] bg-[var(--dashboard-sidebar-surface)] px-4 pb-4 pt-4 shadow-[0_-18px_28px_rgba(15,23,42,0.08)] backdrop-blur md:-mx-[0.9rem] md:px-[0.9rem] max-[960px]:hidden">
        <Link
          href="/profile"
          className="group flex cursor-pointer items-center gap-3 rounded-2xl px-2 py-1 transition hover:bg-[var(--dashboard-nav-hover)]"
          aria-label="Open profile summary"
        >
          <div
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-[var(--dashboard-sidebar-icon-surface)] text-[var(--dashboard-sidebar-icon-ink)] transition group-hover:text-[var(--dashboard-sidebar-title)]"
            aria-hidden="true"
          >
            <UserCircle2 className="size-5" />
          </div>
          <div className="grid min-w-0 gap-0.5">
            <strong className="truncate text-sm font-semibold text-[var(--dashboard-sidebar-text-strong)]">
              {currentUser.full_name || currentUser.username}
            </strong>
            <span className="truncate text-xs text-[var(--dashboard-sidebar-muted)]">{currentUser.role}</span>
            <span className="truncate text-xs text-[var(--dashboard-sidebar-muted)]">
              {getSidebarScopeLabel(currentUser)}
            </span>
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
      </div>
    </aside>
  );
}
