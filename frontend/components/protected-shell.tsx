"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardFooter } from "@/components/dashboard-footer";
import { DashboardSidebar } from "@/components/dashboard-sidebar";
import { PublicCard, PublicScreen, PublicShell } from "@/components/ui/public-shell";
import { isDashboardRole } from "@/lib/roles";

export function ProtectedShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { currentUser, isAuthenticated, isHydrating } = useAuth();
  const isDashboardUser = currentUser ? isDashboardRole(currentUser.role) : false;

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }

    if (!currentUser || !isDashboardRole(currentUser.role)) {
      router.replace("/unauthorized");
    }
  }, [currentUser, isAuthenticated, isHydrating, router]);

  if (isHydrating) {
    return (
      <PublicScreen>
        <PublicShell narrow className="justify-center">
          <PublicCard className="max-w-2xl">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--login-description)]">
              CHIS Dashboard
            </p>
            <h1 className="text-balance text-4xl font-semibold tracking-[-0.04em] text-[var(--totp-ink)]">
              Restoring your session
            </h1>
            <p className="mt-4 text-sm leading-6 text-[var(--login-description)]">
              Checking your current access scope before we render the operational dashboard.
            </p>
          </PublicCard>
        </PublicShell>
      </PublicScreen>
    );
  }

  if (!isAuthenticated || !currentUser || !isDashboardUser) {
    return null;
  }

  return (
    <div className="grid min-h-screen bg-app-bg text-panel-copy md:grid-cols-[260px_minmax(0,1fr)]">
      <DashboardSidebar />
      <div className="grid min-w-0 grid-rows-[1fr_auto]">
        <main className="min-w-0 px-[1.4rem] pb-[1.1rem] max-[640px]:px-4 max-[640px]:pb-4">{children}</main>
        <DashboardFooter />
      </div>
    </div>
  );
}
