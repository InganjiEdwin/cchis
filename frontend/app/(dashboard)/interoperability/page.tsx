"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  ClipboardList,
  Download,
  Eye,
  FileSpreadsheet,
  FileWarning,
  History,
  Link2,
  ListChecks,
  Play,
  RefreshCcw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { hasActionCapability } from "@/lib/capabilities";
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
const TEMPLATE_URL = "/api/dashboard/interoperability/csv-templates/ward_org_unit_mapping_import";

type BadgeTone = "default" | "success" | "warning" | "danger" | "info";
type OrgUnitMappingRecord = InteroperabilityDashboardResponse["org_unit_mappings"][number];
type ReviewItemRecord = InteroperabilityRunRecord["items"][number];

function PlainBadge({
  tone = "default",
  children,
  className,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <StatusBadge tone={tone} className={cn("normal-case tracking-normal", className)}>
      {children}
    </StatusBadge>
  );
}

function formatLabel(value: string | null | undefined) {
  if (!value) return "Not set";
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
      .map(([key, entryValue]) => `${plainFieldLabel(key)}: ${formatPreviewValue(entryValue)}`)
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

function statusTone(status: string | null | undefined): BadgeTone {
  if (!status) return "default";
  if (["COMPLETED", "READY_FOR_CONFIRMATION", "PASS", "ACTIVE"].includes(status)) return "success";
  if (["PARTIAL", "NEEDS_REVIEW", "DRAFT"].includes(status)) return "warning";
  if (["FAILED", "FAIL", "REJECTED"].includes(status)) return "danger";
  if (["RETRY_CREATED"].includes(status)) return "info";
  return "default";
}

function transferStatusLabel(status: string) {
  const labels: Record<string, string> = {
    COMPLETED: "Saved",
    READY_FOR_CONFIRMATION: "Ready to save",
    PARTIAL: "Partly saved",
    FAILED: "Needs fixes",
    RETRY_CREATED: "Trying again",
    DRAFT: "Draft",
  };
  return labels[status] || formatLabel(status);
}

function flowLabel(exchangeType: string) {
  const labels: Record<string, string> = {
    ORG_UNIT_MAPPING: "Location matching",
    RISK_SCORE_EXPORT: "Risk forecast sharing",
    ward_org_unit_mapping_import: "Location matching",
    aggregate_report_export: "Risk forecast sharing",
    alert_action_summary_export: "Alert and action sharing",
    surveillance_case_count_import: "Surveillance case file",
    outbreak_label_import: "Outbreak label file",
    facility_import: "Facility file",
    population_exposure_import: "Population file",
  };
  return labels[exchangeType] || formatLabel(exchangeType);
}

function directionLabel(direction: InteroperabilityRunRecord["direction"]) {
  return direction === "IMPORT" ? "Receiving data" : "Sharing data";
}

function plainFieldLabel(value: string) {
  const labels: Record<string, string> = {
    external_identifier: "External ID",
    external_display_name: "External name",
    internal_object_type: "CCHIS item type",
    internal_object_public_id: "CCHIS item ID",
    internal_object_code: "CCHIS code",
    mapping_confidence: "Match confidence",
    confirmable: "Ready to save",
    operator_confirmation_required: "Needs review before saving",
    mutation_performed: "Already saved",
    next_action: "Next step",
    missing_required_fields: "Missing columns",
    missing_columns: "Missing columns",
    mapping_coverage_report: "Match summary",
    records_seen: "Rows checked",
    records_with_resolved_mapping: "Rows matched",
    records_requiring_review: "Rows to fix",
    coverage_percent: "Percent matched",
  };
  return labels[value] || formatLabel(value);
}

function nextActionLabel(value: unknown) {
  const raw = typeof value === "string" ? value : "";
  const labels: Record<string, string> = {
    resolve_unmapped_rows: "Fix rows that could not be matched",
    confirm_import: "Review and save approved matches",
    none: "No action needed",
  };
  return labels[raw] || formatPreviewValue(value);
}

function errorLabel(value: string) {
  const labels: Record<string, string> = {
    mapping_missing: "Missing match",
    schema_validation_failed: "File format issue",
    auth_failed: "Connection sign-in failed",
    rate_limited: "External system is busy",
    timeout: "Connection timed out",
    server_error: "External system problem",
    operator_cancelled: "Cancelled before saving",
  };
  return labels[value] || formatLabel(value);
}

function setupIssueCount(data: InteroperabilityDashboardResponse | undefined) {
  return [
    ...(data?.exchange_inventory_contract_errors ?? []),
    ...(data?.csv_template_contract_errors ?? []),
    ...(data?.connector_boundary_contract_errors ?? []),
  ].length;
}

function connectionState(data: InteroperabilityDashboardResponse | undefined) {
  if (!data) {
    return {
      title: "Loading data connections",
      message: "Checking whether external data can be received or shared safely.",
      tone: "info" as BadgeTone,
    };
  }
  const issues = data.summary.failed_run_count + setupIssueCount(data);
  if (!data.summary.active_system_count && !data.summary.active_org_unit_mapping_count && !data.summary.run_count) {
    return {
      title: "Not set up yet",
      message: "No external data system is connected. Start by matching DHIS2 locations to CCHIS wards before sharing data.",
      tone: "warning" as BadgeTone,
    };
  }
  if (data.summary.audit_status === "fail" || issues > 0) {
    return {
      title: "Needs attention",
      message: "Some rows or setup checks need review before data can be trusted across systems.",
      tone: "danger" as BadgeTone,
    };
  }
  if (data.summary.active_system_count && data.summary.active_org_unit_mapping_count) {
    return {
      title: "Ready to share data",
      message: "External systems and location matches are ready. Preview outgoing data before sharing it.",
      tone: "success" as BadgeTone,
    };
  }
  return {
    title: "Setup in progress",
    message: "Finish matching locations before using external data for reports or sharing forecast outputs.",
    tone: "info" as BadgeTone,
  };
}

function getSummaryIconClass(tone: BadgeTone) {
  if (tone === "danger") {
    return "bg-[color-mix(in_srgb,var(--danger)_18%,var(--dashboard-panel-surface))] text-[color:var(--danger)]";
  }
  if (tone === "warning") {
    return "bg-[color-mix(in_srgb,var(--warning)_18%,var(--dashboard-panel-surface))] text-[color:var(--warning)]";
  }
  if (tone === "success") {
    return "bg-[color-mix(in_srgb,var(--success)_18%,var(--dashboard-panel-surface))] text-[color:var(--success)]";
  }
  if (tone === "info") {
    return "bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_18%,var(--dashboard-panel-surface))] text-brand";
  }
  return "bg-[color-mix(in_srgb,var(--dashboard-table-line)_72%,var(--dashboard-panel-surface))] text-panel-copy";
}

function SummaryCard({
  label,
  value,
  helper,
  tone,
  icon,
}: {
  label: string;
  value: string | number;
  helper: string;
  tone: BadgeTone;
  icon: ReactNode;
}) {
  return (
    <Card className="grid gap-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <span className={cn("inline-flex size-9 items-center justify-center rounded-[0.5rem]", getSummaryIconClass(tone))}>
          {icon}
        </span>
        <PlainBadge tone={tone}>{label}</PlainBadge>
      </div>
      <div>
        <p className="text-xl font-semibold leading-tight text-panel-strong">{value}</p>
        <p className="mt-1 text-sm leading-6 text-panel-muted">{helper}</p>
      </div>
    </Card>
  );
}

function InlineMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2">
      <p className="text-xs font-semibold text-panel-muted">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold text-panel-strong">{value}</p>
    </div>
  );
}

function DataConnectionsHero({
  data,
  canManageImports,
  onCheckFile,
}: {
  data: InteroperabilityDashboardResponse | undefined;
  canManageImports: boolean;
  onCheckFile: () => void;
}) {
  const state = connectionState(data);
  return (
    <Card
      tone="attention"
      className={cn(
        "grid gap-5 p-5 md:grid-cols-[1fr_auto] md:items-center",
        state.tone === "danger" && "border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))]",
        state.tone === "warning" && "border-[color-mix(in_srgb,var(--warning)_32%,var(--dashboard-table-line))]",
        state.tone === "success" && "border-[color-mix(in_srgb,var(--success)_30%,var(--dashboard-table-line))]",
      )}
    >
      <div className="min-w-0">
        <PlainBadge tone={state.tone}>Connection status</PlainBadge>
        <h1 className="mt-3 text-2xl font-semibold leading-tight text-panel-strong md:text-3xl">{state.title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-panel-muted md:text-base">{state.message}</p>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row md:flex-col">
        {canManageImports ? (
          <Button type="button" onClick={onCheckFile}>
            <Upload className="size-4" aria-hidden="true" />
            Check matching file
          </Button>
        ) : null}
        <a
          className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
          href={TEMPLATE_URL}
        >
          <Download className="size-4" aria-hidden="true" />
          Download template
        </a>
      </div>
    </Card>
  );
}

function SetupChecklist({ data }: { data: InteroperabilityDashboardResponse | undefined }) {
  const hasExportPreview = Boolean(data?.runs.some((run) => run.direction === "EXPORT"));
  const steps = [
    {
      label: "Add or choose the external system",
      helper: data?.summary.active_system_count ? "At least one external system is available." : "Start with DHIS2 or another approved source.",
      done: Boolean(data?.summary.active_system_count),
    },
    {
      label: "Match external locations to CCHIS locations",
      helper: data?.summary.active_org_unit_mapping_count
        ? `${data.summary.active_org_unit_mapping_count} locations are matched.`
        : "Upload a matching file so external locations point to the right CCHIS wards or facilities.",
      done: Boolean(data?.summary.active_org_unit_mapping_count),
    },
    {
      label: "Check the file before saving",
      helper: data?.summary.run_count ? "At least one file has been checked." : "Checking catches missing rows before anything is saved.",
      done: Boolean(data?.summary.run_count),
    },
    {
      label: "Save approved matches",
      helper: data?.summary.active_mapping_version_count ? "An approved matching set is active." : "Only save after rows have been reviewed.",
      done: Boolean(data?.summary.active_mapping_version_count),
    },
    {
      label: "Preview data before sharing",
      helper: hasExportPreview ? "A sharing preview has been created." : "Preview outgoing data before sending it outside CCHIS.",
      done: hasExportPreview,
    },
  ];

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-panel-strong">Setup checklist</h2>
          <p className="mt-1 text-sm text-panel-muted">A calm path from first file to trusted data sharing.</p>
        </div>
        <PlainBadge tone={steps.every((step) => step.done) ? "success" : "warning"}>
          {steps.filter((step) => step.done).length} of {steps.length}
        </PlainBadge>
      </div>
      <div className="grid gap-3">
        {steps.map((step) => {
          const Icon = step.done ? CheckCircle2 : Circle;
          return (
            <div key={step.label} className="flex gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-3">
              <Icon className={cn("mt-0.5 size-5 shrink-0", step.done ? "text-[color:var(--success)]" : "text-panel-muted")} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-panel-strong">{step.label}</p>
                  <PlainBadge tone={step.done ? "success" : "default"}>{step.done ? "Done" : "Needed"}</PlainBadge>
                </div>
                <p className="mt-1 text-sm leading-6 text-panel-muted">{step.helper}</p>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function MappingRecordRow({ mapping }: { mapping: OrgUnitMappingRecord }) {
  const internalName = mapping.ward_name || mapping.facility_name || mapping.internal_object_code || "Unmatched CCHIS location";
  return (
    <div className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-3 md:grid-cols-[1fr_auto] md:items-center">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-panel-strong">
          {mapping.external_display_name || mapping.external_identifier} to {internalName}
        </p>
        <p className="mt-1 text-xs text-panel-muted">
          External ID {mapping.external_identifier} · {formatConfidence(mapping.mapping_confidence)} confidence
        </p>
      </div>
      <PlainBadge tone={statusTone(mapping.status)}>{mapping.status === "ACTIVE" ? "Matched" : formatLabel(mapping.status)}</PlainBadge>
    </div>
  );
}

function LocationMatchingPanel({
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
  const totalSetupIssues = setupIssueCount(data);
  const checksToShow = failingChecks.length ? failingChecks : (data?.audit_checks ?? []).slice(0, 4);

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Link2 className="mt-0.5 size-5 text-brand" aria-hidden="true" />
          <div>
            <h2 className="text-lg font-semibold text-panel-strong">Location matching</h2>
            <p className="mt-1 text-sm leading-6 text-panel-muted">
              Match external locations to CCHIS wards and facilities before receiving or sharing data.
            </p>
          </div>
        </div>
        <PlainBadge tone={failingChecks.length || totalSetupIssues ? "danger" : activeMappings.length ? "success" : "warning"}>
          {failingChecks.length || totalSetupIssues ? "Needs fixes" : activeMappings.length ? "Ready" : "Not started"}
        </PlainBadge>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <InlineMetric label="Matched locations" value={`${activeMappings.length}/${orgMappings.length}`} />
        <InlineMetric label="Approved matching sets" value={`${activeVersions.length}/${mappingVersions.length}`} />
        <InlineMetric label="Issues to fix" value={failingChecks.length} />
        <InlineMetric label="Setup issues" value={totalSetupIssues} />
      </div>

      <div className="mt-4 grid gap-3">
        {checksToShow.map((check) => (
          <div
            key={check.key}
            className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 md:grid-cols-[1fr_auto] md:items-center"
          >
            <div>
              <p className="text-sm font-semibold text-panel-strong">{check.title}</p>
              <p className="mt-1 text-sm leading-6 text-panel-muted">{check.summary}</p>
            </div>
            <PlainBadge tone={statusTone(check.status)}>{check.status === "PASS" ? "Clear" : `${check.count} to fix`}</PlainBadge>
          </div>
        ))}
        {!checksToShow.length ? <p className="text-sm text-panel-muted">No location checks are available yet.</p> : null}
      </div>

      <div className="mt-5">
        <div className="mb-3 flex items-center gap-2">
          <ListChecks className="size-4 text-brand" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-panel-strong">Recent location matches</h3>
        </div>
        <div className="grid gap-2">
          {orgMappings.slice(0, 6).map((mapping) => (
            <MappingRecordRow key={mapping.public_id} mapping={mapping} />
          ))}
          {!orgMappings.length ? (
            <p className="rounded-[0.5rem] border border-dashed border-[var(--dashboard-table-line)] px-3 py-3 text-sm text-panel-muted">
              No locations have been matched yet.
            </p>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

function MatchingFilePanel({
  csvText,
  confirmImport,
  mappingVersionLabel,
  sourceFileName,
  showPasteCsv,
  isPending,
  canManageImports,
  onCsvChange,
  onConfirmChange,
  onFileChange,
  onLabelChange,
  onShowPasteCsv,
  onSubmit,
}: {
  csvText: string;
  confirmImport: boolean;
  mappingVersionLabel: string;
  sourceFileName: string;
  showPasteCsv: boolean;
  isPending: boolean;
  canManageImports: boolean;
  onCsvChange: (value: string) => void;
  onConfirmChange: (value: boolean) => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onLabelChange: (value: string) => void;
  onShowPasteCsv: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <Card id="check-matching-file" className="scroll-mt-24 p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <FileSpreadsheet className="mt-0.5 size-5 text-brand" aria-hidden="true" />
          <div>
            <h2 className="text-lg font-semibold text-panel-strong">Check location matching file</h2>
            <p className="mt-1 text-sm leading-6 text-panel-muted">
              Check rows first. Nothing is saved until you review the result and choose to save approved matches.
            </p>
          </div>
        </div>
        <a
          className="inline-flex h-9 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-medium text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
          href={TEMPLATE_URL}
        >
          <Download className="size-4" aria-hidden="true" />
          Download template
        </a>
      </div>

      {canManageImports ? (
      <form className="grid gap-3" onSubmit={onSubmit}>
        <label className="grid gap-1 text-sm font-medium text-panel-copy">
          Matching set name
          <input
            aria-label="Matching set name"
            value={mappingVersionLabel}
            onChange={(event) => onLabelChange(event.target.value)}
            className="h-11 rounded-[0.5rem] border border-[var(--dashboard-table-line)] bg-panel px-3 text-sm text-panel-strong outline-none focus:border-brand"
            placeholder="Example: DHIS2 locations May 2026"
          />
        </label>

        <label className="grid gap-2 rounded-[0.5rem] border border-dashed border-[var(--dashboard-table-line)] px-3 py-4 text-sm text-panel-copy">
          <span className="font-semibold text-panel-strong">Choose a completed template file</span>
          <span className="text-panel-muted">Use the downloaded template, then upload it here for checking.</span>
          <input aria-label="Choose location matching CSV" type="file" accept=".csv,text/csv" onChange={onFileChange} />
          <span className="text-xs text-panel-muted">Selected file: {sourceFileName}</span>
        </label>

        {showPasteCsv ? (
          <label className="grid gap-1 text-sm font-medium text-panel-copy">
            Paste CSV instead
            <textarea
              aria-label="Location matching CSV"
              value={csvText}
              onChange={(event) => onCsvChange(event.target.value)}
              rows={7}
              className="min-h-40 rounded-[0.5rem] border border-[var(--dashboard-table-line)] bg-panel px-3 py-2 font-mono text-xs text-panel-strong outline-none focus:border-brand"
            />
          </label>
        ) : (
          <Button type="button" variant="secondary" onClick={onShowPasteCsv} className="justify-self-start">
            Paste CSV instead
          </Button>
        )}

        <label className="flex items-center gap-2 text-sm font-medium text-panel-copy">
          <input
            aria-label="Save approved matches"
            type="checkbox"
            checked={confirmImport}
            onChange={(event) => onConfirmChange(event.target.checked)}
            className="size-4 rounded border-[var(--dashboard-table-line)]"
          />
          Save approved matches after review
        </label>

        <Button type="submit" disabled={isPending} className="justify-self-start">
          <Upload className="size-4" aria-hidden="true" />
          {confirmImport ? "Save approved matches" : "Check file"}
        </Button>
      </form>
      ) : (
        <p className="rounded-[0.75rem] border border-[var(--dashboard-table-line)] px-4 py-4 text-sm leading-6 text-panel-muted">
          Matching uploads are limited to operational data managers. Download the template to inspect the expected file shape.
        </p>
      )}
    </Card>
  );
}

function CheckResultPanel({ run }: { run: InteroperabilityRunRecord }) {
  const preview = previewRecord(run.dry_run_preview);
  const coverageReport = previewRecord(preview.mapping_coverage_report);
  const rows = [
    { label: "Ready to save", value: preview.confirmable },
    { label: "Needs review before saving", value: preview.operator_confirmation_required },
    { label: "Already saved", value: preview.mutation_performed },
    { label: "Next step", value: nextActionLabel(preview.next_action) },
    { label: "Missing columns", value: preview.missing_required_fields ?? preview.missing_columns },
    { label: "Match summary", value: coverageReport },
  ].filter((row) => formatPreviewValue(row.value));

  return (
    <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
      <div className="mb-3 flex items-center gap-2">
        <Eye className="size-4 text-brand" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-panel-strong">Check result</h3>
      </div>
      {rows.length ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {rows.map((row) => (
            <InlineMetric key={row.label} label={row.label} value={formatPreviewValue(row.value)} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-panel-muted">No extra check details are available for this transfer.</p>
      )}
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
        <p className="text-sm font-semibold text-panel-strong">{item.external_identifier || "Unmatched row"}</p>
        <PlainBadge tone={statusTone(item.status)}>{item.status === "UNMAPPED" ? "Needs match" : formatLabel(item.status)}</PlainBadge>
      </div>
      <p className="mt-1 text-xs text-panel-muted">
        {item.source_record_ref || "No file row noted"} · {item.internal_object_code || item.internal_object_public_id || "No CCHIS match"}
      </p>
      {contextEntries.length ? (
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          {contextEntries.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs font-semibold text-panel-muted">{plainFieldLabel(key)}</dt>
              <dd className="mt-1 text-xs text-panel-copy">{formatPreviewValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

function TransferRow({
  run,
  onRetry,
  onReview,
  isRetrying,
  canManageImports,
}: {
  run: InteroperabilityRunRecord;
  onRetry: (publicId: string) => void;
  onReview: (run: InteroperabilityRunRecord) => void | Promise<void>;
  isRetrying: boolean;
  canManageImports: boolean;
}) {
  const canRetry = run.status === "FAILED" || run.status === "PARTIAL";
  return (
    <div className="grid gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-4 last:border-b-0 lg:grid-cols-[1.1fr_0.75fr_0.75fr_0.8fr_auto_auto_auto] lg:items-center">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-panel-strong">{flowLabel(run.exchange_type)}</p>
        <p className="mt-1 text-xs text-panel-muted">{run.system_name || run.system_key} · {formatRelativeTimestamp(run.started_at)}</p>
      </div>
      <PlainBadge tone={statusTone(run.status)}>{transferStatusLabel(run.status)}</PlainBadge>
      <p className="text-sm text-panel-copy">{directionLabel(run.direction)}</p>
      <p className="text-sm text-panel-copy">
        {run.records_accepted} saved · {run.records_rejected} to fix
      </p>
      <Button size="sm" variant="secondary" onClick={() => void onReview(run)}>
        <FileWarning className="size-4" aria-hidden="true" />
        Review
      </Button>
      {canRetry && canManageImports ? (
        <Button size="sm" variant="secondary" disabled={isRetrying} onClick={() => onRetry(run.public_id)}>
          <RefreshCcw className="size-4" aria-hidden="true" />
          Try again
        </Button>
      ) : (
        <PlainBadge tone="default">No retry needed</PlainBadge>
      )}
      {run.errors.length ? (
        <a
          className="inline-flex h-9 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-medium text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
          href={`/api/dashboard/interoperability/runs/${encodeURIComponent(run.public_id)}/errors.csv`}
        >
          <Download className="size-4" aria-hidden="true" />
          Download rows to fix
        </a>
      ) : (
        <PlainBadge tone="default">No rows to fix</PlainBadge>
      )}
      {run.error_summary ? <p className="text-sm text-[color:var(--danger)] lg:col-span-7">{run.error_summary}</p> : null}
    </div>
  );
}

function RecentTransfersPanel({
  runs,
  isFetching,
  isLoading,
  onRetry,
  onReview,
  isRetrying,
  canManageImports,
}: {
  runs: InteroperabilityRunRecord[];
  isFetching: boolean;
  isLoading: boolean;
  onRetry: (publicId: string) => void;
  onReview: (run: InteroperabilityRunRecord) => void | Promise<void>;
  isRetrying: boolean;
  canManageImports: boolean;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-[var(--dashboard-table-line)] px-4 py-3">
        <div className="flex items-center gap-3">
          <History className="size-5 text-brand" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-panel-strong">Recent data transfers</h2>
        </div>
        {isFetching ? <PlainBadge tone="info">Refreshing</PlainBadge> : null}
      </div>
      <div>
        {runs.map((run) => (
          <TransferRow
            key={run.public_id}
            run={run}
            onRetry={onRetry}
            onReview={onReview}
            isRetrying={isRetrying}
            canManageImports={canManageImports}
          />
        ))}
        {!runs.length && !isLoading ? (
          <div className="px-4 py-6 text-sm text-panel-muted">No files have been checked or shared yet.</div>
        ) : null}
      </div>
    </Card>
  );
}

function TransferReviewPanel({
  reviewRun,
  reviewItems,
  isLoadingDetail,
  detailError,
}: {
  reviewRun: InteroperabilityRunRecord | null;
  reviewItems: ReviewItemRecord[];
  isLoadingDetail: boolean;
  detailError: Error | null;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {reviewRun?.errors?.length ? (
            <AlertTriangle className="size-5 text-[color:var(--warning)]" aria-hidden="true" />
          ) : (
            <ShieldCheck className="size-5 text-[color:var(--success)]" aria-hidden="true" />
          )}
          <h2 className="text-lg font-semibold text-panel-strong">Transfer review</h2>
        </div>
        {isLoadingDetail ? <PlainBadge tone="info">Loading detail</PlainBadge> : null}
        {detailError ? <PlainBadge tone="warning">Snapshot shown</PlainBadge> : null}
      </div>
      {reviewRun ? (
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <PlainBadge tone={statusTone(reviewRun.status)}>{transferStatusLabel(reviewRun.status)}</PlainBadge>
            <span className="text-sm text-panel-muted">{flowLabel(reviewRun.exchange_type)}</span>
            <span className="text-sm text-panel-muted">{directionLabel(reviewRun.direction)}</span>
            <span className="text-sm text-panel-muted">{reviewRun.records_rejected} rows to fix</span>
            <span className="text-sm text-panel-muted">{reviewRun.mapping_coverage.toFixed(1)}% matched</span>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <InlineMetric label="File or source" value={reviewRun.source_reference || reviewRun.source_file_name || "Not noted"} />
            <InlineMetric label="Checked by" value={reviewRun.operator_username || "System"} />
            <InlineMetric label="Started" value={formatRelativeTimestamp(reviewRun.started_at)} />
            <InlineMetric label="Finished" value={reviewRun.completed_at ? formatRelativeTimestamp(reviewRun.completed_at) : "Still open"} />
            <InlineMetric label="Rows saved" value={reviewRun.records_accepted} />
            <InlineMetric label="Rows to fix" value={reviewRun.records_rejected} />
            {reviewRun.retry_of ? <InlineMetric label="Related transfer" value={reviewRun.retry_of} /> : null}
            {reviewRun.contract_errors.length ? <InlineMetric label="Setup issues" value={reviewRun.contract_errors.join(", ")} /> : null}
          </div>

          <CheckResultPanel run={reviewRun} />

          <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <FileWarning className="size-4 text-brand" aria-hidden="true" />
                <h3 className="text-sm font-semibold text-panel-strong">Rows to fix</h3>
              </div>
              {reviewRun.errors.length ? (
                <a
                  className="inline-flex h-8 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-xs font-medium text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
                  href={`/api/dashboard/interoperability/runs/${encodeURIComponent(reviewRun.public_id)}/errors.csv`}
                >
                  <Download className="size-3.5" aria-hidden="true" />
                  Download rows to fix
                </a>
              ) : null}
            </div>
            <div className="grid gap-2">
              {reviewRun.errors.slice(0, 8).map((item) => (
                <div key={item.public_id} className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
                  <p className="text-sm font-semibold text-panel-strong">{errorLabel(item.error_code)}</p>
                  <p className="mt-1 text-sm leading-6 text-panel-muted">{item.safe_message}</p>
                  {item.remediation_hint ? <p className="mt-2 text-sm font-medium text-panel-copy">{item.remediation_hint}</p> : null}
                  {item.field_path ? <p className="mt-2 text-xs text-panel-muted">Column: {plainFieldLabel(item.field_path)}</p> : null}
                </div>
              ))}
              {!reviewRun.errors.length ? <p className="text-sm text-panel-muted">No rows need fixing for this transfer.</p> : null}
            </div>
          </div>

          <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <div className="mb-3 flex items-center gap-2">
              <ClipboardList className="size-4 text-brand" aria-hidden="true" />
              <h3 className="text-sm font-semibold text-panel-strong">Rows needing review</h3>
            </div>
            <div className="grid gap-2">
              {reviewItems.slice(0, 8).map((item) => (
                <ReviewItemCard key={item.id} item={item} />
              ))}
              {!reviewItems.length ? <p className="text-sm text-panel-muted">No rows need review for this transfer.</p> : null}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-sm text-panel-muted">No transfer has been checked yet.</p>
      )}
    </Card>
  );
}

function AvailableFlowsPanel({ data }: { data: InteroperabilityDashboardResponse | undefined }) {
  const flows = data?.exchange_inventory ?? [];
  return (
    <details className="rounded-panel border border-panel-border bg-panel p-5 text-panel-copy shadow-panel">
      <summary className="cursor-pointer text-sm font-semibold text-panel-strong">Advanced: available data files</summary>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {flows.map((item) => (
          <div key={item.exchange_type} className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-semibold text-panel-strong">{flowLabel(item.exchange_type)}</p>
              <PlainBadge tone={item.direction === "IMPORT" ? "info" : "default"}>
                {item.direction === "IMPORT" ? "Receive" : "Share"}
              </PlainBadge>
            </div>
            <p className="text-xs leading-5 text-panel-muted">
              Owner: {formatLabel(item.source_owner)} · Format: {formatLabel(item.format)} · Timing: {formatLabel(item.cadence)}
            </p>
          </div>
        ))}
        {!flows.length ? <p className="text-sm text-panel-muted">No data file types are listed yet.</p> : null}
      </div>
    </details>
  );
}

export default function InteroperabilityPage() {
  const { currentUser } = useAuth();
  const { data, isLoading, error, refetch, isFetching } = useInteroperabilityDashboardQuery();
  const importMutation = useInteroperabilityOrgUnitMappingImportMutation();
  const exportPreviewMutation = useInteroperabilityExportPreviewMutation();
  const runDetailMutation = useInteroperabilityRunDetailMutation();
  const retryMutation = useInteroperabilityRetryMutation();
  const [csvText, setCsvText] = useState(DEFAULT_MAPPING_CSV);
  const [confirmImport, setConfirmImport] = useState(false);
  const [mappingVersionLabel, setMappingVersionLabel] = useState("");
  const [sourceFileName, setSourceFileName] = useState("location-matching.csv");
  const [showPasteCsv, setShowPasteCsv] = useState(false);
  const [lastRunResult, setLastRunResult] = useState<InteroperabilityRunRecord | null>(null);
  const [selectedRun, setSelectedRun] = useState<InteroperabilityRunRecord | null>(null);
  const latestRun = data?.runs[0] ?? null;
  const reviewRun = lastRunResult ?? selectedRun ?? latestRun;
  const reviewItems = (reviewRun?.items ?? []).filter((item) => item.status !== "ACCEPTED");
  const failingChecks = useMemo(
    () => data?.audit_checks.filter((check) => check.status === "FAIL") ?? [],
    [data?.audit_checks],
  );
  const canManageImports = hasActionCapability(currentUser, "manage_source_data_imports");

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
      source_file_name: sourceFileName,
      csv_text: csvText,
      confirm: confirmImport,
      retry_of_public_id: confirmablePriorRun,
    });
    setLastRunResult(run);
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setSourceFileName(file.name || "location-matching.csv");
    setCsvText(await file.text());
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
      // Keep the dashboard snapshot visible; downloadable rows still carry the full review file.
    }
  }

  const scrollToCheckFile = () => {
    document.getElementById("check-matching-file")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <RoleGate
      pageCapability="interoperability"
      title="Data connections access required"
      message="Data connection review is available to dashboard operators."
    >
      <div className="grid gap-6">
        <DashboardTopbar
          title="Data Connections"
          subtitle="Safely receive files, match locations, and preview data before sharing."
          lastUpdatedLabel={data?.generated_at ? `Updated ${formatRelativeTimestamp(data.generated_at)}` : "Not loaded"}
          lastUpdatedTone={data?.summary.audit_status === "fail" ? "stale" : "default"}
          onRefresh={() => void refetch()}
        >
          {canManageImports ? (
            <Button size="sm" variant="secondary" onClick={handleExportPreview} disabled={exportPreviewMutation.isPending}>
              <Play className="size-4" aria-hidden="true" />
              Preview sharing
            </Button>
          ) : null}
        </DashboardTopbar>

        {error ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_30%,white)] p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 text-[color:var(--danger)]" />
              <div>
                <p className="font-semibold text-panel-strong">Unable to load data connections</p>
                <p className="mt-1 text-sm text-panel-muted">Refresh the page. If this continues, ask the system team to check the connection dashboard.</p>
              </div>
            </div>
          </Card>
        ) : null}

        <DataConnectionsHero data={data} canManageImports={canManageImports} onCheckFile={scrollToCheckFile} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <SummaryCard
            label="Connected systems"
            value={data?.summary.active_system_count ?? 0}
            helper={(data?.summary.active_system_count ?? 0) ? "External systems are available." : "No external system is active yet."}
            tone={(data?.summary.active_system_count ?? 0) ? "success" : "warning"}
            icon={<Link2 className="size-5" />}
          />
          <SummaryCard
            label="Locations matched"
            value={data?.summary.active_org_unit_mapping_count ?? 0}
            helper={(data?.summary.active_org_unit_mapping_count ?? 0) ? "Locations can be used for transfer review." : "Match locations before sharing data."}
            tone={(data?.summary.active_org_unit_mapping_count ?? 0) ? "success" : "warning"}
            icon={<ListChecks className="size-5" />}
          />
          <SummaryCard
            label="Recent transfers"
            value={data?.summary.run_count ?? 0}
            helper={(data?.summary.run_count ?? 0) ? "Recent checks and sharing previews are listed below." : "No file has been checked yet."}
            tone={(data?.summary.run_count ?? 0) ? "info" : "default"}
            icon={<History className="size-5" />}
          />
          <SummaryCard
            label="Issues to fix"
            value={(data?.summary.failed_run_count ?? 0) + failingChecks.length + setupIssueCount(data)}
            helper="Rows or setup items that need review before data is trusted."
            tone={(data?.summary.failed_run_count ?? 0) + failingChecks.length + setupIssueCount(data) ? "danger" : "success"}
            icon={<AlertTriangle className="size-5" />}
          />
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <SetupChecklist data={data} />
          <MatchingFilePanel
            csvText={csvText}
            confirmImport={confirmImport}
            mappingVersionLabel={mappingVersionLabel}
            sourceFileName={sourceFileName}
            showPasteCsv={showPasteCsv}
            isPending={importMutation.isPending}
            canManageImports={canManageImports}
            onCsvChange={setCsvText}
            onConfirmChange={setConfirmImport}
            onFileChange={(event) => void handleFileChange(event)}
            onLabelChange={setMappingVersionLabel}
            onShowPasteCsv={() => setShowPasteCsv(true)}
            onSubmit={(event) => void handleDryRunSubmit(event)}
          />
        </section>

        <LocationMatchingPanel data={data} failingChecks={failingChecks} />

        <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <RecentTransfersPanel
            runs={data?.runs ?? []}
            isFetching={isFetching}
            isLoading={isLoading}
            onRetry={handleRetry}
            onReview={handleReview}
            isRetrying={retryMutation.isPending}
            canManageImports={canManageImports}
          />
          <TransferReviewPanel
            reviewRun={reviewRun}
            reviewItems={reviewItems}
            isLoadingDetail={runDetailMutation.isPending}
            detailError={runDetailMutation.error as Error | null}
          />
        </section>

        <AvailableFlowsPanel data={data} />
      </div>
    </RoleGate>
  );
}
