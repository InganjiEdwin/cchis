"use client";

import { ShieldAlert, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardFooter } from "@/components/dashboard-footer";
import { DashboardSidebar } from "@/components/dashboard-sidebar";
import { StatusBanner } from "@/components/ui/status-banner";
import { PublicCard, PublicScreen, PublicShell } from "@/components/ui/public-shell";
import {
  clearRecoveryCodeLoginNotice,
  readRecoveryCodeLoginNotice,
  type RecoveryCodeLoginNotice,
} from "@/lib/auth";
import { buildPolicyReviewRoute } from "@/lib/navigation";
import { isDashboardRole } from "@/lib/roles";

function RecoveryCodeLoginNoticeBanner() {
  const [notice, setNotice] = useState<RecoveryCodeLoginNotice | null>(null);

  useEffect(() => {
    const pendingNotice = readRecoveryCodeLoginNotice();
    if (!pendingNotice) {
      return;
    }

    setNotice(pendingNotice);
    clearRecoveryCodeLoginNotice();
  }, []);

  if (!notice) {
    return null;
  }

  return (
    <StatusBanner
      tone="warning"
      icon={<ShieldAlert aria-hidden="true" />}
      className="mb-4"
      role="status"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-semibold">Recovery codes are running low.</p>
          <p className="mt-1 text-sm">
            {notice.remaining_count} recovery {notice.remaining_count === 1 ? "code remains" : "codes remain"}. Generate a fresh set from Profile.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link href="/profile" className="inline-flex h-9 items-center rounded-pill border border-current/25 px-3 text-sm font-semibold">
            Manage codes
          </Link>
          <button
            type="button"
            aria-label="Dismiss recovery-code warning"
            onClick={() => setNotice(null)}
            className="inline-flex size-9 items-center justify-center rounded-full border border-current/25"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </StatusBanner>
  );
}

export function ProtectedShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { currentUser, isAuthenticated, isHydrating, requiresPolicyAcceptance } = useAuth();
  const isDashboardUser = currentUser ? isDashboardRole(currentUser.role) : false;
  const search = searchParams.toString();
  const currentPath = search ? `${pathname}?${search}` : pathname;

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
      return;
    }

    if (requiresPolicyAcceptance) {
      router.replace(buildPolicyReviewRoute(currentPath));
    }
  }, [currentPath, currentUser, isAuthenticated, isHydrating, requiresPolicyAcceptance, router]);

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

  if (!isAuthenticated || !currentUser || !isDashboardUser || requiresPolicyAcceptance) {
    return null;
  }

  return (
    <div className="grid min-h-screen bg-app-bg text-panel-copy md:grid-cols-[260px_minmax(0,1fr)]">
      <DashboardSidebar />
      <div className="grid min-w-0 grid-rows-[1fr_auto]">
        <main className="min-w-0 px-[1.4rem] pb-[1.1rem] max-[640px]:px-4 max-[640px]:pb-4">
          <RecoveryCodeLoginNoticeBanner />
          {children}
        </main>
        <DashboardFooter />
      </div>
    </div>
  );
}
