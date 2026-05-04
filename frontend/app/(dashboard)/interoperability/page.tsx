"use client";

import {
  AlertTriangle,
  ClipboardList,
  DatabaseZap,
  Download,
  Eye,
  FileWarning,
  ListChecks,
  Network,
  Play,
  RefreshCcw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import type { InteroperabilityDashboardResponse, InteroperabilityRunRecord } from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import {
  useInteroperabilityDashboardQuery,
  useInteroperabilityExportPreviewMutation,
  useInteroperabilityOrgUnitMappingImportMutation,
  useInteroperabilityRunDetailMutation,
  useInteroperabilityRetryMutation,
} from "@/queries/use-interoperability-query";

const DEFAULT_MAPPING_CSV =
  "external_identifier,external_display_name,internal_object_type,internal_object_public_id,internal_object_code,mapping_confidence,status\n";

type OrgUnitMappingRecord = InteroperabilityDashboardResponse["org_unit_mappings"][number];
type ReviewItemRecord = InteroperabilityRunRecord["items"][number];

function formatLabel(value: string) {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function recordText(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (value === null || value === undefined) return "";
  return String(value);
}

function formatPreviewValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(1);
  if (Array.isArray(value)) return value.map(formatPreviewValue).filter(Boolean).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .slice(0, 4)
      .map(([key, entryValue]) => `${formatLabel(key)}: ${formatPreviewValue(entryValue)}`)
      .join(" · ");
  }
  return String(value).includes("_") ? formatLabel(String(value)) : String(value);
}

function previewRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  return {};
}

function formatConfidence(value: number) {
  const percent = value <= 1 ? value * 100 : value;
  return `${percent.toFixed(0)}%`;
}

function statusTone(status: string): "default" | "success" | "warning" | "danger" | "info" {
  if (["COMPLETED", "READY_FOR_CONFIRMATION", "PASS", "ACTIVE"].includes(status)) return "success";
  if (["PARTIAL", "NEEDS_REVIEW", "DRAFT"].includes(status)) return "warning";
  if (["FAILED", "FAIL", "REJECTED"].includes(status)) return "danger";
  if (["RETRY_CREATED"].includes(status)) return "info";
  return "default";
}

function SummaryTile({ label, value }: { label: string; value: string | number }) {
  return (
    <Card className="grid min-h-28 gap-2 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
      <p className="text-3xl font-semibold text-panel-strong">{value}</p>
    </Card>
  );
}

function InlineMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
      <p className="mt-1 text-sm font-semibold text-panel-strong">{value}</p>
    </div>
  );
}

function MappingCompletenessPanel({
  data,
  failingChecks,
}: {
  data: InteroperabilityDashboardResponse | undefined;
  failingChecks: InteroperabilityDashboardResponse["audit_checks"];
}) {
  const mappingVersions = data?.mapping_versions ?? [];
  const activeVersions = mappingVersions.filter((version) => recordText(version, "status") === "ACTIVE");
  const orgMappings = data?.org_unit_mappings ?? [];
  const activeMappings = orgMappings.filter((mapping) => mapping.status === "ACTIVE" && !mapping.retired_date);
  const totalContractErrors = [
    ...(data?.exchange_inventory_contract_errors ?? []),
    ...(data?.csv_template_contract_errors ?? []),
    ...(data?.connector_boundary_contract_errors ?? []),
  ].length;

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Network className="size-5 text-brand" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-panel-strong">Mapping Completeness</h2>
        </div>
        <StatusBadge tone={failingChecks.length || totalContractErrors ? "danger" : "success"}>
          {failingChecks.length || totalContractErrors ? "Action" : "Clear"}
        </StatusBadge>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <InlineMetric label="Active Versions" value={`${activeVersions.length}/${mappingVersions.length}`} />
        <InlineMetric label="Active Org Mappings" value={`${activeMappings.length}/${orgMappings.length}`} />
        <InlineMetric label="Failed Checks" value={failingChecks.length} />
        <InlineMetric label="Contract Errors" value={totalContractErrors} />
      </div>

      <div className="mt-4 grid gap-3">
        {(data?.audit_checks ?? []).map((check) => (
          <div
            key={check.key}
            className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 md:grid-cols-[1fr_auto] md:items-center"
          >
            <div>
              <p className="text-sm font-semibold text-panel-strong">{check.title}</p>
              <p className="mt-1 text-xs text-panel-muted">{check.summary}</p>
            </div>
            <StatusBadge tone={statusTone(check.status)}>{check.count}</StatusBadge>
          </div>
        ))}
        {!data?.audit_checks.length ? <p className="text-sm text-panel-muted">No audit checks returned.</p> : null}
      </div>

      <div className="mt-5">
        <div className="mb-3 flex items-center gap-2">
          <ListChecks className="size-4 text-brand" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-panel-strong">Recent Mapping Records</h3>
        </div>
        <div className="grid gap-2">
          {orgMappings.slice(0, 6).map((mapping) => (
            <MappingRecordRow key={mapping.public_id} mapping={mapping} />
          ))}
          {!orgMappings.length ? <p className="text-sm text-panel-muted">No mapping records returned.</p> : null}
        </div>
      </div>
    </Card>
  );
}

function MappingRecordRow({ mapping }: { mapping: OrgUnitMappingRecord }) {
  const internalName = mapping.ward_name || mapping.facility_name || mapping.internal_object_code || "Unresolved target";
  return (
    <div className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 md:grid-cols-[1fr_auto] md:items-center">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-panel-strong">
          {mapping.external_identifier} -&gt; {internalName}
        </p>
        <p className="mt-1 text-xs text-panel-muted">
          {formatLabel(mapping.internal_object_type)} · {mapping.mapping_version} · {formatConfidence(mapping.mapping_confidence)}
        </p>
      </div>
      <StatusBadge tone={statusTone(mapping.status)}>{formatLabel(mapping.status)}</StatusBadge>
    </div>
  );
}

function DryRunPreviewPanel({ run }: { run: InteroperabilityRunRecord }) {
  const preview = previewRecord(run.dry_run_preview);
  const coverageReport = previewRecord(preview.mapping_coverage_report);
  const sourceTrace = Array.isArray(preview.source_trace) ? preview.source_trace : [];
  const previewRows = [
    { label: "Confirmable", value: preview.confirmable },
    { label: "Operator Confirmation", value: preview.operator_confirmation_required },
    { label: "Mutation Performed", value: preview.mutation_performed },
    { label: "Next Action", value: preview.next_action },
    { label: "Missing Fields", value: preview.missing_required_fields ?? preview.missing_columns },
    { label: "Coverage Report", value: coverageReport },
  ].filter((row) => formatPreviewValue(row.value));

  return (
    <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
      <div className="mb-3 flex items-center gap-2">
        <Eye className="size-4 text-brand" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-panel-strong">Dry-Run Preview</h3>
      </div>
      {previewRows.length ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {previewRows.map((row) => (
            <InlineMetric key={row.label} label={row.label} value={formatPreviewValue(row.value)} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-panel-muted">No dry-run preview details on this run.</p>
      )}
      {sourceTrace.length ? (
        <div className="mt-3 text-xs text-panel-muted">
          Source trace: {sourceTrace.slice(0, 4).map(formatPreviewValue).join(" · ")}
        </div>
      ) : null}
    </div>
  );
}

function ReviewItemCard({ item }: { item: ReviewItemRecord }) {
  const contextEntries = Object.entries(item.safe_context ?? {})
    .filter(([, value]) => formatPreviewValue(value))
    .slice(0, 6);
  return (
    <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-semibold text-panel-strong">{item.external_identifier || "Unmapped record"}</p>
        <StatusBadge tone={statusTone(item.status)}>{formatLabel(item.status)}</StatusBadge>
      </div>
      <p className="mt-1 text-xs text-panel-muted">
        {item.source_record_ref || "No source reference"} · {item.internal_object_code || item.internal_object_public_id || "No internal match"}
      </p>
      {contextEntries.length ? (
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          {contextEntries.map(([key, value]) => (
            <div key={key}>
              <dt className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-muted">
                {formatLabel(key)}
              </dt>
              <dd className="mt-1 text-xs text-panel-copy">{formatPreviewValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

function RunRow({
  run,
  onRetry,
  onReview,
  isRetrying,
}: {
  run: InteroperabilityRunRecord;
  onRetry: (publicId: string) => void;
  onReview: (run: InteroperabilityRunRecord) => void | Promise<void>;
  isRetrying: boolean;
}) {
  const canRetry = run.status === "FAILED" || run.status === "PARTIAL";
  return (
    <div className="grid gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-4 last:border-b-0 lg:grid-cols-[1.1fr_0.65fr_0.45fr_0.65fr_0.65fr_auto_auto_auto] lg:items-center">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-panel-strong">{formatLabel(run.exchange_type)}</p>
        <p className="mt-1 text-xs text-panel-muted">{run.system_name || run.system_key} · {formatRelativeTimestamp(run.started_at)}</p>
      </div>
      <StatusBadge tone={statusTone(run.status)}>{formatLabel(run.status)}</StatusBadge>
      <p className="text-sm text-panel-copy">{run.direction}</p>
      <p className="text-sm text-panel-copy">{run.records_accepted}/{run.records_seen} accepted</p>
      <p className="text-sm text-panel-copy">{run.mapping_coverage.toFixed(1)}% mapped</p>
      <Button size="sm" variant="secondary" onClick={() => void onReview(run)}>
        <FileWarning className="size-4" aria-hidden="true" />
        Review
      </Button>
      {canRetry ? (
        <Button
          size="sm"
          variant="secondary"
          disabled={isRetrying}
          onClick={() => onRetry(run.public_id)}
        >
          <RefreshCcw className="size-4" aria-hidden="true" />
          Retry
        </Button>
      ) : (
        <StatusBadge tone="default">No retry</StatusBadge>
      )}
      {run.errors.length ? (
        <a
          className="inline-flex h-9 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-medium text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
          href={`/api/dashboard/interoperability/runs/${encodeURIComponent(run.public_id)}/errors.csv`}
        >
          <Download className="size-4" aria-hidden="true" />
          Errors CSV
        </a>
      ) : (
        <StatusBadge tone="default">No errors</StatusBadge>
      )}
      {run.error_summary ? <p className="text-sm text-[color:var(--danger)] lg:col-span-8">{run.error_summary}</p> : null}
    </div>
  );
}

export default function InteroperabilityPage() {
  const { data, isLoading, error, refetch, isFetching } = useInteroperabilityDashboardQuery();
  const importMutation = useInteroperabilityOrgUnitMappingImportMutation();
  const exportPreviewMutation = useInteroperabilityExportPreviewMutation();
  const runDetailMutation = useInteroperabilityRunDetailMutation();
  const retryMutation = useInteroperabilityRetryMutation();
  const [csvText, setCsvText] = useState(DEFAULT_MAPPING_CSV);
  const [confirmImport, setConfirmImport] = useState(false);
  const [mappingVersionLabel, setMappingVersionLabel] = useState("");
  const [lastRunResult, setLastRunResult] = useState<InteroperabilityRunRecord | null>(null);
  const [selectedRun, setSelectedRun] = useState<InteroperabilityRunRecord | null>(null);
  const latestRun = data?.runs[0] ?? null;
  const reviewRun = lastRunResult ?? selectedRun ?? latestRun;
  const reviewItems = (reviewRun?.items ?? []).filter((item) => item.status !== "ACCEPTED");
  const failingChecks = useMemo(
    () => data?.audit_checks.filter((check) => check.status === "FAIL") ?? [],
    [data?.audit_checks],
  );

  async function handleDryRunSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const confirmablePriorRun =
      confirmImport &&
      lastRunResult?.direction === "IMPORT" &&
      lastRunResult.status === "READY_FOR_CONFIRMATION"
        ? lastRunResult.public_id
        : null;
    const run = await importMutation.mutateAsync({
      system_key: "dhis2",
      mapping_version_label: mappingVersionLabel,
      source_file_name: "org-unit-mapping.csv",
      csv_text: csvText,
      confirm: confirmImport,
      retry_of_public_id: confirmablePriorRun,
    });
    setLastRunResult(run);
  }

  async function handleExportPreview() {
    const run = await exportPreviewMutation.mutateAsync({
      system_key: "dhis2",
      mapping_version_label: mappingVersionLabel,
    });
    setLastRunResult(run);
  }

  async function handleRetry(publicId: string) {
    const run = await retryMutation.mutateAsync(publicId);
    setLastRunResult(run);
    setSelectedRun(null);
  }

  async function handleReview(run: InteroperabilityRunRecord) {
    setSelectedRun(run);
    setLastRunResult(null);
    try {
      const detailedRun = await runDetailMutation.mutateAsync(run.public_id);
      setSelectedRun(detailedRun);
    } catch {
      // Keep the dashboard snapshot visible; row-level CSV export still carries the full error ledger.
    }
  }

  return (
    <RoleGate
      allowedRoles={["ADMIN", "SUPERVISOR", "ANALYST"]}
      title="Interoperability access required"
      message="Import/export exchange review is available to dashboard operators."
    >
      <div className="grid gap-6">
        <DashboardTopbar
          title="Interoperability"
          subtitle="CSV-first mappings, exchange runs, and connector readiness"
          lastUpdatedLabel={data?.generated_at ? `Updated ${formatRelativeTimestamp(data.generated_at)}` : "Not loaded"}
          lastUpdatedTone={data?.summary.audit_status === "fail" ? "stale" : "default"}
          onRefresh={() => void refetch()}
        >
          <Button size="sm" variant="secondary" onClick={handleExportPreview} disabled={exportPreviewMutation.isPending}>
            <Play className="size-4" aria-hidden="true" />
            Export preview
          </Button>
        </DashboardTopbar>

        {error ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_30%,white)] p-4 text-sm font-semibold text-[color:var(--danger)]">
            {(error as Error).message}
          </Card>
        ) : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <SummaryTile label="Systems" value={data?.summary.active_system_count ?? 0} />
          <SummaryTile label="Mappings" value={data?.summary.active_org_unit_mapping_count ?? 0} />
          <SummaryTile label="Runs" value={data?.summary.run_count ?? 0} />
          <SummaryTile label="Failures" value={data?.summary.failed_run_count ?? 0} />
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <MappingCompletenessPanel data={data} failingChecks={failingChecks} />

          <Card className="p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <FileWarning className="size-5 text-brand" aria-hidden="true" />
                <h2 className="text-lg font-semibold text-panel-strong">CSV Dry-Run</h2>
              </div>
              <a
                className="inline-flex h-9 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-medium text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
                href="/api/dashboard/interoperability/csv-templates/ward_org_unit_mapping_import"
              >
                <Download className="size-4" aria-hidden="true" />
                Template CSV
              </a>
            </div>
            <form className="grid gap-3" onSubmit={(event) => void handleDryRunSubmit(event)}>
              <input
                aria-label="Mapping version label"
                value={mappingVersionLabel}
                onChange={(event) => setMappingVersionLabel(event.target.value)}
                className="h-11 rounded-[0.5rem] border border-[var(--dashboard-table-line)] bg-panel px-3 text-sm text-panel-strong outline-none focus:border-brand"
                placeholder="Mapping version label"
              />
              <textarea
                aria-label="Org unit mapping CSV"
                value={csvText}
                onChange={(event) => setCsvText(event.target.value)}
                rows={7}
                className="min-h-40 rounded-[0.5rem] border border-[var(--dashboard-table-line)] bg-panel px-3 py-2 font-mono text-xs text-panel-strong outline-none focus:border-brand"
              />
              <label className="flex items-center gap-2 text-sm font-medium text-panel-copy">
                <input
                  type="checkbox"
                  checked={confirmImport}
                  onChange={(event) => setConfirmImport(event.target.checked)}
                  className="size-4 rounded border-[var(--dashboard-table-line)]"
                />
                Confirm import
              </label>
              <Button type="submit" disabled={importMutation.isPending}>
                <Upload className="size-4" aria-hidden="true" />
                {confirmImport ? "Confirm" : "Dry-run"}
              </Button>
            </form>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--dashboard-table-line)] px-4 py-3">
              <div className="flex items-center gap-3">
                <DatabaseZap className="size-5 text-brand" aria-hidden="true" />
                <h2 className="text-lg font-semibold text-panel-strong">Run History</h2>
              </div>
              {isFetching ? <StatusBadge tone="info">Refreshing</StatusBadge> : null}
            </div>
            <div>
              {(data?.runs ?? []).map((run) => (
                <RunRow
                  key={run.public_id}
                  run={run}
                  onRetry={handleRetry}
                  onReview={handleReview}
                  isRetrying={retryMutation.isPending}
                />
              ))}
              {!data?.runs.length && !isLoading ? (
                <div className="px-4 py-6 text-sm text-panel-muted">No interoperability runs.</div>
              ) : null}
            </div>
          </Card>

          <Card className="p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                {reviewRun?.errors?.length ? (
                  <AlertTriangle className="size-5 text-[color:var(--warning)]" aria-hidden="true" />
                ) : (
                  <ShieldCheck className="size-5 text-[color:var(--success)]" aria-hidden="true" />
                )}
                <h2 className="text-lg font-semibold text-panel-strong">Run Detail</h2>
              </div>
              {runDetailMutation.isPending ? <StatusBadge tone="info">Loading detail</StatusBadge> : null}
              {runDetailMutation.error ? <StatusBadge tone="warning">Snapshot shown</StatusBadge> : null}
            </div>
            {reviewRun ? (
              <div className="grid gap-3">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge tone={statusTone(reviewRun.status)}>{formatLabel(reviewRun.status)}</StatusBadge>
                  <span className="text-sm text-panel-muted">{formatLabel(reviewRun.exchange_type)}</span>
                  <span className="text-sm text-panel-muted">{reviewRun.direction}</span>
                  <span className="text-sm text-panel-muted">{reviewRun.records_rejected} rejected</span>
                  <span className="text-sm text-panel-muted">{reviewRun.mapping_coverage.toFixed(1)}% coverage</span>
                </div>

                <div className="grid gap-2 sm:grid-cols-2">
                  <InlineMetric label="Source" value={reviewRun.source_reference || "No source reference"} />
                  <InlineMetric label="Operator" value={reviewRun.operator_username || "System"} />
                  <InlineMetric label="Started" value={formatRelativeTimestamp(reviewRun.started_at)} />
                  <InlineMetric
                    label="Completed"
                    value={reviewRun.completed_at ? formatRelativeTimestamp(reviewRun.completed_at) : "Open"}
                  />
                  <InlineMetric label="Accepted" value={reviewRun.records_accepted} />
                  <InlineMetric label="Rejected" value={reviewRun.records_rejected} />
                  {reviewRun.retry_of ? <InlineMetric label="Retry Of" value={reviewRun.retry_of} /> : null}
                  {reviewRun.contract_errors.length ? (
                    <InlineMetric label="Contract Errors" value={reviewRun.contract_errors.join(", ")} />
                  ) : null}
                </div>

                <DryRunPreviewPanel run={reviewRun} />

                <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <FileWarning className="size-4 text-brand" aria-hidden="true" />
                      <h3 className="text-sm font-semibold text-panel-strong">Error Review</h3>
                    </div>
                    {reviewRun.errors.length ? (
                      <a
                        className="inline-flex h-8 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-xs font-medium text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
                        href={`/api/dashboard/interoperability/runs/${encodeURIComponent(reviewRun.public_id)}/errors.csv`}
                      >
                        <Download className="size-3.5" aria-hidden="true" />
                        Errors CSV
                      </a>
                    ) : null}
                  </div>
                  <div className="grid gap-2">
                    {reviewRun.errors.slice(0, 8).map((item) => (
                      <div key={item.public_id} className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
                        <p className="text-sm font-semibold text-panel-strong">{formatLabel(item.error_code)}</p>
                        <p className="mt-1 text-xs text-panel-muted">{item.safe_message}</p>
                        {item.remediation_hint ? (
                          <p className="mt-2 text-xs font-medium text-panel-copy">{item.remediation_hint}</p>
                        ) : null}
                        {item.field_path ? <p className="mt-2 text-xs text-panel-muted">Field: {item.field_path}</p> : null}
                      </div>
                    ))}
                    {!reviewRun.errors.length ? <p className="text-sm text-panel-muted">No error records on this run.</p> : null}
                  </div>
                </div>

                <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
                  <div className="mb-3 flex items-center gap-2">
                    <ClipboardList className="size-4 text-brand" aria-hidden="true" />
                    <h3 className="text-sm font-semibold text-panel-strong">Unmapped Record Review</h3>
                  </div>
                  <div className="grid gap-2">
                    {reviewItems.slice(0, 8).map((item) => (
                      <ReviewItemCard key={item.id} item={item} />
                    ))}
                    {!reviewItems.length ? <p className="text-sm text-panel-muted">No review errors on this run.</p> : null}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-panel-muted">No latest run.</p>
            )}
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <Card className="p-5">
            <h2 className="text-lg font-semibold text-panel-strong">Exchange Inventory</h2>
            <div className="mt-4 grid gap-3">
              {(data?.exchange_inventory ?? []).map((item) => (
                <div key={item.exchange_type} className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-panel-strong">{item.label}</p>
                    <StatusBadge tone={item.direction === "IMPORT" ? "info" : "default"}>{item.direction}</StatusBadge>
                  </div>
                  <p className="text-xs text-panel-muted">{item.source_owner} · {item.format} · {item.cadence}</p>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-lg font-semibold text-panel-strong">Connector Boundary</h2>
            <div className="mt-4 grid gap-3">
              {(data?.connector_boundary.failure_taxonomy ?? []).slice(0, 8).map((failure) => (
                <div key={failure} className="flex items-center justify-between rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2">
                  <span className="text-sm text-panel-copy">{formatLabel(failure)}</span>
                  <StatusBadge tone="default">Taxonomy</StatusBadge>
                </div>
              ))}
            </div>
          </Card>
        </section>
      </div>
    </RoleGate>
  );
}
