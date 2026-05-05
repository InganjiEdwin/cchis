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
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  createSourceDataUploadViaBff,
  validateSourceDataUploadViaBff,
  type SourceDataFeedDefinition,
  type SourceDataUploadBatchRecord,
} from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { queryKeys } from "@/lib/query-keys";
import {
  useSourceDataFeedTypesQuery,
  useSourceDataUploadQuery,
  useSourceDataUploadsQuery,
} from "@/queries/use-source-data-query";

const ALLOWED_ROLES = ["ADMIN", "SUPERVISOR", "ANALYST"] as const;

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
  if (["ready_for_confirmation", "passed", "imported"].includes(status)) {
    return "success";
  }
  if (["validation_failed", "failed", "import_failed", "rejected", "error"].includes(status)) {
    return "danger";
  }
  if (["uploaded", "running", "validating", "pending", "confirming"].includes(status)) {
    return "warning";
  }
  if (status === "not_started") {
    return "default";
  }
  return "info";
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

function FeedCard({ feed }: { feed: SourceDataFeedDefinition }) {
  return (
    <Card className="grid gap-4 p-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-start">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <StatusBadge tone="info">{formatLabel(feed.domain)}</StatusBadge>
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
    </Card>
  );
}

function UploadWizard({
  feeds,
  selectedUpload,
  onUploadSelected,
}: {
  feeds: SourceDataFeedDefinition[];
  selectedUpload?: SourceDataUploadBatchRecord;
  onUploadSelected: (publicId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [feedKey, setFeedKey] = useState(feeds[0]?.feed_key ?? "");
  const [sourceName, setSourceName] = useState("");
  const [sourceTimestamp, setSourceTimestamp] = useState("");
  const [reportingPeriodStart, setReportingPeriodStart] = useState("");
  const [reportingPeriodEnd, setReportingPeriodEnd] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const selectedFeed = feeds.find((feed) => feed.feed_key === feedKey) ?? feeds[0];
  const requiresReportingPeriod = selectedFeed?.required_metadata.some((field) =>
    ["reporting_period_start", "reporting_period_end"].includes(field),
  );

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
    if (!file || !feedKey || !sourceName || !sourceTimestamp) {
      return;
    }

    uploadMutation.mutate({
      feed_key: feedKey,
      source_name: sourceName,
      source_timestamp: sourceTimestamp,
      reporting_period_start: reportingPeriodStart,
      reporting_period_end: reportingPeriodEnd,
      file,
    });
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
              onChange={(event) => setFeedKey(event.target.value)}
              className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              {feeds.map((feed) => (
                <option key={feed.feed_key} value={feed.feed_key}>
                  {feed.label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            Source name
            <input
              value={sourceName}
              onChange={(event) => setSourceName(event.target.value)}
              placeholder="Migori DHIS2"
              className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            Source timestamp
            <input
              type="datetime-local"
              value={sourceTimestamp}
              onChange={(event) => setSourceTimestamp(event.target.value)}
              className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-panel-copy">
            CSV file
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 py-2 text-sm text-panel-strong outline-none file:mr-3 file:rounded-pill file:border-0 file:bg-[var(--dashboard-icon-button-surface)] file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-panel-copy focus-visible:ring-2 focus-visible:ring-brand/30"
            />
          </label>
        </div>

        {requiresReportingPeriod ? (
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-semibold text-panel-copy">
              Reporting period start
              <input
                type="date"
                value={reportingPeriodStart}
                onChange={(event) => setReportingPeriodStart(event.target.value)}
                className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
              />
            </label>
            <label className="grid gap-2 text-sm font-semibold text-panel-copy">
              Reporting period end
              <input
                type="date"
                value={reportingPeriodEnd}
                onChange={(event) => setReportingPeriodEnd(event.target.value)}
                className="h-11 rounded-[0.5rem] border border-panel-table-wrap bg-panel px-3 text-sm text-panel-strong outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
              />
            </label>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" size="md" disabled={uploadMutation.isPending || !file}>
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

function ValidationSummary({ upload }: { upload?: SourceDataUploadBatchRecord }) {
  const issues = upload?.validation_issues ?? [];
  const topIssues = issues.slice(0, 6);

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

          <div className="grid gap-3 sm:grid-cols-4">
            <FeedMetric label="Rows Seen" value={upload.row_count} />
            <FeedMetric label="Accepted" value={upload.accepted_count} />
            <FeedMetric label="Rejected" value={upload.rejected_count} />
            <FeedMetric label="Warnings" value={upload.warning_count} />
          </div>

          {topIssues.length ? (
            <div className="overflow-hidden rounded-[0.5rem] border border-[var(--dashboard-table-line)]">
              <table className="w-full text-left text-sm">
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
                      <td className="px-3 py-2 text-panel-muted">{issue.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm leading-6 text-panel-muted">
              No validation issues are stored for the selected upload.
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
          Create an upload, then run dry validation to see accepted rows, rejected rows, warnings, and diagnostics.
        </p>
      )}
    </Card>
  );
}

function UploadHistory({
  uploads,
  selectedPublicId,
  onSelect,
}: {
  uploads: SourceDataUploadBatchRecord[];
  selectedPublicId: string | null;
  onSelect: (publicId: string) => void;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-3">
        <FileSpreadsheet className="size-5 text-brand" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-panel-strong">Recent Uploads</h2>
      </div>
      <div className="overflow-hidden rounded-[0.5rem] border border-[var(--dashboard-table-line)]">
        <table className="w-full text-left text-sm">
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
                  No source-data uploads have been created yet.
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
  const { data, isLoading, isError, error, refetch, isFetching } = useSourceDataFeedTypesQuery();
  const [selectedUploadId, setSelectedUploadId] = useState<string | null>(null);
  const uploadsQuery = useSourceDataUploadsQuery({ limit: 20 });
  const latestUploadId = uploadsQuery.data?.results[0]?.public_id ?? null;
  const activeUploadId = selectedUploadId ?? latestUploadId;
  const selectedUploadQuery = useSourceDataUploadQuery(activeUploadId);
  const contractErrors = data?.template_contract_errors ?? [];
  const mvpFeeds = data?.feeds ?? [];
  const selectedUpload = selectedUploadQuery.data ?? uploadsQuery.data?.results.find((item) => item.public_id === activeUploadId);
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
        onRefresh={() => void refetch()}
      >
        <Button variant="secondary" size="md" onClick={() => void refetch()} disabled={isFetching}>
          <RefreshCcw className="size-4" aria-hidden="true" />
          Refresh
        </Button>
      </DashboardTopbar>

      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <UploadWizard feeds={mvpFeeds} selectedUpload={selectedUpload} onUploadSelected={setSelectedUploadId} />
        <ValidationSummary upload={selectedUpload} />
      </section>

      <UploadHistory
        uploads={uploadsQuery.data?.results ?? []}
        selectedPublicId={activeUploadId}
        onSelect={setSelectedUploadId}
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
              <FeedCard key={feed.feed_key} feed={feed} />
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
