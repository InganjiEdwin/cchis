"use client";

import { AlertTriangle, BellRing, CheckCircle2, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import type { OverviewTriggerEvent } from "@/lib/dashboard";

type TriggerReviewDrawerProps = {
  trigger: OverviewTriggerEvent | null;
  onClose: () => void;
};

function formatRiskScore(score: number | null) {
  if (score == null) {
    return "Unavailable";
  }

  const normalized = score <= 1 ? score * 100 : score;
  return `${Math.round(normalized)}%`;
}

function formatConfidenceLabel(confidence: OverviewTriggerEvent["confidence"]) {
  if (confidence === "high") return "High confidence";
  if (confidence === "moderate") return "Moderate confidence";
  return "Needs review";
}

function formatRiskTone(riskLevel: OverviewTriggerEvent["risk_level"]) {
  if (riskLevel === "HIGH") return "danger" as const;
  if (riskLevel === "MEDIUM") return "warning" as const;
  return "default" as const;
}

export function TriggerReviewDrawer({ trigger, onClose }: TriggerReviewDrawerProps) {
  const [isMounted, setIsMounted] = useState(false);
  const [dismissedTriggerIds, setDismissedTriggerIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!trigger) {
      return;
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleEscape);
    };
  }, [onClose, trigger]);

  if (!trigger || dismissedTriggerIds.has(trigger.trigger_id) || !isMounted) {
    return null;
  }

  return createPortal(
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-[rgba(3,8,22,0.48)] backdrop-blur-[2px]"
        aria-label="Close trigger review"
        onClick={onClose}
      />

      <Card className="fixed inset-y-4 right-4 z-50 flex w-[min(44rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-[2rem] border-panel-border p-0 max-[960px]:inset-0 max-[960px]:w-full max-[960px]:rounded-none">
        <div className="border-b border-panel-table-wrap px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                Trigger detected
              </p>
              <h3 className="mt-1 text-[1.65rem] font-semibold tracking-[-0.04em] text-panel-strong">
                {trigger.ward_name}
              </h3>
              <p className="mt-2 max-w-2xl text-sm text-panel-muted">
                The system detected a trigger condition. Review the reasoning, then decide whether to create a real alert request.
              </p>
            </div>
            <Button variant="ghost" size="icon" className="size-10 rounded-[0.9rem]" onClick={onClose} aria-label="Close trigger review">
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <div className="space-y-6">
            <div className="rounded-[1.5rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-5 py-5">
              <div className="flex flex-wrap items-center gap-3">
                <StatusBadge tone={formatRiskTone(trigger.risk_level)} className="rounded-full px-3 py-1 tracking-[0.14em]">
                  {trigger.risk_level ?? "Unknown risk"}
                </StatusBadge>
                <StatusBadge tone={trigger.confidence === "high" ? "danger" : trigger.confidence === "moderate" ? "warning" : "default"} className="rounded-full px-3 py-1 tracking-[0.14em]">
                  {formatConfidenceLabel(trigger.confidence)}
                </StatusBadge>
                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">{trigger.trend_label}</span>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-4">
                <div className="rounded-[1.2rem] bg-panel/70 px-4 py-4">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Risk score</p>
                  <p className="mt-2 text-lg font-semibold text-panel-strong">{formatRiskScore(trigger.risk_score)}</p>
                </div>
                <div className="rounded-[1.2rem] bg-panel/70 px-4 py-4">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Predicted cases</p>
                  <p className="mt-2 text-lg font-semibold text-panel-strong">{trigger.predicted_cases}</p>
                </div>
                <div className="rounded-[1.2rem] bg-panel/70 px-4 py-4">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Open alerts</p>
                  <p className="mt-2 text-lg font-semibold text-panel-strong">{trigger.alert_count}</p>
                </div>
                <div className="rounded-[1.2rem] bg-panel/70 px-4 py-4">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Risk update</p>
                  <p className="mt-2 text-sm font-semibold text-panel-strong">{trigger.latest_risk_update_at ? "Recorded" : "Unavailable"}</p>
                </div>
              </div>
            </div>

            <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
              <div className="flex items-center gap-3">
                <AlertTriangle className="size-4 text-[color:var(--danger)]" aria-hidden="true" />
                <h4 className="text-lg font-semibold text-panel-strong">Why this triggered</h4>
              </div>
              <div className="mt-4 space-y-3">
                {trigger.trigger_reason_items.map((item) => (
                  <div key={item.label} className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                    <div className="flex items-center gap-2">
                      <StatusBadge tone={item.tone === "danger" ? "danger" : item.tone === "warning" ? "warning" : "info"}>
                        {item.label}
                      </StatusBadge>
                    </div>
                    <p className="mt-2 text-sm text-panel-copy">{item.detail}</p>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="size-4 text-[color:var(--success)]" aria-hidden="true" />
                <h4 className="text-lg font-semibold text-panel-strong">Recommended action</h4>
              </div>
              <p className="mt-4 text-sm text-panel-copy">{trigger.recommended_action}</p>
              <div className="mt-3 rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4 text-sm text-panel-muted">
                Expected operational effect: {trigger.expected_operational_effect}
              </div>
            </Card>

            <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
              <div className="flex items-center gap-3">
                <BellRing className="size-4 text-brand" aria-hidden="true" />
                <h4 className="text-lg font-semibold text-panel-strong">Pre-filled alert request</h4>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Ward</p>
                  <p className="mt-2 text-sm font-semibold text-panel-strong">{trigger.ward_name}</p>
                  <p className="mt-1 text-xs text-panel-muted">This field is locked to the detected trigger context.</p>
                </div>
                <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Current flow scope</p>
                  <p className="mt-2 text-sm font-semibold text-panel-strong">Guided single-ward alert request</p>
                  <p className="mt-1 text-xs text-panel-muted">
                    This workflow stays focused on one ward at a time so the request can be reviewed and confirmed clearly.
                  </p>
                </div>
              </div>
              <div className="mt-4">
                <TriggerAlertPanel
                  fixedWard={{
                    id: trigger.ward_id,
                    name: trigger.ward_name,
                    county: null,
                    subCounty: null,
                    riskLevel: trigger.risk_level ?? "UNKNOWN",
                    riskScore: trigger.risk_score,
                    predictedCases: trigger.predicted_cases,
                    updatedAt: trigger.latest_risk_update_at,
                  }}
                  buttonLabel="Trigger Alert"
                  closeLabel="Close Alert Request"
                />
              </div>
            </Card>

            <StatusBadge tone="warning" className="justify-center px-4 py-2">
              Dismiss only removes this review from your current screen. The recorded trigger status does not change.
            </StatusBadge>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-panel-table-wrap px-6 py-5">
          <Button
            variant="secondary"
            onClick={() => {
              setDismissedTriggerIds((current) => new Set(current).add(trigger.trigger_id));
              onClose();
            }}
          >
            Dismiss
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Close review
          </Button>
        </div>
      </Card>
    </>,
    document.body,
  );
}
