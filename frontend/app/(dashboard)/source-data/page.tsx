"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
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
  X,
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
  type SourceDataFreshnessStatus,
  type SourceDataFreshnessSource,
  type SourceDataOperationsResponse,
  type SourceDataUploadBatchRecord,
  type SourceDataUploadFilters,
} from "@/lib/dashboard";
import { hasActionCapability } from "@/lib/capabilities";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { queryKeys } from "@/lib/query-keys";
import {
  useSourceDataFeedTypesQuery,
  useSourceDataOperationsQuery,
  useSourceDataOverviewQuery,
  useSourceDataUploadQuery,
  useSourceDataUploadsQuery,
} from "@/queries/use-source-data-query";

const CLIENT_MAX_CSV_FILE_BYTES = 20 * 1024 * 1024;

type DataReadinessTab = "overview" | "review" | "history" | "templates";

const DATA_READINESS_TABS: Array<{ id: DataReadinessTab; label: string; description: string }> = [
  { id: "overview", label: "Overview", description: "Main priorities" },
  { id: "review", label: "Review update", description: "Check and add" },
  { id: "history", label: "Recent updates", description: "Previous files" },
  { id: "templates", label: "Sources & templates", description: "Registered feeds" },
];

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
  artifact_hash_mismatch: "Upload the file again from the original export so the check and dashboard update use the same file.",
  artifact_missing: "Upload the file again; the previous file is no longer available.",
  binary_file_detected: "Export the source as plain UTF-8 CSV and upload that file.",
  duplicate_header: "Keep one copy of the column, then download a fresh template if needed.",
  duplicate_file_hash: "Confirm this is an intentional repeat, or upload the corrected file.",
  duplicate_snapshot: "Keep only one current row per facility and reported_at timestamp.",
  duplicate_snapshot_in_file: "Remove the repeated facility snapshot row and validate again.",
  duplicate_upload_metadata: "Update the file date, or mark this as an intentional replacement.",
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
  no_data_rows: "Keep the header row and add at least one data row.",
  no_case_counts_or_outbreak_label: "Enter a case count or outbreak label for each surveillance row.",
  pii_email_value_detected: "Remove direct identifiers; source diagnostics must use aggregate or coded data only.",
  pii_header_detected: "Remove personal-information columns such as names, phone numbers, or IDs.",
  pii_identifier_value_detected: "Replace direct identifiers with approved facility, ward, or source references.",
  pii_phone_value_detected: "Remove phone numbers from the CSV before upload.",
  row_limit_exceeded: "Split the file into smaller CSV uploads.",
  service_disruption_reported: "This is a warning; review the facility context before importing.",
  stale_report: "This is a warning; confirm the older report is still the intended source.",
  stockout_detected: "This is a warning; review the stockout flags before importing.",
  unknown_column: "Remove the extra column or ask for the template to be updated.",
  unknown_facility_code: "Check the facility code against the county facility register.",
  unknown_ward_code: "Check the ward code against the Migori ward register.",
  unexpected_content_type: "Upload a CSV file with a CSV content type.",
  unsupported_file_extension: "Upload a .csv file exported from the template.",
  unsafe_text_value_detected: "Remove names, contacts, identifiers, exact locations, and clinical notes from the CSV.",
};

function formatLabel(value: string | null | undefined) {
  if (!value) {
    return "Not reported";
  }
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function feedBackendKey(feed: Partial<SourceDataFeedDefinition> | null | undefined) {
  const value = typeof feed?.feed_key === "string" ? feed.feed_key.trim() : "";
  return value || null;
}

function feedKeyValue(feed: Partial<SourceDataFeedDefinition> | null | undefined, fallback = "unkeyed-feed") {
  return feedBackendKey(feed) ?? fallback;
}

function feedLabelValue(feed: Partial<SourceDataFeedDefinition> | null | undefined) {
  const value = typeof feed?.label === "string" ? feed.label.trim() : "";
  return value || "Unnamed data feed";
}

function feedDomainValue(feed: Partial<SourceDataFeedDefinition> | null | undefined) {
  const value = typeof feed?.domain === "string" ? feed.domain.trim() : "";
  return value || "unclassified";
}

function cadenceLabel(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "Not reported";
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

const ATTENTION_STATUS_PRIORITY: Record<SourceDataFreshnessStatus, number> = {
  failed: 0,
  missing: 1,
  stale: 2,
  demo_backed: 3,
  due_soon: 4,
  current: 5,
};

const SOURCE_STATUS_COPY: Record<string, string> = {
  current: "Up to date",
  due_soon: "Due soon",
  stale: "Needs update",
  missing: "Missing",
  demo_backed: "Using demo data",
  failed: "Needs review",
};

const SOURCE_TRUTH_COPY: Record<string, string> = {
  api_backed: "Automatic source",
  csv_backed: "Manual file",
  fallback: "Temporary file",
  demo_backed: "Demo data",
  seeded_demo: "Demo data",
  proxy: "Proxy data",
  missing: "Not available",
  derived: "Calculated from data",
};

const UPDATE_STATUS_COPY: Record<string, string> = {
  draft: "Draft",
  uploaded: "Uploaded",
  validating: "Checking file",
  validation_failed: "Needs fixes",
  ready_for_confirmation: "Checked and ready",
  confirming: "Adding to dashboard",
  imported: "Added",
  import_failed: "Update failed",
  cancelled: "Cancelled",
  superseded: "Replaced",
  not_started: "Not started",
  running: "In progress",
  passed: "Passed",
  failed: "Failed",
  not_required: "No review needed",
  pending: "Review requested",
  approved: "Reviewed",
  rejected: "Rejected",
  expired: "Expired",
  completed: "Completed",
  queued: "Queued",
  available: "Available",
  unavailable: "Unavailable",
};

const METADATA_COPY: Record<string, string> = {
  source_name: "Source name",
  source_timestamp: "File date",
  reporting_period_start: "Period start",
  reporting_period_end: "Period end",
  release_version: "Release version",
  source_ref: "Source reference",
  correction_mode: "Correction type",
  operator_note: "Note",
};

function friendlyStatusLabel(status: string) {
  return status ? SOURCE_STATUS_COPY[status] ?? formatLabel(status) : "Not reported";
}

function friendlyTruthLabel(value: string) {
  return value ? SOURCE_TRUTH_COPY[value] ?? formatLabel(value) : "Not reported";
}

function friendlyUpdateStatusLabel(value: string) {
  return value ? UPDATE_STATUS_COPY[value] ?? formatLabel(value) : "Not reported";
}

function friendlyFieldLabel(value: string) {
  return value ? METADATA_COPY[value] ?? formatLabel(value) : "Not reported";
}

function friendlyModeLabel(value?: string, csvUploadEnabled?: boolean) {
  if (!value) {
    return "Not reported";
  }
  if (value === "api") {
    return "Automatic updates";
  }
  if (value === "demo") {
    return "Demo data";
  }
  if (value === "manual" || value === "csv") {
    return "Manual upload";
  }
  if (value === "fallback") {
    return csvUploadEnabled === false ? "Manual upload paused" : "Manual backup";
  }
  if (value === "manual" || value === "csv") {
    return csvUploadEnabled === false ? "Manual upload paused" : "Manual upload";
  }
  return formatLabel(value);
}

function friendlyActionText(value: string | null | undefined) {
  if (!value) {
    return "Not available from the backend.";
  }
  return value
    .replaceAll("source-data feeds", "data items")
    .replaceAll("Source-data feeds", "Data items")
    .replaceAll("source-data feed", "data item")
    .replaceAll("Source-data feed", "Data item")
    .replaceAll("source-data", "data")
    .replaceAll("Source-data", "Data")
    .replaceAll("CSV", "file")
    .replaceAll("demo/proxy", "demo")
    .replaceAll("production source", "trusted source")
    .replaceAll("feed import", "data update")
    .replaceAll("feeds", "data items")
    .replaceAll("model-ops", "quality")
    .replaceAll("model ops", "quality")
    .replaceAll("feature dataset", "prediction inputs")
    .replaceAll("feature datasets", "prediction inputs")
    .replaceAll("active scoring pipeline", "current risk scoring")
    .replaceAll("source records", "saved data")
    .replace(/\bpromote a model\b/gi, "change risk scoring")
    .replace(/\bpromotes a model\b/gi, "changes risk scoring")
    .replace(/\bmutate\b/gi, "change")
    .replace(/\bper-row cutoff proof\b/gi, "timestamp check")
    .replace(/^Download the template and upload\s+/i, "Upload ")
    .replace(/^Upload or refresh\s+/i, "Upload a newer file for ")
    .replace(/^Configure or run the source path for\s+/i, "Set up or upload ")
    .replace(/\.$/, ".");
}

function friendlyAlertTitle(value: string | null | undefined) {
  if (!value) {
    return "Operational alert";
  }
  if (value.toLowerCase().includes("overdue critical")) {
    return "Important data needs update";
  }
  return friendlyActionText(value);
}

function friendlyActionLabel(value: string | null | undefined) {
  if (!value) {
    return "Not available from the backend.";
  }
  if (value.includes("surveillance")) {
    return "Refresh risk labels and dashboard inputs";
  }
  if (value.includes("population_exposure")) {
    return "Refresh population and exposure inputs";
  }
  if (value.includes("exposure")) {
    return "Refresh exposure inputs";
  }
  if (value.includes("spatial_facility") || value.includes("facility_forecast")) {
    return "Refresh facility evidence and forecasts";
  }
  if (value.includes("readiness")) {
    return "Refresh facility readiness and forecasts";
  }
  return formatLabel(value)
    .replaceAll("Then", "then")
    .replaceAll("Maker Checker", "Second Review")
    .replaceAll("Labels", "Risk labels")
    .replaceAll("Features", "Dashboard inputs")
    .replaceAll("Truth", "Status");
}

const DOWNSTREAM_ACTION_COPY: Record<
  string,
  {
    label: string;
    available: string;
    unavailable: string;
  }
> = {
  regenerate_surveillance_labels: {
    label: "Refresh surveillance summaries",
    available: "Updates the related surveillance view using the checked file. It will not send messages or change risk scoring.",
    unavailable: "Not needed for this type of update.",
  },
  rebuild_lead_time_features: {
    label: "Refresh prediction inputs",
    available: "Prepares the latest data for risk views. It will not send messages or change risk scoring.",
    unavailable: "Not needed for this type of update.",
  },
  recompute_facility_readiness_evidence: {
    label: "Refresh facility readiness evidence",
    available: "Updates facility readiness evidence used by dashboard views. It will not send messages or change risk scoring.",
    unavailable: "Not needed for this type of update.",
  },
  run_source_and_model_ops_audits: {
    label: "Run quality review",
    available: "Checks the update history and saves a review note. It will not change dashboard data.",
    unavailable: "Not needed for this type of update.",
  },
  run_source_model_ops_audits: {
    label: "Run quality review",
    available: "Checks the update history and saves a review note. It will not change dashboard data.",
    unavailable: "Not needed for this type of update.",
  },
};

function friendlyDownstreamActionLabel(action: SourceDataDownstreamActionDefinition) {
  const actionKey = action.action_key ?? "";
  const actionLabel = action.label ?? "";
  if (actionKey.toLowerCase().includes("audit") || actionLabel.toLowerCase().includes("audit")) {
    return "Run quality review";
  }
  return DOWNSTREAM_ACTION_COPY[actionKey]?.label ?? friendlyActionText(actionLabel);
}

function friendlyDownstreamActionDetail(action: SourceDataDownstreamActionDefinition) {
  const actionKey = action.action_key ?? "";
  const actionLabel = action.label ?? "";
  const copy = DOWNSTREAM_ACTION_COPY[actionKey];
  if (actionKey.toLowerCase().includes("audit") || actionLabel.toLowerCase().includes("audit")) {
    return "Checks this update and saves a review note. It will not change dashboard data.";
  }
  if (action.availability_status === "available") {
    return copy?.available ?? friendlyActionText(action.safe_reason);
  }
  return copy?.unavailable ?? friendlyActionText(action.unavailable_reason || "Not needed for this type of update.");
}

function connectorStatusLabel(status: string) {
  if (!status) {
    return "Not reported";
  }
  if (status === "not_configured") {
    return "Needs setup";
  }
  if (status === "skipped") {
    return "Waiting";
  }
  if (status === "configured") {
    return "Ready";
  }
  if (status === "success") {
    return "Updated";
  }
  if (status === "failed") {
    return "Needs review";
  }
  if (status === "disabled") {
    return "Paused";
  }
  return formatLabel(status);
}

function scopeLabel(scope?: string) {
  if (!scope) {
    return "Not loaded";
  }
  if (scope === "mvp") {
    return "Pilot set";
  }
  return formatLabel(scope);
}

function needsAttention(status: SourceDataFreshnessStatus) {
  return ["failed", "missing", "stale", "demo_backed"].includes(status);
}

function inferredRiskCategory(upload?: SourceDataUploadBatchRecord) {
  if (!upload) {
    return "";
  }
  if (upload.approval_risk_category) {
    return upload.approval_risk_category;
  }
  if (upload.metadata?.duplicate_file_sha256 && upload.metadata?.duplicate_metadata_upload_public_id) {
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
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function hasRequiredOperationsMetrics(metrics: unknown) {
  if (!metrics || typeof metrics !== "object" || Array.isArray(metrics)) {
    return false;
  }
  const record = metrics as Record<string, unknown>;
  const requiredNumericKeys = [
    "upload_count",
    "recent_upload_count",
    "validation_failure_count",
    "import_failure_count",
    "stale_feed_count",
    "duplicate_attempt_count",
  ];
  return requiredNumericKeys.every((key) => numberFromRecord(record[key]) !== null)
    && Boolean(record.status_counts && typeof record.status_counts === "object" && !Array.isArray(record.status_counts));
}

function metricValue(value: unknown, fallback = "Not available"): string | number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return fallback;
}

function timestampValue(value: string | null | undefined) {
  if (!value || !hasValidTimestamp(value)) {
    return "Not available";
  }
  return formatRelativeTimestamp(value);
}

function hasValidTimestamp(value: string | null | undefined) {
  return Boolean(value && !Number.isNaN(new Date(value).getTime()));
}

function periodValue(start: string | null | undefined, end: string | null | undefined) {
  if (start && end) {
    return `${start} to ${end}`;
  }
  if (start) {
    return `From ${start}`;
  }
  if (end) {
    return `Through ${end}`;
  }
  return "Not available";
}

function readinessValidationSummary(upload?: SourceDataUploadBatchRecord) {
  if (!upload || upload.feed_key !== "facility_readiness_snapshot") {
    return null;
  }
  const validationSummary = upload.metadata?.validation_summary as Record<string, unknown> | undefined;
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

function percent(value: unknown, total: unknown) {
  if (
    typeof value !== "number" || !Number.isFinite(value)
    || typeof total !== "number" || !Number.isFinite(total)
    || total <= 0
  ) {
    return null;
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

function ProgressBar({ label, value }: { label: string; value: number | null }) {
  const hasValue = typeof value === "number" && Number.isFinite(value);
  const boundedValue = hasValue ? Math.max(0, Math.min(100, value)) : 0;
  return (
    <div className="grid gap-1">
      <div className="flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
        <span>{label}</span>
        <span>{hasValue ? `${boundedValue}%` : "Not available"}</span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-pill bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)]"
        {...(hasValue
          ? {
              role: "progressbar",
              "aria-label": label,
              "aria-valuemin": 0,
              "aria-valuemax": 100,
              "aria-valuenow": boundedValue,
            }
          : { "aria-label": `${label}: Not available` })}
      >
        {hasValue ? <div className="h-full rounded-pill bg-brand" style={{ width: `${boundedValue}%` }} /> : null}
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
    errors.feed_key = "Choose the data type before uploading.";
  }
  if (!sourceName.trim()) {
    errors.source_name = "Enter where this file came from.";
  }
  if (!sourceTimestamp) {
    errors.source_timestamp = "Choose the file date and time.";
  } else if (Number.isNaN(new Date(sourceTimestamp).getTime())) {
    errors.source_timestamp = "Use a valid file date and time.";
  }
  if (!file) {
    errors.file = "Choose a file saved from the template.";
  } else {
    const fileName = file.name.toLowerCase();
    const csvContentTypes = ["", "text/csv", "application/csv", "application/vnd.ms-excel"];
    if (!fileName.endsWith(".csv") || !csvContentTypes.includes(file.type)) {
      errors.file = "Choose a .csv file. Save Excel workbooks as CSV before upload.";
    } else if (file.size > CLIENT_MAX_CSV_FILE_BYTES) {
      errors.file = "This file is over 20 MB. Split it into smaller files before uploading.";
    }
  }
  if (requiresReportingPeriod && !reportingPeriodStart) {
    errors.reporting_period_start = "Enter the first date covered by this file.";
  }
  if (requiresReportingPeriod && !reportingPeriodEnd) {
    errors.reporting_period_end = "Enter the last date covered by this file.";
  }
  if (reportingPeriodStart && reportingPeriodEnd && reportingPeriodStart > reportingPeriodEnd) {
    errors.reporting_period_end = "Period end must be on or after the start date.";
  }
  if (replacementMode && !(replacementReason ?? "").trim()) {
    errors.replacement_reason = "Explain why this file replaces the selected update.";
  }
  return errors;
}

function TemplateDownloadButton({ feed }: { feed: SourceDataFeedDefinition }) {
  const feedKey = feedBackendKey(feed);
  if (!feed.template_url || !feedKey) {
    return (
      <span className="inline-flex h-10 items-center justify-center rounded-pill border border-[var(--dashboard-table-line)] px-3 text-sm font-semibold text-panel-muted">
        Template not available
      </span>
    );
  }

  return (
    <a
      href={`/api/dashboard/source-data/templates/${encodeURIComponent(feedKey)}`}
      className="inline-flex h-10 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
    >
      <Download className="size-4" aria-hidden="true" />
      Download template
    </a>
  );
}

function templateHelpText(feed: SourceDataFeedDefinition) {
  const columns = new Set(feed.accepted_columns ?? []);
  if (columns.has("ward_code") && columns.has("ward_name") && !columns.has("facility_code")) {
    return "The downloaded file already lists all 40 Migori wards. Fill the blank cells for each ward.";
  }
  if (columns.has("ward_code") && columns.has("ward_name")) {
    return "Ward name sits beside ward code so the file is easier to check before upload.";
  }
  return "Use this file as the starting point, then save it as CSV before upload.";
}

function DataReadinessTabs({
  activeTab,
  onTabChange,
}: {
  activeTab: DataReadinessTab;
  onTabChange: (tab: DataReadinessTab) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-[0.75rem] border border-[var(--dashboard-table-line)] bg-panel p-1" role="tablist" aria-label="Data readiness views">
      <div className="grid min-w-[720px] grid-cols-4 gap-1">
        {DATA_READINESS_TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const tabId = `source-data-tab-${tab.id}`;
          const panelId = `source-data-panel-${tab.id}`;
          return (
            <button
              key={tab.id}
              id={tabId}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={panelId}
              tabIndex={isActive ? 0 : -1}
              className={`rounded-[0.6rem] px-3 py-3 text-left transition ${
                isActive
                  ? "bg-[var(--dashboard-nav-hover)] text-panel-strong shadow-sm"
                  : "text-panel-muted hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_44%,transparent)] hover:text-panel-copy"
              }`}
              onClick={() => onTabChange(tab.id)}
            >
              <span className="block text-sm font-semibold">{tab.label}</span>
              <span className="mt-1 block text-xs leading-5">{tab.description}</span>
            </button>
          );
        })}
      </div>
    </div>
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

function FeedCard({
  feed,
  freshness,
  canUseSourceDataAdminControls,
}: {
  feed: SourceDataFeedDefinition;
  freshness?: SourceDataFreshnessSource;
  canUseSourceDataAdminControls: boolean;
}) {
  const queryClient = useQueryClient();
  const connector = feed.connector_status;
  const csvUploadEnabled = feed.csv_upload_enabled;
  const feedKey = feedBackendKey(feed);
  const feedModeMutation = useMutation({
    mutationFn: () => {
      if (!feedKey) {
        throw new Error("Feed mode cannot be changed because the feed key was not returned.");
      }
      return updateSourceDataFeedModeViaBff(feedKey, {
        feed_mode: csvUploadEnabled ? "api" : "fallback",
        csv_upload_enabled: !csvUploadEnabled,
        authoritative_connector_key: connector?.connector_key || undefined,
        reason: csvUploadEnabled
          ? "API connector marked authoritative for routine source refresh."
          : "CSV fallback re-enabled for corrections and source-gap recovery.",
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sourceData.root() });
    },
  });

  return (
    <Card className="grid gap-4 p-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-start">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <StatusBadge tone="info">{formatLabel(feedDomainValue(feed))}</StatusBadge>
            <StatusBadge tone={feed.feed_mode === "api" ? "success" : csvUploadEnabled === false ? "warning" : "info"}>
              {friendlyModeLabel(feed.feed_mode, csvUploadEnabled)}
            </StatusBadge>
            <StatusBadge tone={freshness ? sourceStatusTone(freshness.status) : "default"}>
              {freshness ? friendlyStatusLabel(freshness.status) : "Freshness not loaded"}
            </StatusBadge>
            {feed.requires_new_ingestion_path ? <StatusBadge tone="warning">Needs setup</StatusBadge> : null}
          </div>
          <h2 className="text-lg font-semibold text-panel-strong">{feedLabelValue(feed)}</h2>
          <p className="mt-1 text-sm leading-6 text-panel-muted">{feed.adapter_notes || "Feed description not returned."}</p>
          <p className="mt-2 text-sm leading-6 text-panel-copy">
            {freshness?.recommended_action || "The backend has not returned a corrective action for this feed."}
          </p>
          <p className="mt-2 text-sm leading-6 text-panel-copy">{templateHelpText(feed)}</p>
        </div>
        <TemplateDownloadButton feed={feed} />
      </div>

      <details open className="group rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
        <summary className="cursor-pointer text-sm font-semibold text-panel-copy marker:text-panel-muted">
          Source and template details
        </summary>

        <div className="mt-3 grid gap-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <FeedMetric label="Domain" value={formatLabel(feedDomainValue(feed))} />
            <FeedMetric label="Update rhythm" value={cadenceLabel(feed.cadence)} />
            <FeedMetric label="Update mode" value={friendlyModeLabel(feed.feed_mode, csvUploadEnabled)} />
            <FeedMetric label="Source truth" value={freshness ? friendlyTruthLabel(freshness.truth_state) : "Not loaded"} />
            <FeedMetric label="Freshness" value={freshness ? friendlyStatusLabel(freshness.status) : "Not loaded"} />
            <FeedMetric
              label="Last source timestamp"
              value={timestampValue(freshness?.last_source_timestamp)}
            />
            <FeedMetric label="Template" value={feed.template_url ? "Available" : "Not available"} />
            <FeedMetric label="Columns to fill" value={metricValue(feed.accepted_columns?.length)} />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Details to include</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {feed.required_metadata?.length ? feed.required_metadata.map((field) => (
                  <span
                    key={field}
                    className="rounded-pill bg-[color-mix(in_srgb,var(--dashboard-table-line)_68%,transparent)] px-2.5 py-1 text-xs font-semibold text-panel-copy"
                  >
                    {friendlyFieldLabel(field)}
                  </span>
                )) : <span className="text-sm text-panel-muted">No required metadata returned.</span>}
              </div>
            </div>
            <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Recommended corrective action</p>
              <p className="mt-2 text-sm font-semibold text-panel-strong">
                {freshness?.recommended_action || "Not available from the backend."}
              </p>
              <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">After dashboard use</p>
              <p className="mt-1 text-sm text-panel-copy">{friendlyActionLabel(feed.downstream_action)}</p>
            </div>
          </div>

          <div className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 md:grid-cols-[1fr_auto] md:items-center">
            {connector?.connector_key ? (
              <div className="grid gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-panel-strong">Automatic update: {connector.label}</p>
                  <StatusBadge tone={connectorTone(connector.status)}>{connectorStatusLabel(connector.status)}</StatusBadge>
                  <StatusBadge tone={connector.enabled ? "success" : "warning"}>
                    {connector.enabled ? "Enabled" : "Disabled"}
                  </StatusBadge>
                  <StatusBadge tone={connector.configured ? "success" : "warning"}>
                    {connector.configured ? "Configured" : "Not configured"}
                  </StatusBadge>
                </div>
                <p className="text-sm leading-6 text-panel-muted">{connector.notes}</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
                  <span>Last run: {timestampValue(connector.last_run_at)}</span>
                  <span>Last run status: {connectorStatusLabel(connector.last_run_status)}</span>
                  <span>Last successful run: {timestampValue(connector.last_successful_fetch_at)}</span>
                </div>
              </div>
            ) : (
              <div className="grid gap-1">
                <p className="font-semibold text-panel-strong">Connector: Not registered</p>
                <p className="text-sm leading-6 text-panel-muted">
                  The backend did not return a connector for this feed. Use the manual file path if it is enabled.
                </p>
              </div>
            )}
            {canUseSourceDataAdminControls && feedKey && connector?.connector_key ? (
              <Button
                type="button"
                variant="secondary"
                size="md"
                disabled={
                  csvUploadEnabled === undefined
                  || !connector.enabled
                  || !connector.configured
                  || feedModeMutation.isPending
                }
                onClick={() => feedModeMutation.mutate()}
              >
                {csvUploadEnabled === undefined
                  ? "Manual upload status unavailable"
                  : csvUploadEnabled
                  ? "Pause manual upload"
                  : "Allow manual upload"}
              </Button>
            ) : null}
          </div>
        </div>
      </details>
    </Card>
  );
}

function UploadWizard({
  feeds,
  recentUploads,
  selectedUpload,
  canManageImports,
  onUploadSelected,
  onCompleted,
}: {
  feeds: SourceDataFeedDefinition[];
  recentUploads: SourceDataUploadBatchRecord[];
  selectedUpload?: SourceDataUploadBatchRecord;
  canManageImports: boolean;
  onUploadSelected: (publicId: string) => void;
  onCompleted?: () => void;
}) {
  const queryClient = useQueryClient();
  const [feedKey, setFeedKey] = useState(feedBackendKey(feeds[0]) ?? "");
  const [sourceName, setSourceName] = useState("");
  const [sourceTimestamp, setSourceTimestamp] = useState("");
  const [reportingPeriodStart, setReportingPeriodStart] = useState("");
  const [reportingPeriodEnd, setReportingPeriodEnd] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [replacementMode, setReplacementMode] = useState(false);
  const [replacementReason, setReplacementReason] = useState("");

  const selectedFeed = feeds.find((feed) => feedBackendKey(feed) === feedKey) ?? feeds[0];
  const requiresReportingPeriod = selectedFeed?.required_metadata?.some((field) =>
    ["reporting_period_start", "reporting_period_end"].includes(field),
  ) ?? false;
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
      onCompleted?.();
      await queryClient.invalidateQueries({ queryKey: queryKeys.sourceData.root() });
    },
  });

  const validateMutation = useMutation({
    mutationFn: validateSourceDataUploadViaBff,
    onSuccess: async (upload) => {
      onUploadSelected(upload.public_id);
      onCompleted?.();
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
        <h2 className="text-lg font-semibold text-panel-strong">File details</h2>
      </div>

      <form className="grid gap-4" onSubmit={handleSubmit}>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            Data type
            <select
              value={feedKey}
              onChange={(event) => {
                setFeedKey(event.target.value);
                setSubmitAttempted(false);
              }}
              aria-invalid={Boolean(showError("feed_key"))}
              aria-describedby="source-data-feed-error"
              className="h-11 w-full min-w-0 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              {feeds.map((feed, index) => (
                <option
                  key={feedKeyValue(feed, `unkeyed-feed-${index}`)}
                  value={feedBackendKey(feed) ?? ""}
                  disabled={!feedBackendKey(feed)}
                >
                  {feedLabelValue(feed)}
                </option>
              ))}
            </select>
            <FieldMessage id="source-data-feed-error" message={showError("feed_key")} />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            Where did this file come from?
            <input
              value={sourceName}
              onChange={(event) => setSourceName(event.target.value)}
              placeholder="Migori DHIS2"
              aria-invalid={Boolean(showError("source_name"))}
              aria-describedby="source-data-source-name-error"
              className="h-11 w-full min-w-0 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            />
            <FieldMessage id="source-data-source-name-error" message={showError("source_name")} />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            File date and time
            <input
              type="datetime-local"
              value={sourceTimestamp}
              onChange={(event) => setSourceTimestamp(event.target.value)}
              aria-invalid={Boolean(showError("source_timestamp"))}
              aria-describedby="source-data-source-timestamp-error"
              className="h-11 w-full min-w-0 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            />
            <FieldMessage id="source-data-source-timestamp-error" message={showError("source_timestamp")} />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            File
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              aria-invalid={Boolean(showError("file"))}
              aria-describedby="source-data-file-error"
              className="h-11 w-full min-w-0 max-w-full rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 py-2 text-sm text-panel-strong outline-none file:mr-3 file:rounded-pill file:border-0 file:bg-[var(--dashboard-icon-button-surface)] file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-panel-copy focus-visible:ring-2 focus-visible:ring-brand/30"
            />
            <FieldMessage id="source-data-file-error" message={showError("file")} />
          </label>
        </div>

        {lastUploadForFeed ? (
          <div className="flex flex-wrap items-center gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 text-sm text-panel-muted">
            <span className="font-semibold text-panel-strong">Last used details</span>
            <span>{lastUploadForFeed.source_name}</span>
            <span>{timestampValue(lastUploadForFeed.source_timestamp)}</span>
            <Button type="button" variant="secondary" size="sm" onClick={applyLastMetadata}>
              Use last details
            </Button>
          </div>
        ) : null}

        {requiresReportingPeriod ? (
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-semibold text-panel-copy">
              Period start
              <input
                type="date"
                value={reportingPeriodStart}
                onChange={(event) => setReportingPeriodStart(event.target.value)}
                aria-invalid={Boolean(showError("reporting_period_start"))}
                aria-describedby="source-data-reporting-start-error"
                className="h-11 w-full min-w-0 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
              />
              <FieldMessage id="source-data-reporting-start-error" message={showError("reporting_period_start")} />
            </label>
            <label className="grid gap-2 text-sm font-semibold text-panel-copy">
              Period end
              <input
                type="date"
                value={reportingPeriodEnd}
                onChange={(event) => setReportingPeriodEnd(event.target.value)}
                aria-invalid={Boolean(showError("reporting_period_end"))}
                aria-describedby="source-data-reporting-end-error"
                className="h-11 w-full min-w-0 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
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
              This file replaces the selected update
            </label>
            {replacementMode ? (
              <label className="grid gap-2 text-sm font-semibold text-panel-copy">
                Why is this replacing it?
                <textarea
                  value={replacementReason}
                  onChange={(event) => setReplacementReason(event.target.value)}
                  rows={3}
                  aria-invalid={Boolean(showError("replacement_reason"))}
                  aria-describedby="source-data-replacement-reason-error"
                  className="w-full min-w-0 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 py-2 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
                />
                <FieldMessage id="source-data-replacement-reason-error" message={showError("replacement_reason")} />
              </label>
            ) : null}
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
              The original update stays visible for review.
            </p>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={uploadMutation.isPending || validateMutation.isPending}
          >
            <Upload className="size-4" aria-hidden="true" />
            {uploadMutation.isPending ? "Uploading…" : "Upload file"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="md"
            disabled={!selectedUpload || uploadMutation.isPending || validateMutation.isPending}
            onClick={() => selectedUpload && validateMutation.mutate(selectedUpload.public_id)}
          >
            <ShieldCheck className="size-4" aria-hidden="true" />
            {validateMutation.isPending ? "Checking…" : "Check file"}
          </Button>
          {selectedFeed ? <TemplateDownloadButton feed={selectedFeed} /> : null}
        </div>

        <p className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 text-sm leading-6 text-panel-muted">
          Upload and Check file are separate steps. Checking only validates the file; it does not send alerts, change
          model approval, or alter risk scores. Dashboard use requires a separate review and confirmation.
        </p>

        {uploadMutation.isPending || validateMutation.isPending ? (
          <p className="text-sm font-semibold text-panel-copy" role="status" aria-live="polite">
            {uploadMutation.isPending ? "Uploading the file. It will not be added to the dashboard automatically." : "Checking the file. Keep this panel open while validation runs."}
          </p>
        ) : null}

        {uploadMutation.error || validateMutation.error ? (
          <p className="text-sm font-semibold text-[color:var(--danger)]" role="alert">
            {(uploadMutation.error ?? validateMutation.error) instanceof Error
              ? (uploadMutation.error ?? validateMutation.error)?.message
              : "We could not upload or check this file."}
          </p>
        ) : null}
      </form>
    </Card>
  );
}

function UploadDrawer({
  isOpen,
  feeds,
  recentUploads,
  selectedUpload,
  canManageImports,
  onUploadSelected,
  onClose,
}: {
  isOpen: boolean;
  feeds: SourceDataFeedDefinition[];
  recentUploads: SourceDataUploadBatchRecord[];
  selectedUpload?: SourceDataUploadBatchRecord;
  canManageImports: boolean;
  onUploadSelected: (publicId: string) => void;
  onClose: () => void;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCloseRef.current();
      }
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown);
    closeButtonRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      if (previouslyFocused?.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[100001] flex justify-end bg-black/40 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-data-drawer-title"
      aria-describedby="source-data-drawer-description"
    >
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close add data panel" onClick={onClose} />
      <aside className="relative z-10 h-full w-full max-w-[720px] overflow-y-auto border-l border-[var(--dashboard-table-line)] bg-panel p-4 shadow-2xl sm:p-6">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Data update</p>
            <h2 id="source-data-drawer-title" className="mt-1 text-xl font-semibold text-panel-strong">
              Add New Data
            </h2>
            <p id="source-data-drawer-description" className="mt-1 text-sm leading-6 text-panel-muted">
              Upload one trusted file, check it, then review the result before adding it to the dashboard.
            </p>
          </div>
          <button
            type="button"
            ref={closeButtonRef}
            className="inline-flex size-10 items-center justify-center rounded-pill border border-panel-table-wrap text-panel-copy transition hover:bg-[var(--dashboard-nav-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            aria-label="Close add data panel"
            onClick={onClose}
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>

        <UploadWizard
          feeds={feeds}
          recentUploads={recentUploads}
          selectedUpload={selectedUpload}
          canManageImports={canManageImports}
          onUploadSelected={onUploadSelected}
          onCompleted={onClose}
        />
      </aside>
    </div>
  );
}

function UploadProgressTimeline({ upload }: { upload: SourceDataUploadBatchRecord }) {
  const latestDownstreamAction = (upload.metadata?.latest_downstream_action ?? {}) as Record<string, unknown>;
  const latestDownstreamStatus =
    typeof latestDownstreamAction.action_status === "string" ? latestDownstreamAction.action_status : "";
  const steps = [
    {
      key: "upload",
      label: "Upload",
      value: "File received",
      tone: "success" as const,
    },
    {
      key: "validation",
      label: "File check",
      value: friendlyUpdateStatusLabel(upload.validation_status),
      tone: statusTone(upload.validation_status),
    },
    {
      key: "approval",
      label: "Review",
      value: friendlyUpdateStatusLabel(upload.approval_status),
      tone: statusTone(upload.approval_status),
    },
    {
      key: "import",
      label: "Dashboard update",
      value: friendlyUpdateStatusLabel(upload.import_status),
      tone: statusTone(upload.import_status),
    },
    {
      key: "downstream",
      label: "Related views",
      value: latestDownstreamStatus ? friendlyUpdateStatusLabel(latestDownstreamStatus) : upload.status === "imported" ? "Ready" : "Waiting",
      tone: latestDownstreamStatus ? statusTone(latestDownstreamStatus) : upload.status === "imported" ? ("warning" as const) : ("default" as const),
    },
  ];

  return (
    <ol className="grid gap-2 sm:grid-cols-5" aria-label="Data update progress">
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
  const rowCount = numberFromRecord(upload.row_count);
  const acceptedCount = numberFromRecord(upload.accepted_count);
  const rejectedCount = numberFromRecord(upload.rejected_count);
  const warningCount = numberFromRecord(upload.warning_count);

  return (
    <div className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 sm:grid-cols-3">
      <ProgressBar label="Rows ready" value={percent(acceptedCount, rowCount)} />
      <ProgressBar label="Rows to fix" value={percent(rejectedCount, rowCount)} />
      <ProgressBar
        label="Warnings"
        value={percent(warningCount, rowCount !== null && warningCount !== null ? Math.max(rowCount, warningCount) : null)}
      />
    </div>
  );
}

function ValidationSummary({ upload }: { upload?: SourceDataUploadBatchRecord }) {
  const issues = Array.isArray(upload?.validation_issues) ? upload.validation_issues : [];
  const topIssues = issues.slice(0, 6);
  const readinessSummary = readinessValidationSummary(upload);
  const riskCategory = inferredRiskCategory(upload);
  const validationStatus = upload?.validation_status ?? "";
  const rowCount = numberFromRecord(upload?.row_count);
  const acceptedCount = numberFromRecord(upload?.accepted_count);
  const rejectedCount = numberFromRecord(upload?.rejected_count);
  const warningCount = numberFromRecord(upload?.warning_count);
  const hasValidationResult = Boolean(upload && validationStatus && validationStatus !== "not_started");

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <CheckCircle2 className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">File Check</h2>
      </div>

      {upload ? (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={statusTone(upload.status ?? "")}>{friendlyUpdateStatusLabel(upload.status ?? "")}</StatusBadge>
            <StatusBadge tone={statusTone(validationStatus)}>
              {friendlyUpdateStatusLabel(validationStatus)}
            </StatusBadge>
            {upload.duplicate_of_public_id ? <StatusBadge tone="warning">Repeated file</StatusBadge> : null}
          </div>

          <UploadProgressTimeline upload={upload} />

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <FeedMetric label="Source name" value={metricValue(upload.source_name)} />
            <FeedMetric label="File timestamp" value={timestampValue(upload.source_timestamp)} />
            <FeedMetric label="Reporting period" value={periodValue(upload.reporting_period_start, upload.reporting_period_end)} />
            <FeedMetric label="Import status" value={friendlyUpdateStatusLabel(upload.import_status ?? "")} />
            <FeedMetric label="Rows checked" value={metricValue(rowCount)} />
            <FeedMetric label="Rows ready" value={metricValue(acceptedCount)} />
            <FeedMetric label="Rows to fix" value={metricValue(rejectedCount)} />
            <FeedMetric label="Warnings" value={metricValue(warningCount)} />
            <FeedMetric
              label="Approval requirement"
              value={riskCategory || upload.approval_status !== "not_required" ? "Review required" : "No extra review"}
            />
            <FeedMetric label="Risk category" value={riskCategory ? formatLabel(riskCategory) : "Not reported"} />
            <FeedMetric
              label="Duplicate / replacement"
              value={upload.duplicate_of_public_id ? "Repeated file" : upload.replaces_upload_public_id ? "Replacement" : "Original upload"}
            />
            <FeedMetric label="Confirmation status" value={friendlyUpdateStatusLabel(upload.status ?? "")} />
          </div>

          <RowCountVisuals upload={upload} />

          {readinessSummary ? (
            <div className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-semibold text-panel-strong">Facility Coverage</p>
                <StatusBadge tone="info">
                  {numberFromRecord(readinessSummary.facility_coverage_percent) !== null
                    ? `${numberFromRecord(readinessSummary.facility_coverage_percent)}% facilities`
                    : "Coverage not reported"}
                </StatusBadge>
              </div>
              <ProgressBar
                label="Facility coverage"
                value={numberFromRecord(readinessSummary.facility_coverage_percent)}
              />
              <div className="grid gap-3 sm:grid-cols-4">
                <FeedMetric label="Facilities" value={metricValue(numberFromRecord(readinessSummary.facilities_reported))} />
                <FeedMetric label="Old reports" value={metricValue(numberFromRecord(readinessSummary.stale_report_count))} />
                <FeedMetric label="Stockouts" value={metricValue(numberFromRecord(readinessSummary.stockout_facility_count))} />
                <FeedMetric label="Disruptions" value={metricValue(numberFromRecord(readinessSummary.service_disruption_count))} />
              </div>
            </div>
          ) : null}

          {topIssues.length ? (
            <div className="overflow-x-auto rounded-[0.5rem] border border-[var(--dashboard-table-line)]">
              <table className="w-full min-w-[760px] text-left text-sm">
                <caption className="sr-only">File issues to fix</caption>
                <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_64%,transparent)] text-xs uppercase text-panel-muted">
                  <tr>
                    <th className="px-3 py-2">Row</th>
                    <th className="px-3 py-2">Level</th>
                    <th className="px-3 py-2">Issue</th>
                    <th className="px-3 py-2">How to fix it</th>
                  </tr>
                </thead>
                <tbody>
                  {topIssues.map((issue) => (
                    <tr key={issue.id} className="border-t border-[var(--dashboard-table-line)]">
                      <td className="px-3 py-2 text-panel-muted">{issue.row_number ?? "-"}</td>
                      <td className="px-3 py-2">
                        <StatusBadge tone={statusTone(issue.severity)}>{friendlyUpdateStatusLabel(issue.severity)}</StatusBadge>
                      </td>
                      <td className="px-3 py-2 font-semibold text-panel-strong">{formatLabel(issue.code)}</td>
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
              {hasValidationResult
                ? "No file issues were returned for this check. The backend did not report rows needing correction."
                : "No file issues are stored for the selected update. Upload a file, then run Check file to refresh this panel."}
              </p>
          )}

          {hasValidationResult ? (
            <a
              href={`/api/dashboard/source-data/uploads/${encodeURIComponent(upload.public_id)}/errors.csv`}
              className="inline-flex h-10 w-fit items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              <Download className="size-4" aria-hidden="true" />
              Download full error CSV{issues.length ? ` (${issues.length} issues)` : ""}
            </a>
          ) : null}
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Upload a file, then run Check file to see which rows are ready and which rows need fixes.
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
            {timestampValue(generatedAt)}
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
                  <StatusBadge tone={sourceStatusTone(source.status)}>{friendlyStatusLabel(source.status)}</StatusBadge>
                </td>
                <td className="px-3 py-2 text-panel-muted">{friendlyTruthLabel(source.truth_state)}</td>
                <td className="px-3 py-2 text-panel-muted">
                  {timestampValue(source.last_source_timestamp)}
                </td>
                <td className="px-3 py-2 text-panel-muted">
                  {source.recommended_action || "Not available from the backend."}
                </td>
              </tr>
            ))}
            {!sources.length ? (
              <tr>
                <td className="px-3 py-4 text-panel-muted" colSpan={5}>
                  No source freshness records were returned.
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
            <p className="text-sm text-panel-muted">
              {gap.recommended_action || "No corrective action was returned by the backend."}
            </p>
            {gap.feed_key ? (
              <a
                href={`/api/dashboard/source-data/templates/${encodeURIComponent(gap.feed_key)}`}
                className="inline-flex h-9 w-fit items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
              >
                <Download className="size-4" aria-hidden="true" />
                Template
              </a>
            ) : (
              <span className="text-sm text-panel-muted">Template not available.</span>
            )}
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

function SummaryTile({
  label,
  value,
  tone = "default",
  detail,
}: {
  label: string;
  value: string | number;
  tone?: "success" | "warning" | "danger" | "info" | "default";
  detail?: string;
}) {
  return (
    <Card className="grid gap-1 p-4">
      <StatusBadge tone={tone}>{label}</StatusBadge>
      <p className="text-2xl font-semibold text-panel-strong">{value}</p>
      {detail ? <p className="text-sm leading-6 text-panel-muted">{detail}</p> : null}
    </Card>
  );
}

function ReadinessSummaryCards({
  sources,
  uploads,
  feedCount,
  sourceState,
  uploadState,
}: {
  sources: SourceDataFreshnessSource[];
  uploads: SourceDataUploadBatchRecord[];
  feedCount: string | number;
  sourceState: "loading" | "error" | "ready";
  uploadState: "loading" | "error" | "ready";
}) {
  const sourceDataLoaded = sourceState === "ready";
  const uploadsLoaded = uploadState === "ready";
  const attentionCount = sources.filter((source) => needsAttention(source.status)).length;
  const currentCount = sources.filter((source) => source.status === "current").length;
  const demoCount = sources.filter((source) => source.status === "demo_backed").length;
  const readyUploadCount = uploads.filter((upload) => upload.status === "ready_for_confirmation").length;

  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Data readiness summary">
      <SummaryTile
        label="Needs attention"
        value={sourceDataLoaded ? attentionCount : "Not loaded"}
        tone={!sourceDataLoaded ? "default" : attentionCount ? "danger" : "success"}
        detail={!sourceDataLoaded ? "Source status is still loading or unavailable." : attentionCount ? "Start with the items below." : "All listed data is ready."}
      />
      <SummaryTile
        label="Up to date"
        value={sourceDataLoaded ? currentCount : "Not loaded"}
        tone={sourceDataLoaded ? "success" : "default"}
        detail={sourceDataLoaded ? "Ready for dashboard use." : "Source status is still loading or unavailable."}
      />
      <SummaryTile
        label="Using demo data"
        value={sourceDataLoaded ? demoCount : "Not loaded"}
        tone={!sourceDataLoaded ? "default" : demoCount ? "warning" : "success"}
        detail={!sourceDataLoaded ? "Source status is still loading or unavailable." : demoCount ? "Replace when trusted data is available." : "No demo data is active."}
      />
      <SummaryTile
        label="Ready to add"
        value={uploadsLoaded ? readyUploadCount : "Not loaded"}
        tone={!uploadsLoaded ? "default" : readyUploadCount ? "warning" : "info"}
        detail={uploadsLoaded ? `${feedCount} registered sources available.` : "Upload history is still loading or unavailable."}
      />
    </section>
  );
}

function AttentionPanel({
  sources,
  gaps,
  onTemplates,
}: {
  sources: SourceDataFreshnessSource[];
  gaps: Array<{
    feed_key: string;
    label: string;
    status: SourceDataFreshnessStatus;
    truth_state: string;
    recommended_action: string;
  }>;
  onTemplates: () => void;
}) {
  const gapFeedKeys = new Set(gaps.map((gap) => gap.feed_key));
  const attentionSources = sources
    .filter((source) => needsAttention(source.status))
    .sort((left, right) => ATTENTION_STATUS_PRIORITY[left.status] - ATTENTION_STATUS_PRIORITY[right.status]);
  const visibleSources = attentionSources.slice(0, 4);
  const hiddenCount = Math.max(0, attentionSources.length - visibleSources.length);

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <AlertTriangle className="size-5 text-[color:var(--warning)]" aria-hidden="true" />
          <div>
            <h2 className="text-lg font-semibold text-panel-strong">What Needs Attention</h2>
            <p className="mt-1 text-sm leading-6 text-panel-muted">
              Start here when data is missing, old, or still demo-based.
            </p>
          </div>
        </div>
        <StatusBadge tone={attentionSources.length ? "warning" : sources.length ? "success" : "default"}>
          {attentionSources.length ? `${attentionSources.length} to review` : sources.length ? "All clear" : "No status records"}
        </StatusBadge>
      </div>

      <div className="grid gap-3">
        {visibleSources.map((source) => (
          <div
            key={source.key}
            className="grid gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 md:grid-cols-[1fr_auto] md:items-center"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-semibold text-panel-strong">{source.label}</p>
                <StatusBadge tone={sourceStatusTone(source.status)}>{friendlyStatusLabel(source.status)}</StatusBadge>
                <StatusBadge tone="info">{friendlyTruthLabel(source.truth_state)}</StatusBadge>
              </div>
              <p className="mt-1 text-sm leading-6 text-panel-muted">{friendlyActionText(source.recommended_action)}</p>
              <p className="mt-1 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
                {formatLabel(source.domain)} · Last data{" "}
                {timestampValue(source.last_source_timestamp)}
              </p>
            </div>
            {source.feed_key || gapFeedKeys.has(source.feed_key) ? (
              <a
                href={`/api/dashboard/source-data/templates/${encodeURIComponent(source.feed_key)}`}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
              >
                <Download className="size-4" aria-hidden="true" />
                Download template
              </a>
            ) : null}
          </div>
        ))}

        {!visibleSources.length ? (
          <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-4">
            <p className="font-semibold text-panel-strong">
              {sources.length ? "All listed data is ready." : "No source status records were returned."}
            </p>
            <p className="mt-1 text-sm leading-6 text-panel-muted">
              {sources.length
                ? "New updates can still be added when a trusted source file is available."
                : "The backend returned a valid but empty source status set."}
            </p>
          </div>
        ) : null}

        {hiddenCount ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <p className="text-sm font-semibold text-panel-muted">
              {hiddenCount} more item{hiddenCount === 1 ? "" : "s"} also need attention.
            </p>
            <Button type="button" variant="secondary" size="sm" onClick={onTemplates}>
              View templates
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function QuickUpdateGuide({
  selectedUpload,
  canManageImports,
  onAddData,
  onReviewData,
}: {
  selectedUpload?: SourceDataUploadBatchRecord;
  canManageImports: boolean;
  onAddData: () => void;
  onReviewData: () => void;
}) {
  const readyForDashboard = selectedUpload?.status === "ready_for_confirmation" && selectedUpload.validation_status === "passed";

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <Upload className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Add Data Safely</h2>
      </div>

      <ol className="grid gap-3 text-sm text-panel-muted">
        {[
          "Download the right template.",
          "Fill the required details.",
          "Upload the file and check it.",
          "Add the checked file to the dashboard.",
        ].map((step, index) => (
          <li key={step} className="flex gap-3 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-pill bg-brand text-xs font-semibold text-white">
              {index + 1}
            </span>
            <span className="pt-1 font-semibold text-panel-copy">{step}</span>
          </li>
        ))}
      </ol>

      <div className="mt-4 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
        <p className="font-semibold text-panel-strong">
          {readyForDashboard ? "A checked file is ready to add." : "No checked file is waiting right now."}
        </p>
        <p className="mt-1 text-sm leading-6 text-panel-muted">
          {!canManageImports
            ? "Download templates and review current data status. Uploads are limited to operational data managers."
            : readyForDashboard
            ? "Review the file check, then add it to refresh dashboard data."
            : "Start with the side panel when you have a trusted file."}
        </p>
        {canManageImports ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" variant="primary" size="md" onClick={readyForDashboard ? onReviewData : onAddData}>
              {readyForDashboard ? "Review checked file" : "Add data"}
            </Button>
            {readyForDashboard ? (
              <Button type="button" variant="secondary" size="md" onClick={onAddData}>
                Upload another file
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function OperationsHealthPanel({
  operations,
  isLoading,
  isError,
  error,
  isFetching,
}: {
  operations?: SourceDataOperationsResponse;
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  isFetching?: boolean;
}) {
  const metrics = operations?.metrics;
  const worker = operations?.worker_health;
  const alerts = Array.isArray(operations?.alerts) ? operations.alerts : null;
  const stuckImports = Array.isArray(operations?.stuck_tasks?.imports) ? operations.stuck_tasks.imports : null;
  const stuckValidations = Array.isArray(operations?.stuck_tasks?.validations) ? operations.stuck_tasks.validations : null;
  const validationFailureCount = numberFromRecord(metrics?.validation_failure_count);
  const importFailureCount = numberFromRecord(metrics?.import_failure_count);
  const staleFeedCount = numberFromRecord(metrics?.stale_feed_count);
  const hasRequiredMetrics = hasRequiredOperationsMetrics(metrics);
  const hasFailureEvidence = validationFailureCount !== null && importFailureCount !== null
    ? validationFailureCount > 0 || importFailureCount > 0
    : true;
  const hasBlockingCondition = Boolean(
    alerts === null
    || alerts.length
    || worker?.status !== "current"
    || stuckImports === null
    || stuckValidations === null
    || stuckImports.length
    || stuckValidations.length
    || hasFailureEvidence
    || staleFeedCount === null
    || staleFeedCount > 0
    || !hasRequiredMetrics,
  );
  const hasRequiredEvidence = Boolean(
    hasValidTimestamp(operations?.generated_at)
    && worker
    && hasValidTimestamp(worker.latest_heartbeat_at)
    && metrics
    && hasRequiredMetrics
    && operations.stuck_tasks
    && Array.isArray(operations.alerts),
  );
  const isUnavailable = Boolean(isError && !operations) || (!operations && !isLoading);
  const isHealthy = Boolean(operations && !isError && !isUnavailable && hasRequiredEvidence && !hasBlockingCondition);
  const statusLabel = isLoading && !operations
    ? "Loading"
    : isUnavailable
    ? "Unavailable / not loaded"
    : isHealthy
    ? "Healthy/current"
    : "Degraded/review needed";
  const statusToneValue: "success" | "warning" | "default" = isHealthy ? "success" : isUnavailable ? "default" : "warning";
  const failureCount = validationFailureCount !== null && importFailureCount !== null
    ? validationFailureCount + importFailureCount
    : null;

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <ShieldCheck className="size-5 text-brand" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-panel-strong">Source Data Operations</h2>
        </div>
        <StatusBadge tone={statusToneValue}>{statusLabel}</StatusBadge>
      </div>

      {isError ? (
        <div className="mb-4 rounded-[0.5rem] border border-[color-mix(in_srgb,var(--danger)_24%,white)] px-3 py-2 text-sm text-[color:var(--danger)]" role="alert">
          {error instanceof Error ? error.message : "Source Data Operations could not be loaded. The feed registry remains available."}
        </div>
      ) : null}

      {operations ? (
        <div className="grid gap-4">
          {isFetching ? (
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted" role="status" aria-live="polite">
              Refreshing operations snapshot…
            </p>
          ) : null}
          <p className="text-sm leading-6 text-panel-muted">
            This status covers Source Data upload and validation operations. It does not indicate that CCHIS, its external
            connectors or its models are production ready.
          </p>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <FeedMetric label="Worker heartbeat" value={worker?.status ? formatLabel(worker.status) : "Not available"} />
            <FeedMetric label="Stuck validations" value={metricValue(stuckValidations?.length)} />
            <FeedMetric label="Stuck imports" value={metricValue(stuckImports?.length)} />
            <FeedMetric label="Recent failures" value={metricValue(failureCount)} />
            <FeedMetric label="Stale feeds" value={metricValue(staleFeedCount)} />
            <FeedMetric label="All updates" value={metricValue(metrics?.upload_count)} />
            <FeedMetric label="Recent updates" value={metricValue(metrics?.recent_upload_count)} />
            <FeedMetric label="Last heartbeat" value={timestampValue(worker?.latest_heartbeat_at)} />
          </div>

          <div className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 text-sm text-panel-muted">
            <p><span className="font-semibold text-panel-copy">Snapshot generated:</span> {timestampValue(operations.generated_at)}</p>
            <p><span className="font-semibold text-panel-copy">Latest worker task:</span> {worker?.latest_task_name || "Not available"}</p>
          </div>

          {alerts?.length ? (
            <div className="grid gap-2">
              {alerts.map((alert) => (
                <div
                  key={alert.key}
                  className="grid gap-1 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone={alert.severity}>{friendlyAlertTitle(alert.title)}</StatusBadge>
                    <p className="text-sm font-semibold text-panel-strong">{friendlyActionText(alert.message)}</p>
                  </div>
                  <p className="text-sm leading-6 text-panel-muted">{friendlyActionText(alert.recommended_action)}</p>
                </div>
              ))}
            </div>
          ) : alerts ? (
            <p className="text-sm leading-6 text-panel-muted">
              No operational alerts were returned by the backend.
            </p>
          ) : (
            <p className="text-sm leading-6 text-panel-muted">
              Operational alert details were not returned by the backend.
            </p>
          )}
        </div>
      ) : isLoading ? (
        <p className="text-sm leading-6 text-panel-muted" role="status" aria-live="polite">
          Loading Source Data Operations…
        </p>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Source Data Operations evidence is unavailable. Refresh when the operations endpoint is available.
        </p>
      )}
    </Card>
  );
}

function ImportConfirmation({
  upload,
  canManageImports,
  canApproveRiskyImports,
}: {
  upload?: SourceDataUploadBatchRecord;
  canManageImports: boolean;
  canApproveRiskyImports: boolean;
}) {
  const queryClient = useQueryClient();
  const [approvalReason, setApprovalReason] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [allowDuplicateReplay, setAllowDuplicateReplay] = useState(false);
  const riskCategory = inferredRiskCategory(upload);
  const isReady = upload?.status === "ready_for_confirmation" && upload.validation_status === "passed";
  const isAdded = upload?.status === "imported" && upload.import_status === "imported";
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
        throw new Error("Select an update before changing review status.");
      }
      return approveSourceDataUploadViaBff(upload.public_id, { action, reason });
    },
    onSuccess: refreshSourceData,
  });

  const confirmMutation = useMutation({
    mutationFn: () => {
      if (!upload) {
        throw new Error("Select an update before using it on the dashboard.");
      }
      return confirmSourceDataUploadViaBff(upload.public_id, { allow_duplicate_replay: allowDuplicateReplay });
    },
    onSuccess: refreshSourceData,
  });

  const cancelMutation = useMutation({
    mutationFn: () => {
      if (!upload) {
        throw new Error("Select an update before cancelling it.");
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
        <h2 className="text-lg font-semibold text-panel-strong">Dashboard use</h2>
      </div>

      {upload ? (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={statusTone(upload.import_status)}>{friendlyUpdateStatusLabel(upload.import_status)}</StatusBadge>
            <StatusBadge tone={statusTone(upload.approval_status)}>{friendlyUpdateStatusLabel(upload.approval_status)}</StatusBadge>
            {riskCategory ? <StatusBadge tone="warning">{formatLabel(riskCategory)}</StatusBadge> : null}
          </div>

          <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
            <p className="font-semibold text-panel-strong">
              {isAdded
                ? "This file is already used by the dashboard."
                : canConfirm
                  ? "This checked file is ready to use."
                  : needsApproval
                    ? "This file needs review before dashboard use."
                    : "This file is not ready for dashboard use yet."}
            </p>
            <p className="mt-1 text-sm leading-6 text-panel-muted">
              {isAdded
                ? "No action is needed here. The dashboard views now use this data."
                : canConfirm
                  ? "Use it when you want dashboard numbers, maps, and summaries to reflect this file."
                  : needsApproval
                    ? "Complete the review first, then the file can be used on the dashboard."
                    : "Run File Check first. When it passes, this section will show the next step."}
            </p>
          </div>

          {riskCategory ? (
            <div className="grid gap-3">
              <label className="grid gap-2 text-sm font-semibold text-panel-copy">
                Review note
                <textarea
                  value={approvalReason}
                  onChange={(event) => setApprovalReason(event.target.value)}
                  rows={3}
                  className="rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 py-2 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
                />
              </label>
              <div className="flex flex-wrap gap-3">
                {canManageImports ? (
                  <Button
                    type="button"
                    variant="secondary"
                    size="md"
                    disabled={approvalMutation.isPending || !approvalReason.trim()}
                    onClick={() => approvalMutation.mutate({ action: "request", reason: approvalReason })}
                  >
                    Request review
                  </Button>
                ) : null}
                {canApproveRiskyImports ? (
                  <>
                    <Button
                      type="button"
                      variant="secondary"
                      size="md"
                      disabled={approvalMutation.isPending || upload.approval_status !== "pending"}
                      onClick={() => approvalMutation.mutate({ action: "approve", reason: approvalReason })}
                    >
                      Mark reviewed
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
                  </>
                ) : null}
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
              This repeated file is intentional
            </label>
          ) : null}

          {!isAdded ? (
            <Button
              type="button"
              variant="primary"
              size="md"
              className="w-fit"
              disabled={!canManageImports || !canConfirm || confirmMutation.isPending}
              onClick={() => confirmMutation.mutate()}
            >
              <CheckCircle2 className="size-4" aria-hidden="true" />
              Use this file on dashboard
            </Button>
          ) : null}

          {canCancel ? (
            <div className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3">
              <label className="grid gap-2 text-sm font-semibold text-panel-copy">
                Reason for cancelling
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
                disabled={!canManageImports || cancelMutation.isPending || !cancelReason.trim()}
                onClick={() => cancelMutation.mutate()}
              >
                <AlertTriangle className="size-4" aria-hidden="true" />
                Cancel update
              </Button>
            </div>
          ) : null}

          {approvalMutation.error || confirmMutation.error || cancelMutation.error ? (
            <p className="text-sm font-semibold text-[color:var(--danger)]">
              {(approvalMutation.error ?? confirmMutation.error ?? cancelMutation.error) instanceof Error
                ? (approvalMutation.error ?? confirmMutation.error ?? cancelMutation.error)?.message
                : "We could not update this file."}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Select a checked file to decide whether dashboard views should use it.
        </p>
      )}
    </Card>
  );
}

function ImportResult({ upload }: { upload?: SourceDataUploadBatchRecord }) {
  const importSummary = (upload?.metadata?.import_summary ?? {}) as Record<string, unknown>;
  const events = Array.isArray(upload?.events) ? upload.events : [];

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <Database className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Update Result</h2>
      </div>

      {upload ? (
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <FeedMetric label="Update type" value={upload.domain_ingestion_run_type ? formatLabel(upload.domain_ingestion_run_type) : "Not added yet"} />
            <FeedMetric label="Reference" value={upload.domain_ingestion_run_id ?? "Pending"} />
            <FeedMetric label="Added by" value={upload.confirmed_by_username ?? "Not added yet"} />
          </div>
          {importSummary.error_summary ? (
            <div className="grid gap-2 rounded-[0.5rem] border border-[color-mix(in_srgb,var(--danger)_24%,white)] px-3 py-2 text-sm">
              <p className="font-semibold text-[color:var(--danger)]">{String(importSummary.error_summary)}</p>
              <p className="font-semibold text-panel-copy">
                Correct the file, run Check file again, then add it to the dashboard. For a corrected file, use the
                replacement option so the failed update stays visible.
              </p>
            </div>
          ) : null}
          <div className="grid gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-muted">Activity</h3>
            <div className="grid gap-2">
              {events.slice(0, 8).map((event) => (
                <div
                  key={event.id}
                  className="grid gap-1 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 sm:grid-cols-[1fr_auto]"
                >
                  <p className="text-sm font-semibold text-panel-strong">{formatLabel(event.event_type)}</p>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
                    {timestampValue(event.event_at)}
                  </p>
                </div>
              ))}
              {!events.length ? (
                <p className="text-sm text-panel-muted">No activity has been recorded yet.</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Completed updates will show who added the file and what changed.
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
    throw new Error("This update does not have a file date for refreshing related dashboard views.");
  }
  const cutoff = new Date(sourceTimestamp);
  if (Number.isNaN(cutoff.getTime())) {
    throw new Error("This update does not have a usable file date for refreshing related dashboard views.");
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

function DownstreamActionsPanel({
  upload,
  canTriggerDownstreamActions,
}: {
  upload?: SourceDataUploadBatchRecord;
  canTriggerDownstreamActions: boolean;
}) {
  const queryClient = useQueryClient();
  const actions = upload?.downstream_actions ?? [];
  const isImported = upload?.status === "imported" && upload.import_status === "imported";

  const downstreamMutation = useMutation({
    mutationFn: (action: SourceDataDownstreamActionDefinition) => {
      if (!upload) {
        throw new Error("Select a completed update before refreshing related dashboard views.");
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
        <h2 className="text-lg font-semibold text-panel-strong">Related dashboard updates</h2>
      </div>

      <div className="mb-4 grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] p-3 text-sm text-panel-muted">
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone="info">Daily refresh 06:00</StatusBadge>
          <StatusBadge tone="default">No messages sent</StatusBadge>
          <StatusBadge tone="default">No risk score changes</StatusBadge>
        </div>
        <p>These updates refresh related views only. They do not send messages or change risk scores.</p>
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
                    <p className="font-semibold text-panel-strong">{friendlyDownstreamActionLabel(action)}</p>
                    {action.recommended ? <StatusBadge tone="success">Recommended</StatusBadge> : null}
                    <StatusBadge tone={action.availability_status === "available" ? "success" : "default"}>
                      {friendlyUpdateStatusLabel(action.availability_status)}
                    </StatusBadge>
                    {action.latest_result ? (
                      <StatusBadge tone={statusTone(action.latest_result.action_status)}>
                        {friendlyUpdateStatusLabel(action.latest_result.action_status)}
                      </StatusBadge>
                    ) : null}
                  </div>
                  <p className="text-sm leading-6 text-panel-muted">{friendlyDownstreamActionDetail(action)}</p>
                  {datasetRef ? (
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
                      Reference {datasetRef}
                    </p>
                  ) : null}
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  disabled={!canTriggerDownstreamActions || action.availability_status !== "available" || downstreamMutation.isPending}
                  onClick={() => downstreamMutation.mutate(action)}
                >
                  <RefreshCcw className="size-4" aria-hidden="true" />
                  Update
                </Button>
              </div>
            );
          })}
          {!actions.length ? (
            <p className="text-sm text-panel-muted">No related dashboard updates are available for this file.</p>
          ) : null}
        </div>
      ) : (
        <p className="text-sm leading-6 text-panel-muted">
          Related dashboard updates become available after a file is added successfully.
        </p>
      )}

      {downstreamMutation.error ? (
        <p className="mt-4 text-sm font-semibold text-[color:var(--danger)]">
          {downstreamMutation.error instanceof Error
            ? downstreamMutation.error.message
            : "We could not refresh related dashboard views."}
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
  canFilterSourceName,
  isLoading,
  isError,
  error,
  isFetching,
  onSelect,
  onFiltersChange,
}: {
  uploads: SourceDataUploadBatchRecord[];
  feeds: SourceDataFeedDefinition[];
  filters: SourceDataUploadFilters;
  selectedPublicId: string | null;
  canFilterSourceName: boolean;
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  isFetching?: boolean;
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
        <h2 className="text-lg font-semibold text-panel-strong">Recent Data Updates</h2>
      </div>
      {isFetching ? (
        <p className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted" role="status" aria-live="polite">
          Refreshing upload history…
        </p>
      ) : null}
      {isError ? (
        <div className="mb-4 rounded-[0.5rem] border border-[color-mix(in_srgb,var(--danger)_24%,white)] px-3 py-2 text-sm text-[color:var(--danger)]" role="alert">
          {error instanceof Error ? error.message : "Upload history could not be loaded."}
        </div>
      ) : null}
      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <label className="grid gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
          Data type
          <select
            value={filters.feed_key ?? ""}
            onChange={(event) => updateFilter("feed_key", event.target.value)}
            className="h-10 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm normal-case tracking-normal text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
          >
            <option value="">All feeds</option>
            {feeds.map((feed, index) => (
              <option
                key={feedKeyValue(feed, `unkeyed-feed-${index}`)}
                value={feedBackendKey(feed) ?? ""}
                disabled={!feedBackendKey(feed)}
              >
                {feedLabelValue(feed)}
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
        {canFilterSourceName ? (
          <label className="grid gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted md:col-span-2">
            Search source
            <input
              value={filters.source_name ?? ""}
              onChange={(event) => updateFilter("source_name", event.target.value)}
              placeholder="Filter by source name"
              className="h-10 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm normal-case tracking-normal text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            />
          </label>
        ) : null}
      </div>
      <div className="overflow-x-auto rounded-[0.5rem] border border-[var(--dashboard-table-line)]">
        <table className="w-full min-w-[760px] text-left text-sm">
          <caption className="sr-only">Recent data updates</caption>
          <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_64%,transparent)] text-xs uppercase text-panel-muted">
            <tr>
              <th className="px-3 py-2">Data type</th>
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
                <td className="px-3 py-2 font-semibold text-panel-strong">
                  <button
                    type="button"
                    className="text-left underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
                    aria-current={upload.public_id === selectedPublicId ? "true" : undefined}
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelect(upload.public_id);
                    }}
                  >
                    {formatLabel(upload.feed_key)}
                  </button>
                </td>
                <td className="px-3 py-2 text-panel-muted">{metricValue(upload.source_name)}</td>
                <td className="px-3 py-2">
                  <StatusBadge tone={statusTone(upload.status)}>{friendlyUpdateStatusLabel(upload.status)}</StatusBadge>
                </td>
                <td className="px-3 py-2 text-panel-muted">{metricValue(upload.row_count)}</td>
                <td className="px-3 py-2 text-panel-muted">{timestampValue(upload.created_at)}</td>
              </tr>
            ))}
            {isLoading ? (
              <tr>
                <td className="px-3 py-4 text-panel-muted" colSpan={5}>
                  Loading upload history…
                </td>
              </tr>
            ) : !uploads.length && !isError ? (
              <tr>
                <td className="px-3 py-4 text-panel-muted" colSpan={5}>
                  No data updates yet. Download a template, fill it, then upload the file above.
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
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch, isFetching } = useSourceDataFeedTypesQuery();
  const overviewQuery = useSourceDataOverviewQuery();
  const operationsQuery = useSourceDataOperationsQuery();
  const [selectedUploadId, setSelectedUploadId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<DataReadinessTab>("overview");
  const [isUploadDrawerOpen, setIsUploadDrawerOpen] = useState(false);
  const [uploadFilters, setUploadFilters] = useState<SourceDataUploadFilters>({ limit: 20 });
  const uploadsQuery = useSourceDataUploadsQuery(uploadFilters);
  const latestUploadId = uploadsQuery.data?.results[0]?.public_id ?? null;
  const activeUploadId = selectedUploadId ?? latestUploadId;
  const selectedUploadQuery = useSourceDataUploadQuery(activeUploadId);
  const contractErrors = data?.template_contract_errors ?? [];
  const mvpFeeds = useMemo(() => data?.feeds ?? [], [data?.feeds]);
  const selectedUpload = selectedUploadQuery.data ?? uploadsQuery.data?.results.find((item) => item.public_id === activeUploadId);
  const canManageImports = hasActionCapability(currentUser, "manage_source_data_imports");
  const canApproveRiskyImports = hasActionCapability(currentUser, "approve_source_data_risky_imports");
  const canManageSourceDataFeedModes = currentUser?.role === "ADMIN";
  const canTriggerDownstreamActions = hasActionCapability(currentUser, "trigger_source_data_downstream_actions");
  const groupedFeeds = useMemo(() => {
    return mvpFeeds.reduce<Record<string, SourceDataFeedDefinition[]>>((groups, feed) => {
      const domain = feedDomainValue(feed);
      groups[domain] = [...(groups[domain] ?? []), feed];
      return groups;
    }, {});
  }, [mvpFeeds]);
  const recentUploads = uploadsQuery.data?.results ?? [];
  const freshnessByFeedKey = useMemo(() => {
    const sourceMap = new Map<string, SourceDataFreshnessSource>();
    for (const source of [
      ...(overviewQuery.data?.feed_statuses ?? []),
      ...(overviewQuery.data?.freshness?.sources ?? []),
    ]) {
      if (source.feed_key) {
        sourceMap.set(source.feed_key, source);
      }
    }
    return sourceMap;
  }, [overviewQuery.data?.feed_statuses, overviewQuery.data?.freshness?.sources]);
  const sourceState: "loading" | "error" | "ready" = overviewQuery.isError
    ? "error"
    : overviewQuery.data
    ? "ready"
    : "loading";
  const uploadState: "loading" | "error" | "ready" = uploadsQuery.isError
    ? "error"
    : uploadsQuery.data
    ? "ready"
    : "loading";
  const canAddData = canManageImports && !isLoading && mvpFeeds.length > 0;
  const handleUploadSelected = (publicId: string) => {
    setSelectedUploadId(publicId);
    setActiveTab("review");
  };
  const refreshSourceData = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.sourceData.root() });
    void Promise.allSettled([
      refetch(),
      overviewQuery.refetch?.(),
      operationsQuery.refetch?.(),
      uploadsQuery.refetch?.(),
      activeUploadId ? selectedUploadQuery.refetch?.() : undefined,
    ]);
  };
  const isRefreshing = Boolean(
    isFetching
    || overviewQuery.isFetching
    || operationsQuery.isFetching
    || uploadsQuery.isFetching
    || selectedUploadQuery.isFetching,
  );

  return (
    <div className="grid gap-6">
      <DashboardTopbar
        title="Data Readiness"
        subtitle="Check which data is up to date, upload new files, and safely add them to the dashboard"
        lastUpdatedLabel={timestampValue(data?.generated_at)}
        lastUpdatedTone={contractErrors.length ? "stale" : "default"}
        onRefresh={refreshSourceData}
      >
        {canAddData ? (
          <Button
            type="button"
            variant="primary"
            size="md"
            onClick={() => setIsUploadDrawerOpen(true)}
          >
            <Upload className="size-4" aria-hidden="true" />
            Add data
          </Button>
        ) : null}
        <Button
          variant="secondary"
          size="md"
          onClick={() => {
            refreshSourceData();
          }}
          disabled={isRefreshing}
        >
          <RefreshCcw className="size-4" aria-hidden="true" />
          Refresh
        </Button>
      </DashboardTopbar>

      <ReadinessSummaryCards
        sources={overviewQuery.data?.freshness?.sources ?? []}
        uploads={uploadsQuery.data?.results ?? []}
        feedCount={metricValue(data?.feed_count)}
        sourceState={sourceState}
        uploadState={uploadState}
      />

      <DataReadinessTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === "overview" ? (
        <div
          id="source-data-panel-overview"
          className="grid gap-6"
          role="tabpanel"
          aria-labelledby="source-data-tab-overview"
          tabIndex={0}
        >
          {overviewQuery.isLoading && !overviewQuery.data ? (
            <Card className="p-5" role="status" aria-live="polite">
              <p className="text-sm font-semibold text-panel-muted">Loading source freshness and gaps…</p>
            </Card>
          ) : null}
          {overviewQuery.isError ? (
            <Card className="p-5" role="alert">
              <div className="flex items-start gap-3 text-sm text-[color:var(--danger)]">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <p>
                  {overviewQuery.error instanceof Error
                    ? overviewQuery.error.message
                    : "Source status could not be loaded. The feed registry and operations status remain available."}
                </p>
              </div>
            </Card>
          ) : null}
          <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            {overviewQuery.data ? (
              <AttentionPanel
                sources={overviewQuery.data.freshness?.sources ?? []}
                gaps={overviewQuery.data.source_gaps ?? []}
                onTemplates={() => setActiveTab("templates")}
              />
            ) : (
              <Card className="p-5">
                <p className="text-sm leading-6 text-panel-muted">
                  Attention items will appear when the Source Data overview is available.
                </p>
              </Card>
            )}
            <QuickUpdateGuide
              selectedUpload={selectedUpload}
              canManageImports={canAddData}
              onAddData={() => setIsUploadDrawerOpen(true)}
              onReviewData={() => setActiveTab("review")}
            />
          </section>
          {overviewQuery.data ? (
            <>
              <FreshnessPanel
                sources={overviewQuery.data.freshness?.sources ?? []}
                generatedAt={overviewQuery.data.freshness?.generated_at}
              />
              <SourceGapsPanel gaps={overviewQuery.data.source_gaps ?? []} />
            </>
          ) : null}
          <OperationsHealthPanel
            operations={operationsQuery.data}
            isLoading={operationsQuery.isLoading}
            isError={operationsQuery.isError}
            error={operationsQuery.error}
            isFetching={operationsQuery.isFetching}
          />
        </div>
      ) : null}

      {activeTab === "review" ? (
        <div
          id="source-data-panel-review"
          className="grid gap-4"
          role="tabpanel"
          aria-labelledby="source-data-tab-review"
          tabIndex={0}
        >
          <Card className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-panel-strong">Selected update</h2>
                <p className="mt-1 text-sm leading-6 text-panel-muted">
                  {selectedUpload
                    ? `${formatLabel(selectedUpload.feed_key)} from ${metricValue(selectedUpload.source_name)}`
                    : "Choose a recent update or add a new file to begin."}
                </p>
              </div>
              {canAddData ? (
                <Button type="button" variant="primary" size="md" onClick={() => setIsUploadDrawerOpen(true)}>
                  <Upload className="size-4" aria-hidden="true" />
                  Add data
                </Button>
              ) : null}
            </div>
          </Card>

          {activeUploadId && selectedUploadQuery.isLoading && !selectedUpload ? (
            <Card className="p-5" role="status" aria-live="polite">
              <p className="text-sm font-semibold text-panel-muted">Loading the selected update…</p>
            </Card>
          ) : null}
          {selectedUploadQuery.isError ? (
            <Card className="p-5" role="alert">
              <p className="text-sm text-[color:var(--danger)]">
                {selectedUploadQuery.error instanceof Error
                  ? selectedUploadQuery.error.message
                  : "The selected update could not be loaded. Recent history remains available."}
              </p>
            </Card>
          ) : null}

          <ValidationSummary upload={selectedUpload} />

          <section className="grid gap-4 xl:grid-cols-2">
            <ImportConfirmation
              upload={selectedUpload}
              canManageImports={canManageImports}
              canApproveRiskyImports={canApproveRiskyImports}
            />
            <ImportResult upload={selectedUpload} />
          </section>

          <DownstreamActionsPanel upload={selectedUpload} canTriggerDownstreamActions={canTriggerDownstreamActions} />
        </div>
      ) : null}

      {activeTab === "history" ? (
        <div
          id="source-data-panel-history"
          role="tabpanel"
          aria-labelledby="source-data-tab-history"
          tabIndex={0}
        >
          <UploadHistory
            uploads={recentUploads}
            feeds={mvpFeeds}
            filters={uploadFilters}
            selectedPublicId={activeUploadId}
            canFilterSourceName={canManageImports}
            isLoading={uploadsQuery.isLoading}
            isError={uploadsQuery.isError}
            error={uploadsQuery.error}
            isFetching={uploadsQuery.isFetching}
            onSelect={(publicId) => {
              setSelectedUploadId(publicId);
              setActiveTab("review");
            }}
            onFiltersChange={(filters) => setUploadFilters({ ...filters, limit: 20 })}
          />
        </div>
      ) : null}

      {activeTab === "templates" ? (
        <div
          id="source-data-panel-templates"
          className="grid gap-6"
          role="tabpanel"
          aria-labelledby="source-data-tab-templates"
          tabIndex={0}
        >
          <section className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
            <Card className="p-5">
              <div className="mb-4 flex items-center gap-3">
                <Database className="size-5 text-brand" aria-hidden="true" />
                <h1 className="text-xl font-semibold text-panel-strong">Sources &amp; Templates</h1>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <FeedMetric label="Registered sources" value={metricValue(data?.feed_count)} />
                <FeedMetric label="Contract issues" value={metricValue(data ? contractErrors.length : null)} />
                <FeedMetric label="Template set" value={scopeLabel(data?.scope)} />
              </div>
            </Card>

            {contractErrors.length ? (
              <Card className="p-5">
                <div className="mb-4 flex items-center gap-3">
                  <ShieldCheck className="size-5 text-brand" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-panel-strong">Template Issues</h2>
                </div>
                <div className="grid gap-2">
                  {contractErrors.map((item) => (
                    <div key={item} className="rounded-[0.5rem] border border-[color-mix(in_srgb,var(--danger)_24%,white)] px-3 py-2 text-sm font-semibold text-[color:var(--danger)]">
                      {item}
                    </div>
                  ))}
                </div>
              </Card>
            ) : null}
          </section>

          <section className="grid gap-4">
            {Object.entries(groupedFeeds).map(([domain, feeds]) => (
              <div key={domain} className="grid gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-muted">
                  {formatLabel(domain)}
                </h2>
                {feeds.map((feed, index) => (
                  <FeedCard
                    key={feedKeyValue(feed, `${domain}-feed-${index}`)}
                    feed={feed}
                    freshness={freshnessByFeedKey.get(feedBackendKey(feed) ?? "")}
                    canUseSourceDataAdminControls={canManageSourceDataFeedModes}
                  />
                ))}
              </div>
            ))}
            {!isLoading && !mvpFeeds.length && !isError ? (
              <Card className="p-5">
                <p className="text-sm text-panel-muted">No data templates are currently available.</p>
              </Card>
            ) : null}
          </section>
        </div>
      ) : null}

      {activeTab === "templates" && isLoading ? (
        <Card className="p-5">
          <div className="flex items-center gap-3 text-sm font-semibold text-panel-muted">
            <FileSpreadsheet className="size-4" aria-hidden="true" />
            Loading data templates...
          </div>
        </Card>
      ) : null}

      {activeTab === "templates" && isError ? (
        <Card className="p-5">
          <div className="flex items-start gap-3 text-sm text-[color:var(--danger)]">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p>{error instanceof Error ? error.message : "Unable to load data templates."}</p>
          </div>
        </Card>
      ) : null}

      {canManageImports ? (
        <UploadDrawer
          isOpen={isUploadDrawerOpen}
          feeds={mvpFeeds}
          recentUploads={recentUploads}
          selectedUpload={selectedUpload}
          canManageImports={canManageImports}
          onUploadSelected={handleUploadSelected}
          onClose={() => setIsUploadDrawerOpen(false)}
        />
      ) : null}
    </div>
  );
}

export default function SourceDataPage() {
  return (
    <RoleGate
      pageCapability="source_data"
      title="Data readiness access is restricted"
      message="Data templates and update status are available to administrators, supervisors, and analysts."
    >
      <SourceDataContent />
    </RoleGate>
  );
}
