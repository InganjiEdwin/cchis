"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Bell,
  ChevronRight,
  Clock3,
  Droplets,
  History,
  MapPinned,
  Minus,
  ShieldAlert,
  Waves,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { AlertRecord, RiskScoreRecord, WardIntelligenceDriverItem } from "@/lib/dashboard";
import { canTriggerAlerts } from "@/lib/roles";
import {
  type WardDetailState,
  useWardDetailQuery,
} from "@/queries/use-ward-detail-query";

const STALE_THRESHOLD_MINUTES = 120;

function normalizeRiskScore(score: number | null) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return 0;
  }
  if (score <= 1) {
    return Math.max(0, Math.min(score * 100, 100));
  }
  return Math.max(0, Math.min(score, 100));
}

function formatRiskScore(score: number | null) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return "N/A";
  }
  return `${Math.round(normalizeRiskScore(score))}/100`;
}

function formatRelativeMinutes(timestamp: string | null) {
  if (!timestamp) return "No recent update";

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";

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
  if (!timestamp) return "No timestamp";

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";

  return `${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} (${formatRelativeMinutes(timestamp)})`;
}

function isStaleTimestamp(timestamp: string | null) {
  if (!timestamp) return true;

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return true;

  return (Date.now() - date.getTime()) / 60000 > STALE_THRESHOLD_MINUTES;
}

function formatRiskLevel(riskLevel: WardDetailState["riskLevel"]) {
  switch (riskLevel) {
    case "HIGH":
      return "High risk";
    case "MEDIUM":
      return "Medium risk";
    case "LOW":
      return "Low risk";
    default:
      return "Unknown risk";
  }
}

function toTitleCase(value: string) {
  return value
    .toLowerCase()
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getAlertHeadline(alert: AlertRecord) {
  if (alert.message && alert.message.trim().length > 0) {
    return alert.message.trim();
  }
  return `${toTitleCase(alert.channel)} alert`;
}

function getRiskDriverIcon(driver: WardIntelligenceDriverItem) {
  switch (driver.source_field) {
    case "rainfall_mm":
      return <Droplets className="size-4" aria-hidden="true" />;
    case "flood_indicator":
      return <Waves className="size-4" aria-hidden="true" />;
    case "predicted_cases":
      return <History className="size-4" aria-hidden="true" />;
    case "model_run.status":
    default:
      return <Clock3 className="size-4" aria-hidden="true" />;
  }
}

function getSafeReturnTo(value: string | null) {
  if (!value) {
    return "/wards";
  }
  return value.startsWith("/wards") ? value : "/wards";
}

function getHistoryTrendIcon(index: number, history: RiskScoreRecord[]) {
  const current = history[index];
  const previous = history[index + 1];

  if (!current || !previous) return "flat" as const;
  if (normalizeRiskScore(current.score) > normalizeRiskScore(previous.score)) return "up" as const;
  if (normalizeRiskScore(current.score) < normalizeRiskScore(previous.score)) return "down" as const;
  return "flat" as const;
}

function getRiskBadgeTone(level: WardDetailState["riskLevel"]) {
  if (level === "HIGH") return "danger" as const;
  if (level === "MEDIUM") return "warning" as const;
  if (level === "LOW") return "success" as const;
  return "default" as const;
}

export default function WardDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const { currentUser } = useAuth();
  const wardId = useMemo(() => Number(params.id), [params.id]);
  const returnTo = useMemo(() => getSafeReturnTo(searchParams.get("returnTo")), [searchParams]);
  const wardDetailQuery = useWardDetailQuery({
    wardId,
    enabled: Boolean(currentUser) && Number.isFinite(wardId),
  });
  const detail = wardDetailQuery.data ?? null;
  const isLoading = wardDetailQuery.isPending;
  const isRefreshing = wardDetailQuery.isFetching;
  const isHistoryLoading = wardDetailQuery.isPending;
  const isAlertsLoading = wardDetailQuery.isPending;
  const error = wardDetailQuery.error instanceof Error ? wardDetailQuery.error.message : null;
  const historyError = null;
  const alertsError = null;

  const isStale = isStaleTimestamp(detail?.updatedAt ?? null);
  const topbarTimestampLabel = isRefreshing
    ? "Refreshing..."
    : `${formatOperationalTime(detail?.updatedAt ?? null)}${isStale ? " · Stale" : ""}`;
  const trend = detail?.trend ?? {
    label: "No previous run available",
    direction: "flat" as const,
    delta_points: null,
    mode: "derived_from_recent_history",
  };
  const drivers = detail?.driverItems ?? [];
  const recommendations = detail?.guidanceItems ?? [];
  const latestAlert = detail?.relatedAlerts[0] ?? null;

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Ward Detail"
        subtitle={detail ? `${detail.county} County ward view` : "Migori County ward view"}
        lastUpdatedLabel={topbarTimestampLabel}
        lastUpdatedTone={isStale ? "stale" : "default"}
        onRefresh={() => {
          void wardDetailQuery.refetch();
        }}
      />

      {error ? (
        <div className="rounded-2xl border border-[color-mix(in_srgb,var(--danger)_20%,white)] bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--danger)]">
          <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <Card className="space-y-5 p-6 md:p-7">
        <Link
          href={returnTo}
          className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to wards
        </Link>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[clamp(2rem,1.2rem+1vw,3rem)] font-semibold tracking-[-0.05em] text-panel-strong">
              {isLoading ? "Loading ward detail..." : detail?.wardName ?? "Ward detail"}
            </h1>
            {!isLoading ? (
              <>
                <StatusBadge
                  tone={getRiskBadgeTone(detail?.riskLevel ?? "UNKNOWN")}
                  className="rounded-full px-3 py-1.5 tracking-[0.14em]"
                >
                  {formatRiskLevel(detail?.riskLevel ?? "UNKNOWN")}
                </StatusBadge>
                <span className="rounded-full border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] px-3 py-1.5 text-sm font-semibold text-panel-copy">
                  Risk score: {formatRiskScore(detail?.riskScore ?? null)}
                </span>
                <span className="text-sm text-panel-muted">
                  Last alert: {latestAlert ? formatRelativeMinutes(latestAlert.created_at) : "No recent alerts"}
                </span>
              </>
            ) : null}
          </div>

          <p className="text-sm text-panel-muted">
            {isLoading
              ? "Preparing the latest ward risk context."
              : detail
                ? `${detail.subCounty || "Unassigned sub-county"}, ${detail.county} County`
                : "Ward-level risk monitoring."}
          </p>
        </div>
      </Card>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.85fr)]">
        <div className="space-y-6">
          <Card className="space-y-5 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)]">
                  <ShieldAlert className="size-5" aria-hidden="true" />
                </span>
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Observed signals</h3>
              </div>
              <div
                className={cn(
                  "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold",
                  trend.direction === "up"
                    ? "bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-[color:var(--danger)]"
                    : trend.direction === "down"
                      ? "bg-[color-mix(in_srgb,var(--success)_10%,white)] text-[color:var(--success)]"
                      : "bg-[color-mix(in_srgb,var(--dashboard-table-line)_40%,transparent)] text-panel-copy",
                )}
              >
                <ArrowUpRight className={cn("size-4", trend.direction === "down" && "rotate-90")} aria-hidden="true" />
                <span>{isLoading ? "Loading trend..." : trend.label}</span>
              </div>
            </div>

            {isLoading ? (
              <div className="space-y-3" aria-hidden="true">
                <div className="h-16 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                <div className="h-16 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                <div className="h-16 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
              </div>
            ) : (
              <div className="space-y-3">
                {drivers.map((driver) => (
                  <article
                    key={driver.text}
                    className="flex items-center gap-3 rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-4"
                  >
                    <span
                      className={cn(
                        "size-3 rounded-full",
                        driver.tone === "critical"
                          ? "bg-[color:var(--danger)]"
                          : driver.tone === "warning"
                            ? "bg-[color:var(--warning)]"
                            : "bg-[color:var(--success)]",
                      )}
                      aria-hidden="true"
                    />
                    <span
                      className={cn(
                        "inline-flex size-9 items-center justify-center rounded-full",
                        driver.tone === "critical"
                          ? "bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-[color:var(--danger)]"
                          : driver.tone === "warning"
                            ? "bg-[color-mix(in_srgb,var(--warning)_10%,white)] text-[color:var(--warning)]"
                            : "bg-[color-mix(in_srgb,var(--dashboard-table-line)_40%,transparent)] text-panel-copy",
                      )}
                    >
                      {getRiskDriverIcon(driver)}
                    </span>
                    <strong className="text-sm font-semibold text-panel-strong">{driver.text}</strong>
                  </article>
                ))}
              </div>
            )}
          </Card>

          <Card className="space-y-5 p-6">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand">
                  <Waves className="size-5" aria-hidden="true" />
                </span>
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Recent risk history</h3>
              </div>
              <p className="text-sm text-panel-muted">Latest recorded model runs for this ward</p>
            </div>

            {isHistoryLoading ? (
              <div className="space-y-3" aria-hidden="true">
                {Array.from({ length: 4 }, (_, index) => (
                  <div
                    key={`history-skeleton-${index}`}
                    className="h-14 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]"
                  />
                ))}
              </div>
            ) : historyError ? (
              <div className="rounded-2xl border border-[color-mix(in_srgb,var(--warning)_20%,white)] bg-[color-mix(in_srgb,var(--warning)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--warning)]">
                <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
                {historyError}
              </div>
            ) : detail && detail.riskHistory.length > 0 ? (
              <div className="overflow-hidden rounded-[1.5rem] border border-[var(--dashboard-table-line)]">
                <div className="overflow-x-auto">
                  <table className="min-w-full border-collapse text-left">
                    <thead>
                      <tr>
                        {["Date/time", "Risk score", "Status", "Trend"].map((label) => (
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
                      {detail.riskHistory.slice(0, 6).map((risk, index, history) => {
                        const historyTrend = getHistoryTrendIcon(index, history);

                        return (
                          <tr key={risk.id}>
                            <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                              {formatOperationalTime(risk.generated_at)}
                            </td>
                            <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm font-semibold text-panel-strong last:border-b-0">
                              {Math.round(normalizeRiskScore(risk.score))}
                            </td>
                            <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                              <StatusBadge
                                tone={getRiskBadgeTone(risk.risk_level)}
                                className="rounded-full px-3 py-1 tracking-[0.14em]"
                              >
                                {risk.risk_level}
                              </StatusBadge>
                            </td>
                            <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                              <span
                                className={cn(
                                  "inline-flex size-8 items-center justify-center rounded-full",
                                  historyTrend === "up"
                                    ? "bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-[color:var(--danger)]"
                                    : historyTrend === "down"
                                      ? "bg-[color-mix(in_srgb,var(--success)_10%,white)] text-[color:var(--success)]"
                                      : "bg-[color-mix(in_srgb,var(--dashboard-table-line)_40%,transparent)] text-panel-copy",
                                )}
                              >
                                {historyTrend === "up" ? (
                                  <ArrowUpRight className="size-4" aria-hidden="true" />
                                ) : historyTrend === "down" ? (
                                  <ArrowUpRight className="size-4 rotate-90" aria-hidden="true" />
                                ) : (
                                  <Minus className="size-4" aria-hidden="true" />
                                )}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p className="text-sm text-panel-muted">No risk history is currently available for this ward.</p>
            )}
          </Card>

          <section className="grid gap-6 lg:grid-cols-2">
            <Card className="space-y-5 p-6">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand">
                  <MapPinned className="size-5" aria-hidden="true" />
                </span>
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Ward context</h3>
              </div>

              {isLoading ? (
                <div className="space-y-3" aria-hidden="true">
                  <div className="h-4 w-full rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                  <div className="h-4 w-full rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                  <div className="h-4 w-1/2 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                </div>
              ) : detail ? (
                <dl className="grid gap-4">
                  {[
                    ["Sub-county", detail.subCounty || "Not recorded"],
                    ["Ward code", detail.wardCode ?? "Not recorded"],
                    ["Predicted cases", detail.predictedCases],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="grid gap-1 border-b border-[var(--dashboard-table-line)] pb-3 last:border-b-0 last:pb-0"
                    >
                      <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</dt>
                      <dd className="text-sm font-medium text-panel-strong">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-sm text-panel-muted">No ward detail is available for this route.</p>
              )}
            </Card>

            <Card className="space-y-5 p-6">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand">
                  <Clock3 className="size-5" aria-hidden="true" />
                </span>
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Freshness and availability</h3>
              </div>

              <dl className="grid gap-4">
                {[
                  ["Freshness", isLoading ? "Loading..." : detail?.freshness.is_stale ? "Stale" : "In range"],
                  ["History coverage", isLoading ? "Loading..." : detail ? `${detail.freshness.history_count} recent runs` : "Unavailable"],
                  [
                    "Alert linkage",
                    isLoading
                      ? "Loading..."
                      : alertsError
                        ? "Temporarily unavailable"
                        : detail
                          ? `${detail.freshness.alert_count} recent alerts`
                          : "Unavailable",
                  ],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="grid gap-1 border-b border-[var(--dashboard-table-line)] pb-3 last:border-b-0 last:pb-0"
                  >
                    <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</dt>
                    <dd className="text-sm font-medium text-panel-strong">{String(value)}</dd>
                  </div>
                ))}
              </dl>

              <p className="text-sm leading-6 text-panel-muted">
                {!isLoading && detail?.freshness.is_stale
                  ? `This ward summary is older than the ${detail.freshness.stale_threshold_minutes}-minute freshness window. Review with caution until the next update lands.`
                  : "Derived from the current ward summary, recent history, and linked alert activity."}
              </p>
            </Card>
          </section>
        </div>

        <aside className="space-y-6">
          <Card className="space-y-5 p-6">
            <div className="flex items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand">
                <Zap className="size-5" aria-hidden="true" />
              </span>
              <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Guidance for this risk tier</h3>
            </div>

            {isLoading ? (
              <div className="space-y-3" aria-hidden="true">
                <div className="h-16 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                <div className="h-16 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                <div className="h-16 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
              </div>
            ) : (
              <div className="space-y-3">
                {recommendations.map((recommendation, index) => (
                  <article
                    key={recommendation.text}
                    className="flex gap-3 rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-4"
                  >
                    <div className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-white">
                      {String(index + 1).padStart(2, "0")}
                    </div>
                    <div className="space-y-1">
                      <strong className="block text-sm font-semibold text-panel-strong">{recommendation.text}</strong>
                      <span className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">
                        {index === 0 && canTriggerAlerts(currentUser.role)
                          ? "Trigger available"
                          : canTriggerAlerts(currentUser.role)
                            ? "Guidance only"
                            : "Read only"}
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            )}

            {detail ? (
              canTriggerAlerts(currentUser.role) ? (
                <TriggerAlertPanel
                  buttonLabel="Trigger Alert"
                  closeLabel="Close action panel"
                  buttonClassName="inline-flex h-12 w-full items-center justify-center gap-2 rounded-pill bg-[var(--login-submit-start)] px-5 text-base font-semibold text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
                  fixedWard={{
                    id: detail.wardId,
                    name: detail.wardName,
                    county: detail.county,
                    subCounty: detail.subCounty,
                    riskLevel: detail.riskLevel,
                    riskScore: detail.riskScore,
                    predictedCases: detail.predictedCases,
                    updatedAt: detail.updatedAt,
                  }}
                />
              ) : (
                <div className="rounded-2xl border border-[color-mix(in_srgb,var(--warning)_20%,white)] bg-[color-mix(in_srgb,var(--warning)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--warning)]">
                  <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
                  Guidance is visible, but this role cannot trigger alerts from this page.
                </div>
              )
            ) : null}
          </Card>

          <Card className="space-y-5 p-6">
            <div className="flex items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand">
                <Bell className="size-5" aria-hidden="true" />
              </span>
              <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Recent alerts</h3>
            </div>

            {isAlertsLoading ? (
              <div className="space-y-3" aria-hidden="true">
                {Array.from({ length: 3 }, (_, index) => (
                  <div
                    key={`alert-skeleton-${index}`}
                    className="h-16 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]"
                  />
                ))}
              </div>
            ) : alertsError ? (
              <div className="rounded-2xl border border-[color-mix(in_srgb,var(--warning)_20%,white)] bg-[color-mix(in_srgb,var(--warning)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--warning)]">
                <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
                {alertsError}
              </div>
            ) : detail && detail.relatedAlerts.length > 0 ? (
              <>
                <div className="space-y-3">
                  {detail.relatedAlerts.slice(0, 4).map((alert) => (
                    <article
                      key={alert.id}
                      className="flex items-start gap-3 rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-4"
                    >
                      <div className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand">
                        <Bell className="size-4" aria-hidden="true" />
                      </div>
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <strong className="text-sm font-semibold text-panel-strong">
                            {getAlertHeadline(alert)}
                          </strong>
                          <StatusBadge
                            tone={
                              alert.status === "DELIVERED"
                                ? "success"
                                : alert.status === "FAILED"
                                  ? "danger"
                                  : "warning"
                            }
                            className="rounded-full px-3 py-1 tracking-[0.14em]"
                          >
                            {alert.status}
                          </StatusBadge>
                        </div>
                        <p className="text-sm text-panel-muted">
                          Via {toTitleCase(alert.channel)} • {toTitleCase(alert.status)}
                        </p>
                      </div>
                      <div className="text-xs font-medium text-panel-muted">
                        {formatRelativeMinutes(alert.created_at)}
                      </div>
                    </article>
                  ))}
                </div>
                <Link
                  href="/alerts"
                  className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
                >
                  View Alert History
                  <ChevronRight className="size-4" aria-hidden="true" />
                </Link>
              </>
            ) : (
              <p className="text-sm text-panel-muted">No alerts are currently visible for this ward.</p>
            )}
          </Card>
        </aside>
      </section>
    </div>
  );
}
