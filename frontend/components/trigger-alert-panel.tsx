"use client";

import { AlertTriangle, BellRing, CheckCircle2, LoaderCircle, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  fetchWardRiskDataViaBff,
  triggerAlertViaBff,
  type LatestWardRisk,
  type TriggerAlertResponse,
  type WardSummary,
} from "@/lib/dashboard";

type TriggerableWard = {
  id: number;
  name: string;
  county: string;
  subCounty: string;
  latestRisk: LatestWardRisk | null;
};

type FixedWardContext = {
  id: number;
  name: string;
  county: string;
  subCounty: string;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
  riskScore: number | null;
  predictedCases: number | null;
  updatedAt: string | null;
};

type TriggerAlertPanelProps = {
  buttonLabel?: string;
  closeLabel?: string;
  buttonClassName?: string;
  fixedWard?: FixedWardContext | null;
};

function formatWardOptionLabel(ward: TriggerableWard) {
  const riskLabel = ward.latestRisk?.risk_level ?? "UNKNOWN";
  return `${ward.name} (${ward.county}) - ${riskLabel} risk`;
}

function formatTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return "No timestamp available";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  return date.toLocaleString();
}

export function TriggerAlertPanel({
  buttonLabel = "Trigger Alert",
  closeLabel = "Close Trigger Panel",
  buttonClassName = "button",
  fixedWard = null,
}: TriggerAlertPanelProps) {
  const { currentUser } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [wards, setWards] = useState<TriggerableWard[]>([]);
  const [selectedWardId, setSelectedWardId] = useState("");
  const [sendSms, setSendSms] = useState(false);
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<TriggerAlertResponse | null>(null);

  useEffect(() => {
    if (!isOpen || !currentUser) {
      return;
    }

    if (fixedWard) {
      setWards([
        {
          id: fixedWard.id,
          name: fixedWard.name,
          county: fixedWard.county,
          subCounty: fixedWard.subCounty,
          latestRisk: {
            ward_id: fixedWard.id,
            ward_name: fixedWard.name,
            risk_level: fixedWard.riskLevel === "UNKNOWN" ? null : fixedWard.riskLevel,
            risk_score: fixedWard.riskScore,
            predicted_cases: fixedWard.predictedCases ?? 0,
            generated_at: fixedWard.updatedAt,
          },
        },
      ]);
      setSelectedWardId(String(fixedWard.id));
      setIsLoading(false);
      setLoadError(null);
      return;
    }

    const user = currentUser;
    let isActive = true;

    async function loadWards() {
      setIsLoading(true);
      setLoadError(null);

      try {
        const data = await fetchWardRiskDataViaBff();

        if (!isActive) {
          return;
        }

        const latestRiskByWardId = new Map<number, LatestWardRisk>(
          data.latestRisks.map((risk) => [risk.ward_id, risk]),
        );
        const mappedWards = data.wards.results.map<TriggerableWard>((ward: WardSummary) => ({
          id: ward.id,
          name: ward.name,
          county: ward.county,
          subCounty: ward.sub_county,
          latestRisk: latestRiskByWardId.get(ward.id) ?? null,
        }));

        setWards(mappedWards);

        const preferredWardId = user.scope_ward_id ?? user.ward ?? mappedWards[0]?.id;

        if (preferredWardId) {
          setSelectedWardId((currentValue) => currentValue || String(preferredWardId));
        }
      } catch (error) {
        if (!isActive) {
          return;
        }

        setLoadError(error instanceof Error ? error.message : "Unable to load wards for alert triggering.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadWards();

    return () => {
      isActive = false;
    };
  }, [currentUser, fixedWard, isOpen]);

  const selectedWard = useMemo(
    () => wards.find((ward) => ward.id === Number(selectedWardId)) ?? null,
    [selectedWardId, wards],
  );

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedWard) {
      setSubmitError("Select a ward before queuing an alert.");
      return;
    }

    if (!isConfirmed) {
      setSubmitError("Confirm the operational impact before triggering an alert.");
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);

    try {
      const response = await triggerAlertViaBff({
        ward_id: selectedWard.id,
        send_sms: sendSms,
      });

      setSubmitSuccess(response);
      setIsConfirmed(false);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unable to queue the alert trigger request.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleToggle() {
    setIsOpen((previous) => !previous);
    setSubmitError(null);
    setSubmitSuccess(null);
  }

  return (
    <div className="trigger-panel">
      <button
        type="button"
        className={buttonClassName}
        onClick={handleToggle}
        aria-expanded={isOpen}
        aria-controls="trigger-alert-panel"
      >
        <BellRing className="section-icon" aria-hidden="true" />
        {isOpen ? closeLabel : buttonLabel}
      </button>

      {isOpen ? (
        <section id="trigger-alert-panel" className="trigger-panel-card">
          <div className="card-header">
            <ShieldAlert className="section-icon" aria-hidden="true" />
            <h3>Queue an operational alert</h3>
          </div>
          <p className="muted">
            This action sends a backend trigger request for the selected ward. Use it carefully and avoid duplicate
            submissions while an existing alert is still being processed.
          </p>

          {loadError ? (
            <div className="status status-error">
              <AlertTriangle className="section-icon" aria-hidden="true" />
              {loadError}
            </div>
          ) : null}

          {submitError ? (
            <div className="status status-error">
              <AlertTriangle className="section-icon" aria-hidden="true" />
              {submitError}
            </div>
          ) : null}

          {submitSuccess ? (
            <div className="status">
              <CheckCircle2 className="section-icon" aria-hidden="true" />
              {submitSuccess.message} Task {submitSuccess.task_id} is queued for risk score {submitSuccess.risk_score_id}.
            </div>
          ) : null}

          <form className="stack" onSubmit={handleSubmit}>
            <div className="trigger-panel-grid">
              {fixedWard ? (
                <label className="field">
                  <span>Ward</span>
                  <input value={fixedWard.name} readOnly disabled />
                </label>
              ) : (
                <label className="field">
                  <span>Ward</span>
                  <select
                    value={selectedWardId}
                    onChange={(event) => {
                      setSelectedWardId(event.target.value);
                      setSubmitError(null);
                      setSubmitSuccess(null);
                    }}
                    disabled={isLoading || isSubmitting}
                  >
                    <option value="">Select a ward</option>
                    {wards.map((ward) => (
                      <option key={ward.id} value={ward.id}>
                        {formatWardOptionLabel(ward)}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={sendSms}
                  onChange={(event) => setSendSms(event.target.checked)}
                  disabled={isSubmitting}
                />
                <span>Also request SMS delivery where the backend supports it.</span>
              </label>
            </div>

            <article className="trigger-summary">
              <div className="card-header">
                <BellRing className="section-icon" aria-hidden="true" />
                <h4>Trigger summary</h4>
              </div>
              {isLoading ? (
                <p className="muted">Loading current ward risk context...</p>
              ) : selectedWard ? (
                <dl className="detail-list">
                  <div>
                    <dt>Ward</dt>
                    <dd>{selectedWard.name}</dd>
                  </div>
                  <div>
                    <dt>County</dt>
                    <dd>{selectedWard.county}</dd>
                  </div>
                  <div>
                    <dt>Sub-county</dt>
                    <dd>{selectedWard.subCounty || "Not recorded"}</dd>
                  </div>
                  <div>
                    <dt>Current risk</dt>
                    <dd>
                      {selectedWard.latestRisk?.risk_level ?? "UNKNOWN"}
                      {typeof selectedWard.latestRisk?.risk_score === "number"
                        ? ` (${selectedWard.latestRisk.risk_score.toFixed(2)})`
                        : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>Predicted cases</dt>
                    <dd>{selectedWard.latestRisk?.predicted_cases ?? "Not available"}</dd>
                  </div>
                  <div>
                    <dt>Last update</dt>
                    <dd>{formatTimestamp(selectedWard.latestRisk?.generated_at ?? null)}</dd>
                  </div>
                </dl>
              ) : (
                <p className="muted">Select a ward to review the latest risk context before submitting.</p>
              )}
            </article>

            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={isConfirmed}
                onChange={(event) => setIsConfirmed(event.target.checked)}
                disabled={isSubmitting || !selectedWard}
              />
              <span>I confirm this ward context is correct and I want to queue this alert now.</span>
            </label>

            <div className="inline-actions">
              <button
                type="submit"
                className="button"
                disabled={isSubmitting || isLoading || !selectedWardId || !isConfirmed}
              >
                {isSubmitting ? (
                  <>
                    <LoaderCircle className="section-icon spinning" aria-hidden="true" />
                    Queueing alert...
                  </>
                ) : (
                  <>
                    <BellRing className="section-icon" aria-hidden="true" />
                    Confirm and trigger
                  </>
                )}
              </button>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => {
                  setIsOpen(false);
                  setIsConfirmed(false);
                  setSubmitError(null);
                }}
                disabled={isSubmitting}
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      ) : null}
    </div>
  );
}
