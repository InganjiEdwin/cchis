"use client";

import { AlertTriangle, Clock3, DatabaseZap, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { RoleGate } from "@/components/role-gate";
import { useAuth } from "@/components/auth-provider";
import { fetchSystemData } from "@/lib/dashboard";

type SystemSnapshot = {
  visibleWards: number;
  visibleAlerts: number;
  latestRiskTimestamp: string | null;
  latestAlertTimestamp: string | null;
};

function describeFreshness(timestamp: string | null, thresholdMinutes: number) {
  if (!timestamp) {
    return {
      label: "No current timestamp available",
      stateClass: "status-warning",
    };
  }

  const ageMs = Date.now() - new Date(timestamp).getTime();

  if (ageMs > thresholdMinutes * 60 * 1000) {
    return {
      label: "Data may be stale",
      stateClass: "status-warning",
    };
  }

  return {
    label: "Data is within the current freshness window",
    stateClass: "",
  };
}

export default function SystemPage() {
  const { accessToken, currentUser } = useAuth();
  const [snapshot, setSnapshot] = useState<SystemSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  if (!currentUser) {
    return null;
  }

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    const token = accessToken;
    let isActive = true;

    async function loadSystemSnapshot() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await fetchSystemData(token);

        if (!isActive) {
          return;
        }

        const latestRiskTimestamp = data.latestRisks.reduce<string | null>((latest, item) => {
          if (!item.generated_at) {
            return latest;
          }

          if (!latest || new Date(item.generated_at).getTime() > new Date(latest).getTime()) {
            return item.generated_at;
          }

          return latest;
        }, null);

        const latestAlertTimestamp = data.alerts.results.reduce<string | null>((latest, item) => {
          if (!latest || new Date(item.created_at).getTime() > new Date(latest).getTime()) {
            return item.created_at;
          }

          return latest;
        }, null);

        setSnapshot({
          visibleWards: data.wards.count,
          visibleAlerts: data.alerts.count,
          latestRiskTimestamp,
          latestAlertTimestamp,
        });
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load system freshness data.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadSystemSnapshot();

    return () => {
      isActive = false;
    };
  }, [accessToken]);

  const riskFreshness = describeFreshness(snapshot?.latestRiskTimestamp ?? null, 360);
  const alertFreshness = describeFreshness(snapshot?.latestAlertTimestamp ?? null, 15);

  return (
    <PageFrame
      title="System"
      summary="A role-aware system and data freshness surface for Admin and Analyst users, without pretending full infrastructure observability already exists."
      role={currentUser.role}
    >
      <RoleGate
        allowedRoles={["ADMIN", "ANALYST"]}
        title="System view is role-restricted"
        message="Only Admin and Analyst roles should access the first-pass system and data freshness surface."
      >
        {error ? (
          <div className="status status-error">
            <AlertTriangle className="section-icon" aria-hidden="true" />
            {error}
          </div>
        ) : null}

        <section className="page-grid metrics-3">
          <article className="card">
            <div className="card-header">
              <DatabaseZap className="section-icon" aria-hidden="true" />
              <h3>Visible wards</h3>
            </div>
            <p className="metric-value">{isLoading ? "..." : snapshot?.visibleWards ?? 0}</p>
            <p className="muted">Current ward count available in your scope.</p>
          </article>

          <article className="card">
            <div className="card-header">
              <ShieldCheck className="section-icon" aria-hidden="true" />
              <h3>Visible alerts</h3>
            </div>
            <p className="metric-value">{isLoading ? "..." : snapshot?.visibleAlerts ?? 0}</p>
            <p className="muted">Current alert count available in your scope.</p>
          </article>

          <article className="card">
            <div className="card-header">
              <Clock3 className="section-icon" aria-hidden="true" />
              <h3>System shape</h3>
            </div>
            <p className="metric-value">v1</p>
            <p className="muted">Freshness-oriented summary only. No dedicated infrastructure endpoint yet.</p>
          </article>
        </section>

        <section className="page-grid metrics-2">
          <article className="card">
            <div className="card-header">
              <Clock3 className="section-icon" aria-hidden="true" />
              <h3>Risk data freshness</h3>
            </div>
            <div className={`status ${riskFreshness.stateClass}`.trim()}>
              <Clock3 className="section-icon" aria-hidden="true" />
              {isLoading ? "Checking risk timestamps..." : riskFreshness.label}
            </div>
            <p className="muted">
              Last visible risk update:{" "}
              {isLoading
                ? "Loading..."
                : snapshot?.latestRiskTimestamp
                  ? new Date(snapshot.latestRiskTimestamp).toLocaleString()
                  : "No timestamp available"}
            </p>
            <p className="muted">Current stale threshold: 6 hours.</p>
          </article>

          <article className="card">
            <div className="card-header">
              <Clock3 className="section-icon" aria-hidden="true" />
              <h3>Alert activity freshness</h3>
            </div>
            <div className={`status ${alertFreshness.stateClass}`.trim()}>
              <Clock3 className="section-icon" aria-hidden="true" />
              {isLoading ? "Checking alert timestamps..." : alertFreshness.label}
            </div>
            <p className="muted">
              Last visible alert activity:{" "}
              {isLoading
                ? "Loading..."
                : snapshot?.latestAlertTimestamp
                  ? new Date(snapshot.latestAlertTimestamp).toLocaleString()
                  : "No timestamp available"}
            </p>
            <p className="muted">Current stale threshold: 15 minutes.</p>
          </article>
        </section>

        <section className="page-grid">
          <article className="card">
            <div className="card-header">
              <DatabaseZap className="section-icon" aria-hidden="true" />
              <h3>Current interpretation</h3>
            </div>
            <p className="muted">
              This page is intentionally limited to data freshness and visible-scope summaries. It should not be
              interpreted as full infrastructure observability, queue monitoring, or ETL health until a dedicated
              backend system-status endpoint exists.
            </p>
          </article>
        </section>
      </RoleGate>
    </PageFrame>
  );
}
