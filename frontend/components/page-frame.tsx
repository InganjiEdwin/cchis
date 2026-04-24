import { Eye, type LucideIcon } from "lucide-react";

import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import { Card } from "@/components/ui/card";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge } from "@/components/ui/status-badge";
import type { UserRole } from "@/lib/auth";
import { canTriggerAlerts } from "@/lib/roles";

type PageFrameProps = {
  title: string;
  summary: string;
  role: UserRole;
  children?: React.ReactNode;
};

export function PageFrame({ title, summary, role, children }: PageFrameProps) {
  const ActionIcon: LucideIcon = Eye;

  return (
    <div className="space-y-6">
      <PageSectionHeader
        title={title}
        description={summary}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge tone="info" className="rounded-full px-3 py-1.5 tracking-[0.14em]">
              {role}
            </StatusBadge>
            {canTriggerAlerts(role) ? (
              <TriggerAlertPanel
                buttonClassName="inline-flex h-11 items-center justify-center gap-2 rounded-pill bg-[var(--login-submit-start)] px-4 text-sm font-semibold text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
              />
            ) : (
              <Card className="flex items-center gap-2 rounded-2xl px-4 py-2.5 shadow-none">
                <ActionIcon className="size-4 text-[color:var(--warning)]" aria-hidden="true" />
                <span className="text-sm font-medium text-panel-copy">Read-only access for this role.</span>
              </Card>
            )}
          </div>
        }
      />
      {children}
    </div>
  );
}
