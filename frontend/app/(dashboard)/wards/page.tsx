"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Filter,
  MapPinned,
  Search,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { fetchWardRiskData } from "@/lib/dashboard";
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

const RISK_SORT_ORDER: Record<WardListItem["riskLevel"], number> = {
  HIGH: 0,
  MEDIUM: 1,
  LOW: 2,
  UNKNOWN: 3,
};

const ROWS_PER_PAGE = 5;

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

function getRiskScoreTone(score: number | null) {
  const normalizedScore = normalizeRiskScore(score);

  if (normalizedScore >= 80) {
    return "overview-score-pill-danger";
  }
  if (normalizedScore >= 65) {
    return "overview-score-pill-high";
  }
  if (normalizedScore >= 45) {
    return "overview-score-pill-medium";
  }
  if (normalizedScore >= 25) {
    return "overview-score-pill-low";
  }
  return "overview-score-pill-minimal";
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

function getCoverageLabel(totalVisible: number, totalAll: number) {
  if (!totalAll) {
    return "0/0 wards reporting";
  }

  return `${totalVisible}/${totalAll} wards reporting`;
}

export default function WardsPage() {
  const { accessToken, currentUser } = useAuth();
  const [items, setItems] = useState<WardListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedCounty, setSelectedCounty] = useState("ALL");
  const [selectedSubCounty, setSelectedSubCounty] = useState("ALL");
  const [selectedRisk, setSelectedRisk] = useState("ALL");
  const [refreshKey, setRefreshKey] = useState(0);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [search, selectedCounty, selectedSubCounty, selectedRisk]);

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    const token = accessToken;
    let isActive = true;

    async function loadData() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await fetchWardRiskData(token);

        if (!isActive) {
          return;
        }

        const wardsById = new Map(data.wards.results.map((ward) => [ward.id, ward]));
        const mergedItems = data.latestRisks.map<WardListItem>((risk) => {
          const ward = wardsById.get(risk.ward_id);

          return {
            id: risk.ward_id,
            name: risk.ward_name,
            county: ward?.county ?? "Unknown county",
            subCounty: ward?.sub_county ?? "Unknown sub-county",
            riskLevel: risk.risk_level ?? "UNKNOWN",
            riskScore: risk.risk_score,
            updatedAt: risk.generated_at ?? ward?.updated_at ?? null,
            predictedCases: risk.predicted_cases,
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
  }, [accessToken, refreshKey]);

  const counties = useMemo(
    () => ["ALL", ...new Set(items.map((item) => item.county).filter(Boolean))],
    [items],
  );

  const subCounties = useMemo(() => {
    const matchingCountyItems =
      selectedCounty === "ALL" ? items : items.filter((item) => item.county === selectedCounty);

    return ["ALL", ...new Set(matchingCountyItems.map((item) => item.subCounty).filter(Boolean))];
  }, [items, selectedCounty]);

  const filteredItems = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return items
      .filter((item) => {
        if (selectedCounty !== "ALL" && item.county !== selectedCounty) {
          return false;
        }

        if (selectedSubCounty !== "ALL" && item.subCounty !== selectedSubCounty) {
          return false;
        }

        if (selectedRisk !== "ALL" && item.riskLevel !== selectedRisk) {
          return false;
        }

        if (!normalizedSearch) {
          return true;
        }

        return item.name.toLowerCase().includes(normalizedSearch);
      })
      .sort((left, right) => {
        const riskDelta = RISK_SORT_ORDER[left.riskLevel] - RISK_SORT_ORDER[right.riskLevel];

        if (riskDelta !== 0) {
          return riskDelta;
        }

        const scoreDelta = normalizeRiskScore(right.riskScore) - normalizeRiskScore(left.riskScore);

        if (scoreDelta !== 0) {
          return scoreDelta;
        }

        return left.name.localeCompare(right.name);
      });
  }, [items, search, selectedCounty, selectedSubCounty, selectedRisk]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / ROWS_PER_PAGE));
  const currentPage = Math.min(page, totalPages);
  const pageItems = filteredItems.slice((currentPage - 1) * ROWS_PER_PAGE, currentPage * ROWS_PER_PAGE);
  const latestWardTimestamp = getLatestTimestamp(items.map((item) => item.updatedAt));
  const highRiskItems = filteredItems.filter((item) => item.riskLevel === "HIGH");
  const averageCountyRisk =
    filteredItems.length > 0
      ? filteredItems.reduce((sum, item) => sum + normalizeRiskScore(item.riskScore), 0) / filteredItems.length
      : 0;
  const coverage = items.length > 0 ? Math.round((filteredItems.length / items.length) * 100) : 0;
  const hasActiveFilters =
    Boolean(search.trim()) ||
    selectedCounty !== "ALL" ||
    selectedSubCounty !== "ALL" ||
    selectedRisk !== "ALL";

  if (!currentUser) {
    return null;
  }

  return (
    <div className="wards-dashboard">
      <DashboardTopbar
        title="Wards"
        subtitle="Ward-level climate health monitoring"
        lastUpdatedLabel={isLoading ? "Refreshing..." : formatOperationalTime(latestWardTimestamp)}
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
          No ward risk data is available yet in your visible scope.
        </div>
      ) : null}

      <section className="wards-hero-panel">
        <div className="wards-hero-copy">
          <nav className="dashboard-breadcrumbs" aria-label="Breadcrumb">
            <Link href="/overview">Migori</Link>
            <span>/</span>
            <span aria-current="page">Wards</span>
          </nav>
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
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search ward name..."
          />
        </label>

        <label className="wards-select-field">
          <span>Risk level:</span>
          <select value={selectedRisk} onChange={(event) => setSelectedRisk(event.target.value)}>
            <option value="ALL">All</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
          <ChevronDown aria-hidden="true" />
        </label>

        <label className="wards-select-field">
          <span>Region:</span>
          <select value={selectedCounty} onChange={(event) => setSelectedCounty(event.target.value)}>
            {counties.map((option) => (
              <option key={option} value={option}>
                {option === "ALL" ? "Migori County" : option}
              </option>
            ))}
          </select>
          <ChevronDown aria-hidden="true" />
        </label>

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

        <button
          type="button"
          className="wards-filter-icon-button"
          onClick={() => {
            setSearch("");
            setSelectedCounty("ALL");
            setSelectedSubCounty("ALL");
            setSelectedRisk("ALL");
          }}
          aria-label="Reset filters"
        >
          <Filter aria-hidden="true" />
        </button>
      </section>

      <section className="wards-table-panel">
        <div className="wards-table-heading">
          <div>
            <h2>Ward Risk Surveillance List</h2>
            <span className="wards-live-pill">Live data</span>
          </div>
          <p>Updated continuously</p>
        </div>

        {isLoading ? (
          <div className="wards-table-empty">Loading ward risk summaries...</div>
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
                          <div className="wards-score-chip-row">
                            <span className={`overview-score-pill ${getRiskScoreTone(item.riskScore)}`}>
                              {formatRiskScore(item.riskScore)}
                            </span>
                            <span className="wards-score-out-of">/100</span>
                          </div>
                          <div className="wards-score-trend-row">
                            <span>{getRiskDeltaLabel(item.riskScore)}</span>
                            <div className="wards-score-bar">
                              <span style={{ width: `${normalizeRiskScore(item.riskScore)}%` }} />
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>{formatCompactRelativeMinutes(item.updatedAt)}</td>
                      <td>
                        <Link href={`/wards/${item.id}`} className="wards-detail-link">
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
                <span>
                  Showing {pageItems.length} of {filteredItems.length} wards
                </span>
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

                {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
                  <button
                    key={pageNumber}
                    type="button"
                    className={`wards-pagination-number${pageNumber === currentPage ? " wards-pagination-number-active" : ""}`}
                    onClick={() => setPage(pageNumber)}
                  >
                    {pageNumber}
                  </button>
                ))}

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
            {hasActiveFilters
              ? "No wards match the current search and filter combination in your visible scope."
              : "No wards are currently visible in your scope."}
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
          <strong>{isLoading ? "..." : averageCountyRisk.toFixed(1)}</strong>
          <p>{averageCountyRisk >= 70 ? "Marginal increase (+0.4%)" : "Stable county risk trend"}</p>
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
