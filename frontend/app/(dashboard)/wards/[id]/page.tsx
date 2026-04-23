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
  Zap,
  Waves,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import {
  fetchWardDetailViaBff,
  type AlertRecord,
  type RiskScoreRecord,
} from "@/lib/dashboard";
import { canTriggerAlerts } from "@/lib/roles";

type WardRiskLevel = "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
type DriverTone = "critical" | "warning" | "watch";

type RiskDriver = {
  icon: "rainfall" | "flood" | "outbreak" | "status";
  text: string;
  tone: DriverTone;
};

type WardDetailState = {
  wardId: number;
  wardName: string;
  wardCode: string | null;
  county: string;
  subCounty: string;
  riskLevel: WardRiskLevel;
  riskScore: number | null;
  predictedCases: number;
  updatedAt: string | null;
  source: string | null;
  modelVersion: string | null;
  riskHistory: RiskScoreRecord[];
  relatedAlerts: AlertRecord[];
};

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
  if (!timestamp) {
    return "No recent update";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const diffMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));

  if (diffMinutes < 1) {
    return "Just now";
  }
  if (diffMinutes === 1) {
    return "1 min ago";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} min ago`;
  }

  const diffHours = Math.round(diffMinutes / 60);

  if (diffHours === 1) {
    return "1 hr ago";
  }
  if (diffHours < 24) {
    return `${diffHours} hr ago`;
  }

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

  return `${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} (${formatRelativeMinutes(timestamp)})`;
}

function isStaleTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return true;
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return true;
  }

  return (Date.now() - date.getTime()) / 60000 > STALE_THRESHOLD_MINUTES;
}

function formatRiskLevel(riskLevel: WardRiskLevel) {
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

function buildOperationalRecommendations(riskLevel: WardRiskLevel) {
  switch (riskLevel) {
    case "HIGH":
      return [
        "Send CHV alert and confirm the escalation channel is active.",
        "Activate hygiene and safe-water messaging for this ward immediately.",
        "Review ORS and dehydration-response readiness with field teams.",
        "Monitor flood, water contamination, and outbreak signals closely over the next cycle.",
      ];
    case "MEDIUM":
      return [
        "Increase surveillance cadence and review the next risk update promptly.",
        "Prepare CHV messaging in case the ward escalates to high risk.",
        "Check field reporting continuity and local readiness for rapid response.",
      ];
    case "LOW":
      return [
        "Continue routine surveillance and keep this ward in the standard monitoring queue.",
        "Verify reporting continuity so trend changes are detected early.",
        "Watch for rapid movement in rainfall, flood proxy, or predicted case signals.",
      ];
    default:
      return [
        "Keep this ward under observation until fresher risk data is available.",
        "Review reporting continuity and confirm the next model run lands as expected.",
      ];
  }
}

function buildRiskDrivers(detail: WardDetailState | null): RiskDriver[] {
  if (!detail || detail.riskHistory.length === 0) {
    return [
      {
        icon: "status",
        text: "Recent driver detail is not yet available from the backend feed.",
        tone: "watch",
      },
    ];
  }

  const latestRisk = detail.riskHistory[0];
  const drivers: RiskDriver[] = [];

  if (latestRisk.rainfall_mm > 80) {
    drivers.push({
      icon: "rainfall",
      text: `Rainfall threshold is elevated at ${latestRisk.rainfall_mm.toFixed(0)} mm.`,
      tone: "critical",
    });
  }
  if (latestRisk.flood_indicator > 0) {
    drivers.push({
      icon: "flood",
      text: "Flood proxy is elevated in the latest model run.",
      tone: "warning",
    });
  }
  if (latestRisk.predicted_cases > 0) {
    drivers.push({
      icon: "outbreak",
      text: `Predicted cases remain elevated at ${latestRisk.predicted_cases}.`,
      tone: "watch",
    });
  }
  if (latestRisk.model_run_status) {
    drivers.push({
      icon: "status",
      text: `Latest model run status: ${latestRisk.model_run_status.toLowerCase()}.`,
      tone: latestRisk.model_run_status.toLowerCase() === "success" ? "critical" : "watch",
    });
  }

  return drivers.length > 0
    ? drivers
    : [
        {
          icon: "status",
          text: "Current monitoring is based on the latest available model run for this ward.",
          tone: "watch",
        },
      ];
}

function getRiskDriverIcon(driver: RiskDriver) {
  switch (driver.icon) {
    case "rainfall":
      return <Droplets aria-hidden="true" />;
    case "flood":
      return <Waves aria-hidden="true" />;
    case "outbreak":
      return <History aria-hidden="true" />;
    case "status":
    default:
      return <Clock3 aria-hidden="true" />;
  }
}

function getTrend(detail: WardDetailState | null) {
  if (!detail || detail.riskHistory.length < 2) {
    return {
      label: "No previous run available",
      tone: "neutral" as const,
      value: null as number | null,
    };
  }

  const currentScore = normalizeRiskScore(detail.riskHistory[0].score);
  const previousScore = normalizeRiskScore(detail.riskHistory[1].score);
  const delta = currentScore - previousScore;

  if (Math.abs(delta) < 1) {
    return {
      label: "Stable versus previous run",
      tone: "neutral" as const,
      value: 0,
    };
  }

  return {
    label: `${delta > 0 ? "+" : ""}${Math.round(delta)} points vs previous run`,
    tone: delta > 0 ? ("up" as const) : ("down" as const),
    value: delta,
  };
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

  if (!current || !previous) {
    return "flat" as const;
  }

  if (normalizeRiskScore(current.score) > normalizeRiskScore(previous.score)) {
    return "up" as const;
  }

  if (normalizeRiskScore(current.score) < normalizeRiskScore(previous.score)) {
    return "down" as const;
  }

  return "flat" as const;
}

export default function WardDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const { currentUser } = useAuth();
  const [detail, setDetail] = useState<WardDetailState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [isAlertsLoading, setIsAlertsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const wardId = useMemo(() => Number(params.id), [params.id]);
  const returnTo = useMemo(() => getSafeReturnTo(searchParams.get("returnTo")), [searchParams]);

  useEffect(() => {
    if (!currentUser || !Number.isFinite(wardId)) {
      return;
    }
    let isActive = true;

    async function loadDetail() {
      setIsLoading(true);
      setIsHistoryLoading(true);
      setIsAlertsLoading(true);
      setError(null);
      setHistoryError(null);
      setAlertsError(null);

      try {
        const response = await fetchWardDetailViaBff(wardId);

        if (!isActive) {
          return;
        }

        const riskHistory = response.riskHistory.results;
        const relatedAlerts = response.alerts.results;
        const latestHistory = riskHistory[0] ?? null;

        setDetail({
          wardId,
          wardName: response.ward.name,
          wardCode: response.ward.ward_code ?? null,
          county: response.ward.county,
          subCounty: response.ward.sub_county,
          riskLevel:
            latestHistory?.risk_level ??
            response.ward.current_risk_level ??
            "UNKNOWN",
          riskScore:
            latestHistory?.score ??
            response.ward.current_risk_score ??
            null,
          predictedCases: latestHistory?.predicted_cases ?? response.ward.predicted_cases ?? 0,
          updatedAt:
            latestHistory?.generated_at ??
            response.ward.latest_generated_at ??
            response.ward.updated_at ??
            null,
          source: latestHistory?.source ?? response.ward.latest_source ?? null,
          modelVersion: latestHistory?.model_version ?? response.ward.latest_model_version ?? null,
          riskHistory,
          relatedAlerts,
        });
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setDetail(null);
        setError(loadError instanceof Error ? loadError.message : "Unable to load ward detail.");
      } finally {
        if (isActive) {
          setIsLoading(false);
          setIsHistoryLoading(false);
          setIsAlertsLoading(false);
        }
      }
    }

    void loadDetail();

    return () => {
      isActive = false;
    };
  }, [currentUser, refreshKey, wardId]);

  const isStale = isStaleTimestamp(detail?.updatedAt ?? null);
  const topbarTimestampLabel = isLoading
    ? "Refreshing..."
    : `${formatOperationalTime(detail?.updatedAt ?? null)}${isStale ? " · Stale" : ""}`;
  const trend = getTrend(detail);
  const drivers = buildRiskDrivers(detail);
  const recommendations = buildOperationalRecommendations(detail?.riskLevel ?? "UNKNOWN");
  const latestAlert = detail?.relatedAlerts[0] ?? null;
  const dataCoverageScore =
    (detail ? 25 : 0) +
    (!isStale ? 25 : 0) +
    (!historyError ? 25 : 0) +
    (!alertsError ? 25 : 0);

  if (!currentUser) {
    return null;
  }

  return (
    <div className="wards-dashboard ward-detail-dashboard">
      <DashboardTopbar
        title="Ward Detail"
        subtitle={detail ? `${detail.county} County operational view` : "Migori County operational view"}
        lastUpdatedLabel={topbarTimestampLabel}
        lastUpdatedTone={isStale ? "stale" : "default"}
        onRefresh={() => setRefreshKey((value) => value + 1)}
      />

      {error ? (
        <div className="status status-error">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <section className="ward-detail-hero ward-detail-hero-redesign">
        <div className="ward-detail-hero-copy ward-detail-hero-copy-redesign">
          <Link href={returnTo} className="ward-detail-back-link">
            <ArrowLeft aria-hidden="true" />
            Back to wards
          </Link>

          <div className="ward-detail-title-row">
            <h1>{isLoading ? "Loading ward detail..." : detail?.wardName ?? "Ward detail"}</h1>
            {!isLoading ? (
              <>
                <span className={`risk-pill risk-pill-${(detail?.riskLevel ?? "UNKNOWN").toLowerCase()}`}>
                  {formatRiskLevel(detail?.riskLevel ?? "UNKNOWN")}
                </span>
                <span className="ward-detail-title-metric">Risk score: {formatRiskScore(detail?.riskScore ?? null)}</span>
                <span className="ward-detail-title-meta">
                  Last alert: {latestAlert ? formatRelativeMinutes(latestAlert.created_at) : "No recent alerts"}
                </span>
              </>
            ) : null}
          </div>

          <p>
            {isLoading
              ? "Preparing the latest ward risk context."
              : detail
                ? `${detail.subCounty || "Unassigned sub-county"}, ${detail.county} County`
                : "Ward-level operational risk monitoring."}
          </p>
        </div>
      </section>

      <section className="ward-detail-layout">
        <div className="ward-detail-main-column">
          <article className="card ward-detail-driver-card">
            <div className="ward-detail-card-heading">
              <div className="card-header">
                <ShieldAlert className="section-icon" aria-hidden="true" />
                <h3>Primary risk drivers</h3>
              </div>
              <div className={`ward-detail-trend-badge ward-detail-trend-badge-${trend.tone}`}>
                <ArrowUpRight className="section-icon" aria-hidden="true" />
                <span>{isLoading ? "Loading trend..." : trend.label}</span>
              </div>
            </div>

            {isLoading ? (
              <div className="ward-detail-skeleton-stack" aria-hidden="true">
                <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body" />
                <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body" />
                <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body-short" />
              </div>
            ) : (
              <div className="ward-detail-driver-list-grid">
                {drivers.map((driver) => (
                  <article key={driver.text} className="ward-detail-driver-item">
                    <span className={`ward-detail-driver-dot ward-detail-driver-dot-${driver.tone}`} aria-hidden="true" />
                    <span className={`ward-detail-driver-icon ward-detail-driver-icon-${driver.tone}`}>
                      {getRiskDriverIcon(driver)}
                    </span>
                    <strong>{driver.text}</strong>
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className="card ward-detail-history-card ward-detail-history-card-redesign">
            <div className="ward-detail-card-heading">
              <div className="card-header">
                <Waves className="section-icon" aria-hidden="true" />
                <h3>Recent risk history</h3>
              </div>
              <p>Latest model runs for this ward</p>
            </div>

            {isHistoryLoading ? (
              <div className="ward-detail-table-skeleton" aria-hidden="true">
                {Array.from({ length: 4 }, (_, index) => (
                  <div key={`history-skeleton-${index}`} className="ward-detail-table-skeleton-row">
                    <span className="ward-detail-skeleton-line ward-detail-skeleton-line-table-wide" />
                    <span className="ward-detail-skeleton-line ward-detail-skeleton-line-table-score" />
                    <span className="ward-detail-skeleton-pill" />
                    <span className="ward-detail-skeleton-line ward-detail-skeleton-line-table-score" />
                  </div>
                ))}
              </div>
            ) : historyError ? (
              <div className="status status-warning">
                <AlertTriangle className="section-icon" aria-hidden="true" />
                {historyError}
              </div>
            ) : detail && detail.riskHistory.length > 0 ? (
              <div className="wards-table-wrap">
                <table className="wards-table ward-detail-history-table ward-detail-history-table-redesign">
                  <thead>
                    <tr>
                      <th>Date/time</th>
                      <th>Risk score</th>
                      <th>Status</th>
                      <th>Trend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.riskHistory.slice(0, 6).map((risk, index, history) => {
                      const historyTrend = getHistoryTrendIcon(index, history);

                      return (
                        <tr key={risk.id}>
                          <td>{formatOperationalTime(risk.generated_at)}</td>
                          <td className="ward-detail-history-score">{Math.round(normalizeRiskScore(risk.score))}</td>
                          <td>
                            <span className={`risk-pill risk-pill-${risk.risk_level.toLowerCase()}`}>{risk.risk_level}</span>
                          </td>
                          <td>
                            <span className={`ward-detail-history-trend ward-detail-history-trend-${historyTrend}`}>
                              {historyTrend === "up" ? (
                                <ArrowUpRight aria-hidden="true" />
                              ) : historyTrend === "down" ? (
                                <ArrowUpRight className="ward-detail-history-trend-down-icon" aria-hidden="true" />
                              ) : (
                                <Minus aria-hidden="true" />
                              )}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">No risk history is currently available for this ward.</p>
            )}
          </article>

          <section className="ward-detail-bottom-grid">
            <article className="card ward-detail-context-card">
              <div className="ward-detail-card-heading">
                <div className="card-header">
                  <MapPinned className="section-icon" aria-hidden="true" />
                  <h3>Ward context</h3>
                </div>
              </div>

              {isLoading ? (
                <div className="ward-detail-skeleton-stack" aria-hidden="true">
                  <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body" />
                  <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body" />
                  <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body-short" />
                </div>
              ) : detail ? (
                <dl className="ward-detail-stat-list">
                  <div>
                    <dt>Sub-county</dt>
                    <dd>{detail.subCounty || "Not recorded"}</dd>
                  </div>
                  <div>
                    <dt>Ward code</dt>
                    <dd>{detail.wardCode ?? "Not recorded"}</dd>
                  </div>
                  <div>
                    <dt>Predicted cases</dt>
                    <dd>{detail.predictedCases}</dd>
                  </div>
                </dl>
              ) : (
                <p className="muted">No ward detail is available for this route.</p>
              )}
            </article>

            <article className="card ward-detail-reliability-card">
              <div className="ward-detail-card-heading">
                <div className="card-header">
                  <Clock3 className="section-icon" aria-hidden="true" />
                  <h3>Data reliability</h3>
                </div>
              </div>

              <div className="ward-detail-coverage-bar" aria-hidden="true">
                <span style={{ width: `${dataCoverageScore}%` }} />
              </div>
              <p className="ward-detail-coverage-label">{dataCoverageScore}% operational data coverage</p>
              <dl className="ward-detail-reliability-list">
                <div>
                  <dt>Freshness</dt>
                  <dd>{isLoading ? "Loading..." : isStale ? "Stale" : "Current"}</dd>
                </div>
                <div>
                  <dt>History coverage</dt>
                  <dd>{isLoading ? "Loading..." : detail ? `${detail.riskHistory.length} recent runs` : "Unavailable"}</dd>
                </div>
                <div>
                  <dt>Alert linkage</dt>
                  <dd>
                    {isLoading
                      ? "Loading..."
                      : alertsError
                        ? "Temporarily unavailable"
                        : detail
                          ? `${detail.relatedAlerts.length} recent alerts`
                          : "Unavailable"}
                  </dd>
                </div>
              </dl>
              {!isLoading && isStale ? (
                <p className="ward-detail-reliability-note">
                  This ward summary is older than the expected freshness window. Review with caution until the next update lands.
                </p>
              ) : (
                <p className="ward-detail-reliability-note">
                  Based on the current ward summary, recent history, and linked alert activity.
                </p>
              )}
            </article>
          </section>

        </div>

        <aside className="ward-detail-side-column">
          <article className="card ward-detail-action-card ward-detail-action-card-redesign">
            <div className="card-header">
              <Zap className="section-icon" aria-hidden="true" />
              <h3>Recommended actions</h3>
            </div>

            {isLoading ? (
              <div className="ward-detail-skeleton-stack" aria-hidden="true">
                <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body" />
                <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body" />
                <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body-short" />
                <span className="ward-detail-skeleton-pill ward-detail-skeleton-pill-button" />
              </div>
            ) : (
              <div className="ward-detail-action-steps">
                {recommendations.map((recommendation, index) => (
                  <article key={recommendation} className="ward-detail-action-step">
                    <div className="ward-detail-action-step-index">{String(index + 1).padStart(2, "0")}</div>
                    <div className="ward-detail-action-step-copy">
                      <strong>{recommendation}</strong>
                      <span>
                        {index === 0 && canTriggerAlerts(currentUser.role)
                          ? "Ready to trigger"
                          : canTriggerAlerts(currentUser.role)
                            ? "Pending"
                            : "Review only"}
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            )}

            {detail ? (
              canTriggerAlerts(currentUser.role) ? (
                <div className="ward-detail-action-panel ward-detail-action-panel-redesign">
                  <TriggerAlertPanel
                    buttonLabel="Send Emergency Alerts"
                    closeLabel="Close action panel"
                    buttonClassName="button ward-detail-emergency-button"
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
                </div>
              ) : (
                <div className="status status-warning">
                  <AlertTriangle className="section-icon" aria-hidden="true" />
                  Recommended actions are visible, but this role cannot trigger alerts from this page.
                </div>
              )
            ) : null}
          </article>

          <article className="card ward-detail-alert-card">
            <div className="ward-detail-card-heading">
              <div className="card-header">
                <Bell className="section-icon" aria-hidden="true" />
                <h3>Recent alerts</h3>
              </div>
            </div>

            {isAlertsLoading ? (
              <div className="ward-detail-skeleton-stack" aria-hidden="true">
                {Array.from({ length: 3 }, (_, index) => (
                  <div key={`alert-skeleton-${index}`} className="ward-detail-alert-item ward-detail-alert-item-skeleton">
                    <span className="ward-detail-skeleton-pill" />
                    <div className="ward-detail-skeleton-stack ward-detail-skeleton-stack-tight">
                      <span className="ward-detail-skeleton-line ward-detail-skeleton-line-body-short" />
                      <span className="ward-detail-skeleton-line ward-detail-skeleton-line-meta" />
                    </div>
                  </div>
                ))}
              </div>
            ) : alertsError ? (
              <div className="status status-warning">
                <AlertTriangle className="section-icon" aria-hidden="true" />
                {alertsError}
              </div>
            ) : detail && detail.relatedAlerts.length > 0 ? (
              <>
                <div className="ward-detail-alert-list">
                  {detail.relatedAlerts.slice(0, 4).map((alert) => (
                    <article key={alert.id} className="ward-detail-alert-item">
                      <div className="ward-detail-alert-icon">
                        <Bell aria-hidden="true" />
                      </div>
                      <div className="ward-detail-alert-copy">
                        <div className="ward-detail-alert-topline">
                          <strong>{getAlertHeadline(alert)}</strong>
                          <span className={`status-pill status-pill-${alert.status.toLowerCase()}`}>{alert.status}</span>
                        </div>
                        <p>Via {toTitleCase(alert.channel)} • {toTitleCase(alert.status)}</p>
                      </div>
                      <div className="ward-detail-alert-meta">
                        <span>{formatRelativeMinutes(alert.created_at)}</span>
                      </div>
                    </article>
                  ))}
                </div>
                <Link href="/alerts" className="ward-detail-alert-history-link">
                  View Alert History
                  <ChevronRight aria-hidden="true" />
                </Link>
              </>
            ) : (
              <p className="muted">No alerts are currently visible for this ward.</p>
            )}
          </article>
        </aside>

      </section>
    </div>
  );
}
