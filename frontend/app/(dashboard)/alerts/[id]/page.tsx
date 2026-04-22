"use client";

import { AlertTriangle, ArrowLeft, BellDot, Clock3, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { useAuth } from "@/components/auth-provider";
import { fetchAlertById, type AlertRecord } from "@/lib/dashboard";

export default function AlertDetailPage() {
  const params = useParams<{ id: string }>();
  const { accessToken, currentUser } = useAuth();
  const [alert, setAlert] = useState<AlertRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const alertId = useMemo(() => Number(params.id), [params.id]);

  useEffect(() => {
    if (!accessToken || !Number.isFinite(alertId)) {
      return;
    }

    const token = accessToken;
    let isActive = true;

    async function loadAlert() {
      setIsLoading(true);
      setError(null);

      try {
        const detail = await fetchAlertById(token, alertId);

        if (!isActive) {
          return;
        }

        if (!detail) {
          setError("Alert detail is not available in your current scope.");
          setAlert(null);
          return;
        }

        setAlert(detail);
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load alert detail.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadAlert();

    return () => {
      isActive = false;
    };
  }, [accessToken, alertId]);

  if (!currentUser) {
    return null;
  }

  return (
    <PageFrame
      title={alert ? `Alert #${alert.id}` : "Alert detail"}
      summary="A first-pass alert detail page composed from the alerts list until a dedicated alert-detail backend endpoint exists."
      role={currentUser.role}
    >
      <div className="inline-actions">
        <Link href="/alerts" className="button button-secondary">
          <ArrowLeft className="section-icon" aria-hidden="true" />
          Back to alerts
        </Link>
        {alert ? (
          <Link href={`/wards/${alert.ward}`} className="button button-secondary">
            <BellDot className="section-icon" aria-hidden="true" />
            Open ward
          </Link>
        ) : null}
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
            <BellDot className="section-icon" aria-hidden="true" />
            <h3>Status</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : alert?.status ?? "N/A"}</p>
          <p className="muted">Delivery state currently exposed by the backend.</p>
        </article>
        <article className="card">
          <div className="card-header">
            <ShieldAlert className="section-icon" aria-hidden="true" />
            <h3>Channel</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : alert?.channel ?? "N/A"}</p>
          <p className="muted">{isLoading ? "Loading..." : alert?.ward_name ?? "No ward recorded"}</p>
        </article>
        <article className="card">
          <div className="card-header">
            <Clock3 className="section-icon" aria-hidden="true" />
            <h3>Attempts</h3>
          </div>
          <p className="metric-value">
            {isLoading ? "..." : alert ? `${alert.attempt_count}/${alert.max_attempts}` : "N/A"}
          </p>
          <p className="muted">Current delivery attempt count and maximum retry ceiling.</p>
        </article>
      </section>

      <section className="page-grid metrics-2">
        <article className="card">
          <div className="card-header">
            <BellDot className="section-icon" aria-hidden="true" />
            <h3>Alert metadata</h3>
          </div>
          {isLoading ? (
            <p className="muted">Loading alert metadata...</p>
          ) : alert ? (
            <dl className="detail-list">
              <div>
                <dt>Ward</dt>
                <dd>{alert.ward_name}</dd>
              </div>
              <div>
                <dt>Recipient</dt>
                <dd>{alert.recipient}</dd>
              </div>
              <div>
                <dt>Backend</dt>
                <dd>{alert.delivery_backend || "Not recorded"}</dd>
              </div>
              <div>
                <dt>External ID</dt>
                <dd>{alert.external_id || "Not recorded"}</dd>
              </div>
            </dl>
          ) : (
            <p className="muted">No alert detail is available for this route.</p>
          )}
        </article>

        <article className="card">
          <div className="card-header">
            <Clock3 className="section-icon" aria-hidden="true" />
            <h3>Delivery timeline</h3>
          </div>
          {isLoading ? (
            <p className="muted">Loading delivery timestamps...</p>
          ) : alert ? (
            <dl className="detail-list">
              <div>
                <dt>Created</dt>
                <dd>{new Date(alert.created_at).toLocaleString()}</dd>
              </div>
              <div>
                <dt>Sent</dt>
                <dd>{alert.sent_at ? new Date(alert.sent_at).toLocaleString() : "Not yet sent"}</dd>
              </div>
              <div>
                <dt>Last attempted</dt>
                <dd>
                  {alert.last_attempted_at ? new Date(alert.last_attempted_at).toLocaleString() : "Not recorded"}
                </dd>
              </div>
              <div>
                <dt>Next retry</dt>
                <dd>{alert.next_retry_at ? new Date(alert.next_retry_at).toLocaleString() : "None scheduled"}</dd>
              </div>
            </dl>
          ) : (
            <p className="muted">No delivery timeline is available for this route.</p>
          )}
        </article>
      </section>

      <section className="page-grid">
        <article className="card">
          <div className="card-header">
            <ShieldAlert className="section-icon" aria-hidden="true" />
            <h3>Message and error context</h3>
          </div>
          {isLoading ? (
            <p className="muted">Loading message context...</p>
          ) : alert ? (
            <div className="stack">
              <div className="status">
                <BellDot className="section-icon" aria-hidden="true" />
                {alert.message}
              </div>
              {alert.error_message ? (
                <div className="status status-warning">
                  <AlertTriangle className="section-icon" aria-hidden="true" />
                  {alert.error_message}
                </div>
              ) : (
                <p className="muted">No backend error message is currently recorded for this alert.</p>
              )}
            </div>
          ) : (
            <p className="muted">No message context is available for this route.</p>
          )}
        </article>
      </section>
    </PageFrame>
  );
}
