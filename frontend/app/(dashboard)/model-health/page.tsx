"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  History,
  LineChart,
  ListChecks,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { ReactNode } from "react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type {
  ModelMonitoringSnapshotPanel,
  ModelOperationsActiveModel,
  ModelOperationsHealthResponse,
  ModelOperationsHealthTone,
  ModelOperationsModelState,
  ModelRollbackHistoryItem,
} from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { useModelOperationsHealthQuery } from "@/queries/use-model-health-query";

type BadgeTone = ModelOperationsHealthTone;

type ReadinessStep = {
  label: string;
  helper: string;
  done: boolean;
  tone?: BadgeTone;
};

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

function formatMetricValue(value: number | null) {
  if (value === null || value === undefined) return "not available";
  return Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(3);
}

function toneForState(value: string | null | undefined): BadgeTone {
  if (!value) return "default";
  if (["HEALTHY", "ACTIVE_PROMOTED", "BENCHMARK_ONLY", "active_promoted", "healthy"].includes(value)) return "success";
  if (["WARNING", "REVIEW_REQUIRED", "NOT_COMPARABLE", "warning", "review_required"].includes(value)) return "warning";
  if (["BREACHED", "ROLLED_BACK", "no_active_model", "rolled_back"].includes(value)) return "danger";
  if (["benchmark_only", "candidate", "retired_promoted", "not_configured", "NOT_CONFIGURED"].includes(value)) return "info";
  return "default";
}

function readinessTitle(data: ModelOperationsHealthResponse) {
  switch (data.summary.health_state) {
    case "healthy":
      return "Ready for operational use";
    case "warning":
    case "review_required":
      return "Needs review before teams rely on it";
    case "breached":
      return "Do not use for decisions yet";
    case "no_active_model":
      return "Not ready for operational use";
    default:
      return data.summary.active_model_present ? "Forecast needs review" : "Not ready for operational use";
  }
}

function readinessMessage(data: ModelOperationsHealthResponse) {
  if (!data.summary.active_model_present) {
    return "No approved ward-risk forecast is live. Keep using existing ward reports until a forecast is reviewed and approved.";
  }
  if (data.summary.health_state === "healthy") {
    return "The approved forecast is live and the latest quality checks do not show issues that need attention.";
  }
  if (data.summary.health_state === "breached") {
    return "Quality checks found a serious issue. Pause operational use until the forecast is reviewed.";
  }
  return "The forecast is live, but one or more quality checks need a person to review them.";
}

function approvedForecastLabel(activeModel: ModelOperationsActiveModel | null | undefined) {
  return activeModel?.model_version || "None live";
}

function qualityStatus(data: ModelOperationsHealthResponse) {
  const warningCount = data.summary.drift_warning_count + data.summary.calibration_warning_count;
  if (!data.summary.active_model_present) return "Waiting for an approved forecast";
  if (data.summary.monitoring_state === "NOT_CONFIGURED") return "Quality checks not set up";
  if (warningCount > 0) return `${warningCount} check${warningCount === 1 ? "" : "s"} need review`;
  return "Checks look good";
}

function qualityHelper(data: ModelOperationsHealthResponse) {
  const warningCount = data.summary.drift_warning_count + data.summary.calibration_warning_count;
  if (!data.summary.active_model_present) return "Checks will start after a forecast is approved for use.";
  if (data.summary.monitoring_state === "NOT_CONFIGURED") return "Set up checks before teams rely on forecast outputs.";
  if (warningCount > 0) return "Review the changed data or accuracy signals before expanding use.";
  return "No action needed from the latest quality check.";
}

function testingVersion(challenger: ModelOperationsHealthResponse["challenger_comparison"]) {
  const summary = challenger.dashboard_summary ?? {};
  const record = (summary.challenger ?? null) as null | Record<string, unknown>;
  return record?.model_version ? String(record.model_version) : "No new version";
}

function testingHelper(challenger: ModelOperationsHealthResponse["challenger_comparison"]) {
  const summary = challenger.dashboard_summary ?? {};
  if (!challenger.configured) return "No new forecast version is currently being tested.";
  if (summary.challenger_outputs_affect_alerts) return "This version may be linked to alerts. Review it before any field use.";
  return "This version is being tested and does not guide alerts.";
}

function metricLabel(metricName: string) {
  const labels: Record<string, string> = {
    feature_distribution_drift: "Input data changed",
    score_distribution_drift: "Risk scores shifted",
    source_quality_drift: "Source data changed",
    calibration_drift: "Accuracy check changed",
  };
  return labels[metricName] || formatLabel(metricName);
}

function versionStateLabel(state: ModelOperationsModelState) {
  const labels: Record<string, string> = {
    active_promoted: "Approved and live",
    benchmark_only: "Testing only",
    candidate: "Draft version",
    retired_promoted: "Previous approved version",
    rolled_back: "Replaced by backup",
    registry_missing_promoted_metadata: "Needs approval review",
    ungoverned_promoted_metadata: "Needs approval review",
  };
  return labels[state.visual_state] || state.visual_state_label || formatLabel(state.visual_state);
}

function purposeLabel(state: ModelOperationsModelState) {
  if (state.alert_eligible) return "Can guide alerts";
  if (state.promotion_target === "benchmark_only") return "Testing only";
  if (state.visual_state === "candidate") return "Not approved yet";
  if (state.visual_state === "retired_promoted") return "Kept for reference";
  return "Not used for alerts";
}

function blockerLabel(blocker: string) {
  const labels: Record<string, string> = {
    challenger_scores_already_used_for_alerts: "Testing output is already connected to alerts",
    champion_registry_entry_missing: "Current approved forecast is missing",
    input_alignment_failed: "Inputs do not match the current forecast",
    not_comparable: "The versions cannot be compared fairly",
  };
  return labels[blocker] || formatLabel(blocker);
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
        <span className="inline-flex size-9 items-center justify-center rounded-[0.5rem] bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_10%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_18%,transparent)]">
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

function ReadinessHero({
  data,
  onReviewVersions,
  onViewChecks,
}: {
  data: ModelOperationsHealthResponse;
  onReviewVersions: () => void;
  onViewChecks: () => void;
}) {
  const tone = data.summary.health_tone;

  return (
    <Card
      tone="attention"
      className={cn(
        "grid gap-5 p-5 md:grid-cols-[1fr_auto] md:items-center",
        tone === "danger" && "border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))]",
        tone === "warning" && "border-[color-mix(in_srgb,var(--warning)_32%,var(--dashboard-table-line))]",
        tone === "success" && "border-[color-mix(in_srgb,var(--success)_30%,var(--dashboard-table-line))]",
      )}
    >
      <div className="min-w-0">
        <PlainBadge tone={tone}>Forecast status</PlainBadge>
        <h1 className="mt-3 text-2xl font-semibold leading-tight text-panel-strong md:text-3xl">{readinessTitle(data)}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-panel-muted md:text-base">{readinessMessage(data)}</p>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row md:flex-col">
        <Button type="button" onClick={onReviewVersions}>
          <ListChecks className="size-4" />
          Review versions
        </Button>
        <Button type="button" variant="secondary" onClick={onViewChecks}>
          <ShieldCheck className="size-4" />
          View checks
        </Button>
      </div>
    </Card>
  );
}

function ReadinessChecklist({ data }: { data: ModelOperationsHealthResponse }) {
  const activeModel = data.active_model;
  const warningCount = data.summary.drift_warning_count + data.summary.calibration_warning_count;
  const checksReady = Boolean(activeModel) && data.summary.monitoring_state !== "NOT_CONFIGURED" && warningCount === 0;
  const steps: ReadinessStep[] = [
    {
      label: "Approve one forecast for ward decisions",
      helper: activeModel ? `${activeModel.model_version} is the current approved forecast.` : "No approved forecast is live yet.",
      done: Boolean(activeModel),
      tone: activeModel ? "success" : "warning",
    },
    {
      label: "Run quality checks on recent data",
      helper: qualityHelper(data),
      done: checksReady,
      tone: checksReady ? "success" : activeModel ? "warning" : "default",
    },
    {
      label: "Name a responsible reviewer",
      helper: activeModel?.owner ? `${activeModel.owner} is listed as responsible.` : "Assign a person or team before operational use.",
      done: Boolean(activeModel?.owner),
      tone: activeModel?.owner ? "success" : "warning",
    },
    {
      label: "Keep a backup plan visible",
      helper: data.rollback_history.length ? "Previous backup switches are visible for review." : "No backup switch has been recorded yet.",
      done: data.rollback_history.length > 0,
      tone: data.rollback_history.length ? "success" : "default",
    },
  ];

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-panel-strong">Readiness checklist</h2>
          <p className="mt-1 text-sm text-panel-muted">The shortest path to making forecasts usable for field decisions.</p>
        </div>
        <PlainBadge tone={data.summary.active_model_present && checksReady ? "success" : "warning"}>
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
                  <PlainBadge tone={step.tone}>{step.done ? "Done" : "Needed"}</PlainBadge>
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

function ApprovedForecastPanel({
  activeModel,
  monitoringState,
}: {
  activeModel: ModelOperationsActiveModel | null | undefined;
  monitoringState: string | undefined;
}) {
  if (!activeModel) {
    return (
      <Card className="p-5">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 size-5 text-[color:var(--warning)]" />
          <div>
            <h2 className="text-lg font-semibold text-panel-strong">Current approved forecast</h2>
            <p className="mt-1 text-sm leading-6 text-panel-muted">
              No approved forecast is live. Keep operational decisions tied to existing ward reports until one is reviewed and approved.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  const rows = [
    ["Approved", activeModel.promotion_date ? formatRelativeTimestamp(activeModel.promotion_date) : "Date not set"],
    ["Review due", activeModel.review_due_date ?? "Not set"],
    ["Responsible reviewer", activeModel.owner || "Unassigned"],
    ["Review note", activeModel.promotion_evidence_report_ref || "No note attached"],
  ];

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-panel-strong">Current approved forecast</h2>
          <p className="mt-1 text-2xl font-semibold text-panel-strong">{activeModel.model_version}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <PlainBadge tone={toneForState(activeModel.promotion_state)}>Approved</PlainBadge>
          <PlainBadge tone={toneForState(monitoringState)}>{qualityStatusLabel(activeModel.monitoring_state)}</PlainBadge>
        </div>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-3">
            <p className="text-xs font-semibold text-panel-muted">{label}</p>
            <p className="mt-1 min-w-0 break-words text-sm font-semibold text-panel-strong">{value}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function qualityStatusLabel(state: string | null | undefined) {
  if (state === "NOT_CONFIGURED") return "Checks not set up";
  if (state === "HEALTHY") return "Checks look good";
  if (state === "WARNING") return "Needs review";
  if (state === "REVIEW_REQUIRED") return "Review required";
  if (state === "BREACHED") return "Pause use";
  return formatLabel(state);
}

function TestingPanel({
  challenger,
}: {
  challenger: ModelOperationsHealthResponse["challenger_comparison"];
}) {
  const summary = challenger.dashboard_summary ?? {};
  const blockers = challenger.promotion_blockers ?? [];
  const unsafe = Boolean(summary.challenger_outputs_affect_alerts);

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Sparkles className="mt-0.5 size-5 text-brand" />
          <div>
            <h2 className="text-lg font-semibold text-panel-strong">New version being tested</h2>
            <p className="mt-1 text-xl font-semibold text-panel-strong">{testingVersion(challenger)}</p>
          </div>
        </div>
        <PlainBadge tone={unsafe ? "danger" : challenger.configured ? "info" : "default"}>
          {unsafe ? "Needs review" : challenger.configured ? "Testing only" : "None"}
        </PlainBadge>
      </div>
      <p className="mt-4 text-sm leading-6 text-panel-muted">{testingHelper(challenger)}</p>
      {blockers.length ? (
        <div className="mt-4 grid gap-2">
          <p className="text-sm font-semibold text-panel-strong">What needs attention</p>
          {blockers.slice(0, 4).map((blocker) => (
            <div key={blocker} className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 text-sm text-panel-copy">
              {blockerLabel(blocker)}
            </div>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function QualityCheckRows({
  title,
  emptyMessage,
  snapshots,
}: {
  title: string;
  emptyMessage: string;
  snapshots: ModelMonitoringSnapshotPanel[];
}) {
  return (
    <section className="grid gap-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-panel-strong">{title}</h3>
        <PlainBadge tone={snapshots.length ? "warning" : "success"}>{snapshots.length ? "Needs review" : "Clear"}</PlainBadge>
      </div>
      <div className="grid gap-2">
        {snapshots.length ? (
          snapshots.map((snapshot) => (
            <div
              key={snapshot.snapshot_public_id}
              className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-3 md:grid-cols-[1.1fr_1fr_auto]"
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-panel-strong">{metricLabel(snapshot.metric_name)}</p>
                <p className="mt-1 text-xs text-panel-muted">
                  Updated {formatRelativeTimestamp(snapshot.generated_at)}
                </p>
              </div>
              <p className="text-sm leading-6 text-panel-copy">
                Current value {formatMetricValue(snapshot.value)}
                {snapshot.threshold_value !== null ? `; review point ${formatMetricValue(snapshot.threshold_value)}` : ""}
              </p>
              <PlainBadge tone={toneForState(snapshot.state)}>{qualityStatusLabel(snapshot.state)}</PlainBadge>
            </div>
          ))
        ) : (
          <p className="rounded-[0.5rem] border border-dashed border-[var(--dashboard-table-line)] px-3 py-3 text-sm text-panel-muted">
            {emptyMessage}
          </p>
        )}
      </div>
    </section>
  );
}

function QualityPanel({ data }: { data: ModelOperationsHealthResponse }) {
  const emptyMessage =
    data.summary.monitoring_state === "NOT_CONFIGURED"
      ? "Quality checks are not set up yet."
      : "No issues found in the latest quality check.";

  return (
    <Card id="quality-checks" className="scroll-mt-24 p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-panel-strong">Quality checks</h2>
          <p className="mt-1 text-sm leading-6 text-panel-muted">{qualityHelper(data)}</p>
        </div>
        <PlainBadge tone={toneForState(data.monitoring.state)}>{qualityStatus(data)}</PlainBadge>
      </div>
      <div className="grid gap-5">
        <QualityCheckRows title="Data changed" snapshots={data.monitoring.drift_warnings} emptyMessage={emptyMessage} />
        <QualityCheckRows title="Accuracy check" snapshots={data.monitoring.calibration_warnings} emptyMessage={emptyMessage} />
      </div>
    </Card>
  );
}

function BackupSwitchPanel({ items }: { items: ModelRollbackHistoryItem[] }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <History className="size-5 text-brand" />
          <h2 className="text-lg font-semibold text-panel-strong">Backup switches</h2>
        </div>
        <PlainBadge tone={items.length ? "info" : "default"}>{items.length}</PlainBadge>
      </div>
      <div className="grid gap-3">
        {items.length ? (
          items.map((item) => {
            const materializedCount = Number(item.current_risk_materialization.materialized_ward_count ?? 0);
            return (
              <div key={item.rollback_event_public_id} className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-panel-strong">
                      {item.rolled_back_from.model_version} to {item.rollback_target.model_version}
                    </p>
                    <p className="mt-1 text-xs text-panel-muted">
                      {formatRelativeTimestamp(item.occurred_at)} by {item.rolled_back_by || "unknown reviewer"}
                    </p>
                  </div>
                  <PlainBadge tone="info">{materializedCount} wards updated</PlainBadge>
                </div>
                <p className="mt-2 text-sm leading-6 text-panel-copy">{item.reason}</p>
              </div>
            );
          })
        ) : (
          <p className="rounded-[0.5rem] border border-dashed border-[var(--dashboard-table-line)] px-3 py-3 text-sm text-panel-muted">
            No backup switch has been needed.
          </p>
        )}
      </div>
    </Card>
  );
}

function ForecastVersionsTable({ states }: { states: ModelOperationsModelState[] }) {
  return (
    <section id="forecast-versions" className="scroll-mt-24 grid gap-4">
      <div className="flex items-center gap-3">
        <LineChart className="size-5 text-brand" />
        <div>
          <h2 className="text-lg font-semibold text-panel-strong">Forecast versions</h2>
          <p className="mt-1 text-sm text-panel-muted">Recent forecast runs, shown by whether they can guide alerts.</p>
        </div>
      </div>
      <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
        <div className="hidden grid-cols-[1fr_0.9fr_0.9fr_0.8fr] border-b border-[var(--dashboard-table-line)] px-4 py-3 text-xs font-semibold text-panel-muted md:grid">
          <span>Version</span>
          <span>Status</span>
          <span>Purpose</span>
          <span>Alerts</span>
        </div>
        {states.map((state) => (
          <div
            key={state.model_run_id}
            className="grid gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0 md:grid-cols-[1fr_0.9fr_0.9fr_0.8fr] md:items-center md:py-3"
          >
            <div className="min-w-0">
              <p className="truncate font-semibold text-panel-strong">{state.model_version}</p>
              <p className="mt-1 truncate text-xs text-panel-muted">Method: {state.algorithm_name}</p>
            </div>
            <PlainBadge tone={toneForState(state.visual_state)}>{versionStateLabel(state)}</PlainBadge>
            <span className="min-w-0 text-panel-copy">{purposeLabel(state)}</span>
            <PlainBadge tone={state.alert_eligible ? "success" : "default"}>
              {state.alert_eligible ? "Can guide alerts" : "Not used"}
            </PlainBadge>
          </div>
        ))}
        {!states.length ? (
          <p className="px-4 py-4 text-sm text-panel-muted">No forecast versions are available yet.</p>
        ) : null}
      </div>
    </section>
  );
}

export default function ModelHealthPage() {
  const { data, isPending, error, refetch, isFetching } = useModelOperationsHealthQuery();
  const lastUpdatedLabel = data?.generated_at ? formatRelativeTimestamp(data.generated_at) : "No readiness snapshot";
  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <RoleGate
      allowedRoles={["ADMIN", "SUPERVISOR", "ANALYST"]}
      title="Forecast readiness unavailable"
      message="Your role cannot view forecast readiness."
    >
      <div className="space-y-7">
        <DashboardTopbar
          title="Forecast Readiness"
          subtitle="See whether ward-risk forecasts are ready to guide alerts and planning."
          lastUpdatedLabel={lastUpdatedLabel}
          lastUpdatedTone={data?.summary.health_tone === "success" ? "default" : "stale"}
          onRefresh={() => refetch()}
        />

        {error ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 text-[color:var(--danger)]" />
              <div>
                <p className="font-semibold text-panel-strong">Unable to load forecast readiness</p>
                <p className="mt-1 text-sm text-panel-muted">Refresh the page. If this keeps happening, ask the system team to check the dashboard connection.</p>
              </div>
            </div>
          </Card>
        ) : null}

        {isPending ? (
          <div className="grid gap-4">
            <div className="h-44 animate-pulse rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)]" />
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <div
                  key={index}
                  className="h-32 animate-pulse rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)]"
                />
              ))}
            </div>
          </div>
        ) : data ? (
          <>
            <ReadinessHero
              data={data}
              onReviewVersions={() => scrollToSection("forecast-versions")}
              onViewChecks={() => scrollToSection("quality-checks")}
            />

            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <SummaryCard
                label="Approved forecast"
                value={approvedForecastLabel(data.active_model)}
                helper={data.active_model ? "This is the version teams can use." : "No version is approved for alerts."}
                tone={data.active_model ? "success" : "warning"}
                icon={<Activity className="size-5" />}
              />
              <SummaryCard
                label="Quality checks"
                value={qualityStatus(data)}
                helper={qualityHelper(data)}
                tone={toneForState(data.summary.monitoring_state)}
                icon={<ShieldCheck className="size-5" />}
              />
              <SummaryCard
                label="Testing"
                value={testingVersion(data.challenger_comparison)}
                helper={testingHelper(data.challenger_comparison)}
                tone={data.challenger_comparison.configured ? "info" : "default"}
                icon={<Sparkles className="size-5" />}
              />
              <SummaryCard
                label="Backup switches"
                value={data.summary.rollback_event_count}
                helper={data.summary.rollback_event_count ? "Past switches are available for review." : "No backup switch has been needed."}
                tone={data.summary.rollback_event_count ? "info" : "default"}
                icon={<Clock3 className="size-5" />}
              />
            </section>

            <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
              <ReadinessChecklist data={data} />
              <ApprovedForecastPanel activeModel={data.active_model} monitoringState={data.summary.monitoring_state} />
            </section>

            <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
              <QualityPanel data={data} />
              <TestingPanel challenger={data.challenger_comparison} />
            </section>

            <BackupSwitchPanel items={data.rollback_history} />
            <ForecastVersionsTable states={data.model_states} />
          </>
        ) : null}

        <div className="flex justify-end">
          <Button type="button" variant="secondary" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("size-4", isFetching && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>
    </RoleGate>
  );
}
