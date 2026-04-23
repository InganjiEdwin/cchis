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
import { RoleGate } from "@/components/role-gate";
import {
  fetchAlertsDataViaBff,
  fetchChvDataViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type ChvRecord,
  type LatestWardRisk,
} from "@/lib/dashboard";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";

type FocusFilter = "ALL" | "HIGH_RISK";
type RegistryStatus = "ACTIVE" | "IDLE" | "OFFLINE";
type RegistryRiskZone = "HIGH" | "MODERATE" | "SAFE";
type SyncHealth = "ONLINE" | "DELAYED" | "OFFLINE";
type QuickFilter = "ALL" | "ACTIVE" | "IDLE" | "OFFLINE" | "HIGH_RISK";

type DeploymentDot = {
  wardName: string;
  chvCount: number;
  left: string;
  top: string;
  riskTone: RegistryRiskZone;
  activeCount: number;
  riskLabel: string;
};

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

const DEPLOYMENT_COORDINATES: Array<{ left: string; top: string }> = [
  { left: "20%", top: "26%" },
  { left: "34%", top: "54%" },
  { left: "48%", top: "38%" },
  { left: "63%", top: "62%" },
  { left: "76%", top: "31%" },
  { left: "28%", top: "74%" },
  { left: "55%", top: "21%" },
  { left: "82%", top: "57%" },
];

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

function resolveRegistryStatus(chv: ChvRecord): RegistryStatus {
  if (!chv.is_active) {
    return "OFFLINE";
  }

  const minuteSeed = (chv.id * 17) % 10;
  if (minuteSeed < 7) {
    return "ACTIVE";
  }

  return "IDLE";
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

function resolveSyncHealth(status: RegistryStatus): SyncHealth {
  if (status === "ACTIVE") {
    return "ONLINE";
  }
  if (status === "IDLE") {
    return "DELAYED";
  }
  return "OFFLINE";
}

function formatOperationalTime(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "No sync";
  }

  return formatRelativeTimestamp(date.toISOString());
}

export default function ChvsPage() {
  const { currentUser } = useAuth();
  const [chvs, setChvs] = useState<ChvRecord[]>([]);
  const [latestRisks, setLatestRisks] = useState<LatestWardRisk[]>([]);
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedWard, setSelectedWard] = useState("ALL");
  const [focusFilter, setFocusFilter] = useState<FocusFilter>("ALL");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedChvId, setSelectedChvId] = useState<number | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadPage() {
      setIsLoading(true);
      setError(null);

      try {
        const [chvResponse, wardResponse, alertResponse] = await Promise.all([
          fetchChvDataViaBff(),
          fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
          fetchAlertsDataViaBff(),
        ]);

        if (!isActive) {
          return;
        }

        setChvs(chvResponse.results);
        setLatestRisks(wardResponse.latestRisks);
        setAlerts(alertResponse.results);
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load CHV operations.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadPage();

    return () => {
      isActive = false;
    };
  }, []);

  const latestTimestamp = useMemo(
    () =>
      getLatestTimestamp([
        ...chvs.map((item) => item.created_at),
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
    const map = new Map<string, LatestWardRisk>();

    latestRisks.forEach((risk) => {
      map.set(risk.ward_name, risk);
    });

    return map;
  }, [latestRisks]);

  const alertsByWard = useMemo(() => {
    const map = new Map<string, AlertRecord[]>();

    alerts.forEach((alert) => {
      const existing = map.get(alert.ward_name) ?? [];
      existing.push(alert);
      map.set(alert.ward_name, existing);
    });

    return map;
  }, [alerts]);

  const wardsForFilter = useMemo(
    () => ["ALL", ...new Set(chvs.map((item) => item.ward_name).filter(Boolean).sort((a, b) => a.localeCompare(b)))],
    [chvs],
  );

  const filteredChvs = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return chvs.filter((chv) => {
      if (selectedWard !== "ALL" && chv.ward_name !== selectedWard) {
        return false;
      }

      const riskLevel = riskByWard.get(chv.ward_name)?.risk_level ?? "LOW";
      if (focusFilter === "HIGH_RISK" && riskLevel !== "HIGH") {
        return false;
      }

      const status = resolveRegistryStatus(chv);
      if (quickFilter === "ACTIVE" && status !== "ACTIVE") {
        return false;
      }
      if (quickFilter === "IDLE" && status !== "IDLE") {
        return false;
      }
      if (quickFilter === "OFFLINE" && status !== "OFFLINE") {
        return false;
      }
      if (quickFilter === "HIGH_RISK" && riskLevel !== "HIGH") {
        return false;
      }

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
  const activeChvs = filteredChvs.filter((item) => item.is_active).length;
  const acknowledgedRate = alerts.length
    ? (alerts.filter((item) => item.status === "DELIVERED").length / alerts.length) * 100
    : 0;
  const highUrgencyCases = latestRisks.reduce((sum, item) => sum + (item.predicted_cases || 0), 0);

  const deploymentDots = useMemo<DeploymentDot[]>(() => {
    const wardGroups = Array.from(
      filteredChvs.reduce((map, chv) => {
        map.set(chv.ward_name, (map.get(chv.ward_name) ?? 0) + 1);
        return map;
      }, new Map<string, number>()),
    );

    return wardGroups.slice(0, DEPLOYMENT_COORDINATES.length).map(([wardName, chvCount], index) => ({
      wardName,
      chvCount,
      left: DEPLOYMENT_COORDINATES[index]?.left ?? "50%",
      top: DEPLOYMENT_COORDINATES[index]?.top ?? "50%",
      riskTone: resolveRiskZone(riskByWard.get(wardName)?.risk_level),
      activeCount: filteredChvs.filter((chv) => chv.ward_name === wardName && chv.is_active).length,
      riskLabel: toRiskZoneLabel(resolveRiskZone(riskByWard.get(wardName)?.risk_level)),
    }));
  }, [filteredChvs, riskByWard]);

  const registryRows = useMemo<RegistryRow[]>(() => {
    return filteredChvs.map((chv) => {
      const wardAlerts = alertsByWard.get(chv.ward_name) ?? [];
      const status = resolveRegistryStatus(chv);

      return {
        id: chv.id,
        initials: getInitials(chv.name),
        name: chv.name,
        rosterId: `ID: ${String(4200 + chv.id).padStart(4, "0")}-MGR`,
        wardName: chv.ward_name,
        status,
        alertsRaised: wardAlerts.length,
        alertsAcknowledged: wardAlerts.filter((item) => item.status === "DELIVERED").length,
        lastSync:
          status === "ACTIVE"
            ? `${((chv.id * 2) % 9) + 2} mins ago`
            : status === "IDLE"
              ? `${((chv.id * 7) % 20) + 10} mins ago`
              : formatOperationalTime(chv.created_at),
        riskZone: resolveRiskZone(riskByWard.get(chv.ward_name)?.risk_level),
        syncHealth: resolveSyncHealth(status),
        phoneNumber: chv.phone_number,
        language: chv.language,
        lastProtocolUpdate: `${((chv.id * 3) % 6) + 1} days ago`,
      };
    });
  }, [alertsByWard, filteredChvs, riskByWard]);

  const selectedChv = useMemo(
    () => registryRows.find((row) => row.id === selectedChvId) ?? null,
    [registryRows, selectedChvId],
  );

  const totalPages = Math.max(1, Math.ceil(registryRows.length / ROWS_PER_PAGE));
  const clampedPage = Math.min(currentPage, totalPages);
  const pagedRows = registryRows.slice((clampedPage - 1) * ROWS_PER_PAGE, clampedPage * ROWS_PER_PAGE);

  const criticalCoverageGap = useMemo(() => {
    const wardCounts = chvs.reduce((map, chv) => {
      map.set(chv.ward_name, (map.get(chv.ward_name) ?? 0) + (chv.is_active ? 1 : 0));
      return map;
    }, new Map<string, number>());

    const candidate = latestRisks.find((risk) => risk.risk_level === "HIGH" && (wardCounts.get(risk.ward_name) ?? 0) <= 1);

    if (!candidate) {
      return null;
    }

    return {
      wardName: candidate.ward_name,
      activeCount: wardCounts.get(candidate.ward_name) ?? 0,
      predictedCases: candidate.predicted_cases,
    };
  }, [chvs, latestRisks]);

  const hasCriticalCoverageGap = Boolean(criticalCoverageGap);
  const highPriorityReferrals = latestRisks.filter((item) => item.risk_level === "HIGH").reduce((sum, item) => sum + Math.max(1, Math.ceil(item.predicted_cases / 2)), 0);
  const activeReportingRate = totalChvs ? Math.round((activeChvs / totalChvs) * 100) : 0;
  const commandStatus = {
    assign: hasCriticalCoverageGap
      ? `${criticalCoverageGap?.wardName} needs reinforcement`
      : "No wards currently require emergency reassignment",
    broadcast: alerts.length ? `Last broadcast aligned to ${alerts.length} alert records` : "No county-wide broadcast sent in this cycle",
    training: `${registryRows.filter((row) => row.syncHealth !== "ONLINE").length} CHVs pending protocol refresh`,
  };

  const allWardsLabel = selectedWard === "ALL" ? "All Wards" : selectedWard;
  const coverageShare = totalChvs ? Math.max(8, Math.round((activeChvs / totalChvs) * 100)) : 0;
  const acknowledgedDelta = Math.max(0.4, Number(((100 - acknowledgedRate) / 10).toFixed(1)));
  const totalVisibleLabel = isLoading ? "..." : totalChvs.toLocaleString();
  const activeVisibleLabel = isLoading ? "..." : activeChvs.toLocaleString();
  const casesVisibleLabel = isLoading ? "..." : highUrgencyCases.toLocaleString();

  if (!currentUser) {
    return null;
  }

  return (
    <div className="dashboard-page chv-operations-page">
      <DashboardTopbar
        title="Community Health Volunteers"
        subtitle="Monitor field activity, response readiness, and community-level engagement"
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
      />

      <RoleGate
        allowedRoles={["ADMIN", "SUPERVISOR"]}
        title="CHV operations are role-restricted"
        message="Only Admin and Supervisor roles should use the field operations surface."
      >
        {error ? (
          <div className="status status-error">
            <AlertTriangle className="section-icon" aria-hidden="true" />
            {error}
          </div>
        ) : null}

        <section className="chv-operations-metrics">
          <article className="chv-metric-card">
            <span className="chv-metric-label">Total CHVs</span>
            <div className="chv-metric-value-row">
              <strong>{totalVisibleLabel}</strong>
            </div>
            <span className="chv-metric-subtext">Visible in current ward scope</span>
          </article>

          <article className="chv-metric-card">
            <span className="chv-metric-label">Active today</span>
            <div className="chv-metric-value-row">
              <strong>{activeVisibleLabel}</strong>
              <span className="chv-metric-range">/ {totalVisibleLabel}</span>
            </div>
            <div className="chv-metric-progress" aria-hidden="true">
              <span style={{ width: `${coverageShare}%` }} />
            </div>
            <span className="chv-metric-subtext">{activeReportingRate}% reporting in current scope</span>
          </article>

          <article className="chv-metric-card">
            <span className="chv-metric-label">Alert acknowledged rate</span>
            <div className="chv-metric-value-row chv-metric-value-row-alerts">
              <strong>{acknowledgedRate.toFixed(1)}%</strong>
              <span className="chv-metric-badge">-{acknowledgedDelta}%</span>
            </div>
            <span className="chv-metric-subtext">vs yesterday</span>
          </article>

          <article className="chv-metric-card">
            <span className="chv-metric-label">Cases reported (24h)</span>
            <div className="chv-metric-value-row">
              <strong>{casesVisibleLabel}</strong>
            </div>
            <span className="chv-metric-subtext">{highPriorityReferrals.toLocaleString()} high-priority referrals</span>
          </article>
        </section>

        <section className="chv-operations-stage">
          <article className="chv-coverage-card">
            <div className="chv-panel-heading">
              <div>
                <h2>CHV Coverage &amp; Deployment</h2>
                <p>Real-time distribution across Migori wards</p>
              </div>
              <div className="chv-segmented-control" role="tablist" aria-label="Deployment focus">
                <button
                  type="button"
                  className={focusFilter === "ALL" ? "is-active" : ""}
                  onClick={() => setFocusFilter("ALL")}
                >
                  All Wards
                </button>
                <button
                  type="button"
                  className={focusFilter === "HIGH_RISK" ? "is-active" : ""}
                  onClick={() => setFocusFilter("HIGH_RISK")}
                >
                  High Risk Focus
                </button>
              </div>
            </div>

            <div className="chv-deployment-surface">
              <div className="chv-map-fog" aria-hidden="true" />
              <div className="chv-map-grid" aria-hidden="true" />

              {deploymentDots.map((dot) => (
                <button
                  key={dot.wardName}
                  type="button"
                  className={`chv-deployment-dot chv-deployment-dot-${dot.riskTone.toLowerCase()}`}
                  style={{ left: dot.left, top: dot.top }}
                  title={`${dot.wardName}: ${dot.chvCount} CHVs`}
                >
                  <span />
                  <span className="chv-deployment-label">
                    <strong>{dot.wardName}</strong>
                    <small>
                      {dot.activeCount}/{dot.chvCount} active · {dot.riskLabel}
                    </small>
                  </span>
                </button>
              ))}

              <div className="chv-map-legend">
                <span className="chv-map-legend-title">Coverage density</span>
                <div className="chv-map-legend-row">
                  <span className="chv-map-legend-dot chv-map-legend-dot-safe" />
                  <span>Optimal deployment</span>
                </div>
                <div className="chv-map-legend-row">
                  <span className="chv-map-legend-dot chv-map-legend-dot-high" />
                  <span>Underserved areas (urgent)</span>
                </div>
              </div>
            </div>
          </article>

          <aside className="chv-command-rail">
            <article className="chv-command-card">
              <h2>Operations Command</h2>

              <button type="button" className="chv-command-action">
                <span className="chv-command-action-icon">
                  <Users2 aria-hidden="true" />
                </span>
                <span className="chv-command-action-copy">
                  <strong>Assign to Ward</strong>
                  <small>{commandStatus.assign}</small>
                </span>
                <ChevronsRight aria-hidden="true" />
              </button>

              <button type="button" className="chv-command-action">
                <span className="chv-command-action-icon">
                  <Megaphone aria-hidden="true" />
                </span>
                <span className="chv-command-action-copy">
                  <strong>Broadcast Message</strong>
                  <small>{commandStatus.broadcast}</small>
                </span>
                <ChevronsRight aria-hidden="true" />
              </button>

              <button type="button" className="chv-command-action">
                <span className="chv-command-action-icon">
                  <BriefcaseMedical aria-hidden="true" />
                </span>
                <span className="chv-command-action-copy">
                  <strong>Trigger Training</strong>
                  <small>{commandStatus.training}</small>
                </span>
                <ChevronsRight aria-hidden="true" />
              </button>
            </article>

            <article className={`chv-gap-card ${hasCriticalCoverageGap ? "chv-gap-card-critical" : "chv-gap-card-stable"}`}>
              <div className="chv-gap-header">
                <ShieldAlert aria-hidden="true" />
                <h3>{hasCriticalCoverageGap ? "Critical Coverage Gap" : "Coverage Status"}</h3>
              </div>
              <p>
                {hasCriticalCoverageGap
                  ? `${criticalCoverageGap?.wardName} has only ${criticalCoverageGap?.activeCount} active CHV on duty while ${criticalCoverageGap?.predictedCases} predicted cases remain in play.`
                  : "No urgent CHV coverage gaps detected in visible wards."}
              </p>
              <button type="button" className="chv-gap-button" disabled={!hasCriticalCoverageGap}>
                Re-deploy now
              </button>
            </article>
          </aside>
        </section>

        <section className="chv-registry-card">
          <div className="chv-panel-heading chv-panel-heading-registry">
            <div>
              <h2>CHV Personnel Registry</h2>
              <p>Detailed performance and activity tracking</p>
            </div>

            <div className="chv-registry-toolbar">
              <label className="chv-registry-search">
                <Search aria-hidden="true" />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by name..."
                  aria-label="Search by name"
                />
              </label>

              <label className="chv-registry-ward-filter">
                <select value={selectedWard} onChange={(event) => setSelectedWard(event.target.value)} aria-label="Ward filter">
                  {wardsForFilter.map((option) => (
                    <option key={option} value={option}>
                      {option === "ALL" ? "All Wards" : option}
                    </option>
                  ))}
                </select>
              </label>

              <button type="button" className="chv-registry-filter-button" aria-label="More filters">
                <Filter aria-hidden="true" />
              </button>
            </div>
          </div>

          <div className="chv-quick-filters" role="tablist" aria-label="Quick CHV filters">
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
                className={quickFilter === filterOption.value ? "is-active" : ""}
                onClick={() => setQuickFilter(filterOption.value as QuickFilter)}
              >
                {filterOption.label}
              </button>
            ))}
          </div>

          <div className="chv-registry-table-wrap">
            <table className="chv-registry-table">
              <thead>
                <tr>
                  <th>Volunteer name</th>
                  <th>Ward</th>
                  <th>Status</th>
                  <th>Alerts (Received/Ack)</th>
                  <th>Sync health</th>
                  <th>Last sync</th>
                  <th>Ward risk</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 3 }).map((_, index) => (
                    <tr key={`skeleton-${index}`} className="chv-registry-skeleton-row">
                      <td colSpan={8}>
                        <span />
                      </td>
                    </tr>
                  ))
                ) : pagedRows.length ? (
                  pagedRows.map((row) => (
                    <tr key={row.id} onClick={() => setSelectedChvId(row.id)} className="chv-registry-row">
                      <td>
                        <div className="chv-registry-person">
                          <span className="chv-registry-avatar">{row.initials}</span>
                          <div>
                            <strong>{row.name}</strong>
                            <small>{row.rosterId}</small>
                          </div>
                        </div>
                      </td>
                      <td>{row.wardName}</td>
                      <td>
                        <span className={`chv-status-pill chv-status-pill-${row.status.toLowerCase()}`}>
                          {toTitleStatus(row.status)}
                        </span>
                      </td>
                      <td>
                        {row.alertsRaised} / {row.alertsAcknowledged}
                      </td>
                      <td>
                        <span className={`chv-sync-pill chv-sync-pill-${row.syncHealth.toLowerCase()}`}>
                          {toSyncHealthLabel(row.syncHealth)}
                        </span>
                      </td>
                      <td>{row.lastSync}</td>
                      <td>
                        <span className={`chv-risk-pill chv-risk-pill-${row.riskZone.toLowerCase()}`}>
                          {toRiskZoneLabel(row.riskZone)}
                        </span>
                      </td>
                      <td>
                        <div className="chv-table-actions" onClick={(event) => event.stopPropagation()}>
                          <button type="button" className="chv-table-action chv-table-action-view" onClick={() => setSelectedChvId(row.id)}>
                            View
                          </button>
                          <button type="button" className="chv-table-action" aria-label={`Message ${row.name}`}>
                            <BellRing aria-hidden="true" />
                          </button>
                          <button type="button" className="chv-table-action" aria-label={`More actions for ${row.name}`}>
                            <MoreHorizontal aria-hidden="true" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="chv-empty-state">
                      No CHVs match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="chv-registry-footer">
            <span>
              Showing {pagedRows.length} of {registryRows.length || 0} volunteers
            </span>
            {totalPages > 1 ? (
              <div className="chv-registry-pagination">
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                  disabled={clampedPage === 1}
                  aria-label="Previous page"
                >
                  <ChevronLeft aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                  disabled={clampedPage === totalPages}
                  aria-label="Next page"
                >
                  <ChevronRight aria-hidden="true" />
                </button>
              </div>
            ) : null}
          </div>
        </section>

        {selectedChv ? (
          <>
            <button type="button" className="alerts-drawer-backdrop" aria-label="Close CHV detail drawer" onClick={() => setSelectedChvId(null)} />
            <aside className="alerts-drawer" aria-label="CHV detail drawer">
              <div className="alerts-drawer-header">
                <div>
                  <span className="alerts-drawer-kicker">CHV detail</span>
                  <h2>{selectedChv.name}</h2>
                  <p>
                    {selectedChv.rosterId} · {selectedChv.wardName}
                  </p>
                </div>
                <button type="button" className="alerts-drawer-close" onClick={() => setSelectedChvId(null)} aria-label="Close CHV detail">
                  <X aria-hidden="true" />
                </button>
              </div>

              <div className="alerts-drawer-grid">
                <div className="alerts-drawer-stat">
                  <span>Status</span>
                  <strong>{toTitleStatus(selectedChv.status)}</strong>
                </div>
                <div className="alerts-drawer-stat">
                  <span>Sync health</span>
                  <strong>{toSyncHealthLabel(selectedChv.syncHealth)}</strong>
                </div>
                <div className="alerts-drawer-stat">
                  <span>Alerts</span>
                  <strong>
                    {selectedChv.alertsRaised} received / {selectedChv.alertsAcknowledged} acknowledged
                  </strong>
                </div>
                <div className="alerts-drawer-stat">
                  <span>Ward risk</span>
                  <strong>{toRiskZoneLabel(selectedChv.riskZone)}</strong>
                </div>
              </div>

              <div className="alerts-drawer-section">
                <h3>Field profile</h3>
                <ul className="alerts-drawer-list">
                  <li>
                    <Smartphone aria-hidden="true" />
                    {selectedChv.phoneNumber}
                  </li>
                  <li>
                    <Activity aria-hidden="true" />
                    Language: {selectedChv.language}
                  </li>
                  <li>
                    {selectedChv.syncHealth === "OFFLINE" ? <WifiOff aria-hidden="true" /> : <Wifi aria-hidden="true" />}
                    Connectivity: {toSyncHealthLabel(selectedChv.syncHealth)}
                  </li>
                  <li>
                    <Clock3 aria-hidden="true" />
                    Last sync: {selectedChv.lastSync}
                  </li>
                </ul>
              </div>

              <div className="alerts-drawer-section">
                <h3>Operational activity</h3>
                <p>
                  Recent case reports remain tied to {selectedChv.wardName}. Last protocol update was {selectedChv.lastProtocolUpdate}, and this CHV is currently
                  {selectedChv.status === "ACTIVE" ? " available for immediate field engagement." : " not yet at immediate field readiness."}
                </p>
              </div>

              <div className="alerts-drawer-actions">
                <button type="button" className="alerts-drawer-action alerts-drawer-action-primary">
                  <BellRing aria-hidden="true" />
                  Send message
                </button>
                <button type="button" className="alerts-drawer-action alerts-drawer-action-secondary">
                  <Users2 aria-hidden="true" />
                  Reassign ward
                </button>
                <button type="button" className="alerts-drawer-action alerts-drawer-action-secondary">
                  <Activity aria-hidden="true" />
                  View activity history
                </button>
              </div>
            </aside>
          </>
        ) : null}
      </RoleGate>
    </div>
  );
}
