"use client";

import { AlertTriangle, BellDot, Search, ShieldAlert, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { useAuth } from "@/components/auth-provider";
import { fetchAlertsData, type AlertRecord } from "@/lib/dashboard";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";
import { canTriggerAlerts } from "@/lib/roles";

export default function AlertsPage() {
  const { accessToken, currentUser } = useAuth();
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("ALL");
  const [selectedChannel, setSelectedChannel] = useState("ALL");

  if (!currentUser) {
    return null;
  }

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    const token = accessToken;
    let isActive = true;

    async function loadAlerts() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetchAlertsData(token);

        if (!isActive) {
          return;
        }

        setAlerts(response.results);
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load alerts.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadAlerts();

    return () => {
      isActive = false;
    };
  }, [accessToken]);

  const filteredAlerts = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return alerts.filter((alert) => {
      if (selectedStatus !== "ALL" && alert.status !== selectedStatus) {
        return false;
      }

      if (selectedChannel !== "ALL" && alert.channel !== selectedChannel) {
        return false;
      }

      if (!normalizedSearch) {
        return true;
      }

      return (
        alert.ward_name.toLowerCase().includes(normalizedSearch) ||
        alert.recipient.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [alerts, search, selectedStatus, selectedChannel]);

  const deliveredCount = filteredAlerts.filter((alert) => alert.status === "DELIVERED").length;
  const queuedCount = filteredAlerts.filter(
    (alert) => alert.status === "QUEUED" || alert.status === "RETRY_PENDING",
  ).length;
  const failedCount = filteredAlerts.filter((alert) => alert.status === "FAILED").length;
  const latestAlertTimestamp = getLatestTimestamp(alerts.map((alert) => alert.created_at));
  const alertFreshness = describeFreshness(latestAlertTimestamp, 15);
  const hasActiveFilters = Boolean(search.trim()) || selectedStatus !== "ALL" || selectedChannel !== "ALL";

  return (
    <PageFrame
      title="Alerts"
      summary="Alert monitoring is available to Admin, Supervisor, and Analyst roles, while alert triggering remains visible only to Admin and Supervisor roles."
      role={currentUser.role}
    >
      {error ? (
        <div className="status status-error">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      {!isLoading && !error && alerts.length === 0 ? (
        <div className="status status-warning">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          No alerts are available yet in your visible scope.
        </div>
      ) : null}

      {!isLoading && !error && alerts.length > 0 && alertFreshness.isStale ? (
        <div className="status status-warning">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          Alert activity may be stale. Latest visible activity was {formatRelativeTimestamp(latestAlertTimestamp)}.
        </div>
      ) : null}

      <section className="page-grid metrics-2">
        <article className="card">
          <div className="card-header">
            <BellDot className="section-icon" aria-hidden="true" />
            <h3>Visible alerts</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : filteredAlerts.length}</p>
          <p className="muted">Alerts in the current filtered list and current backend scope.</p>
        </article>
        <article className="card">
          <div className="card-header">
            <ShieldAlert className="section-icon" aria-hidden="true" />
            <h3>Freshness and access</h3>
          </div>
          <p className="muted" style={{ marginBottom: "0.65rem" }}>
            {canTriggerAlerts(currentUser.role)
              ? "This role can see future trigger actions."
              : "This role remains read-only and should never receive trigger controls."}
          </p>
          <div className={`status ${alertFreshness.isStale ? "status-warning" : ""}`.trim()}>
            <ShieldAlert className="section-icon" aria-hidden="true" />
            {isLoading ? "Checking alert freshness..." : alertFreshness.label}
          </div>
          <p className="muted compact">
            Latest alert activity: {isLoading ? "Loading..." : formatRelativeTimestamp(latestAlertTimestamp)}
          </p>
        </article>
      </section>

      <section className="page-grid metrics-3">
        <article className="card">
          <div className="card-header">
            <BellDot className="section-icon" aria-hidden="true" />
            <h3>Delivered</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : deliveredCount}</p>
          <p className="muted">Alerts marked as delivered in the current filtered list.</p>
        </article>
        <article className="card">
          <div className="card-header">
            <BellDot className="section-icon" aria-hidden="true" />
            <h3>Queued</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : queuedCount}</p>
          <p className="muted">Queued or retry-pending alerts awaiting or repeating delivery work.</p>
        </article>
        <article className="card">
          <div className="card-header">
            <AlertTriangle className="section-icon" aria-hidden="true" />
            <h3>Failed</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : failedCount}</p>
          <p className="muted">Failed alerts that may need operational review or backend follow-up.</p>
        </article>
      </section>

      <section className="page-grid">
        <article className="card">
          <div className="card-header">
            <SlidersHorizontal className="section-icon" aria-hidden="true" />
            <h3>Filters</h3>
          </div>
          <div className="filter-grid filter-grid-3">
            <label className="field">
              <span>Search by ward or recipient</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search alerts"
              />
            </label>

            <label className="field">
              <span>Status</span>
              <select value={selectedStatus} onChange={(event) => setSelectedStatus(event.target.value)}>
                <option value="ALL">All statuses</option>
                <option value="QUEUED">Queued</option>
                <option value="RETRY_PENDING">Retry pending</option>
                <option value="DELIVERED">Delivered</option>
                <option value="FAILED">Failed</option>
              </select>
            </label>

            <label className="field">
              <span>Channel</span>
              <select value={selectedChannel} onChange={(event) => setSelectedChannel(event.target.value)}>
                <option value="ALL">All channels</option>
                <option value="SMS">SMS</option>
                <option value="WHATSAPP">WhatsApp</option>
                <option value="DASHBOARD">Dashboard</option>
              </select>
            </label>
          </div>
        </article>
      </section>

      <section className="page-grid">
        <article className="card">
          <div className="card-header">
            <Search className="section-icon" aria-hidden="true" />
            <h3>Alert activity</h3>
          </div>
          {isLoading ? (
            <p className="muted">Loading alert activity...</p>
          ) : filteredAlerts.length > 0 ? (
            <div className="stack">
              {filteredAlerts.map((alert) => (
                <div key={alert.id} className="summary-row">
                  <div>
                    <strong>{alert.ward_name}</strong>
                    <p className="muted compact">
                      {alert.recipient} • {new Date(alert.created_at).toLocaleString()}
                    </p>
                    <p className="muted compact">
                      Backend: {alert.delivery_backend || "Not recorded"}
                      {alert.sent_at ? ` • Sent: ${new Date(alert.sent_at).toLocaleString()}` : ""}
                    </p>
                    {alert.error_message ? <p className="muted compact">Error: {alert.error_message}</p> : null}
                    <p className="compact" style={{ marginTop: "0.6rem" }}>
                      <Link href={`/alerts/${alert.id}`} className="detail-link">
                        Open alert detail
                      </Link>
                    </p>
                  </div>
                  <div className="summary-row-side stack summary-meta">
                    <span className={`status-pill status-pill-${alert.status.toLowerCase()}`}>
                      {alert.status.replace("_", " ")}
                    </span>
                    <span className="role-pill">{alert.channel}</span>
                    <span className="muted compact">
                      Attempts {alert.attempt_count}/{alert.max_attempts}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">
              {hasActiveFilters
                ? "No alerts match the current search and filter combination."
                : "No alerts are currently visible in your scope."}
            </p>
          )}
        </article>
      </section>
    </PageFrame>
  );
}
