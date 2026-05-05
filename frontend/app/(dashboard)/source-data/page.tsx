"use client";

import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Download,
  FileSpreadsheet,
  RefreshCcw,
  ShieldCheck,
  Upload,
} from "lucide-react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { useAuth } from "@/components/auth-provider";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  approveSourceDataUploadViaBff,
  cancelSourceDataUploadViaBff,
  confirmSourceDataUploadViaBff,
  createSourceDataUploadViaBff,
  runSourceDataDownstreamActionViaBff,
  updateSourceDataFeedModeViaBff,
  validateSourceDataUploadViaBff,
  type SourceDataDownstreamActionDefinition,
  type SourceDataDownstreamActionPayload,
  type SourceDataFeedDefinition,
  type SourceDataFreshnessSource,
  type SourceDataOperationsResponse,
  type SourceDataUploadBatchRecord,
  type SourceDataUploadFilters,
} from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { queryKeys } from "@/lib/query-keys";
import {
  useSourceDataFeedTypesQuery,
  useSourceDataOperationsQuery,
  useSourceDataOverviewQuery,
  useSourceDataUploadQuery,
  useSourceDataUploadsQuery,
} from "@/queries/use-source-data-query";

const ALLOWED_ROLES = ["ADMIN", "SUPERVISOR", "ANALYST"] as const;
const CLIENT_MAX_CSV_FILE_BYTES = 20 * 1024 * 1024;

type UploadFormErrors = Partial<
  Record<
    | "feed_key"
    | "source_name"
    | "source_timestamp"
    | "file"
    | "reporting_period_start"
    | "reporting_period_end"
    | "replacement_reason",
    string
  >
>;

const ISSUE_FIX_COPY: Record<string, string> = {
  artifact_hash_mismatch: "Upload the file again from the original export so validation and import use the same artifact.",
  artifact_missing: "Create a fresh upload; the stored file is no longer available to the validator.",
  binary_file_detected: "Export the source as plain UTF-8 CSV and upload that file.",
  duplicate_header: "Keep one copy of the column, then download a fresh template if needed.",
  duplicate_file_hash: "Confirm this is an intentional replay before import, or upload the corrected file.",
  duplicate_snapshot: "Keep only one current row per facility and reported_at timestamp.",
  duplicate_snapshot_in_file: "Remove the repeated facility snapshot row and validate again.",
  duplicate_upload_metadata: "Update the source timestamp or mark this as an intentional replacement/replay.",
  empty_file: "Export the CSV with the header row and at least one data row.",
  formula_injection_value: "Remove spreadsheet formulas from the CSV and save plain values only.",
  future_reported_at: "Use the actual facility report timestamp, not a future collection date.",
  html_or_xml_file_detected: "Export the source as a plain CSV file before upload.",
  invalid_boolean: "Use true or false for readiness yes/no fields.",
  invalid_encoding: "Save the file as UTF-8 CSV before uploading.",
  invalid_nonnegative_integer: "Use whole numbers greater than or equal to zero.",
  invalid_reporting_period: "Use YYYY-MM-DD dates in the reporting period fields.",
  invalid_reporting_period_bounds: "Make the reporting period end on or after the start date.",
  missing_headers: "Download the template and keep the first row as column headers.",
  missing_required_column_group: "Add one of the required identity columns shown in the template.",
  missing_required_field: "Fill the required readiness fields before validating again.",
  no_data_rows: "Keep the header row and add at least one source-data row.",
  no_case_counts_or_outbreak_label: "Enter a case count or outbreak label for each surveillance row.",
  pii_email_value_detected: "Remove direct identifiers; source diagnostics must use aggregate or coded data only.",
  pii_header_detected: "Remove personal-information columns such as names, phone numbers, or IDs.",
  pii_identifier_value_detected: "Replace direct identifiers with approved facility, ward, or source references.",
  pii_phone_value_detected: "Remove phone numbers from the CSV before upload.",
  row_limit_exceeded: "Split the file into smaller CSV uploads.",
  service_disruption_reported: "This is a warning; review the facility context before importing.",
  stale_report: "This is a warning; confirm the older report is still the intended source.",
  stockout_detected: "This is a warning; review the stockout flags before importing.",
  unknown_column: "Remove the extra column or ask for the source-data contract to be updated.",
  unknown_facility_code: "Check the facility code against the county facility register.",
  unknown_ward_code: "Check the ward code against the Migori ward register.",
  unexpected_content_type: "Upload a CSV file with a CSV content type.",
  unsupported_file_extension: "Upload a .csv file exported from the template.",
  unsafe_text_value_detected: "Remove names, contacts, identifiers, exact locations, and clinical notes from the CSV.",
};

function formatLabel(value: string) {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function cadenceLabel(value: string) {
  return value.replaceAll("_", " ");
}

function FeedMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
      <p className="mt-1 text-sm font-semibold text-panel-strong">{value}</p>
    </div>
  );
}

function statusTone(status: string): "success" | "warning" | "danger" | "info" | "default" {
  if (["ready_for_confirmation", "passed", "imported", "approved", "completed", "available", "not_required"].includes(status)) {
    return "success";
  }
  if (["validation_failed", "failed", "import_failed", "rejected", "error"].includes(status)) {
    return "danger";
  }
  if (["uploaded", "running", "validating", "pending", "confirming", "queued"].includes(status)) {
    return "warning";
  }
  if (["not_started", "unavailable"].includes(status)) {
    return "default";
  }
  return "info";
}

function inferredRiskCategory(upload?: SourceDataUploadBatchRecord) {
  if (!upload) {
    return "";
  }
  if (upload.approval_risk_category) {
    return upload.approval_risk_category;
  }
  if (upload.metadata.duplicate_file_sha256 && upload.metadata.duplicate_metadata_upload_public_id) {
    return "replay_import";
  }
  if (upload.replaces_upload_public_id || upload.replacement_reason || upload.correction_mode === "release_replacement") {
    return "replacement_import";
  }
  if (upload.feed_key === "surveillance_backfill" || upload.correction_mode === "backfill") {
    return "historical_backfill";
  }
  if (upload.correction_mode === "amendment") {
    return "replacement_import";
  }
  return "";
}

function numberFromRecord(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function readinessValidationSummary(upload?: SourceDataUploadBatchRecord) {
  if (!upload || upload.feed_key !== "facility_readiness_snapshot") {
    return null;
  }
  const validationSummary = upload.metadata.validation_summary as Record<string, unknown> | undefined;
  const summary = validationSummary?.readiness_summary as Record<string, unknown> | undefined;
  return summary ?? null;
}

function sourceStatusTone(status: string): "success" | "warning" | "danger" | "info" | "default" {
  if (status === "current") {
    return "success";
  }
  if (["due_soon", "demo_backed"].includes(status)) {
    return "warning";
  }
  if (["stale", "missing", "failed"].includes(status)) {
    return "danger";
  }
  return "info";
}

function issueFixCopy(code: string) {
  return ISSUE_FIX_COPY[code] ?? "Review the row, compare it with the template, and validate again after correcting the CSV.";
}

function percent(value: number, total: number) {
  if (!total) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
}

function toDatetimeLocalValue(value: string | null | undefined) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function ProgressBar({ label, value }: { label: string; value: number }) {
  const boundedValue = Math.max(0, Math.min(100, value));
  return (
    <div className="grid gap-1">
      <div className="flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
        <span>{label}</span>
        <span>{boundedValue}%</span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-pill bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)]"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={boundedValue}
      >
        <div className="h-full rounded-pill bg-brand" style={{ width: `${boundedValue}%` }} />
      </div>
    </div>
  );
}

function FieldMessage({ id, message }: { id: string; message?: string }) {
  if (!message) {
    return null;
  }
  return (
    <p id={id} className="text-xs font-semibold text-[color:var(--danger)]" role="alert">
      {message}
    </p>
  );
}

function validateUploadForm({
  selectedFeed,
  feedKey,
  sourceName,
  sourceTimestamp,
  reportingPeriodStart,
  reportingPeriodEnd,
  file,
  requiresReportingPeriod,
  replacementMode,
  replacementReason,
}: {
  selectedFeed?: SourceDataFeedDefinition;
  feedKey: string;
  sourceName: string;
  sourceTimestamp: string;
  reportingPeriodStart: string;
  reportingPeriodEnd: string;
  file: File | null;
  requiresReportingPeriod: boolean;
  replacementMode?: boolean;
  replacementReason?: string;
}) {
  const errors: UploadFormErrors = {};
  if (!feedKey || !selectedFeed) {
    errors.feed_key = "Choose the source feed before uploading.";
  }
  if (!sourceName.trim()) {
    errors.source_name = "Enter the source system or county workbook name.";
  }
  if (!sourceTimestamp) {
    errors.source_timestamp = "Choose when this source extract was generated.";
  } else if (Number.isNaN(new Date(sourceTimestamp).getTime())) {
    errors.source_timestamp = "Use a valid source timestamp.";
  }
  if (!file) {
    errors.file = "Choose a CSV file exported from the template.";
  } else {
    const fileName = file.name.toLowerCase();
    const csvContentTypes = ["", "text/csv", "application/csv", "application/vnd.ms-excel"];
    if (!fileName.endsWith(".csv") || !csvContentTypes.includes(file.type)) {
      errors.file = "Choose a .csv file. Export Excel workbooks as CSV before upload.";
    } else if (file.size > CLIENT_MAX_CSV_FILE_BYTES) {
      errors.file = "This file is over 20 MB. Split the CSV before uploading.";
    }
  }
  if (requiresReportingPeriod && !reportingPeriodStart) {
    errors.reporting_period_start = "Enter the first date covered by this source extract.";
  }
  if (requiresReportingPeriod && !reportingPeriodEnd) {
    errors.reporting_period_end = "Enter the last date covered by this source extract.";
  }
  if (reportingPeriodStart && reportingPeriodEnd && reportingPeriodStart > reportingPeriodEnd) {
    errors.reporting_period_end = "Reporting period end must be on or after the start date.";
  }
  if (replacementMode && !(replacementReason ?? "").trim()) {
    errors.replacement_reason = "Explain why this upload replaces the selected batch.";
  }
  return errors;
}

function TemplateDownloadButton({ feed }: { feed: SourceDataFeedDefinition }) {
  return (
    <a
      href={`/api/dashboard/source-data/templates/${encodeURIComponent(feed.feed_key)}`}
      className="inline-flex h-10 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
    >
      <Download className="size-4" aria-hidden="true" />
      Template
    </a>
  );
}

function connectorTone(status: string): "success" | "warning" | "danger" | "info" | "default" {
  if (status === "success" || status === "configured") {
    return "success";
  }
  if (status === "failed") {
    return "danger";
  }
  if (["disabled", "skipped", "not_configured"].includes(status)) {
    return "warning";
  }
  return statusTone(status);
}

function FeedCard({ feed, canManageImports }: { feed: SourceDataFeedDefinition; canManageImports: boolean }) {
  const queryClient = useQueryClient();
  const connector = feed.connector_status;
  const csvUploadEnabled = feed.csv_upload_enabled ?? true;
  const feedModeMutation = useMutation({
    mutationFn: () =>
      updateSourceDataFeedModeViaBff(feed.feed_key, {
        feed_mode: csvUploadEnabled ? "api" : "fallback",
        csv_upload_enabled: !csvUploadEnabled,
        authoritative_connector_key: connector?.connector_key || undefined,
        reason: csvUploadEnabled
          ? "API connector marked authoritative for routine source refresh."
          : "CSV fallback re-enabled for corrections and source-gap recovery.",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sourceData.root() });
    },
  });

  return (
    <Card className="grid gap-4 p-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-start">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <StatusBadge tone="info">{formatLabel(feed.domain)}</StatusBadge>
            <StatusBadge tone={feed.feed_mode === "api" ? "success" : "default"}>
              {formatLabel(feed.feed_mode ?? "csv")}
            </StatusBadge>
            <StatusBadge tone={csvUploadEnabled ? "info" : "warning"}>
              {csvUploadEnabled ? "CSV Fallback" : "CSV Disabled"}
            </StatusBadge>
            {feed.requires_new_ingestion_path ? <StatusBadge tone="warning">New Path</StatusBadge> : null}
          </div>
          <h2 className="text-lg font-semibold text-panel-strong">{feed.label}</h2>
          <p className="mt-1 text-sm leading-6 text-panel-muted">{feed.adapter_notes}</p>
        </div>
        <TemplateDownloadButton feed={feed} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <FeedMetric label="Cadence" value={cadenceLabel(feed.cadence)} />
        <FeedMetric label="Source Type" value={feed.source_type} />
        <FeedMetric label="Columns" value={feed.accepted_columns.length} />
        <FeedMetric label="Metadata" value={feed.required_metadata.length} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Required Metadata</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {feed.required_metadata.map((field) => (
              <span
                key={field}
                className="rounded-pill bg-[color-mix(in_srgb,var(--dashboard-table-line)_68%,transparent)] px-2.5 py-1 text-xs font-semibold text-panel-copy"
              >
                {field}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Downstream Action</p>
          <p className="mt-2 text-sm font-semibold text-panel-strong">{cadenceLabel(feed.downstream_action)}</p>
        </div>
      </div>

      {connector?.connector_key ? (
        <div className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 md:grid-cols-[1fr_auto] md:items-center">
          <div className="grid gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-semibold text-panel-strong">{connector.label}</p>
              <StatusBadge tone={connectorTone(connector.status)}>{formatLabel(connector.status)}</StatusBadge>
              {!connector.enabled ? <StatusBadge tone="warning">API Disabled</StatusBadge> : null}
              {connector.configured ? <StatusBadge tone="success">Configured</StatusBadge> : <StatusBadge tone="warning">Needs Config</StatusBadge>}
            </div>
            <p className="text-sm leading-6 text-panel-muted">{connector.notes}</p>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
              Last successful fetch{" "}
              {connector.last_successful_fetch_at ? formatRelativeTimestamp(connector.last_successful_fetch_at) : "not recorded"}
            </p>
          </div>
          {canManageImports ? (
            <Button
              type="button"
              variant="secondary"
              size="md"
              disabled={!connector.enabled || !connector.configured || feedModeMutation.isPending}
              onClick={() => feedModeMutation.mutate()}
            >
              {csvUploadEnabled ? "Disable CSV" : "Enable CSV"}
            </Button>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

function UploadWizard({
  feeds,
  recentUploads,
  selectedUpload,
  canManageImports,
  onUploadSelected,
}: {
  feeds: SourceDataFeedDefinition[];
  recentUploads: SourceDataUploadBatchRecord[];
  selectedUpload?: SourceDataUploadBatchRecord;
  canManageImports: boolean;
  onUploadSelected: (publicId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [feedKey, setFeedKey] = useState(feeds[0]?.feed_key ?? "");
  const [sourceName, setSourceName] = useState("");
  const [sourceTimestamp, setSourceTimestamp] = useState("");
  const [reportingPeriodStart, setReportingPeriodStart] = useState("");
  const [reportingPeriodEnd, setReportingPeriodEnd] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [replacementMode, setReplacementMode] = useState(false);
  const [replacementReason, setReplacementReason] = useState("");

  const selectedFeed = feeds.find((feed) => feed.feed_key === feedKey) ?? feeds[0];
  const requiresReportingPeriod = Boolean(selectedFeed?.required_metadata.some((field) =>
    ["reporting_period_start", "reporting_period_end"].includes(field),
  ));
  const lastUploadForFeed = useMemo(
    () => recentUploads.find((upload) => upload.feed_key === feedKey),
    [feedKey, recentUploads],
  );
  const formErrors = validateUploadForm({
    selectedFeed,
    feedKey,
    sourceName,
    sourceTimestamp,
    reportingPeriodStart,
    reportingPeriodEnd,
    file,
    requiresReportingPeriod,
    replacementMode,
    replacementReason,
  });
  const showError = (field: keyof UploadFormErrors) => (submitAttempted ? formErrors[field] : undefined);

  const uploadMutation = useMutation({
    mutationFn: createSourceDataUploadViaBff,
    onSuccess: async (upload) => {
      onUploadSelected(upload.public_id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.sourceData.root() });
    },
  });

  const validateMutation = useMutation({
    mutationFn: validateSourceDataUploadViaBff,
    onSuccess: async (upload) => {
      onUploadSelected(upload.public_id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.sourceData.root() });
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitAttempted(true);
    if (Object.keys(formErrors).length || !file) {
      return;
    }

    uploadMutation.mutate({
      feed_key: feedKey,
      source_name: sourceName,
      source_timestamp: sourceTimestamp,
      reporting_period_start: reportingPeriodStart,
      reporting_period_end: reportingPeriodEnd,
      replacement_reason: replacementMode ? replacementReason : undefined,
      replaces_upload_public_id: replacementMode ? selectedUpload?.public_id : undefined,
      file,
    });
  }

  function applyLastMetadata() {
    if (!lastUploadForFeed) {
      return;
    }
    setSourceName(lastUploadForFeed.source_name);
    setSourceTimestamp(toDatetimeLocalValue(lastUploadForFeed.source_timestamp));
    setReportingPeriodStart(lastUploadForFeed.reporting_period_start ?? "");
    setReportingPeriodEnd(lastUploadForFeed.reporting_period_end ?? "");
  }

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <Upload className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Upload And Dry Validate</h2>
      </div>

      <form className="grid gap-4" onSubmit={handleSubmit}>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            Feed
            <select
              value={feedKey}
              onChange={(event) => {
                setFeedKey(event.target.value);
                setSubmitAttempted(false);
              }}
              aria-invalid={Boolean(showError("feed_key"))}
              aria-describedby="source-data-feed-error"
              className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              {feeds.map((feed) => (
                <option key={feed.feed_key} value={feed.feed_key}>
                  {feed.label}
                </option>
              ))}
            </select>
            <FieldMessage id="source-data-feed-error" message={showError("feed_key")} />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            Source name
            <input
              value={sourceName}
              onChange={(event) => setSourceName(event.target.value)}
              placeholder="Migori DHIS2"
              aria-invalid={Boolean(showError("source_name"))}
              aria-describedby="source-data-source-name-error"
              className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            />
            <FieldMessage id="source-data-source-name-error" message={showError("source_name")} />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            Source timestamp
            <input
              type="datetime-local"
              value={sourceTimestamp}
              onChange={(event) => setSourceTimestamp(event.target.value)}
              aria-invalid={Boolean(showError("source_timestamp"))}
              aria-describedby="source-data-source-timestamp-error"
              className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            />
            <FieldMessage id="source-data-source-timestamp-error" message={showError("source_timestamp")} />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            CSV file
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              aria-invalid={Boolean(showError("file"))}
              aria-describedby="source-data-file-error"
              className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 py-2 text-sm text-panel-strong outline-none file:mr-3 file:rounded-pill file:border-0 file:bg-[var(--dashboard-icon-button-surface)] file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-panel-copy focus-visible:ring-2 focus-visible:ring-brand/30"
            />
            <FieldMessage id="source-data-file-error" message={showError("file")} />
          </label>
        </div>

        {lastUploadForFeed ? (
          <div className="flex flex-wrap items-center gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 text-sm text-panel-muted">
            <span className="font-semibold text-panel-strong">Last metadata</span>
            <span>{lastUploadForFeed.source_name}</span>
            <span>{lastUploadForFeed.source_timestamp ? formatRelativeTimestamp(lastUploadForFeed.source_timestamp) : "No source timestamp"}</span>
            <Button type="button" variant="secondary" size="sm" onClick={applyLastMetadata}>
              Use Last Metadata
            </Button>
          </div>
        ) : null}

        {requiresReportingPeriod ? (
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-semibold text-panel-copy">
              Reporting period start
              <input
                type="date"
                value={reportingPeriodStart}
                onChange={(event) => setReportingPeriodStart(event.target.value)}
                aria-invalid={Boolean(showError("reporting_period_start"))}
                aria-describedby="source-data-reporting-start-error"
                className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
              />
              <FieldMessage id="source-data-reporting-start-error" message={showError("reporting_period_start")} />
            </label>
            <label className="grid gap-2 text-sm font-semibold text-panel-copy">
              Reporting period end
              <input
                type="date"
                value={reportingPeriodEnd}
                onChange={(event) => setReportingPeriodEnd(event.target.value)}
                aria-invalid={Boolean(showError("reporting_period_end"))}
                aria-describedby="source-data-reporting-end-error"
                className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
              />
              <FieldMessage id="source-data-reporting-end-error" message={showError("reporting_period_end")} />
            </label>
          </div>
        ) : null}

        {canManageImports && selectedUpload ? (
          <div className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <label className="flex items-center gap-3 text-sm font-semibold text-panel-copy">
              <input
                type="checkbox"
                checked={replacementMode}
                onChange={(event) => setReplacementMode(event.target.checked)}
                className="size-4 rounded border-panel-table-wrap"
              />
              Upload as replacement for selected batch
            </label>
            {replacementMode ? (
              <label className="grid gap-2 text-sm font-semibold text-panel-copy">
                Replacement reason
                <textarea
                  value={replacementReason}
                  onChange={(event) => setReplacementReason(event.target.value)}
                  rows={3}
                  aria-invalid={Boolean(showError("replacement_reason"))}
                  aria-describedby="source-data-replacement-reason-error"
                  className="rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 py-2 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
                />
                <FieldMessage id="source-data-replacement-reason-error" message={showError("replacement_reason")} />
              </label>
            ) : null}
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
              Admin/Supervisor replacement path keeps the original upload in audit history.
            </p>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" size="md" disabled={uploadMutation.isPending}>
            <Upload className="size-4" aria-hidden="true" />
            Create Upload
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="md"
            disabled={!selectedUpload || validateMutation.isPending}
            onClick={() => selectedUpload && validateMutation.mutate(selectedUpload.public_id)}
          >
            <ShieldCheck className="size-4" aria-hidden="true" />
            Dry Validate
          </Button>
          {selectedFeed ? <TemplateDownloadButton feed={selectedFeed} /> : null}
        </div>

        {uploadMutation.error || validateMutation.error ? (
          <p className="text-sm font-semibold text-[color:var(--danger)]">
            {(uploadMutation.error ?? validateMutation.error) instanceof Error
              ? (uploadMutation.error ?? validateMutation.error)?.message
              : "Source-data upload action failed."}
          </p>
        ) : null}
      </form>
    </Card>
  );
}

function UploadProgressTimeline({ upload }: { upload: SourceDataUploadBatchRecord }) {
  const latestDownstreamAction = (upload.metadata.latest_downstream_action ?? {}) as Record<string, unknown>;
  const latestDownstreamStatus =
    typeof latestDownstreamAction.action_status === "string" ? latestDownstreamAction.action_status : "";
  const steps = [
    {
      key: "upload",
      label: "Upload",
      value: "File stored",
      tone: "success" as const,
    },
    {
      key: "validation",
      label: "Dry validation",
      value: formatLabel(upload.validation_status),
      tone: statusTone(upload.validation_status),
    },
    {
      key: "approval",
      label: "Approval",
      value: formatLabel(upload.approval_status),
      tone: statusTone(upload.approval_status),
    },
    {
      key: "import",
      label: "Import",
      value: formatLabel(upload.import_status),
      tone: statusTone(upload.import_status),
    },
    {
      key: "downstream",
      label: "Downstream evidence",
      value: latestDownstreamStatus ? formatLabel(latestDownstreamStatus) : upload.status === "imported" ? "Ready" : "Waiting",
      tone: latestDownstreamStatus ? statusTone(latestDownstreamStatus) : upload.status === "imported" ? ("warning" as const) : ("default" as const),
    },
  ];

  return (
    <ol className="grid gap-2 sm:grid-cols-5" aria-label="Source-data upload progress">
      {steps.map((step) => (
        <li
          key={step.key}
          className="grid gap-1 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2"
        >
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{step.label}</span>
          <StatusBadge tone={step.tone}>{step.value}</StatusBadge>
        </li>
      ))}
    </ol>
  );
}

function RowCountVisuals({ upload }: { upload: SourceDataUploadBatchRecord }) {
  return (
    <div className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 sm:grid-cols-3">
      <ProgressBar label="Accepted rows" value={percent(upload.accepted_count, upload.row_count)} />
      <ProgressBar label="Rejected rows" value={percent(upload.rejected_count, upload.row_count)} />
      <ProgressBar label="Warning share" value={percent(upload.warning_count, Math.max(upload.row_count, upload.warning_count))} />
    </div>
  );
}

function ValidationSummary({ upload }: { upload?: SourceDataUploadBatchRecord }) {
  const issues = upload?.validation_issues ?? [];
  const topIssues = issues.slice(0, 6);
  const readinessSummary = readinessValidationSummary(upload);

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <CheckCircle2 className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Validation Summary</h2>
      </div>

      {upload ? (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={statusTone(upload.status)}>{formatLabel(upload.status)}</StatusBadge>
            <StatusBadge tone={statusTone(upload.validation_status)}>
              {formatLabel(upload.validation_status)}
            </StatusBadge>
            {upload.duplicate_of_public_id ? <StatusBadge tone="warning">Duplicate Metadata/File</StatusBadge> : null}
          </div>

          <UploadProgressTimeline upload={upload} />

          <div className="grid gap-3 sm:grid-cols-4">
            <FeedMetric label="Rows Seen" value={upload.row_count} />
            <FeedMetric label="Accepted" value={upload.accepted_count} />
            <FeedMetric label="Rejected" value={upload.rejected_count} />
            <FeedMetric label="Warnings" value={upload.warning_count} />
          </div>

          <RowCountVisuals upload={upload} />

          {readinessSummary ? (
            <div className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-semibold text-panel-strong">Readiness Coverage</p>
                <StatusBadge tone="info">
                  {numberFromRecord(readinessSummary.facility_coverage_percent)}% facilities
                </StatusBadge>
              </div>
              <ProgressBar
                label="Facility coverage"
                value={numberFromRecord(readinessSummary.facility_coverage_percent)}
              />
              <div className="grid gap-3 sm:grid-cols-4">
                <FeedMetric label="Facilities" value={numberFromRecord(readinessSummary.facilities_reported)} />
                <FeedMetric label="Stale Reports" value={numberFromRecord(readinessSummary.stale_report_count)} />
                <FeedMetric label="Stockouts" value={numberFromRecord(readinessSummary.stockout_facility_count)} />
                <FeedMetric label="Disruptions" value={numberFromRecord(readinessSummary.service_disruption_count)} />
              </div>
            </div>
          ) : null}

          {topIssues.length ? (
            <div className="overflow-x-auto rounded-[0.5rem] border border-[var(--dashboard-table-line)]">
              <table className="w-full min-w-[760px] text-left text-sm">
                <caption className="sr-only">Source-data validation issues</caption>
                <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_64%,transparent)] text-xs uppercase text-panel-muted">
                  <tr>
                    <th className="px-3 py-2">Row</th>
                    <th className="px-3 py-2">Severity</th>
                    <th className="px-3 py-2">Code</th>
                    <th className="px-3 py-2">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {topIssues.map((issue) => (
                    <tr key={issue.id} className="border-t border-[var(--dashboard-table-line)]">
                      <td className="px-3 py-2 text-panel-muted">{issue.row_number ?? "-"}</td>
                      <td className="px-3 py-2">
                        <StatusBadge tone={statusTone(issue.severity)}>{formatLabel(issue.severity)}</StatusBadge>
                      </td>
                      <td className="px-3 py-2 font-semibold text-panel-strong">{issue.code}</td>
                      <td className="px-3 py-2 text-panel-muted">
                        <p>{issue.message}</p>
                        <p className="mt-1 text-xs font-semibold text-panel-copy">{issueFixCopy(issue.code)}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm leading-6 text-panel-muted">
              No validation issues are stored for the selected upload. Run Dry Validate after creating an upload to refresh this panel.
            </p>
          )}

          {issues.length ? (
            <a
              href={`/api/dashboard/source-data/uploads/${encodeURIComponent(upload.public_id)}/errors.csv`}
              className="inline-flex h-10 w-fit items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              <Download className="size-4" aria-hidden="true" />
              Download rejected rows
            </a>
          ) : null}
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Create an upload from the wizard, then run Dry Validate to see accepted rows, rejected rows, warnings, and diagnostics.
        </p>
      )}
    </Card>
  );
}

function FreshnessPanel({
  sources,
  generatedAt,
}: {
  sources: SourceDataFreshnessSource[];
  generatedAt?: string;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Database className="size-5 text-brand" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-panel-strong">Source Freshness</h2>
        </div>
        {generatedAt ? (
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
            {formatRelativeTimestamp(generatedAt)}
          </p>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-[0.5rem] border border-[var(--dashboard-table-line)]">
        <table className="w-full min-w-[760px] text-left text-sm">
          <caption className="sr-only">Current source-data freshness by feed and system source</caption>
          <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_64%,transparent)] text-xs uppercase text-panel-muted">
            <tr>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Truth</th>
              <th className="px-3 py-2">Last Source</th>
              <th className="px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.key} className="border-t border-[var(--dashboard-table-line)]">
                <td className="px-3 py-2">
                  <p className="font-semibold text-panel-strong">{source.label}</p>
                  <p className="text-xs text-panel-muted">{formatLabel(source.domain)}</p>
                </td>
                <td className="px-3 py-2">
                  <StatusBadge tone={sourceStatusTone(source.status)}>{formatLabel(source.status)}</StatusBadge>
                </td>
                <td className="px-3 py-2 text-panel-muted">{formatLabel(source.truth_state)}</td>
                <td className="px-3 py-2 text-panel-muted">
                  {source.last_source_timestamp ? formatRelativeTimestamp(source.last_source_timestamp) : "Missing"}
                </td>
                <td className="px-3 py-2 text-panel-muted">{source.recommended_action}</td>
              </tr>
            ))}
            {!sources.length ? (
              <tr>
                <td className="px-3 py-4 text-panel-muted" colSpan={5}>
                  Source freshness has not loaded yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SourceGapsPanel({
  gaps,
}: {
  gaps: Array<{
    feed_key: string;
    label: string;
    status: string;
    truth_state: string;
    recommended_action: string;
  }>;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <AlertTriangle className="size-5 text-[color:var(--warning)]" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Source Gaps</h2>
      </div>
      <div className="grid gap-3">
        {gaps.map((gap) => (
          <div key={gap.feed_key} className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-semibold text-panel-strong">{gap.label}</p>
              <StatusBadge tone={sourceStatusTone(gap.status)}>{formatLabel(gap.status)}</StatusBadge>
              <StatusBadge tone="info">{formatLabel(gap.truth_state)}</StatusBadge>
            </div>
            <p className="text-sm text-panel-muted">{gap.recommended_action}</p>
            <a
              href={`/api/dashboard/source-data/templates/${encodeURIComponent(gap.feed_key)}`}
              className="inline-flex h-9 w-fit items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              <Download className="size-4" aria-hidden="true" />
              Template
            </a>
          </div>
        ))}
        {!gaps.length ? (
          <p className="text-sm leading-6 text-panel-muted">
            No stale, missing, failed, or demo-backed source gaps are currently visible.
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function OperationsHealthPanel({ operations }: { operations?: SourceDataOperationsResponse }) {
  const metrics = operations?.metrics;
  const worker = operations?.worker_health;
  const stuckImportCount = operations?.stuck_tasks.imports.length ?? 0;
  const stuckValidationCount = operations?.stuck_tasks.validations.length ?? 0;

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <ShieldCheck className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Production Health</h2>
      </div>

      {operations ? (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={statusTone(worker?.status ?? "missing")}>
              Worker {formatLabel(worker?.status ?? "missing")}
            </StatusBadge>
            <StatusBadge tone={operations.retention.expired_raw_artifact_count ? "warning" : "success"}>
              {operations.retention.expired_raw_artifact_count} Expired Artifacts
            </StatusBadge>
            <StatusBadge tone={stuckImportCount || stuckValidationCount ? "danger" : "success"}>
              {stuckImportCount + stuckValidationCount} Stuck Tasks
            </StatusBadge>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <FeedMetric label="Uploads" value={metrics?.upload_count ?? 0} />
            <FeedMetric label="Recent" value={metrics?.recent_upload_count ?? 0} />
            <FeedMetric label="Validation Fail" value={metrics?.validation_failure_count ?? 0} />
            <FeedMetric label="Import Fail" value={metrics?.import_failure_count ?? 0} />
            <FeedMetric label="Stale Feeds" value={metrics?.stale_feed_count ?? 0} />
            <FeedMetric label="Duplicates" value={metrics?.duplicate_attempt_count ?? 0} />
          </div>

          {operations.alerts.length ? (
            <div className="grid gap-2">
              {operations.alerts.map((alert) => (
                <div
                  key={alert.key}
                  className="grid gap-1 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone={alert.severity}>{alert.title}</StatusBadge>
                    <p className="text-sm font-semibold text-panel-strong">{alert.message}</p>
                  </div>
                  <p className="text-sm leading-6 text-panel-muted">{alert.recommended_action}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-6 text-panel-muted">
              No repeated import failures, overdue critical feeds, or stuck source-data tasks are active.
            </p>
          )}

          <div className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 text-sm text-panel-muted">
            <p>
              Cleanup task: <span className="font-semibold text-panel-strong">{operations.retention.cleanup_task_name}</span>
            </p>
            <p>
              Next artifact expiry:{" "}
              <span className="font-semibold text-panel-strong">
                {operations.retention.next_artifact_expiry_at
                  ? formatRelativeTimestamp(operations.retention.next_artifact_expiry_at)
                  : "No raw artifacts queued"}
              </span>
            </p>
            <p>{operations.production_controls.audit_review_reference}</p>
          </div>
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Production health metrics will appear after the operations endpoint loads.
        </p>
      )}
    </Card>
  );
}

function ImportConfirmation({ upload }: { upload?: SourceDataUploadBatchRecord }) {
  const queryClient = useQueryClient();
  const [approvalReason, setApprovalReason] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [allowDuplicateReplay, setAllowDuplicateReplay] = useState(false);
  const riskCategory = inferredRiskCategory(upload);
  const isReady = upload?.status === "ready_for_confirmation" && upload.validation_status === "passed";
  const needsApproval = Boolean(riskCategory && upload?.approval_status !== "approved");
  const canConfirm = Boolean(isReady && !needsApproval);
  const canCancel = Boolean(
    upload &&
      ["draft", "uploaded", "validation_failed", "ready_for_confirmation", "import_failed"].includes(upload.status),
  );

  const refreshSourceData = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.sourceData.root() });
  };

  const approvalMutation = useMutation({
    mutationFn: ({ action, reason }: { action: "request" | "approve" | "reject"; reason?: string }) => {
      if (!upload) {
        throw new Error("Select an upload before changing approval.");
      }
      return approveSourceDataUploadViaBff(upload.public_id, { action, reason });
    },
    onSuccess: refreshSourceData,
  });

  const confirmMutation = useMutation({
    mutationFn: () => {
      if (!upload) {
        throw new Error("Select an upload before confirming import.");
      }
      return confirmSourceDataUploadViaBff(upload.public_id, { allow_duplicate_replay: allowDuplicateReplay });
    },
    onSuccess: refreshSourceData,
  });

  const cancelMutation = useMutation({
    mutationFn: () => {
      if (!upload) {
        throw new Error("Select an upload before cancelling it.");
      }
      return cancelSourceDataUploadViaBff(upload.public_id, { reason: cancelReason });
    },
    onSuccess: async () => {
      setCancelReason("");
      await refreshSourceData();
    },
  });

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <ShieldCheck className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Import Confirmation</h2>
      </div>

      {upload ? (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={statusTone(upload.import_status)}>{formatLabel(upload.import_status)}</StatusBadge>
            <StatusBadge tone={statusTone(upload.approval_status)}>{formatLabel(upload.approval_status)}</StatusBadge>
            {riskCategory ? <StatusBadge tone="warning">{formatLabel(riskCategory)}</StatusBadge> : null}
          </div>

          {riskCategory ? (
            <div className="grid gap-3">
              <label className="grid gap-2 text-sm font-semibold text-panel-copy">
                Approval reason
                <textarea
                  value={approvalReason}
                  onChange={(event) => setApprovalReason(event.target.value)}
                  rows={3}
                  className="rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 py-2 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
                />
              </label>
              <div className="flex flex-wrap gap-3">
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  disabled={approvalMutation.isPending || !approvalReason.trim()}
                  onClick={() => approvalMutation.mutate({ action: "request", reason: approvalReason })}
                >
                  Request Approval
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  disabled={approvalMutation.isPending || upload.approval_status !== "pending"}
                  onClick={() => approvalMutation.mutate({ action: "approve", reason: approvalReason })}
                >
                  Approve
                </Button>
                <Button
                  type="button"
                  variant="danger"
                  size="md"
                  disabled={approvalMutation.isPending || upload.approval_status !== "pending"}
                  onClick={() => approvalMutation.mutate({ action: "reject", reason: approvalReason })}
                >
                  Reject
                </Button>
              </div>
            </div>
          ) : null}

          {upload.duplicate_of_public_id ? (
            <label className="flex items-center gap-3 text-sm font-semibold text-panel-copy">
              <input
                type="checkbox"
                checked={allowDuplicateReplay}
                onChange={(event) => setAllowDuplicateReplay(event.target.checked)}
                className="size-4 rounded border-panel-table-wrap"
              />
              Confirm this duplicate as an intentional replay
            </label>
          ) : null}

          <Button
            type="button"
            variant="primary"
            size="md"
            className="w-fit"
            disabled={!canConfirm || confirmMutation.isPending}
            onClick={() => confirmMutation.mutate()}
          >
            <CheckCircle2 className="size-4" aria-hidden="true" />
            Confirm Import
          </Button>

          <div className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <label className="grid gap-2 text-sm font-semibold text-panel-copy">
              Cancel reason
              <textarea
                value={cancelReason}
                onChange={(event) => setCancelReason(event.target.value)}
                rows={2}
                className="rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 py-2 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
              />
            </label>
            <Button
              type="button"
              variant="danger"
              size="md"
              className="w-fit"
              disabled={!canCancel || cancelMutation.isPending || !cancelReason.trim()}
              onClick={() => cancelMutation.mutate()}
            >
              <AlertTriangle className="size-4" aria-hidden="true" />
              Cancel Upload
            </Button>
          </div>

          {approvalMutation.error || confirmMutation.error || cancelMutation.error ? (
            <p className="text-sm font-semibold text-[color:var(--danger)]">
              {(approvalMutation.error ?? confirmMutation.error ?? cancelMutation.error) instanceof Error
                ? (approvalMutation.error ?? confirmMutation.error ?? cancelMutation.error)?.message
                : "Source-data import action failed."}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Select a validated upload to confirm import or request maker-checker approval.
        </p>
      )}
    </Card>
  );
}

function ImportResult({ upload }: { upload?: SourceDataUploadBatchRecord }) {
  const importSummary = (upload?.metadata.import_summary ?? {}) as Record<string, unknown>;

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <Database className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Import Result</h2>
      </div>

      {upload ? (
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <FeedMetric label="Run Type" value={upload.domain_ingestion_run_type || "Not linked"} />
            <FeedMetric label="Run ID" value={upload.domain_ingestion_run_id ?? "Pending"} />
            <FeedMetric label="Confirmed By" value={upload.confirmed_by_username ?? "Not confirmed"} />
          </div>
          {importSummary.error_summary ? (
            <div className="grid gap-2 rounded-[0.5rem] border border-[color-mix(in_srgb,var(--danger)_24%,white)] px-3 py-2 text-sm">
              <p className="font-semibold text-[color:var(--danger)]">{String(importSummary.error_summary)}</p>
              <p className="font-semibold text-panel-copy">
                Retry path: correct the source CSV, run Dry Validate again, then Confirm Import. For a corrected file,
                use the replacement option in the upload wizard so the failed batch stays auditable.
              </p>
            </div>
          ) : null}
          <div className="grid gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-muted">Event Timeline</h3>
            <div className="grid gap-2">
              {upload.events.slice(0, 8).map((event) => (
                <div
                  key={event.id}
                  className="grid gap-1 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 sm:grid-cols-[1fr_auto]"
                >
                  <p className="text-sm font-semibold text-panel-strong">{formatLabel(event.event_type)}</p>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
                    {formatRelativeTimestamp(event.event_at)}
                  </p>
                </div>
              ))}
              {!upload.events.length ? (
                <p className="text-sm text-panel-muted">No upload events have been recorded yet.</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Imported batches will show their linked ingestion run, counts, and audit timeline here.
        </p>
      )}
    </Card>
  );
}

function nextPredictionDateForUpload(upload: SourceDataUploadBatchRecord) {
  const anchorValue = upload.reporting_period_end ?? upload.source_timestamp ?? upload.confirmed_at ?? upload.created_at;
  const anchor = new Date(anchorValue);
  if (Number.isNaN(anchor.getTime())) {
    return new Date().toISOString().slice(0, 10);
  }
  anchor.setUTCDate(anchor.getUTCDate() + 1);
  return anchor.toISOString().slice(0, 10);
}

function sourceCutoffTimestampForUpload(upload: SourceDataUploadBatchRecord) {
  const sourceTimestamp = upload.source_timestamp;
  if (!sourceTimestamp) {
    throw new Error("This upload does not have a source timestamp for downstream cutoff evidence.");
  }
  const cutoff = new Date(sourceTimestamp);
  if (Number.isNaN(cutoff.getTime())) {
    throw new Error("This upload does not have a usable source timestamp for downstream cutoff evidence.");
  }
  return cutoff.toISOString();
}

function downstreamPayloadForAction(
  upload: SourceDataUploadBatchRecord,
  action: SourceDataDownstreamActionDefinition,
) {
  const payload: SourceDataDownstreamActionPayload = {
    action_key: action.action_key,
    as_of: sourceCutoffTimestampForUpload(upload),
  };
  if (action.action_key === "regenerate_surveillance_labels") {
    payload.dataset_role = "evaluation";
  }
  if (action.action_key === "rebuild_lead_time_features") {
    payload.prediction_date = nextPredictionDateForUpload(upload);
  }
  return payload;
}

function DownstreamActionsPanel({ upload }: { upload?: SourceDataUploadBatchRecord }) {
  const queryClient = useQueryClient();
  const actions = upload?.downstream_actions ?? [];
  const isImported = upload?.status === "imported" && upload.import_status === "imported";

  const downstreamMutation = useMutation({
    mutationFn: (action: SourceDataDownstreamActionDefinition) => {
      if (!upload) {
        throw new Error("Select an imported upload before running a downstream action.");
      }
      return runSourceDataDownstreamActionViaBff(upload.public_id, downstreamPayloadForAction(upload, action));
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sourceData.root() });
    },
  });

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <RefreshCcw className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Downstream Actions</h2>
      </div>

      <div className="mb-4 grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 text-sm text-panel-muted">
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone="info">Scheduled scoring 06:00</StatusBadge>
          <StatusBadge tone="default">No SMS</StatusBadge>
          <StatusBadge tone="default">No model promotion</StatusBadge>
        </div>
        <p>Manual risk scoring remains behind system readiness gates; this panel only rebuilds evidence or records audits.</p>
      </div>

      {upload && isImported ? (
        <div className="grid gap-3">
          {actions.map((action) => {
            const latestEvidence = (action.latest_result?.evidence ?? {}) as Record<string, unknown>;
            const datasetRef = typeof latestEvidence.dataset_ref === "string" ? latestEvidence.dataset_ref : "";
            return (
              <div
                key={action.action_key}
                className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 lg:grid-cols-[1fr_auto] lg:items-center"
              >
                <div className="grid gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-panel-strong">{action.label}</p>
                    {action.recommended ? <StatusBadge tone="success">Recommended</StatusBadge> : null}
                    <StatusBadge tone={action.availability_status === "available" ? "success" : "default"}>
                      {formatLabel(action.availability_status)}
                    </StatusBadge>
                    {action.latest_result ? (
                      <StatusBadge tone={statusTone(action.latest_result.action_status)}>
                        {formatLabel(action.latest_result.action_status)}
                      </StatusBadge>
                    ) : null}
                  </div>
                  <p className="text-sm leading-6 text-panel-muted">
                    {action.availability_status === "available" ? action.safe_reason : action.unavailable_reason}
                  </p>
                  {datasetRef ? (
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
                      Dataset {datasetRef}
                    </p>
                  ) : null}
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  disabled={action.availability_status !== "available" || downstreamMutation.isPending}
                  onClick={() => downstreamMutation.mutate(action)}
                >
                  <RefreshCcw className="size-4" aria-hidden="true" />
                  Run
                </Button>
              </div>
            );
          })}
          {!actions.length ? (
            <p className="text-sm text-panel-muted">No downstream actions are registered for this upload.</p>
          ) : null}
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Downstream actions become available after an import completes successfully.
        </p>
      )}

      {downstreamMutation.error ? (
        <p className="mt-4 text-sm font-semibold text-[color:var(--danger)]">
          {downstreamMutation.error instanceof Error
            ? downstreamMutation.error.message
            : "Source-data downstream action failed."}
        </p>
      ) : null}
    </Card>
  );
}

function UploadHistory({
  uploads,
  feeds,
  filters,
  selectedPublicId,
  onSelect,
  onFiltersChange,
}: {
  uploads: SourceDataUploadBatchRecord[];
  feeds: SourceDataFeedDefinition[];
  filters: SourceDataUploadFilters;
  selectedPublicId: string | null;
  onSelect: (publicId: string) => void;
  onFiltersChange: (filters: SourceDataUploadFilters) => void;
}) {
  function updateFilter(key: keyof SourceDataUploadFilters, value: string) {
    onFiltersChange({ ...filters, [key]: value || undefined });
  }

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <FileSpreadsheet className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Recent Uploads</h2>
      </div>
      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <label className="grid gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
          Feed
          <select
            value={filters.feed_key ?? ""}
            onChange={(event) => updateFilter("feed_key", event.target.value)}
            className="h-10 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm normal-case tracking-normal text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
          >
            <option value="">All feeds</option>
            {feeds.map((feed) => (
              <option key={feed.feed_key} value={feed.feed_key}>
                {feed.label}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
          Status
          <select
            value={filters.status ?? ""}
            onChange={(event) => updateFilter("status", event.target.value)}
            className="h-10 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm normal-case tracking-normal text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
          >
            <option value="">All statuses</option>
            <option value="uploaded">Uploaded</option>
            <option value="ready_for_confirmation">Ready</option>
            <option value="confirming">Confirming</option>
            <option value="imported">Imported</option>
            <option value="import_failed">Failed</option>
          </select>
        </label>
        <label className="grid gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted md:col-span-2">
          Source search
          <input
            value={filters.source_name ?? ""}
            onChange={(event) => updateFilter("source_name", event.target.value)}
            placeholder="Filter by source name"
            className="h-10 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm normal-case tracking-normal text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
          />
        </label>
      </div>
      <div className="overflow-x-auto rounded-[0.5rem] border border-[var(--dashboard-table-line)]">
        <table className="w-full min-w-[760px] text-left text-sm">
          <caption className="sr-only">Recent source-data uploads</caption>
          <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_64%,transparent)] text-xs uppercase text-panel-muted">
            <tr>
              <th className="px-3 py-2">Feed</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Rows</th>
              <th className="px-3 py-2">Created</th>
            </tr>
          </thead>
          <tbody>
            {uploads.map((upload) => (
              <tr
                key={upload.public_id}
                className={`cursor-pointer border-t border-[var(--dashboard-table-line)] ${
                  upload.public_id === selectedPublicId ? "bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_62%,transparent)]" : ""
                }`}
                onClick={() => onSelect(upload.public_id)}
              >
                <td className="px-3 py-2 font-semibold text-panel-strong">{formatLabel(upload.feed_key)}</td>
                <td className="px-3 py-2 text-panel-muted">{upload.source_name}</td>
                <td className="px-3 py-2">
                  <StatusBadge tone={statusTone(upload.status)}>{formatLabel(upload.status)}</StatusBadge>
                </td>
                <td className="px-3 py-2 text-panel-muted">{upload.row_count}</td>
                <td className="px-3 py-2 text-panel-muted">{formatRelativeTimestamp(upload.created_at)}</td>
              </tr>
            ))}
            {!uploads.length ? (
              <tr>
                <td className="px-3 py-4 text-panel-muted" colSpan={5}>
                  No source-data uploads yet. Download a template, fill the CSV, then create an upload above.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SourceDataContent() {
  const { currentUser } = useAuth();
  const { data, isLoading, isError, error, refetch, isFetching } = useSourceDataFeedTypesQuery();
  const overviewQuery = useSourceDataOverviewQuery();
  const operationsQuery = useSourceDataOperationsQuery();
  const [selectedUploadId, setSelectedUploadId] = useState<string | null>(null);
  const [uploadFilters, setUploadFilters] = useState<SourceDataUploadFilters>({ limit: 20 });
  const uploadsQuery = useSourceDataUploadsQuery(uploadFilters);
  const latestUploadId = uploadsQuery.data?.results[0]?.public_id ?? null;
  const activeUploadId = selectedUploadId ?? latestUploadId;
  const selectedUploadQuery = useSourceDataUploadQuery(activeUploadId);
  const contractErrors = data?.template_contract_errors ?? [];
  const mvpFeeds = data?.feeds ?? [];
  const selectedUpload = selectedUploadQuery.data ?? uploadsQuery.data?.results.find((item) => item.public_id === activeUploadId);
  const canManageImports = currentUser?.role === "ADMIN" || currentUser?.role === "SUPERVISOR";
  const groupedFeeds = useMemo(() => {
    return mvpFeeds.reduce<Record<string, SourceDataFeedDefinition[]>>((groups, feed) => {
      groups[feed.domain] = [...(groups[feed.domain] ?? []), feed];
      return groups;
    }, {});
  }, [mvpFeeds]);

  return (
    <div className="grid gap-6">
      <DashboardTopbar
        title="Source Data"
        subtitle="Versioned CSV feed contracts and source intake templates"
        lastUpdatedLabel={data?.generated_at ? `Updated ${formatRelativeTimestamp(data.generated_at)}` : "Not loaded"}
        lastUpdatedTone={contractErrors.length ? "stale" : "default"}
        onRefresh={() => {
          void refetch();
          void overviewQuery.refetch();
          void operationsQuery.refetch();
        }}
      >
        <Button
          variant="secondary"
          size="md"
          onClick={() => {
            void refetch();
            void overviewQuery.refetch();
            void operationsQuery.refetch();
          }}
          disabled={isFetching || overviewQuery.isFetching || operationsQuery.isFetching}
        >
          <RefreshCcw className="size-4" aria-hidden="true" />
          Refresh
        </Button>
      </DashboardTopbar>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <FreshnessPanel
          sources={overviewQuery.data?.freshness.sources ?? []}
          generatedAt={overviewQuery.data?.generated_at}
        />
        <SourceGapsPanel gaps={overviewQuery.data?.source_gaps ?? []} />
      </section>

      <OperationsHealthPanel operations={operationsQuery.data} />

      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <UploadWizard
          feeds={mvpFeeds}
          recentUploads={uploadsQuery.data?.results ?? []}
          selectedUpload={selectedUpload}
          canManageImports={canManageImports}
          onUploadSelected={setSelectedUploadId}
        />
        <ValidationSummary upload={selectedUpload} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <ImportConfirmation upload={selectedUpload} />
        <ImportResult upload={selectedUpload} />
      </section>

      <DownstreamActionsPanel upload={selectedUpload} />

      <UploadHistory
        uploads={uploadsQuery.data?.results ?? []}
        feeds={mvpFeeds}
        filters={uploadFilters}
        selectedPublicId={activeUploadId}
        onSelect={setSelectedUploadId}
        onFiltersChange={(filters) => setUploadFilters({ ...filters, limit: 20 })}
      />

      <section className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
        <Card className="p-5">
          <div className="mb-4 flex items-center gap-3">
            <Database className="size-5 text-brand" aria-hidden="true" />
            <h1 className="text-xl font-semibold text-panel-strong">Feed Registry</h1>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <FeedMetric label="MVP Feeds" value={data?.feed_count ?? 0} />
            <FeedMetric label="Template Errors" value={contractErrors.length} />
            <FeedMetric label="Scope" value={data?.scope ? formatLabel(data.scope) : "Loading"} />
          </div>
        </Card>

        <Card className="p-5">
          <div className="mb-4 flex items-center gap-3">
            <ShieldCheck className="size-5 text-brand" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-panel-strong">Template Safety</h2>
          </div>
          {contractErrors.length ? (
            <div className="grid gap-2">
              {contractErrors.map((item) => (
                <div key={item} className="rounded-[0.5rem] border border-[color-mix(in_srgb,var(--danger)_24%,white)] px-3 py-2 text-sm font-semibold text-[color:var(--danger)]">
                  {item}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-6 text-panel-muted">
              Published templates passed contract checks for supported source feeds.
            </p>
          )}
        </Card>
      </section>

      {isLoading ? (
        <Card className="p-5">
          <div className="flex items-center gap-3 text-sm font-semibold text-panel-muted">
            <FileSpreadsheet className="size-4" aria-hidden="true" />
            Loading source-data templates...
          </div>
        </Card>
      ) : null}

      {isError ? (
        <Card className="p-5">
          <div className="flex items-start gap-3 text-sm text-[color:var(--danger)]">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p>{error instanceof Error ? error.message : "Unable to load source-data feed types."}</p>
          </div>
        </Card>
      ) : null}

      <section className="grid gap-4">
        {Object.entries(groupedFeeds).map(([domain, feeds]) => (
          <div key={domain} className="grid gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-muted">
            {formatLabel(domain)}
          </h2>
          {feeds.map((feed) => (
              <FeedCard key={feed.feed_key} feed={feed} canManageImports={canManageImports} />
          ))}
        </div>
      ))}
        {!isLoading && !mvpFeeds.length && !isError ? (
          <Card className="p-5">
            <p className="text-sm text-panel-muted">No source-data feeds are currently exposed.</p>
          </Card>
        ) : null}
      </section>
    </div>
  );
}

export default function SourceDataPage() {
  return (
    <RoleGate
      allowedRoles={[...ALLOWED_ROLES]}
      title="Source data access is restricted"
      message="Source-data templates and feed metadata are available to administrators, supervisors, and analysts."
    >
      <SourceDataContent />
    </RoleGate>
  );
}
