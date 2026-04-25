"use client";

import { AlertTriangle, ArrowRight, Bell, CircleAlert, MapPin, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { OverviewHotspotMap, type OverviewMapFilter } from "@/components/overview-hotspot-map";
import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import { Card } from "@/components/ui/card";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge } from "@/components/ui/status-badge";
import type { AlertRecord, WardMapFeature } from "@/lib/dashboard";
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

function getMapFilterLabel(filter: OverviewMapFilter) {
  if (filter === "high") return "High risk";
  if (filter === "medium") return "Medium risk";
  if (filter === "low") return "Low risk";
  if (filter === "alerts") return "Active alerts";
  return "All wards";
}

function getFeatureAction(feature: WardMapFeature) {
  if (feature.properties.alert_count > 0) {
    return {
      why: `${feature.properties.alert_count} active alert${feature.properties.alert_count === 1 ? "" : "s"} require review in this ward.`,
      action: "Review ward alerts and investigate field conditions.",
    };
  }

  if (feature.properties.risk_level === "HIGH") {
    return {
      why: "This ward is currently classified as high risk in the latest visible model run.",
      action: "Open ward intelligence and review mitigation priorities.",
    };
  }

  if (feature.properties.risk_level === "MEDIUM") {
    return {
      why: "This ward is trending at watch level and may need closer review.",
      action: "Monitor closely and compare with adjacent wards.",
    };
  }

  return {
    why: "No immediate hotspot signal is visible for this ward right now.",
    action: "Continue routine monitoring.",
  };
}

function getMapControlClass(isActive: boolean) {
  return isActive
    ? "border-brand bg-[color-mix(in_srgb,var(--brand)_14%,transparent)] text-panel-strong shadow-[0_10px_24px_rgba(29,111,218,0.12)]"
    : "border-panel-table-wrap bg-panel/70 text-panel-muted hover:border-brand/40 hover:text-panel-strong";
}

function getKpiCardClass(activeTone: "brand" | "danger" | "warning" | "alerts", isActive: boolean) {
  if (!isActive) {
    return "p-0";
  }

  if (activeTone === "danger") {
    return "overflow-hidden border-[color-mix(in_srgb,var(--danger)_34%,white)] ring-1 ring-[color:var(--danger)]/20 p-0 dark:border-[color-mix(in_srgb,var(--danger)_28%,transparent)]";
  }

  if (activeTone === "warning") {
    return "overflow-hidden border-[color-mix(in_srgb,var(--warning)_34%,white)] ring-1 ring-[color:var(--warning)]/20 p-0 dark:border-[color-mix(in_srgb,var(--warning)_28%,transparent)]";
  }

  if (activeTone === "alerts") {
    return "overflow-hidden border-[color-mix(in_srgb,#F97316_34%,white)] ring-1 ring-[#F97316]/20 p-0 dark:border-[color-mix(in_srgb,#F97316_28%,transparent)]";
  }

  return "overflow-hidden border-brand/35 ring-1 ring-brand/20 p-0";
}

export default function OverviewPage() {
  const { currentUser } = useAuth();
  const router = useRouter();
  const overviewQuery = useOverviewQuery({ enabled: Boolean(currentUser) });
  const overview = overviewQuery.data ?? null;
  const error = overviewQuery.error instanceof Error ? overviewQuery.error.message : null;
  const isLoading = overviewQuery.isPending;
  const isRefreshing = overviewQuery.isFetching;
  const [mapFilter, setMapFilter] = useState<OverviewMapFilter>("all");
  const [hoveredMapFilter, setHoveredMapFilter] = useState<OverviewMapFilter | null>(null);
  const [selectedWardId, setSelectedWardId] = useState<number | null>(null);

  const immediateAttention = useMemo(() => overview?.highRiskWards.slice(0, 3) ?? [], [overview]);
  const wardFeatures = overview?.wardMap?.features ?? [];
  const selectedFeature = useMemo(
    () => wardFeatures.find((feature) => feature.properties.backend_ward_id === selectedWardId) ?? null,
    [selectedWardId, wardFeatures],
  );
  const hotspotHighlightWardId = selectedWardId ?? overview?.recentAlerts[0]?.ward ?? null;
  const topAlertWard = useMemo(
    () =>
      [...wardFeatures]
        .filter((feature) => feature.properties.alert_count > 0)
        .sort((left, right) => {
          if (right.properties.alert_count !== left.properties.alert_count) {
            return right.properties.alert_count - left.properties.alert_count;
          }

          const leftRisk = left.properties.risk_level === "HIGH" ? 3 : left.properties.risk_level === "MEDIUM" ? 2 : 1;
          const rightRisk = right.properties.risk_level === "HIGH" ? 3 : right.properties.risk_level === "MEDIUM" ? 2 : 1;
          return rightRisk - leftRisk;
        })[0] ?? null,
    [wardFeatures],
  );

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
          buttonLabel="Create Alert"
          closeLabel="Close Alert Flow"
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
        <Card className={getKpiCardClass("brand", mapFilter === "all")}>
          <button
            type="button"
            className="flex h-full w-full items-start gap-4 rounded-panel p-6 text-left transition"
            onClick={() => setMapFilter("all")}
            onMouseEnter={() => setHoveredMapFilter("all")}
            onMouseLeave={() => setHoveredMapFilter(null)}
          >
            <div className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
              <MapPin className="size-5" aria-hidden="true" />
            </div>
            <div className="space-y-1">
              <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Total wards</span>
              <strong className="block text-4xl font-semibold tracking-[-0.05em] text-panel-strong">
                {isLoading ? "..." : overview?.totalWards ?? 0}
              </strong>
              <p className="text-sm text-panel-muted">Reset map to all wards</p>
            </div>
          </button>
        </Card>

        <Card className={getKpiCardClass("danger", mapFilter === "high")}>
          <button
            type="button"
            className="flex h-full w-full items-start gap-4 rounded-panel p-6 text-left transition"
            onClick={() => setMapFilter((current) => (current === "high" ? "all" : "high"))}
            onMouseEnter={() => setHoveredMapFilter("high")}
            onMouseLeave={() => setHoveredMapFilter(null)}
          >
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
              <p className="text-sm text-panel-muted">Highlight high risk wards on map</p>
            </div>
          </button>
        </Card>

        <Card className={getKpiCardClass("warning", mapFilter === "medium")}>
          <button
            type="button"
            className="flex h-full w-full items-start gap-4 rounded-panel p-6 text-left transition"
            onClick={() => setMapFilter((current) => (current === "medium" ? "all" : "medium"))}
            onMouseEnter={() => setHoveredMapFilter("medium")}
            onMouseLeave={() => setHoveredMapFilter(null)}
          >
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
              <p className="text-sm text-panel-muted">Highlight medium risk wards on map</p>
            </div>
          </button>
        </Card>

        <Card className={getKpiCardClass("alerts", mapFilter === "alerts")}>
          <button
            type="button"
            className="flex h-full w-full items-start gap-4 rounded-panel p-6 text-left transition"
            onClick={() => setMapFilter((current) => (current === "alerts" ? "all" : "alerts"))}
            onMouseEnter={() => setHoveredMapFilter("alerts")}
            onMouseLeave={() => setHoveredMapFilter(null)}
          >
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
              <p className="text-sm text-panel-muted">Highlight active alert wards on map</p>
            </div>
          </button>
        </Card>
      </section>

      <Card className="space-y-4 p-6">
        <div className="flex flex-col gap-3">
          <PageSectionHeader
            title="Live Risk Hotspots"
            description="Real-time ward-level risk and alert activity"
          />
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-panel-muted">
            {([
              { key: "all", label: "All wards", dot: "bg-panel-copy" },
              { key: "high", label: "High risk", dot: "bg-[#DC2626]" },
              { key: "medium", label: "Medium risk", dot: "bg-[#F59E0B]" },
              { key: "low", label: "Low risk", dot: "bg-[#16A34A]" },
              { key: "alerts", label: "Active alerts", dot: "bg-[#F97316]" },
            ] as const).map((item) => {
              const active = mapFilter === item.key;
              const hovered = hoveredMapFilter === item.key;

              return (
                <button
                  key={item.key}
                  type="button"
                  className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 transition ${getMapControlClass(active || hovered)}`}
                  onClick={() => setMapFilter((current) => (current === item.key ? "all" : item.key))}
                  onMouseEnter={() => setHoveredMapFilter(item.key)}
                  onMouseLeave={() => setHoveredMapFilter(null)}
                >
                  <span className={`size-2.5 rounded-full ${item.dot}`} />
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="overflow-hidden rounded-[1.75rem] border border-panel-table-wrap bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_10%,transparent),transparent_38%),linear-gradient(135deg,color-mix(in_srgb,var(--panel)_94%,var(--background-fade)),var(--panel))] p-2">
          <div className="h-[28rem] lg:h-[30rem]">
            {overview?.wardMap?.features?.length ? (
              <OverviewHotspotMap
                features={overview.wardMap.features}
                highlightedWardId={hotspotHighlightWardId}
                activeFilter={mapFilter}
                hoveredFilter={hoveredMapFilter}
                lastUpdatedLabel={formatCompactRelativeMinutes(overview?.latestTimestamp ?? null)}
                onSelectWard={(feature) => {
                  setSelectedWardId(feature.properties.backend_ward_id ?? null);
                }}
              />
            ) : (
              <div className="flex h-full items-center justify-center rounded-[1.35rem] border border-dashed border-panel-table-wrap px-6 text-center text-sm text-panel-muted">
                Hotspot geography is not available for this scope yet.
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-panel-muted">
          <span>Current map focus: {getMapFilterLabel(mapFilter)}</span>
          <span>{selectedFeature ? `Selected ward: ${selectedFeature.properties.name}` : "Click a hotspot to update the attention panel."}</span>
        </div>
      </Card>

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
            <PageSectionHeader title={selectedFeature ? "Attention Focus" : "Immediate Attention"} />

            <div className="space-y-4">
              {isLoading ? (
                <Card className="rounded-[1.5rem] p-4 shadow-none">
                  <p className="text-sm text-panel-muted">Loading priority wards...</p>
                </Card>
              ) : selectedFeature ? (
                <Card
                  className={getAttentionCardClass(selectedFeature.properties.risk_level, true)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <strong className="text-lg font-semibold text-panel-strong">{selectedFeature.properties.name}</strong>
                      <p className="text-sm text-panel-muted">
                        {selectedFeature.properties.alert_count > 0
                          ? "Selected hotspot from the live risk surface."
                          : "Selected ward from the live risk surface."}
                      </p>
                    </div>
                    <StatusBadge
                      tone={getRiskBadgeTone(selectedFeature.properties.risk_level)}
                      className="rounded-full px-3 py-1 tracking-[0.14em]"
                    >
                      {selectedFeature.properties.risk_level ?? "Unknown"}
                    </StatusBadge>
                  </div>

                  <div className="grid grid-cols-2 gap-3 rounded-[1.2rem] border border-panel-table-wrap/80 bg-panel/60 p-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Alerts</p>
                      <strong className="mt-1 block text-2xl font-semibold text-panel-strong">
                        {selectedFeature.properties.alert_count}
                      </strong>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Predicted cases</p>
                      <strong className="mt-1 block text-2xl font-semibold text-panel-strong">
                        {selectedFeature.properties.predicted_cases}
                      </strong>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Why it matters</p>
                      <p className="mt-1 text-sm text-panel-copy">{getFeatureAction(selectedFeature).why}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Suggested action</p>
                      <p className="mt-1 text-sm text-panel-copy">{getFeatureAction(selectedFeature).action}</p>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-3 pt-1">
                    {selectedFeature.properties.backend_ward_id ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-2 rounded-full bg-[linear-gradient(180deg,#1d6fda_0%,#175fc2_100%)] px-4 py-2 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(23,95,194,0.18)] transition hover:-translate-y-px"
                        onClick={() => router.push(`/wards/${selectedFeature.properties.backend_ward_id}`)}
                      >
                        View ward
                        <ArrowRight className="size-4" aria-hidden="true" />
                      </button>
                    ) : null}
                    <Link
                      href="/alerts"
                      className="inline-flex items-center gap-2 rounded-full border border-panel-table-wrap px-4 py-2 text-sm font-semibold text-panel-strong transition hover:border-brand/40 hover:text-brand"
                    >
                      Review alerts
                    </Link>
                  </div>
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
                  <p className="text-sm font-semibold text-panel-strong">System stable</p>
                  <p className="mt-2 text-sm text-panel-muted">
                    No high-risk wards are currently visible in your scope.
                  </p>
                  {topAlertWard ? (
                    <p className="mt-3 text-sm text-panel-copy">
                      Most active alert ward: <strong className="text-panel-strong">{topAlertWard.properties.name}</strong>
                    </p>
                  ) : null}
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

        </aside>
      </section>
    </div>
  );
}
