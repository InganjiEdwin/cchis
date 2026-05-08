"use client";

import {
  AlertTriangle,
  ArrowLeft,
  Bell,
  Building2,
  MapPinned,
  PackagePlus,
  ShieldAlert,
  Truck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { DashboardTopbar } from "@/components/dashboard-topbar";
import { MigoriWardMap } from "@/components/migori-ward-map";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { riskTone } from "@/lib/facility-readiness";
import { describeFreshness, formatRelativeTimestamp } from "@/lib/freshness";
import { useFacilityDetailQuery } from "@/queries/use-facility-detail-query";
import {
  useAcknowledgeFacilityReadinessReviewMutation,
  useCreateFacilityEscalationMutation,
  useCreateFacilityReadinessReviewMutation,
  useCreateFacilityUpdateRequestMutation,
} from "@/queries/use-facility-readiness-actions";

function timelineToneClasses(tone: "danger" | "warning" | "info" | "success") {
  switch (tone) {
    case "danger":
      return "border border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_13%,var(--dashboard-panel-surface))] text-[color:var(--danger)]";
    case "success":
      return "border border-[color-mix(in_srgb,var(--success)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--success)_13%,var(--dashboard-panel-surface))] text-[color:var(--success)]";
    case "warning":
      return "border border-[color-mix(in_srgb,var(--warning)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_14%,var(--dashboard-panel-surface))] text-[color:var(--warning)]";
    case "info":
    default:
      return "border border-[color-mix(in_srgb,var(--brand)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--brand)_13%,var(--dashboard-panel-surface))] text-brand";
  }
}

function compactTimelineDescription(item: { id: string; category: string; description: string; meta: string | null }) {
  if (item.id === "facility-record") {
    return "Derived from facility identity and ward risk.";
  }

  if (item.category === "alert") {
    return item.description
      .replace(/^Pilot alert for [^.]+\.?\s*/i, "")
      .replace(/Risk level:\s*/i, "Risk: ")
      .replace(/\.\s*Predicted cases:\s*/i, " | Predicted: ")
      .replace(/\.$/, "");
  }

  return item.meta ?? item.description;
}

function workflowStatusLabel(status: string | null | undefined) {
  if (!status) {
    return "No active workflow";
  }
  return status
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function reasonCodeLabel(code: string) {
  return code
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function actionMutationError(...errors: Array<unknown>) {
  const error = errors.find(Boolean);
  return error instanceof Error ? error.message : null;
}

export default function FacilityDetailPage() {
  const params = useParams<{ id: string }>();
  const facilityId = Number(params.id);
  const [isUpdateRequestModalOpen, setIsUpdateRequestModalOpen] = useState(false);
  const [updateRequestMessage, setUpdateRequestMessage] = useState("");
  const { data, isPending: isLoading, error } = useFacilityDetailQuery(
    Number.isInteger(facilityId) && facilityId > 0 ? facilityId : null,
  );
  const intelligence = data?.intelligence ?? null;
  const facilityRecord = intelligence?.facility ?? null;
  const readiness = intelligence?.readiness ?? null;
  const context = intelligence?.context ?? null;
  const decisionSummary = intelligence?.decision_summary ?? null;
  const timeline = intelligence?.timeline ?? [];
  const capabilities = intelligence?.capabilities ?? null;
  const activeReview = intelligence?.active_review ?? null;
  const activeUpdateRequest = intelligence?.active_update_request ?? null;
  const activeEscalation = intelligence?.active_escalation ?? null;
  const contact = intelligence?.contact ?? null;
  const linkedAlerts = intelligence?.linked_alerts ?? [];
  const chvOperations = intelligence?.chv_operations ?? null;
  const wardMap = data?.wardMap ?? null;
  const createReviewMutation = useCreateFacilityReadinessReviewMutation(Number.isInteger(facilityId) && facilityId > 0 ? facilityId : null);
  const acknowledgeReviewMutation = useAcknowledgeFacilityReadinessReviewMutation(Number.isInteger(facilityId) && facilityId > 0 ? facilityId : null);
  const createUpdateRequestMutation = useCreateFacilityUpdateRequestMutation(Number.isInteger(facilityId) && facilityId > 0 ? facilityId : null);
  const createEscalationMutation = useCreateFacilityEscalationMutation(Number.isInteger(facilityId) && facilityId > 0 ? facilityId : null);
  const selectedMapWard = useMemo(
    () => wardMap?.features.find((feature) => feature.properties.backend_ward_id === facilityRecord?.ward) ?? null,
    [facilityRecord?.ward, wardMap],
  );
  const focusedWardMapFeatures = useMemo(() => (selectedMapWard ? [selectedMapWard] : []), [selectedMapWard]);
  const latestTimestamp = intelligence?.freshness.updated_at ?? null;
  const freshness = useMemo(() => describeFreshness(latestTimestamp, 120), [latestTimestamp]);
  const lastUpdatedLabel = latestTimestamp ? formatRelativeTimestamp(latestTimestamp) : freshness.label;

  if (!isLoading && (!facilityRecord || !readiness || !context || !capabilities)) {
    notFound();
  }

  const isLowConfidence =
    Boolean(decisionSummary?.confidence === "DEGRADED" || readiness?.freshness_state === "STALE" || freshness.isStale);
  const isFlaggedForReview = Boolean(
    decisionSummary?.state === "REVIEW" ||
      decisionSummary?.state === "DEGRADED_CONFIDENCE" ||
      readiness?.surge_risk === "EXTREME" ||
      readiness?.surge_risk === "MODERATE",
  );
  const readinessUnavailable = readiness?.dashboard_truth_state === "unavailable" || readiness?.backing_source === "unavailable";
  const readinessBannerTitle = readinessUnavailable ? "Full readiness assessment unavailable" : readiness?.status_banner_label;
  const readinessBannerBody = readinessUnavailable
    ? "Facility-level forecast data is not yet integrated. Current metrics are derived from ward-level signals."
    : isLowConfidence
      ? "Current guidance is limited by stale or proxy-backed inputs."
      : "Current calculated readiness signals are available for review.";
  const decisionContextLabel = isFlaggedForReview
    ? "Flagged for readiness review"
    : "Not currently flagged for readiness review";
  const decisionContextDetail = isLowConfidence
    ? "Assessment confidence: low due to stale or proxy-backed data."
    : "Assessment confidence: normal for the current derived inputs.";
  const riskContextSummary = readinessUnavailable
    ? "No facility-level forecast available. Capacity estimates are derived from ward risk only."
    : context?.summary ?? "";
  const primaryLinkedAlert = linkedAlerts[0] ?? null;
  const hasAnyWorkflowAction = Boolean(
    capabilities?.can_open_linked_alert ||
      capabilities?.can_open_chv_operations ||
    capabilities?.can_request_facility_update ||
      (capabilities?.can_escalate_county_review && capabilities?.has_county_review_queue) ||
      capabilities?.can_acknowledge_review ||
      capabilities?.can_open_readiness_review,
  );
  const mutationError = actionMutationError(
    createReviewMutation.error,
    acknowledgeReviewMutation.error,
    createUpdateRequestMutation.error,
    createEscalationMutation.error,
  );

  const defaultUpdateRequestMessage = facilityRecord
    ? `Please share the latest readiness update for ${facilityRecord.name}: ORS availability, staffing, and any capacity concerns.`
    : "";

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Facility Detail"
        subtitle="Facility identity and calculated facility summary are shown here."
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
      />

      <RoleGate
        pageCapability="facility_readiness"
        title="Facility detail is role-restricted"
        message="Facility detail is intended for dashboard roles coordinating preparedness and response."
      >
        {error ? (
          <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
            {error instanceof Error ? error.message : "Unable to load facility detail."}
          </StatusBanner>
        ) : null}

        {isLoading || !facilityRecord || !readiness || !context || !capabilities ? (
          <Card className="rounded-[2rem] p-6 text-sm text-panel-muted">Loading facility detail...</Card>
        ) : (
          <>
            <Card className="rounded-[2rem] px-5 py-5">
              <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                <div className="space-y-3">
                  <Link
                    href="/facility-readiness"
                    className="inline-flex items-center gap-2 text-sm font-medium text-panel-muted transition hover:text-panel-strong"
                  >
                    <ArrowLeft className="size-4" aria-hidden="true" />
                    Back to Facilities
                  </Link>
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={riskTone(readiness.surge_risk)} className="tracking-[0.14em]">
                        {readiness.surge_risk_label} calculated risk
                      </StatusBadge>
                      <span className="text-sm text-panel-muted">Last reported: {readiness.last_reported_at ? formatRelativeTimestamp(readiness.last_reported_at) : "No timestamp recorded"}</span>
                    </div>
                    <h1 className="text-4xl font-semibold text-panel-strong">
                      {facilityRecord.name}
                    </h1>
                    <p className="text-sm text-panel-muted">
                      {facilityRecord.sub_county} Sub-County | {readiness.facility_type_label} | {facilityRecord.ward_name} Ward
                    </p>
                    <div className="inline-flex flex-wrap items-center gap-2 rounded-[1rem] border border-panel-table-wrap px-3 py-2 text-xs text-panel-copy">
                      <span className="font-semibold text-panel-strong">{decisionContextLabel}</span>
                      <span className={cn("font-medium", isLowConfidence ? "text-[color:var(--warning)]" : "text-panel-muted")}>
                        {decisionContextDetail}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="max-w-md rounded-[1.25rem] border border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_10%,var(--dashboard-panel-surface))] px-4 py-3">
                  <div className="text-sm font-semibold text-[color:var(--danger)]">{readinessBannerTitle}</div>
                  <p className="mt-1 text-xs leading-5 text-panel-copy">{readinessBannerBody}</p>
                </div>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="border-l-2 border-[color:var(--danger)] px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated risk</span>
                  <div className="mt-3 text-2xl font-semibold text-[color:var(--danger)]">
                    {readiness.surge_risk_label}
                  </div>
                </div>
                <div className="border-l-2 border-panel-table-wrap px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated load</span>
                  <div className="mt-3 text-2xl font-semibold text-panel-strong">~{readiness.predicted_cases_per_day} <span className="text-sm font-medium text-panel-muted">cases/day</span></div>
                </div>
                <div className="border-l-2 border-[color:var(--danger)] px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated ORS estimate</span>
                  <div className="mt-3 text-2xl font-semibold text-[color:var(--danger)]">
                    {readiness.ors_estimate_percent}% <span className="text-xs font-semibold uppercase">{readiness.ors_state}</span>
                  </div>
                </div>
                <div className="border-l-2 border-panel-table-wrap px-4 py-2">
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Calculated staffing estimate</span>
                  <div className="mt-3 text-2xl font-semibold text-panel-strong">
                    {readiness.staffing_filled}/{readiness.staffing_required} <span className="text-sm font-medium text-panel-muted">Active</span>
                  </div>
                </div>
              </div>
            </Card>

            <section className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_22rem]">
              <div className="space-y-5">
                <Card className="rounded-[2rem] px-4 py-4">
                  <div className="flex items-center gap-3 text-sm font-semibold text-panel-strong">
                    <MapPinned className="size-7 text-brand" aria-hidden="true" />
                    Risk Context
                  </div>

                  <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
                    <div className="space-y-4">
                      <p className="text-sm leading-6 text-panel-copy">{riskContextSummary}</p>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">Ward risk score</div>
                          <div className="mt-2 text-sm font-semibold text-panel-strong">
                            {context.ward_risk_score?.toFixed(2) ?? "--"}
                          </div>
                        </div>
                        <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">Ward-linked alerts</div>
                          <div className="mt-2 text-sm font-semibold text-panel-strong">
                            {context.ward_alert_count}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="overflow-hidden rounded-[1.5rem] border border-panel-table-wrap bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_10%,var(--dashboard-panel-surface)),transparent_35%),radial-gradient(circle_at_bottom_right,color-mix(in_srgb,var(--warning)_10%,var(--dashboard-panel-surface)),transparent_32%),linear-gradient(135deg,color-mix(in_srgb,var(--dashboard-table-line)_18%,var(--dashboard-panel-surface)),var(--dashboard-panel-surface))] p-4">
                      <div className="flex h-full min-h-[14rem] flex-col gap-3 rounded-[1.1rem] border border-panel-table-wrap bg-panel/80 p-4">
                        <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-panel-subtle">
                          <span>Selected ward map</span>
                          <span>{selectedMapWard ? "Focused geometry" : "No ward geometry"}</span>
                        </div>
                        <div className="min-h-[13rem] rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,var(--dashboard-panel-surface))] p-2">
                          {focusedWardMapFeatures.length ? (
                            <MigoriWardMap
                              features={focusedWardMapFeatures}
                              selectedWardCode={selectedMapWard?.properties.ward_code ?? null}
                              onSelectWard={() => undefined}
                            />
                          ) : (
                            <div className="flex h-full items-center justify-center text-center text-sm text-panel-muted">
                              Ward geometry is not available for this facility view yet.
                            </div>
                          )}
                        </div>
                        <div className="inline-flex w-max items-center gap-2 rounded-full border border-[color-mix(in_srgb,var(--brand)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--brand)_12%,var(--dashboard-panel-surface))] px-3 py-1.5 text-xs font-semibold text-panel-strong">
                          <span className="size-2 rounded-full bg-brand" />
                          {selectedMapWard?.properties.name ?? facilityRecord.ward_name} ward context
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>

                <div className="space-y-3">
                  <h2 className="text-lg font-semibold text-panel-strong">Resource Estimates</h2>
                  <div className="grid gap-4 md:grid-cols-3">
                    <Card className="rounded-[1.6rem] bg-panel px-4 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--danger)_12%,var(--panel))] text-[color:var(--danger)]">
                          <PackagePlus className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-[color:var(--danger)]">{readiness.ors_state} estimate</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">ORS coverage estimate</div>
                      <div className="mt-2 text-3xl font-semibold text-panel-strong">{readiness.ors_estimate_percent}%</div>
                      <div className="mt-1 text-sm text-panel-muted">Calculated from ward pressure</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--danger)_14%,var(--dashboard-panel-surface))]">
                        <div className="h-full rounded-full bg-[color:var(--danger)]" style={{ width: `${readiness.ors_estimate_percent}%` }} />
                      </div>
                    </Card>

                    <Card className="rounded-[1.6rem] bg-panel px-4 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl border border-[color-mix(in_srgb,var(--brand)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--brand)_13%,var(--dashboard-panel-surface))] text-brand">
                          <Users className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-brand">{readiness.staffing_state} estimate</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Staffing adequacy</div>
                      <div className="mt-2 text-3xl font-semibold text-panel-strong">{readiness.staffing_percent}%</div>
                      <div className="mt-1 text-sm text-panel-muted">Calculated from ward pressure</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--brand)_14%,var(--dashboard-panel-surface))]">
                        <div className="h-full rounded-full bg-brand" style={{ width: `${readiness.staffing_percent}%` }} />
                      </div>
                    </Card>

                    <Card className="rounded-[1.6rem] bg-panel px-4 py-4">
                      <div className="flex items-center justify-between">
                        <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_12%,var(--panel))] text-[color:var(--warning)]">
                          <Building2 className="size-4" aria-hidden="true" />
                        </span>
                        <span className="text-xs font-semibold text-[color:var(--warning)]">{readiness.surge_risk_label}</span>
                      </div>
                      <div className="mt-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Expected daily load</div>
                      <div className="mt-2 text-3xl font-semibold text-panel-strong">~{readiness.predicted_cases_per_day}</div>
                      <div className="mt-1 text-sm text-panel-muted">Calculated cases/day estimate</div>
                      <div className="mt-4 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--warning)_14%,var(--dashboard-panel-surface))]">
                        <div className="h-full rounded-full bg-[color:var(--warning)]" style={{ width: `${Math.min(100, readiness.projected_cases * 4)}%` }} />
                      </div>
                    </Card>
                  </div>
                </div>

                <Card className="rounded-[2rem] px-4 py-4">
                  <h2 className="text-lg font-semibold text-panel-strong">Facility Record Timeline</h2>
                  <div className="mt-4 space-y-3">
                    {timeline.map((item) => (
                      <div key={item.id} className="flex gap-3">
                        <div className={cn("mt-1 inline-flex size-9 shrink-0 items-center justify-center rounded-full", timelineToneClasses(item.tone))}>
                          {item.tone === "danger" ? <AlertTriangle className="size-4" aria-hidden="true" /> : item.tone === "warning" ? <Bell className="size-4" aria-hidden="true" /> : <Truck className="size-4" aria-hidden="true" />}
                        </div>
                        <div className="min-w-0 flex-1 rounded-[1.1rem] border border-panel-table-wrap px-4 py-3">
                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <strong className="text-panel-strong">{item.title}</strong>
                            <span className="text-panel-muted">{item.timestamp ? formatRelativeTimestamp(item.timestamp) : "No timestamp recorded"}</span>
                          </div>
                          <p className="mt-1 text-sm leading-5 text-panel-copy">{compactTimelineDescription(item)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="rounded-[2rem] px-4 py-4">
                  <h2 className="text-lg font-semibold text-panel-strong">Operational History</h2>
                  <div className="mt-4 rounded-[1.25rem] border border-dashed border-panel-table-wrap px-4 py-4 text-sm text-panel-copy">
                    No operational workflow activity is recorded for this facility.
                  </div>
                </Card>
              </div>

              <div className="space-y-5">
                <Card className="rounded-[2rem] px-4 py-4">
                  <div className="flex items-center gap-3 text-sm font-semibold text-panel-strong">
                    <ShieldAlert className="size-7 text-brand" aria-hidden="true" />
                    Operational Actions
                  </div>
                  <div className="mt-4 rounded-[1.1rem] border border-panel-table-wrap px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-panel-strong">
                        {activeReview ? "Readiness review active" : isFlaggedForReview ? "Review can be opened" : "No review signals detected"}
                      </span>
                      {activeReview ? (
                        <StatusBadge tone={activeReview.status === "OPEN" ? "warning" : "success"}>
                          {workflowStatusLabel(activeReview.status)}
                        </StatusBadge>
                      ) : null}
                    </div>
                    <p className="mt-2 text-sm leading-6 text-panel-copy">
                      {activeReview
                        ? `Reason: ${activeReview.reason_codes.map(reasonCodeLabel).join(", ") || "Manual readiness review."}`
                        : isFlaggedForReview
                          ? "Open a readiness review to create an auditable container before requesting updates or escalation."
                          : "No operational workflow is available for this facility yet."}
                    </p>
                  </div>

                  {activeUpdateRequest ? (
                    <div className="mt-3 rounded-[1.1rem] border border-panel-table-wrap px-4 py-3 text-sm text-panel-copy">
                      <strong className="text-panel-strong">Facility update pending</strong>
                      <span className="ml-2 text-panel-muted">
                        {workflowStatusLabel(activeUpdateRequest.status)} via {activeUpdateRequest.channel}
                        {activeUpdateRequest.requested_at ? `, requested ${formatRelativeTimestamp(activeUpdateRequest.requested_at)}` : ""}.
                      </span>
                    </div>
                  ) : null}

                  {activeEscalation ? (
                    <div className="mt-3 rounded-[1.1rem] border border-panel-table-wrap px-4 py-3 text-sm text-panel-copy">
                      <strong className="text-panel-strong">County review requested</strong>
                      <span className="ml-2 text-panel-muted">
                        {workflowStatusLabel(activeEscalation.status)}
                        {activeEscalation.assigned_to_username ? `, assigned to ${activeEscalation.assigned_to_username}` : ""}.
                      </span>
                    </div>
                  ) : null}

                  {mutationError ? (
                    <div className="mt-3 rounded-[1rem] border border-[color-mix(in_srgb,var(--danger)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_10%,var(--dashboard-panel-surface))] px-4 py-3 text-sm text-[color:var(--danger)]">
                      {mutationError}
                    </div>
                  ) : null}

                  <div className="mt-4 grid gap-3">
                    {capabilities.can_open_readiness_review ? (
                      <Button
                        onClick={() =>
                          createReviewMutation.mutate({
                            notes: "Opened from facility readiness detail.",
                          })
                        }
                        disabled={createReviewMutation.isPending}
                      >
                        {createReviewMutation.isPending ? "Opening review..." : "Open readiness review"}
                      </Button>
                    ) : null}

                    {capabilities.can_acknowledge_review && activeReview ? (
                      <Button
                        variant="secondary"
                        onClick={() =>
                          acknowledgeReviewMutation.mutate({
                            reviewPublicId: activeReview.public_id,
                            payload: { notes: "Marked as reviewed from facility readiness detail." },
                          })
                        }
                        disabled={acknowledgeReviewMutation.isPending}
                      >
                        {acknowledgeReviewMutation.isPending ? "Marking reviewed..." : "Mark as reviewed"}
                      </Button>
                    ) : null}

                    {capabilities.can_request_facility_update && activeReview ? (
                      <Button
                        onClick={() => {
                          setUpdateRequestMessage(defaultUpdateRequestMessage);
                          setIsUpdateRequestModalOpen(true);
                        }}
                      >
                        Request facility update
                      </Button>
                    ) : null}

                    {capabilities.can_escalate_county_review && capabilities.has_county_review_queue && activeReview ? (
                      <Button
                        variant="secondary"
                        onClick={() =>
                          createEscalationMutation.mutate({
                            reviewPublicId: activeReview.public_id,
                            payload: {
                              reason: "Escalated from facility readiness detail for county review.",
                              severity: activeReview.severity,
                            },
                          })
                        }
                        disabled={createEscalationMutation.isPending}
                      >
                        {createEscalationMutation.isPending ? "Escalating..." : "Escalate for county review"}
                      </Button>
                    ) : null}

                    {capabilities.can_open_linked_alert && primaryLinkedAlert ? (
                      <Link
                        href={primaryLinkedAlert.dashboard_url}
                        className="inline-flex h-10 items-center justify-center rounded-pill border border-panel-table-wrap px-4 text-sm font-semibold text-panel-copy transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_72%,transparent)] hover:text-panel-strong"
                      >
                        Open linked alert
                      </Link>
                    ) : null}

                    {capabilities.can_open_chv_operations && chvOperations ? (
                      <Link
                        href={chvOperations.dashboard_url}
                        className="inline-flex h-10 items-center justify-center rounded-pill border border-panel-table-wrap px-4 text-sm font-semibold text-panel-copy transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_72%,transparent)] hover:text-panel-strong"
                      >
                        Open CHV Operations
                      </Link>
                    ) : null}

                    {!hasAnyWorkflowAction ? (
                      <div className="rounded-[1.1rem] border border-dashed border-panel-table-wrap px-4 py-3 text-sm text-panel-copy">
                        No operational workflow is available for this facility yet.
                      </div>
                    ) : null}
                  </div>
                </Card>

                <Card className="rounded-[2rem] px-4 py-4">
                  <div className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                    Contact availability
                  </div>
                  <div className="mt-4 rounded-[1.25rem] border border-dashed border-panel-table-wrap px-4 py-4 text-sm text-panel-copy">
                    {contact ? (
                      <>
                        <strong className="text-panel-strong">{contact.display_label}</strong>
                        <span className="ml-2 text-panel-muted">
                          Verified {contact.preferred_channel}
                          {contact.phone_last4 ? ` contact ending ${contact.phone_last4}` : " contact"}.
                        </span>
                      </>
                    ) : (
                      "No named facility contacts are available from current records."
                    )}
                  </div>
                </Card>
              </div>
            </section>

            {isUpdateRequestModalOpen && activeReview ? (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
                <div
                  className="absolute inset-0"
                  role="button"
                  tabIndex={0}
                  aria-label="Close update request modal"
                  onClick={() => setIsUpdateRequestModalOpen(false)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape" || event.key === "Enter") {
                      setIsUpdateRequestModalOpen(false);
                    }
                  }}
                />
                <Card className="relative z-10 w-full max-w-2xl rounded-[1.75rem] px-5 py-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                        Facility update request
                      </div>
                      <h2 className="mt-2 text-2xl font-semibold text-panel-strong">
                        Request facility update
                      </h2>
                      <p className="mt-1 text-sm text-panel-muted">
                        {contact
                          ? `Request will use verified ${contact.preferred_channel} contact: ${contact.display_label}.`
                          : "Verified contact is required before sending a request."}
                      </p>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => setIsUpdateRequestModalOpen(false)}>
                      Close
                    </Button>
                  </div>

                  <label className="mt-5 block text-sm font-semibold text-panel-strong" htmlFor="facility-update-message">
                    Message body
                  </label>
                  <textarea
                    id="facility-update-message"
                    value={updateRequestMessage}
                    onChange={(event) => setUpdateRequestMessage(event.target.value)}
                    className="mt-2 min-h-36 w-full rounded-[1.25rem] border border-panel-table-wrap bg-panel px-4 py-3 text-sm text-panel-strong outline-none transition focus:border-brand"
                  />

                  <div className="mt-5 flex flex-wrap justify-end gap-3">
                    <Button variant="ghost" onClick={() => setIsUpdateRequestModalOpen(false)}>
                      Cancel
                    </Button>
                    <Button
                      onClick={() =>
                        createUpdateRequestMutation.mutate(
                          {
                            reviewPublicId: activeReview.public_id,
                            payload: {
                              channel: contact?.preferred_channel ?? "SMS",
                              message_body: updateRequestMessage,
                            },
                          },
                          {
                            onSuccess: () => setIsUpdateRequestModalOpen(false),
                          },
                        )
                      }
                      disabled={createUpdateRequestMutation.isPending}
                    >
                      {createUpdateRequestMutation.isPending ? "Requesting..." : "Request update"}
                    </Button>
                  </div>
                </Card>
              </div>
            ) : null}

          </>
        )}
      </RoleGate>
    </div>
  );
}
