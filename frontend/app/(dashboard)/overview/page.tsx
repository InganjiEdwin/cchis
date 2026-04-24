"use client";

import { AlertTriangle, ArrowRight, Bell, CircleAlert, MapPin, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import { Card } from "@/components/ui/card";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge } from "@/components/ui/status-badge";
import type { AlertRecord } from "@/lib/dashboard";
import { useOverviewQuery } from "@/queries/use-overview-query";

function formatStatusLabel(status: AlertRecord["status"]) {
  return status
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatChannelLabel(channel: AlertRecord["channel"]) {
  if (channel === "DASHBOARD") {
    return "System";
  }
  return channel;
}

function normalizeRiskScore(score: number) {
  if (!Number.isFinite(score)) {
    return 0;
  }
  if (score <= 1) {
    return Math.max(0, Math.min(score * 100, 100));
  }
  return Math.max(0, Math.min(score, 100));
}

function formatRiskScore(score: number) {
  if (!Number.isFinite(score)) {
    return "N/A";
  }
  return Math.round(normalizeRiskScore(score)).toString();
}

function formatCompactRelativeMinutes(timestamp: string | null) {
  if (!timestamp) {
    return "No recent update";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const diffMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));

  if (diffMinutes < 1) return "Just now";
  if (diffMinutes === 1) return "1 min ago";
  if (diffMinutes < 60) return `${diffMinutes} min ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours === 1) return "1 hr ago";
  if (diffHours < 24) return `${diffHours} hr ago`;

  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} d ago`;
}

function formatOperationalTime(timestamp: string | null) {
  if (!timestamp) {
    return "No timestamp";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const timeLabel = date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return `${timeLabel} (${formatCompactRelativeMinutes(timestamp)})`;
}

function getScoreTone(score: number) {
  const normalizedScore = normalizeRiskScore(score);

  if (normalizedScore >= 80)
    return "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_20%,transparent)]";
  if (normalizedScore >= 65)
    return "bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_16%,transparent)]";
  if (normalizedScore >= 45)
    return "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]";
  if (normalizedScore >= 25)
    return "bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]";
  return "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]";
}

function getRiskBadgeTone(level: "LOW" | "MEDIUM" | "HIGH" | null) {
  if (level === "HIGH") return "danger" as const;
  if (level === "MEDIUM") return "warning" as const;
  return "success" as const;
}

function getAttentionCardClass(level: "LOW" | "MEDIUM" | "HIGH" | null, isPrimary: boolean) {
  const base = "space-y-3 rounded-[1.5rem] p-4 shadow-none";

  if (level === "HIGH") {
    return `${base} border-[color-mix(in_srgb,var(--danger)_22%,white)] bg-[color-mix(in_srgb,var(--danger)_8%,white)] dark:border-[color-mix(in_srgb,var(--danger)_28%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_14%,transparent)]${isPrimary ? " ring-1 ring-[color:var(--danger)]/15 dark:ring-[color:var(--danger)]/25" : ""}`;
  }

  if (level === "MEDIUM") {
    return `${base} border-[color-mix(in_srgb,var(--warning)_22%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] dark:border-[color-mix(in_srgb,var(--warning)_28%,transparent)] dark:bg-[color-mix(in_srgb,var(--warning)_14%,transparent)]`;
  }

  return `${base} border-[color-mix(in_srgb,var(--success)_20%,white)] bg-[color-mix(in_srgb,var(--success)_8%,white)] dark:border-[color-mix(in_srgb,var(--success)_28%,transparent)] dark:bg-[color-mix(in_srgb,var(--success)_14%,transparent)]`;
}

export default function OverviewPage() {
  const { currentUser } = useAuth();
  const overviewQuery = useOverviewQuery({ enabled: Boolean(currentUser) });
  const overview = overviewQuery.data ?? null;
  const error = overviewQuery.error instanceof Error ? overviewQuery.error.message : null;
  const isLoading = overviewQuery.isPending;
  const isRefreshing = overviewQuery.isFetching;

  const immediateAttention = useMemo(() => overview?.highRiskWards.slice(0, 3) ?? [], [overview]);

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Overview"
        subtitle="Climate Health Risk Monitoring"
        lastUpdatedLabel={isRefreshing ? "Refreshing..." : formatOperationalTime(overview?.latestTimestamp ?? null)}
        onRefresh={() => {
          void overviewQuery.refetch();
        }}
      >
        <TriggerAlertPanel
          buttonLabel="Trigger Alert"
          closeLabel="Close Alert Builder"
          buttonClassName="inline-flex h-11 items-center justify-center gap-2 rounded-[0.8rem] bg-[linear-gradient(180deg,#1d6fda_0%,#175fc2_100%)] px-4 text-sm font-semibold text-white shadow-[0_16px_32px_rgba(23,95,194,0.22)] transition hover:-translate-y-px"
        />
      </DashboardTopbar>

      {error ? (
        <div className="rounded-2xl border border-[color-mix(in_srgb,var(--danger)_20%,white)] bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--danger)] dark:border-[color-mix(in_srgb,var(--danger)_34%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]">
          <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-4">
        <Card className="flex items-start gap-4 p-6">
          <div className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
            <MapPin className="size-5" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Total wards</span>
            <strong className="block text-4xl font-semibold tracking-[-0.05em] text-panel-strong">
              {isLoading ? "..." : overview?.totalWards ?? 0}
            </strong>
            <p className="text-sm text-panel-muted">Total wards monitored</p>
          </div>
        </Card>

        <Card className="flex items-start gap-4 p-6">
          <div className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--danger)_12%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_20%,transparent)]">
            <TriangleAlert className="size-5" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <StatusBadge tone="danger" className="rounded-full px-3 py-1 tracking-[0.14em]">
              Immediate action
            </StatusBadge>
            <strong className="block text-4xl font-semibold tracking-[-0.05em] text-panel-strong">
              {isLoading ? "..." : overview?.highRiskWards.length ?? 0}
            </strong>
            <p className="text-sm text-panel-muted">High risk wards</p>
          </div>
        </Card>

        <Card className="flex items-start gap-4 p-6">
          <div className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]">
            <CircleAlert className="size-5" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <StatusBadge tone="warning" className="rounded-full px-3 py-1 tracking-[0.14em]">
              Derived review
            </StatusBadge>
            <strong className="block text-4xl font-semibold tracking-[-0.05em] text-panel-strong">
              {isLoading ? "..." : overview?.mediumRiskWards.length ?? 0}
            </strong>
            <p className="text-sm text-panel-muted">Medium risk wards</p>
          </div>
        </Card>

        <Card className="flex items-start gap-4 p-6">
          <div className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)] text-panel-copy">
            <Bell className="size-5" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
              {overview?.deliveredAlertRate ?? 0}% delivered from visible alerts
            </span>
            <strong className="block text-4xl font-semibold tracking-[-0.05em] text-panel-strong">
              {isLoading ? "..." : overview?.alertsTodayCount ?? 0}
            </strong>
            <p className="text-sm text-panel-muted">Alerts today</p>
          </div>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.9fr)]">
        <Card className="space-y-5 p-6">
          <PageSectionHeader
            title="Recent Alerts"
            description={`${overview?.primaryCountyLabel ?? "Current scope"} visible alert activity`}
          />

          <div className="overflow-hidden rounded-[1.5rem] border border-[var(--dashboard-table-line)]">
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-left">
                <thead>
                  <tr>
                    {["Administrative ward", "Channel", "Score", "Status", "Time"].map((label) => (
                      <th
                        key={label}
                        className="border-b border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted"
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-sm text-panel-muted">
                        Loading alert records...
                      </td>
                    </tr>
                  ) : overview && overview.recentAlerts.length > 0 ? (
                    overview.recentAlerts.map((alert) => (
                      <tr key={alert.id}>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <Link
                            href={`/alerts/${alert.id}`}
                            className="font-semibold text-panel-strong transition hover:text-brand"
                          >
                            {alert.ward_name}
                          </Link>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                          {formatChannelLabel(alert.channel)}
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          {typeof alert.risk_score === "number" ? (
                            <span
                              className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${getScoreTone(alert.risk_score)}`}
                            >
                              {formatRiskScore(alert.risk_score)}
                            </span>
                          ) : (
                            <span className="text-panel-muted">N/A</span>
                          )}
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <StatusBadge
                            tone={
                              alert.status === "DELIVERED"
                                ? "success"
                                : alert.status === "FAILED"
                                  ? "danger"
                                  : alert.status === "RETRY_PENDING"
                                    ? "warning"
                                    : "default"
                            }
                            className="rounded-full px-3 py-1 tracking-[0.14em]"
                          >
                            {formatStatusLabel(alert.status)}
                          </StatusBadge>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                          {formatOperationalTime(alert.created_at)}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-sm text-panel-muted">
                        No visible alerts in the current scope yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-panel-muted">
            <span>Risk prioritization is derived from the current visible ward risk feed.</span>
            <span>Alert activity is sourced from the current visible alerts feed.</span>
          </div>
        </Card>

        <aside className="space-y-6">
          <Card className="space-y-5 p-6">
            <PageSectionHeader title="Immediate Attention" />

            <div className="space-y-4">
              {isLoading ? (
                <Card className="rounded-[1.5rem] p-4 shadow-none">
                  <p className="text-sm text-panel-muted">Loading priority wards...</p>
                </Card>
              ) : immediateAttention.length > 0 ? (
                immediateAttention.map((ward, index) => (
                  <Card
                    key={ward.ward_id}
                    className={getAttentionCardClass(ward.risk_level, index === 0)}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <strong className="text-base font-semibold text-panel-strong">{ward.ward_name}</strong>
                      <StatusBadge
                        tone={getRiskBadgeTone(ward.risk_level)}
                        className="rounded-full px-3 py-1 tracking-[0.14em]"
                      >
                        {ward.risk_level ?? "Unknown"}
                      </StatusBadge>
                    </div>
                    <p className="text-sm text-panel-muted">
                      {index === 0 ? "Highest current risk score" : "Current risk score"}
                    </p>
                    <div className="flex items-end gap-2">
                      <strong className="text-3xl font-semibold tracking-[-0.05em] text-panel-strong">
                        {typeof ward.risk_score === "number" ? formatRiskScore(ward.risk_score) : "N/A"}
                      </strong>
                      <span className="pb-1 text-sm text-panel-muted">/100</span>
                    </div>
                  </Card>
                ))
              ) : (
                <Card className="rounded-[1.5rem] p-4 shadow-none">
                  <p className="text-sm text-panel-muted">No high-risk wards are currently visible in your scope.</p>
                </Card>
              )}
            </div>

            <Link
              href="/wards"
              className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
            >
              View high risk wards
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </Card>

          <Card className="space-y-4 p-6">
            <div
              className="flex min-h-[180px] items-center justify-center rounded-[1.75rem] border border-dashed border-[var(--dashboard-table-line)] bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--dashboard-sidebar-title)_10%,white),transparent_52%),radial-gradient(circle_at_bottom_right,color-mix(in_srgb,var(--warning)_10%,white),transparent_48%),var(--color-panel)] dark:bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--dashboard-sidebar-title)_22%,transparent),transparent_52%),radial-gradient(circle_at_bottom_right,color-mix(in_srgb,var(--warning)_20%,transparent),transparent_48%),var(--color-panel)]"
              aria-hidden="true"
            >
              <span className="rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)] px-4 py-2 text-sm font-semibold text-panel-copy">
                {overview?.primaryCountyLabel ?? "County"}
              </span>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
                Live geographic monitor
              </p>
              <strong className="block text-lg font-semibold text-panel-strong">
                {overview?.primaryCountyLabel ?? "Current scope"}
              </strong>
              <span className="text-sm text-panel-muted">
                Map-ready boundary and hotspot overlays need backend geographic endpoints.
              </span>
            </div>
          </Card>
        </aside>
      </section>
    </div>
  );
}
