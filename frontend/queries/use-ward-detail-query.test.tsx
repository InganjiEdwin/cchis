import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWardDetailQuery } from "@/queries/use-ward-detail-query";

const mockFetchWardDetailViaBff = vi.fn();
const mockFetchWardMapViaBff = vi.fn();
const mockFetchPreparednessActionsViaBff = vi.fn();

vi.mock("@/lib/dashboard", async () => {
  const actual = await vi.importActual<typeof import("@/lib/dashboard")>("@/lib/dashboard");
  return {
    ...actual,
    fetchWardDetailViaBff: (...args: unknown[]) => mockFetchWardDetailViaBff(...args),
    fetchWardMapViaBff: (...args: unknown[]) => mockFetchWardMapViaBff(...args),
    fetchPreparednessActionsViaBff: (...args: unknown[]) => mockFetchPreparednessActionsViaBff(...args),
  };
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe("useWardDetailQuery", () => {
  beforeEach(() => {
    mockFetchPreparednessActionsViaBff.mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("prefers backend-owned header and decision fields in the ward detail view model", async () => {
    mockFetchWardDetailViaBff.mockResolvedValueOnce({
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
        alert_count: 1,
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
      operational_evidence: {
        schema_version: "ward-operational-evidence-v1",
        ward_id: 12,
        forecast_horizon: {
          label: "7 to 14 day forecast horizon",
          min_days: 7,
          max_days: 14,
          display_value: "7 to 14 days",
          expected_cases_label: "Expected cases in the next 7 days",
          lead_time_supported_days: [7, 14],
          validation_status: "ready_for_lead_time_review",
          mode: "lead_time_validation",
        },
        model_readiness: {
          state: "promoted",
          label: "Promoted",
          tone: "success",
          detail: "Promoted run",
          evidence: ["promotion_target=live_baseline"],
        },
        source_badges: [],
        alert_candidate_review: {
          review_state: "needs_human_review",
          alert_decision: "alert_candidate",
          policy_version: "ward-risk-policy-test",
          risk_level: "HIGH",
          risk_score: 0.91,
          predicted_cases: 9,
          automatic_alert_allowed: true,
          automatic_alert_blockers: [],
          reason_codes: [],
          recommended_action: "Review ward",
          active_alert_count: 0,
        },
        outcome_evaluation: {
          mode: "prediction_vs_surveillance_labels",
          evaluated_count: 0,
          hit_count: 0,
          false_alert_count: 0,
          missed_outbreak_count: 0,
          pending_label_count: 0,
          correct_quiet_count: 0,
          rows: [],
        },
        prediction_label_history: [],
        outcome_feedback: {
          mode: "alert_to_action_outcome_feedback",
          reference_at: null,
          model_quality_state: "pending_label",
          response_quality_state: "response_not_required",
          attribution: "pending_outcome",
          accountability_note: "Prediction outcome and response execution are shown separately.",
          observed_outcome: {
            state: "pending",
            label: "Pending outcome label",
            detail: "The 7 to 14 day label window has not been observed yet.",
            observed_label: "PENDING",
            observed_truth_level: "",
            suspected_case_count: 0,
            confirmed_case_count: 0,
          },
          summary: {
            step_count: 0,
            recorded_step_count: 0,
            downstream_failure_count: 0,
            in_progress_step_count: 0,
            review_item_count: 0,
          },
          steps: [],
          review_items: [],
          facility_action_evidence: {
            reviews: [],
            update_requests: [],
            escalations: [],
          },
        },
        false_missed_review: {
          mode: "ward_prediction_outcome_review",
          open_review_count: 0,
          workflow_label: "No review items",
          items: [],
        },
        chv_action_status: {
          mode: "chv_coverage_requests_linked_to_alerts",
          summary: {
            visible_request_count: 0,
            active_request_count: 0,
            linked_alert_count: 0,
            latest_status: "NO_REQUEST",
          },
          requests: [],
        },
      },
      risk_history: [],
      related_alerts: [],
    });
    mockFetchWardMapViaBff.mockResolvedValueOnce({
      type: "FeatureCollection",
      features: [],
    });

    const { result } = renderHook(() => useWardDetailQuery({ wardId: 12 }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toMatchObject({
      wardId: 12,
      wardName: "North Kamagambo",
      triggerState: "REVIEW_PENDING",
      actionRequired: true,
      primaryCtaKind: "REVIEW_TRIGGER",
      riskScore: 0.91,
      predictedCases: 9,
      updatedAt: "2026-04-27T08:30:00Z",
      lastAlertAt: "2026-04-27T08:34:00Z",
    });
    expect(result.current.data?.operationalEvidence?.forecast_horizon.display_value).toBe("7 to 14 days");
    expect(result.current.data?.operationalEvidence?.model_readiness.state).toBe("promoted");
    expect(result.current.data?.operationalEvidence?.outcome_feedback?.mode).toBe("alert_to_action_outcome_feedback");
  });

  it("falls back safely when header_context and decision_summary are missing", async () => {
    mockFetchWardDetailViaBff.mockResolvedValueOnce({
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
        risk_level: null,
        risk_score: null,
        predicted_cases: 0,
        generated_at: null,
        source: null,
        model_version: null,
        model_run_status: null,
      },
      trend: {
        label: "No previous run available",
        direction: "flat",
        delta_points: null,
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
        generated_at: null,
        is_stale: false,
        stale_threshold_minutes: 120,
        history_count: 0,
        alert_count: 0,
        mode: "timestamp_and_record_availability",
      },
      workflow: null,
      risk_history: [],
      related_alerts: [],
    });
    mockFetchWardMapViaBff.mockResolvedValueOnce({
      type: "FeatureCollection",
      features: [],
    });

    const { result } = renderHook(() => useWardDetailQuery({ wardId: 12 }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toMatchObject({
      triggerState: "NONE",
      actionRequired: false,
      primaryCtaKind: "VIEW_ALERT_HISTORY",
      riskScore: 0.82,
      predictedCases: 0,
      updatedAt: "2026-04-27T08:30:00Z",
      lastAlertAt: null,
    });
    expect(result.current.data?.decisionSummary.headline).toBe("Ward decision summary unavailable.");
  });
});
