"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Search,
  ShieldAlert,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { getLatestTimestamp } from "@/lib/freshness";
import { useWardsQuery } from "@/queries/use-wards-query";

type SortOption = "RISK_DESC" | "RISK_ASC" | "UPDATED_DESC" | "NAME_ASC";
type TriggerFilter = "ALL" | "TRIGGER_ACTIVE" | "AWAITING_ACTION" | "RESOLVED";

const ROWS_PER_PAGE = 5;
const COUNTY_SCOPE = "Migori";
const SEARCH_DEBOUNCE_MS = 300;
const STALE_THRESHOLD_MINUTES = 120;
const TABLE_SKELETON_ROWS = 5;

function parseRiskParam(value: string | null) {
  if (value === "HIGH" || value === "MEDIUM" || value === "LOW" || value === "UNKNOWN") {
    return value;
  }
  return "ALL";
}

function parseSortParam(value: string | null): SortOption {
  switch (value) {
    case "risk_asc":
      return "RISK_ASC";
    case "updated_desc":
      return "UPDATED_DESC";
    case "name_asc":
      return "NAME_ASC";
    case "risk_desc":
    default:
      return "RISK_DESC";
  }
}

function parseTriggerParam(value: string | null): TriggerFilter {
  switch (value) {
    case "trigger_active":
      return "TRIGGER_ACTIVE";
    case "awaiting_action":
      return "AWAITING_ACTION";
    case "resolved":
      return "RESOLVED";
    case "all":
    default:
      return "ALL";
  }
}

function parsePageParam(value: string | null) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return 1;
  }
  return Math.floor(parsed);
}

function formatSortParam(value: SortOption) {
  switch (value) {
    case "RISK_ASC":
      return "risk_asc";
    case "UPDATED_DESC":
      return "updated_desc";
    case "NAME_ASC":
      return "name_asc";
    case "RISK_DESC":
    default:
      return "risk_desc";
  }
}

function formatTriggerParam(value: TriggerFilter) {
  switch (value) {
    case "TRIGGER_ACTIVE":
      return "trigger_active";
    case "AWAITING_ACTION":
      return "awaiting_action";
    case "RESOLVED":
      return "resolved";
    case "ALL":
    default:
      return "all";
  }
}

function getWardOrderingParam(value: SortOption) {
  switch (value) {
    case "RISK_ASC":
      return "current_risk_score";
    case "UPDATED_DESC":
      return "-updated_at";
    case "NAME_ASC":
      return "name";
    case "RISK_DESC":
    default:
      return "-current_risk_score";
  }
}

function normalizeRiskScore(score: number | null) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return 0;
  }
  if (score <= 1) {
    return Math.max(0, Math.min(score * 100, 100));
  }
  return Math.max(0, Math.min(score, 100));
}

function formatRiskScore(score: number | null) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return "N/A";
  }
  return Math.round(normalizeRiskScore(score)).toString();
}

function formatCompactRelativeMinutes(timestamp: string | null) {
  if (!timestamp) {
    return "No recent update";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const diffMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes === 1) return "1 min ago";
  if (diffMinutes < 60) return `${diffMinutes} min ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours === 1) return "1 hr ago";
  if (diffHours < 24) return `${diffHours} hr ago`;

  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} d ago`;
}

function formatOperationalTime(timestamp: string | null) {
  if (!timestamp) {
    return "No timestamp";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const timeLabel = date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return `${timeLabel} (${formatCompactRelativeMinutes(timestamp)})`;
}

function isStaleTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return true;
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return true;
  }

  return (Date.now() - date.getTime()) / 60000 > STALE_THRESHOLD_MINUTES;
}

function getCoverageLabel(totalVisible: number, totalAll: number) {
  if (!totalAll) {
    return "0/0 wards reporting";
  }
  return `${totalVisible}/${totalAll} wards reporting`;
}

function buildPaginationItems(currentPage: number, totalPages: number): Array<number | "..."> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  if (currentPage <= 4) {
    return [1, 2, 3, 4, 5, "...", totalPages];
  }
  if (currentPage >= totalPages - 3) {
    return [1, "...", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  }
  return [1, "...", currentPage - 1, currentPage, currentPage + 1, "...", totalPages];
}

function getRiskBadgeTone(level: string) {
  if (level === "HIGH") return "danger" as const;
  if (level === "MEDIUM") return "warning" as const;
  if (level === "LOW") return "success" as const;
  return "default" as const;
}

function getTriggerStateLabel(value: TriggerFilter) {
  switch (value) {
    case "TRIGGER_ACTIVE":
      return "Trigger active";
    case "AWAITING_ACTION":
      return "Awaiting action";
    case "RESOLVED":
      return "Resolved";
    case "ALL":
    default:
      return "All";
  }
}

function getQueueTriggerStateLabel(value: string) {
  switch (value) {
    case "TRIGGER_ACTIVE":
      return "Trigger active";
    case "REVIEW_PENDING":
      return "Awaiting review";
    case "ACTION_IN_PROGRESS":
      return "Action in progress";
    case "RESOLVED":
      return "Resolved";
    case "NONE":
    default:
      return "No active trigger";
  }
}

function getQueueTriggerStateTone(value: string) {
  if (value === "REVIEW_PENDING") return "warning" as const;
  if (value === "ACTION_IN_PROGRESS") return "danger" as const;
  if (value === "TRIGGER_ACTIVE") return "success" as const;
  if (value === "RESOLVED") return "success" as const;
  return "default" as const;
}

export default function WardsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { currentUser } = useAuth();
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [selectedSubCounty, setSelectedSubCounty] = useState("ALL");
  const [selectedRisk, setSelectedRisk] = useState("ALL");
  const [triggerFilter, setTriggerFilter] = useState<TriggerFilter>("ALL");
  const [sortBy, setSortBy] = useState<SortOption>("RISK_DESC");
  const [page, setPage] = useState(1);
  const [hasSyncedFromUrl, setHasSyncedFromUrl] = useState(false);
  const hasAppliedInitialFilterState = useRef(false);

  useEffect(() => {
    const q = searchParams.get("q")?.trim() ?? "";
    const risk = parseRiskParam(searchParams.get("risk"));
    const subCounty = searchParams.get("sub_county")?.trim() || "ALL";
    const trigger = parseTriggerParam(searchParams.get("trigger"));
    const sort = parseSortParam(searchParams.get("sort"));
    const nextPage = parsePageParam(searchParams.get("page"));

    setSearchInput(q);
    setSearch(q);
    setSelectedRisk(risk);
    setSelectedSubCounty(subCounty);
    setTriggerFilter(trigger);
    setSortBy(sort);
    setPage(nextPage);
    setHasSyncedFromUrl(true);
  }, [searchParams]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setSearch(searchInput.trim());
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [searchInput]);

  useEffect(() => {
    if (!hasSyncedFromUrl) {
      return;
    }

    if (!hasAppliedInitialFilterState.current) {
      hasAppliedInitialFilterState.current = true;
      return;
    }

    setPage(1);
  }, [hasSyncedFromUrl, search, selectedSubCounty, selectedRisk, triggerFilter, sortBy]);

  useEffect(() => {
    if (!hasSyncedFromUrl) {
      return;
    }

    const nextParams = new URLSearchParams(searchParams.toString());

    if (search) nextParams.set("q", search);
    else nextParams.delete("q");

    if (selectedRisk !== "ALL") nextParams.set("risk", selectedRisk);
    else nextParams.delete("risk");

    if (triggerFilter !== "ALL") nextParams.set("trigger", formatTriggerParam(triggerFilter));
    else nextParams.delete("trigger");

    nextParams.set("scope", COUNTY_SCOPE);

    if (selectedSubCounty !== "ALL") nextParams.set("sub_county", selectedSubCounty);
    else nextParams.delete("sub_county");

    nextParams.set("sort", formatSortParam(sortBy));

    if (page > 1) nextParams.set("page", String(page));
    else nextParams.delete("page");

    const currentQuery = searchParams.toString();
    const nextQuery = nextParams.toString();

    if (currentQuery !== nextQuery) {
      router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
    }
  }, [hasSyncedFromUrl, page, pathname, router, search, searchParams, selectedRisk, selectedSubCounty, sortBy, triggerFilter]);

  const wardsQuery = useWardsQuery({
    county: COUNTY_SCOPE,
    q: search || undefined,
    risk: selectedRisk !== "ALL" ? selectedRisk : undefined,
    sub_county: selectedSubCounty !== "ALL" ? selectedSubCounty : undefined,
    ordering: getWardOrderingParam(sortBy),
    enabled: Boolean(currentUser),
  });
  const items = useMemo(() => wardsQuery.data?.items ?? [], [wardsQuery.data?.items]);
  const isLoading = wardsQuery.isPending;
  const isRefreshing = wardsQuery.isFetching;
  const error = wardsQuery.error instanceof Error ? wardsQuery.error.message : null;

  const subCounties = useMemo(() => ["ALL", ...new Set(items.map((item) => item.subCounty).filter(Boolean))], [items]);

  useEffect(() => {
    if (selectedSubCounty !== "ALL" && !subCounties.includes(selectedSubCounty)) {
      setSelectedSubCounty("ALL");
    }
  }, [selectedSubCounty, subCounties]);

  const filteredItems = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return items
      .filter((item) => {
      if (!normalizedSearch) return true;
      return item.name.toLowerCase().includes(normalizedSearch);
      })
      .filter((item) => {
        if (triggerFilter === "ALL") return true;
        if (triggerFilter === "TRIGGER_ACTIVE") {
          return item.triggerState === "TRIGGER_ACTIVE";
        }
        if (triggerFilter === "AWAITING_ACTION") {
          return item.requiresAction;
        }
        if (triggerFilter === "RESOLVED") {
          return item.triggerState === "RESOLVED";
        }
        return true;
      });
  }, [items, search, triggerFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / ROWS_PER_PAGE));
  const currentPage = Math.min(page, totalPages);
  const paginationItems = buildPaginationItems(currentPage, totalPages);
  const pageItems = filteredItems.slice((currentPage - 1) * ROWS_PER_PAGE, currentPage * ROWS_PER_PAGE);
  const latestWardTimestamp = getLatestTimestamp(filteredItems.map((item) => item.updatedAt));
  const wardsRequiringAction = filteredItems.filter((item) => item.requiresAction);
  const workflowActiveWards = filteredItems.filter((item) => item.triggerState !== "NONE" && item.triggerState !== "RESOLVED");
  const alertsPendingCount = filteredItems.reduce((sum, item) => sum + item.deliveryConcernCount, 0);
  const isStale = isStaleTimestamp(latestWardTimestamp);
  const hasActiveFilters =
    Boolean(search.trim()) || selectedSubCounty !== "ALL" || selectedRisk !== "ALL" || triggerFilter !== "ALL" || sortBy !== "RISK_DESC";

  const topbarTimestampLabel = isRefreshing
    ? "Refreshing..."
    : `${formatOperationalTime(latestWardTimestamp)}${isStale ? " · Stale" : ""}`;
  const currentListQuery = searchParams.toString();

  function resetFilters() {
    setSearchInput("");
    setSearch("");
    setSelectedRisk("ALL");
    setSelectedSubCounty("ALL");
    setTriggerFilter("ALL");
    setSortBy("RISK_DESC");
  }

  function getEmptyStateMessage() {
    if (search.trim()) return "No wards match your search.";
    if (selectedSubCounty !== "ALL") return "No wards found in this sub-county.";
    if (selectedRisk !== "ALL") return "No wards match the selected risk filter.";
    if (triggerFilter !== "ALL") return `No wards match the ${getTriggerStateLabel(triggerFilter).toLowerCase()} filter.`;
    if (hasActiveFilters) return "No wards match the current filters.";
    return "No ward risk data is available yet.";
  }

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Wards"
        subtitle="Migori County dashboard"
        lastUpdatedLabel={topbarTimestampLabel}
        lastUpdatedTone={isStale ? "stale" : "default"}
        onRefresh={() => {
          void wardsQuery.refetch();
        }}
      />

      {error ? (
        <div className="rounded-2xl border border-[color-mix(in_srgb,var(--danger)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_10%,var(--dashboard-panel-surface))] px-4 py-3 text-sm font-medium text-[color:var(--danger)]">
          <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      {!isLoading && !error && items.length === 0 ? (
        <div className="rounded-2xl border border-[color-mix(in_srgb,var(--warning)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_10%,var(--dashboard-panel-surface))] px-4 py-3 text-sm font-medium text-[color:var(--warning)]">
          <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
          No ward risk data is available yet.
        </div>
      ) : null}

      <Card className="flex flex-col gap-5 p-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <h1 className="text-[clamp(1.9rem,1.2rem+1vw,2.5rem)] font-semibold tracking-[-0.05em] text-panel-strong">
            Ward Action Queue
          </h1>
          <p className="max-w-3xl text-sm text-panel-muted">
            Identify wards requiring attention and review the latest climate-health risk and trigger state across Migori County.
          </p>
        </div>

        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] px-4 py-2 text-sm font-medium text-panel-copy">
          <ArrowUpRight className="size-4" aria-hidden="true" />
          <span>Latest visible record: {isLoading ? "Refreshing..." : formatCompactRelativeMinutes(latestWardTimestamp)}</span>
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,0.8fr))]">
          <label className="grid gap-2 xl:col-span-1">
            <span aria-hidden="true" className="text-xs font-semibold uppercase tracking-[0.16em] text-transparent">
              Search
            </span>
            <InputShell
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search ward name..."
              icon={<Search className="size-4" aria-hidden="true" />}
              inputClassName="pr-6"
            />
          </label>

          <label className="grid gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Risk</span>
            <div className="relative">
              <select
                value={selectedRisk}
                onChange={(event) => setSelectedRisk(event.target.value)}
                className="h-11 w-full appearance-none rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 pr-10 text-sm font-medium text-panel-copy outline-none transition focus:border-[var(--dashboard-icon-button-border)]"
              >
                <option value="ALL">All</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
                <option value="UNKNOWN">Unknown</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-panel-muted" />
            </div>
          </label>

          <div className="grid gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Scope</span>
            <div className="flex h-11 items-center rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-strong">
              {COUNTY_SCOPE} County
            </div>
          </div>

          <label className="grid gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Sub-county</span>
            <div className="relative">
              <select
                value={selectedSubCounty}
                onChange={(event) => setSelectedSubCounty(event.target.value)}
                className="h-11 w-full appearance-none rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 pr-10 text-sm font-medium text-panel-copy outline-none transition focus:border-[var(--dashboard-icon-button-border)]"
              >
                {subCounties.map((option) => (
                  <option key={option} value={option}>
                    {option === "ALL" ? "All" : option}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-panel-muted" />
            </div>
          </label>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {searchInput ? (
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 py-1.5 text-xs font-medium text-panel-copy transition hover:text-panel-strong"
                onClick={() => setSearchInput("")}
              >
                <X className="size-3.5" aria-hidden="true" />
                Clear search
              </button>
            ) : null}
            {hasActiveFilters ? (
              <button
                type="button"
                className="text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
                onClick={resetFilters}
              >
                Reset filters
              </button>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={isStale ? "warning" : "success"} className="rounded-full px-3 py-1.5 tracking-[0.14em]">
              {isStale ? "Data freshness warning" : "Feed timestamps in range"}
            </StatusBadge>
            {isStale ? (
              <span className="text-sm text-panel-muted">Some risk scores may be outdated — review before acting.</span>
            ) : null}
          </div>
        </div>
      </Card>

      <Card className="space-y-5 p-6">
        {wardsRequiringAction.length > 0 ? (
          <div className="flex flex-col gap-3 rounded-[1.4rem] border border-[color-mix(in_srgb,var(--warning)_32%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_10%,var(--dashboard-panel-surface))] px-4 py-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-3">
              <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl border border-[color-mix(in_srgb,var(--warning)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_14%,var(--dashboard-panel-surface))] text-[color:var(--warning)]">
                <TriangleAlert className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[color:var(--warning)]">Action queue signal</p>
                <p className="text-base font-semibold text-panel-strong">
                  {wardsRequiringAction.length} ward{wardsRequiringAction.length === 1 ? "" : "s"}{" "}
                  {wardsRequiringAction.length === 1 ? "requires" : "require"} action now
                </p>
                <p className="text-sm text-panel-muted">
                  Review wards awaiting trigger action or delivery follow-up before lower-priority monitoring work.
                </p>
              </div>
            </div>
            <button
              type="button"
              className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
              onClick={() => {
                setTriggerFilter("AWAITING_ACTION");
                setPage(1);
              }}
            >
              Review queue
              <ChevronRight className="size-4" aria-hidden="true" />
            </button>
          </div>
        ) : null}

        <PageSectionHeader
          title="Ward Action Queue"
          description="Latest ward records merged from risk, workflow, and alert signals"
          actions={
            <div className="flex flex-wrap items-end gap-3">
              <label className="grid gap-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Trigger state</span>
                <div className="relative min-w-[220px]">
                  <select
                    value={triggerFilter}
                    onChange={(event) => setTriggerFilter(event.target.value as TriggerFilter)}
                    className="h-11 w-full appearance-none rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 pr-10 text-sm font-medium text-panel-copy outline-none transition focus:border-[var(--dashboard-icon-button-border)]"
                  >
                    <option value="ALL">All</option>
                    <option value="TRIGGER_ACTIVE">Trigger active</option>
                    <option value="AWAITING_ACTION">Awaiting action</option>
                    <option value="RESOLVED">Resolved</option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-panel-muted" />
                </div>
              </label>

              <label className="grid gap-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Sort by</span>
                <div className="relative min-w-[220px]">
                  <select
                    value={sortBy}
                    onChange={(event) => setSortBy(event.target.value as SortOption)}
                    className="h-11 w-full appearance-none rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 pr-10 text-sm font-medium text-panel-copy outline-none transition focus:border-[var(--dashboard-icon-button-border)]"
                  >
                    <option value="RISK_DESC">Risk score (highest first)</option>
                    <option value="RISK_ASC">Risk score (lowest first)</option>
                    <option value="UPDATED_DESC">Last updated</option>
                    <option value="NAME_ASC">Ward name (A-Z)</option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-panel-muted" />
                </div>
              </label>
            </div>
          }
        />

        {isLoading ? (
          <div className="space-y-4">
            <div className="overflow-hidden rounded-[1.5rem] border border-[var(--dashboard-table-line)]">
              <table className="min-w-full border-collapse">
                <thead>
                  <tr>
                    {["Ward name", "Trigger state", "Risk level", "Risk score", "Expected cases (7d)", "Last updated", "Actions"].map((label) => (
                      <th
                        key={label}
                        className="border-b border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted"
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: TABLE_SKELETON_ROWS }, (_, index) => (
                    <tr key={`skeleton-${index}`}>
                      <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 last:border-b-0">
                        <div className="flex items-center gap-3">
                          <span className="size-3 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_90%,transparent)]" />
                          <div className="space-y-2">
                            <div className="h-4 w-32 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_90%,transparent)]" />
                            <div className="h-3 w-20 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_65%,transparent)]" />
                          </div>
                        </div>
                      </td>
                      {Array.from({ length: 6 }, (_, cellIndex) => (
                        <td
                          key={`cell-${cellIndex}`}
                          className="border-b border-[var(--dashboard-table-line)] px-4 py-4 last:border-b-0"
                        >
                          <div className="h-4 w-20 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)]" />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-sm text-panel-muted">Loading ward risk summaries...</p>
          </div>
        ) : pageItems.length > 0 ? (
          <>
            <div className="overflow-hidden rounded-[1.5rem] border border-[var(--dashboard-table-line)]">
              <div className="overflow-x-auto">
                <table className="min-w-full border-collapse text-left">
                  <thead>
                    <tr>
                      {["Ward name", "Trigger state", "Risk level", "Risk score", "Expected cases (7d)", "Last updated", "Actions"].map((label) => (
                        <th
                          key={label}
                          className="border-b border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted"
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {pageItems.map((item) => (
                      <tr key={item.id}>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <div className="flex items-center gap-3">
                            <span
                              className={cn(
                                "size-3 rounded-full",
                                item.riskLevel === "HIGH"
                                  ? "bg-[color:var(--danger)]"
                                  : item.riskLevel === "MEDIUM"
                                    ? "bg-[color:var(--warning)]"
                                    : item.riskLevel === "LOW"
                                      ? "bg-[color:var(--success)]"
                                      : "bg-panel-muted",
                              )}
                            />
                            <div className="space-y-0.5">
                              <strong className="block font-semibold text-panel-strong">{item.name}</strong>
                              <span className="text-xs text-panel-muted">{item.subCounty}</span>
                            </div>
                          </div>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <StatusBadge
                            tone={getQueueTriggerStateTone(item.triggerState)}
                            className="rounded-full px-3 py-1 tracking-[0.14em]"
                          >
                            {getQueueTriggerStateLabel(item.triggerState)}
                          </StatusBadge>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <StatusBadge
                            tone={getRiskBadgeTone(item.riskLevel)}
                            className="rounded-full px-3 py-1 tracking-[0.14em]"
                          >
                            {item.riskLevel}
                          </StatusBadge>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <div className="space-y-2">
                            <div className="flex items-end gap-1.5">
                              <strong className="text-lg font-semibold tracking-[-0.04em] text-panel-strong">
                                {formatRiskScore(item.riskScore)}
                              </strong>
                              <span className="pb-0.5 text-xs text-panel-muted">/100</span>
                            </div>
                            <div className="h-1.5 w-full rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)]">
                              <span
                                className="block h-full rounded-full bg-[linear-gradient(90deg,var(--login-submit-start),var(--login-submit-end))]"
                                style={{ width: `${normalizeRiskScore(item.riskScore)}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                          {typeof item.predictedCases === "number" ? item.predictedCases : "—"}
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                          {formatCompactRelativeMinutes(item.updatedAt)}
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <Link
                            href={
                              currentListQuery
                                ? `/wards/${item.id}?returnTo=${encodeURIComponent(`${pathname}?${currentListQuery}`)}`
                                : `/wards/${item.id}`
                            }
                            className="inline-flex items-center gap-2 font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
                          >
                            {item.requiresAction ? "Review" : "View details"}
                            <ChevronRight className="size-4" aria-hidden="true" />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-panel-muted">
                <span>
                  {pageItems.length} of {filteredItems.length} wards
                </span>
                <span>Rows per page: {ROWS_PER_PAGE}</span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="inline-flex size-10 items-center justify-center rounded-full border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy transition hover:text-panel-strong disabled:pointer-events-none disabled:opacity-50"
                  disabled={currentPage === 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="size-4" aria-hidden="true" />
                </button>

                {paginationItems.map((pageItem, index) =>
                  pageItem === "..." ? (
                    <span key={`ellipsis-${index}`} className="px-2 text-sm text-panel-muted">
                      ...
                    </span>
                  ) : (
                    <button
                      key={pageItem}
                      type="button"
                      className={cn(
                        "inline-flex size-10 items-center justify-center rounded-full text-sm font-semibold transition",
                        pageItem === currentPage
                          ? "bg-[var(--login-submit-start)] text-white shadow-[var(--login-submit-shadow)]"
                          : "border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy hover:text-panel-strong",
                      )}
                      onClick={() => setPage(Number(pageItem))}
                    >
                      {pageItem}
                    </button>
                  ),
                )}

                <button
                  type="button"
                  className="inline-flex size-10 items-center justify-center rounded-full border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy transition hover:text-panel-strong disabled:pointer-events-none disabled:opacity-50"
                  disabled={currentPage === totalPages}
                  onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                  aria-label="Next page"
                >
                  <ChevronRight className="size-4" aria-hidden="true" />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-[1.5rem] border border-dashed border-[var(--dashboard-table-line)] px-5 py-10 text-center text-sm text-panel-muted">
            {getEmptyStateMessage()}
          </div>
        )}
      </Card>

      <section className="grid gap-6 xl:grid-cols-3">
        <Card className="space-y-4 p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Wards requiring action</span>
            <ShieldAlert className="size-5 text-[color:var(--danger)]" aria-hidden="true" />
          </div>
          <strong className="block text-4xl font-semibold tracking-[-0.05em] text-panel-strong">
            {isLoading ? "..." : String(wardsRequiringAction.length).padStart(2, "0")}
          </strong>
          <p className="text-sm text-panel-muted">
            {isLoading ? "Loading queue summary..." : `${wardsRequiringAction.length} visible in the current queue require review or follow-up`}
          </p>
        </Card>

        <Card className="space-y-4 p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Workflow-active wards</span>
            <TriangleAlert className="size-5 text-[color:var(--warning)]" aria-hidden="true" />
          </div>
          <strong className="block text-4xl font-semibold tracking-[-0.05em] text-panel-strong">
            {isLoading ? "..." : String(workflowActiveWards.length).padStart(2, "0")}
          </strong>
          <p className="text-sm text-panel-muted">
            {isLoading ? "Loading workflow state..." : `${workflowActiveWards.length} visible wards currently have an in-flight trigger workflow`}
          </p>
        </Card>

        <Card className="space-y-4 p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Alerts pending</span>
            <TriangleAlert className="size-5 text-[color:var(--warning)]" aria-hidden="true" />
          </div>
          <strong className="block text-4xl font-semibold tracking-[-0.05em] text-panel-strong">
            {isLoading ? "..." : String(alertsPendingCount).padStart(2, "0")}
          </strong>
          <p className="text-sm text-panel-muted">
            {isLoading ? "Loading delivery concerns..." : `${alertsPendingCount} retry-pending or failed deliveries are linked to the visible wards`}
          </p>
        </Card>
      </section>
    </div>
  );
}
