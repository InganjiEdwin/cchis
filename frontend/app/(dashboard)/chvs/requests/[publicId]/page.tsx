"use client";

import { AlertTriangle, ArrowLeft, ClipboardList, ShieldAlert, UserPlus } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { hasActionCapability } from "@/lib/capabilities";
import { type ChvCoverageRequestRecord } from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { useAssignChvCoverageRequestMutation } from "@/queries/use-assign-chv-coverage-request-mutation";
import { useChvCoverageRequestDetailQuery } from "@/queries/use-chv-coverage-request-detail-query";
import { useChvOperationsQuery } from "@/queries/use-chv-operations-query";

function getCoverageRequestStatusTone(status: ChvCoverageRequestRecord["status"]) {
  if (status === "REJECTED" || status === "CANCELLED") {
    return "warning" as const;
  }
  if (status === "RESOLVED") {
    return "success" as const;
  }
  if (status === "IN_PROGRESS") {
    return "info" as const;
  }
  return "default" as const;
}

function hasStoredAlertLinkage(requestRecord: Pick<ChvCoverageRequestRecord, "trigger_source" | "linked_alerts_summary">) {
  return requestRecord.trigger_source === "ALERT_DRIVEN" && requestRecord.linked_alerts_summary.length > 0;
}

function hasLinkedAlertContext(requestRecord: Pick<ChvCoverageRequestRecord, "linked_alerts_summary">) {
  return requestRecord.linked_alerts_summary.length > 0;
}

function getCoverageRequestSourceLabel(requestRecord: Pick<ChvCoverageRequestRecord, "trigger_source" | "linked_alerts_summary">) {
  return hasStoredAlertLinkage(requestRecord) ? "Alert-driven request" : "Manual request";
}

function getCoverageRequestSourceDescription(
  requestRecord: Pick<ChvCoverageRequestRecord, "trigger_source" | "linked_alerts_summary">,
) {
  if (hasStoredAlertLinkage(requestRecord)) {
    return "This request was opened from alert context.";
  }
  if (hasLinkedAlertContext(requestRecord)) {
    return "This request was opened manually and later linked to alert context.";
  }
  return "This request was opened without stored alert-linked context.";
}

export default function ChvCoverageRequestPage() {
  const params = useParams<{ publicId: string }>();
  const { currentUser } = useAuth();
  const [assignmentChvId, setAssignmentChvId] = useState<number | null>(null);
  const [assignmentNotes, setAssignmentNotes] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  const publicId = useMemo(() => params.publicId ?? null, [params.publicId]);
  const canManageAssignments = hasActionCapability(currentUser, "manage_chv_operations");
  const detailQuery = useChvCoverageRequestDetailQuery({
    publicId,
    enabled: Boolean(currentUser) && Boolean(publicId),
  });
  const operationsQuery = useChvOperationsQuery({
    enabled: Boolean(currentUser) && canManageAssignments && detailQuery.isSuccess,
  });
  const assignMutation = useAssignChvCoverageRequestMutation();

  const requestRecord = detailQuery.data ?? null;
  const wardChvs = useMemo(() => {
    if (!requestRecord) {
      return [];
    }

    return (operationsQuery.data?.chvs ?? []).filter(
      (chv) =>
        chv.ward === requestRecord.ward &&
        chv.is_active &&
        chv.operational_status !== "OFFLINE",
    );
  }, [operationsQuery.data?.chvs, requestRecord]);

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="CHV Coverage Request"
        subtitle="Recorded request state, assignment readiness, and audit timeline"
        lastUpdatedLabel={requestRecord ? formatRelativeTimestamp(requestRecord.updated_at) : "Loading request"}
        lastUpdatedTone={requestRecord?.is_overdue ? "stale" : "default"}
      />

      <div className="flex items-center gap-3">
        <Link
          href="/chvs"
          className="inline-flex h-10 items-center justify-center rounded-pill border border-panel-table-wrap px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
        >
          <ArrowLeft className="mr-2 size-4" aria-hidden="true" />
          Back to CHV Operations
        </Link>
      </div>

      {detailQuery.error instanceof Error ? (
        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
          {detailQuery.error.message}
        </StatusBanner>
      ) : null}
      {assignMutation.error instanceof Error ? (
        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
          {assignMutation.error.message}
        </StatusBanner>
      ) : null}
      {feedback ? (
        <StatusBanner tone="success" icon={<ShieldAlert aria-hidden="true" />}>
          {feedback}
        </StatusBanner>
      ) : null}

      {detailQuery.isPending || !requestRecord ? (
        <Card className="rounded-[2rem] px-5 py-8">
          <p className="text-sm text-panel-muted">Loading CHV coverage request detail...</p>
        </Card>
      ) : (
        <>
          <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
            <Card className="rounded-[2rem] px-5 py-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Coverage request</span>
                  <h1 className="mt-2 text-[clamp(1.7rem,1rem+1vw,2.5rem)] font-semibold leading-tight text-panel-strong">
                    {requestRecord.ward_name}
                  </h1>
                  <p className="mt-2 text-sm text-panel-muted">
                    Requested by {requestRecord.requested_by_username ?? "Unknown"} · {formatRelativeTimestamp(requestRecord.created_at)}
                  </p>
                </div>
                <StatusBadge tone={getCoverageRequestStatusTone(requestRecord.status)}>{requestRecord.status}</StatusBadge>
              </div>

              <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ["Priority", requestRecord.priority],
                  ["Source", getCoverageRequestSourceLabel(requestRecord)],
                  ["Requested CHVs", String(requestRecord.requested_chv_count)],
                  ["Assignments", String(requestRecord.assignments.length)],
                ].map(([label, value]) => (
                  <Card key={label} className="rounded-2xl px-4 py-4 shadow-none">
                    <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">{label}</span>
                    <strong className="mt-2 block text-base text-panel-strong">{value}</strong>
                  </Card>
                ))}
              </div>

              <Card className="mt-6 rounded-2xl px-4 py-4 shadow-none">
                <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Request source</h2>
                <p className="mt-3 text-sm leading-6 text-panel-copy">
                  {getCoverageRequestSourceDescription(requestRecord)}
                </p>
                {requestRecord.linked_alerts_summary.length ? (
                  <div className="mt-4 space-y-3">
                    {requestRecord.linked_alerts_summary.map((alertSummary) => (
                      <div key={alertSummary.alert_public_id} className="rounded-2xl border border-panel-table-wrap px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <strong className="text-sm text-panel-strong">Alert {alertSummary.alert_public_id}</strong>
                          <StatusBadge tone={alertSummary.status === "DELIVERED" ? "success" : alertSummary.status === "FAILED" ? "warning" : "info"}>
                            {alertSummary.status}
                          </StatusBadge>
                        </div>
                        <p className="mt-2 text-sm text-panel-copy">
                          {alertSummary.ward_name ?? requestRecord.ward_name} · {alertSummary.channel}
                          {alertSummary.risk_score !== null ? ` · Risk score ${Math.round(alertSummary.risk_score)}` : ""}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Link
                            href={`/alerts/${alertSummary.alert_id}`}
                            className="inline-flex h-9 items-center justify-center rounded-pill border border-panel-table-wrap px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                          >
                            Open alert
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </Card>

              <Card className="mt-6 rounded-2xl px-4 py-4 shadow-none">
                <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Reason</h2>
                <p className="mt-3 text-sm leading-6 text-panel-copy">{requestRecord.reason}</p>
                {requestRecord.notes ? <p className="mt-3 text-sm leading-6 text-panel-muted">{requestRecord.notes}</p> : null}
              </Card>

              <Card className="mt-6 rounded-2xl px-4 py-4 shadow-none">
                <div className="flex items-center gap-2">
                  <ClipboardList className="size-4 text-panel-muted" aria-hidden="true" />
                  <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Audit timeline</h2>
                </div>
                <div className="mt-4 space-y-3">
                  {requestRecord.events.length ? (
                    requestRecord.events.map((event) => (
                      <div key={event.public_id} className="rounded-2xl border border-panel-table-wrap px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <strong className="text-sm text-panel-strong">{event.action.replaceAll("_", " ")}</strong>
                          <span className="text-xs text-panel-muted">{formatRelativeTimestamp(event.created_at)}</span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-panel-copy">{event.detail}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-panel-muted">No workflow events are recorded for this request yet.</p>
                  )}
                </div>
              </Card>
            </Card>

            <div className="space-y-5">
              <Card className="rounded-[2rem] px-5 py-5">
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Assignment controls</span>
                {requestRecord.status === "APPROVED" && canManageAssignments ? (
                  <div className="mt-4 space-y-4">
                    <p className="text-sm text-panel-copy">
                      Assignment is available here because the backend request is approved. This surface only offers real ward-linked CHVs from current records.
                    </p>
                    {wardChvs.length ? (
                      <>
                        <select
                          value={assignmentChvId ?? ""}
                          onChange={(event) => setAssignmentChvId(Number(event.target.value) || null)}
                          className="h-11 w-full rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
                        >
                          <option value="">Select CHV</option>
                          {wardChvs.map((chv) => (
                            <option key={chv.id} value={chv.id}>
                              {chv.name} · {chv.phone_number}
                            </option>
                          ))}
                        </select>
                        <textarea
                          value={assignmentNotes}
                          onChange={(event) => setAssignmentNotes(event.target.value)}
                          rows={3}
                          placeholder="Optional assignment notes"
                          className="w-full rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-strong outline-none"
                        />
                        <Button
                          disabled={!assignmentChvId || assignMutation.isPending}
                          onClick={async () => {
                            if (!assignmentChvId) {
                              return;
                            }

                            try {
                              await assignMutation.mutateAsync({
                                publicId: requestRecord.public_id,
                                payload: {
                                  chv_id: assignmentChvId,
                                  notes: assignmentNotes.trim(),
                                },
                              });
                              setFeedback(`CHV assigned for ${requestRecord.ward_name}.`);
                            } catch {
                              // Error handled by banner.
                            }
                          }}
                        >
                          <UserPlus className="mr-2 size-4" aria-hidden="true" />
                          {assignMutation.isPending ? "Assigning CHV..." : "Assign CHV"}
                        </Button>
                      </>
                    ) : (
                      <StatusBanner tone="warning">No active ward-linked CHVs are available for direct assignment here.</StatusBanner>
                    )}
                  </div>
                ) : requestRecord.status === "APPROVED" ? (
                  <p className="mt-4 text-sm text-panel-muted">
                    This request is approved, but assignment controls are limited to Admin and Supervisor roles.
                  </p>
                ) : (
                  <p className="mt-4 text-sm text-panel-muted">
                    Assign CHV is only available inside request detail when the workflow is approved and assignment-ready.
                  </p>
                )}
              </Card>

              <Card className="rounded-[2rem] px-5 py-5">
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Assignments</span>
                <div className="mt-4 space-y-3">
                  {requestRecord.assignments.length ? (
                    requestRecord.assignments.map((assignment) => (
                      <div key={assignment.public_id} className="rounded-2xl border border-panel-table-wrap px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <strong className="text-sm text-panel-strong">{assignment.chv_name}</strong>
                          <StatusBadge tone={assignment.status === "ACTIVE" ? "info" : assignment.status === "COMPLETED" ? "success" : "warning"}>
                            {assignment.status}
                          </StatusBadge>
                        </div>
                        <p className="mt-2 text-sm text-panel-copy">
                          Assigned by {assignment.assigned_by_username ?? "Unknown"} · {formatRelativeTimestamp(assignment.created_at)}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-panel-muted">No CHV assignments are linked to this request yet.</p>
                  )}
                </div>
              </Card>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
