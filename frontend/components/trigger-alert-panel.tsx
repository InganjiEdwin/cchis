"use client";

import {
  AlertTriangle,
  BellRing,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Globe,
  Megaphone,
  MessageSquareText,
  Radio,
  Search,
  ShieldAlert,
  Smartphone,
  Waves,
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
import { type LatestWardRisk, type WardSummary } from "@/lib/dashboard";
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

type TargetMode = "WARDS" | "FACILITIES" | "CHVS" | "COUNTY";
type AlertKind = "OPERATIONAL" | "ADVISORY" | "EMERGENCY";
type DeliveryPriority = "NORMAL" | "HIGH";
type DeliveryTiming = "NOW" | "SCHEDULE";
type DeliveryChannel = "SMS" | "USSD" | "APP";

type TemplateDefinition = {
  id: string;
  kind: AlertKind;
  title: string;
  body: string;
};

const STEP_LABELS = ["Select Target", "Define Alert", "Delivery", "Review"];
const ALERT_TEMPLATES: TemplateDefinition[] = [
  {
    id: "flood-hygiene",
    kind: "ADVISORY",
    title: "Flood risk detected",
    body: "Flood risk detected. Increase hygiene messaging, monitor water points, and report new diarrheal cases immediately.",
  },
  {
    id: "ors-surge",
    kind: "OPERATIONAL",
    title: "ORS stock low",
    body: "ORS stock is low. Prepare for surge conditions, review facility readiness, and update county coordination within 30 minutes.",
  },
  {
    id: "outbreak-protocol",
    kind: "EMERGENCY",
    title: "Suspected outbreak",
    body: "Suspected outbreak signal detected. Initiate protocol, confirm field reports, and escalate urgent cases to the county command center.",
  },
];

const TARGET_OPTIONS: Array<{
  value: TargetMode;
  label: string;
  description: string;
}> = [
  { value: "WARDS", label: "Wards", description: "Notify ward-level operational recipients." },
  { value: "FACILITIES", label: "Facilities", description: "Send to selected health facilities only." },
  { value: "CHVS", label: "CHVs", description: "Target field workers by ward or cluster." },
  { value: "COUNTY", label: "Entire county", description: "Restricted broadcast for county-wide action." },
];

function formatWardOptionLabel(ward: TriggerableWard) {
  const riskLabel = ward.latestRisk?.risk_level ?? "UNKNOWN";
  return `${ward.name} (${ward.county})`;
}

function estimateRecipients(targetMode: TargetMode, selectedWards: TriggerableWard[]) {
  if (targetMode === "COUNTY") {
    return {
      summary: "County-wide broadcast",
      recipientCount: 148,
      detail: "148 recipients across facilities, CHVs, and county channels",
    };
  }

  const wardCount = selectedWards.length;
  const facilityCount = wardCount * 2;
  const chvCount = wardCount * 12;

  if (targetMode === "FACILITIES") {
    return {
      summary: `${facilityCount} facilities across ${wardCount} wards`,
      recipientCount: facilityCount,
      detail: `${facilityCount} facilities selected`,
    };
  }

  if (targetMode === "CHVS") {
    return {
      summary: `${chvCount} CHVs across ${wardCount} wards`,
      recipientCount: chvCount,
      detail: `${chvCount} CHVs selected`,
    };
  }

  return {
    summary: `${chvCount} CHVs, ${facilityCount} facilities`,
    recipientCount: chvCount + facilityCount,
    detail: `${wardCount} ward-level recipient clusters`,
  };
}

export function TriggerAlertPanel({
  buttonLabel = "Trigger Alert",
  closeLabel = "Close Alert Builder",
  buttonClassName,
  fixedWard = null,
}: TriggerAlertPanelProps) {
  const { currentUser } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [wards, setWards] = useState<TriggerableWard[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedTargetMode, setSelectedTargetMode] = useState<TargetMode>(fixedWard ? "FACILITIES" : "WARDS");
  const [selectedWardIds, setSelectedWardIds] = useState<number[]>(fixedWard ? [fixedWard.id] : []);
  const [alertKind, setAlertKind] = useState<AlertKind>("OPERATIONAL");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("ors-surge");
  const [message, setMessage] = useState<string>("");
  const [language, setLanguage] = useState<"EN" | "SW">("EN");
  const [channels, setChannels] = useState<DeliveryChannel[]>(["SMS", "APP"]);
  const [priority, setPriority] = useState<DeliveryPriority>("HIGH");
  const [deliveryTiming, setDeliveryTiming] = useState<DeliveryTiming>("NOW");
  const [internalNote, setInternalNote] = useState("");
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const wardsQuery = useWardsQuery({
    enabled: Boolean(isOpen && currentUser && !fixedWard),
  });
  const isLoading = !fixedWard && wardsQuery.isPending;

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    const template = ALERT_TEMPLATES.find((item) => item.id === selectedTemplateId);
    if (template) {
      setAlertKind(template.kind);
      setMessage(template.body);
    }
  }, [selectedTemplateId]);

  useEffect(() => {
    const matchingTemplate = ALERT_TEMPLATES.find((item) => item.kind === alertKind);
    if (matchingTemplate && matchingTemplate.id !== selectedTemplateId) {
      setSelectedTemplateId(matchingTemplate.id);
    }
  }, [alertKind, selectedTemplateId]);

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
      setSelectedWardIds([fixedWard.id]);
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

    setLoadError(null);

    const latestRiskByWardId = new Map<number, LatestWardRisk>(
      wardsQuery.data.latestRisks.map((risk) => [risk.ward_id, risk]),
    );

    const mappedWards = wardsQuery.data.wards.results.map<TriggerableWard>((ward: WardSummary) => ({
      id: ward.id,
      name: ward.name,
      county: ward.county,
      subCounty: ward.sub_county,
      latestRisk: latestRiskByWardId.get(ward.id) ?? null,
    }));

    setWards(mappedWards);
    if (selectedWardIds.length === 0) {
      const preferredWardId = currentUser.scope_ward_id ?? currentUser.ward ?? mappedWards[0]?.id;
      if (preferredWardId) {
        setSelectedWardIds([preferredWardId]);
      }
    }
  }, [currentUser, fixedWard, isOpen, selectedWardIds.length, wardsQuery.data, wardsQuery.error]);

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

  const selectedWards = useMemo(
    () => wards.filter((ward) => selectedWardIds.includes(ward.id)),
    [selectedWardIds, wards],
  );

  const recipientSummary = estimateRecipients(selectedTargetMode, selectedWards);
  const isCountyRestricted = selectedTargetMode === "COUNTY" && currentUser?.role !== "ADMIN";
  const canContinueTargetStep = selectedTargetMode === "COUNTY" ? !isCountyRestricted : selectedWardIds.length > 0;
  const canContinueDefinitionStep = message.trim().length > 0;
  const canContinueDeliveryStep = channels.length > 0;

  const stepIntro = [
    "Choose where this alert should go before you define the message.",
    "Pick the type, template, and message structure with minimal free typing.",
    "Confirm channels, delivery priority, and timing before review.",
    "Review the full alert carefully before sending anything to the field.",
  ][step];

  function resetPanel() {
    setStep(0);
    setSearch("");
    setSelectedTargetMode(fixedWard ? "FACILITIES" : "WARDS");
    setSelectedWardIds(fixedWard ? [fixedWard.id] : []);
    setSelectedTemplateId("ors-surge");
    setAlertKind("OPERATIONAL");
    setChannels(["SMS", "APP"]);
    setPriority("HIGH");
    setDeliveryTiming("NOW");
    setInternalNote("");
    setIsSubmitted(false);
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

  function handleWardToggle(wardId: number) {
    setSelectedWardIds((currentValue) => {
      if (currentValue.includes(wardId)) {
        return currentValue.filter((id) => id !== wardId);
      }
      return [...currentValue, wardId];
    });
  }

  function handleChannelToggle(channel: DeliveryChannel) {
    setChannels((currentValue) => {
      if (currentValue.includes(channel)) {
        return currentValue.filter((item) => item !== channel);
      }
      return [...currentValue, channel];
    });
  }

  function handleContinue() {
    if (step === 0 && !canContinueTargetStep) return;
    if (step === 1 && !canContinueDefinitionStep) return;
    if (step === 2 && !canContinueDeliveryStep) return;
    setStep((currentValue) => Math.min(currentValue + 1, 3));
  }

  function handleSendAlert() {
    setIsSubmitted(true);
  }

  const targetSummary =
    selectedTargetMode === "COUNTY"
      ? "Entire county"
      : selectedWards.length > 0
        ? selectedWards.map((ward) => ward.name).join(", ")
        : "No target selected";

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
            className="fixed inset-y-4 right-4 z-50 flex w-[min(44rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-[2rem] border-panel-border p-0 max-[960px]:inset-0 max-[960px]:w-full max-[960px]:rounded-none"
          >
            {isSubmitted ? (
              <div className="flex h-full flex-col">
                <div className="flex items-center justify-between border-b border-panel-table-wrap px-6 py-5">
                  <div>
                    <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                      Alert Sent
                    </p>
                    <h3 className="mt-1 text-[1.65rem] font-semibold tracking-[-0.04em] text-panel-strong">
                      Alert sent successfully
                    </h3>
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

                <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
                  <div className="rounded-[1.5rem] border border-[color-mix(in_srgb,var(--success)_24%,white)] bg-[color-mix(in_srgb,var(--success)_10%,white)] px-5 py-5 dark:border-[color-mix(in_srgb,var(--success)_30%,transparent)] dark:bg-[color-mix(in_srgb,var(--success)_16%,transparent)]">
                    <div className="flex items-start gap-3">
                      <span className="inline-flex size-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--success)_16%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_22%,transparent)]">
                        <CheckCircle2 className="size-5" aria-hidden="true" />
                      </span>
                      <div>
                        <strong className="block text-lg font-semibold text-panel-strong">Delivery started</strong>
                        <p className="mt-1 text-sm text-panel-copy">
                          Dispatching {alertKind.toLowerCase()} alert to {recipientSummary.summary.toLowerCase()} via{" "}
                          {channels.join(", ")}.
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                        Alert ID
                      </p>
                      <p className="mt-2 text-xl font-semibold tracking-[-0.04em] text-panel-strong">ALT-0042</p>
                    </Card>
                    <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                        Current status
                      </p>
                      <p className="mt-2 text-xl font-semibold tracking-[-0.04em] text-panel-strong">Preparing</p>
                    </Card>
                    <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)] px-4 py-4 shadow-none">
                      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                        Estimated reach
                      </p>
                      <p className="mt-2 text-xl font-semibold tracking-[-0.04em] text-panel-strong">
                        {recipientSummary.recipientCount}
                      </p>
                    </Card>
                  </div>

                  <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                    <div className="flex items-center justify-between gap-3">
                      <h4 className="text-lg font-semibold text-panel-strong">Dispatch Timeline</h4>
                      <StatusBadge tone="info" className="px-3 py-1 tracking-[0.14em]">
                        In progress
                      </StatusBadge>
                    </div>

                    <div className="mt-5 space-y-4">
                      {[
                        { title: "Requested", detail: "Alert configured by system admin", tone: "success" as const },
                        { title: "Approved", detail: "Safety checks completed for selected scope", tone: "success" as const },
                        { title: "Preparing delivery", detail: "Outbound channel dispatch is being prepared", tone: "warning" as const },
                        { title: "In transit", detail: "Awaiting provider acknowledgements", tone: "default" as const },
                      ].map((item) => (
                        <div key={item.title} className="flex gap-3">
                          <span
                            className={cn(
                              "mt-1 inline-flex size-3 shrink-0 rounded-full",
                              item.tone === "success" && "bg-[color:var(--success)]",
                              item.tone === "warning" && "bg-[color:var(--warning)]",
                              item.tone === "default" && "bg-[var(--dashboard-subtle-copy)]",
                            )}
                          />
                          <div>
                            <strong className="block text-sm font-semibold text-panel-strong">{item.title}</strong>
                            <p className="mt-1 text-sm text-panel-muted">{item.detail}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-panel-table-wrap px-6 py-5">
                  <div className="flex flex-wrap gap-3">
                    <Button variant="secondary">
                      <BellRing className="size-4" aria-hidden="true" />
                      Notify Facility
                    </Button>
                    <Link
                      href="/alerts"
                      className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                    >
                      View Alert Timeline
                    </Link>
                  </div>
                  <Button
                    onClick={() => {
                      resetPanel();
                    }}
                  >
                    Send Another
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex h-full flex-col">
                <div className="border-b border-panel-table-wrap px-6 py-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                        Trigger Alert
                      </p>
                      <h3 className="mt-1 text-[1.65rem] font-semibold tracking-[-0.04em] text-panel-strong">
                        Structured alert workflow
                      </h3>
                      <p className="mt-2 max-w-2xl text-sm text-panel-muted">{stepIntro}</p>
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

                  <div className="mt-5 grid gap-3 md:grid-cols-4">
                    {STEP_LABELS.map((label, index) => (
                      <div
                        key={label}
                        className={cn(
                          "rounded-[1.2rem] border px-4 py-3",
                          index === step
                            ? "border-brand bg-[color-mix(in_srgb,var(--brand)_8%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                            : index < step
                              ? "border-[color-mix(in_srgb,var(--success)_22%,white)] bg-[color-mix(in_srgb,var(--success)_8%,white)] dark:bg-[color-mix(in_srgb,var(--success)_12%,transparent)]"
                              : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_22%,transparent)]",
                        )}
                      >
                        <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                          Step {index + 1}
                        </p>
                        <p className="mt-1 text-sm font-semibold text-panel-strong">{label}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[minmax(0,1fr)_18rem]">
                  <div className="min-h-0 overflow-y-auto px-6 py-6">
                    {loadError ? (
                      <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
                        {loadError}
                      </StatusBanner>
                    ) : null}

                    {step === 0 ? (
                      <div className="space-y-6">
                        <div className="grid gap-3 md:grid-cols-2">
                          {TARGET_OPTIONS.map((option) => (
                            <button
                              key={option.value}
                              type="button"
                              className={cn(
                                "rounded-[1.45rem] border px-4 py-4 text-left transition",
                                selectedTargetMode === option.value
                                  ? "border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_16%,transparent)]"
                                  : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] hover:border-[var(--dashboard-icon-button-border)]",
                                option.value === "COUNTY" &&
                                  currentUser?.role !== "ADMIN" &&
                                  "cursor-not-allowed opacity-60",
                              )}
                              onClick={() => {
                                setSelectedTargetMode(option.value);
                              }}
                            >
                              <div className="flex items-center justify-between gap-3">
                                <strong className="text-base font-semibold text-panel-strong">{option.label}</strong>
                                {selectedTargetMode === option.value ? (
                                  <StatusBadge tone="info" className="px-3 py-1 tracking-[0.14em]">
                                    Selected
                                  </StatusBadge>
                                ) : null}
                              </div>
                              <p className="mt-2 text-sm text-panel-muted">{option.description}</p>
                            </button>
                          ))}
                        </div>

                        {selectedTargetMode !== "COUNTY" ? (
                          <>
                            <InputShell
                              icon={<Search className="size-4" aria-hidden="true" />}
                              value={search}
                              onChange={(event) => setSearch(event.target.value)}
                              placeholder="Search ward, county, or sub-county..."
                            />

                            <div className="rounded-[1.5rem] border border-panel-table-wrap">
                              <div className="max-h-[18rem] overflow-y-auto p-3">
                                <div className="grid gap-3">
                                  {visibleWards.map((ward) => {
                                    const isSelected = selectedWardIds.includes(ward.id);
                                    return (
                                      <button
                                        key={ward.id}
                                        type="button"
                                        className={cn(
                                          "rounded-[1.2rem] border px-4 py-4 text-left transition",
                                          isSelected
                                            ? "border-brand bg-[color-mix(in_srgb,var(--brand)_8%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                                            : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] hover:border-[var(--dashboard-icon-button-border)]",
                                        )}
                                        onClick={() => handleWardToggle(ward.id)}
                                      >
                                        <div className="flex items-start justify-between gap-3">
                                          <div>
                                            <strong className="block text-sm font-semibold text-panel-strong">
                                              {formatWardOptionLabel(ward)}
                                            </strong>
                                            <p className="mt-1 text-xs text-panel-muted">
                                              {ward.subCounty || "Sub-county not recorded"}
                                            </p>
                                          </div>
                                          <StatusBadge
                                            tone={
                                              ward.latestRisk?.risk_level === "HIGH"
                                                ? "danger"
                                                : ward.latestRisk?.risk_level === "MEDIUM"
                                                  ? "warning"
                                                  : "success"
                                            }
                                            className="px-3 py-1 tracking-[0.14em]"
                                          >
                                            {ward.latestRisk?.risk_level ?? "Unknown"}
                                          </StatusBadge>
                                        </div>
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>
                            </div>
                          </>
                        ) : (
                          <StatusBanner tone={isCountyRestricted ? "warning" : "info"} icon={<ShieldAlert aria-hidden="true" />}>
                            {isCountyRestricted
                              ? "Entire county targeting is restricted to admin users."
                              : "County-wide broadcast will notify every active facility, CHV cluster, and county recipient group."}
                          </StatusBanner>
                        )}
                      </div>
                    ) : null}

                    {step === 1 ? (
                      <div className="space-y-6">
                        <div className="grid gap-3 md:grid-cols-3">
                          {[
                            { value: "OPERATIONAL", label: "Operational Alert", icon: ShieldAlert },
                            { value: "ADVISORY", label: "Health Advisory", icon: MessageSquareText },
                            { value: "EMERGENCY", label: "Emergency Broadcast", icon: Megaphone },
                          ].map((option) => {
                            const Icon = option.icon;
                            return (
                              <button
                                key={option.value}
                                type="button"
                                className={cn(
                                  "rounded-[1.35rem] border px-4 py-4 text-left transition",
                                  alertKind === option.value
                                    ? "border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                                    : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)]",
                                )}
                                onClick={() => setAlertKind(option.value as AlertKind)}
                              >
                                <Icon className="size-5 text-brand" aria-hidden="true" />
                                <strong className="mt-3 block text-sm font-semibold text-panel-strong">{option.label}</strong>
                              </button>
                            );
                          })}
                        </div>

                        <div className="grid gap-3">
                          {ALERT_TEMPLATES.filter((template) => template.kind === alertKind).map((template) => (
                            <button
                              key={template.id}
                              type="button"
                              className={cn(
                                "rounded-[1.35rem] border px-4 py-4 text-left transition",
                                selectedTemplateId === template.id
                                  ? "border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                                  : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)]",
                              )}
                              onClick={() => setSelectedTemplateId(template.id)}
                            >
                              <strong className="block text-sm font-semibold text-panel-strong">{template.title}</strong>
                              <p className="mt-2 text-sm leading-6 text-panel-muted">{template.body}</p>
                            </button>
                          ))}
                        </div>

                        <div className="grid gap-3">
                          <label className="text-sm font-medium text-panel-copy">Message</label>
                          <textarea
                            value={message}
                            onChange={(event) => setMessage(event.target.value)}
                            rows={6}
                            className="min-h-[9rem] rounded-[1.35rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-4 text-sm leading-6 text-panel-strong outline-none transition focus:border-[var(--dashboard-icon-button-border)]"
                          />
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <label className="flex items-center gap-3 rounded-pill border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-2 text-sm text-panel-copy">
                              <Globe className="size-4" aria-hidden="true" />
                              <select
                                value={language}
                                onChange={(event) => setLanguage(event.target.value as "EN" | "SW")}
                                className="bg-transparent text-sm font-medium text-panel-strong outline-none"
                              >
                                <option value="EN">English</option>
                                <option value="SW">Swahili</option>
                              </select>
                            </label>
                            <span className="text-sm text-panel-muted">{message.length} characters</span>
                          </div>
                        </div>
                      </div>
                    ) : null}

                    {step === 2 ? (
                      <div className="space-y-6">
                        <div className="grid gap-3 md:grid-cols-3">
                          {[
                            { value: "SMS", label: "SMS", reach: `${Math.max(12, recipientSummary.recipientCount - 3)} recipients`, icon: Smartphone },
                            { value: "USSD", label: "USSD", reach: `${Math.max(8, recipientSummary.recipientCount - 8)} recipients`, icon: Radio },
                            { value: "APP", label: "App notification", reach: `${recipientSummary.recipientCount} recipients`, icon: BellRing },
                          ].map((channel) => {
                            const Icon = channel.icon;
                            const isSelected = channels.includes(channel.value as DeliveryChannel);
                            return (
                              <button
                                key={channel.value}
                                type="button"
                                className={cn(
                                  "rounded-[1.35rem] border px-4 py-4 text-left transition",
                                  isSelected
                                    ? "border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                                    : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)]",
                                )}
                                onClick={() => handleChannelToggle(channel.value as DeliveryChannel)}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <Icon className="size-5 text-brand" aria-hidden="true" />
                                  {isSelected ? (
                                    <StatusBadge tone="info" className="px-3 py-1 tracking-[0.14em]">
                                      Selected
                                    </StatusBadge>
                                  ) : null}
                                </div>
                                <strong className="mt-3 block text-sm font-semibold text-panel-strong">{channel.label}</strong>
                                <p className="mt-2 text-sm text-panel-muted">Estimated reach: {channel.reach}</p>
                              </button>
                            );
                          })}
                        </div>

                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="rounded-[1.35rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4">
                            <p className="text-sm font-medium text-panel-copy">Delivery priority</p>
                            <div className="mt-3 flex gap-2">
                              {(["NORMAL", "HIGH"] as const).map((option) => (
                                <button
                                  key={option}
                                  type="button"
                                  className={cn(
                                    "inline-flex h-10 items-center justify-center rounded-pill border px-4 text-sm font-semibold transition",
                                    priority === option
                                      ? "border-brand bg-brand text-white"
                                      : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy",
                                  )}
                                  onClick={() => setPriority(option)}
                                >
                                  {option === "NORMAL" ? "Normal" : "High"}
                                </button>
                              ))}
                            </div>
                          </div>

                          <div className="rounded-[1.35rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4">
                            <p className="text-sm font-medium text-panel-copy">Delivery timing</p>
                            <div className="mt-3 flex gap-2">
                              {([
                                { value: "NOW", label: "Send now" },
                                { value: "SCHEDULE", label: "Schedule" },
                              ] as const).map((option) => (
                                <button
                                  key={option.value}
                                  type="button"
                                  className={cn(
                                    "inline-flex h-10 items-center justify-center rounded-pill border px-4 text-sm font-semibold transition",
                                    deliveryTiming === option.value
                                      ? "border-brand bg-brand text-white"
                                      : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy",
                                  )}
                                  onClick={() => setDeliveryTiming(option.value)}
                                >
                                  {option.label}
                                </button>
                              ))}
                            </div>
                            {deliveryTiming === "SCHEDULE" ? (
                              <div className="mt-3 flex items-center gap-2 text-sm text-panel-muted">
                                <CalendarClock className="size-4" aria-hidden="true" />
                                Scheduling UI will be wired with backend delivery windows later.
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ) : null}

                    {step === 3 ? (
                      <div className="space-y-6">
                        <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                          <div className="grid gap-5 md:grid-cols-2">
                            <div className="space-y-3">
                              <div>
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                                  Target
                                </p>
                                <p className="mt-1 text-base font-semibold text-panel-strong">{recipientSummary.summary}</p>
                                <p className="mt-1 text-sm text-panel-muted">{targetSummary}</p>
                              </div>
                              <div>
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                                  Alert type
                                </p>
                                <p className="mt-1 text-base font-semibold text-panel-strong">
                                  {alertKind === "OPERATIONAL"
                                    ? "Operational Alert"
                                    : alertKind === "ADVISORY"
                                      ? "Health Advisory"
                                      : "Emergency Broadcast"}
                                </p>
                              </div>
                              <div>
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                                  Channels
                                </p>
                                <p className="mt-1 text-base font-semibold text-panel-strong">{channels.join(", ")}</p>
                              </div>
                            </div>

                            <div className="space-y-3">
                              <div>
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                                  Estimated delivery time
                                </p>
                                <p className="mt-1 text-base font-semibold text-panel-strong">
                                  {deliveryTiming === "NOW" ? "< 2 minutes" : "Scheduled"}
                                </p>
                              </div>
                              <div>
                                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                                  Priority
                                </p>
                                <p className="mt-1 text-base font-semibold text-panel-strong">
                                  {priority === "HIGH" ? "High" : "Normal"}
                                </p>
                              </div>
                            </div>
                          </div>

                          <div className="mt-5 rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4">
                            <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                              Message preview
                            </p>
                            <p className="mt-3 text-sm leading-6 text-panel-copy">{message}</p>
                          </div>

                          {(alertKind === "EMERGENCY" || selectedTargetMode === "COUNTY") ? (
                            <div className="mt-5 rounded-[1.25rem] border border-[color-mix(in_srgb,var(--danger)_22%,white)] bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-4 py-4 dark:border-[color-mix(in_srgb,var(--danger)_28%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_14%,transparent)]">
                              <div className="flex items-start gap-3">
                                <AlertTriangle className="mt-0.5 size-4 text-[color:var(--danger)]" aria-hidden="true" />
                                <div>
                                  <strong className="block text-sm font-semibold text-panel-strong">
                                    Large or high-risk broadcast
                                  </strong>
                                  <p className="mt-1 text-sm text-panel-copy">
                                    This action affects a large audience. Review recipients and message tone carefully before sending.
                                  </p>
                                </div>
                              </div>
                            </div>
                          ) : null}

                          <div className="mt-5">
                            <label className="text-sm font-medium text-panel-copy">Internal note</label>
                            <textarea
                              value={internalNote}
                              onChange={(event) => setInternalNote(event.target.value)}
                              rows={3}
                              placeholder="Optional note for the audit trail..."
                              className="mt-2 min-h-[7rem] w-full rounded-[1.2rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-strong outline-none transition focus:border-[var(--dashboard-icon-button-border)]"
                            />
                          </div>
                        </Card>
                      </div>
                    ) : null}
                  </div>

                  <aside className="border-l border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] px-5 py-6 max-lg:border-l-0 max-lg:border-t">
                    <div className="space-y-4">
                      <h4 className="text-lg font-semibold text-panel-strong">Dispatch Brief</h4>
                      <p className="text-sm text-panel-muted">
                        Live summary of the alert as you build it.
                      </p>
                    </div>

                    <div className="mt-5 space-y-4">
                      <div className="rounded-[1.25rem] border border-panel-table-wrap bg-[var(--dashboard-panel-surface)] px-4 py-4">
                        <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Target</p>
                        <p className="mt-2 text-sm font-semibold text-panel-strong">{recipientSummary.summary}</p>
                        <p className="mt-1 text-xs text-panel-muted">{recipientSummary.detail}</p>
                      </div>
                      <div className="rounded-[1.25rem] border border-panel-table-wrap bg-[var(--dashboard-panel-surface)] px-4 py-4">
                        <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Alert</p>
                        <p className="mt-2 text-sm font-semibold text-panel-strong">
                          {alertKind === "OPERATIONAL"
                            ? "Operational Alert"
                            : alertKind === "ADVISORY"
                              ? "Health Advisory"
                              : "Emergency Broadcast"}
                        </p>
                        <p className="mt-1 text-xs text-panel-muted">{language === "EN" ? "English" : "Swahili"} message</p>
                      </div>
                      <div className="rounded-[1.25rem] border border-panel-table-wrap bg-[var(--dashboard-panel-surface)] px-4 py-4">
                        <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Channels</p>
                        <p className="mt-2 text-sm font-semibold text-panel-strong">{channels.join(", ") || "None selected"}</p>
                        <p className="mt-1 text-xs text-panel-muted">
                          {priority === "HIGH" ? "High priority" : "Normal priority"} •{" "}
                          {deliveryTiming === "NOW" ? "Send immediately" : "Schedule later"}
                        </p>
                      </div>
                    </div>
                  </aside>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-panel-table-wrap px-6 py-5">
                  <div className="flex gap-3">
                    <Button
                      variant="secondary"
                      disabled={step === 0}
                      onClick={() => setStep((currentValue) => Math.max(currentValue - 1, 0))}
                    >
                      Back
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setIsOpen(false);
                        resetPanel();
                      }}
                    >
                      Cancel
                    </Button>
                  </div>

                  {step < 3 ? (
                    <Button
                      onClick={handleContinue}
                      disabled={
                        (step === 0 && !canContinueTargetStep) ||
                        (step === 1 && !canContinueDefinitionStep) ||
                        (step === 2 && !canContinueDeliveryStep)
                      }
                    >
                      Continue
                      <ChevronRight className="size-4" aria-hidden="true" />
                    </Button>
                  ) : (
                    <Button onClick={handleSendAlert}>
                      <BellRing className="size-4" aria-hidden="true" />
                      Send Alert
                    </Button>
                  )}
                </div>
              </div>
            )}
          </Card>
            </>,
            document.body,
          )
        : null}
    </div>
  );
}
