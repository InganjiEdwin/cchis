"use client";

import {
  Activity,
  AlertTriangle,
  BellRing,
  BriefcaseMedical,
  ChevronLeft,
  ChevronRight,
  ChevronsRight,
  Clock3,
  Filter,
  Megaphone,
  MoreHorizontal,
  Search,
  ShieldAlert,
  Smartphone,
  Users2,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { MigoriWardMap } from "@/components/migori-ward-map";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { LatestWardRisk, WardMapFeature } from "@/lib/dashboard";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";
import { useChvOperationsQuery } from "@/queries/use-chv-operations-query";

type FocusFilter = "ALL" | "HIGH_RISK";
type RegistryStatus = "ACTIVE" | "IDLE" | "OFFLINE";
type RegistryRiskZone = "HIGH" | "MODERATE" | "SAFE";
type SyncHealth = "ONLINE" | "DELAYED" | "OFFLINE";
type QuickFilter = "ALL" | "ACTIVE" | "IDLE" | "OFFLINE" | "HIGH_RISK";
type SelectedWardFilter = "ALL" | `id:${number}`;

type RegistryRow = {
  id: number;
  initials: string;
  name: string;
  rosterId: string;
  wardName: string;
  status: RegistryStatus;
  alertsRaised: number;
  alertsAcknowledged: number;
  lastSync: string;
  riskZone: RegistryRiskZone;
  syncHealth: SyncHealth;
  phoneNumber: string;
  language: string;
  lastProtocolUpdate: string;
};

const ROWS_PER_PAGE = 5;
const STALE_THRESHOLD_MINUTES = 120;

function getInitials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function toTitleStatus(status: RegistryStatus) {
  switch (status) {
    case "ACTIVE":
      return "Active";
    case "IDLE":
      return "Idle";
    case "OFFLINE":
    default:
      return "Offline";
  }
}

function toRiskZoneLabel(zone: RegistryRiskZone) {
  switch (zone) {
    case "HIGH":
      return "High risk";
    case "MODERATE":
      return "Watch";
    case "SAFE":
    default:
      return "Safe";
  }
}

function resolveRiskZone(level: string | null | undefined): RegistryRiskZone {
  if (level === "HIGH") {
    return "HIGH";
  }
  if (level === "MEDIUM") {
    return "MODERATE";
  }
  return "SAFE";
}

function toSyncHealthLabel(syncHealth: SyncHealth) {
  switch (syncHealth) {
    case "ONLINE":
      return "Online";
    case "DELAYED":
      return "Delayed sync";
    case "OFFLINE":
    default:
      return "Offline";
  }
}

function statusTone(status: RegistryStatus) {
  switch (status) {
    case "ACTIVE":
      return "success" as const;
    case "IDLE":
      return "warning" as const;
    case "OFFLINE":
    default:
      return "default" as const;
  }
}

function riskTone(zone: RegistryRiskZone) {
  switch (zone) {
    case "HIGH":
      return "danger" as const;
    case "MODERATE":
      return "warning" as const;
    case "SAFE":
    default:
      return "success" as const;
  }
}

function syncTone(sync: SyncHealth) {
  switch (sync) {
    case "ONLINE":
      return "success" as const;
    case "DELAYED":
      return "warning" as const;
    case "OFFLINE":
    default:
      return "default" as const;
  }
}

function getCoverageStatus(feature: WardMapFeature) {
  if (!feature.properties.has_backend_ward) {
    return {
      label: "Unmatched",
      tone: "default" as const,
      reason: "Geometry exists locally, but no backend ward row is matched yet.",
    };
  }

  const active = feature.properties.active_chv_count;
  const total = feature.properties.chv_count;
  const riskLevel = feature.properties.risk_level;

  if (active === 0) {
    return {
      label: "Gap",
      tone: "danger" as const,
      reason: "0 active CHVs are recorded in this ward.",
    };
  }

  if (riskLevel === "HIGH" && active <= 1) {
    return {
      label: "Gap",
      tone: "danger" as const,
      reason: "High recorded risk is paired with only 1 active CHV.",
    };
  }

  if ((riskLevel === "HIGH" && active <= 2) || (riskLevel === "MEDIUM" && active <= 1)) {
    return {
      label: "Watch",
      tone: "warning" as const,
      reason: "Recorded risk is elevated relative to the visible active CHV count.",
    };
  }

  if (total > 0 && active / total < 0.5) {
    return {
      label: "Watch",
      tone: "warning" as const,
      reason: "Less than half of linked CHVs are active in this ward.",
    };
  }

  return {
    label: "Adequate",
    tone: "success" as const,
    reason: "Active CHV coverage is present for the current recorded ward risk.",
  };
}

export default function ChvsPage() {
  const { currentUser } = useAuth();
  const [search, setSearch] = useState("");
  const [selectedWard, setSelectedWard] = useState<SelectedWardFilter>("ALL");
  const [focusFilter, setFocusFilter] = useState<FocusFilter>("ALL");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedChvId, setSelectedChvId] = useState<number | null>(null);
  const { data, isPending: isLoading, error } = useChvOperationsQuery({
    enabled: Boolean(currentUser),
  });
  const chvs = data?.chvs ?? [];
  const latestRisks = data?.latestRisks ?? [];
  const alerts = data?.alerts ?? [];
  const wardMap = data?.wardMap ?? null;
  const mapFeatures = wardMap?.features ?? [];

  const latestTimestamp = useMemo(
    () =>
      getLatestTimestamp([
        ...chvs.flatMap((item) => [item.created_at, item.last_activity_at, item.last_sync_at].filter(Boolean)),
        ...latestRisks.map((item) => item.generated_at),
        ...alerts.map((item) => item.created_at),
      ]),
    [alerts, chvs, latestRisks],
  );

  const freshness = useMemo(
    () => describeFreshness(latestTimestamp, STALE_THRESHOLD_MINUTES),
    [latestTimestamp],
  );
  const lastUpdatedLabel = latestTimestamp ? formatRelativeTimestamp(latestTimestamp) : freshness.label;

  const riskByWard = useMemo(() => {
    const map = new Map<number, LatestWardRisk>();
    latestRisks.forEach((risk) => {
      map.set(risk.ward_id, risk);
    });
    return map;
  }, [latestRisks]);

  const wardsForFilter = useMemo(() => {
    const options = new Map<string, string>();
    options.set("ALL", "All Wards");

    mapFeatures.forEach((feature) => {
      if (feature.properties.backend_ward_id) {
        options.set(`id:${feature.properties.backend_ward_id}`, feature.properties.name);
      }
    });

    chvs.forEach((chv) => {
      options.set(`id:${chv.ward}`, chv.ward_name);
    });

    return [...options.entries()]
      .map(([value, label]) => ({ value, label }))
      .sort((left, right) => {
        if (left.value === "ALL") return -1;
        if (right.value === "ALL") return 1;
        return left.label.localeCompare(right.label);
      });
  }, [chvs, mapFeatures]);

  const filteredChvs = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return chvs.filter((chv) => {
      if (selectedWard !== "ALL") {
        if (chv.ward !== Number(selectedWard.slice(3))) {
          return false;
        }
      }

      const riskLevel = riskByWard.get(chv.ward)?.risk_level ?? "LOW";
      if (focusFilter === "HIGH_RISK" && riskLevel !== "HIGH") {
        return false;
      }

      const status = chv.operational_status;
      if (quickFilter === "ACTIVE" && status !== "ACTIVE") return false;
      if (quickFilter === "IDLE" && status !== "IDLE") return false;
      if (quickFilter === "OFFLINE" && status !== "OFFLINE") return false;
      if (quickFilter === "HIGH_RISK" && riskLevel !== "HIGH") return false;

      if (!normalizedSearch) {
        return true;
      }

      return (
        chv.name.toLowerCase().includes(normalizedSearch) ||
        chv.phone_number.toLowerCase().includes(normalizedSearch) ||
        chv.ward_name.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [chvs, focusFilter, quickFilter, riskByWard, search, selectedWard]);

  useEffect(() => {
    setCurrentPage(1);
  }, [focusFilter, quickFilter, search, selectedWard]);

  const totalChvs = chvs.length;
  const activeChvs = filteredChvs.filter((item) => item.operational_status === "ACTIVE").length;
  const acknowledgedRate = alerts.length
    ? (alerts.filter((item) => item.status === "DELIVERED").length / alerts.length) * 100
    : 0;
  const highUrgencyCases = filteredChvs.reduce((sum, item) => sum + item.triage_sessions_24h, 0);

  const registryRows = useMemo<RegistryRow[]>(() => {
    return filteredChvs.map((chv) => {
      return {
        id: chv.id,
        initials: getInitials(chv.name),
        name: chv.name,
        rosterId: `Phone ${chv.phone_number}`,
        wardName: chv.ward_name,
        status: chv.operational_status,
        alertsRaised: chv.ward_alerts_total,
        alertsAcknowledged: chv.ward_alerts_delivered,
        lastSync: chv.last_sync_at ? formatRelativeTimestamp(chv.last_sync_at) : "No sync recorded",
        riskZone: resolveRiskZone(riskByWard.get(chv.ward)?.risk_level),
        syncHealth: chv.sync_health,
        phoneNumber: chv.phone_number,
        language: chv.language,
        lastProtocolUpdate: chv.last_activity_at ? formatRelativeTimestamp(chv.last_activity_at) : "No recent activity",
      };
    });
  }, [filteredChvs, riskByWard]);

  const selectedChv = useMemo(
    () => registryRows.find((row) => row.id === selectedChvId) ?? null,
    [registryRows, selectedChvId],
  );

  const totalPages = Math.max(1, Math.ceil(registryRows.length / ROWS_PER_PAGE));
  const clampedPage = Math.min(currentPage, totalPages);
  const pagedRows = registryRows.slice((clampedPage - 1) * ROWS_PER_PAGE, clampedPage * ROWS_PER_PAGE);

  const criticalCoverageGap = useMemo(() => {
    const wardCounts = chvs.reduce((map, chv) => {
      map.set(chv.ward, (map.get(chv.ward) ?? 0) + (chv.operational_status === "ACTIVE" ? 1 : 0));
      return map;
    }, new Map<number, number>());

    const candidate = latestRisks.find(
      (risk) => risk.risk_level === "HIGH" && (wardCounts.get(risk.ward_id) ?? 0) <= 1,
    );

    if (!candidate) {
      return null;
    }

    return {
      wardName: candidate.ward_name,
      activeCount: wardCounts.get(candidate.ward_id) ?? 0,
      predictedCases: candidate.predicted_cases,
    };
  }, [chvs, latestRisks]);

  const hasCriticalCoverageGap = Boolean(criticalCoverageGap);
  const highPriorityReferrals = latestRisks
    .filter((item) => item.risk_level === "HIGH")
    .reduce(
      (sum, item) =>
        sum +
        filteredChvs
          .filter((chv) => chv.ward === item.ward_id)
          .reduce((chvSum, chv) => chvSum + chv.referrals_24h, 0),
      0,
    );
  const activeReportingRate = totalChvs ? Math.round((activeChvs / totalChvs) * 100) : 0;
  const commandStatus = {
    assign: hasCriticalCoverageGap
      ? `${criticalCoverageGap?.wardName} stands out in the visible coverage summary`
      : "No visible wards stand out in the coverage summary",
    broadcast: alerts.length
      ? `${alerts.length} visible alert records are in this view`
      : "No visible alert records are in this view",
    training: `${registryRows.filter((row) => row.syncHealth !== "ONLINE").length} CHVs show delayed sync or offline status`,
  };

  const coverageShare = totalChvs ? Math.max(8, Math.round((activeChvs / totalChvs) * 100)) : 0;
  const totalVisibleLabel = isLoading ? "..." : totalChvs.toLocaleString();
  const activeVisibleLabel = isLoading ? "..." : activeChvs.toLocaleString();
  const casesVisibleLabel = isLoading ? "..." : highUrgencyCases.toLocaleString();
  const selectedMapWard = useMemo<WardMapFeature | null>(() => {
    if (!mapFeatures.length) {
      return null;
    }

    if (selectedWard !== "ALL") {
      return mapFeatures.find((feature) => feature.properties.backend_ward_id === Number(selectedWard.slice(3))) ?? null;
    }

    const highestPriority = mapFeatures
      .filter((feature) => feature.properties.risk_level === "HIGH")
      .sort((left, right) => right.properties.predicted_cases - left.properties.predicted_cases)[0];

    return highestPriority ?? mapFeatures[0];
  }, [mapFeatures, selectedWard]);
  const selectedWardCoverage = useMemo(
    () => (selectedMapWard ? getCoverageStatus(selectedMapWard) : null),
    [selectedMapWard],
  );
  const selectedWardRecords = useMemo(
    () =>
      selectedMapWard?.properties.backend_ward_id
        ? chvs.filter((chv) => chv.ward === selectedMapWard.properties.backend_ward_id)
        : [],
    [chvs, selectedMapWard],
  );
  const selectedWardLatestActivity = useMemo(
    () => getLatestTimestamp(selectedWardRecords.map((item) => item.last_activity_at).filter(Boolean)),
    [selectedWardRecords],
  );
  const selectedWardLatestSync = useMemo(
    () => getLatestTimestamp(selectedWardRecords.map((item) => item.last_sync_at).filter(Boolean)),
    [selectedWardRecords],
  );
  const selectedWardSyncFreshness = useMemo(
    () => describeFreshness(selectedWardLatestSync, STALE_THRESHOLD_MINUTES),
    [selectedWardLatestSync],
  );
  const selectedWardRiskLabel = selectedMapWard?.properties.risk_level
    ? toRiskZoneLabel(resolveRiskZone(selectedMapWard.properties.risk_level))
    : "No backend risk";
  const selectedWardPanelTone = selectedWardCoverage?.tone ?? "default";
  const selectedWardPanelClassName =
    selectedWardPanelTone === "danger"
      ? "border-[color:var(--danger)]/25 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--danger)_7%,white),white)]"
      : selectedWardPanelTone === "warning"
        ? "border-[color:var(--warning)]/28 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--warning)_8%,white),white)]"
        : selectedWardPanelTone === "success"
          ? "border-[color:var(--success)]/24 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--success)_7%,white),white)]"
          : "border-panel-table-wrap bg-white";

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Community Health Volunteers"
        subtitle="CHV activity summaries, sync status, and ward-linked engagement data"
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
      />

      <RoleGate
        allowedRoles={["ADMIN", "SUPERVISOR"]}
        title="CHV operations are role-restricted"
        message="Only Admin and Supervisor roles should use the CHV operations page."
      >
        {error ? (
          <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
            {error instanceof Error ? error.message : "Unable to load CHV operations."}
          </StatusBanner>
        ) : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card className="rounded-[2rem] px-5 py-5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Visible CHVs</span>
            <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">{totalVisibleLabel}</div>
            <p className="mt-4 text-sm text-panel-muted">Visible in the selected ward filter</p>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Visible active CHVs</span>
            <div className="mt-3 flex items-end gap-2">
              <strong className="text-4xl font-semibold leading-none text-panel-strong">{activeVisibleLabel}</strong>
              <span className="pb-1 text-sm font-medium text-panel-muted">/ {totalVisibleLabel}</span>
            </div>
            <div className="mt-4 h-2 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)]">
              <span
                className="block h-full rounded-full bg-brand"
                style={{ width: `${coverageShare}%` }}
                aria-hidden="true"
              />
            </div>
            <p className="mt-3 text-sm text-panel-muted">{activeReportingRate}% active in the selected filter</p>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">
              Alert delivery rate
            </span>
            <div className="mt-3 flex items-center gap-3">
              <strong className="text-4xl font-semibold leading-none text-panel-strong">{acknowledgedRate.toFixed(1)}%</strong>
              <StatusBadge tone="warning" className="tracking-[0.12em]">
                Calculated
              </StatusBadge>
            </div>
            <p className="mt-4 text-sm text-panel-muted">Calculated from visible alert delivery outcomes in this view</p>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">
              Recorded triage sessions (24h)
            </span>
            <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">{casesVisibleLabel}</div>
            <p className="mt-4 text-sm text-panel-muted">{highPriorityReferrals.toLocaleString()} referrals in high-risk wards (calculated)</p>
          </Card>
        </section>

        <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_22rem]">
          <Card className="overflow-hidden rounded-[2rem] p-5 sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-[clamp(1.6rem,1rem+1vw,2.35rem)] font-semibold leading-tight text-panel-strong">
                  CHV Ward Coverage
                </h2>
                <p className="mt-2 text-sm text-panel-muted">
                  Backend-backed Migori ward geometry with visible risk, CHV, alert, and facility counts
                </p>
                {wardMap ? (
                  <p className="mt-2 text-xs text-panel-subtle">
                    Geometry coverage: {wardMap.metadata.geometry_feature_count}/{wardMap.metadata.expected_ward_count} wards.
                    {wardMap.metadata.missing_source_wards.length
                      ? ` Source still lacks ${wardMap.metadata.missing_source_wards.join(", ")}.`
                      : ""}
                  </p>
                ) : null}
                {wardMap?.metadata.geometry_note ? (
                  <p className="mt-2 max-w-2xl text-xs text-[color:var(--warning)]">
                    {wardMap.metadata.geometry_note}
                  </p>
                ) : null}
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={cn(
                    "inline-flex h-10 items-center justify-center rounded-pill px-4 text-sm font-semibold transition",
                    focusFilter === "ALL"
                      ? "bg-brand text-white shadow-[var(--login-submit-shadow)]"
                      : "border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy",
                  )}
                  onClick={() => setFocusFilter("ALL")}
                >
                  All Wards
                </button>
                <button
                  type="button"
                  className={cn(
                    "inline-flex h-10 items-center justify-center rounded-pill px-4 text-sm font-semibold transition",
                    focusFilter === "HIGH_RISK"
                      ? "bg-brand text-white shadow-[var(--login-submit-shadow)]"
                      : "border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy",
                  )}
                  onClick={() => setFocusFilter("HIGH_RISK")}
                >
                  High-Risk Filter
                </button>
              </div>
            </div>

            <div className="relative mt-6 min-h-[30rem] overflow-hidden rounded-[1.75rem] border border-[#CBD5E1] bg-[#F6F9FC] p-5">
              <div className="relative z-10 grid h-full gap-4 lg:grid-cols-[minmax(0,1fr)_17rem]">
                <div className="min-h-[26rem] rounded-[1.5rem] border border-[#D9E2EC] bg-white/92 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
                  {mapFeatures.length ? (
                    <div className="flex h-full flex-col gap-4">
                      <div className="flex flex-wrap items-center gap-3 rounded-[1.25rem] border border-[#E2E8F0] bg-white/95 px-4 py-3 text-xs text-panel-copy">
                        <span className="inline-flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[#CBD5E1] bg-[#EEF6F2]" />
                          Safe / normal ward
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[#F59E0B] bg-[#FFF4E5]" />
                          Watch / medium risk
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[#DC2626] bg-[#FEE2E2]" />
                          High risk
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[#94A3B8] bg-[#F1F5F9]" />
                          Unmatched source
                        </span>
                      </div>

                      <div className="min-h-[22rem] flex-1">
                        <MigoriWardMap
                          features={mapFeatures}
                          selectedWardCode={selectedMapWard?.properties.ward_code ?? null}
                          focusHighRisk={focusFilter === "HIGH_RISK"}
                          onSelectWard={(feature) =>
                            feature.properties.backend_ward_id
                              ? setSelectedWard(`id:${feature.properties.backend_ward_id}`)
                              : undefined
                          }
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="flex h-full items-center justify-center rounded-[1.25rem] border border-dashed border-panel-table-wrap px-6 text-center text-sm text-panel-muted">
                      Ward geometry is not available for this scope yet.
                    </div>
                  )}
                </div>

                <Card className={cn("rounded-[1.5rem] border px-4 py-4 shadow-none", selectedWardPanelClassName)}>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Selected ward</span>
                  {selectedMapWard ? (
                    <div className="mt-4 space-y-4">
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h3 className="text-lg font-semibold text-panel-strong">{selectedMapWard.properties.name}</h3>
                            <p className="mt-1 text-sm text-panel-muted">{selectedWardRiskLabel}</p>
                          </div>
                          {selectedWardCoverage ? (
                            <StatusBadge tone={selectedWardCoverage.tone}>{selectedWardCoverage.label}</StatusBadge>
                          ) : null}
                        </div>
                        <p className="mt-3 text-sm text-panel-copy">
                          {selectedWardCoverage?.reason ??
                            "Select a ward to review CHV coverage relative to its recorded risk."}
                        </p>
                      </div>

                      <div className="rounded-[1.25rem] border border-white/70 bg-white/70 p-3">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                          Coverage status
                        </span>
                        <div className="mt-2 flex items-center justify-between gap-3">
                          <strong className="text-base text-panel-strong">
                            {selectedMapWard.properties.active_chv_count}/{selectedMapWard.properties.chv_count} active CHVs
                          </strong>
                          {selectedWardCoverage ? (
                            <StatusBadge tone={selectedWardCoverage.tone}>{selectedWardCoverage.label}</StatusBadge>
                          ) : null}
                        </div>
                      </div>

                      <div className="grid gap-3 text-sm text-panel-copy">
                        <div className="flex items-center justify-between gap-3">
                          <span>Recorded risk</span>
                          {selectedMapWard.properties.risk_level ? (
                            <StatusBadge tone={riskTone(resolveRiskZone(selectedMapWard.properties.risk_level))}>
                              {toRiskZoneLabel(resolveRiskZone(selectedMapWard.properties.risk_level))}
                            </StatusBadge>
                          ) : (
                            <StatusBadge tone="default">No backend risk</StatusBadge>
                          )}
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Active CHVs / total CHVs</span>
                          <strong className="text-panel-strong">
                            {selectedMapWard.properties.active_chv_count}/{selectedMapWard.properties.chv_count}
                          </strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Predicted cases</span>
                          <strong className="text-panel-strong">{selectedMapWard.properties.predicted_cases}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Open alert records</span>
                          <strong className="text-panel-strong">{selectedMapWard.properties.alert_count}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Active facilities</span>
                          <strong className="text-panel-strong">{selectedMapWard.properties.facility_count}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Last CHV activity</span>
                          <strong className="text-right text-panel-strong">
                            {selectedWardLatestActivity ? formatRelativeTimestamp(selectedWardLatestActivity) : "No recent activity"}
                          </strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Sync freshness</span>
                          <StatusBadge tone={selectedWardLatestSync ? (selectedWardSyncFreshness.isStale ? "warning" : "success") : "default"}>
                            {selectedWardLatestSync ? selectedWardSyncFreshness.label : "No sync recorded"}
                          </StatusBadge>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Ward code</span>
                          <strong className="text-panel-strong">{selectedMapWard.properties.ward_code}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Backend public ID</span>
                          <strong className="max-w-[10rem] truncate text-panel-strong">
                            {selectedMapWard.properties.backend_public_id ?? "Not matched"}
                          </strong>
                        </div>
                      </div>

                      <div className="space-y-3 border-t border-panel-table-wrap pt-4 text-sm text-panel-copy">
                        <div className="flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[color:color-mix(in_srgb,var(--brand)_34%,var(--panel-muted))] bg-[color:color-mix(in_srgb,var(--panel-muted)_10%,white)]" />
                          <span>Safe / normal ward</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[color:color-mix(in_srgb,var(--warning)_72%,black_6%)] bg-[color:color-mix(in_srgb,var(--warning)_18%,white)]" />
                          <span>Watch / medium recorded risk</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[color:color-mix(in_srgb,var(--danger)_72%,black_6%)] bg-[color:color-mix(in_srgb,var(--danger)_18%,white)]" />
                          <span>High recorded risk ward</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[color:color-mix(in_srgb,var(--panel-muted)_58%,white)] bg-[color:color-mix(in_srgb,var(--panel-muted)_16%,white)]" />
                          <span>Geometry-only / unmatched backend ward</span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-4 text-sm text-panel-muted">
                      Select a ward on the map to inspect its visible backend-backed counts.
                    </p>
                  )}
                </Card>
              </div>
            </div>
          </Card>

          <div className="space-y-5">
            <Card className="rounded-[2rem] px-5 py-5">
              <h2 className="text-2xl font-semibold text-panel-strong">Planning Summary</h2>
              <p className="mt-3 text-sm text-panel-muted">
                Assignment, alert count, and training notes below are calculated from visible records only. This page does not expose backend action routes for those actions.
              </p>

              <div className="mt-5 space-y-3">
                {[
                  {
                    icon: Users2,
                    title: "Ward coverage summary",
                    detail: commandStatus.assign,
                  },
                  {
                    icon: Megaphone,
                    title: "Alert count summary",
                    detail: commandStatus.broadcast,
                  },
                  {
                    icon: BriefcaseMedical,
                    title: "Training status summary",
                    detail: commandStatus.training,
                  },
                ].map((item) => (
                  <button
                    key={item.title}
                    type="button"
                    disabled
                    className="flex w-full items-center gap-3 rounded-[1.5rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-4 text-left"
                  >
                    <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                      <item.icon className="size-5" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <strong className="block text-base text-panel-strong">{item.title}</strong>
                      <small className="mt-1 block text-sm text-panel-muted">{item.detail}</small>
                    </span>
                    <span className="text-sm font-semibold text-panel-muted">Read only</span>
                  </button>
                ))}
              </div>
            </Card>

            <Card
              className={cn(
                "rounded-[2rem] px-5 py-5",
                hasCriticalCoverageGap
                  ? "border-[color:var(--warning)]/25 bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))]"
                  : "border-[color:var(--success)]/25 bg-[color-mix(in_srgb,var(--success)_6%,var(--panel))]",
              )}
            >
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    "inline-flex size-10 items-center justify-center rounded-full",
                    hasCriticalCoverageGap
                      ? "bg-[color-mix(in_srgb,var(--warning)_18%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]"
                      : "bg-[color-mix(in_srgb,var(--success)_18%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]",
                  )}
                >
                  <ShieldAlert className="size-4" aria-hidden="true" />
                </span>
                <h3 className="text-xl font-semibold text-panel-strong">
                  {hasCriticalCoverageGap ? "Coverage Note" : "Coverage Summary"}
                </h3>
              </div>
              <p className="mt-4 text-sm leading-6 text-panel-copy">
                {hasCriticalCoverageGap
                  ? `${criticalCoverageGap?.wardName} shows ${criticalCoverageGap?.activeCount} active CHV in visible records while the linked ward risk feed still shows ${criticalCoverageGap?.predictedCases} predicted cases.`
                  : "No CHV coverage difference stands out in the visible ward set."}
              </p>
              <Button className="mt-5 w-full justify-center" disabled>
                Redeployment unavailable
              </Button>
            </Card>
          </div>
        </section>

        <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <h2 className="text-[clamp(1.6rem,1rem+1vw,2.3rem)] font-semibold leading-tight text-panel-strong">
                CHV Personnel Registry
              </h2>
              <p className="mt-2 text-sm text-panel-muted">Recorded CHV identity, sync, alert, and ward-linked status fields</p>
            </div>

            <div className="flex min-w-0 flex-1 flex-col gap-4 xl:max-w-3xl xl:flex-row xl:flex-wrap xl:justify-end">
              <InputShell
                className="min-w-0 flex-[1.2]"
                icon={<Search className="size-4" aria-hidden="true" />}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by name..."
                aria-label="Search by name"
              />

              <label className="flex min-w-[12rem] flex-col">
                <span className="relative flex h-11 items-center rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 shadow-sm">
                  <select
                    value={selectedWard}
                    onChange={(event) => setSelectedWard(event.target.value as SelectedWardFilter)}
                    aria-label="Ward filter"
                    className="h-full w-full appearance-none bg-transparent pr-8 text-sm text-panel-strong outline-none"
                  >
                    {wardsForFilter.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </span>
              </label>

              <Button variant="secondary" size="icon" className="size-11" aria-label="More filters">
                <Filter className="size-4" aria-hidden="true" />
              </Button>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {[
              { value: "ALL", label: "All" },
              { value: "ACTIVE", label: "Active" },
              { value: "IDLE", label: "Idle" },
              { value: "OFFLINE", label: "Offline" },
              { value: "HIGH_RISK", label: "High-risk wards" },
            ].map((filterOption) => (
              <button
                key={filterOption.value}
                type="button"
                className={cn(
                  "inline-flex h-10 items-center justify-center rounded-pill border px-4 text-sm font-semibold transition",
                  quickFilter === filterOption.value
                    ? "border-brand bg-brand text-white shadow-[var(--login-submit-shadow)]"
                    : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong",
                )}
                onClick={() => setQuickFilter(filterOption.value as QuickFilter)}
              >
                {filterOption.label}
              </button>
            ))}
          </div>

          <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-panel-table-wrap">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-panel-table-wrap text-sm">
                <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]">
                  <tr className="text-left">
              {[
                  "Volunteer name",
                  "Ward",
                  "Status",
                  "Ward alerts (Total/Delivered)",
                  "Sync health",
                  "Last sync",
                  "Ward risk",
                      "Record",
                    ].map((label) => (
                      <th
                        key={label}
                        className="px-5 py-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle"
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-panel-table-wrap bg-panel">
                  {isLoading ? (
                    Array.from({ length: 3 }).map((_, index) => (
                      <tr key={`skeleton-${index}`}>
                        <td colSpan={8} className="px-5 py-5">
                          <div className="h-6 w-full animate-pulse rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                        </td>
                      </tr>
                    ))
                  ) : pagedRows.length ? (
                    pagedRows.map((row) => (
                      <tr
                        key={row.id}
                        onClick={() => setSelectedChvId(row.id)}
                        className="cursor-pointer transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_40%,transparent)]"
                      >
                        <td className="px-5 py-4 align-top">
                          <div className="flex items-center gap-3">
                            <span className="inline-flex size-11 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-sm font-semibold text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                              {row.initials}
                            </span>
                            <div>
                              <strong className="block text-base text-panel-strong">{row.name}</strong>
                              <small className="text-sm text-panel-muted">{row.rosterId}</small>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4 align-top text-panel-copy">{row.wardName}</td>
                        <td className="px-5 py-4 align-top">
                          <StatusBadge tone={statusTone(row.status)} className="tracking-[0.12em]">
                            {toTitleStatus(row.status)}
                          </StatusBadge>
                        </td>
                        <td className="px-5 py-4 align-top text-panel-copy">
                          {row.alertsRaised} / {row.alertsAcknowledged}
                        </td>
                        <td className="px-5 py-4 align-top">
                          <StatusBadge tone={syncTone(row.syncHealth)} className="tracking-[0.12em]">
                            {toSyncHealthLabel(row.syncHealth)}
                          </StatusBadge>
                        </td>
                        <td className="px-5 py-4 align-top text-panel-copy">{row.lastSync}</td>
                        <td className="px-5 py-4 align-top">
                          <StatusBadge tone={riskTone(row.riskZone)} className="tracking-[0.12em]">
                            {toRiskZoneLabel(row.riskZone)}
                          </StatusBadge>
                        </td>
                        <td className="px-5 py-4 align-top">
                          <div className="flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
                            <Button variant="ghost" className="h-9 rounded-pill px-3 text-sm" onClick={() => setSelectedChvId(row.id)}>
                              Open
                            </Button>
                            <Button variant="secondary" size="icon" className="size-9" aria-label={`Messaging unavailable for ${row.name}`} disabled>
                              <BellRing className="size-4" aria-hidden="true" />
                            </Button>
                            <Button variant="secondary" size="icon" className="size-9" aria-label={`Additional actions unavailable for ${row.name}`} disabled>
                              <MoreHorizontal className="size-4" aria-hidden="true" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={8} className="px-5 py-10 text-center text-sm text-panel-muted">
                        No CHVs match the selected filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-sm text-panel-muted">
              Showing {pagedRows.length} of {registryRows.length || 0} volunteers
            </span>
            {totalPages > 1 ? (
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="icon"
                  className="size-10"
                  onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                  disabled={clampedPage === 1}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="size-4" aria-hidden="true" />
                </Button>
                <Button
                  variant="secondary"
                  size="icon"
                  className="size-10"
                  onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                  disabled={clampedPage === totalPages}
                  aria-label="Next page"
                >
                  <ChevronRight className="size-4" aria-hidden="true" />
                </Button>
              </div>
            ) : null}
          </div>
        </Card>

        {selectedChv ? (
          <>
            <button
              type="button"
              className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-[1px]"
              aria-label="Close CHV detail drawer"
              onClick={() => setSelectedChvId(null)}
            />
            <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[30rem] flex-col border-l border-panel-border bg-panel shadow-2xl">
              <div className="flex items-start justify-between gap-4 border-b border-panel-table-wrap px-5 py-5 sm:px-6">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">CHV detail</span>
                  <h2 className="mt-2 text-2xl font-semibold text-panel-strong">{selectedChv.name}</h2>
                  <p className="mt-1 text-sm text-panel-muted">
                    {selectedChv.rosterId} · {selectedChv.wardName}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-10 shrink-0"
                  onClick={() => setSelectedChvId(null)}
                  aria-label="Close CHV detail"
                >
                  <X className="size-4" aria-hidden="true" />
                </Button>
              </div>

              <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-6">
                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    ["Status", toTitleStatus(selectedChv.status)],
                    ["Sync health", toSyncHealthLabel(selectedChv.syncHealth)],
                    ["Ward alerts", `${selectedChv.alertsRaised} total / ${selectedChv.alertsAcknowledged} delivered`],
                    ["Ward risk", toRiskZoneLabel(selectedChv.riskZone)],
                  ].map(([label, value]) => (
                    <Card key={label} className="rounded-2xl px-4 py-4 shadow-none">
                      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">{label}</span>
                      <strong className="mt-2 block text-base text-panel-strong">{value}</strong>
                    </Card>
                  ))}
                </div>

                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Field profile</h3>
                  <ul className="mt-4 space-y-3 text-sm text-panel-copy">
                    <li className="flex items-center gap-3">
                      <Smartphone className="size-4 text-panel-muted" aria-hidden="true" />
                      {selectedChv.phoneNumber}
                    </li>
                    <li className="flex items-center gap-3">
                      <Activity className="size-4 text-panel-muted" aria-hidden="true" />
                      Language: {selectedChv.language}
                    </li>
                    <li className="flex items-center gap-3">
                      {selectedChv.syncHealth === "OFFLINE" ? (
                        <WifiOff className="size-4 text-panel-muted" aria-hidden="true" />
                      ) : (
                        <Wifi className="size-4 text-panel-muted" aria-hidden="true" />
                      )}
                      Connectivity: {toSyncHealthLabel(selectedChv.syncHealth)}
                    </li>
                    <li className="flex items-center gap-3">
                      <Clock3 className="size-4 text-panel-muted" aria-hidden="true" />
                      Last sync: {selectedChv.lastSync}
                    </li>
                  </ul>
                </Card>

                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recorded activity</h3>
                  <p className="mt-3 text-sm leading-6 text-panel-copy">
                    Recent activity for {selectedChv.wardName} is derived from backend sync, triage, and USSD traces. Last activity was{" "}
                    {selectedChv.lastProtocolUpdate}, and this CHV is marked as{" "}
                    {selectedChv.status === "ACTIVE" ? "active in visible records." : selectedChv.status === "IDLE" ? "idle in visible records." : "offline in visible records."}
                  </p>
                </Card>
              </div>

              <div className="flex flex-col gap-3 border-t border-panel-table-wrap px-5 py-5 sm:px-6">
                <p className="text-sm text-panel-muted">
                  Messaging, reassignment, and detailed history actions are unavailable from this screen because the corresponding backend routes are not exposed here.
                </p>
                <Button className="w-full justify-center" disabled>
                  <BellRing className="size-4" aria-hidden="true" />
                  Messaging unavailable
                </Button>
                <Button variant="secondary" className="w-full justify-center" disabled>
                  <Users2 className="size-4" aria-hidden="true" />
                  Reassignment unavailable
                </Button>
                <Button variant="secondary" className="w-full justify-center" disabled>
                  <Activity className="size-4" aria-hidden="true" />
                  Activity history unavailable
                </Button>
              </div>
            </aside>
          </>
        ) : null}
      </RoleGate>
    </div>
  );
}
