"use client";

import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  ChevronRight,
  LoaderCircle,
  Search,
  ShieldAlert,
  Smartphone,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { formatRelativeTimestamp } from "@/lib/freshness";
import {
  getPageWorkflowStateLabel,
  type LatestWardRisk,
  type TriggerActionType,
  type TriggerAlertResponse,
} from "@/lib/dashboard";
import { useTriggerAlertContextQuery } from "@/queries/use-trigger-alert-context-query";
import { useTriggerAlertMutation } from "@/queries/use-trigger-alert-mutation";
import { useTriggerAlertPreviewQuery } from "@/queries/use-trigger-alert-preview-query";
import { useTriggerAlertRequestStatusQuery } from "@/queries/use-trigger-alert-request-status-query";
import { useWardsQuery } from "@/queries/use-wards-query";

type TriggerableWard = {
  id: number;
  name: string;
  county: string;
  subCounty: string;
  latestRisk: LatestWardRisk | null;
  recentAlertCount: number;
};

type FixedWardContext = {
  id: number;
  name: string;
  county: string | null;
  subCounty: string | null;
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

type FlowStep = 1 | 2 | 3 | 4;

const ACTION_LABELS: Record<TriggerActionType, string> = {
  HIGH_RISK_ESCALATION: "High-risk escalation",
  FOLLOW_UP_REVIEW: "Follow-up / review alert",
  DELIVERY_RETRY: "Delivery retry alert",
  CUSTOM: "Custom alert",
};

function formatRiskLabel(risk: TriggerableWard["latestRisk"]) {
  if (!risk?.risk_level) {
    return "No current risk level";
  }
  const score = risk.risk_score == null ? "" : ` • Score ${Math.round(risk.risk_score * 100)}%`;
  const cases = risk.predicted_cases ? ` • ${risk.predicted_cases} predicted cases` : "";
  return `${risk.risk_level}${score}${cases}`;
}

function formatRiskPriority(riskLevel: LatestWardRisk["risk_level"]) {
  switch (riskLevel) {
    case "HIGH":
      return 0;
    case "MEDIUM":
      return 1;
    case "LOW":
      return 2;
    default:
      return 3;
  }
}

function getRiskTone(level: string | null | undefined) {
  if (level === "HIGH") return "danger" as const;
  if (level === "MEDIUM") return "warning" as const;
  return "default" as const;
}

function getTriggerTypeDescription(type: TriggerActionType) {
  if (type === "HIGH_RISK_ESCALATION") return "Use when risk is elevated and field response should be accelerated.";
  if (type === "FOLLOW_UP_REVIEW") return "Use when recent alerts or open review work still need field confirmation.";
  if (type === "DELIVERY_RETRY") return "Use when delivery is blocked or retry follow-up needs reinforcement.";
  return "Use when the system context is relevant but none of the guided action types fit cleanly.";
}

function getSuccessNextStep(sendSms: boolean) {
  if (sendSms) {
    return "CHVs will be notified shortly. You can track delivery and responses in Alerts.";
  }
  return "The alert request is now logged for review and tracking in Alerts.";
}

function getMessageModeLabel(messageMode: TriggerAlertResponse["message_mode"]) {
  return messageMode === "operator_edited" ? "Edited by operator" : "System-generated draft";
}

export function TriggerAlertPanel({
  buttonLabel = "Create Alert",
  closeLabel = "Close Alert Flow",
  buttonClassName,
  fixedWard = null,
}: TriggerAlertPanelProps) {
  const { currentUser } = useAuth();
  const [isMounted, setIsMounted] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [wards, setWards] = useState<TriggerableWard[]>([]);
  const [selectedWardId, setSelectedWardId] = useState<number | null>(fixedWard?.id ?? null);
  const [step, setStep] = useState<FlowStep>(1);
  const [triggerType, setTriggerType] = useState<TriggerActionType | null>(null);
  const [sendSms, setSendSms] = useState(false);
  const [isEditingMessage, setIsEditingMessage] = useState(false);
  const [messageDraft, setMessageDraft] = useState("");
  const [messageDirty, setMessageDirty] = useState(false);
  const [queuedResponse, setQueuedResponse] = useState<TriggerAlertResponse | null>(null);

  const wardsQuery = useWardsQuery({
    enabled: Boolean(isOpen && currentUser && !fixedWard),
  });
  const contextQuery = useTriggerAlertContextQuery(selectedWardId, Boolean(isOpen && selectedWardId));
  const previewQuery = useTriggerAlertPreviewQuery(selectedWardId, triggerType, null, Boolean(isOpen && selectedWardId && triggerType));
  const triggerMutation = useTriggerAlertMutation();
  const requestStatusQuery = useTriggerAlertRequestStatusQuery(
    queuedResponse?.request_id ?? null,
    Boolean(queuedResponse?.request_id && !queuedResponse?.alert_id),
  );
  const contextError = contextQuery.error instanceof Error ? contextQuery.error.message : null;

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen || !currentUser) {
      return;
    }

    if (fixedWard) {
      setWards([
        {
          id: fixedWard.id,
          name: fixedWard.name,
          county: fixedWard.county ?? "",
          subCounty: fixedWard.subCounty ?? "",
          recentAlertCount: 0,
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
      setSelectedWardId(fixedWard.id);
      setLoadError(null);
      return;
    }

    if (wardsQuery.error) {
      setLoadError(
        wardsQuery.error instanceof Error ? wardsQuery.error.message : "Unable to load wards for alert targeting.",
      );
      return;
    }

    if (!wardsQuery.data) {
      return;
    }

    const latestRiskByWardId = new Map<number, LatestWardRisk>(wardsQuery.data.latestRisks.map((risk) => [risk.ward_id, risk]));

    const nextWards = wardsQuery.data.items.map<TriggerableWard>((ward) => ({
      id: ward.id,
      name: ward.name,
      county: ward.county,
      subCounty: ward.subCounty,
      recentAlertCount: ward.recentAlertCount,
      latestRisk:
        latestRiskByWardId.get(ward.id) ??
        ({
          ward_id: ward.id,
          ward_name: ward.name,
          risk_level: ward.riskLevel === "UNKNOWN" ? null : ward.riskLevel,
          risk_score: ward.riskScore,
          predicted_cases: ward.predictedCases ?? 0,
          generated_at: ward.updatedAt,
        } satisfies LatestWardRisk),
    }));

    setWards(nextWards);
    setLoadError(null);
  }, [currentUser, fixedWard, isOpen, wardsQuery.data, wardsQuery.error]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!contextQuery.data?.system_context.recommended_trigger_type) {
      return;
    }

    setTriggerType((current) => current ?? contextQuery.data.system_context.recommended_trigger_type);
  }, [contextQuery.data?.system_context.recommended_trigger_type]);

  useEffect(() => {
    if (!previewQuery.data?.message_preview || messageDirty) {
      return;
    }

    setMessageDraft(previewQuery.data.message_preview);
  }, [messageDirty, previewQuery.data?.message_preview]);

  const visibleWards = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return wards
      .filter((ward) => {
        if (!normalizedSearch) {
          return true;
        }

        return (
          ward.name.toLowerCase().includes(normalizedSearch) ||
          ward.county.toLowerCase().includes(normalizedSearch) ||
          ward.subCounty.toLowerCase().includes(normalizedSearch)
        );
      })
      .sort((left, right) => {
        const riskPriority =
          formatRiskPriority(left.latestRisk?.risk_level ?? null) -
          formatRiskPriority(right.latestRisk?.risk_level ?? null);
        if (riskPriority !== 0) {
          return riskPriority;
        }
        if (right.recentAlertCount !== left.recentAlertCount) {
          return right.recentAlertCount - left.recentAlertCount;
        }
        const leftScore = left.latestRisk?.risk_score ?? -1;
        const rightScore = right.latestRisk?.risk_score ?? -1;
        if (rightScore !== leftScore) {
          return rightScore - leftScore;
        }
        return left.name.localeCompare(right.name);
      });
  }, [search, wards]);

  const selectedWard = useMemo(
    () => wards.find((ward) => ward.id === selectedWardId) ?? null,
    [selectedWardId, wards],
  );

  function resetPanel() {
    setSearch("");
    setSendSms(false);
    setQueuedResponse(null);
    setLoadError(null);
    setSelectedWardId(fixedWard?.id ?? null);
    setStep(1);
    setTriggerType(null);
    setIsEditingMessage(false);
    setMessageDraft("");
    setMessageDirty(false);
    triggerMutation.reset();
  }

  function handleToggle() {
    setIsOpen((previous) => {
      const next = !previous;
      if (!next) {
        resetPanel();
      }
      return next;
    });
  }

  function handleWardSelection(wardId: number) {
    setSelectedWardId(wardId);
    setStep(1);
    setTriggerType(null);
    setIsEditingMessage(false);
    setMessageDraft("");
    setMessageDirty(false);
  }

  async function handleSubmit() {
    if (!selectedWardId) {
      return;
    }

    const normalizedDraft = messageDraft.trim();
    const previewMessage = previewQuery.data?.message_preview?.trim() ?? "";
    const messageOverride =
      normalizedDraft && normalizedDraft !== previewMessage
        ? normalizedDraft
        : undefined;

    try {
      const response = await triggerMutation.mutateAsync({
        ward_id: selectedWardId,
        send_sms: sendSms,
        trigger_type: triggerType ?? undefined,
        message_override: messageOverride,
      });
      setQueuedResponse(response);
    } catch {
      // mutation state surfaces backend error
    }
  }

  const mutationError = triggerMutation.error instanceof Error ? triggerMutation.error.message : null;
  const canSubmit = Boolean(selectedWardId) && !triggerMutation.isPending;
  const hasWardSelectionStep = !fixedWard;
  const showWardSelection = hasWardSelectionStep && !selectedWardId;
  const stepItems = [
    { id: 1 as FlowStep, label: "Context" },
    { id: 2 as FlowStep, label: "Action" },
    { id: 3 as FlowStep, label: "Delivery" },
    { id: 4 as FlowStep, label: "Review" },
  ];

  const currentTitle = selectedWard ? `Create alert for ${selectedWard.name}` : "Create Alert Request";
  const currentSubtitle = contextQuery.data
    ? `${contextQuery.data.ward.sub_county}, ${contextQuery.data.ward.county}`
    : selectedWard && (selectedWard.subCounty || selectedWard.county)
      ? [selectedWard.subCounty, selectedWard.county].filter(Boolean).join(", ")
      : "Guided trigger flow for operational review and action.";
  const reviewMessage = messageDraft.trim() || previewQuery.data?.message_preview || "Message preview unavailable.";
  const reviewMessageMode =
    previewQuery.data?.message_preview && reviewMessage.trim() !== previewQuery.data.message_preview.trim()
      ? "operator_edited"
      : previewQuery.data?.message_mode ?? "backend_generated";
  const trackedAlertId = queuedResponse?.alert_id ?? requestStatusQuery.data?.alert_id ?? null;
  const trackedRequestPending = Boolean(queuedResponse?.request_id && !trackedAlertId);
  const fallbackWorkflowStatus =
    selectedWard == null
      ? null
      : selectedWard.recentAlertCount > 0
        ? "REVIEW_PENDING"
        : selectedWard.latestRisk?.risk_level === "HIGH" || selectedWard.latestRisk?.risk_level === "MEDIUM"
          ? "REVIEW_PENDING"
          : "NONE";
  const fallbackTriggerType: TriggerActionType | null = selectedWard
    ? selectedWard.recentAlertCount > 0
      ? "FOLLOW_UP_REVIEW"
      : selectedWard.latestRisk?.risk_level === "HIGH"
        ? "HIGH_RISK_ESCALATION"
        : "CUSTOM"
    : null;
  const fallbackContext = selectedWard && fallbackWorkflowStatus
    ? {
        ward: {
          id: selectedWard.id,
          name: selectedWard.name,
          county: selectedWard.county,
          sub_county: selectedWard.subCounty,
        },
        risk: {
          level: selectedWard.latestRisk?.risk_level ?? null,
          score: selectedWard.latestRisk?.risk_score ?? null,
          predicted_cases: selectedWard.latestRisk?.predicted_cases ?? 0,
          last_risk_update_at: selectedWard.latestRisk?.generated_at ?? null,
        },
        workflow: {
          status: fallbackWorkflowStatus,
          decision_mode: "risk_only",
          trigger_reason:
            selectedWard.recentAlertCount > 0
              ? `${selectedWard.name} has recent alert activity that still needs operator review.`
              : fallbackWorkflowStatus === "REVIEW_PENDING"
                ? `${selectedWard.name} should be reviewed using the latest visible ward signals before escalation.`
                : `${selectedWard.name} has no active trigger condition in the latest visible ward signals.`,
          recommended_action:
            selectedWard.latestRisk?.risk_level === "HIGH"
              ? "Review the ward now and decide whether to create an operational alert request."
              : selectedWard.recentAlertCount > 0
                ? "Review recent alert activity and confirm whether follow-up is still needed."
                : fallbackWorkflowStatus === "REVIEW_PENDING"
                  ? "Review this ward and compare recent visible signals before escalating."
                  : "Continue routine monitoring and review recent activity for any early signal changes.",
          active_alert_count: selectedWard.recentAlertCount,
          alert_delivery_state: fallbackWorkflowStatus === "NONE" ? "no_active_delivery" : "awaiting_review",
          alert_delivery_label:
            fallbackWorkflowStatus === "NONE" ? "No active delivery" : "Trigger detected, awaiting alert request",
        },
        system_context: {
          why_this_might_need_an_alert:
            selectedWard.recentAlertCount > 0
              ? [`${selectedWard.recentAlertCount} recent alert${selectedWard.recentAlertCount === 1 ? "" : "s"} need review in this ward.`]
              : fallbackWorkflowStatus === "REVIEW_PENDING"
                ? ["Latest visible ward signals suggest review before escalation."]
                : ["No active trigger condition is visible right now."],
          what_happens_if_no_action:
            selectedWard.recentAlertCount > 0
              ? "Recent alert activity may remain unreviewed and follow-up can be delayed."
              : "The ward will remain in routine monitoring without an additional alert request.",
          trigger_status_label: getPageWorkflowStateLabel(fallbackWorkflowStatus),
          recommended_trigger_type: fallbackTriggerType ?? "CUSTOM",
          confidence_label:
            selectedWard.latestRisk?.risk_level === "HIGH"
              ? "Moderate confidence"
              : "Review required",
        },
        recipient_preview: {
          chv_count: 0,
        },
        supported_delivery_channels: ["DASHBOARD", "SMS_CHV"],
        supported_trigger_types: [
          "HIGH_RISK_ESCALATION",
          "FOLLOW_UP_REVIEW",
          "DELIVERY_RETRY",
          "CUSTOM",
        ] as TriggerActionType[],
      }
    : null;
  const effectiveContext = contextQuery.data ?? fallbackContext;
  const isUsingFallbackContext = !contextQuery.data && Boolean(fallbackContext);

  return (
    <div className="relative grid justify-items-end gap-3 max-[960px]:justify-items-stretch">
      <Button
        type="button"
        className={cn(buttonClassName)}
        onClick={handleToggle}
        aria-expanded={isOpen}
        aria-controls="trigger-alert-panel"
      >
        <BellRing className="size-4" aria-hidden="true" />
        {isOpen ? closeLabel : buttonLabel}
      </Button>

      {isOpen && isMounted
        ? createPortal(
            <>
              <button
                type="button"
                className="fixed inset-0 z-40 bg-[rgba(3,8,22,0.48)] backdrop-blur-[2px]"
                aria-label="Close trigger flow"
                onClick={() => {
                  setIsOpen(false);
                  resetPanel();
                }}
              />

              <Card
                id="trigger-alert-panel"
                className="fixed inset-y-4 right-4 z-50 flex w-[min(44rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-[2rem] border-panel-border p-0 max-[960px]:inset-0 max-[960px]:w-full max-[960px]:rounded-none"
              >
                <div className="border-b border-panel-table-wrap px-6 py-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                        Guided Alert Request
                      </p>
                      <h3 className="mt-1 text-[1.65rem] font-semibold tracking-[-0.04em] text-panel-strong">
                        {currentTitle}
                      </h3>
                      <p className="mt-2 max-w-2xl text-sm text-panel-muted">{currentSubtitle}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-10 rounded-[0.9rem]"
                      onClick={() => {
                        setIsOpen(false);
                        resetPanel();
                      }}
                      aria-label="Close trigger flow"
                    >
                      <X className="size-4" aria-hidden="true" />
                    </Button>
                  </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
                  {queuedResponse ? (
                    <div className="space-y-6">
                      <div className="rounded-[1.5rem] border border-[color-mix(in_srgb,var(--success)_24%,white)] bg-[color-mix(in_srgb,var(--success)_10%,white)] px-5 py-5 dark:border-[color-mix(in_srgb,var(--success)_30%,transparent)] dark:bg-[color-mix(in_srgb,var(--success)_16%,transparent)]">
                        <div className="flex items-start gap-3">
                          <span className="inline-flex size-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--success)_16%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_22%,transparent)]">
                            <CheckCircle2 className="size-5" aria-hidden="true" />
                          </span>
                          <div>
                            <strong className="block text-lg font-semibold text-panel-strong">Alert request queued</strong>
                            <p className="mt-1 text-sm text-panel-copy">
                              Your guided alert request for {queuedResponse.ward_name} has been accepted.
                            </p>
                            <p className="mt-2 text-sm text-panel-muted">{getSuccessNextStep(queuedResponse.send_sms)}</p>
                          </div>
                        </div>
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Ward</p>
                          <p className="mt-2 text-base font-semibold text-panel-strong">{queuedResponse.ward_name}</p>
                          <p className="mt-1 text-xs text-panel-muted">
                            {queuedResponse.risk_level}
                            {queuedResponse.risk_score != null ? ` • Score ${Math.round(queuedResponse.risk_score * 100)}%` : ""}
                          </p>
                        </Card>
                        <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Delivery</p>
                          <p className="mt-2 text-base font-semibold text-panel-strong">
                            {queuedResponse.send_sms ? "SMS to CHVs + dashboard tracking" : "Dashboard tracking only"}
                          </p>
                          <p className="mt-1 text-xs text-panel-muted">
                            {queuedResponse.send_sms && queuedResponse.estimated_chv_recipient_count != null
                              ? `${queuedResponse.estimated_chv_recipient_count} CHVs queued for notification`
                              : "The request is now available for monitoring in Alerts."}
                          </p>
                        </Card>
                      </div>

                      <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                        <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Message source</p>
                        <p className="mt-2 text-base font-semibold text-panel-strong">
                          {getMessageModeLabel(queuedResponse.message_mode)}
                        </p>
                        <p className="mt-1 text-xs text-panel-muted">
                          {queuedResponse.message_mode === "operator_edited"
                            ? "The queued request used an operator-adjusted guided message."
                            : "The queued request used the system-generated guided draft."}
                        </p>
                      </Card>

                      <div className="grid gap-4 md:grid-cols-2">
                        <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">What happens next</p>
                          <p className="mt-2 text-sm font-semibold text-panel-strong">
                            {trackedAlertId
                              ? "Alert record is now available for review."
                              : queuedResponse.trigger_linkage_state === "linked_existing_workflow"
                                ? "Linked to the current trigger workflow."
                                : "The request will continue through the alert workflow."}
                          </p>
                          <p className="mt-1 text-xs text-panel-muted">
                            {trackedAlertId && requestStatusQuery.data?.last_materialized_at
                              ? `Materialized ${formatRelativeTimestamp(requestStatusQuery.data.last_materialized_at)}`
                              : `Queued ${formatRelativeTimestamp(queuedResponse.queued_at)}`}
                          </p>
                        </Card>
                        <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Latest risk update</p>
                          <p className="mt-2 text-sm font-semibold text-panel-strong">
                            {queuedResponse.last_risk_update_at
                              ? formatRelativeTimestamp(queuedResponse.last_risk_update_at)
                              : "Unavailable"}
                          </p>
                        </Card>
                      </div>

                      <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                        <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Request tracking</p>
                        <p className="mt-2 text-base font-semibold text-panel-strong">
                          {trackedAlertId ? "Alert record linked" : "Waiting for alert record"}
                        </p>
                        <p className="mt-1 text-xs text-panel-muted">
                          {trackedAlertId
                            ? "You can open the recorded alert now."
                            : requestStatusQuery.isFetching
                              ? "Checking the queue for the recorded alert..."
                              : "The request is queued. This panel will link to the recorded alert as soon as it is created."}
                        </p>
                      </Card>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      {loadError ? (
                        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
                          {loadError}
                        </StatusBanner>
                      ) : null}

                      {mutationError ? (
                        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
                          {mutationError}
                        </StatusBanner>
                      ) : null}

                      {!showWardSelection && contextError ? (
                        <StatusBanner tone={isUsingFallbackContext ? "warning" : "danger"} icon={<AlertTriangle aria-hidden="true" />}>
                          {isUsingFallbackContext
                            ? "Detailed ward guidance is temporarily unavailable. Continuing with the latest visible dashboard data for this ward."
                            : contextError}
                        </StatusBanner>
                      ) : null}

                      {!showWardSelection ? (
                        <div className="flex flex-wrap gap-2">
                          {stepItems.map((item) => (
                            <div
                              key={item.id}
                              className={cn(
                                "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold tracking-[0.12em]",
                                step === item.id
                                  ? "border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-brand"
                                  : "border-panel-table-wrap text-panel-muted",
                              )}
                            >
                              <span>{item.id}</span>
                              <span>{item.label}</span>
                            </div>
                          ))}
                        </div>
                      ) : null}

                      {showWardSelection ? (
                        <div className="space-y-4">
                          <div className="space-y-2">
                            <h4 className="text-lg font-semibold text-panel-strong">Choose a ward to review</h4>
                            <p className="text-sm text-panel-muted">
                              Start by selecting the ward you want the system to evaluate for alert action.
                            </p>
                          </div>

                          <InputShell
                            icon={<Search className="size-4" aria-hidden="true" />}
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Search ward, county, or sub-county..."
                          />

                          <div className="rounded-[1.5rem] border border-panel-table-wrap">
                            <div className="max-h-[24rem] overflow-y-auto p-3">
                              <div className="grid gap-3">
                                {wardsQuery.isPending ? (
                                  <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-6 text-sm text-panel-muted">
                                    Loading available wards...
                                  </div>
                                ) : visibleWards.length > 0 ? (
                                  visibleWards.map((ward) => (
                                    <button
                                      key={ward.id}
                                      type="button"
                                      className={cn(
                                        "rounded-[1.3rem] border px-4 py-4 text-left transition",
                                        selectedWardId === ward.id
                                          ? "border-brand bg-[color-mix(in_srgb,var(--brand)_8%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                                          : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] hover:border-[var(--dashboard-icon-button-border)]",
                                      )}
                                      onClick={() => handleWardSelection(ward.id)}
                                    >
                                      <div className="flex items-start justify-between gap-3">
                                        <div>
                                          <strong className="block text-sm font-semibold text-panel-strong">{ward.name}</strong>
                                          <p className="mt-1 text-xs text-panel-muted">
                                            {ward.subCounty}, {ward.county}
                                          </p>
                                          <p className="mt-2 text-xs font-medium text-panel-copy">{formatRiskLabel(ward.latestRisk)}</p>
                                        </div>
                                        <StatusBadge tone={getRiskTone(ward.latestRisk?.risk_level)} className="px-3 py-1 tracking-[0.14em]">
                                          {ward.latestRisk?.risk_level ?? "NO RISK"}
                                        </StatusBadge>
                                      </div>
                                    </button>
                                  ))
                                ) : (
                                  <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-6 text-sm text-panel-muted">
                                    No wards match the current search.
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : null}

                      {!showWardSelection && contextQuery.isLoading && !effectiveContext ? (
                        <Card className="rounded-[1.5rem] px-5 py-6 shadow-none">
                          <div className="flex items-center gap-3 text-sm text-panel-muted">
                            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                            Loading alert guidance...
                          </div>
                        </Card>
                      ) : null}

                      {!showWardSelection && effectiveContext ? (
                        <>
                          {step === 1 ? (
                            <div className="space-y-4">
                              <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                                <div className="flex items-start justify-between gap-4">
                                  <div>
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Context</p>
                                    <h4 className="mt-2 text-lg font-semibold text-panel-strong">{effectiveContext.ward.name}</h4>
                                    <p className="mt-1 text-sm text-panel-muted">
                                      {effectiveContext.ward.sub_county}, {effectiveContext.ward.county}
                                    </p>
                                  </div>
                                  <StatusBadge tone={getRiskTone(effectiveContext.risk.level)} className="px-3 py-1 tracking-[0.14em]">
                                    {effectiveContext.risk.level ?? "NO RISK"}
                                  </StatusBadge>
                                </div>

                                <div className="mt-4 grid gap-3 md:grid-cols-2">
                                  <div className="rounded-[1.2rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4">
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Current risk</p>
                                    <p className="mt-2 text-sm font-semibold text-panel-strong">
                                      {effectiveContext.risk.level ?? "Unavailable"}
                                      {effectiveContext.risk.score != null ? ` • Score ${Math.round(effectiveContext.risk.score * 100)}%` : ""}
                                    </p>
                                    <p className="mt-1 text-xs text-panel-muted">
                                      {effectiveContext.risk.last_risk_update_at
                                        ? `Last updated ${formatRelativeTimestamp(effectiveContext.risk.last_risk_update_at)}`
                                        : "Last risk update unavailable"}
                                    </p>
                                  </div>
                                  <div className="rounded-[1.2rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4">
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Trigger status</p>
                                    <p className="mt-2 text-sm font-semibold text-panel-strong">
                                      {effectiveContext.system_context.trigger_status_label}
                                    </p>
                                    <p className="mt-1 text-xs text-panel-muted">
                                      {effectiveContext.workflow.active_alert_count} active alert
                                      {effectiveContext.workflow.active_alert_count === 1 ? "" : "s"} in the current workflow.
                                    </p>
                                  </div>
                                </div>

                                <div className="mt-4 space-y-3">
                                  <div>
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Why this matters</p>
                                    <ul className="mt-2 space-y-2 text-sm text-panel-copy">
                                      {effectiveContext.system_context.why_this_might_need_an_alert.map((reason) => (
                                        <li key={reason}>{reason}</li>
                                      ))}
                                    </ul>
                                  </div>
                                  <div>
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                                      What happens if no action is taken
                                    </p>
                                    <p className="mt-2 text-sm text-panel-copy">{effectiveContext.system_context.what_happens_if_no_action}</p>
                                  </div>
                                  <div className="grid gap-3 md:grid-cols-2">
                                    <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recommended action</p>
                                      <p className="mt-2 text-sm font-semibold text-panel-strong">{effectiveContext.workflow.recommended_action}</p>
                                    </div>
                                    <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Confidence</p>
                                      <p className="mt-2 text-sm font-semibold text-panel-strong">
                                        {effectiveContext.system_context.confidence_label}
                                      </p>
                                    </div>
                                  </div>
                                </div>
                              </Card>
                            </div>
                          ) : null}

                          {step === 2 ? (
                            <div className="space-y-4">
                              <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                                <h4 className="text-lg font-semibold text-panel-strong">What action do you want to take?</h4>
                                <p className="mt-2 text-sm text-panel-muted">
                                  The system has preselected a recommended action based on current workflow state and recent alert activity.
                                </p>

                                <div className="mt-4 grid gap-3">
                                  {effectiveContext.supported_trigger_types.map((type) => {
                                    const isSelected = triggerType === type;
                                    return (
                                      <button
                                        key={type}
                                        type="button"
                                        className={cn(
                                          "rounded-[1.3rem] border px-4 py-4 text-left transition",
                                          isSelected
                                            ? "border-brand bg-[color-mix(in_srgb,var(--brand)_8%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                                            : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] hover:border-[var(--dashboard-icon-button-border)]",
                                        )}
                                        onClick={() => setTriggerType(type)}
                                      >
                                        <div className="flex items-start justify-between gap-3">
                                          <div>
                                            <strong className="block text-sm font-semibold text-panel-strong">{ACTION_LABELS[type]}</strong>
                                            <p className="mt-1 text-sm text-panel-muted">{getTriggerTypeDescription(type)}</p>
                                          </div>
                                          {effectiveContext.system_context.recommended_trigger_type === type ? (
                                            <StatusBadge tone="info" className="px-3 py-1 tracking-[0.14em]">
                                              Recommended
                                            </StatusBadge>
                                          ) : null}
                                        </div>
                                      </button>
                                    );
                                  })}
                                </div>
                              </Card>

                              <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div>
                                    <h4 className="text-lg font-semibold text-panel-strong">Message preview</h4>
                                    <p className="mt-2 text-sm text-panel-muted">
                                      Start from the system draft, then adjust the wording only if local context requires it.
                                    </p>
                                  </div>
                                  {previewQuery.data?.supports_editing ? (
                                    <Button
                                      type="button"
                                      variant="secondary"
                                      onClick={() => {
                                        setIsEditingMessage((current) => !current);
                                        setMessageDraft((current) => current || previewQuery.data?.message_preview || "");
                                      }}
                                    >
                                      {isEditingMessage ? "Use system draft view" : "Edit message"}
                                    </Button>
                                  ) : null}
                                </div>
                                {previewQuery.isLoading ? (
                                  <div className="mt-4 flex items-center gap-3 text-sm text-panel-muted">
                                    <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                                    Preparing message preview...
                                  </div>
                                ) : (
                                  <>
                                    {isEditingMessage ? (
                                      <div className="mt-4 space-y-3">
                                        <textarea
                                          value={messageDraft}
                                          onChange={(event) => {
                                            setMessageDraft(event.target.value);
                                            setMessageDirty(true);
                                          }}
                                          rows={6}
                                          maxLength={320}
                                          className="w-full rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4 text-sm text-panel-copy outline-none transition focus:border-brand"
                                        />
                                        <div className="flex items-center justify-between gap-3 text-xs text-panel-muted">
                                          <span>Your edited message will be validated and audited when the request is queued.</span>
                                          <span>{messageDraft.length}/320</span>
                                        </div>
                                      </div>
                                    ) : (
                                      <p className="mt-4 rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4 text-sm text-panel-copy">
                                        {previewQuery.data?.message_preview ?? "Message preview unavailable."}
                                      </p>
                                    )}
                                    <p className="mt-3 text-xs text-panel-muted">
                                      {isEditingMessage
                                        ? "Edited wording is optional. If unchanged, the system draft will be used."
                                        : "This draft is generated from the current workflow state and ward context."}
                                    </p>
                                  </>
                                )}
                              </Card>
                            </div>
                          ) : null}

                          {step === 3 ? (
                            <div className="space-y-4">
                              <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                                <h4 className="text-lg font-semibold text-panel-strong">Delivery</h4>
                                <div className="mt-4 grid gap-3">
                                  <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                    <div className="flex items-start justify-between gap-3">
                                      <div>
                                        <strong className="block text-sm font-semibold text-panel-strong">Dashboard record</strong>
                                        <p className="mt-1 text-sm text-panel-muted">Logs the alert for tracking and review.</p>
                                      </div>
                                      <StatusBadge tone="info" className="px-3 py-1 tracking-[0.14em]">
                                        Included
                                      </StatusBadge>
                                    </div>
                                  </div>

                                  <label className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                    <div className="flex items-start gap-3">
                                      <input
                                        type="checkbox"
                                        className="mt-1 size-4 rounded border border-panel-table-wrap accent-[var(--brand)]"
                                        checked={sendSms}
                                        onChange={(event) => setSendSms(event.target.checked)}
                                      />
                                      <div className="min-w-0 flex-1">
                                        <strong className="block text-sm font-semibold text-panel-strong">SMS to CHVs</strong>
                                        <p className="mt-1 text-sm text-panel-muted">Notifies community health volunteers.</p>
                                        <p className="mt-2 text-xs text-panel-muted">
                                          {previewQuery.data?.recipient_preview.chv_count != null
                                            ? `${previewQuery.data.recipient_preview.chv_count} CHVs available in this ward`
                                            : "Recipient count unavailable right now."}
                                        </p>
                                      </div>
                                      <Smartphone className="mt-0.5 size-4 text-brand" aria-hidden="true" />
                                    </div>
                                  </label>
                                </div>
                              </Card>
                            </div>
                          ) : null}

                          {step === 4 ? (
                            <div className="space-y-4">
                              <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                                <h4 className="text-lg font-semibold text-panel-strong">Review</h4>
                                <div className="mt-4 grid gap-3 md:grid-cols-2">
                                  <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Ward</p>
                                    <p className="mt-2 text-sm font-semibold text-panel-strong">{effectiveContext.ward.name}</p>
                                    <p className="mt-1 text-xs text-panel-muted">
                                      {effectiveContext.risk.level ?? "Unavailable"}
                                      {effectiveContext.risk.score != null ? ` • Score ${Math.round(effectiveContext.risk.score * 100)}%` : ""}
                                    </p>
                                  </div>
                                  <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">What action do you want to take?</p>
                                    <p className="mt-2 text-sm font-semibold text-panel-strong">
                                      {triggerType ? ACTION_LABELS[triggerType] : "Not selected"}
                                    </p>
                                  </div>
                                  <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Who will be notified</p>
                                    <p className="mt-2 text-sm font-semibold text-panel-strong">
                                      {sendSms
                                        ? `${previewQuery.data?.recipient_preview.chv_count ?? 0} CHVs plus dashboard tracking`
                                        : "Dashboard tracking only"}
                                    </p>
                                  </div>
                                  <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Based on</p>
                                    <p className="mt-2 text-sm font-semibold text-panel-strong">
                                      workflow state and recent alert activity
                                    </p>
                                    <p className="mt-1 text-xs text-panel-muted">{effectiveContext.workflow.trigger_reason}</p>
                                  </div>
                                </div>

                                <div className="mt-3 rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Message</p>
                                  <p className="mt-2 text-sm text-panel-copy">{reviewMessage}</p>
                                  <p className="mt-2 text-xs text-panel-muted">
                                    {reviewMessageMode === "operator_edited" ? "Edited by operator before queueing" : "System-generated draft"}
                                  </p>
                                </div>

                                <div className="mt-3 rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">What happens next</p>
                                  <p className="mt-2 text-sm text-panel-copy">
                                    {sendSms
                                      ? "The request will queue dashboard tracking and SMS delivery for CHVs in this ward."
                                      : "The request will queue dashboard tracking so the team can monitor the resulting alert activity."}
                                  </p>
                                </div>
                              </Card>
                            </div>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-panel-table-wrap px-6 py-5">
                  {queuedResponse ? (
                    <>
                      <div className="flex flex-wrap items-center gap-3">
                        {trackedAlertId ? (
                          <Link
                            href={`/alerts/${trackedAlertId}`}
                            className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                          >
                            View alert
                          </Link>
                        ) : trackedRequestPending ? (
                          <div className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 text-sm font-semibold text-panel-muted">
                            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                            Tracking alert record
                          </div>
                        ) : null}
                        <Link
                          href={selectedWardId ? `/wards/${selectedWardId}` : "/alerts"}
                          className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                        >
                          Go to ward
                        </Link>
                      </div>
                      <Button
                        onClick={() => {
                          setQueuedResponse(null);
                          triggerMutation.reset();
                        }}
                      >
                        Create another
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          if (showWardSelection) {
                            setIsOpen(false);
                            resetPanel();
                            return;
                          }
                          if (step > 1) {
                            setStep((current) => (current - 1) as FlowStep);
                            return;
                          }
                          if (!fixedWard) {
                            setSelectedWardId(null);
                            setTriggerType(null);
                            return;
                          }
                          setIsOpen(false);
                          resetPanel();
                        }}
                      >
                        {!showWardSelection && step > 1 ? "Back" : "Cancel"}
                      </Button>

                      {showWardSelection ? (
                        <Button
                          onClick={() => {
                            if (selectedWardId) {
                              setStep(1);
                            }
                          }}
                          disabled={!selectedWardId}
                        >
                          Continue
                        </Button>
                      ) : step < 4 ? (
                        <Button
                          onClick={() => setStep((current) => (current + 1) as FlowStep)}
                          disabled={
                            (contextQuery.isLoading && !effectiveContext) ||
                            (step === 2 && (!triggerType || previewQuery.isLoading)) ||
                            (step === 1 && !effectiveContext)
                          }
                        >
                          Continue
                          <ChevronRight className="size-4" aria-hidden="true" />
                        </Button>
                      ) : (
                        <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
                          {triggerMutation.isPending ? (
                            <>
                              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                              Queueing request...
                            </>
                          ) : (
                            <>
                              <BellRing className="size-4" aria-hidden="true" />
                              Queue Alert Request
                            </>
                          )}
                        </Button>
                      )}
                    </>
                  )}
                </div>
              </Card>
            </>,
            document.body,
          )
        : null}
    </div>
  );
}
