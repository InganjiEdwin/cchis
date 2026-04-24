"use client";

import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
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
import { type LatestWardRisk, type TriggerAlertResponse, type WardSummary } from "@/lib/dashboard";
import { useTriggerAlertMutation } from "@/queries/use-trigger-alert-mutation";
import { useWardsQuery } from "@/queries/use-wards-query";

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

function formatRiskLabel(risk: TriggerableWard["latestRisk"]) {
  if (!risk?.risk_level) {
    return "No current risk level";
  }
  const score = risk.risk_score == null ? "" : ` • Score ${Math.round(risk.risk_score * 100)}%`;
  const cases = risk.predicted_cases ? ` • ${risk.predicted_cases} predicted cases` : "";
  return `${risk.risk_level}${score}${cases}`;
}

export function TriggerAlertPanel({
  buttonLabel = "Trigger Alert",
  closeLabel = "Close Alert Builder",
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
  const [sendSms, setSendSms] = useState(false);
  const [queuedResponse, setQueuedResponse] = useState<TriggerAlertResponse | null>(null);
  const wardsQuery = useWardsQuery({
    enabled: Boolean(isOpen && currentUser && !fixedWard),
  });
  const triggerMutation = useTriggerAlertMutation();

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

    const latestRiskByWardId = new Map<number, LatestWardRisk>(
      wardsQuery.data.latestRisks.map((risk) => [risk.ward_id, risk]),
    );

    const nextWards = wardsQuery.data.wards.results.map<TriggerableWard>((ward: WardSummary) => ({
      id: ward.id,
      name: ward.name,
      county: ward.county,
      subCounty: ward.sub_county,
      latestRisk: latestRiskByWardId.get(ward.id) ?? null,
    }));

    setWards(nextWards);
    setLoadError(null);

    if (!selectedWardId) {
      setSelectedWardId(currentUser.scope_ward_id ?? currentUser.ward ?? nextWards[0]?.id ?? null);
    }
  }, [currentUser, fixedWard, isOpen, selectedWardId, wardsQuery.data, wardsQuery.error]);

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

  const visibleWards = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return wards.filter((ward) => {
      if (!normalizedSearch) {
        return true;
      }

      return (
        ward.name.toLowerCase().includes(normalizedSearch) ||
        ward.county.toLowerCase().includes(normalizedSearch) ||
        ward.subCounty.toLowerCase().includes(normalizedSearch)
      );
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

  async function handleSubmit() {
    if (!selectedWardId) {
      return;
    }

    try {
      const response = await triggerMutation.mutateAsync({
        ward_id: selectedWardId,
        send_sms: sendSms,
      });
      setQueuedResponse(response);
    } catch {
      // Query mutation state already surfaces the backend error.
    }
  }

  const canSubmit = Boolean(selectedWardId) && !triggerMutation.isPending;
  const mutationError = triggerMutation.error instanceof Error ? triggerMutation.error.message : null;

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
                aria-label="Close alert builder"
                onClick={() => {
                  setIsOpen(false);
                  resetPanel();
                }}
              />

              <Card
                id="trigger-alert-panel"
                className="fixed inset-y-4 right-4 z-50 flex w-[min(42rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-[2rem] border-panel-border p-0 max-[960px]:inset-0 max-[960px]:w-full max-[960px]:rounded-none"
              >
                <div className="border-b border-panel-table-wrap px-6 py-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                        Trigger Alert
                      </p>
                      <h3 className="mt-1 text-[1.65rem] font-semibold tracking-[-0.04em] text-panel-strong">
                        Queue a real alert trigger
                      </h3>
                      <p className="mt-2 max-w-2xl text-sm text-panel-muted">
                        This workflow now matches the backend contract: select one ward and decide whether CHV SMS delivery should also be queued.
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-10 rounded-[0.9rem]"
                      onClick={() => {
                        setIsOpen(false);
                        resetPanel();
                      }}
                      aria-label="Close alert workflow"
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
                            <strong className="block text-lg font-semibold text-panel-strong">Alert trigger queued</strong>
                            <p className="mt-1 text-sm text-panel-copy">
                              The backend accepted the request and queued alert generation for {selectedWard?.name ?? "the selected ward"}.
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="grid gap-4 md:grid-cols-3">
                        <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Task ID</p>
                          <p className="mt-2 break-all text-base font-semibold text-panel-strong">{queuedResponse.task_id}</p>
                        </Card>
                        <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Risk Score</p>
                          <p className="mt-2 text-xl font-semibold tracking-[-0.04em] text-panel-strong">
                            {queuedResponse.risk_score_id}
                          </p>
                        </Card>
                        <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Delivery scope</p>
                          <p className="mt-2 text-sm font-semibold text-panel-strong">
                            Dashboard {sendSms ? "+ SMS to active CHVs" : "only"}
                          </p>
                        </Card>
                      </div>

                      <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                        <h4 className="text-lg font-semibold text-panel-strong">What is real now</h4>
                        <div className="mt-4 space-y-3 text-sm text-panel-copy">
                          <p>The task is queued in the backend and will create alert records from the latest matching ward risk score in scope.</p>
                          <p>Delivery progress, retries, and failures will appear as real alert records on the alerts pages after the task runs.</p>
                          <p>Templates, approval chains, scheduling, and multi-channel orchestration are intentionally out of scope for this v1 trigger flow.</p>
                        </div>
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

                      <StatusBanner tone="warning" icon={<ShieldAlert aria-hidden="true" />}>
                        The richer alert-builder flow has been collapsed to the current backend-owned contract. Unsupported features like templates, scheduling, and approval timelines are no longer simulated here.
                      </StatusBanner>

                      {!fixedWard ? (
                        <div className="space-y-4">
                          <div className="space-y-2">
                            <h4 className="text-lg font-semibold text-panel-strong">Select one ward</h4>
                            <p className="text-sm text-panel-muted">
                              The backend trigger uses the latest matching risk score for the selected ward.
                            </p>
                          </div>

                          <InputShell
                            icon={<Search className="size-4" aria-hidden="true" />}
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Search ward, county, or sub-county..."
                          />

                          <div className="rounded-[1.5rem] border border-panel-table-wrap">
                            <div className="max-h-[18rem] overflow-y-auto p-3">
                              <div className="grid gap-3">
                                {wardsQuery.isPending ? (
                                  <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-6 text-sm text-panel-muted">
                                    Loading available wards...
                                  </div>
                                ) : visibleWards.length > 0 ? (
                                  visibleWards.map((ward) => {
                                    const isSelected = selectedWardId === ward.id;
                                    return (
                                      <button
                                        key={ward.id}
                                        type="button"
                                        className={cn(
                                          "rounded-[1.3rem] border px-4 py-4 text-left transition",
                                          isSelected
                                            ? "border-brand bg-[color-mix(in_srgb,var(--brand)_8%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                                            : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] hover:border-[var(--dashboard-icon-button-border)]",
                                        )}
                                        onClick={() => setSelectedWardId(ward.id)}
                                      >
                                        <div className="flex items-start justify-between gap-3">
                                          <div>
                                            <strong className="block text-sm font-semibold text-panel-strong">{ward.name}</strong>
                                            <p className="mt-1 text-xs text-panel-muted">
                                              {ward.subCounty}, {ward.county}
                                            </p>
                                            <p className="mt-2 text-xs font-medium text-panel-copy">
                                              {formatRiskLabel(ward.latestRisk)}
                                            </p>
                                          </div>
                                          {isSelected ? (
                                            <StatusBadge tone="info" className="px-3 py-1 tracking-[0.14em]">
                                              Selected
                                            </StatusBadge>
                                          ) : null}
                                        </div>
                                      </button>
                                    );
                                  })
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

                      {selectedWard ? (
                        <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                                Selected ward
                              </p>
                              <h4 className="mt-2 text-lg font-semibold text-panel-strong">{selectedWard.name}</h4>
                              <p className="mt-1 text-sm text-panel-muted">
                                {selectedWard.subCounty}, {selectedWard.county}
                              </p>
                            </div>
                            <StatusBadge
                              tone={
                                selectedWard.latestRisk?.risk_level === "HIGH"
                                  ? "danger"
                                  : selectedWard.latestRisk?.risk_level === "MEDIUM"
                                    ? "warning"
                                    : "default"
                              }
                              className="px-3 py-1 tracking-[0.14em]"
                            >
                              {selectedWard.latestRisk?.risk_level ?? "NO RISK"}
                            </StatusBadge>
                          </div>

                          <div className="mt-4 grid gap-3 md:grid-cols-2">
                            <div className="rounded-[1.2rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4">
                              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Risk signal</p>
                              <p className="mt-2 text-sm font-semibold text-panel-strong">{formatRiskLabel(selectedWard.latestRisk)}</p>
                            </div>
                            <div className="rounded-[1.2rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4">
                              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Delivery behavior</p>
                              <p className="mt-2 text-sm font-semibold text-panel-strong">
                                Dashboard alert{sendSms ? " plus SMS to active CHVs" : " only"}
                              </p>
                            </div>
                          </div>
                        </Card>
                      ) : null}

                      <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                        <div className="flex items-start gap-3">
                          <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_16%,transparent)]">
                            <Smartphone className="size-4" aria-hidden="true" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <label className="flex cursor-pointer items-start gap-3">
                              <input
                                type="checkbox"
                                className="mt-1 size-4 rounded border border-panel-table-wrap accent-[var(--brand)]"
                                checked={sendSms}
                                onChange={(event) => setSendSms(event.target.checked)}
                              />
                              <div>
                                <strong className="block text-sm font-semibold text-panel-strong">Also queue SMS delivery</strong>
                                <p className="mt-1 text-sm text-panel-muted">
                                  When enabled, the backend will create SMS alerts for active CHVs in the selected ward in addition to the dashboard alert.
                                </p>
                              </div>
                            </label>
                          </div>
                        </div>
                      </Card>
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-panel-table-wrap px-6 py-5">
                  {queuedResponse ? (
                    <>
                      <Link
                        href="/alerts"
                        className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                      >
                        View Alerts
                      </Link>
                      <Button
                        onClick={() => {
                          setQueuedResponse(null);
                          triggerMutation.reset();
                        }}
                      >
                        Queue Another
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setIsOpen(false);
                          resetPanel();
                        }}
                      >
                        Cancel
                      </Button>
                      <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
                        {triggerMutation.isPending ? (
                          <>
                            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                            Queueing...
                          </>
                        ) : (
                          <>
                            <BellRing className="size-4" aria-hidden="true" />
                            Queue Alert
                          </>
                        )}
                      </Button>
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
