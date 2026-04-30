import { describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/dashboard/wards/[id]/route";

const mockFetchBackendJson = vi.fn();

vi.mock("@/lib/server-api", () => ({
  ServerApiError: class ServerApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  fetchBackendJson: (...args: unknown[]) => mockFetchBackendJson(...args),
}));

describe("dashboard ward detail route", () => {
  it("passes through backend-owned decision console contract fields", async () => {
    mockFetchBackendJson.mockResolvedValueOnce({
      ward: {
        id: 12,
        public_id: "WRD-012",
        name: "North Kamagambo",
        county: "Migori",
        sub_county: "Rongo",
        ward_code: "MIG-12",
        current_risk_level: "HIGH",
        current_risk_score: 0.82,
        predicted_cases: 6,
        latest_generated_at: "2026-04-27T08:30:00Z",
        latest_source: "MODEL",
        latest_model_version: "v2",
        is_active: true,
        updated_at: "2026-04-27T08:45:00Z",
      },
      current_risk: {
        risk_level: "HIGH",
        risk_score: 0.82,
        predicted_cases: 6,
        generated_at: "2026-04-27T08:30:00Z",
        source: "MODEL",
        model_version: "v2",
        model_run_status: "COMPLETED",
      },
      trend: {
        label: "+12 points vs previous run",
        direction: "up",
        delta_points: 12,
        mode: "derived_from_recent_history",
      },
      driver_summary: {
        mode: "derived_from_latest_record",
        items: [],
      },
      guidance_summary: {
        mode: "static_risk_playbook",
        items: [],
      },
      freshness: {
        generated_at: "2026-04-27T08:30:00Z",
        is_stale: true,
        stale_threshold_minutes: 120,
        history_count: 2,
        alert_count: 2,
        mode: "timestamp_and_record_availability",
      },
      workflow: {
        public_id: "WF-100",
        status: "REVIEW_PENDING",
        status_label: "Awaiting review",
        recommended_action: "Review active alerts and confirm whether trigger action is still needed.",
        expected_operational_effect: "Clarifies whether escalation or delivery follow-up is required.",
        eligible_actions: ["REVIEW_TRIGGER", "VIEW_ALERT_HISTORY"],
        active_alert_count: 2,
        retry_pending_alert_count: 1,
        failed_alert_count: 0,
        queued_alert_count: 0,
        latest_risk_update_at: "2026-04-27T08:30:00Z",
        updated_at: "2026-04-27T08:42:00Z",
      },
      decision_summary: {
        action_required: true,
        headline: "Action required. Review active alerts and trigger status.",
        why: "Risk spike detected",
        next_steps: ["Review trigger", "Review full alert history"],
        primary_cta_kind: "REVIEW_TRIGGER",
      },
      header_context: {
        last_alert_at: "2026-04-27T08:34:00Z",
        latest_record_at: "2026-04-27T08:30:00Z",
        freshness_state: "STALE",
        trigger_state: "REVIEW_PENDING",
        expected_cases_7d: 9,
        risk_score: 0.91,
      },
      risk_history: [],
      related_alerts: [],
    });

    const request = new Request("http://localhost:3000/api/dashboard/wards/12");
    const response = await GET(request, { params: Promise.resolve({ id: "12" }) });
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.workflow).toMatchObject({
      public_id: "WF-100",
      status: "REVIEW_PENDING",
      status_label: "Awaiting review",
      recommended_action: "Review active alerts and confirm whether trigger action is still needed.",
      expected_operational_effect: "Clarifies whether escalation or delivery follow-up is required.",
      eligible_actions: ["REVIEW_TRIGGER", "VIEW_ALERT_HISTORY"],
      active_alert_count: 2,
      retry_pending_alert_count: 1,
      failed_alert_count: 0,
      queued_alert_count: 0,
      latest_risk_update_at: "2026-04-27T08:30:00Z",
      updated_at: "2026-04-27T08:42:00Z",
    });
    expect(payload.decision_summary).toEqual({
      action_required: true,
      headline: "Action required. Review active alerts and trigger status.",
      why: "Risk spike detected",
      next_steps: ["Review trigger", "Review full alert history"],
      primary_cta_kind: "REVIEW_TRIGGER",
    });
    expect(payload.header_context).toEqual({
      last_alert_at: "2026-04-27T08:34:00Z",
      latest_record_at: "2026-04-27T08:30:00Z",
      freshness_state: "STALE",
      trigger_state: "REVIEW_PENDING",
      expected_cases_7d: 9,
      risk_score: 0.91,
    });
    expect(mockFetchBackendJson).toHaveBeenCalledTimes(1);
  });

  it("surfaces backend API errors as route errors", async () => {
    mockFetchBackendJson.mockRejectedValueOnce(new Error("boom"));

    const request = new Request("http://localhost:3000/api/dashboard/wards/12");
    const response = await GET(request, { params: Promise.resolve({ id: "12" }) });
    const payload = await response.json();

    expect(response.status).toBe(500);
    expect(payload).toEqual({ detail: "Unable to load ward detail." });
  });
});
