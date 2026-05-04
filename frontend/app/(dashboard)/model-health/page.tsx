"use client";

import {
  Activity,
  AlertTriangle,
  Clock3,
  DatabaseZap,
  Network,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type {
  ModelOperationsActiveModel,
  ModelOperationsHealthResponse,
  ModelMonitoringSnapshotPanel,
  ModelOperationsHealthTone,
  ModelOperationsModelState,
  ModelRollbackHistoryItem,
} from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { useModelOperationsHealthQuery } from "@/queries/use-model-health-query";

type BadgeTone = ModelOperationsHealthTone;

function formatLabel(value: string | null | undefined) {
  if (!value) return "Unknown";
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMetricValue(value: number | null) {
  if (value === null || value === undefined) return "No value";
  return Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(3);
}

function toneForState(value: string | null | undefined): BadgeTone {
  if (!value) return "default";
  if (["HEALTHY", "ACTIVE_PROMOTED", "BENCHMARK_ONLY", "active_promoted", "healthy"].includes(value)) return "success";
  if (["WARNING", "REVIEW_REQUIRED", "NOT_COMPARABLE", "warning", "review_required"].includes(value)) return "warning";
  if (["BREACHED", "ROLLED_BACK", "no_active_model", "rolled_back"].includes(value)) return "danger";
  if (["benchmark_only", "candidate", "retired_promoted"].includes(value)) return "info";
  return "default";
}

function SummaryTile({
  label,
  value,
  tone = "default",
  icon,
}: {
  label: string;
  value: string | number;
  tone?: BadgeTone;
  icon: ReactNode;
}) {
  return (
    <Card className="grid min-h-32 gap-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <span className="inline-flex size-10 items-center justify-center rounded-[0.5rem] bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
          {icon}
        </span>
        <StatusBadge tone={tone}>{formatLabel(String(tone))}</StatusBadge>
      </div>
      <div>
        <p className="text-2xl font-semibold text-panel-strong">{value}</p>
        <p className="mt-1 text-sm text-panel-muted">{label}</p>
      </div>
    </Card>
  );
}

function WarningRows({ title, snapshots }: { title: string; snapshots: ModelMonitoringSnapshotPanel[] }) {
  return (
    <section className="grid gap-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-muted">{title}</h3>
        <StatusBadge tone={snapshots.length ? "warning" : "success"}>{snapshots.length}</StatusBadge>
      </div>
      <div className="grid gap-2">
        {snapshots.length ? (
          snapshots.map((snapshot) => (
            <div
              key={snapshot.snapshot_public_id}
              className="grid gap-2 rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-3 md:grid-cols-[1.2fr_0.8fr_0.8fr]"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-panel-strong">{formatLabel(snapshot.metric_name)}</p>
                <p className="mt-1 text-xs text-panel-muted">{snapshot.threshold_version || "No threshold version"}</p>
              </div>
              <p className="text-sm text-panel-copy">{formatMetricValue(snapshot.value)}</p>
              <StatusBadge tone={toneForState(snapshot.state)}>{snapshot.state_label}</StatusBadge>
            </div>
          ))
        ) : (
          <p className="rounded-[0.5rem] border border-dashed border-[var(--dashboard-table-line)] px-3 py-3 text-sm text-panel-muted">
            No warning snapshots in the latest monitoring run.
          </p>
        )}
      </div>
    </section>
  );
}

function ActiveModelPanel({
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
          <AlertTriangle className="mt-0.5 size-5 text-[color:var(--danger)]" />
          <div>
            <p className="font-semibold text-panel-strong">No active promoted model</p>
            <p className="mt-1 text-sm text-panel-muted">Model registry sync or Phase 4 promotion is required.</p>
          </div>
        </div>
      </Card>
    );
  }

  const rows = [
    ["Model", activeModel.model_version],
    ["Algorithm", activeModel.algorithm],
    ["Promotion Date", activeModel.promotion_date ? formatRelativeTimestamp(activeModel.promotion_date) : "Not set"],
    ["Review Due", activeModel.review_due_date ?? "Not set"],
    ["Owner", activeModel.owner || "Unassigned"],
    ["Evidence", activeModel.promotion_evidence_report_ref || "No evidence ref"],
  ];

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Active Champion</p>
          <h2 className="mt-1 text-2xl font-semibold text-panel-strong">{activeModel.model_version}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone={toneForState(activeModel.promotion_state)}>{activeModel.promotion_state_label}</StatusBadge>
          <StatusBadge tone={toneForState(monitoringState)}>{activeModel.monitoring_state_label}</StatusBadge>
        </div>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
            <p className="mt-1 min-w-0 break-words text-sm font-semibold text-panel-strong">{value}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ChallengerPanel({
  challenger,
}: {
  challenger: ModelOperationsHealthResponse["challenger_comparison"] | undefined;
}) {
  const summary = challenger?.dashboard_summary ?? {};
  const challengerRecord = (summary.challenger ?? null) as null | Record<string, unknown>;
  const blockers = challenger?.promotion_blockers ?? [];

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <Network className="size-5 text-brand" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Challenger</p>
            <h2 className="mt-1 text-lg font-semibold text-panel-strong">
              {challengerRecord?.model_version ? String(challengerRecord.model_version) : "No benchmark configured"}
            </h2>
          </div>
        </div>
        <StatusBadge tone={toneForState(challenger?.benchmark_status)}>{formatLabel(challenger?.benchmark_status)}</StatusBadge>
      </div>
      <div className="mt-5 grid gap-3 text-sm">
        <div className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-3">
          <p className="font-semibold text-panel-strong">
            {summary.challenger_outputs_affect_alerts ? "Affects alerts" : "Benchmark only"}
          </p>
          <p className="mt-1 text-panel-muted">
            {summary.can_replace_champion_without_phase_4_promotion
              ? "Promotion controls need review."
              : "Cannot replace the champion without Phase 4 promotion gates."}
          </p>
        </div>
        {blockers.length ? (
          <div className="grid gap-2">
            {blockers.slice(0, 4).map((blocker) => (
              <div key={blocker} className="rounded-[0.5rem] border border-[var(--dashboard-table-line)] px-3 py-2 text-panel-copy">
                {formatLabel(blocker)}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function RollbackHistoryPanel({ items }: { items: ModelRollbackHistoryItem[] }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Clock3 className="size-5 text-brand" />
          <h2 className="text-lg font-semibold text-panel-strong">Rollback History</h2>
        </div>
        <StatusBadge tone={items.length ? "info" : "default"}>{items.length}</StatusBadge>
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
                      {item.rolled_back_from.model_version} → {item.rollback_target.model_version}
                    </p>
                    <p className="mt-1 text-xs text-panel-muted">
                      {formatRelativeTimestamp(item.occurred_at)} · {item.rolled_back_by || "Unknown operator"}
                    </p>
                  </div>
                  <StatusBadge tone="info">{materializedCount} wards</StatusBadge>
                </div>
                <p className="mt-2 text-sm text-panel-copy">{item.reason}</p>
              </div>
            );
          })
        ) : (
          <p className="rounded-[0.5rem] border border-dashed border-[var(--dashboard-table-line)] px-3 py-3 text-sm text-panel-muted">
            No rollback events have been recorded.
          </p>
        )}
      </div>
    </Card>
  );
}

function ModelStateTable({ states }: { states: ModelOperationsModelState[] }) {
  return (
    <section className="grid gap-4">
      <div className="flex items-center gap-3">
        <DatabaseZap className="size-5 text-brand" />
        <h2 className="text-lg font-semibold text-panel-strong">Candidate And Promoted States</h2>
      </div>
      <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
        <div className="grid grid-cols-[1fr_0.9fr_0.8fr_0.8fr] border-b border-[var(--dashboard-table-line)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
          <span>Model</span>
          <span>State</span>
          <span>Target</span>
          <span>Alerts</span>
        </div>
        {states.map((state) => (
          <div
            key={state.model_run_id}
            className="grid grid-cols-[1fr_0.9fr_0.8fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0"
          >
            <div className="min-w-0">
              <p className="truncate font-semibold text-panel-strong">{state.model_version}</p>
              <p className="mt-1 truncate text-xs text-panel-muted">{state.algorithm_name}</p>
            </div>
            <StatusBadge tone={toneForState(state.visual_state)}>{state.visual_state_label}</StatusBadge>
            <span className="min-w-0 truncate text-panel-copy">{formatLabel(state.promotion_target)}</span>
            <StatusBadge tone={state.alert_eligible ? "success" : "default"}>
              {state.alert_eligible ? "Eligible" : "Blocked"}
            </StatusBadge>
          </div>
        ))}
        {!states.length ? (
          <p className="px-4 py-4 text-sm text-panel-muted">No successful model runs are available.</p>
        ) : null}
      </div>
    </section>
  );
}

export default function ModelHealthPage() {
  const { data, isPending, error, refetch, isFetching } = useModelOperationsHealthQuery();
  const lastUpdatedLabel = data?.generated_at ? formatRelativeTimestamp(data.generated_at) : "No health snapshot";

  return (
    <RoleGate
      allowedRoles={["ADMIN", "SUPERVISOR", "ANALYST"]}
      title="Model health unavailable"
      message="Your role cannot view model operations health."
    >
      <div className="space-y-8">
        <DashboardTopbar
          title="Model Health"
          subtitle="Champion, challenger, monitoring, and rollback status for ward-risk model operations."
          lastUpdatedLabel={lastUpdatedLabel}
          lastUpdatedTone={data?.summary.health_tone === "success" ? "default" : "stale"}
          onRefresh={() => refetch()}
        />

        <PageSectionHeader
          title="Operations State"
          description="Active promoted outputs are separated from candidate and benchmark model runs."
          actions={
            <Button type="button" variant="secondary" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCcw className={cn("mr-2 size-4", isFetching && "animate-spin")} />
              Refresh
            </Button>
          }
        />

        {error ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 text-[color:var(--danger)]" />
              <div>
                <p className="font-semibold text-panel-strong">Unable to load model health</p>
                <p className="mt-1 text-sm text-panel-muted">{error.message}</p>
              </div>
            </div>
          </Card>
        ) : null}

        {isPending ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, index) => (
              <div
                key={index}
                className="h-36 animate-pulse rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)]"
              />
            ))}
          </div>
        ) : data ? (
          <>
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <SummaryTile
                label="Overall health"
                value={data.summary.health_state_label}
                tone={data.summary.health_tone}
                icon={<Activity className="size-5" />}
              />
              <SummaryTile
                label="Monitoring state"
                value={formatLabel(data.summary.monitoring_state)}
                tone={toneForState(data.summary.monitoring_state)}
                icon={<ShieldCheck className="size-5" />}
              />
              <SummaryTile
                label="Drift warnings"
                value={data.summary.drift_warning_count}
                tone={data.summary.drift_warning_count ? "warning" : "success"}
                icon={<AlertTriangle className="size-5" />}
              />
              <SummaryTile
                label="Calibration warnings"
                value={data.summary.calibration_warning_count}
                tone={data.summary.calibration_warning_count ? "warning" : "success"}
                icon={<AlertTriangle className="size-5" />}
              />
              <SummaryTile
                label="Rollback events"
                value={data.summary.rollback_event_count}
                tone={data.summary.rollback_event_count ? "info" : "default"}
                icon={<Clock3 className="size-5" />}
              />
            </section>

            <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
              <ActiveModelPanel activeModel={data.active_model} monitoringState={data.summary.monitoring_state} />
              <ChallengerPanel challenger={data.challenger_comparison} />
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <Card className="p-5">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold text-panel-strong">Monitoring Warnings</h2>
                  <StatusBadge tone={toneForState(data.monitoring.state)}>{data.monitoring.state_label}</StatusBadge>
                </div>
                <div className="grid gap-5">
                  <WarningRows title="Drift" snapshots={data.monitoring.drift_warnings} />
                  <WarningRows title="Calibration" snapshots={data.monitoring.calibration_warnings} />
                </div>
              </Card>
              <RollbackHistoryPanel items={data.rollback_history} />
            </section>

            <ModelStateTable states={data.model_states} />
          </>
        ) : null}
      </div>
    </RoleGate>
  );
}
