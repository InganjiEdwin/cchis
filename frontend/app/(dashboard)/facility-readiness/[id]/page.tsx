"use client";

import {
  AlertTriangle,
  ArrowLeft,
  Bell,
  Building2,
  MapPinned,
  PackagePlus,
  ShieldAlert,
  ShieldCheck,
  Truck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { useMemo } from "react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { MigoriWardMap } from "@/components/migori-ward-map";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { riskTone, stockTone } from "@/lib/facility-readiness";
import { describeFreshness, formatRelativeTimestamp } from "@/lib/freshness";
import { useFacilityDetailQuery } from "@/queries/use-facility-detail-query";

function timelineToneClasses(tone: "danger" | "warning" | "info" | "success") {
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

export default function FacilityDetailPage() {
  const params = useParams<{ id: string }>();
  const facilityId = Number(params.id);
  const { data, isPending: isLoading, error } = useFacilityDetailQuery(
    Number.isInteger(facilityId) && facilityId > 0 ? facilityId : null,
  );
  const intelligence = data?.intelligence ?? null;
  const facilityRecord = intelligence?.facility ?? null;
  const readiness = intelligence?.readiness ?? null;
  const context = intelligence?.context ?? null;
  const timeline = intelligence?.timeline ?? [];
  const capabilities = intelligence?.capabilities ?? null;
  const wardMap = data?.wardMap ?? null;
  const selectedMapWard = useMemo(
    () => wardMap?.features.find((feature) => feature.properties.name === facilityRecord?.ward_name) ?? null,
    [facilityRecord?.ward_name, wardMap],
  );
  const latestTimestamp = intelligence?.freshness.updated_at ?? null;
  const freshness = useMemo(() => describeFreshness(latestTimestamp, 120), [latestTimestamp]);
  const lastUpdatedLabel = latestTimestamp ? formatRelativeTimestamp(latestTimestamp) : freshness.label;

  if (!isLoading && (!facilityRecord || !readiness || !context || !capabilities)) {
    notFound();
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Facility Detail"
        subtitle="Facility identity and calculated facility summary are backend-backed for this page."
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

        {isLoading || !facilityRecord || !readiness || !context || !capabilities ? (
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
                      <StatusBadge tone={riskTone(readiness.surge_risk)} className="tracking-[0.14em]">
                        {readiness.surge_risk_label} Risk
                      </StatusBadge>
                      <span className="text-sm text-panel-muted">Last reported: {readiness.last_reported_at ? formatRelativeTimestamp(readiness.last_reported_at) : "No timestamp recorded"}</span>
                    </div>
                    <h1 className="text-[clamp(2.2rem,1.4rem+2vw,3.5rem)] font-semibold tracking-[-0.05em] text-panel-strong">
                      {facilityRecord.name}
                    </h1>
                    <p className="text-sm text-panel-muted">
                      {facilityRecord.sub_county} Sub-County | {readiness.facility_type_label} | {facilityRecord.ward_name} Ward
                    </p>
                  </div>
                </div>

                <div className="rounded-[1.5rem] border border-[color:var(--danger)]/18 bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-4 py-3 text-sm font-semibold text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_16%,transparent)]">
                  {readiness.status_banner_label}
                </div>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="border-l-2 border-[color:var(--danger)] px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Derived risk</span>
                  <div className="mt-3 text-3xl font-semibold text-[color:var(--danger)]">
                    {readiness.surge_risk_label}
                  </div>
                </div>
                <div className="border-l-2 border-panel-table-wrap px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated load</span>
                  <div className="mt-3 text-3xl font-semibold text-panel-strong">~{readiness.predicted_cases_per_day} <span className="text-base font-medium text-panel-muted">cases/day</span></div>
                </div>
                <div className="border-l-2 border-[color:var(--danger)] px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated ORS estimate</span>
                  <div className="mt-3 text-3xl font-semibold text-[color:var(--danger)]">
                    {readiness.ors_estimate_percent}% <span className="text-sm font-semibold uppercase">{readiness.ors_state}</span>
                  </div>
                </div>
                <div className="border-l-2 border-panel-table-wrap px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated staffing estimate</span>
                  <div className="mt-3 text-3xl font-semibold text-panel-strong">
                    {readiness.staffing_filled}/{readiness.staffing_required} <span className="text-base font-medium text-panel-muted">Active</span>
                  </div>
                </div>
              </div>
            </Card>

            <section className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_22rem]">
              <div className="space-y-5">
                <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
                  <div className="flex items-center gap-2 text-sm font-semibold text-panel-strong">
                    <MapPinned className="size-4 text-brand" aria-hidden="true" />
                    Risk Context
                  </div>

                  <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
                    <div className="space-y-4">
                      <p className="text-sm leading-7 text-panel-copy">{context.summary}</p>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">Ward risk score</div>
                          <div className="mt-2 text-sm font-semibold text-panel-strong">
                            {context.ward_risk_score?.toFixed(2) ?? "--"}
                          </div>
                        </div>
                        <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">Ward-linked alerts</div>
                          <div className="mt-2 text-sm font-semibold text-panel-strong">
                            {context.ward_alert_count}
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
                              selectedWardName={facilityRecord.ward_name}
                              onSelectWard={() => undefined}
                            />
                          ) : (
                            <div className="flex h-full items-center justify-center text-center text-sm text-panel-muted">
                              Ward geometry is not available for this facility view yet.
                            </div>
                          )}
                        </div>
                        <div className="inline-flex w-max items-center gap-2 rounded-full bg-[color-mix(in_srgb,var(--brand)_10%,white)] px-3 py-1.5 text-xs font-semibold text-panel-strong">
                          <span className="size-2 rounded-full bg-brand" />
                          {facilityRecord.ward_name} ward context
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>

                <div className="space-y-3">
                  <h2 className="text-2xl font-semibold text-panel-strong">Resource Estimates</h2>
                  <div className="grid gap-4 md:grid-cols-3">
                    <Card className="rounded-[1.6rem] bg-panel px-5 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--danger)_12%,white)] text-[color:var(--danger)]">
                          <PackagePlus className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-[color:var(--danger)]">{readiness.ors_state} estimate</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated ORS estimate</div>
                      <div className="mt-2 text-4xl font-semibold text-panel-strong">{readiness.ors_estimate_percent}%</div>
                      <div className="mt-1 text-sm text-panel-muted">Calculated from ward pressure</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--danger)_12%,white)]">
                        <div className="h-full rounded-full bg-[color:var(--danger)]" style={{ width: `${readiness.ors_estimate_percent}%` }} />
                      </div>
                    </Card>

                    <Card className="rounded-[1.6rem] bg-panel px-5 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand">
                          <Users className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-brand">{readiness.staffing_state} estimate</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated staffing estimate</div>
                      <div className="mt-2 text-4xl font-semibold text-panel-strong">{readiness.staffing_percent}%</div>
                      <div className="mt-1 text-sm text-panel-muted">Calculated from ward pressure</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)]">
                        <div className="h-full rounded-full bg-brand" style={{ width: `${readiness.staffing_percent}%` }} />
                      </div>
                    </Card>

                    <Card className="rounded-[1.6rem] bg-panel px-5 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)]">
                          <Building2 className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-[color:var(--warning)]">{readiness.surge_risk_label}</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated demand</div>
                      <div className="mt-2 text-4xl font-semibold text-panel-strong">~{readiness.predicted_cases_per_day}</div>
                      <div className="mt-1 text-sm text-panel-muted">Calculated cases/day estimate</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--warning)_12%,white)]">
                        <div className="h-full rounded-full bg-[color:var(--warning)]" style={{ width: `${Math.min(100, readiness.projected_cases * 4)}%` }} />
                      </div>
                    </Card>
                  </div>
                </div>

                <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
                  <h2 className="text-2xl font-semibold text-panel-strong">Facility Record Timeline</h2>
                  <div className="mt-5 space-y-4">
                    {timeline.map((item) => (
                      <div key={item.id} className="flex gap-4">
                        <div className={cn("mt-1 inline-flex size-9 shrink-0 items-center justify-center rounded-full", timelineToneClasses(item.tone))}>
                          {item.tone === "danger" ? <AlertTriangle className="size-4" aria-hidden="true" /> : item.tone === "warning" ? <Bell className="size-4" aria-hidden="true" /> : <Truck className="size-4" aria-hidden="true" />}
                        </div>
                        <div className="min-w-0 flex-1 rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <strong className="text-panel-strong">{item.title}</strong>
                            <span className="text-panel-muted">{item.timestamp ? formatRelativeTimestamp(item.timestamp) : "No timestamp recorded"}</span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-panel-copy">{item.description}</p>
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
                    Unavailable Actions
                  </div>
                  <p className="mt-4 rounded-[1.25rem] border border-[color:var(--danger)]/16 bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-4 py-3 text-sm leading-6 text-panel-copy dark:bg-[color-mix(in_srgb,var(--danger)_14%,transparent)]">
                    Calculated context: ORS, staffing, and demand posture on this page are backend-backed summaries. Dispatch and communication routes are not exposed on this page.
                  </p>
                  <div className="mt-5 space-y-3">
                    <Button className="w-full justify-center" disabled>
                      <Truck className="size-4" aria-hidden="true" />
                      {capabilities.can_dispatch ? "Dispatch route exposed" : "Dispatch unavailable"}
                    </Button>
                    <Button variant="secondary" className="w-full justify-between" disabled>
                      {capabilities.can_open_chat ? "Facility chat route exposed" : "Facility chat unavailable"}
                      <span className="text-panel-muted">+</span>
                    </Button>
                    <Button variant="secondary" className="w-full justify-between" disabled>
                      {capabilities.can_notify_chvs ? "CHV notification route exposed" : "CHV notification unavailable"}
                      <span className="text-panel-muted">+</span>
                    </Button>
                    <Button variant="danger" className="w-full justify-between" disabled>
                      {capabilities.can_escalate_county ? "County escalation route exposed" : "County escalation unavailable"}
                      <span>!</span>
                    </Button>
                  </div>
                </Card>

                <Card className="rounded-[2rem] px-5 py-5">
                  <div className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                    Contact registry
                  </div>
                  <div className="mt-4 rounded-[1.25rem] border border-dashed border-panel-table-wrap px-4 py-4 text-sm text-panel-copy">
                    No backend contact registry is exposed to this page yet, so named operational contacts are intentionally hidden rather than hardcoded.
                  </div>
                </Card>
              </div>
            </section>

          </>
        )}
      </RoleGate>
    </div>
  );
}
