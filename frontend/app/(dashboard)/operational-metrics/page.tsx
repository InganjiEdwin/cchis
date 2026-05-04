"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  Building2,
  Clock3,
  DatabaseZap,
  Download,
  Filter,
  Network,
  RefreshCcw,
  ShieldCheck,
  Smartphone,
  Stethoscope,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { downloadOperationalKpiExportFile, fetchOperationalKpiMeExportViaBff } from "@/lib/dashboard";
import type {
  FetchOperationalKpiDashboardParams,
  OperationalInteroperabilityContractsPanel,
  OperationalMetricCard,
  OperationalMetricSourceWarning,
  OperationalMetricStatusTone,
  OperationalMetricThresholdAlert,
  OperationalMetricTrendSeries,
} from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { useOperationalMetricsQuery } from "@/queries/use-operational-metrics-query";

type BadgeTone = "default" | "success" | "warning" | "danger" | "info";

function cleanParam(value: string | null) {
  return value?.trim() || undefined;
}

function paramsFromSearch(searchParams: URLSearchParams): FetchOperationalKpiDashboardParams {
  return {
    date_from: cleanParam(searchParams.get("date_from")),
    date_to: cleanParam(searchParams.get("date_to")),
    ward_id: cleanParam(searchParams.get("ward_id")),
    sub_county: cleanParam(searchParams.get("sub_county")),
    source_channel: cleanParam(searchParams.get("source_channel")),
  };
}

function toneForStatus(tone: OperationalMetricStatusTone): BadgeTone {
  if (tone === "danger") return "danger";
  if (tone === "success") return "success";
  if (tone === "warning") return "warning";
  if (tone === "info") return "info";
  return "default";
}

function formatStatus(status: string) {
  return status
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatGroup(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDelta(metric: OperationalMetricCard) {
  const baseline = metric.baseline.baseline;
  if (!baseline) return "No baseline";
  const sign = baseline.delta > 0 ? "+" : "";
  return `${sign}${baseline.delta.toFixed(metric.value_type === "count" ? 0 : 1)} ${metric.value_unit}`;
}

function latestPoint(series: OperationalMetricTrendSeries) {
  return series.points[series.points.length - 1] ?? null;
}

function MetricTile({ metric, compact = false }: { metric: OperationalMetricCard; compact?: boolean }) {
  return (
    <Card className={cn("grid min-h-[11rem] gap-4 p-4", compact && "min-h-[9rem]")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{formatGroup(metric.metric_group)}</p>
          <h3 className="mt-1 text-base font-semibold leading-snug text-panel-strong">{metric.display_name}</h3>
        </div>
        <StatusBadge tone={toneForStatus(metric.status_tone)}>{formatStatus(metric.status)}</StatusBadge>
      </div>
      <div>
        <p className="text-3xl font-semibold leading-tight text-panel-strong">{metric.display_value}</p>
        <p className="mt-1 text-xs text-panel-muted">
          {metric.snapshot_date ?? "No snapshot"} · {metric.source_record_count} source records
        </p>
      </div>
      <div className="grid gap-2 text-xs text-panel-muted">
        <div className="flex items-center justify-between gap-3 border-t border-[var(--dashboard-table-line)] pt-3">
          <span>Baseline</span>
          <span className="font-semibold text-panel-copy">{formatDelta(metric)}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span>SLA</span>
          <span className="font-semibold text-panel-copy">{metric.sla.label}</span>
        </div>
      </div>
    </Card>
  );
}

function TrendPanel({ title, icon, series }: { title: string; icon: ReactNode; series: OperationalMetricTrendSeries[] }) {
  return (
    <section className="grid gap-4">
      <div className="flex items-center gap-3">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
          {icon}
        </span>
        <h3 className="text-lg font-semibold text-panel-strong">{title}</h3>
      </div>
      <div className="grid gap-3">
        {series.map((item) => {
          const maxValue = Math.max(...item.points.map((point) => point.value ?? 0), 1);
          const last = latestPoint(item);
          return (
            <Card key={item.metric_key} className="p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-panel-strong">{item.display_name}</p>
                  <p className="mt-1 text-xs text-panel-muted">{last?.display_value ?? "No current value"}</p>
                </div>
                <StatusBadge tone={last ? toneForStatus(last.status === "COMPLETE" ? "success" : "warning") : "default"}>
                  {last ? formatStatus(last.status) : "Missing"}
                </StatusBadge>
              </div>
              <div className="mt-4 grid min-h-16 grid-cols-[repeat(auto-fit,minmax(1.4rem,1fr))] items-end gap-2">
                {item.points.length ? (
                  item.points.map((point) => {
                    const height = point.value === null ? 8 : Math.max(8, Math.round(((point.value ?? 0) / maxValue) * 64));
                    return (
                      <div key={`${item.metric_key}-${point.date}`} className="grid gap-1">
                        <div
                          className="rounded-t-md bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_62%,var(--success))]"
                          style={{ height }}
                          title={`${point.date}: ${point.display_value}`}
                        />
                        <span className="truncate text-center text-[0.62rem] text-panel-subtle">
                          {point.date.slice(5)}
                        </span>
                      </div>
                    );
                  })
                ) : (
                  <div className="col-span-full rounded-[1rem] border border-dashed border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-muted">
                    No snapshots in range
                  </div>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

function WarningPanel({ warnings }: { warnings: OperationalMetricSourceWarning[] }) {
  if (!warnings.length) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-3">
          <ShieldCheck className="size-5 text-[color:var(--success)]" />
          <p className="text-sm font-semibold text-panel-strong">No source coverage warnings</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1.2fr_1.6fr_0.8fr] border-b border-[var(--dashboard-table-line)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
        <span>Metric</span>
        <span>Warning</span>
        <span>Status</span>
      </div>
      {warnings.slice(0, 10).map((warning) => (
        <div
          key={`${warning.metric_key}-${warning.warning}-${warning.snapshot_key ?? warning.snapshot_date ?? "audit"}`}
          className="grid grid-cols-[1.2fr_1.6fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0"
        >
          <span className="min-w-0 truncate font-medium text-panel-strong">{warning.metric_key}</span>
          <span className="min-w-0 text-panel-copy">{formatStatus(warning.warning)}</span>
          <span className="text-panel-muted">{formatStatus(warning.status)}</span>
        </div>
      ))}
    </div>
  );
}

function ThresholdAlertPanel({ alerts }: { alerts: OperationalMetricThresholdAlert[] }) {
  if (!alerts.length) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-3">
          <ShieldCheck className="size-5 text-[color:var(--success)]" />
          <p className="text-sm font-semibold text-panel-strong">No active KPI threshold alerts</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[0.8fr_1.3fr_1.5fr] border-b border-[var(--dashboard-table-line)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
        <span>Severity</span>
        <span>Metric</span>
        <span>Attribution</span>
      </div>
      {alerts.slice(0, 10).map((alert) => (
        <div
          key={`${alert.breach_key ?? alert.metric_key}-${alert.breach_type}-${alert.warning_code}`}
          className="grid grid-cols-[0.8fr_1.3fr_1.5fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0"
        >
          <StatusBadge tone={alert.severity === "CRITICAL" ? "danger" : "warning"}>{formatStatus(alert.severity)}</StatusBadge>
          <div className="min-w-0">
            <p className="truncate font-medium text-panel-strong">{alert.display_name}</p>
            <p className="mt-1 text-xs text-panel-muted">{alert.observed_display_value}</p>
          </div>
          <div className="min-w-0 text-panel-copy">
            <p className="truncate">{alert.warning_code ? formatStatus(alert.warning_code) : formatStatus(alert.breach_type)}</p>
            <p className="mt-1 truncate text-xs text-panel-muted">
              {alert.attribution.ward_name || alert.attribution.sub_county || alert.attribution.source_channel || "Global KPI"}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function InteroperabilityContractPanel({ panel }: { panel: OperationalInteroperabilityContractsPanel }) {
  const latestRun = panel.latest_run;

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <Network className="size-5 text-brand" />
          <h3 className="text-lg font-semibold text-panel-strong">Interoperability Contracts</h3>
        </div>
        <StatusBadge tone={panel.audit_status === "pass" ? "success" : "warning"}>
          {formatStatus(panel.audit_status)}
        </StatusBadge>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-[1rem] border border-[var(--dashboard-table-line)] px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Coverage</p>
          <p className="mt-1 text-2xl font-semibold text-panel-strong">
            {panel.latest_mapping_coverage === null ? "None" : `${panel.latest_mapping_coverage.toFixed(1)}%`}
          </p>
        </div>
        <div className="rounded-[1rem] border border-[var(--dashboard-table-line)] px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Mappings</p>
          <p className="mt-1 text-2xl font-semibold text-panel-strong">{panel.active_org_unit_mapping_count}</p>
        </div>
        <div className="rounded-[1rem] border border-[var(--dashboard-table-line)] px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Failed Runs</p>
          <p className="mt-1 text-2xl font-semibold text-panel-strong">{panel.failed_run_count}</p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 text-sm">
        <p className="text-panel-muted">
          {latestRun
            ? `${formatGroup(latestRun.exchange_type)} · ${formatStatus(latestRun.status)} · ${latestRun.records_accepted}/${latestRun.records_seen} accepted`
            : "No interoperability runs have been recorded."}
        </p>
        {panel.audit_failures.slice(0, 4).map((failure) => (
          <div key={failure.key} className="rounded-[0.75rem] border border-[var(--dashboard-table-line)] px-3 py-2">
            <p className="font-semibold text-panel-strong">{failure.title}</p>
            <p className="mt-1 text-xs text-panel-muted">{failure.summary}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function OperationalMetricsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => paramsFromSearch(searchParams), [searchParams]);
  const { data, isPending, error, refetch, isFetching } = useOperationalMetricsQuery(filters);
  const [draftFilters, setDraftFilters] = useState(filters);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const lastUpdatedLabel = data?.generated_at ? formatRelativeTimestamp(data.generated_at) : "No dashboard snapshot";

  useEffect(() => {
    setDraftFilters(filters);
  }, [filters]);

  function updateDraft(key: keyof FetchOperationalKpiDashboardParams, value: string) {
    setDraftFilters((current) => ({ ...current, [key]: value || undefined }));
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(draftFilters)) {
      if (value !== undefined && value !== "") {
        params.set(key, String(value));
      }
    }
    router.push(`/operational-metrics${params.size ? `?${params.toString()}` : ""}`);
  }

  function resetFilters() {
    setDraftFilters({});
    router.push("/operational-metrics");
  }

  async function exportCsv() {
    setIsExporting(true);
    setExportError(null);
    try {
      const exportPayload = await fetchOperationalKpiMeExportViaBff({ ...filters, export_format: "csv" });
      downloadOperationalKpiExportFile(exportPayload);
    } catch (exportFailure) {
      setExportError(exportFailure instanceof Error ? exportFailure.message : "Unable to export operational KPI report.");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <RoleGate
      allowedRoles={["ADMIN", "SUPERVISOR", "ANALYST"]}
      title="Operational KPI dashboard unavailable"
      message="Your role cannot view operational monitoring metrics."
    >
      <div className="space-y-8">
        <DashboardTopbar
          title="Operational KPIs"
          subtitle="Alert delivery, response action, adoption, facility, USSD, and source health."
          lastUpdatedLabel={lastUpdatedLabel}
          lastUpdatedTone={data?.summary.operational_health === "pass" ? "default" : "stale"}
          onRefresh={() => refetch()}
        />

        <PageSectionHeader
          title="M&E Dashboard"
          description="Operational performance is shown separately from prediction model artifacts."
          actions={
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" onClick={exportCsv} disabled={isExporting}>
                <Download className={cn("mr-2 size-4", isExporting && "animate-pulse")} />
                Export CSV
              </Button>
              <Button type="button" variant="secondary" onClick={() => refetch()} disabled={isFetching}>
                <RefreshCcw className={cn("mr-2 size-4", isFetching && "animate-spin")} />
                Refresh
              </Button>
            </div>
          }
        />

        <form
          onSubmit={applyFilters}
          className="grid gap-3 rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] p-4 lg:grid-cols-[repeat(5,minmax(0,1fr))_auto]"
        >
          <InputShell
            label="From"
            type="date"
            value={draftFilters.date_from ?? ""}
            onChange={(event) => updateDraft("date_from", event.target.value)}
          />
          <InputShell
            label="To"
            type="date"
            value={draftFilters.date_to ?? ""}
            onChange={(event) => updateDraft("date_to", event.target.value)}
          />
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-medium text-panel-copy">Ward</span>
            <select
              className="h-10 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
              value={draftFilters.ward_id ?? ""}
              onChange={(event) => updateDraft("ward_id", event.target.value)}
            >
              <option value="">All wards</option>
              {data?.available_filters.wards.map((ward) => (
                <option key={ward.id} value={ward.id}>
                  {ward.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-medium text-panel-copy">Sub-county</span>
            <select
              className="h-10 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
              value={draftFilters.sub_county ?? ""}
              onChange={(event) => updateDraft("sub_county", event.target.value)}
            >
              <option value="">All sub-counties</option>
              {data?.available_filters.sub_counties.map((subCounty) => (
                <option key={subCounty} value={subCounty}>
                  {subCounty}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-medium text-panel-copy">Channel</span>
            <select
              className="h-10 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
              value={draftFilters.source_channel ?? ""}
              onChange={(event) => updateDraft("source_channel", event.target.value)}
            >
              <option value="">All channels</option>
              {data?.available_filters.source_channels.map((channel) => (
                <option key={channel} value={channel}>
                  {channel}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <Button type="submit">
              <Filter className="mr-2 size-4" />
              Apply
            </Button>
            <Button type="button" variant="secondary" onClick={resetFilters}>
              Reset
            </Button>
          </div>
        </form>

        {error ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 text-[color:var(--danger)]" />
              <div>
                <p className="font-semibold text-panel-strong">Unable to load operational KPIs</p>
                <p className="mt-1 text-sm text-panel-muted">{error.message}</p>
              </div>
            </div>
          </Card>
        ) : null}

        {exportError ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 text-[color:var(--danger)]" />
              <div>
                <p className="font-semibold text-panel-strong">Unable to export operational KPIs</p>
                <p className="mt-1 text-sm text-panel-muted">{exportError}</p>
              </div>
            </div>
          </Card>
        ) : null}

        {isPending ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, index) => (
              <div
                key={index}
                className="h-44 animate-pulse rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)]"
              />
            ))}
          </div>
        ) : data ? (
          <>
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              <Card className="p-4">
                <BarChart3 className="size-5 text-brand" />
                <p className="mt-3 text-2xl font-semibold text-panel-strong">{data.summary.metric_count}</p>
                <p className="text-sm text-panel-muted">Metric definitions</p>
              </Card>
              <Card className="p-4">
                <Activity className="size-5 text-brand" />
                <p className="mt-3 text-2xl font-semibold text-panel-strong">{data.summary.snapshot_count}</p>
                <p className="text-sm text-panel-muted">Snapshots in range</p>
              </Card>
              <Card className="p-4">
                <ShieldCheck className="size-5 text-[color:var(--success)]" />
                <p className="mt-3 text-2xl font-semibold text-panel-strong">{data.summary.complete_metric_count}</p>
                <p className="text-sm text-panel-muted">Complete current KPIs</p>
              </Card>
              <Card className="p-4">
                <AlertTriangle className="size-5 text-[color:var(--warning)]" />
                <p className="mt-3 text-2xl font-semibold text-panel-strong">{data.summary.warning_count}</p>
                <p className="text-sm text-panel-muted">Coverage warnings</p>
              </Card>
              <Card className="p-4">
                <AlertTriangle className="size-5 text-[color:var(--danger)]" />
                <p className="mt-3 text-2xl font-semibold text-panel-strong">{data.summary.threshold_alert_count}</p>
                <p className="text-sm text-panel-muted">Threshold alerts</p>
              </Card>
              <Card className="p-4">
                <DatabaseZap className="size-5 text-brand" />
                <p className="mt-3 text-2xl font-semibold text-panel-strong">{data.summary.latest_snapshot_date ?? "None"}</p>
                <p className="text-sm text-panel-muted">Latest KPI window</p>
              </Card>
            </section>

            <section className="grid gap-4">
              <div className="flex items-center gap-3">
                <Clock3 className="size-5 text-brand" />
                <h3 className="text-lg font-semibold text-panel-strong">Operational Overview</h3>
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                {data.panels.operational_overview.map((metric) => (
                  <MetricTile key={metric.metric_key} metric={metric} />
                ))}
              </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
              <div className="grid gap-4">
                <div className="flex items-center gap-3">
                  <ShieldCheck className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">SLA Panel</h3>
                </div>
                <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-1">
                  {data.panels.sla.map((metric) => (
                    <MetricTile key={metric.metric_key} metric={metric} compact />
                  ))}
                </div>
              </div>
              <div className="grid gap-4">
                <div className="flex items-center gap-3">
                  <Stethoscope className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">Adoption And Coverage</h3>
                </div>
                <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-1">
                  {data.panels.adoption_coverage.map((metric) => (
                    <MetricTile key={metric.metric_key} metric={metric} compact />
                  ))}
                </div>
              </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-3">
              <TrendPanel title="Response-Time Trends" icon={<Clock3 className="size-5" />} series={data.panels.response_time_trends} />
              <TrendPanel title="Facility Preparedness Trends" icon={<Building2 className="size-5" />} series={data.panels.facility_preparedness_trends} />
              <TrendPanel title="USSD Completion Trends" icon={<Smartphone className="size-5" />} series={data.panels.ussd_completion_trends} />
            </section>

            <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
              <section className="grid gap-4">
                <div className="flex items-center gap-3">
                  <AlertTriangle className="size-5 text-[color:var(--danger)]" />
                  <h3 className="text-lg font-semibold text-panel-strong">Threshold Alerts</h3>
                </div>
                <ThresholdAlertPanel alerts={data.panels.threshold_alerts} />
              </section>
              <section className="grid gap-4">
                <div className="flex items-center gap-3">
                  <AlertTriangle className="size-5 text-[color:var(--warning)]" />
                  <h3 className="text-lg font-semibold text-panel-strong">Source Coverage Warnings</h3>
                </div>
                <WarningPanel warnings={data.panels.source_coverage_warnings} />
              </section>
            </section>

            <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
              <InteroperabilityContractPanel panel={data.panels.interoperability_contracts} />
              <Card className="p-5">
                <div className="flex items-center gap-3">
                  <BarChart3 className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">Model Versus Operations</h3>
                </div>
                <div className="mt-5 grid gap-4 text-sm">
                  <div className="rounded-[1rem] border border-[var(--dashboard-table-line)] px-4 py-3">
                    <p className="font-semibold text-panel-strong">Operational KPI family</p>
                    <p className="mt-1 text-panel-muted">{data.panels.model_vs_operations.operational_metric_family}</p>
                  </div>
                  <div className="rounded-[1rem] border border-[var(--dashboard-table-line)] px-4 py-3">
                    <p className="font-semibold text-panel-strong">Latest model run</p>
                    <p className="mt-1 text-panel-muted">
                      {data.panels.model_vs_operations.latest_model_run.model_version ?? "No model run"} ·{" "}
                      {data.panels.model_vs_operations.latest_model_run.status ?? "Unavailable"}
                    </p>
                  </div>
                  <p className="text-sm leading-6 text-panel-muted">{data.panels.model_vs_operations.separation_statement}</p>
                </div>
              </Card>
            </section>
          </>
        ) : null}
      </div>
    </RoleGate>
  );
}
