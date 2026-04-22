"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardFooter } from "@/components/dashboard-footer";
import { DashboardSidebar } from "@/components/dashboard-sidebar";
import { isDashboardRole } from "@/lib/roles";

export function ProtectedShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { currentUser, isAuthenticated, isHydrating } = useAuth();

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

  if (isHydrating || !currentUser) {
    return (
      <div className="auth-shell">
      <div className="auth-card">
          <p className="eyebrow">CHIS Dashboard</p>
          <h1 className="title">Restoring your session</h1>
          <p className="subtitle">
            Checking your current access scope before we render the operational dashboard.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-shell">
      <DashboardSidebar />
      <div className="dashboard-stage">
        <main className="dashboard-main">{children}</main>
        <DashboardFooter />
      </div>
    </div>
  );
}
