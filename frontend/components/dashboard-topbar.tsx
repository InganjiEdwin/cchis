"use client";

import { Bell, RefreshCcw } from "lucide-react";

type DashboardTopbarProps = {
  title: string;
  subtitle: string;
  lastUpdatedLabel?: string;
  onRefresh?: () => void;
  children?: React.ReactNode;
};

export function DashboardTopbar({
  title,
  subtitle,
  lastUpdatedLabel,
  onRefresh,
  children,
}: DashboardTopbarProps) {
  return (
    <header className="dashboard-topbar">
      <div className="dashboard-topbar-copy">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>

      <div className="dashboard-topbar-actions">
        {lastUpdatedLabel ? (
          <div className="dashboard-topbar-status">
            <span className="dashboard-topbar-status-dot" aria-hidden="true" />
            <span>Last updated: {lastUpdatedLabel}</span>
          </div>
        ) : null}

        <button
          type="button"
          className="dashboard-icon-button"
          onClick={onRefresh}
          aria-label="Refresh dashboard"
        >
          <RefreshCcw aria-hidden="true" />
        </button>

        <button type="button" className="dashboard-icon-button" aria-label="Notifications">
          <Bell aria-hidden="true" />
        </button>

        {children}
      </div>
    </header>
  );
}
