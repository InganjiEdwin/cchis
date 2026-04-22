"use client";

import { AlertTriangle, Search, SlidersHorizontal, Stethoscope } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { RoleGate } from "@/components/role-gate";
import { useAuth } from "@/components/auth-provider";
import { fetchChvData, type ChvRecord } from "@/lib/dashboard";

export default function ChvsPage() {
  const { accessToken, currentUser } = useAuth();
  const [chvs, setChvs] = useState<ChvRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedWard, setSelectedWard] = useState("ALL");
  const [selectedStatus, setSelectedStatus] = useState("ALL");

  if (!currentUser) {
    return null;
  }

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    const token = accessToken;
    let isActive = true;

    async function loadChvs() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetchChvData(token);

        if (!isActive) {
          return;
        }

        setChvs(response.results);
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load CHV directory.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadChvs();

    return () => {
      isActive = false;
    };
  }, [accessToken]);

  const wards = useMemo(
    () => ["ALL", ...new Set(chvs.map((item) => item.ward_name).filter(Boolean))],
    [chvs],
  );

  const filteredChvs = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return chvs.filter((item) => {
      if (selectedWard !== "ALL" && item.ward_name !== selectedWard) {
        return false;
      }

      if (selectedStatus === "ACTIVE" && !item.is_active) {
        return false;
      }

      if (selectedStatus === "INACTIVE" && item.is_active) {
        return false;
      }

      if (!normalizedSearch) {
        return true;
      }

      return (
        item.name.toLowerCase().includes(normalizedSearch) ||
        item.phone_number.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [chvs, search, selectedWard, selectedStatus]);

  const activeCount = filteredChvs.filter((item) => item.is_active).length;

  return (
    <PageFrame
      title="CHVs"
      summary="A role-restricted CHV directory for Admin and Supervisor users, focused on field coverage visibility rather than deeper workflow editing."
      role={currentUser.role}
    >
      <RoleGate
        allowedRoles={["ADMIN", "SUPERVISOR"]}
        title="CHV access is role-restricted"
        message="Only Admin and Supervisor roles should use the CHV dashboard surfaces in this frontend shell."
      >
        {error ? (
          <div className="status status-error">
            <AlertTriangle className="section-icon" aria-hidden="true" />
            {error}
          </div>
        ) : null}

        <section className="page-grid metrics-3">
          <article className="card">
            <div className="card-header">
              <Stethoscope className="section-icon" aria-hidden="true" />
              <h3>Visible CHVs</h3>
            </div>
            <p className="metric-value">{isLoading ? "..." : filteredChvs.length}</p>
            <p className="muted">Directory entries currently visible in your backend scope.</p>
          </article>

          <article className="card">
            <div className="card-header">
              <Stethoscope className="section-icon" aria-hidden="true" />
              <h3>Active CHVs</h3>
            </div>
            <p className="metric-value">{isLoading ? "..." : activeCount}</p>
            <p className="muted">Active CHVs in the current filtered directory view.</p>
          </article>

          <article className="card">
            <div className="card-header">
              <Search className="section-icon" aria-hidden="true" />
              <h3>Search scope</h3>
            </div>
            <p className="metric-value">{search.trim() ? `"${search.trim()}"` : "All"}</p>
            <p className="muted">Search applies to CHV names and phone numbers after scope filtering.</p>
          </article>
        </section>

        <section className="page-grid">
          <article className="card">
            <div className="card-header">
              <SlidersHorizontal className="section-icon" aria-hidden="true" />
              <h3>Filters</h3>
            </div>
            <div className="filter-grid filter-grid-3">
              <label className="field">
                <span>Search by name or phone</span>
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search CHV directory"
                />
              </label>

              <label className="field">
                <span>Ward</span>
                <select value={selectedWard} onChange={(event) => setSelectedWard(event.target.value)}>
                  {wards.map((option) => (
                    <option key={option} value={option}>
                      {option === "ALL" ? "All wards" : option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Status</span>
                <select value={selectedStatus} onChange={(event) => setSelectedStatus(event.target.value)}>
                  <option value="ALL">All statuses</option>
                  <option value="ACTIVE">Active</option>
                  <option value="INACTIVE">Inactive</option>
                </select>
              </label>
            </div>
          </article>
        </section>

        <section className="page-grid">
          <article className="card">
            <div className="card-header">
              <Stethoscope className="section-icon" aria-hidden="true" />
              <h3>CHV directory</h3>
            </div>
            {isLoading ? (
              <p className="muted">Loading CHV directory...</p>
            ) : filteredChvs.length > 0 ? (
              <div className="stack">
                {filteredChvs.map((item) => (
                  <div key={item.id} className="summary-row">
                    <div>
                      <strong>{item.name}</strong>
                      <p className="muted compact">
                        {item.phone_number} • {item.ward_name}
                      </p>
                      <p className="muted compact">
                        Language: {item.language || "Not recorded"} • Added {new Date(item.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="summary-row-side stack summary-meta">
                      <span className={`status-pill status-pill-${item.is_active ? "delivered" : "failed"}`}>
                        {item.is_active ? "ACTIVE" : "INACTIVE"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">No CHVs match the current search and filter combination.</p>
            )}
          </article>
        </section>
      </RoleGate>
    </PageFrame>
  );
}
