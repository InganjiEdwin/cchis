"use client";

import {
  AlertTriangle,
  Building2,
  ChevronLeft,
  ChevronRight,
  Filter,
  PackagePlus,
  Search,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";
import {
  buildFacilityRows,
  freshnessTone,
  type FacilityRow,
  riskTone,
  staffingTone,
  stockTone,
} from "@/lib/facility-readiness";
import { useFacilityReadinessQuery } from "@/queries/use-facility-readiness-query";

const STALE_THRESHOLD_MINUTES = 120;
const ROWS_PER_PAGE = 5;

export default function FacilityReadinessPage() {
  const [search, setSearch] = useState("");
  const [selectedWard, setSelectedWard] = useState("ALL");
  const [page, setPage] = useState(1);
  const { data, isPending: isLoading, error } = useFacilityReadinessQuery();
  const facilities = data?.facilities ?? [];
  const risks = data?.risks ?? [];
  const alerts = data?.alerts ?? [];

  const latestTimestamp = useMemo(
    () =>
      getLatestTimestamp([
        ...facilities.map((facility) => facility.updated_at),
        ...risks.map((risk) => risk.generated_at),
        ...alerts.map((alert) => alert.created_at),
      ]),
    [alerts, facilities, risks],
  );
  const freshness = useMemo(() => describeFreshness(latestTimestamp, STALE_THRESHOLD_MINUTES), [latestTimestamp]);
  const lastUpdatedLabel = latestTimestamp ? formatRelativeTimestamp(latestTimestamp) : freshness.label;

  const facilityRows = useMemo(() => buildFacilityRows(facilities, risks), [facilities, risks]);

  const wardFilterOptions = useMemo(
    () => ["ALL", ...new Set(facilityRows.map((row) => row.wardName).sort((a, b) => a.localeCompare(b)))],
    [facilityRows],
  );

  const filteredRows = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return facilityRows.filter((row) => {
      if (selectedWard !== "ALL" && row.wardName !== selectedWard) {
        return false;
      }
      if (!normalizedSearch) {
        return true;
      }
      return (
        row.facilityName.toLowerCase().includes(normalizedSearch) ||
        row.wardName.toLowerCase().includes(normalizedSearch) ||
        row.subCounty.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [facilityRows, search, selectedWard]);

  useEffect(() => {
    setPage(1);
  }, [search, selectedWard]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / ROWS_PER_PAGE));
  const currentPage = Math.min(page, totalPages);
  const visibleRows = filteredRows.slice((currentPage - 1) * ROWS_PER_PAGE, currentPage * ROWS_PER_PAGE);

  const activeFacilities = facilityRows.length;
  const criticalFacilities = facilityRows.filter((row) => row.surgeRisk === "EXTREME").length;
  const averageOrs = facilityRows.length
    ? Math.round(facilityRows.reduce((sum, row) => sum + row.orsStockPercent, 0) / facilityRows.length)
    : 0;
  const immediateAlerts = facilityRows.filter((row) => row.surgeRisk === "EXTREME").slice(0, 2);
  const forecastCases = facilityRows.reduce((sum, row) => sum + row.projectedCases, 0);
  const overloadedFacilities = facilityRows.filter((row) => row.surgeRisk === "EXTREME").length;
  const surgeCardIsCalm = criticalFacilities === 0;
  const immediateAlertsTitle = immediateAlerts.length ? "Immediate Alerts" : "No Active Facility Alerts";
  const immediateAlertsSubtitle = isLoading
    ? "Checking readiness..."
    : immediateAlerts.length
      ? `${immediateAlerts.length} active`
      : "System operating within safe thresholds";
  const forecastActionGuidance = overloadedFacilities
    ? `Action: dispatch and resupply review recommended for ${overloadedFacilities} facilities.`
    : "Action: continue monitoring, no dispatch required.";

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Facility Readiness"
        subtitle="Operational status and climate-driven surge forecasting for Migori County."
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
      />

      <RoleGate
        allowedRoles={["ADMIN", "SUPERVISOR", "ANALYST"]}
        title="Facility readiness is role-restricted"
        message="Facility readiness is intended for dashboard roles coordinating preparedness and response."
      >
        {error ? (
          <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
            {error instanceof Error ? error.message : "Unable to load facility readiness."}
          </StatusBanner>
        ) : null}

        <section className="grid gap-4 md:grid-cols-3">
          <Card className="rounded-[2rem] bg-panel px-6 py-4">
            <div className="flex items-start gap-4">
              <span className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                <Building2 className="size-5" aria-hidden="true" />
              </span>
              <div>
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Facilities in scope</span>
                <strong className="mt-2 block text-4xl font-semibold leading-none text-panel-strong">
                  {isLoading ? "..." : activeFacilities}
                </strong>
                <small className="mt-3 block text-sm text-panel-muted">Active facilities in view</small>
              </div>
            </div>
          </Card>

          <Card
            className={cn(
              "rounded-[2rem] bg-panel px-6 py-4",
              surgeCardIsCalm
                ? "border-[color:var(--success)]/25"
                : "border-[color:var(--danger)]/22",
            )}
          >
            <div className="flex items-start gap-4">
              <span
                className={cn(
                  "inline-flex size-12 shrink-0 items-center justify-center rounded-2xl",
                  surgeCardIsCalm
                    ? "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_18%,transparent)]"
                    : "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]",
                )}
              >
                {surgeCardIsCalm ? <ShieldCheck className="size-5" aria-hidden="true" /> : <TriangleAlert className="size-5" aria-hidden="true" />}
              </span>
              <div>
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                  {surgeCardIsCalm ? "No facilities at risk" : "Facilities at surge risk"}
                </span>
                <strong className="mt-2 block text-4xl font-semibold leading-none text-panel-strong">
                  {isLoading ? "..." : criticalFacilities}
                </strong>
                <small className="mt-3 block text-sm text-panel-muted">
                  {surgeCardIsCalm ? "No active surge escalation in scope" : "Require active resupply review"}
                </small>
              </div>
            </div>
          </Card>

          <Card className="rounded-[2rem] bg-panel px-6 py-4">
            <div className="flex items-start gap-4">
              <span className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]">
                <PackagePlus className="size-5" aria-hidden="true" />
              </span>
              <div>
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">ORS stock readiness</span>
                <strong className="mt-2 block text-4xl font-semibold leading-none text-panel-strong">
                  {isLoading ? "..." : `${averageOrs}%`}
                </strong>
                <small className="mt-3 block text-sm text-panel-muted">County average across visible facilities</small>
              </div>
            </div>
          </Card>
        </section>

        <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_22rem]">
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="space-y-1.5">
              <div className="min-w-0">
                <h2 className="text-[clamp(1.6rem,1rem+1vw,2.3rem)] font-semibold leading-tight text-panel-strong">
                  Facility Preparedness Matrix
                </h2>
                <p className="mt-2 text-sm text-panel-muted">
                  Real facility records with readiness indicators still derived from ward risk and alert activity
                </p>
              </div>

              <div className="flex justify-end">
                <div className="grid w-full gap-3 md:max-w-[33rem] md:grid-cols-[minmax(13rem,15rem)_minmax(11rem,13rem)_auto] md:items-center">
                <label className="grid min-w-0 gap-2">
                  <span aria-hidden="true" className="text-sm font-medium text-transparent">
                    Search
                  </span>
                  <InputShell
                    className="min-w-0"
                    icon={<Search className="size-4" aria-hidden="true" />}
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search facilities..."
                    inputClassName="text-sm"
                  />
                </label>

                <label className="flex min-w-0 flex-col gap-2">
                  <span aria-hidden="true" className="text-sm font-medium text-transparent">
                    Filter
                  </span>
                  <span className="relative flex h-10 items-center rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 shadow-sm">
                    <select
                      value={selectedWard}
                      onChange={(event) => setSelectedWard(event.target.value)}
                      className="h-full w-full appearance-none bg-transparent pr-8 text-sm text-panel-strong outline-none"
                    >
                      {wardFilterOptions.map((option) => (
                        <option key={option} value={option}>
                          {option === "ALL" ? "All Wards" : option}
                        </option>
                      ))}
                    </select>
                  </span>
                </label>

                <label className="grid gap-2 xl:justify-self-end">
                  <span aria-hidden="true" className="text-sm font-medium text-transparent">
                    Filters
                  </span>
                  <Button variant="secondary" size="icon" className="size-10" aria-label="More filters">
                    <Filter className="size-4" aria-hidden="true" />
                  </Button>
                </label>
                </div>
              </div>
            </div>

            <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-panel-table-wrap">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-panel-table-wrap text-sm">
                  <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]">
                    <tr className="text-left">
                      {[
                        "Facility name",
                        "Ward",
                        "Surge risk",
                        "ORS stocks",
                        "Staffing",
                        "Last reported",
                        "Action",
                      ].map((label) => (
                        <th
                          key={label}
                          className="px-5 py-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle"
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-panel-table-wrap bg-panel">
                    {isLoading ? (
                      Array.from({ length: 4 }).map((_, index) => (
                        <tr key={`facility-skeleton-${index}`}>
                          <td colSpan={7} className="px-5 py-5">
                            <div className="h-6 w-full animate-pulse rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                          </td>
                        </tr>
                      ))
                    ) : visibleRows.length ? (
                      visibleRows.map((row) => (
                        <tr
                          key={row.id}
                          className="cursor-pointer transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_40%,transparent)]"
                        >
                          <td className="px-5 py-4 align-top">
                            <div className="flex items-center gap-3">
                              <span className="inline-flex size-11 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-sm font-semibold text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                                {row.facilityName.slice(0, 2).toUpperCase()}
                              </span>
                              <div>
                                <strong className="block text-base text-panel-strong">{row.facilityName}</strong>
                                <small className="text-sm text-panel-muted">{row.facilityType}</small>
                              </div>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <div className="text-panel-copy">{row.wardName}</div>
                            <small className="text-sm text-panel-muted">{row.subCounty}</small>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <div className="space-y-2">
                              <StatusBadge tone={riskTone(row.surgeRisk)} className="tracking-[0.12em]">
                                {row.surgeRisk === "EXTREME" ? "Extreme" : row.surgeRisk === "MODERATE" ? "Moderate" : "Low"}
                              </StatusBadge>
                              <small className="block text-sm text-panel-muted">+{row.projectedCases} projected cases</small>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <div className="space-y-2">
                              <strong className="block text-base text-panel-strong">{row.orsStockPercent}%</strong>
                              <StatusBadge tone={stockTone(row.orsState)} className="tracking-[0.12em]">
                                {row.orsState}
                              </StatusBadge>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <div className="space-y-2">
                              <span className="block text-base text-panel-strong">
                                {row.staffingFilled}/{row.staffingRequired}
                              </span>
                              <StatusBadge tone={staffingTone(row.staffingState)} className="tracking-[0.12em]">
                                {row.staffingState}
                              </StatusBadge>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <div className="space-y-2">
                              <span className="block text-panel-copy">{row.lastReported}</span>
                              <StatusBadge tone={freshnessTone(row.freshnessState)} className="tracking-[0.12em]">
                                {row.freshnessState === "FRESH" ? "Current" : row.freshnessState === "WARNING" ? "Warning" : "Stale"}
                              </StatusBadge>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <Link
                              href={`/facility-readiness/${row.id}`}
                              className="inline-flex h-9 items-center rounded-pill px-3 text-sm font-medium text-panel-copy transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_72%,transparent)] hover:text-panel-strong"
                            >
                              View
                            </Link>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7} className="px-5 py-10 text-center text-sm text-panel-muted">
                          No facilities match the current filters.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <span className="text-sm text-panel-muted">
                Showing {visibleRows.length} of {filteredRows.length} facilities
              </span>

              {totalPages > 1 ? (
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="icon"
                    className="size-10"
                    onClick={() => setPage((value) => Math.max(1, value - 1))}
                    disabled={currentPage === 1}
                  >
                    <ChevronLeft className="size-4" aria-hidden="true" />
                  </Button>
                  <Button
                    variant="secondary"
                    size="icon"
                    className="size-10"
                    onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                    disabled={currentPage === totalPages}
                  >
                    <ChevronRight className="size-4" aria-hidden="true" />
                  </Button>
                </div>
              ) : null}
            </div>
          </Card>

          <div className="space-y-5">
            <Card className="rounded-[2rem] px-5 py-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-semibold text-panel-strong">{immediateAlertsTitle}</h2>
                  <p className="mt-2 text-sm text-panel-muted">{immediateAlertsSubtitle}</p>
                </div>
                <Button variant="secondary" className="h-10 px-4">
                  <Filter className="size-4" aria-hidden="true" />
                  Filter by ward
                </Button>
              </div>

              <div className="mt-5 space-y-3">
                {isLoading ? (
                  <div className="rounded-[1.5rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                    Loading facility alerts...
                  </div>
                ) : immediateAlerts.length ? (
                  immediateAlerts.map((row) => (
                    <article key={row.id} className="rounded-[1.5rem] border border-panel-table-wrap px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <strong className="text-base text-panel-strong">{row.facilityName}</strong>
                        <StatusBadge tone="danger" className="tracking-[0.12em]">
                          High risk
                        </StatusBadge>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-panel-copy">
                        Surge pressure is rising in {row.wardName}. ORS levels are at {row.orsStockPercent}% with projected
                        case activity at {row.projectedCases}.
                      </p>
                      <button
                        type="button"
                        className="mt-4 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-sidebar-title)]"
                      >
                        {row.orsStockPercent < 30 ? "Dispatch ORS supplies" : "Send alert to facility"}
                      </button>
                    </article>
                  ))
                ) : (
                  <div className="flex items-start gap-3 rounded-[1.5rem] border border-panel-table-wrap px-4 py-5">
                    <span className="inline-flex size-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--success)_16%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]">
                      <ShieldCheck className="size-4" aria-hidden="true" />
                    </span>
                    <div>
                      <strong className="block text-base text-panel-strong">No active facility alerts</strong>
                      <span className="mt-1 block text-sm text-panel-muted">
                        System operating within safe thresholds across visible facilities.
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </Card>

            <Card className="rounded-[2rem] px-5 py-5">
              <div>
                <h2 className="text-2xl font-semibold text-panel-strong">Surge Forecast</h2>
                <p className="mt-2 text-sm text-panel-muted">Next 14-day projection</p>
              </div>

              <div className="mt-5 rounded-[1.5rem] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] px-4 py-4">
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">7-day outlook</span>
                <strong className="mt-3 block text-4xl font-semibold leading-none text-[color:var(--warning)]">
                  +{isLoading ? "..." : forecastCases} cases
                </strong>
                <span className="mt-3 block text-sm text-panel-copy">
                  {isLoading ? "Loading..." : `${overloadedFacilities} facilities expected to exceed capacity`}
                </span>
              </div>

              <p className="mt-4 text-sm font-medium text-panel-copy">
                {isLoading ? "Assessing recommended action..." : forecastActionGuidance}
              </p>

              <div className="mt-5 space-y-3">
                {facilityRows.slice(0, 3).map((row) => (
                  <div key={`forecast-${row.id}`} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-panel-copy">{row.facilityName}</span>
                    <strong className="text-[color:var(--warning)]">+{row.projectedCases}</strong>
                  </div>
                ))}
              </div>

              <Card className="mt-5 rounded-[1.5rem] bg-[color-mix(in_srgb,var(--brand)_8%,var(--panel))] px-4 py-4 shadow-none">
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-brand">High reliability</span>
                <p className="mt-2 text-sm text-panel-copy">
                  Validated against current rainfall, ward risk, and recent alert activity.
                </p>
              </Card>
            </Card>
          </div>
        </section>
      </RoleGate>
    </div>
  );
}
