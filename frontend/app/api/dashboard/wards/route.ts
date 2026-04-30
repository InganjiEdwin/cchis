import { NextResponse } from "next/server";

import type {
  AlertRecord,
  AlertWorkflowRecord,
  LatestWardRisk,
  PaginatedResponse,
  WardQueueItem,
  WardQueueSummary,
  WardSummary,
} from "@/lib/dashboard";
import {
  normalizeAlertWorkflowStatusToPageState,
  pageWorkflowStateCountsAsWorkflowActive,
  pageWorkflowStateRequiresAction,
} from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

function workflowPriority(workflow: AlertWorkflowRecord) {
  const statusRank: Record<AlertWorkflowRecord["status"], number> = {
    FAILED: 5,
    RETRY_PENDING: 4,
    QUEUED: 3,
    DELIVERED: 2,
    REVIEW_PENDING: 1,
    RESOLVED: 0,
  };
  const severityRank: Record<AlertWorkflowRecord["trigger_severity"], number> = {
    high: 3,
    medium: 2,
    review: 1,
  };

  return [
    statusRank[workflow.status] ?? 0,
    severityRank[workflow.trigger_severity] ?? 0,
    workflow.risk_score ?? 0,
    workflow.predicted_cases ?? 0,
    workflow.updated_at ?? "",
  ] as const;
}

function compareWorkflowPriority(a: AlertWorkflowRecord, b: AlertWorkflowRecord) {
  const aPriority = workflowPriority(a);
  const bPriority = workflowPriority(b);

  for (let index = 0; index < aPriority.length; index += 1) {
    if (aPriority[index] > bPriority[index]) return -1;
    if (aPriority[index] < bPriority[index]) return 1;
  }

  return 0;
}

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { searchParams } = new URL(request.url);

  const county = searchParams.get("county")?.trim() || "Migori";
  const q = searchParams.get("q")?.trim() || "";
  const risk = searchParams.get("risk")?.trim() || "";
  const subCounty = searchParams.get("sub_county")?.trim() || "";
  const ordering = searchParams.get("ordering")?.trim() || "name";

  const wardParams = new URLSearchParams({
    page_size: "200",
    ordering,
    county,
  });

  if (q) {
    wardParams.set("q", q);
  }
  if (risk) {
    wardParams.set("risk", risk);
  }
  if (subCounty) {
    wardParams.set("sub_county", subCounty);
  }

  const latestRiskParams = new URLSearchParams({ county });
  if (q) {
    latestRiskParams.set("q", q);
  }
  if (risk) {
    latestRiskParams.set("risk", risk);
  }
  if (subCounty) {
    latestRiskParams.set("sub_county", subCounty);
  }

  try {
    const [wards, latestRisks, alerts, workflows] = await Promise.all([
      fetchBackendJson<PaginatedResponse<WardSummary>>(`/wards/?${wardParams.toString()}`, {
        cookieHeader,
      }),
      fetchBackendJson<LatestWardRisk[]>(`/risk-score/latest/?${latestRiskParams.toString()}`, {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>(`/alerts/?page_size=200&ordering=-created_at`, {
        cookieHeader,
      }),
      fetchBackendJson<{ count: number; results: AlertWorkflowRecord[] }>(`/alerts/workflows/`, {
        cookieHeader,
      }),
    ]);

    const recentAlertCountsByWard = alerts.results.reduce<Record<string, number>>((accumulator, alert) => {
      const key = String(alert.ward);
      accumulator[key] = (accumulator[key] ?? 0) + 1;
      return accumulator;
    }, {});

    const visibleWardIds = new Set(wards.results.map((ward) => ward.id));
    const latestRiskByWardId = new Map(latestRisks.map((riskItem) => [riskItem.ward_id, riskItem]));
    const workflowByWardId = new Map<number, AlertWorkflowRecord>();

    for (const workflow of workflows.results.filter((item) => visibleWardIds.has(item.ward_id))) {
      const existing = workflowByWardId.get(workflow.ward_id);
      if (!existing || compareWorkflowPriority(workflow, existing) < 0) {
        workflowByWardId.set(workflow.ward_id, workflow);
      }
    }

    const wardQueueItems: WardQueueItem[] = wards.results.map((ward) => {
      const latestRisk = latestRiskByWardId.get(ward.id);
      const workflow = workflowByWardId.get(ward.id);
      const triggerState = normalizeAlertWorkflowStatusToPageState(workflow?.status);
      const deliveryConcernCount = workflow ? (workflow.retry_pending_alert_count ?? 0) + (workflow.failed_alert_count ?? 0) : 0;

      return {
        id: ward.id,
        public_id: ward.public_id,
        name: ward.name,
        county: ward.county,
        sub_county: ward.sub_county,
        risk_level: workflow?.risk_level ?? latestRisk?.risk_level ?? ward.current_risk_level ?? "UNKNOWN",
        risk_score: workflow?.risk_score ?? latestRisk?.risk_score ?? ward.current_risk_score ?? null,
        expected_cases_7d: workflow?.predicted_cases ?? latestRisk?.predicted_cases ?? null,
        last_updated_at: workflow?.latest_risk_update_at ?? latestRisk?.generated_at ?? ward.updated_at ?? null,
        trigger_state: triggerState,
        requires_action: pageWorkflowStateRequiresAction(triggerState),
        recent_alert_count: recentAlertCountsByWard[String(ward.id)] ?? 0,
        delivery_concern_count: deliveryConcernCount,
        workflow_public_id: workflow?.public_id ?? null,
        recommended_action: workflow?.recommended_action ?? null,
      };
    });

    const wardQueueSummary: WardQueueSummary = wardQueueItems.reduce(
      (summary, item) => {
        if (item.requires_action) {
          summary.wards_requiring_action += 1;
        }
        if (pageWorkflowStateCountsAsWorkflowActive(item.trigger_state)) {
          summary.workflow_active_wards += 1;
        }
        summary.alerts_pending += item.delivery_concern_count;
        return summary;
      },
      {
        wards_requiring_action: 0,
        workflow_active_wards: 0,
        alerts_pending: 0,
      },
    );

    return NextResponse.json({
      wards,
      latestRisks,
      recentAlertCountsByWard,
      wardQueue: {
        items: wardQueueItems,
        summary: wardQueueSummary,
        urgency: {
          has_actionable_wards: wardQueueSummary.wards_requiring_action > 0,
          requires_action_count: wardQueueSummary.wards_requiring_action,
        },
      },
    });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load ward risk data." }, { status: 500 });
  }
}
