"use client";

import {
  AlertTriangle,
  ArrowLeft,
  Bell,
  Building2,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  MapPinned,
  PackagePlus,
  ShieldAlert,
  ShieldCheck,
  Truck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { MigoriWardMap } from "@/components/migori-ward-map";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import {
  buildFacilityRows,
  findFacilityAlerts,
  riskTone,
  stockTone,
  type FacilityRow,
} from "@/lib/facility-readiness";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";
import type { AlertRecord } from "@/lib/dashboard";
import { useFacilityDetailQuery } from "@/queries/use-facility-detail-query";

type TimelineItem = {
  id: string;
  title: string;
  body: string;
  timestamp: string;
  tone: "danger" | "warning" | "info" | "success";
};

type DispatchPriority = "CRITICAL" | "HIGH" | "ROUTINE";
type SupplyKey =
  | "ors_kits"
  | "iv_fluids"
  | "water_treatment"
  | "hygiene_kits"
  | "protective_equipment"
  | "custom_package";

type DispatchSupplyItem = {
  label: string;
  unit: string;
  quantity: number;
  note: string;
};

type DispatchDraft = {
  priority: DispatchPriority;
  supplies: Record<SupplyKey, DispatchSupplyItem>;
  source: string;
  transport: string;
  eta: string;
  handler: string;
  facilityContact: string;
  facilityPhone: string;
  logisticsNotes: string;
  approvalNote: string;
  dispatchId: string;
};

type DispatchSelectField = "source" | "transport" | "handler" | "eta";

const DISPATCH_STAGES = [
  "Requested",
  "Approved",
  "Preparing supplies",
  "In transit",
  "Delivered",
  "Confirmed received",
  "Closed",
] as const;

const DISPATCH_STEP_META = [
  {
    kicker: "Step 1",
    title: "Dispatch Review",
    description: "Review the readiness signal, urgency, and why county resources are being recommended.",
  },
  {
    kicker: "Step 2",
    title: "Select Dispatch Package",
    description: "Choose the supply package, adjust quantities, and keep the preset recommendations grounded in the shortage.",
  },
  {
    kicker: "Step 3",
    title: "Logistics Confirmation",
    description: "Confirm source, route, handler, and destination before escalating into a real movement chain.",
  },
  {
    kicker: "Step 4",
    title: "Review And Approve",
    description: "Pause at the approval checkpoint and confirm the full operational picture before dispatch is created.",
  },
  {
    kicker: "Step 5",
    title: "Dispatch Created",
    description: "The dispatch now has an ID, a current stage, and a tracking path for the team to follow.",
  },
] as const;

function supplyAccentClasses(key: SupplyKey) {
  switch (key) {
    case "ors_kits":
      return "bg-[color-mix(in_srgb,var(--danger)_12%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]";
    case "iv_fluids":
      return "bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]";
    case "water_treatment":
      return "bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]";
    case "hygiene_kits":
      return "bg-[color-mix(in_srgb,var(--success)_12%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_18%,transparent)]";
    case "protective_equipment":
      return "bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_16%,transparent)]";
    case "custom_package":
    default:
      return "bg-panel text-panel-copy";
  }
}

function createDispatchDraft(row: FacilityRow): DispatchDraft {
  return {
    priority: row.surgeRisk === "EXTREME" ? "CRITICAL" : row.surgeRisk === "MODERATE" ? "HIGH" : "ROUTINE",
    supplies: {
      ors_kits: {
        label: "ORS kits",
        unit: "cartons",
        quantity: row.orsStockPercent < 30 ? 30 : 12,
        note: "Recommended from stock shortfall model",
      },
      iv_fluids: {
        label: "IV fluids",
        unit: "crates",
        quantity: row.surgeRisk === "EXTREME" ? 8 : 4,
        note: "",
      },
      water_treatment: {
        label: "Water treatment supplies",
        unit: "boxes",
        quantity: row.surgeRisk === "EXTREME" ? 10 : 4,
        note: "Pre-filled due to flood-related contamination risk",
      },
      hygiene_kits: {
        label: "Hygiene kits",
        unit: "bundles",
        quantity: row.surgeRisk === "EXTREME" ? 12 : 0,
        note: "",
      },
      protective_equipment: {
        label: "Protective equipment",
        unit: "packs",
        quantity: row.surgeRisk === "EXTREME" ? 6 : 0,
        note: "",
      },
      custom_package: {
        label: "Custom package",
        unit: "units",
        quantity: 0,
        note: "",
      },
    },
    source: "Migori County Warehouse",
    transport: row.surgeRisk === "EXTREME" ? "County vehicle" : "Motorcycle rider",
    eta: row.surgeRisk === "EXTREME" ? "2h 15m" : "4h 10m",
    handler: "John Otieno",
    facilityContact: `${row.facilityName} Nurse in Charge`,
    facilityPhone: "+254 712 000 421",
    logisticsNotes: row.surgeRisk === "EXTREME" ? "Call before delivery. Flooding reported on secondary access road." : "",
    approvalNote: "",
    dispatchId: `DSP-${row.id.padStart(4, "0")}`,
  };
}

function timelineToneClasses(tone: TimelineItem["tone"]) {
  switch (tone) {
    case "danger":
      return "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]";
    case "success":
      return "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_18%,transparent)]";
    case "warning":
      return "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]";
    case "info":
    default:
      return "bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]";
  }
}

function readinessTone(value: number) {
  if (value >= 90) return "danger";
  if (value >= 75) return "warning";
  return "info";
}

function buildTimeline(row: FacilityRow, alerts: AlertRecord[]): TimelineItem[] {
  const items: TimelineItem[] = [
    {
      id: "facility-record",
      title: "Facility Record Refreshed",
      body: `${row.facilityName} is using its current backend facility record. Readiness figures on this page still derive from facility identity plus ward risk data.`,
      timestamp: row.lastReported,
      tone: "success",
    },
  ];

  alerts.slice(0, 2).forEach((alert) => {
    items.push({
      id: `alert-${alert.id}`,
      title: `${alert.channel} alert ${alert.status.toLowerCase().replaceAll("_", " ")}`,
      body: alert.message,
      timestamp: formatRelativeTimestamp(alert.created_at),
      tone: alert.status === "FAILED" ? "danger" : alert.status === "DELIVERED" ? "success" : "warning",
    });
  });

  if (!alerts.length) {
    items.push({
      id: "alert-gap",
      title: "No ward-linked alert records",
      body: "No alert events are currently attached to this facility's ward in the backend alert log.",
      timestamp: row.lastReported,
      tone: "info",
    });
  }

  return items;
}

function priorityTone(priority: DispatchPriority) {
  switch (priority) {
    case "CRITICAL":
      return "danger" as const;
    case "HIGH":
      return "warning" as const;
    case "ROUTINE":
    default:
      return "info" as const;
  }
}

export default function FacilityDetailPage() {
  const params = useParams<{ id: string }>();
  const facilityId = Number(params.id);
  const { data, isPending: isLoading, error } = useFacilityDetailQuery(
    Number.isInteger(facilityId) && facilityId > 0 ? facilityId : null,
  );
  const facilityRecord = data?.facility ?? null;
  const risks = data?.risks ?? [];
  const alerts = data?.alerts ?? [];
  const wardMap = data?.wardMap ?? null;

  const facility = useMemo(
    () => (facilityRecord ? buildFacilityRows([facilityRecord], risks)[0] ?? null : null),
    [facilityRecord, risks],
  );

  const facilityAlerts = useMemo(() => (facility ? findFacilityAlerts(facility, alerts) : []), [alerts, facility]);
  const selectedMapWard = useMemo(
    () => wardMap?.features.find((feature) => feature.properties.name === facilityRecord?.ward_name) ?? null,
    [facilityRecord?.ward_name, wardMap],
  );
  const latestTimestamp = useMemo(
    () =>
      getLatestTimestamp([
        ...(facilityRecord ? [facilityRecord.updated_at] : []),
        ...risks.map((risk) => risk.generated_at),
        ...alerts.map((alert) => alert.created_at),
      ]),
    [alerts, facilityRecord, risks],
  );
  const freshness = useMemo(() => describeFreshness(latestTimestamp, 120), [latestTimestamp]);
  const lastUpdatedLabel = latestTimestamp ? formatRelativeTimestamp(latestTimestamp) : freshness.label;

  const timeline = useMemo(() => (facility ? buildTimeline(facility, facilityAlerts) : []), [facility, facilityAlerts]);
  const [dispatchOpen, setDispatchOpen] = useState(false);
  const [dispatchStep, setDispatchStep] = useState(0);
  const [dispatchDraft, setDispatchDraft] = useState<DispatchDraft | null>(null);

  if (!isLoading && !facility) {
    notFound();
  }

  const staffingPercent = facility ? Math.round((facility.staffingFilled / facility.staffingRequired) * 100) : 0;
  const bedOccupancy = facility ? Math.min(97, facility.projectedCases + 18) : 0;
  const dispatchReason = facility
    ? `ORS stock is at ${facility.orsStockPercent}% while projected load is rising to ~${facility.projectedCases * 5} cases/day.`
    : "";

  function openDispatchWizard() {
    if (!facility) return;
    setDispatchDraft(createDispatchDraft(facility));
    setDispatchStep(0);
    setDispatchOpen(true);
  }

  function closeDispatchWizard() {
    setDispatchOpen(false);
    setDispatchStep(0);
  }

  function updateSupply(key: SupplyKey, field: keyof DispatchSupplyItem, value: string | number) {
    setDispatchDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        supplies: {
          ...current.supplies,
          [key]: {
            ...current.supplies[key],
            [field]: value,
          },
        },
      };
    });
  }

  function updateDispatch(field: keyof DispatchDraft, value: string) {
    setDispatchDraft((current) => (current ? { ...current, [field]: value } : current));
  }

  const selectedSupplyEntries = dispatchDraft
    ? Object.entries(dispatchDraft.supplies).filter(([, item]) => item.quantity > 0) as Array<[SupplyKey, DispatchSupplyItem]>
    : [];

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Facility Detail"
        subtitle="Facility identity is backend-backed; readiness posture remains partly derived until a dedicated backend readiness contract exists."
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
      />

      <RoleGate
        allowedRoles={["ADMIN", "SUPERVISOR", "ANALYST"]}
        title="Facility detail is role-restricted"
        message="Facility detail is intended for dashboard roles coordinating preparedness and response."
      >
        {error ? (
          <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
            {error instanceof Error ? error.message : "Unable to load facility detail."}
          </StatusBanner>
        ) : null}

        {isLoading || !facility ? (
          <Card className="rounded-[2rem] p-6 text-sm text-panel-muted">Loading facility detail...</Card>
        ) : (
          <>
            <Card className="rounded-[2rem] px-6 py-6">
              <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                <div className="space-y-3">
                  <Link
                    href="/facility-readiness"
                    className="inline-flex items-center gap-2 text-sm font-medium text-panel-muted transition hover:text-panel-strong"
                  >
                    <ArrowLeft className="size-4" aria-hidden="true" />
                    Back to Facilities
                  </Link>
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={riskTone(facility.surgeRisk)} className="tracking-[0.14em]">
                        {facility.surgeRisk === "EXTREME" ? "Extreme Risk" : facility.surgeRisk === "MODERATE" ? "Moderate Risk" : "Low Risk"}
                      </StatusBadge>
                      <span className="text-sm text-panel-muted">Last reported: {facility.lastReported}</span>
                    </div>
                    <h1 className="text-[clamp(2.2rem,1.4rem+2vw,3.5rem)] font-semibold tracking-[-0.05em] text-panel-strong">
                      {facility.facilityName}
                    </h1>
                    <p className="text-sm text-panel-muted">
                      {facility.subCounty} Sub-County | {facility.facilityType} | {facility.wardName} Ward
                    </p>
                  </div>
                </div>

                <div className="rounded-[1.5rem] border border-[color:var(--danger)]/18 bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-4 py-3 text-sm font-semibold text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_16%,transparent)]">
                  {facility.surgeRisk === "EXTREME" ? "Extreme Surge Risk (Critical)" : "Facility Under Monitoring"}
                </div>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="border-l-2 border-[color:var(--danger)] px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Surge risk</span>
                  <div className="mt-3 text-3xl font-semibold text-[color:var(--danger)]">
                    {facility.surgeRisk === "EXTREME" ? "Extreme" : facility.surgeRisk === "MODERATE" ? "Moderate" : "Low"}
                  </div>
                </div>
                <div className="border-l-2 border-panel-table-wrap px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Predicted load</span>
                  <div className="mt-3 text-3xl font-semibold text-panel-strong">~{facility.projectedCases * 5} <span className="text-base font-medium text-panel-muted">cases/day</span></div>
                </div>
                <div className="border-l-2 border-[color:var(--danger)] px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">ORS stock</span>
                  <div className="mt-3 text-3xl font-semibold text-[color:var(--danger)]">
                    {facility.orsStockPercent}% <span className="text-sm font-semibold uppercase">{facility.orsState}</span>
                  </div>
                </div>
                <div className="border-l-2 border-panel-table-wrap px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Staffing</span>
                  <div className="mt-3 text-3xl font-semibold text-panel-strong">
                    {facility.staffingFilled}/{facility.staffingRequired} <span className="text-base font-medium text-panel-muted">Active</span>
                  </div>
                </div>
              </div>
            </Card>

            <section className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_22rem]">
              <div className="space-y-5">
                <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
                  <div className="flex items-center gap-2 text-sm font-semibold text-panel-strong">
                    <MapPinned className="size-4 text-brand" aria-hidden="true" />
                    Surge & Risk Context
                  </div>

                  <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
                    <div className="space-y-4">
                      <p className="text-sm leading-7 text-panel-copy">
                        This facility currently inherits a ward status of{" "}
                        <strong>{facility.surgeRisk === "EXTREME" ? "Extreme" : facility.surgeRisk === "MODERATE" ? "Moderate" : "Low"}</strong>{" "}
                        from the backend ward-risk feed for {facility.wardName}. The map below is real ward geometry, but this page does not yet have facility catchment, rainfall-series, or dispatch-log contracts.
                      </p>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">Ward risk score</div>
                          <div className="mt-2 text-sm font-semibold text-panel-strong">
                            {facilityRecord?.ward_risk_score?.toFixed(2) ?? "--"}
                          </div>
                        </div>
                        <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">Ward-linked alerts</div>
                          <div className="mt-2 text-sm font-semibold text-panel-strong">
                            {facilityAlerts.length}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="overflow-hidden rounded-[1.5rem] border border-panel-table-wrap bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_10%,transparent),transparent_35%),radial-gradient(circle_at_bottom_right,color-mix(in_srgb,var(--warning)_10%,transparent),transparent_32%),linear-gradient(135deg,color-mix(in_srgb,var(--panel)_92%,white),var(--panel))] p-4">
                      <div className="flex h-full min-h-[14rem] flex-col gap-3 rounded-[1.1rem] border border-panel-table-wrap bg-panel/80 p-4">
                        <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-panel-subtle">
                          <span>Ward context map</span>
                          <span>{selectedMapWard ? "Backend geometry" : "No ward geometry"}</span>
                        </div>
                        <div className="min-h-[13rem] rounded-[1rem] border border-panel-table-wrap bg-white/60 p-2 dark:bg-panel/70">
                          {wardMap?.features.length ? (
                            <MigoriWardMap
                              features={wardMap.features}
                              selectedWardName={facility.wardName}
                              onSelectWard={() => undefined}
                            />
                          ) : (
                            <div className="flex h-full items-center justify-center text-center text-sm text-panel-muted">
                              Ward geometry is not available for this facility scope yet.
                            </div>
                          )}
                        </div>
                        <div className="inline-flex w-max items-center gap-2 rounded-full bg-[color-mix(in_srgb,var(--brand)_10%,white)] px-3 py-1.5 text-xs font-semibold text-panel-strong">
                          <span className="size-2 rounded-full bg-brand" />
                          {facility.wardName} ward context
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>

                <div className="space-y-3">
                  <h2 className="text-2xl font-semibold text-panel-strong">Resource Availability</h2>
                  <div className="grid gap-4 md:grid-cols-3">
                    <Card className="rounded-[1.6rem] bg-panel px-5 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--danger)_12%,white)] text-[color:var(--danger)]">
                          <PackagePlus className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-[color:var(--danger)]">Declining</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">ORS Stocks</div>
                      <div className="mt-2 text-4xl font-semibold text-panel-strong">{facility.orsStockPercent}%</div>
                      <div className="mt-1 text-sm text-panel-muted">Current</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--danger)_12%,white)]">
                        <div className="h-full rounded-full bg-[color:var(--danger)]" style={{ width: `${facility.orsStockPercent}%` }} />
                      </div>
                    </Card>

                    <Card className="rounded-[1.6rem] bg-panel px-5 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand">
                          <Users className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-brand">Stable</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Staffing</div>
                      <div className="mt-2 text-4xl font-semibold text-panel-strong">{staffingPercent}%</div>
                      <div className="mt-1 text-sm text-panel-muted">Capacity</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)]">
                        <div className="h-full rounded-full bg-brand" style={{ width: `${staffingPercent}%` }} />
                      </div>
                    </Card>

                    <Card className="rounded-[1.6rem] bg-panel px-5 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)]">
                          <Building2 className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-[color:var(--warning)]">Near limit</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Bed Occupancy</div>
                      <div className="mt-2 text-4xl font-semibold text-panel-strong">{bedOccupancy}%</div>
                      <div className="mt-1 text-sm text-panel-muted">Full</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--warning)_12%,white)]">
                        <div className="h-full rounded-full bg-[color:var(--warning)]" style={{ width: `${bedOccupancy}%` }} />
                      </div>
                    </Card>
                  </div>
                </div>

                <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
                  <h2 className="text-2xl font-semibold text-panel-strong">Facility Activity Summary</h2>
                  <div className="mt-5 space-y-4">
                    {timeline.map((item) => (
                      <div key={item.id} className="flex gap-4">
                        <div className={cn("mt-1 inline-flex size-9 shrink-0 items-center justify-center rounded-full", timelineToneClasses(item.tone))}>
                          {item.tone === "danger" ? <AlertTriangle className="size-4" aria-hidden="true" /> : item.tone === "warning" ? <Bell className="size-4" aria-hidden="true" /> : <Truck className="size-4" aria-hidden="true" />}
                        </div>
                        <div className="min-w-0 flex-1 rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <strong className="text-panel-strong">{item.title}</strong>
                            <span className="text-panel-muted">{item.timestamp}</span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-panel-copy">{item.body}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
                  <h2 className="text-2xl font-semibold text-panel-strong">Dispatch History</h2>
                  <div className="mt-5 rounded-[1.5rem] border border-dashed border-panel-table-wrap px-5 py-5 text-sm text-panel-copy">
                    No backend dispatch-log contract exists yet for facilities, so historical shipment rows are intentionally hidden here instead of being simulated.
                  </div>
                </Card>
              </div>

              <div className="space-y-5">
                <Card className="rounded-[2rem] px-5 py-5">
                  <div className="flex items-center gap-2 text-sm font-semibold text-panel-strong">
                    <ShieldAlert className="size-4 text-brand" aria-hidden="true" />
                    Recommended Actions
                  </div>
                  <p className="mt-4 rounded-[1.25rem] border border-[color:var(--danger)]/16 bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-4 py-3 text-sm leading-6 text-panel-copy dark:bg-[color-mix(in_srgb,var(--danger)_14%,transparent)]">
                    Derived context: ORS, staffing, and demand posture on this page are still calculated from facility identity plus ward risk data. Actual dispatch workflows remain pending backend implementation.
                  </p>
                  <div className="mt-5 space-y-3">
                    <Button className="w-full justify-center" disabled>
                      <Truck className="size-4" aria-hidden="true" />
                      Dispatch Workflow Pending
                    </Button>
                    <Button variant="secondary" className="w-full justify-between">
                      Open Facility Chat
                      <span className="text-panel-muted">+</span>
                    </Button>
                    <Button variant="secondary" className="w-full justify-between">
                      Notify CHVs
                      <span className="text-panel-muted">+</span>
                    </Button>
                    <Button variant="danger" className="w-full justify-between">
                      Escalate to County
                      <span>!</span>
                    </Button>
                  </div>
                </Card>

                <Card className="rounded-[2rem] px-5 py-5">
                  <div className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                    Operational contacts
                  </div>
                  <div className="mt-4 space-y-4">
                    {[
                      ["Dr. Silas Okoth", "County Health Superintendent"],
                      ["Mercy Wanjiku", "Sub-County Logistics Lead"],
                    ].map(([name, role]) => (
                      <div key={name} className="flex items-start gap-3 rounded-[1.25rem] border border-panel-table-wrap px-4 py-3">
                        <span className="inline-flex size-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand">
                          <Users className="size-4" aria-hidden="true" />
                        </span>
                        <div>
                          <strong className="block text-sm text-panel-strong">{name}</strong>
                          <span className="block text-sm text-panel-muted">{role}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            </section>

            {dispatchOpen && dispatchDraft ? (
              <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/35 p-4 backdrop-blur-sm sm:p-6">
                <div className="flex h-[min(100%,56rem)] w-full max-w-[58rem] flex-col overflow-hidden rounded-[2rem] border border-panel-table-wrap bg-panel shadow-2xl ring-1 ring-white/5">
                  <div className="border-b border-panel-table-wrap bg-[linear-gradient(180deg,color-mix(in_srgb,var(--brand)_6%,transparent),transparent)] px-6 py-5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                          Dispatch Workflow
                        </div>
                        <h2 className="mt-2 text-2xl font-semibold text-panel-strong">Dispatch to {facility.facilityName}</h2>
                        <p className="mt-2 text-sm text-panel-muted">
                          Controlled, auditable supply dispatch based on live facility readiness signals.
                        </p>
                      </div>
                      <Button variant="ghost" size="sm" onClick={closeDispatchWizard}>
                        Close
                      </Button>
                    </div>

                    <div className="mt-5 grid grid-cols-5 gap-2">
                      {DISPATCH_STEP_META.map((step, index) => (
                        <div
                          key={step.title}
                          className={cn(
                            "rounded-[1rem] border px-3 py-2",
                            index === dispatchStep
                              ? "border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_16%,transparent)]"
                              : index < dispatchStep
                                ? "border-[color:var(--success)]/25 bg-[color-mix(in_srgb,var(--success)_8%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_14%,transparent)]"
                                : "border-panel-table-wrap bg-panel text-panel-subtle",
                          )}
                        >
                          <div className="text-[0.65rem] font-semibold uppercase tracking-[0.14em]">{step.kicker}</div>
                          <div className="mt-1 text-xs font-semibold">{step.title}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
                    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]">
                      <div className="space-y-6">
                        <div className="rounded-[1.4rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_28%,transparent)] px-5 py-4">
                          <div className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                            {DISPATCH_STEP_META[dispatchStep].kicker}
                          </div>
                          <div className="mt-2 text-xl font-semibold text-panel-strong">{DISPATCH_STEP_META[dispatchStep].title}</div>
                          <p className="mt-2 text-sm leading-6 text-panel-copy">{DISPATCH_STEP_META[dispatchStep].description}</p>
                        </div>

                    {dispatchStep === 0 ? (
                      <div className="space-y-6">
                        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                          {[
                            ["Surge risk", facility.surgeRisk === "EXTREME" ? "Extreme" : facility.surgeRisk === "MODERATE" ? "Moderate" : "Low"],
                            ["Predicted case load", `~${facility.projectedCases * 5}/day`],
                            ["ORS stock", `${facility.orsStockPercent}% ${facility.orsState}`],
                            ["Staffing", `${facility.staffingFilled}/${facility.staffingRequired} active`],
                            ["Last updated", facility.lastReported],
                          ].map(([label, value]) => (
                            <div key={label} className="rounded-[1.25rem] border border-panel-table-wrap bg-panel px-4 py-4">
                              <div className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle">{label}</div>
                              <div className="mt-2 text-base font-semibold text-panel-strong">{value}</div>
                            </div>
                          ))}
                        </div>

                        <Card className="rounded-[1.5rem] border-[color:var(--danger)]/18 bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-5 py-5 shadow-none dark:bg-[color-mix(in_srgb,var(--danger)_14%,transparent)]">
                          <div className="flex items-center gap-2 text-sm font-semibold text-panel-strong">
                            <ShieldAlert className="size-4 text-[color:var(--danger)]" aria-hidden="true" />
                            Recommended action: Immediate ORS dispatch
                          </div>
                          <p className="mt-2 text-sm leading-6 text-panel-copy">
                            Reason: Stock below threshold during projected surge window. Current ORS coverage is at {facility.orsStockPercent}% while projected pediatric load is trending upward.
                          </p>
                        </Card>

                        <div className="space-y-3">
                          <div className="text-sm font-semibold text-panel-strong">Dispatch urgency</div>
                          <div className="grid gap-3 md:grid-cols-3">
                            {(["CRITICAL", "HIGH", "ROUTINE"] as DispatchPriority[]).map((priority) => (
                              <button
                                key={priority}
                                type="button"
                                onClick={() => updateDispatch("priority", priority)}
                                className={cn(
                                  "rounded-[1.25rem] border px-4 py-4 text-left transition duration-200",
                                  dispatchDraft.priority === priority
                                    ? "border-brand bg-[color-mix(in_srgb,var(--brand)_8%,white)] dark:bg-[color-mix(in_srgb,var(--brand)_14%,transparent)]"
                                    : "border-panel-table-wrap bg-panel hover:border-[var(--dashboard-icon-button-border)]",
                                )}
                              >
                                <StatusBadge tone={priorityTone(priority)}>{priority}</StatusBadge>
                                <div className="mt-3 text-sm text-panel-copy">
                                  {priority === "CRITICAL"
                                    ? "Immediate dispatch with active county oversight."
                                    : priority === "HIGH"
                                      ? "Fast-tracked dispatch within the current shift."
                                      : "Routine resupply under monitored conditions."}
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : null}

                    {dispatchStep === 1 ? (
                      <div className="space-y-4">
                          <div className="text-sm font-semibold text-panel-strong">Select supplies</div>
                          <div className="grid gap-4 md:grid-cols-2">
                            {(Object.entries(dispatchDraft.supplies) as Array<[SupplyKey, DispatchSupplyItem]>).map(([key, item]) => (
                              <div
                                key={key}
                                className={cn(
                                  "rounded-[1.35rem] border px-4 py-4 transition duration-200",
                                  item.quantity > 0
                                    ? "border-brand/35 bg-[color-mix(in_srgb,var(--brand)_5%,transparent)]"
                                    : "border-panel-table-wrap bg-panel",
                                )}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div className="flex items-start gap-3">
                                    <span className={cn("inline-flex size-10 shrink-0 items-center justify-center rounded-2xl", supplyAccentClasses(key))}>
                                      {key === "ors_kits" ? <PackagePlus className="size-4" aria-hidden="true" /> : key === "iv_fluids" ? <Truck className="size-4" aria-hidden="true" /> : key === "water_treatment" ? <Bell className="size-4" aria-hidden="true" /> : key === "hygiene_kits" ? <ShieldCheck className="size-4" aria-hidden="true" /> : key === "protective_equipment" ? <Users className="size-4" aria-hidden="true" /> : <ClipboardCheck className="size-4" aria-hidden="true" />}
                                    </span>
                                    <div>
                                    <div className="text-sm font-semibold text-panel-strong">{item.label}</div>
                                    <div className="mt-1 text-sm text-panel-muted">Unit: {item.unit}</div>
                                      {item.note ? <div className="mt-2 text-xs text-panel-subtle">{item.note}</div> : null}
                                    </div>
                                  </div>
                                  <StatusBadge tone={item.quantity > 0 ? "info" : "default"}>
                                    {item.quantity > 0 ? "Included" : "Optional"}
                                  </StatusBadge>
                                </div>
                                <div className="mt-4 flex items-center gap-3">
                                  <Button variant="secondary" size="sm" onClick={() => updateSupply(key, "quantity", Math.max(0, item.quantity - 1))}>
                                    -
                                  </Button>
                                  <input
                                    type="number"
                                    min={0}
                                    value={item.quantity}
                                    onChange={(event) => updateSupply(key, "quantity", Math.max(0, Number(event.target.value) || 0))}
                                    className="h-10 w-24 rounded-pill border border-panel-table-wrap bg-panel px-4 text-sm text-panel-strong outline-none focus:border-[var(--dashboard-icon-button-border)]"
                                  />
                                  <Button variant="secondary" size="sm" onClick={() => updateSupply(key, "quantity", item.quantity + 1)}>
                                    +
                                  </Button>
                                </div>
                                <textarea
                                  value={item.note}
                                  onChange={(event) => updateSupply(key, "note", event.target.value)}
                                  rows={2}
                                  placeholder="Optional notes"
                                  className="mt-4 min-h-20 w-full rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-3 text-sm text-panel-strong outline-none placeholder:text-panel-subtle focus:border-[var(--dashboard-icon-button-border)]"
                                />
                                <div className="mt-4 flex items-center justify-between rounded-[1rem] border border-panel-table-wrap/80 bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_24%,transparent)] px-3 py-2 text-xs">
                                  <span className="font-semibold uppercase tracking-[0.12em] text-panel-subtle">Suggested default</span>
                                  <span className="text-panel-copy">
                                    {item.quantity > 0 ? `${item.quantity} ${item.unit}` : `0 ${item.unit}`}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                    ) : null}

                    {dispatchStep === 2 ? (
                      <div className="grid gap-5 lg:grid-cols-2">
                        <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                          <div className="text-sm font-semibold text-panel-strong">Destination</div>
                          <div className="mt-4 space-y-4">
                            <div className="rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-3 text-sm">
                              <div className="font-semibold text-panel-strong">{facility.facilityName}</div>
                              <div className="mt-1 text-panel-muted">{facility.wardName}, {facility.subCounty}</div>
                            </div>
                            <input
                              value={dispatchDraft.facilityContact}
                              onChange={(event) => updateDispatch("facilityContact", event.target.value)}
                              placeholder="Facility contact person"
                              className="h-11 w-full rounded-pill border border-panel-table-wrap bg-panel px-4 text-sm text-panel-strong outline-none focus:border-[var(--dashboard-icon-button-border)]"
                            />
                            <input
                              value={dispatchDraft.facilityPhone}
                              onChange={(event) => updateDispatch("facilityPhone", event.target.value)}
                              placeholder="Phone number"
                              className="h-11 w-full rounded-pill border border-panel-table-wrap bg-panel px-4 text-sm text-panel-strong outline-none focus:border-[var(--dashboard-icon-button-border)]"
                            />
                          </div>
                        </Card>

                        <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                          <div className="text-sm font-semibold text-panel-strong">Logistics confirmation</div>
                          <div className="mt-4 space-y-4">
                            {[
                              {
                                field: "source" as DispatchSelectField,
                                label: "Dispatch source",
                                options: ["Migori County Warehouse", "Sub-county store", "Partner inventory point"],
                              },
                              {
                                field: "transport" as DispatchSelectField,
                                label: "Transport method",
                                options: ["County vehicle", "Motorcycle rider", "Partner transport", "External courier"],
                              },
                              {
                                field: "handler" as DispatchSelectField,
                                label: "Assigned handler",
                                options: ["John Otieno", "Grace Achieng", "Moses Odhiambo"],
                              },
                              {
                                field: "eta" as DispatchSelectField,
                                label: "Estimated arrival time",
                                options: ["2h 15m", "3h 40m", "4h 10m"],
                              },
                            ].map(({ field, label, options }) => (
                              <label key={field} className="grid gap-2">
                                <span className="text-sm font-medium text-panel-copy">{label}</span>
                                <select
                                  value={dispatchDraft[field]}
                                  onChange={(event) => updateDispatch(field, event.target.value)}
                                  className="h-11 rounded-pill border border-panel-table-wrap bg-panel px-4 text-sm text-panel-strong outline-none focus:border-[var(--dashboard-icon-button-border)]"
                                >
                                  {options.map((option) => (
                                    <option key={option} value={option}>
                                      {option}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            ))}
                            <textarea
                              value={dispatchDraft.logisticsNotes}
                              onChange={(event) => updateDispatch("logisticsNotes", event.target.value)}
                              rows={4}
                              placeholder="Special notes for route or access constraints"
                              className="min-h-28 w-full rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-3 text-sm text-panel-strong outline-none placeholder:text-panel-subtle focus:border-[var(--dashboard-icon-button-border)]"
                            />
                          </div>
                        </Card>
                      </div>
                    ) : null}

                    {dispatchStep === 3 ? (
                      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
                        <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                          <div className="text-sm font-semibold text-panel-strong">Dispatch summary</div>
                          <div className="mt-4 grid gap-4 md:grid-cols-2">
                            {[
                              ["Facility", facility.facilityName],
                              ["Supplies", selectedSupplyEntries.map(([, item]) => `${item.quantity} ${item.unit} ${item.label}`).join(", ") || "No supplies selected"],
                              ["Source", dispatchDraft.source],
                              ["Transport", dispatchDraft.transport],
                              ["ETA", dispatchDraft.eta],
                              ["Handler", dispatchDraft.handler],
                              ["Priority", dispatchDraft.priority],
                            ].map(([label, value]) => (
                              <div key={label} className="rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-3">
                                <div className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle">{label}</div>
                                <div className="mt-2 text-sm font-semibold text-panel-strong">{value}</div>
                              </div>
                            ))}
                          </div>
                          <div className="mt-5 rounded-[1.25rem] border border-[color:var(--danger)]/16 bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-4 py-4 text-sm leading-6 text-panel-copy dark:bg-[color-mix(in_srgb,var(--danger)_14%,transparent)]">
                            <strong className="block text-panel-strong">Reason for dispatch</strong>
                            ORS stock is critically low, projected 7-day surge remains elevated, and the facility is likely to exceed readiness thresholds without immediate resupply.
                          </div>
                          <textarea
                            value={dispatchDraft.approvalNote}
                            onChange={(event) => updateDispatch("approvalNote", event.target.value)}
                            rows={4}
                            placeholder="Optional approval note"
                            className="mt-5 min-h-28 w-full rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-3 text-sm text-panel-strong outline-none placeholder:text-panel-subtle focus:border-[var(--dashboard-icon-button-border)]"
                          />
                        </Card>

                        <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                          <div className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle">Approval checkpoint</div>
                          <div className="mt-4 space-y-4 text-sm text-panel-copy">
                            <p>Review the dispatch package, route, and assigned logistics chain before committing county resources.</p>
                            <div className="rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-4">
                              <div className="font-semibold text-panel-strong">Safe confirmation</div>
                              <div className="mt-2 text-panel-muted">High-trust dispatch. One strong confirmation required before the request is created.</div>
                            </div>
                          </div>
                        </Card>
                      </div>
                    ) : null}

                    {dispatchStep === 4 ? (
                      <div className="space-y-6">
                        <div className="rounded-[1.5rem] border border-[color:var(--success)]/18 bg-[linear-gradient(135deg,color-mix(in_srgb,var(--success)_10%,white),color-mix(in_srgb,var(--brand)_10%,white))] px-5 py-5 dark:bg-[linear-gradient(135deg,color-mix(in_srgb,var(--success)_14%,transparent),color-mix(in_srgb,var(--brand)_12%,transparent))]">
                          <div className="flex items-start gap-4">
                            <span className="inline-flex size-12 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]">
                              <CheckCircle2 className="size-6" aria-hidden="true" />
                            </span>
                            <div>
                              <div className="text-lg font-semibold text-panel-strong">Dispatch created successfully</div>
                              <div className="mt-2 text-sm text-panel-copy">
                                Dispatch ID <strong>{dispatchDraft.dispatchId}</strong> is now in <strong>Preparing shipment</strong> status.
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
                          <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                            <div className="text-sm font-semibold text-panel-strong">Dispatch tracking timeline</div>
                            <div className="mt-5 space-y-4">
                              {DISPATCH_STAGES.map((stage, index) => (
                                <div key={stage} className="flex gap-4">
                                  <div className="flex flex-col items-center">
                                    <span
                                      className={cn(
                                        "inline-flex size-9 items-center justify-center rounded-full text-xs font-semibold",
                                        index <= 2
                                          ? "bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]"
                                          : "bg-panel text-panel-subtle",
                                      )}
                                    >
                                      {index <= 2 ? <ClipboardCheck className="size-4" aria-hidden="true" /> : index + 1}
                                    </span>
                                    {index < DISPATCH_STAGES.length - 1 ? <span className="mt-2 h-8 w-px bg-panel-table-wrap" /> : null}
                                  </div>
                                  <div className="pt-1">
                                    <div className="text-sm font-semibold text-panel-strong">{stage}</div>
                                    <div className="mt-1 text-sm text-panel-muted">
                                      {index === 0
                                        ? "Requested by county health official"
                                        : index === 1
                                          ? "Approved and committed for dispatch"
                                          : index === 2
                                            ? "Warehouse team packing supplies"
                                            : "Pending completion"}
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </Card>

                          <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                            <div className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle">Next actions</div>
                            <div className="mt-4 space-y-3">
                              <Button variant="secondary" className="w-full justify-between">
                                Notify Facility
                                <ChevronRight className="size-4" aria-hidden="true" />
                              </Button>
                              <Button variant="secondary" className="w-full justify-between">
                                Open Facility Chat
                                <ChevronRight className="size-4" aria-hidden="true" />
                              </Button>
                              <Button variant="secondary" className="w-full justify-between">
                                View Dispatch Timeline
                                <ChevronRight className="size-4" aria-hidden="true" />
                              </Button>
                            </div>
                          </Card>
                        </div>
                      </div>
                    ) : null}
                      </div>

                      <div className="space-y-4">
                        <Card className="rounded-[1.5rem] px-5 py-5 shadow-none">
                          <div className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle">Dispatch brief</div>
                          <div className="mt-4 space-y-4 text-sm">
                            <div className="rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-4">
                              <div className="text-panel-muted">Facility</div>
                              <div className="mt-1 font-semibold text-panel-strong">{facility.facilityName}</div>
                              <div className="mt-1 text-panel-muted">{facility.wardName}, {facility.subCounty}</div>
                            </div>
                            <div className="rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-4">
                              <div className="text-panel-muted">Priority</div>
                              <div className="mt-2">
                                <StatusBadge tone={priorityTone(dispatchDraft.priority)}>{dispatchDraft.priority}</StatusBadge>
                              </div>
                              <div className="mt-2 text-panel-copy">{dispatchReason}</div>
                            </div>
                            <div className="rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-4">
                              <div className="text-panel-muted">Selected supplies</div>
                              <div className="mt-3 space-y-2">
                                {selectedSupplyEntries.length ? (
                                  selectedSupplyEntries.map(([key, item]) => (
                                    <div key={key} className="flex items-center justify-between gap-3">
                                      <span className="text-panel-copy">{item.label}</span>
                                      <strong className="text-panel-strong">{item.quantity} {item.unit}</strong>
                                    </div>
                                  ))
                                ) : (
                                  <div className="text-panel-muted">No package selected yet.</div>
                                )}
                              </div>
                            </div>
                            {dispatchStep >= 2 ? (
                              <div className="rounded-[1rem] border border-panel-table-wrap bg-panel px-4 py-4">
                                <div className="text-panel-muted">Logistics</div>
                                <div className="mt-2 space-y-2 text-panel-copy">
                                  <div className="flex items-center justify-between gap-3"><span>Source</span><strong className="text-panel-strong">{dispatchDraft.source}</strong></div>
                                  <div className="flex items-center justify-between gap-3"><span>Transport</span><strong className="text-panel-strong">{dispatchDraft.transport}</strong></div>
                                  <div className="flex items-center justify-between gap-3"><span>ETA</span><strong className="text-panel-strong">{dispatchDraft.eta}</strong></div>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        </Card>
                      </div>
                    </div>
                  </div>

                  <div className="border-t border-panel-table-wrap px-6 py-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <Button variant="ghost" onClick={dispatchStep === 0 ? closeDispatchWizard : () => setDispatchStep((value) => Math.max(0, value - 1))}>
                        {dispatchStep === 0 ? "Cancel" : "Back"}
                      </Button>

                      <div className="flex flex-wrap items-center gap-3">
                        {dispatchStep < 4 ? (
                          <Button onClick={() => setDispatchStep((value) => Math.min(4, value + 1))}>
                            {dispatchStep === 0
                              ? "Continue"
                              : dispatchStep === 1
                                ? "Review logistics"
                                : dispatchStep === 2
                                  ? "Review and approve"
                                  : "Confirm Dispatch"}
                          </Button>
                        ) : (
                          <Button onClick={closeDispatchWizard}>Close</Button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </>
        )}
      </RoleGate>
    </div>
  );
}
