import { Eye, type LucideIcon } from "lucide-react";

import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
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
    <div className="stack">
      <header className="page-header">
        <div>
          <p className="eyebrow">Operational Dashboard</p>
          <h2>{title}</h2>
          <p className="subtitle">{summary}</p>
        </div>
        <div className="inline-actions">
          <span className="role-pill">{role}</span>
          {canTriggerAlerts(role) ? (
            <TriggerAlertPanel />
          ) : (
            <div className="status status-warning">
              <ActionIcon className="section-icon" aria-hidden="true" />
              Read-only access for this role.
            </div>
          )}
        </div>
      </header>
      {children}
    </div>
  );
}
