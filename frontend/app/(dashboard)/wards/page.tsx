"use client";

import { AlertTriangle, MapPinned, Search, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { useAuth } from "@/components/auth-provider";
import { fetchWardRiskData } from "@/lib/dashboard";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";

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

export default function WardsPage() {
  const { accessToken, currentUser } = useAuth();
  const [items, setItems] = useState<WardListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedCounty, setSelectedCounty] = useState("ALL");
  const [selectedSubCounty, setSelectedSubCounty] = useState("ALL");
  const [selectedRisk, setSelectedRisk] = useState("ALL");

  if (!currentUser) {
    return null;
  }

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
  }, [accessToken]);

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

        const scoreDelta = (right.riskScore ?? -1) - (left.riskScore ?? -1);

        if (scoreDelta !== 0) {
          return scoreDelta;
        }

        return left.name.localeCompare(right.name);
      });
  }, [items, search, selectedCounty, selectedSubCounty, selectedRisk]);

  const latestWardTimestamp = getLatestTimestamp(items.map((item) => item.updatedAt));
  const wardFreshness = describeFreshness(latestWardTimestamp, 360);
  const hasActiveFilters =
    Boolean(search.trim()) ||
    selectedCounty !== "ALL" ||
    selectedSubCounty !== "ALL" ||
    selectedRisk !== "ALL";

  return (
    <PageFrame
      title="Wards"
      summary="A prioritized ward risk list, filtered by the backend scope model and designed to help operators focus on the highest-risk locations first."
      role={currentUser.role}
    >
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

      {!isLoading && !error && items.length > 0 && wardFreshness.isStale ? (
        <div className="status status-warning">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          Ward risk data may be stale. Latest visible update was {formatRelativeTimestamp(latestWardTimestamp)}.
        </div>
      ) : null}

      <section className="page-grid metrics-3">
        <article className="card">
          <div className="card-header">
            <MapPinned className="section-icon" aria-hidden="true" />
            <h3>Visible wards</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : filteredItems.length}</p>
          <p className="muted">Wards currently visible after role and geography filtering.</p>
        </article>

        <article className="card">
          <div className="card-header">
            <SlidersHorizontal className="section-icon" aria-hidden="true" />
            <h3>High priority</h3>
          </div>
          <p className="metric-value">
            {isLoading ? "..." : filteredItems.filter((item) => item.riskLevel === "HIGH").length}
          </p>
          <p className="muted">High-risk wards in the current filtered list.</p>
        </article>

        <article className="card">
          <div className="card-header">
            <Search className="section-icon" aria-hidden="true" />
            <h3>Freshness</h3>
          </div>
          <p className="metric-value">{isLoading ? "..." : wardFreshness.isStale ? "Stale" : "Current"}</p>
          <p className="muted">
            {isLoading
              ? "Checking latest ward update..."
              : `Latest visible update ${formatRelativeTimestamp(latestWardTimestamp)}`}
          </p>
        </article>
      </section>

      <section className="page-grid">
        <article className="card">
          <div className="card-header">
            <SlidersHorizontal className="section-icon" aria-hidden="true" />
            <h3>Filters</h3>
          </div>
          <div className="filter-grid">
            <label className="field">
              <span>Search by ward</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search ward name"
              />
            </label>

            <label className="field">
              <span>County</span>
              <select value={selectedCounty} onChange={(event) => setSelectedCounty(event.target.value)}>
                {counties.map((option) => (
                  <option key={option} value={option}>
                    {option === "ALL" ? "All counties" : option}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Sub-county</span>
              <select value={selectedSubCounty} onChange={(event) => setSelectedSubCounty(event.target.value)}>
                {subCounties.map((option) => (
                  <option key={option} value={option}>
                    {option === "ALL" ? "All sub-counties" : option}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Risk level</span>
              <select value={selectedRisk} onChange={(event) => setSelectedRisk(event.target.value)}>
                <option value="ALL">All levels</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
                <option value="UNKNOWN">Unknown</option>
              </select>
            </label>
          </div>
        </article>
      </section>

      <section className="page-grid">
        <article className="card">
          <div className="card-header">
            <MapPinned className="section-icon" aria-hidden="true" />
            <h3>Ward risk listing</h3>
          </div>
          {isLoading ? (
            <p className="muted">Loading ward risk summaries...</p>
          ) : filteredItems.length > 0 ? (
            <div className="stack">
              {filteredItems.map((item) => (
                <div key={item.id} className="summary-row">
                  <div>
                    <strong>{item.name}</strong>
                    <p className="muted compact">
                      {item.county}
                      {item.subCounty ? ` • ${item.subCounty}` : ""}
                    </p>
                    <p className="muted compact">
                      Updated: {item.updatedAt ? new Date(item.updatedAt).toLocaleString() : "No timestamp available"}
                    </p>
                    <p className="compact" style={{ marginTop: "0.6rem" }}>
                      <Link href={`/wards/${item.id}`} className="detail-link">
                        Open ward detail
                      </Link>
                    </p>
                  </div>
                  <div className="summary-row-side stack summary-meta">
                    <span className={`risk-pill risk-pill-${item.riskLevel.toLowerCase()}`}>{item.riskLevel}</span>
                    <span className="role-pill">
                      {typeof item.riskScore === "number" ? item.riskScore.toFixed(2) : "N/A"}
                    </span>
                    {item.predictedCases > 0 ? (
                      <span className="muted compact">{item.predictedCases} predicted cases</span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">
              {hasActiveFilters
                ? "No wards match the current search and filter combination in your visible scope."
                : "No wards are currently visible in your scope."}
            </p>
          )}
        </article>
      </section>
    </PageFrame>
  );
}
