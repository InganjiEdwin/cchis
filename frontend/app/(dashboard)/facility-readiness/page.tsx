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
import { useEffect, useMemo, useRef, useState } from "react";

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

type FacilityAdvancedFilter = "ALL" | "STALE" | "ACTIVE_REVIEW" | "UPDATE_PENDING" | "ESCALATED" | "HIGH_RISK";

const ADVANCED_FILTER_LABELS: Record<FacilityAdvancedFilter, string> = {
  ALL: "All facility signals",
  STALE: "Stale reports",
  ACTIVE_REVIEW: "Review open",
  UPDATE_PENDING: "Update pending",
  ESCALATED: "Escalated",
  HIGH_RISK: "High calculated risk",
};

function compactFacilityName(name: string) {
  return name.replace(/\s+(Dispensary|Health Centre|Health Center|Hospital)$/i, "");
}

export default function FacilityReadinessPage() {
  const [search, setSearch] = useState("");
  const [selectedWard, setSelectedWard] = useState("ALL");
  const [advancedFilter, setAdvancedFilter] = useState<FacilityAdvancedFilter>("ALL");
  const [isAdvancedFilterOpen, setIsAdvancedFilterOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [focusedFacilityId, setFocusedFacilityId] = useState<number | null>(null);
  const matrixRef = useRef<HTMLElement | null>(null);
  const { data, isPending: isLoading, error } = useFacilityReadinessQuery();
  const facilities = data?.facilities ?? [];
  const risks = data?.risks ?? [];
  const alerts = data?.alerts ?? [];
  const decisionSummary = data?.decisionSummary ?? null;
  const workflowStates = data?.workflowStates ?? [];

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
  const workflowStateByFacilityId = useMemo(
    () => new Map(workflowStates.map((workflowState) => [workflowState.facility_id, workflowState])),
    [workflowStates],
  );
  const hasClientMatrixFilters = selectedWard !== "ALL" || search.trim().length > 0 || advancedFilter !== "ALL";

  const wardFilterOptions = useMemo(
    () => ["ALL", ...new Set(facilityRows.map((row) => row.wardName).sort((a, b) => a.localeCompare(b)))],
    [facilityRows],
  );

  const filteredRows = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return facilityRows.filter((row) => {
      const workflowState = workflowStateByFacilityId.get(row.facilityId);
      if (selectedWard !== "ALL" && row.wardName !== selectedWard) {
        return false;
      }
      if (advancedFilter === "STALE" && row.freshnessState !== "STALE") {
        return false;
      }
      if (advancedFilter === "ACTIVE_REVIEW" && !workflowState?.has_active_review) {
        return false;
      }
      if (advancedFilter === "UPDATE_PENDING" && !workflowState?.has_active_update_request) {
        return false;
      }
      if (advancedFilter === "ESCALATED" && !workflowState?.has_active_escalation) {
        return false;
      }
      if (advancedFilter === "HIGH_RISK" && row.surgeRisk !== "EXTREME") {
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
  }, [advancedFilter, facilityRows, search, selectedWard, workflowStateByFacilityId]);

  const advancedFilterCounts = useMemo(() => {
    return facilityRows.reduce(
      (counts, row) => {
        const workflowState = workflowStateByFacilityId.get(row.facilityId);
        if (row.freshnessState === "STALE") {
          counts.STALE += 1;
        }
        if (workflowState?.has_active_review) {
          counts.ACTIVE_REVIEW += 1;
        }
        if (workflowState?.has_active_update_request) {
          counts.UPDATE_PENDING += 1;
        }
        if (workflowState?.has_active_escalation) {
          counts.ESCALATED += 1;
        }
        if (row.surgeRisk === "EXTREME") {
          counts.HIGH_RISK += 1;
        }
        return counts;
      },
      {
        ALL: facilityRows.length,
        STALE: 0,
        ACTIVE_REVIEW: 0,
        UPDATE_PENDING: 0,
        ESCALATED: 0,
        HIGH_RISK: 0,
      } satisfies Record<FacilityAdvancedFilter, number>,
    );
  }, [facilityRows, workflowStateByFacilityId]);

  useEffect(() => {
    setPage(1);
  }, [advancedFilter, search, selectedWard]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / ROWS_PER_PAGE));
  const currentPage = Math.min(page, totalPages);
  const visibleRows = filteredRows.slice((currentPage - 1) * ROWS_PER_PAGE, currentPage * ROWS_PER_PAGE);

  const activeFacilities = facilityRows.length;
  const criticalFacilities = facilityRows.filter((row) => row.surgeRisk === "EXTREME").length;
  const allFacilitiesStale = facilityRows.length > 0 && facilityRows.every((row) => row.freshnessState === "STALE");
  const averageOrs = facilityRows.length
    ? Math.round(facilityRows.reduce((sum, row) => sum + row.orsStockPercent, 0) / facilityRows.length)
    : 0;
  const forecastCases = facilityRows.reduce((sum, row) => sum + row.projectedCases, 0);
  const overloadedFacilities = facilityRows.filter((row) => row.surgeRisk === "EXTREME").length;
  const surgeCardIsCalm = criticalFacilities === 0;
  const recommendationTone =
    decisionSummary?.state === "DEGRADED_CONFIDENCE" ||
    decisionSummary?.confidence === "DEGRADED" ||
    (!decisionSummary && allFacilitiesStale)
      ? "warning"
      : "default";
  const priorityItems = decisionSummary?.top_priorities ?? [];
  const totalReviewFacilityCount =
    typeof decisionSummary?.total_review_facility_count === "number"
      ? decisionSummary.total_review_facility_count
      : null;
  const topPriority = priorityItems[0] ?? null;
  const nextPriority = priorityItems[1] ?? null;
  const priorityLabelByFacilityId = useMemo(
    () => new Map(priorityItems.map((priority) => [priority.facility_id, priority.priority_label])),
    [priorityItems],
  );
  const workflowCounts = useMemo(
    () =>
      workflowStates.reduce(
        (counts, workflowState) => ({
          activeReviews: counts.activeReviews + (workflowState.has_active_review ? 1 : 0),
          updateRequests: counts.updateRequests + (workflowState.has_active_update_request ? 1 : 0),
          escalations: counts.escalations + (workflowState.has_active_escalation ? 1 : 0),
        }),
        { activeReviews: 0, updateRequests: 0, escalations: 0 },
      ),
    [workflowStates],
  );
  const priorityRows = useMemo(
    () =>
      priorityItems
        .map((priority) => facilityRows.find((row) => row.facilityId === priority.facility_id))
        .filter((row): row is FacilityRow => Boolean(row)),
    [facilityRows, priorityItems],
  );
  const recommendationHeadline = isLoading
    ? "Preparing readiness guidance"
    : decisionSummary?.headline
      ? decisionSummary.headline
      : allFacilitiesStale
        ? "Decision confidence degraded"
        : "No immediate facility review required";
  const recommendationBody = isLoading
    ? "Loading readiness guidance."
    : decisionSummary?.body
      ? decisionSummary.body
      : allFacilitiesStale
        ? "Facility readiness inputs are stale. No facilities are currently flagged for review, but this assessment is based on outdated data."
        : "Based on the current derived readiness estimates, no facility is flagged for review.";
  const reviewSummaryTitle = "Current review summary";
  const reviewSummarySubtitle = isLoading
    ? "Checking readiness priorities..."
    : decisionSummary?.state === "DEGRADED_CONFIDENCE"
      ? typeof totalReviewFacilityCount === "number" && totalReviewFacilityCount > 0
        ? "Facilities are flagged for readiness review, but data freshness is limited."
        : "No facilities are currently flagged for review, but data freshness is limited."
      : typeof totalReviewFacilityCount === "number" && totalReviewFacilityCount > 0
        ? `${totalReviewFacilityCount} facilities are currently flagged for readiness review in this view.`
        : decisionSummary && totalReviewFacilityCount === null
          ? "Readiness review count is unavailable in this view."
        : "No facilities are currently flagged for readiness review in this view.";
  const forecastImpactScan = isLoading
    ? "Calculating..."
    : typeof totalReviewFacilityCount === "number" && totalReviewFacilityCount > 0
      ? `${totalReviewFacilityCount} review signal${totalReviewFacilityCount === 1 ? "" : "s"}`
      : decisionSummary && totalReviewFacilityCount === null
        ? "Review count unavailable"
        : "No capacity concern";
  const forecastActionScan = isLoading
    ? "Preparing..."
    : topPriority
      ? `Review ${compactFacilityName(topPriority.facility_name)}`
      : decisionSummary?.state === "DEGRADED_CONFIDENCE" || allFacilitiesStale
        ? "Monitor stale reports"
        : "Continue monitoring";
  const forecastConfidenceScan = decisionSummary?.state === "DEGRADED_CONFIDENCE" || allFacilitiesStale
    ? "Low (stale inputs)"
    : "Normal";

  function focusPriorityInMatrix(facilityId: number, facilityName: string, wardName: string) {
    setFocusedFacilityId(facilityId);
    setSearch(facilityName);
    setSelectedWard(wardName);
    setPage(1);
    if (typeof matrixRef.current?.scrollIntoView === "function") {
      matrixRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Facility Readiness"
        subtitle="Facility records with calculated readiness estimates for Migori County."
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
      />

      <RoleGate
        pageCapability="facility_readiness"
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
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Facilities assessed</span>
                <strong className="mt-2 block text-4xl font-semibold leading-none text-panel-strong">
                  {isLoading ? "..." : activeFacilities}
                </strong>
                <small className="mt-3 block text-sm text-panel-muted">Facility records included in this readiness view</small>
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
                  {surgeCardIsCalm ? "No facilities in high calculated risk" : "Facilities in high calculated risk"}
                </span>
                <strong className="mt-2 block text-4xl font-semibold leading-none text-panel-strong">
                  {isLoading ? "..." : criticalFacilities}
                </strong>
                <small className="mt-3 block text-sm text-panel-muted">
                  {surgeCardIsCalm
                    ? "No high calculated readiness concern detected"
                    : "Calculated readiness concern is present in this view"}
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
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Estimated ORS coverage</span>
                <strong className="mt-2 block text-4xl font-semibold leading-none text-panel-strong">
                  {isLoading ? "..." : `${averageOrs}%`}
                </strong>
                <small className="mt-3 block text-sm text-panel-muted">
                  Estimated from ward risk and facility identity in this readiness view, not live stock feeds
                </small>
              </div>
            </div>
          </Card>
        </section>

        <Card
          className={cn(
            "rounded-[2rem] px-5 py-5 sm:px-6",
            recommendationTone === "warning"
              ? "border-[color:var(--warning)]/30 bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))]"
              : "bg-panel",
          )}
        >
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">System recommendation</span>
          <div className="mt-3 space-y-2">
            <h2 className="text-2xl font-semibold text-panel-strong">
              {recommendationHeadline}
            </h2>
            <p className="text-sm leading-6 text-panel-copy">
              {recommendationBody}
            </p>
            {!isLoading && decisionSummary?.confidence === "DEGRADED" ? (
              <p className="text-sm font-medium text-[color:var(--warning)]">
                Decision confidence degraded
                {decisionSummary.confidence_reason ? `: ${decisionSummary.confidence_reason.replaceAll("_", " ")}.` : "."}
              </p>
            ) : null}
          </div>

          {!isLoading && priorityItems.length > 0 ? (
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {[topPriority, nextPriority].filter(Boolean).map((priority) => (
                <div
                  key={priority!.facility_id}
                  className="rounded-2xl border border-panel-border bg-panel/55 px-4 py-4"
                >
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                    {priority!.priority_label}
                  </span>
                  <h3 className="mt-2 text-lg font-semibold text-panel-strong">{priority!.facility_name}</h3>
                  <p className="mt-1 text-sm text-panel-muted">{priority!.ward_name}</p>
                  <p className="mt-3 text-sm leading-6 text-panel-copy">{priority!.reason_text}</p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <Button
                      variant="secondary"
                      className="w-full justify-center"
                      onClick={() => focusPriorityInMatrix(priority!.facility_id, priority!.facility_name, priority!.ward_name)}
                    >
                      Focus in matrix
                    </Button>
                    <Link
                      href={priority!.review_href ?? `/facility-readiness/${priority!.facility_id}`}
                      className="inline-flex h-11 w-full items-center justify-center rounded-pill bg-[var(--login-submit-start)] px-4 text-sm font-semibold text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
                    >
                      Review detail
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {!isLoading && decisionSummary && priorityItems.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-panel-border bg-panel/55 px-4 py-4">
              <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Current readiness scope</span>
              <p className="mt-2 text-sm leading-6 text-panel-copy">
                No facilities are currently flagged for readiness review in this view.
              </p>
            </div>
          ) : null}

          {!isLoading && decisionSummary?.related_surfaces.has_linked_alerts ? (
            <p className="mt-4 text-sm text-panel-muted">
              Linked alert context is present for {decisionSummary.related_surfaces.linked_alert_count} alert
              {decisionSummary.related_surfaces.linked_alert_count === 1 ? "" : " records"} in the current readiness scope.
            </p>
          ) : null}

          {!isLoading && hasClientMatrixFilters ? (
            <p className="mt-3 text-sm text-panel-muted">
              The matrix filters below are narrower than the readiness summary shown above.
            </p>
          ) : null}
        </Card>

        <section ref={matrixRef} className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_22rem]">
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="space-y-1.5">
              <div className="min-w-0">
                <h2 className="text-[clamp(1.6rem,1rem+1vw,2.3rem)] font-semibold leading-tight text-panel-strong">
                  Facility Preparedness Matrix
                </h2>
                <p className="mt-2 text-sm text-panel-muted">
                  Facility records with readiness estimates calculated from ward risk and alert activity
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

                <div className="grid gap-2 xl:justify-self-end">
                  <span aria-hidden="true" className="text-sm font-medium text-transparent">
                    Filters
                  </span>
                  <div className="relative">
                    <Button
                      variant="secondary"
                      size="icon"
                      className={cn(
                        "size-10",
                        advancedFilter !== "ALL" &&
                          "border-[color:var(--brand)]/45 bg-[color-mix(in_srgb,var(--brand)_14%,var(--panel))] text-brand",
                      )}
                      aria-label={`More filters${advancedFilter !== "ALL" ? `: ${ADVANCED_FILTER_LABELS[advancedFilter]}` : ""}`}
                      aria-expanded={isAdvancedFilterOpen}
                      onClick={() => setIsAdvancedFilterOpen((value) => !value)}
                    >
                      <Filter className="size-4" aria-hidden="true" />
                    </Button>

                    {isAdvancedFilterOpen ? (
                      <div className="absolute right-0 z-20 mt-2 w-72 rounded-[1.5rem] border border-panel-border bg-panel p-3 shadow-[var(--dashboard-card-shadow)]">
                        <div className="flex items-start justify-between gap-3 px-2 py-1">
                          <div>
                            <p className="text-sm font-semibold text-panel-strong">Filter facilities</p>
                            <p className="mt-1 text-xs leading-5 text-panel-muted">Narrow the matrix by operational signal.</p>
                          </div>
                          {advancedFilter !== "ALL" ? (
                            <button
                              type="button"
                              className="text-xs font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
                              onClick={() => {
                                setAdvancedFilter("ALL");
                                setIsAdvancedFilterOpen(false);
                              }}
                            >
                              Reset
                            </button>
                          ) : null}
                        </div>

                        <div className="mt-2 space-y-1">
                          {(["ALL", "STALE", "ACTIVE_REVIEW", "UPDATE_PENDING", "ESCALATED", "HIGH_RISK"] satisfies FacilityAdvancedFilter[]).map(
                            (filter) => (
                              <button
                                key={filter}
                                type="button"
                                className={cn(
                                  "flex w-full items-center justify-between gap-3 rounded-2xl px-3 py-2 text-left text-sm transition",
                                  advancedFilter === filter
                                    ? "bg-[color-mix(in_srgb,var(--brand)_14%,var(--panel))] text-panel-strong"
                                    : "text-panel-copy hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_45%,transparent)]",
                                )}
                                onClick={() => {
                                  setAdvancedFilter(filter);
                                  setIsAdvancedFilterOpen(false);
                                }}
                              >
                                <span>{ADVANCED_FILTER_LABELS[filter]}</span>
                                <span className="rounded-pill border border-panel-border px-2 py-0.5 text-xs font-semibold text-panel-muted">
                                  {advancedFilterCounts[filter]}
                                </span>
                              </button>
                            ),
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
                </div>
              </div>
            </div>

            {advancedFilter !== "ALL" ? (
              <div className="mt-4 flex flex-wrap items-center gap-2 text-sm text-panel-muted">
                <span>Active filter:</span>
                <button
                  type="button"
                  className="inline-flex items-center rounded-pill border border-[color:var(--brand)]/35 bg-[color-mix(in_srgb,var(--brand)_10%,var(--panel))] px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-brand transition hover:bg-[color-mix(in_srgb,var(--brand)_16%,var(--panel))]"
                  onClick={() => setAdvancedFilter("ALL")}
                >
                  {ADVANCED_FILTER_LABELS[advancedFilter]}
                </button>
              </div>
            ) : null}

            <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-panel-table-wrap">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-panel-table-wrap text-sm">
                  <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]">
                    <tr className="text-left">
                      {[
                        "Facility name",
                        "Ward",
                        "Calculated risk",
                        "Calculated ORS",
                        "Calculated staffing",
                        "Last reported",
                        "Record",
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
                      visibleRows.map((row) => {
                        const workflowState = workflowStateByFacilityId.get(row.facilityId);
                        return (
                        <tr
                          key={row.id}
                          className={cn(
                            "cursor-pointer transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_40%,transparent)]",
                            priorityLabelByFacilityId.has(row.facilityId) &&
                              "bg-[color-mix(in_srgb,var(--brand)_8%,transparent)]",
                            focusedFacilityId === row.facilityId &&
                              "bg-[color-mix(in_srgb,var(--brand)_12%,transparent)] ring-1 ring-[color:var(--brand)]/25",
                          )}
                        >
                          <td className="px-5 py-4 align-top">
                            <div className="flex items-center gap-3">
                              <span className="inline-flex size-11 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-sm font-semibold text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                                {row.facilityName.slice(0, 2).toUpperCase()}
                              </span>
                              <div>
                                <strong className="block text-base text-panel-strong">{row.facilityName}</strong>
                                {priorityLabelByFacilityId.has(row.facilityId) ? (
                                  <small className="mt-1 inline-flex rounded-pill bg-[color-mix(in_srgb,var(--brand)_12%,white)] px-2.5 py-1 text-xs font-semibold text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                                    {priorityLabelByFacilityId.get(row.facilityId)}
                                  </small>
                                ) : null}
                                {workflowState && workflowState.label !== "No review signals" ? (
                                  <small className="mt-1 block">
                                    <StatusBadge tone={workflowState.tone} className="tracking-[0.1em]">
                                      {workflowState.label}
                                    </StatusBadge>
                                  </small>
                                ) : null}
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
                                {row.surgeRisk === "EXTREME" ? "High" : row.surgeRisk === "MODERATE" ? "Moderate" : "Low"}
                              </StatusBadge>
                              <small className="block text-sm text-panel-muted">+{row.projectedCases} calculated cases</small>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <div className="space-y-2">
                              <strong className="block text-base text-panel-strong">{row.orsStockPercent}%</strong>
                              <StatusBadge tone={stockTone(row.orsState)} className="tracking-[0.12em]">
                                {row.orsState} estimate
                              </StatusBadge>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <div className="space-y-2">
                              <span className="block text-base text-panel-strong">
                                {row.staffingFilled}/{row.staffingRequired}
                              </span>
                              <StatusBadge tone={staffingTone(row.staffingState)} className="tracking-[0.12em]">
                                {row.staffingState} estimate
                              </StatusBadge>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <div className="space-y-2">
                              <span className="block text-panel-copy">{row.lastReported}</span>
                              <span title={row.freshnessState === "STALE" ? "Last reported data is outdated." : undefined}>
                                <StatusBadge tone={freshnessTone(row.freshnessState)} className="tracking-[0.12em]">
                                  {row.freshnessState === "FRESH" ? "Recent" : row.freshnessState === "WARNING" ? "Warning" : "Stale"}
                                </StatusBadge>
                              </span>
                            </div>
                          </td>
                          <td className="px-5 py-4 align-top">
                            <Link
                              href={`/facility-readiness/${row.id}`}
                              className="inline-flex h-9 items-center rounded-pill px-3 text-sm font-medium text-panel-copy transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_72%,transparent)] hover:text-panel-strong"
                            >
                              Review detail
                            </Link>
                          </td>
                        </tr>
                      );
                      })
                    ) : (
                      <tr>
                        <td colSpan={7} className="px-5 py-10 text-center text-sm text-panel-muted">
                          No facilities match the selected filters.
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
                  <h2 className="text-2xl font-semibold text-panel-strong">{reviewSummaryTitle}</h2>
                  <p className="mt-2 text-sm text-panel-muted">{reviewSummarySubtitle}</p>
                </div>
                {!isLoading && (decisionSummary?.state === "DEGRADED_CONFIDENCE" || allFacilitiesStale) ? (
                  <StatusBadge tone="warning" className="tracking-[0.12em]">
                    Low confidence
                  </StatusBadge>
                ) : null}
              </div>

              <div className="mt-5 space-y-3">
                {!isLoading && workflowStates.length > 0 ? (
                  <div className="grid gap-2 rounded-[1.25rem] border border-panel-table-wrap px-4 py-3 text-sm text-panel-copy">
                    <div className="flex items-center justify-between gap-3">
                      <span>Active reviews</span>
                      <strong className="text-panel-strong">{workflowCounts.activeReviews}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Update requests pending</span>
                      <strong className="text-panel-strong">{workflowCounts.updateRequests}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>County reviews escalated</span>
                      <strong className="text-panel-strong">{workflowCounts.escalations}</strong>
                    </div>
                  </div>
                ) : null}

                {isLoading ? (
                  <div className="rounded-[1.5rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                    Loading facility readiness rows...
                  </div>
                ) : priorityItems.length ? (
                  priorityItems.map((priority) => {
                    const row = priorityRows.find((candidate) => candidate.facilityId === priority.facility_id);
                    return (
                    <article key={priority.facility_id} className="rounded-[1.5rem] border border-panel-table-wrap px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <strong className="text-base text-panel-strong">{priority.facility_name}</strong>
                          <span className="mt-1 block text-sm text-panel-muted">{priority.ward_name}</span>
                        </div>
                        <StatusBadge
                          tone={priority.priority_rank === 1 ? "warning" : "default"}
                          className="tracking-[0.12em]"
                        >
                          {priority.priority_label}
                        </StatusBadge>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-panel-copy">
                        {priority.reason_text}
                      </p>
                      {row ? (
                        <p className="mt-3 text-sm text-panel-muted">
                          Calculated ORS estimate: {row.orsStockPercent}%. Projected cases: +{row.projectedCases}.
                        </p>
                      ) : null}
                      <Button
                        variant="secondary"
                        className="mt-4"
                        onClick={() => focusPriorityInMatrix(priority.facility_id, priority.facility_name, priority.ward_name)}
                      >
                        Focus in matrix
                      </Button>
                    </article>
                  );
                  })
                ) : (
                  <div className="flex items-start gap-3 rounded-[1.5rem] border border-panel-table-wrap px-4 py-5">
                    <span className="inline-flex size-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--success)_16%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]">
                      <ShieldCheck className="size-4" aria-hidden="true" />
                    </span>
                    <div>
                      <strong className="block text-base text-panel-strong">
                        {decisionSummary?.state === "DEGRADED_CONFIDENCE" || allFacilitiesStale
                          ? "No review signals detected (low confidence)"
                          : "Safe current view"}
                      </strong>
                      <span className="mt-1 block text-sm text-panel-muted">
                        {decisionSummary?.state === "DEGRADED_CONFIDENCE" || allFacilitiesStale
                          ? "No facilities are currently flagged for review, but data freshness is limited."
                          : "No visible facilities are currently flagged for readiness review."}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </Card>

            <Card className="rounded-[2rem] px-5 py-5">
              <div>
                <h2 className="text-2xl font-semibold text-panel-strong">Surge Forecast</h2>
                <p className="mt-1 text-xs text-panel-muted">7-day projection from ward risk and alert activity</p>
              </div>

              <div className="mt-4 rounded-[1.5rem] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] px-4 py-4">
                <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">7-day calculated outlook</span>
                <strong className="mt-2 block text-4xl font-semibold leading-none text-[color:var(--warning)]">
                  +{isLoading ? "..." : forecastCases} cases
                </strong>
                <span className="mt-2 block text-xs text-panel-muted">
                  {isLoading ? "Loading..." : `${overloadedFacilities} facilities in high calculated readiness difference`}
                </span>
              </div>

              <div className="mt-4 space-y-2 rounded-[1.25rem] border border-panel-table-wrap px-3 py-3 text-sm">
                {[
                  ["Impact", forecastImpactScan],
                  ["Action", forecastActionScan],
                  ["Confidence", forecastConfidenceScan],
                ].map(([label, value]) => (
                  <div key={label} className="grid grid-cols-[5.75rem_minmax(0,1fr)] items-start gap-3">
                    <span className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle">{label}</span>
                    <span className={cn("font-semibold text-panel-strong", label === "Confidence" && forecastConfidenceScan.startsWith("Low") ? "text-[color:var(--warning)]" : "")}>
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-5 space-y-3">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Top contributors</span>
                {(priorityRows.length ? priorityRows : facilityRows.slice(0, 3)).map((row) => (
                  <div key={`forecast-${row.id}`} className="flex items-center justify-between gap-3 text-sm">
                    <div className="min-w-0">
                      <span className="block truncate text-panel-copy">{compactFacilityName(row.facilityName)}</span>
                      {priorityLabelByFacilityId.has(row.facilityId) ? (
                        <span className="ml-2 text-xs font-semibold uppercase tracking-[0.12em] text-panel-subtle">
                          {priorityLabelByFacilityId.get(row.facilityId)}
                        </span>
                      ) : null}
                    </div>
                    <strong className="text-[color:var(--warning)]">+{row.projectedCases}</strong>
                  </div>
                ))}
              </div>

              <Card className="mt-5 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--brand)_8%,var(--panel))] px-3 py-3 shadow-none">
                <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-brand">Limitation</span>
                <p className="mt-1 text-xs leading-5 text-panel-copy">
                  Calculated estimates only. No live inventory, staffing, or bed feeds.
                </p>
              </Card>
            </Card>
          </div>
        </section>
      </RoleGate>
    </div>
  );
}
