"use client";

import { AlertTriangle, ArrowLeft, Bell, MapPinned } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { useAuth } from "@/components/auth-provider";
import {
  fetchAlertsForWard,
  fetchRiskHistoryForWard,
  fetchWardRiskData,
  type AlertRecord,
  type RiskScoreRecord,
} from "@/lib/dashboard";

type WardDetailState = {
  wardName: string;
  county: string;
  subCounty: string;
  riskLevel: string;
  riskScore: number | null;
  predictedCases: number;
  updatedAt: string | null;
  riskHistory: RiskScoreRecord[];
  relatedAlerts: AlertRecord[];
};

export default function WardDetailPage() {
  const params = useParams<{ id: string }>();
  const { accessToken, currentUser } = useAuth();
  const [detail, setDetail] = useState<WardDetailState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const wardId = useMemo(() => Number(params.id), [params.id]);

  useEffect(() => {
    if (!accessToken || !Number.isFinite(wardId)) {
      return;
    }

    const token = accessToken;
    let isActive = true;

    async function loadDetail() {
      setIsLoading(true);
      setError(null);

      try {
        const [wardData, riskHistory, alerts] = await Promise.all([
          fetchWardRiskData(token),
          fetchRiskHistoryForWard(token, wardId),
          fetchAlertsForWard(token, wardId),
        ]);

        if (!isActive) {
          return;
        }

        const wardsById = new Map(wardData.wards.results.map((ward) => [ward.id, ward]));
        const wardSummary = wardData.latestRisks.find((item) => item.ward_id === wardId);
        const wardMeta = wardsById.get(wardId);

        if (!wardSummary || !wardMeta) {
          setDetail(null);
          setError("Ward detail is not available in your current scope.");
          return;
        }

        setDetail({
          wardName: wardSummary.ward_name,
          county: wardMeta.county,
          subCounty: wardMeta.sub_county,
          riskLevel: wardSummary.risk_level ?? "UNKNOWN",
          riskScore: wardSummary.risk_score,
          predictedCases: wardSummary.predicted_cases,
          updatedAt: wardSummary.generated_at ?? wardMeta.updated_at ?? null,
          riskHistory: riskHistory.results,
          relatedAlerts: alerts.results,
        });
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load ward detail.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadDetail();

    return () => {
      isActive = false;
    };
  }, [accessToken, wardId]);

  if (!currentUser) {
    return null;
  }

  return (
    <PageFrame
      title={detail ? detail.wardName : "Ward detail"}
      summary="A first-pass ward detail view composed from list endpoints until a dedicated ward-detail backend endpoint exists."
      role={currentUser.role}
    >
      <div className="inline-actions">
        <Link href="/wards" className="button button-secondary">
          <ArrowLeft className="section-icon" aria-hidden="true" />
          Back to wards
        </Link>
      </div>

      {error ? (
        <div className="status status-error">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <section className="page-grid metrics-3">
        <article className="card">
          <div className="card-header">
            <MapPinned className="section-icon" aria-hidden="true" />
            <h3>Current risk</h3>
          </div>
          <p className="metric-value">
            {isLoading ? "..." : typeof detail?.riskScore === "number" ? detail.riskScore.toFixed(2) : "N/A"}
          </p>
          <p className="muted">{isLoading ? "Loading..." : `${detail?.riskLevel ?? "Unknown"} risk level`}</p>
        </article>
        <article className="card">
          <div className="card-header">
            <MapPinned className="section-icon" aria-hidden="true" />
            <h3>Location</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : detail?.county ?? "N/A"}</p>
          <p className="muted">{isLoading ? "Loading..." : detail?.subCounty ?? "No sub-county available"}</p>
        </article>
        <article className="card">
          <div className="card-header">
            <Bell className="section-icon" aria-hidden="true" />
            <h3>Related alerts</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : detail?.relatedAlerts.length ?? 0}</p>
          <p className="muted">
            {isLoading
              ? "Loading..."
              : detail?.updatedAt
                ? `Latest update ${new Date(detail.updatedAt).toLocaleString()}`
                : "No update timestamp available"}
          </p>
        </article>
      </section>

      <section className="page-grid metrics-2">
        <article className="card">
          <div className="card-header">
            <MapPinned className="section-icon" aria-hidden="true" />
            <h3>Operational context</h3>
          </div>
          {isLoading ? (
            <p className="muted">Loading ward context...</p>
          ) : detail ? (
            <dl className="detail-list">
              <div>
                <dt>Ward</dt>
                <dd>{detail.wardName}</dd>
              </div>
              <div>
                <dt>County</dt>
                <dd>{detail.county}</dd>
              </div>
              <div>
                <dt>Sub-county</dt>
                <dd>{detail.subCounty || "Not recorded"}</dd>
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

        <article className="card">
          <div className="card-header">
            <Bell className="section-icon" aria-hidden="true" />
            <h3>Recent alerts</h3>
          </div>
          {isLoading ? (
            <p className="muted">Loading related alerts...</p>
          ) : detail && detail.relatedAlerts.length > 0 ? (
            <div className="stack">
              {detail.relatedAlerts.slice(0, 5).map((alert) => (
                <div key={alert.id} className="summary-row">
                  <div>
                    <strong>{alert.channel}</strong>
                    <p className="muted compact">
                      {alert.status} • {new Date(alert.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="summary-row-side">
                    <Link href={`/alerts/${alert.id}`} className="detail-link">
                      Open alert
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No alerts are currently visible for this ward.</p>
          )}
        </article>
      </section>

      <section className="page-grid">
        <article className="card">
          <div className="card-header">
            <MapPinned className="section-icon" aria-hidden="true" />
            <h3>Risk history</h3>
          </div>
          {isLoading ? (
            <p className="muted">Loading recent risk history...</p>
          ) : detail && detail.riskHistory.length > 0 ? (
            <div className="stack">
              {detail.riskHistory.map((risk) => (
                <div key={risk.id} className="summary-row">
                  <div>
                    <strong>{risk.risk_level}</strong>
                    <p className="muted compact">
                      Generated {new Date(risk.generated_at).toLocaleString()}
                    </p>
                    <p className="muted compact">
                      Predicted cases {risk.predicted_cases} • Source {risk.source}
                    </p>
                  </div>
                  <div className="summary-row-side">
                    <span className="role-pill">{risk.score.toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No risk history is currently available for this ward.</p>
          )}
        </article>
      </section>
    </PageFrame>
  );
}
