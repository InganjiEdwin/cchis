"use client";

import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CircleAlert,
  MapPin,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import {
  fetchOverviewData,
  type AlertRecord,
  type LatestWardRisk,
  type WardSummary,
} from "@/lib/dashboard";
import { getLatestTimestamp } from "@/lib/freshness";

type OverviewViewModel = {
  wards: WardSummary[];
  totalWards: number;
  highRiskWards: LatestWardRisk[];
  mediumRiskWards: LatestWardRisk[];
  recentAlerts: AlertRecord[];
  alertsTodayCount: number;
  deliveredAlertRate: number;
  latestTimestamp: string | null;
  primaryCountyLabel: string;
};

function startOfTodayIso() {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

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

function getStatusTone(status: AlertRecord["status"]) {
  switch (status) {
    case "DELIVERED":
      return "dashboard-badge-success";
    case "RETRY_PENDING":
      return "dashboard-badge-warning";
    case "FAILED":
      return "dashboard-badge-danger";
    default:
      return "dashboard-badge-muted";
  }
}

function getRiskTone(level: LatestWardRisk["risk_level"]) {
  if (level === "HIGH") {
    return "dashboard-risk-high";
  }
  if (level === "MEDIUM") {
    return "dashboard-risk-medium";
  }
  return "dashboard-risk-low";
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

  const timeLabel = date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return `${timeLabel} (${formatCompactRelativeMinutes(timestamp)})`;
}

function getScoreTone(score: number) {
  const normalizedScore = normalizeRiskScore(score);

  if (normalizedScore >= 80) {
    return "overview-score-pill-danger";
  }
  if (normalizedScore >= 65) {
    return "overview-score-pill-high";
  }
  if (normalizedScore >= 45) {
    return "overview-score-pill-medium";
  }
  if (normalizedScore >= 25) {
    return "overview-score-pill-low";
  }
  return "overview-score-pill-minimal";
}

function buildOverviewViewModel(wards: WardSummary[], latestRisks: LatestWardRisk[], alerts: AlertRecord[]): OverviewViewModel {
  const highRiskWards = latestRisks
    .filter((item) => item.risk_level === "HIGH")
    .sort((left, right) => (right.risk_score ?? 0) - (left.risk_score ?? 0));
  const mediumRiskWards = latestRisks
    .filter((item) => item.risk_level === "MEDIUM")
    .sort((left, right) => (right.risk_score ?? 0) - (left.risk_score ?? 0));
  const latestTimestamp = getLatestTimestamp([
    ...latestRisks.map((item) => item.generated_at),
    ...alerts.map((item) => item.created_at),
  ]);
  const deliveredAlertRate = alerts.length
    ? Math.round((alerts.filter((item) => item.status === "DELIVERED").length / alerts.length) * 100)
    : 0;
  const alertsTodayCount = alerts.filter((item) => new Date(item.created_at).getTime() >= startOfTodayIso()).length;
  const countyCounts = wards.reduce<Map<string, number>>((accumulator, ward) => {
    accumulator.set(ward.county, (accumulator.get(ward.county) ?? 0) + 1);
    return accumulator;
  }, new Map<string, number>());
  const primaryCountyLabel =
    [...countyCounts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? "Operational";

  return {
    wards,
    totalWards: wards.length ? Math.max(wards.length, latestRisks.length) : latestRisks.length,
    highRiskWards,
    mediumRiskWards,
    recentAlerts: alerts.slice(0, 5),
    alertsTodayCount,
    deliveredAlertRate,
    latestTimestamp,
    primaryCountyLabel: primaryCountyLabel === "Operational" ? "Migori" : primaryCountyLabel,
  };
}

export default function OverviewPage() {
  const { accessToken, currentUser } = useAuth();
  const [overview, setOverview] = useState<OverviewViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    const token = accessToken;
    let isActive = true;

    async function loadOverview() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await fetchOverviewData(token);

        if (!isActive) {
          return;
        }

        const migoriWards = data.wards.results.filter((ward) => ward.county === "Migori");
        const migoriWardIds = new Set(migoriWards.map((ward) => ward.id));
        const migoriRisks = data.latestRisks.filter((risk) => migoriWardIds.has(risk.ward_id));
        const migoriAlerts = data.alerts.results.filter((alert) => migoriWardIds.has(alert.ward));
        const model = buildOverviewViewModel(migoriWards, migoriRisks, migoriAlerts);
        setOverview({
          ...model,
          totalWards: migoriWards.length,
        });
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load overview data.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadOverview();

    return () => {
      isActive = false;
    };
  }, [accessToken, refreshKey]);

  const immediateAttention = useMemo(
    () => overview?.highRiskWards.slice(0, 3) ?? [],
    [overview],
  );

  if (!currentUser) {
    return null;
  }

  return (
    <div className="overview-dashboard">
      <DashboardTopbar
        title="Overview"
        subtitle="Climate Health Risk Monitoring"
        lastUpdatedLabel={isLoading ? "Refreshing..." : formatOperationalTime(overview?.latestTimestamp ?? null)}
        onRefresh={() => setRefreshKey((value) => value + 1)}
      >
        <TriggerAlertPanel
          buttonLabel="Send Emergency Alerts"
          closeLabel="Close Emergency Alerts"
          buttonClassName="dashboard-primary-action"
        />
      </DashboardTopbar>

      {error ? (
        <div className="status status-error">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <section className="overview-metrics">
        <article className="overview-metric-card">
          <div className="overview-metric-icon overview-metric-icon-blue">
            <MapPin aria-hidden="true" />
          </div>
          <div className="overview-metric-copy">
            <span className="overview-metric-label">Total wards</span>
            <strong>{isLoading ? "..." : overview?.totalWards ?? 0}</strong>
            <p>Total wards monitored</p>
          </div>
        </article>

        <article className="overview-metric-card">
          <div className="overview-metric-icon overview-metric-icon-red">
            <TriangleAlert aria-hidden="true" />
          </div>
          <div className="overview-metric-copy">
            <span className="overview-metric-label overview-metric-pill">Immediate action</span>
            <strong>{isLoading ? "..." : overview?.highRiskWards.length ?? 0}</strong>
            <p>High risk wards</p>
          </div>
        </article>

        <article className="overview-metric-card">
          <div className="overview-metric-icon overview-metric-icon-amber">
            <CircleAlert aria-hidden="true" />
          </div>
          <div className="overview-metric-copy">
            <span className="overview-metric-label overview-metric-pill overview-metric-pill-muted">
              Stable monitoring
            </span>
            <strong>{isLoading ? "..." : overview?.mediumRiskWards.length ?? 0}</strong>
            <p>Medium risk wards</p>
          </div>
        </article>

        <article className="overview-metric-card">
          <div className="overview-metric-icon overview-metric-icon-slate">
            <Bell aria-hidden="true" />
          </div>
          <div className="overview-metric-copy">
            <span className="overview-metric-label">{overview?.deliveredAlertRate ?? 0}% delivered</span>
            <strong>{isLoading ? "..." : overview?.alertsTodayCount ?? 0}</strong>
            <p>Alerts today</p>
          </div>
        </article>
      </section>

      <section className="overview-content-grid">
        <div className="overview-table-panel">
          <div className="overview-section-heading">
            <div>
              <h2>Recent Alerts</h2>
              <p>{overview?.primaryCountyLabel ?? "Current scope"} operational activity</p>
            </div>
          </div>

          <div className="overview-table-wrap">
            <table className="overview-table">
              <thead>
                <tr>
                  <th>Administrative ward</th>
                  <th>Channel</th>
                  <th className="overview-table-score-column">Score</th>
                  <th>Status</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={5} className="overview-table-empty">
                      Loading operational alerts...
                    </td>
                  </tr>
                ) : overview && overview.recentAlerts.length > 0 ? (
                  overview.recentAlerts.map((alert) => (
                    <tr key={alert.id}>
                      <td>
                        <strong>{alert.ward_name}</strong>
                      </td>
                      <td>{formatChannelLabel(alert.channel)}</td>
                      <td className="overview-table-score-column">
                        {typeof alert.risk_score === "number" ? (
                          <span className={`overview-score-pill ${getScoreTone(alert.risk_score)}`}>
                            {formatRiskScore(alert.risk_score)}
                          </span>
                        ) : (
                          "N/A"
                        )}
                      </td>
                      <td>
                        <span className={`dashboard-status-badge ${getStatusTone(alert.status)}`}>
                          {formatStatusLabel(alert.status)}
                        </span>
                      </td>
                      <td>{formatOperationalTime(alert.created_at)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="overview-table-empty">
                      No visible alerts in the current scope yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="overview-table-meta">
            <span>Model confidence: derived from current risk feed</span>
            <span>Data quality: live API-backed</span>
          </div>
        </div>

        <aside className="overview-aside">
          <section className="overview-attention-panel">
            <div className="overview-section-heading">
              <h2>Immediate Attention</h2>
            </div>

            <div className="overview-attention-list">
              {isLoading ? (
                <div className="overview-attention-card">
                  <p>Loading priority wards...</p>
                </div>
              ) : immediateAttention.length > 0 ? (
                immediateAttention.map((ward, index) => (
                  <article
                    key={ward.ward_id}
                    className={`overview-attention-card ${getRiskTone(ward.risk_level)}${index === 0 ? " overview-attention-card-primary" : ""}`}
                  >
                    <div className="overview-attention-card-top">
                      <strong>{ward.ward_name}</strong>
                      <span>{ward.risk_level ?? "Unknown"}</span>
                    </div>
                    <p>{index === 0 ? "Highest current risk score" : "Current risk score"}</p>
                    <div className="overview-attention-score">
                      <strong>{typeof ward.risk_score === "number" ? formatRiskScore(ward.risk_score) : "N/A"}</strong>
                      <span>/100</span>
                    </div>
                  </article>
                ))
              ) : (
                <div className="overview-attention-card">
                  <p>No high-risk wards are currently visible in your scope.</p>
                </div>
              )}
            </div>

            <Link href="/wards" className="overview-secondary-link">
              View high risk wards
              <ArrowRight aria-hidden="true" />
            </Link>
          </section>

          <section className="overview-map-card">
            <div className="overview-map-visual" aria-hidden="true">
              <span>{overview?.primaryCountyLabel ?? "County"}</span>
            </div>
            <div className="overview-map-copy">
              <p>Live geographic monitor</p>
              <strong>{overview?.primaryCountyLabel ?? "Current scope"}</strong>
              <span>Map-ready boundary and hotspot overlays need backend geographic endpoints.</span>
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
