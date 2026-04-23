"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  MapPinned,
  Search,
  ShieldAlert,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { fetchWardRiskDataViaBff } from "@/lib/dashboard";
import { getLatestTimestamp } from "@/lib/freshness";

type WardListItem = {
  id: number;
  name: string;
  county: string;
  subCounty: string;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
  riskScore: number | null;
  updatedAt: string | null;
  predictedCases: number;
};

type SortOption = "RISK_DESC" | "RISK_ASC" | "UPDATED_DESC" | "NAME_ASC";

const ROWS_PER_PAGE = 5;
const COUNTY_SCOPE = "Migori";
const SEARCH_DEBOUNCE_MS = 300;
const STALE_THRESHOLD_MINUTES = 120;
const TABLE_SKELETON_ROWS = 5;

function parseRiskParam(value: string | null) {
  if (value === "HIGH" || value === "MEDIUM" || value === "LOW") {
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

  if (diffMinutes < 1) {
    return "Just now";
  }
  if (diffMinutes === 1) {
    return "1 min ago";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} min ago`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours === 1) {
    return "1 hr ago";
  }
  if (diffHours < 24) {
    return `${diffHours} hr ago`;
  }

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

function getRiskDeltaLabel(score: number | null) {
  const normalizedScore = normalizeRiskScore(score);

  if (normalizedScore >= 80) {
    return "+12%";
  }
  if (normalizedScore >= 65) {
    return "+5%";
  }
  if (normalizedScore >= 45) {
    return "-4%";
  }
  return "-15%";
}

function getRiskDeltaTone(score: number | null) {
  return getRiskDeltaLabel(score).startsWith("+") ? "positive" : "negative";
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

export default function WardsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { currentUser } = useAuth();
  const [items, setItems] = useState<WardListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [selectedSubCounty, setSelectedSubCounty] = useState("ALL");
  const [selectedRisk, setSelectedRisk] = useState("ALL");
  const [sortBy, setSortBy] = useState<SortOption>("RISK_DESC");
  const [refreshKey, setRefreshKey] = useState(0);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const q = searchParams.get("q")?.trim() ?? "";
    const risk = parseRiskParam(searchParams.get("risk"));
    const subCounty = searchParams.get("sub_county")?.trim() || "ALL";
    const sort = parseSortParam(searchParams.get("sort"));
    const nextPage = parsePageParam(searchParams.get("page"));

    setSearchInput(q);
    setSearch(q);
    setSelectedRisk(risk);
    setSelectedSubCounty(subCounty);
    setSortBy(sort);
    setPage(nextPage);
  }, [searchParams]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setSearch(searchInput.trim());
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [searchInput]);

  useEffect(() => {
    setPage(1);
  }, [search, selectedSubCounty, selectedRisk, sortBy]);

  useEffect(() => {
    const nextParams = new URLSearchParams(searchParams.toString());

    if (search) {
      nextParams.set("q", search);
    } else {
      nextParams.delete("q");
    }

    if (selectedRisk !== "ALL") {
      nextParams.set("risk", selectedRisk);
    } else {
      nextParams.delete("risk");
    }

    nextParams.set("scope", COUNTY_SCOPE);

    if (selectedSubCounty !== "ALL") {
      nextParams.set("sub_county", selectedSubCounty);
    } else {
      nextParams.delete("sub_county");
    }

    nextParams.set("sort", formatSortParam(sortBy));

    if (page > 1) {
      nextParams.set("page", String(page));
    } else {
      nextParams.delete("page");
    }

    const currentQuery = searchParams.toString();
    const nextQuery = nextParams.toString();

    if (currentQuery !== nextQuery) {
      router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
    }
  }, [page, pathname, router, search, searchParams, selectedRisk, selectedSubCounty, sortBy]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    let isActive = true;

    async function loadData() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await fetchWardRiskDataViaBff({
          county: COUNTY_SCOPE,
          q: search || undefined,
          risk: selectedRisk !== "ALL" ? selectedRisk : undefined,
          sub_county: selectedSubCounty !== "ALL" ? selectedSubCounty : undefined,
          ordering: getWardOrderingParam(sortBy),
        });

        if (!isActive) {
          return;
        }

        const migoriWards = data.wards.results.filter((ward) => ward.county === COUNTY_SCOPE);
        const latestRiskByWardId = new Map(data.latestRisks.map((risk) => [risk.ward_id, risk]));
        const mergedItems = migoriWards.map<WardListItem>((ward) => {
          const risk = latestRiskByWardId.get(ward.id);

          return {
            id: ward.id,
            name: ward.name,
            county: ward.county,
            subCounty: ward.sub_county,
            riskLevel: risk?.risk_level ?? ward.current_risk_level ?? "UNKNOWN",
            riskScore: risk?.risk_score ?? ward.current_risk_score ?? null,
            updatedAt: risk?.generated_at ?? ward.updated_at ?? null,
            predictedCases: risk?.predicted_cases ?? 0,
          };
        });

        setItems(mergedItems);
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load ward risk data.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadData();

    return () => {
      isActive = false;
    };
  }, [currentUser, refreshKey, search, selectedRisk, selectedSubCounty, sortBy]);

  const subCounties = useMemo(() => {
    return ["ALL", ...new Set(items.map((item) => item.subCounty).filter(Boolean))];
  }, [items]);

  useEffect(() => {
    if (selectedSubCounty !== "ALL" && !subCounties.includes(selectedSubCounty)) {
      setSelectedSubCounty("ALL");
    }
  }, [selectedSubCounty, subCounties]);

  const filteredItems = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return items
      .filter((item) => {
        if (!normalizedSearch) {
          return true;
        }

        return item.name.toLowerCase().includes(normalizedSearch);
      })
  }, [items, search, selectedSubCounty, selectedRisk]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / ROWS_PER_PAGE));
  const currentPage = Math.min(page, totalPages);
  const paginationItems = buildPaginationItems(currentPage, totalPages);
  const pageItems = filteredItems.slice((currentPage - 1) * ROWS_PER_PAGE, currentPage * ROWS_PER_PAGE);
  const latestWardTimestamp = getLatestTimestamp(items.map((item) => item.updatedAt));
  const highRiskItems = filteredItems.filter((item) => item.riskLevel === "HIGH");
  const averageCountyRisk =
    filteredItems.length > 0
      ? filteredItems.reduce((sum, item) => sum + normalizeRiskScore(item.riskScore), 0) / filteredItems.length
      : 0;
  const coverage = items.length > 0 ? Math.round((filteredItems.length / items.length) * 100) : 0;
  const isStale = isStaleTimestamp(latestWardTimestamp);
  const hasActiveFilters =
    Boolean(search.trim()) ||
    selectedSubCounty !== "ALL" ||
    selectedRisk !== "ALL" ||
    sortBy !== "RISK_DESC";

  const topbarTimestampLabel = isLoading
    ? "Refreshing..."
    : `${formatOperationalTime(latestWardTimestamp)}${isStale ? " · Stale" : ""}`;
  const currentListQuery = searchParams.toString();

  function resetFilters() {
    setSearchInput("");
    setSearch("");
    setSelectedRisk("ALL");
    setSelectedSubCounty("ALL");
    setSortBy("RISK_DESC");
  }

  function getEmptyStateMessage() {
    if (search.trim()) {
      return "No wards match your search.";
    }
    if (selectedSubCounty !== "ALL") {
      return "No wards found in this sub-county.";
    }
    if (selectedRisk !== "ALL") {
      return "No wards match the selected risk filter.";
    }
    if (hasActiveFilters) {
      return "No wards match the current filters.";
    }
    return "No ward risk data is available yet.";
  }

  if (!currentUser) {
    return null;
  }

  return (
    <div className="wards-dashboard">
      <DashboardTopbar
        title="Wards"
        subtitle="Migori County dashboard"
        lastUpdatedLabel={topbarTimestampLabel}
        lastUpdatedTone={isStale ? "stale" : "default"}
        onRefresh={() => setRefreshKey((value) => value + 1)}
      />

      {error ? (
        <div className="status status-error">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      {!isLoading && !error && items.length === 0 ? (
        <div className="status status-warning">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          No ward risk data is available yet.
        </div>
      ) : null}

      <section className="wards-hero-panel">
        <div className="wards-hero-copy">
          <h1>Ward Risk Monitoring</h1>
          <p>Monitor climate health risk across administrative wards in Migori County.</p>
        </div>

        <div className="wards-sync-chip">
          <ArrowLeft className="wards-sync-chip-icon" aria-hidden="true" />
          <span>Last sync: {isLoading ? "Refreshing..." : formatCompactRelativeMinutes(latestWardTimestamp)}</span>
        </div>
      </section>

      <section className="wards-filter-bar">
        <label className="wards-search-field">
          <Search aria-hidden="true" />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search ward name..."
          />
          {searchInput ? (
            <button
              type="button"
              className="wards-search-clear"
              onClick={() => setSearchInput("")}
              aria-label="Clear search"
            >
              <X aria-hidden="true" />
            </button>
          ) : null}
        </label>

        <label className="wards-select-field">
          <span>Risk:</span>
          <select value={selectedRisk} onChange={(event) => setSelectedRisk(event.target.value)}>
            <option value="ALL">All</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
          <ChevronDown aria-hidden="true" />
        </label>

        <div className="wards-static-field">
          <span>Scope:</span>
          <strong>{COUNTY_SCOPE} County</strong>
        </div>

        <label className="wards-select-field wards-select-field-subcounty">
          <span>Sub-county:</span>
          <select value={selectedSubCounty} onChange={(event) => setSelectedSubCounty(event.target.value)}>
            {subCounties.map((option) => (
              <option key={option} value={option}>
                {option === "ALL" ? "All" : option}
              </option>
            ))}
          </select>
          <ChevronDown aria-hidden="true" />
        </label>

      </section>

      <div className="wards-filter-actions">
        <button
          type="button"
          className="wards-reset-button"
          onClick={resetFilters}
          disabled={!hasActiveFilters}
        >
          Reset filters
        </button>
      </div>

      <section className="wards-table-panel">
        <div className="wards-table-heading">
          <div>
            <h2>Ward Risk Surveillance List</h2>
            <span className="wards-live-pill">Live</span>
          </div>
          <div className="wards-table-heading-tools">
            <p>Continuously updated</p>
            <label className="wards-sort-field">
              <span>Sort by</span>
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value as SortOption)}>
                <option value="RISK_DESC">Risk score (highest first)</option>
                <option value="RISK_ASC">Risk score (lowest first)</option>
                <option value="UPDATED_DESC">Last updated</option>
                <option value="NAME_ASC">Ward name (A-Z)</option>
              </select>
              <ChevronDown aria-hidden="true" />
            </label>
          </div>
        </div>

        {isLoading ? (
          <>
            <div className="wards-table-wrap">
              <table className="wards-table wards-table-skeleton" aria-hidden="true">
                <thead>
                  <tr>
                    <th>Ward name</th>
                    <th>County</th>
                    <th>Risk level</th>
                    <th>Risk score</th>
                    <th>Last updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: TABLE_SKELETON_ROWS }, (_, index) => (
                    <tr key={`skeleton-${index}`}>
                      <td>
                        <div className="wards-skeleton-name">
                          <span className="wards-skeleton-dot" />
                          <div>
                            <span className="wards-skeleton-line wards-skeleton-line-name" />
                            <span className="wards-skeleton-line wards-skeleton-line-meta" />
                          </div>
                        </div>
                      </td>
                      <td><span className="wards-skeleton-line wards-skeleton-line-cell" /></td>
                      <td><span className="wards-skeleton-pill" /></td>
                      <td>
                        <div className="wards-skeleton-score">
                          <span className="wards-skeleton-line wards-skeleton-line-score" />
                          <span className="wards-skeleton-line wards-skeleton-line-bar" />
                          <span className="wards-skeleton-line wards-skeleton-line-trend" />
                        </div>
                      </td>
                      <td><span className="wards-skeleton-line wards-skeleton-line-cell" /></td>
                      <td><span className="wards-skeleton-line wards-skeleton-line-action" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="wards-table-loading-copy">Loading ward risk summaries...</div>
          </>
        ) : pageItems.length > 0 ? (
          <>
            <div className="wards-table-wrap">
              <table className="wards-table">
                <thead>
                  <tr>
                    <th>Ward name</th>
                    <th>County</th>
                    <th>Risk level</th>
                    <th>Risk score</th>
                    <th>Last updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <div className="wards-name-cell">
                          <span className={`wards-risk-dot wards-risk-dot-${item.riskLevel.toLowerCase()}`} />
                          <div>
                            <strong>{item.name}</strong>
                            <span>{item.subCounty}</span>
                          </div>
                        </div>
                      </td>
                      <td>{item.county}</td>
                      <td>
                        <span className={`risk-pill risk-pill-${item.riskLevel.toLowerCase()}`}>{item.riskLevel}</span>
                      </td>
                      <td>
                        <div className="wards-score-cell">
                          <div className="wards-score-primary">
                            <strong>{formatRiskScore(item.riskScore)}</strong>
                            <span className="wards-score-out-of">/100</span>
                          </div>
                          <div className="wards-score-bar">
                            <span style={{ width: `${normalizeRiskScore(item.riskScore)}%` }} />
                          </div>
                          <div className={`wards-score-trend-row wards-score-trend-${getRiskDeltaTone(item.riskScore)}`}>
                            <span>{getRiskDeltaLabel(item.riskScore)}</span>
                          </div>
                        </div>
                      </td>
                      <td>{formatCompactRelativeMinutes(item.updatedAt)}</td>
                      <td>
                        <Link
                          href={
                            currentListQuery
                              ? `/wards/${item.id}?returnTo=${encodeURIComponent(`${pathname}?${currentListQuery}`)}`
                              : `/wards/${item.id}`
                          }
                          className="wards-detail-link"
                        >
                          View details
                          <ChevronRight aria-hidden="true" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="wards-table-footer">
              <div className="wards-table-footer-copy">
                <span>{pageItems.length} of {filteredItems.length} wards</span>
                <span>Rows per page: {ROWS_PER_PAGE}</span>
              </div>

              <div className="wards-pagination">
                <button
                  type="button"
                  className="wards-pagination-button"
                  disabled={currentPage === 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeft aria-hidden="true" />
                </button>

                {paginationItems.map((pageItem, index) =>
                  pageItem === "..." ? (
                    <span key={`ellipsis-${index}`} className="wards-pagination-ellipsis">
                      ...
                    </span>
                  ) : (
                    <button
                      key={pageItem}
                      type="button"
                      className={`wards-pagination-number${pageItem === currentPage ? " wards-pagination-number-active" : ""}`}
                      onClick={() => setPage(Number(pageItem))}
                    >
                      {pageItem}
                    </button>
                  ),
                )}

                <button
                  type="button"
                  className="wards-pagination-button"
                  disabled={currentPage === totalPages}
                  onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                  aria-label="Next page"
                >
                  <ChevronRight aria-hidden="true" />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="wards-table-empty">
            {getEmptyStateMessage()}
          </div>
        )}
      </section>

      <section className="wards-summary-grid">
        <article className="wards-summary-card">
          <div className="wards-summary-header">
            <span>Critical alert wards</span>
            <ShieldAlert aria-hidden="true" />
          </div>
          <strong>{isLoading ? "..." : String(highRiskItems.length).padStart(2, "0")}</strong>
          <p>{highRiskItems.length > 0 ? `+${Math.max(1, highRiskItems.length - 1)} from yesterday` : "No change from yesterday"}</p>
        </article>

        <article className="wards-summary-card">
          <div className="wards-summary-header">
            <span>Avg. county risk score</span>
            <MapPinned aria-hidden="true" />
          </div>
          <strong>{isLoading ? "..." : `${averageCountyRisk.toFixed(1)}/100`}</strong>
          <p>{averageCountyRisk >= 70 ? "Elevated county risk profile" : "Stable county risk trend"}</p>
        </article>

        <article className="wards-summary-card">
          <div className="wards-summary-header">
            <span>Surveillance coverage</span>
            <TriangleAlert aria-hidden="true" />
          </div>
          <strong>{isLoading ? "..." : `${coverage}%`}</strong>
          <p>{getCoverageLabel(filteredItems.length, items.length)}</p>
        </article>
      </section>
    </div>
  );
}
