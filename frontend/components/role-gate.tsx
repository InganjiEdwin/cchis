"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { Card } from "@/components/ui/card";
import type { UserRole } from "@/lib/auth";
import { hasRole } from "@/lib/roles";

type RoleGateProps = {
  allowedRoles: UserRole[];
  title: string;
  message: string;
  children: React.ReactNode;
};

export function RoleGate({ allowedRoles, title, message, children }: RoleGateProps) {
  const { currentUser } = useAuth();

  if (!currentUser) {
    return null;
  }

  if (hasRole(currentUser.role, allowedRoles)) {
    return <>{children}</>;
  }

  return (
    <section className="grid gap-6">
      <Card className="max-w-3xl p-6 md:p-8">
        <h3 className="text-2xl font-semibold tracking-[-0.03em] text-panel-strong">{title}</h3>
        <p className="mt-3 text-sm leading-6 text-panel-muted">{message}</p>
        <div className="mt-4 rounded-2xl border border-[color-mix(in_srgb,var(--warning)_24%,white)] bg-[color-mix(in_srgb,var(--warning)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--warning)]">
          This route exists, but your current role does not have access to it.
        </div>
        <div className="mt-4">
          <Link
            href="/overview"
            className="inline-flex h-11 items-center justify-center rounded-pill bg-[var(--login-submit-start)] px-4 text-sm font-semibold text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
          >
            Return to Overview
          </Link>
        </div>
      </Card>
    </section>
  );
}
