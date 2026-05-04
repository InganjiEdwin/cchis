"use client";

import {
  AlertTriangle,
  Ban,
  Check,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Filter,
  Link2,
  Play,
  Search,
  ShieldCheck,
  type LucideIcon,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import {
  type FetchPreparednessActionsParams,
  type PreparednessActionPriority,
  type PreparednessActionRecord,
  type PreparednessActionStatus,
  type PreparednessActionTransitionPayload,
  type PreparednessActionType,
} from "@/lib/dashboard";
import { canManagePreparednessActions } from "@/lib/roles";
import {
  usePreparednessActionsQuery,
  useUpdatePreparednessActionMutation,
} from "@/queries/use-preparedness-actions-query";

type QueueFilter = "ALL" | "ACTIVE" | "OVERDUE" | "BLOCKED" | "COMPLETED" | "MINE" | "UNASSIGNED";
type BadgeTone = "default" | "success" | "warning" | "danger" | "info";

const ACTIVE_STATUSES = new Set<PreparednessActionStatus>([
  "DRAFT",
  "QUEUED",
  "ASSIGNED",
  "ACKNOWLEDGED",
  "IN_PROGRESS",
  "BLOCKED",
  "ESCALATED",
]);

const STATUS_TRANSITIONS: Record<PreparednessActionStatus, PreparednessActionStatus[]> = {
  DRAFT: ["QUEUED", "CANCELLED"],
  QUEUED: ["ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS", "BLOCKED", "ESCALATED", "CANCELLED", "EXPIRED"],
  ASSIGNED: ["ACKNOWLEDGED", "IN_PROGRESS", "BLOCKED", "ESCALATED", "COMPLETED", "CANCELLED", "EXPIRED"],
  ACKNOWLEDGED: ["IN_PROGRESS", "BLOCKED", "ESCALATED", "COMPLETED", "CANCELLED", "EXPIRED"],
  IN_PROGRESS: ["BLOCKED", "ESCALATED", "COMPLETED", "CANCELLED", "EXPIRED"],
  BLOCKED: ["ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS", "ESCALATED", "CANCELLED", "EXPIRED"],
  ESCALATED: ["IN_PROGRESS", "BLOCKED", "COMPLETED", "CANCELLED", "EXPIRED"],
  COMPLETED: [],
  CANCELLED: [],
  EXPIRED: [],
};

const ACTION_TYPE_LABELS: Record<PreparednessActionType, string> = {
  chv_follow_up: "CHV follow-up",
  household_prevention_message: "Household prevention message",
  facility_ors_review: "Facility ORS review",
  facility_staffing_review: "Facility staffing review",
  county_escalation: "County escalation",
  water_treatment_distribution: "Water treatment distribution",
  surveillance_follow_up: "Surveillance follow-up",
  field_verification: "Field verification",
};

const FILTER_LABELS: Record<QueueFilter, string> = {
  ALL: "All",
  ACTIVE: "Active",
  OVERDUE: "Overdue",
  BLOCKED: "Blocked",
  COMPLETED: "Completed",
  MINE: "Mine",
  UNASSIGNED: "Unassigned",
};

function toTitleCase(value: string) {
  return value
    .toLowerCase()
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTimestamp(timestamp: string | null) {
  if (!timestamp) return "Not set";

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";

  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDueDelta(timestamp: string | null) {
  if (!timestamp) return "No SLA";

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";

  const diffMinutes = Math.round((date.getTime() - Date.now()) / 60000);
  const absoluteMinutes = Math.abs(diffMinutes);
  const value =
    absoluteMinutes < 60
      ? `${Math.max(1, absoluteMinutes)}m`
      : absoluteMinutes < 1440
        ? `${Math.round(absoluteMinutes / 60)}h`
        : `${Math.round(absoluteMinutes / 1440)}d`;

  return diffMinutes >= 0 ? `Due in ${value}` : `${value} overdue`;
}

function getStatusTone(status: PreparednessActionStatus, isOverdue: boolean): BadgeTone {
  if (isOverdue) return "danger";
  if (status === "COMPLETED") return "success";
  if (status === "CANCELLED" || status === "EXPIRED") return "default";
  if (status === "BLOCKED" || status === "ESCALATED") return "danger";
  if (status === "ACKNOWLEDGED" || status === "IN_PROGRESS" || status === "ASSIGNED") return "warning";
  return "info";
}

function getPriorityTone(priority: PreparednessActionPriority): BadgeTone {
  if (priority === "URGENT") return "danger";
  if (priority === "HIGH") return "warning";
  if (priority === "MEDIUM") return "info";
  return "default";
}

function getPriorityRank(priority: PreparednessActionPriority) {
  if (priority === "URGENT") return 4;
  if (priority === "HIGH") return 3;
  if (priority === "MEDIUM") return 2;
  return 1;
}

function getOwnerLabel(action: PreparednessActionRecord) {
  return action.assigned_to_username || action.assigned_to_team || "Unassigned";
}

function getLineageLabel(action: PreparednessActionRecord) {
  if (action.alert_public_id) return "Alert";
  if (action.alert_workflow_public_id) return "Alert workflow";
  if (action.chv_coverage_request_public_id) return "CHV coverage";
  if (action.facility_readiness_review_public_id) return "Facility review";
  if (action.facility_escalation_public_id) return "Facility escalation";
  if (action.risk_score) return "Risk score";
  return toTitleCase(action.source_trigger_type);
}

function evidenceEntries(evidence: Record<string, unknown>) {
  return Object.entries(evidence).filter(([, value]) => value !== null && value !== undefined && value !== "");
}

function matchesSearch(action: PreparednessActionRecord, search: string) {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return true;

  return [
    action.ward_name,
    action.facility_name ?? "",
    action.chv_name ?? "",
    ACTION_TYPE_LABELS[action.action_type],
    action.status,
    action.priority,
    getOwnerLabel(action),
    getLineageLabel(action),
    action.notes,
  ]
    .join(" ")
    .toLowerCase()
    .includes(normalized);
}

function filterAction(action: PreparednessActionRecord, filter: QueueFilter, currentUserId: number | null) {
  if (filter === "ACTIVE") return ACTIVE_STATUSES.has(action.status);
  if (filter === "OVERDUE") return action.is_overdue;
  if (filter === "BLOCKED") return action.status === "BLOCKED";
  if (filter === "COMPLETED") return action.status === "COMPLETED";
  if (filter === "MINE") return Boolean(currentUserId && action.assigned_to === currentUserId);
  if (filter === "UNASSIGNED") return !action.assigned_to && !action.assigned_to_team;
  return true;
}

function getBackendFiltersForQueueFilter(
  filter: QueueFilter,
): Pick<FetchPreparednessActionsParams, "assigned" | "ordering" | "overdue" | "status" | "statuses"> {
  if (filter === "ACTIVE") return { statuses: [...ACTIVE_STATUSES], ordering: "due_at" };
  if (filter === "OVERDUE") return { overdue: true, ordering: "due_at" };
  if (filter === "BLOCKED") return { status: "BLOCKED", ordering: "due_at" };
  if (filter === "COMPLETED") return { status: "COMPLETED", ordering: "-updated_at" };
  if (filter === "MINE") return { assigned: "mine", ordering: "due_at" };
  if (filter === "UNASSIGNED") return { assigned: "unassigned", ordering: "due_at" };
  return { ordering: "due_at" };
}

function sortActions(left: PreparednessActionRecord, right: PreparednessActionRecord) {
  if (left.is_overdue !== right.is_overdue) return left.is_overdue ? -1 : 1;
  const priorityDelta = getPriorityRank(right.priority) - getPriorityRank(left.priority);
  if (priorityDelta !== 0) return priorityDelta;

  const leftDue = left.due_at ? new Date(left.due_at).getTime() : Number.POSITIVE_INFINITY;
  const rightDue = right.due_at ? new Date(right.due_at).getTime() : Number.POSITIVE_INFINITY;
  return leftDue - rightDue;
}

function actionSummary(actions: PreparednessActionRecord[]) {
  return actions.reduce(
    (summary, action) => {
      summary.total += 1;
      if (ACTIVE_STATUSES.has(action.status)) summary.active += 1;
      if (action.is_overdue) summary.overdue += 1;
      if (action.status === "BLOCKED") summary.blocked += 1;
      if (action.status === "COMPLETED") summary.completed += 1;
      return summary;
    },
    { total: 0, active: 0, overdue: 0, blocked: 0, completed: 0 },
  );
}

function ActionDetailDrawer({
  action,
  canManage,
  onClose,
}: {
  action: PreparednessActionRecord | null;
  canManage: boolean;
  onClose: () => void;
}) {
  const updateActionMutation = useUpdatePreparednessActionMutation();
  const availableTransitions = action ? STATUS_TRANSITIONS[action.status] : [];
  const [targetStatus, setTargetStatus] = useState<PreparednessActionStatus | "">("");
  const [detail, setDetail] = useState("");
  const [assignedToTeam, setAssignedToTeam] = useState("");
  const [completionSummary, setCompletionSummary] = useState("");
  const [completionReference, setCompletionReference] = useState("");
  const [cancellationReason, setCancellationReason] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    setTargetStatus(availableTransitions[0] ?? "");
    setDetail("");
    setAssignedToTeam(action?.assigned_to_team ?? "");
    setCompletionSummary("");
    setCompletionReference("");
    setCancellationReason("");
    setFormError(null);
  }, [action?.public_id]);

  if (!action) {
    return null;
  }

  const currentAction = action;
  const completionEvidence = evidenceEntries(action.completion_evidence);
  const canSubmit = canManage && Boolean(targetStatus) && !updateActionMutation.isPending;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!targetStatus) return;

    const trimmedDetail = detail.trim();
    const payload: PreparednessActionTransitionPayload = {
      status: targetStatus,
      detail: trimmedDetail,
    };

    if (targetStatus === "ASSIGNED") {
      if (!assignedToTeam.trim() && !currentAction.assigned_to) {
        setFormError("Assigned actions need an owner or team.");
        return;
      }
      payload.assigned_to_team = assignedToTeam.trim();
    }

    if (targetStatus === "COMPLETED") {
      if (!completionSummary.trim()) {
        setFormError("Completion evidence summary is required.");
        return;
      }
      payload.completion_evidence = {
        summary: completionSummary.trim(),
        reference: completionReference.trim(),
        captured_via: "frontend_action_queue",
        captured_at: new Date().toISOString(),
      };
    }

    if (targetStatus === "CANCELLED") {
      if (!cancellationReason.trim()) {
        setFormError("Cancellation reason is required.");
        return;
      }
      payload.cancellation_reason = cancellationReason.trim();
    }

    if (targetStatus === "ESCALATED") {
      payload.escalation_metadata = {
        reason: trimmedDetail || "Escalated from action queue.",
        captured_via: "frontend_action_queue",
      };
    }

    setFormError(null);
    await updateActionMutation.mutateAsync({ publicId: currentAction.public_id, payload });
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="flex h-full w-full max-w-[34rem] flex-col overflow-y-auto border-l border-panel-border bg-panel p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <StatusBadge tone={getStatusTone(action.status, action.is_overdue)} className="rounded-full px-3 py-1 tracking-[0.14em]">
              {toTitleCase(action.status)}
            </StatusBadge>
            <h2 className="text-2xl font-semibold tracking-[-0.04em] text-panel-strong">
              {ACTION_TYPE_LABELS[action.action_type]}
            </h2>
            <p className="text-sm text-panel-muted">{action.ward_name}</p>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close action detail" onClick={onClose}>
            <X className="size-5" aria-hidden="true" />
          </Button>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {[
            ["Priority", action.priority],
            ["Owner", getOwnerLabel(action)],
            ["Due", formatTimestamp(action.due_at)],
            ["Source", getLineageLabel(action)],
          ].map(([label, value]) => (
            <div key={label} className="rounded-[1.25rem] border border-[var(--dashboard-table-line)] px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
              <p className="mt-2 text-sm font-semibold text-panel-strong">{value}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 space-y-4">
          <section className="rounded-[1.25rem] border border-[var(--dashboard-table-line)] px-4 py-4">
            <h3 className="text-sm font-semibold text-panel-strong">Completion evidence</h3>
            {completionEvidence.length ? (
              <dl className="mt-3 space-y-3">
                {completionEvidence.map(([key, value]) => (
                  <div key={key} className="border-b border-[var(--dashboard-table-line)] pb-3 last:border-b-0 last:pb-0">
                    <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{toTitleCase(key)}</dt>
                    <dd className="mt-1 break-words text-sm text-panel-copy">
                      {typeof value === "object" ? JSON.stringify(value) : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-sm text-panel-muted">No completion evidence recorded.</p>
            )}
          </section>

          <section className="rounded-[1.25rem] border border-[var(--dashboard-table-line)] px-4 py-4">
            <h3 className="text-sm font-semibold text-panel-strong">Event timeline</h3>
            {action.events.length ? (
              <ol className="mt-4 space-y-3">
                {action.events.slice().reverse().slice(0, 6).map((event) => (
                  <li key={event.public_id} className="flex gap-3">
                    <span className="mt-1 size-2 shrink-0 rounded-full bg-brand" />
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-panel-strong">{toTitleCase(event.event_type)}</p>
                      <p className="text-xs text-panel-muted">{formatTimestamp(event.created_at)}</p>
                      {event.detail ? <p className="text-sm text-panel-copy">{event.detail}</p> : null}
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-2 text-sm text-panel-muted">No lifecycle events recorded.</p>
            )}
          </section>
        </div>

        {canManage ? (
          <form className="mt-6 space-y-4 rounded-[1.25rem] border border-[var(--dashboard-table-line)] px-4 py-4" onSubmit={handleSubmit}>
            <div className="grid gap-1.5">
              <label htmlFor="target-status" className="text-sm font-semibold text-panel-strong">
                Update status
              </label>
              <select
                id="target-status"
                value={targetStatus}
                onChange={(event) => setTargetStatus(event.target.value as PreparednessActionStatus)}
                className="h-11 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-strong outline-none"
                disabled={!availableTransitions.length}
              >
                {availableTransitions.length ? null : <option value="">No transitions available</option>}
                {availableTransitions.map((status) => (
                  <option key={status} value={status}>
                    {toTitleCase(status)}
                  </option>
                ))}
              </select>
            </div>

            {targetStatus === "ASSIGNED" ? (
              <InputShell
                label="Assigned team"
                value={assignedToTeam}
                onChange={(event) => setAssignedToTeam(event.target.value)}
                placeholder="County operations"
              />
            ) : null}

            <label className="grid gap-1.5">
              <span className="text-sm font-semibold text-panel-strong">Operator note</span>
              <textarea
                value={detail}
                onChange={(event) => setDetail(event.target.value)}
                rows={3}
                className="min-h-24 rounded-[1.25rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-strong outline-none placeholder:text-panel-subtle"
                placeholder="Field check completed, CHV contacted, facility reviewed..."
              />
            </label>

            {targetStatus === "COMPLETED" ? (
              <div className="grid gap-3 rounded-[1rem] border border-[color-mix(in_srgb,var(--success)_20%,var(--dashboard-table-line))] px-3 py-3">
                <InputShell
                  label="Evidence summary"
                  value={completionSummary}
                  onChange={(event) => setCompletionSummary(event.target.value)}
                  placeholder="ORS stock verified and ward CHVs briefed"
                />
                <InputShell
                  label="Evidence reference"
                  value={completionReference}
                  onChange={(event) => setCompletionReference(event.target.value)}
                  placeholder="Facility note, call log, photo ref, dispatch ref"
                />
              </div>
            ) : null}

            {targetStatus === "CANCELLED" ? (
              <InputShell
                label="Cancellation reason"
                value={cancellationReason}
                onChange={(event) => setCancellationReason(event.target.value)}
                placeholder="Duplicate task replaced by county escalation"
              />
            ) : null}

            {formError ? <p className="text-sm font-semibold text-[color:var(--danger)]">{formError}</p> : null}
            {updateActionMutation.error instanceof Error ? (
              <p className="text-sm font-semibold text-[color:var(--danger)]">{updateActionMutation.error.message}</p>
            ) : null}

            <Button type="submit" disabled={!canSubmit} className="w-full">
              <Check className="size-4" aria-hidden="true" />
              Update action
            </Button>
          </form>
        ) : (
          <div className="mt-6 rounded-[1.25rem] border border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-muted">
            Lifecycle updates are limited to admin and supervisor accounts.
          </div>
        )}
      </div>
    </div>
  );
}

export default function PreparednessActionsPage() {
  const { currentUser } = useAuth();
  const searchParams = useSearchParams();
  const wardIdParam = searchParams.get("ward_id");
  const wardId = wardIdParam && Number.isFinite(Number(wardIdParam)) ? Number(wardIdParam) : null;
  const facilityIdParam = searchParams.get("facility_id");
  const facilityId = facilityIdParam && Number.isFinite(Number(facilityIdParam)) ? Number(facilityIdParam) : null;
  const chvIdParam = searchParams.get("chv_id");
  const chvId = chvIdParam && Number.isFinite(Number(chvIdParam)) ? Number(chvIdParam) : null;
  const [search, setSearch] = useState("");
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("ACTIVE");
  const [selectedPublicId, setSelectedPublicId] = useState<string | null>(null);
  const canManage = canManagePreparednessActions(currentUser?.role);
  const scopeLabels = [
    wardId ? `ward ${wardId}` : null,
    facilityId ? `facility ${facilityId}` : null,
    chvId ? `CHV ${chvId}` : null,
  ].filter(Boolean);
  const actionQueryFilters = useMemo<FetchPreparednessActionsParams>(
    () => ({
      page_size: 200,
      ward_id: wardId ?? undefined,
      facility_id: facilityId ?? undefined,
      chv_id: chvId ?? undefined,
      ...getBackendFiltersForQueueFilter(queueFilter),
    }),
    [chvId, facilityId, queueFilter, wardId],
  );
  const actionsQuery = usePreparednessActionsQuery({
    filters: actionQueryFilters,
    enabled: Boolean(currentUser),
  });
  const actions = actionsQuery.data?.results ?? [];
  const summary = actionSummary(actions);
  const summaryCards: Array<{ label: string; value: number; icon: LucideIcon; tone: BadgeTone }> = [
    { label: "Total", value: summary.total, icon: ClipboardList, tone: "info" },
    { label: "Active", value: summary.active, icon: Play, tone: "warning" },
    { label: "Overdue", value: summary.overdue, icon: Clock3, tone: summary.overdue ? "danger" : "default" },
    { label: "Blocked", value: summary.blocked, icon: Ban, tone: summary.blocked ? "danger" : "default" },
    { label: "Completed", value: summary.completed, icon: CheckCircle2, tone: "success" },
  ];

  const filteredActions = useMemo(
    () =>
      actions
        .filter((action) => filterAction(action, queueFilter, currentUser?.id ?? null))
        .filter((action) => matchesSearch(action, search))
        .slice()
        .sort(sortActions),
    [actions, currentUser?.id, queueFilter, search],
  );

  const selectedAction = actions.find((action) => action.public_id === selectedPublicId) ?? null;
  const latestUpdatedAt = actions
    .map((action) => action.updated_at)
    .filter(Boolean)
    .sort()
    .at(-1) ?? null;

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Action Queue"
        subtitle={
          scopeLabels.length
            ? `Preparedness tasks for ${scopeLabels.join(", ")}`
            : "Preparedness tasks across visible wards"
        }
        lastUpdatedLabel={actionsQuery.isFetching ? "Refreshing..." : formatTimestamp(latestUpdatedAt)}
        lastUpdatedTone={summary.overdue > 0 || summary.blocked > 0 ? "stale" : "default"}
        onRefresh={() => {
          void actionsQuery.refetch();
        }}
      />

      {actionsQuery.error instanceof Error ? (
        <div className="rounded-2xl border border-[color-mix(in_srgb,var(--danger)_20%,white)] bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--danger)]">
          <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
          {actionsQuery.error.message}
        </div>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {summaryCards.map(({ label, value, icon: SummaryIcon, tone }) => {
          return (
            <Card key={label} className="p-5">
              <div className="flex items-center justify-between gap-3">
                <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                  <SummaryIcon className="size-5" aria-hidden="true" />
                </span>
                <StatusBadge tone={tone} className="rounded-full px-2.5 py-1 tracking-[0.12em]">
                  {label}
                </StatusBadge>
              </div>
              <p className="mt-5 text-3xl font-semibold tracking-[-0.05em] text-panel-strong">{String(value)}</p>
            </Card>
          );
        })}
      </section>

      <Card className="space-y-5 p-5 md:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center gap-3">
            <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_20%,transparent)]">
              <ShieldCheck className="size-5" aria-hidden="true" />
            </span>
            <div>
              <h1 className="text-2xl font-semibold tracking-[-0.04em] text-panel-strong">Preparedness task ledger</h1>
              <p className="text-sm text-panel-muted">{filteredActions.length} visible actions</p>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <InputShell
              className="sm:w-72"
              icon={<Search className="size-4" aria-hidden="true" />}
              placeholder="Search ward, task, owner"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search action queue"
            />
            <div className="flex flex-wrap gap-2" aria-label="Action queue filters">
              {(Object.keys(FILTER_LABELS) as QueueFilter[]).map((filter) => (
                <Button
                  key={filter}
                  variant={queueFilter === filter ? "primary" : "secondary"}
                  size="sm"
                  className="gap-1.5"
                  onClick={() => setQueueFilter(filter)}
                >
                  {filter === "OVERDUE" || filter === "BLOCKED" ? <Filter className="size-3.5" aria-hidden="true" /> : null}
                  {FILTER_LABELS[filter]}
                </Button>
              ))}
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-[1.25rem] border border-[var(--dashboard-table-line)]">
          <div className="grid grid-cols-[1.2fr_0.9fr_0.85fr_0.8fr_0.8fr_auto] gap-4 border-b border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted max-[980px]:hidden">
            <span>Action</span>
            <span>Ward</span>
            <span>Status</span>
            <span>Due</span>
            <span>Owner</span>
            <span>Open</span>
          </div>

          {actionsQuery.isPending ? (
            <div className="space-y-3 px-4 py-5">
              {[1, 2, 3].map((item) => (
                <div key={item} className="h-16 animate-pulse rounded-[1rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_42%,transparent)]" />
              ))}
            </div>
          ) : filteredActions.length ? (
            <div className="divide-y divide-[var(--dashboard-table-line)]">
              {filteredActions.map((action) => (
                <article
                  key={action.public_id}
                  className="grid grid-cols-[1.2fr_0.9fr_0.85fr_0.8fr_0.8fr_auto] items-center gap-4 px-4 py-4 max-[980px]:grid-cols-1"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-panel-strong">{ACTION_TYPE_LABELS[action.action_type]}</p>
                      <StatusBadge tone={getPriorityTone(action.priority)} className="rounded-full px-2 py-0.5 tracking-[0.12em]">
                        {action.priority}
                      </StatusBadge>
                    </div>
                    <p className="mt-1 text-sm text-panel-muted">{getLineageLabel(action)}</p>
                  </div>

                  <div>
                    <Link href={`/wards/${action.ward}`} className="text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]">
                      {action.ward_name}
                    </Link>
                    {action.facility_name ? <p className="text-xs text-panel-muted">{action.facility_name}</p> : null}
                    {action.chv_name ? <p className="text-xs text-panel-muted">{action.chv_name}</p> : null}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone={getStatusTone(action.status, action.is_overdue)} className="rounded-full px-3 py-1 tracking-[0.14em]">
                      {toTitleCase(action.status)}
                    </StatusBadge>
                    {action.is_overdue ? <span className="text-xs font-semibold text-[color:var(--danger)]">Overdue</span> : null}
                  </div>

                  <div>
                    <p className="text-sm font-semibold text-panel-strong">{formatTimestamp(action.due_at)}</p>
                    <p className="text-xs text-panel-muted">{formatDueDelta(action.due_at)}</p>
                  </div>

                  <div className="flex items-center gap-2 text-sm text-panel-copy">
                    <UserRound className="size-4 shrink-0 text-panel-muted" aria-hidden="true" />
                    <span className="min-w-0 truncate">{getOwnerLabel(action)}</span>
                  </div>

                  <Button variant="secondary" size="sm" onClick={() => setSelectedPublicId(action.public_id)}>
                    <Link2 className="size-4" aria-hidden="true" />
                    Open action
                  </Button>
                </article>
              ))}
            </div>
          ) : (
            <div className="px-4 py-10 text-center">
              <p className="font-semibold text-panel-strong">No preparedness actions match this view.</p>
              <p className="mt-1 text-sm text-panel-muted">Try a different status filter or search term.</p>
            </div>
          )}
        </div>
      </Card>

      <ActionDetailDrawer action={selectedAction} canManage={canManage} onClose={() => setSelectedPublicId(null)} />
    </div>
  );
}
