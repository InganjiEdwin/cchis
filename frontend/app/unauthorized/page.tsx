import { ShieldBan } from "lucide-react";
import Link from "next/link";

import { PublicCard, PublicFooter, PublicScreen, PublicShell, PublicTopbar } from "@/components/ui/public-shell";

export default function UnauthorizedPage() {
  return (
    <PublicScreen className="bg-[var(--forgot-background)]">
      <PublicTopbar />
      <PublicShell narrow className="justify-center">
        <PublicCard className="max-w-[640px] text-center">
          <div className="mx-auto mb-5 inline-flex size-16 items-center justify-center rounded-[1.5rem] bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)]">
            <ShieldBan className="size-8" aria-hidden="true" />
          </div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-panel-muted">Access Restricted</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-panel-strong">
            This dashboard role is not enabled here
          </h1>
          <p className="mt-3 text-base text-panel-copy">
            The current web dashboard is intended for Admin, Supervisor, and Analyst roles. CHV workflows remain field-focused and should not be forced into the dashboard shell.
          </p>
          <div className="mt-5 rounded-2xl border border-[color-mix(in_srgb,var(--warning)_28%,white)] bg-[color-mix(in_srgb,var(--warning)_10%,white)] px-4 py-3 text-sm text-[color:var(--warning)]">
            Backend permissions remain the source of truth, and this screen simply reflects the current frontend scope.
          </div>
          <Link
            className="mt-6 inline-flex items-center justify-center rounded-pill bg-[var(--login-submit-start)] px-5 py-3 text-sm font-semibold text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)]"
            href="/login"
          >
            Return to login
          </Link>
        </PublicCard>
        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
