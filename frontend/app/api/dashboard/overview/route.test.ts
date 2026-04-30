import { describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/dashboard/overview/route";

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

describe("dashboard overview route", () => {
  it("normalizes workflow state while preserving delivery detail in trigger linkage", async () => {
    mockFetchBackendJson
      .mockResolvedValueOnce({
        count: 4,
        next: null,
        previous: null,
        results: [
          {
            id: 11,
            public_id: "WRD-011",
            name: "Ward A",
            county: "Migori",
            sub_county: "Rongo",
            ward_code: "MIG-11",
            current_risk_level: "HIGH",
            current_risk_score: 0.8,
            is_active: true,
            updated_at: "2026-04-27T08:00:00Z",
          },
          {
            id: 12,
            public_id: "WRD-012",
            name: "Ward B",
            county: "Migori",
            sub_county: "Rongo",
            ward_code: "MIG-12",
            current_risk_level: "MEDIUM",
            current_risk_score: 0.6,
            is_active: true,
            updated_at: "2026-04-27T08:00:00Z",
          },
          {
            id: 13,
            public_id: "WRD-013",
            name: "Ward C",
            county: "Migori",
            sub_county: "Rongo",
            ward_code: "MIG-13",
            current_risk_level: "HIGH",
            current_risk_score: 0.9,
            is_active: true,
            updated_at: "2026-04-27T08:00:00Z",
          },
          {
            id: 14,
            public_id: "WRD-014",
            name: "Ward D",
            county: "Migori",
            sub_county: "Rongo",
            ward_code: "MIG-14",
            current_risk_level: "LOW",
            current_risk_score: 0.2,
            is_active: true,
            updated_at: "2026-04-27T08:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce([
        {
          ward_id: 11,
          ward_name: "Ward A",
          risk_level: "HIGH",
          risk_score: 0.8,
          predicted_cases: 5,
          generated_at: "2026-04-27T08:10:00Z",
        },
        {
          ward_id: 12,
          ward_name: "Ward B",
          risk_level: "MEDIUM",
          risk_score: 0.6,
          predicted_cases: 3,
          generated_at: "2026-04-27T08:11:00Z",
        },
        {
          ward_id: 13,
          ward_name: "Ward C",
          risk_level: "HIGH",
          risk_score: 0.9,
          predicted_cases: 6,
          generated_at: "2026-04-27T08:12:00Z",
        },
        {
          ward_id: 14,
          ward_name: "Ward D",
          risk_level: "LOW",
          risk_score: 0.2,
          predicted_cases: 1,
          generated_at: "2026-04-27T08:13:00Z",
        },
      ])
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({
        type: "FeatureCollection",
        metadata: {
          county: "Migori",
          geometry_source: "test",
          geometry_feature_count: 0,
          expected_ward_count: 4,
          missing_source_wards: [],
          backend_ward_match_count: 0,
          returned_feature_count: 0,
          backend_wards_without_geometry: [],
          placeholder_geometry_detected: false,
          geometry_note: null,
        },
        features: [],
      })
      .mockResolvedValueOnce({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 1,
            model_type: "risk",
            version: "v1",
            status: "COMPLETED",
            metrics: {},
            metadata: {},
            training_window_start: null,
            training_window_end: null,
            scoring_window_start: null,
            scoring_window_end: null,
            feature_dataset_ref: "dataset",
            started_at: "2026-04-27T08:00:00Z",
            completed_at: "2026-04-27T08:30:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 1,
            run_type: "INGEST",
            status: "COMPLETED",
            source_mode: "AUTO",
            source_kind: "feed",
            source_name: "source",
            source_priority: 1,
            requested_wards: [],
            source_timestamp: "2026-04-27T08:00:00Z",
            freshness_state: "fresh",
            fallback_used: false,
            records_seen: 10,
            records_loaded: 10,
            records_rejected: 0,
            operator_note: "",
            results: {},
            error_message: "",
            started_at: "2026-04-27T08:00:00Z",
            completed_at: "2026-04-27T08:05:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({
        count: 4,
        results: [
          {
            id: 201,
            public_id: "WF-201",
            ward_id: 11,
            ward_name: "Ward A",
            status: "REVIEW_PENDING",
            decision_mode: "rule" as const,
            confidence: "review" as const,
            trigger_severity: "review" as const,
            alert_delivery_state: "awaiting_review" as const,
            alert_delivery_label: "Awaiting review",
            risk_level: "HIGH",
            risk_score: 80,
            predicted_cases: 5,
            reason_flagged: "review",
            trigger_reason: "Review needed",
            recommended_action: "Review trigger",
            recommended_response: "Review",
            expected_operational_effect: "Review",
            rules_basis: { source: "bff_rules_v1", rule_id: "review", rule_label: "Review", inputs: ["review"] },
            trigger_reason_items: [],
            eligible_actions: [],
            active_alert_count: 0,
            delivered_alert_count: 0,
            retry_pending_alert_count: 0,
            failed_alert_count: 0,
            queued_alert_count: 0,
            triggered_at: "2026-04-27T08:20:00Z",
            latest_risk_update_at: "2026-04-27T08:20:00Z",
            last_manual_request_at: null,
            updated_at: "2026-04-27T08:20:00Z",
          },
          {
            id: 202,
            public_id: "WF-202",
            ward_id: 12,
            ward_name: "Ward B",
            status: "FAILED",
            decision_mode: "rule" as const,
            confidence: "high" as const,
            trigger_severity: "high" as const,
            alert_delivery_state: "triggered_failed" as const,
            alert_delivery_label: "Triggered but failed",
            risk_level: "MEDIUM",
            risk_score: 60,
            predicted_cases: 3,
            reason_flagged: "failed",
            trigger_reason: "Delivery failed",
            recommended_action: "Review delivery failure",
            recommended_response: "Retry",
            expected_operational_effect: "Retry",
            rules_basis: { source: "bff_rules_v1", rule_id: "failed", rule_label: "Failed", inputs: ["failed"] },
            trigger_reason_items: [],
            eligible_actions: [],
            active_alert_count: 1,
            delivered_alert_count: 0,
            retry_pending_alert_count: 0,
            failed_alert_count: 1,
            queued_alert_count: 0,
            triggered_at: "2026-04-27T08:21:00Z",
            latest_risk_update_at: "2026-04-27T08:21:00Z",
            last_manual_request_at: null,
            updated_at: "2026-04-27T08:21:00Z",
          },
          {
            id: 203,
            public_id: "WF-203",
            ward_id: 13,
            ward_name: "Ward C",
            status: "DELIVERED",
            decision_mode: "rule" as const,
            confidence: "high" as const,
            trigger_severity: "high" as const,
            alert_delivery_state: "triggered_delivered" as const,
            alert_delivery_label: "Triggered and delivered",
            risk_level: "HIGH",
            risk_score: 90,
            predicted_cases: 6,
            reason_flagged: "delivered",
            trigger_reason: "Delivered alert",
            recommended_action: "Monitor trigger",
            recommended_response: "Monitor",
            expected_operational_effect: "Active",
            rules_basis: { source: "bff_rules_v1", rule_id: "delivered", rule_label: "Delivered", inputs: ["delivered"] },
            trigger_reason_items: [],
            eligible_actions: [],
            active_alert_count: 1,
            delivered_alert_count: 1,
            retry_pending_alert_count: 0,
            failed_alert_count: 0,
            queued_alert_count: 0,
            triggered_at: "2026-04-27T08:22:00Z",
            latest_risk_update_at: "2026-04-27T08:22:00Z",
            last_manual_request_at: null,
            updated_at: "2026-04-27T08:22:00Z",
          },
          {
            id: 204,
            public_id: "WF-204",
            ward_id: 14,
            ward_name: "Ward D",
            status: "RESOLVED",
            decision_mode: "rule" as const,
            confidence: "review" as const,
            trigger_severity: "review" as const,
            alert_delivery_state: "triggered_delivered" as const,
            alert_delivery_label: "Triggered and delivered",
            risk_level: "LOW",
            risk_score: 20,
            predicted_cases: 1,
            reason_flagged: "resolved",
            trigger_reason: "Resolved workflow",
            recommended_action: "No action",
            recommended_response: "No action",
            expected_operational_effect: "Resolved",
            rules_basis: { source: "bff_rules_v1", rule_id: "resolved", rule_label: "Resolved", inputs: ["resolved"] },
            trigger_reason_items: [],
            eligible_actions: [],
            active_alert_count: 0,
            delivered_alert_count: 1,
            retry_pending_alert_count: 0,
            failed_alert_count: 0,
            queued_alert_count: 0,
            triggered_at: "2026-04-27T08:23:00Z",
            latest_risk_update_at: "2026-04-27T08:23:00Z",
            last_manual_request_at: null,
            updated_at: "2026-04-27T08:23:00Z",
          },
        ],
      });

    const response = await GET(new Request("http://localhost:3000/api/dashboard/overview"));
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.triggerLinkage.triggered_wards).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          ward_id: 11,
          workflow_state: "REVIEW_PENDING",
          workflow_state_label: "Awaiting review",
          alert_delivery_label: "Awaiting review",
        }),
        expect.objectContaining({
          ward_id: 12,
          workflow_state: "ACTION_IN_PROGRESS",
          workflow_state_label: "Action in progress",
          alert_delivery_label: "Triggered but failed",
        }),
        expect.objectContaining({
          ward_id: 13,
          workflow_state: "TRIGGER_ACTIVE",
          workflow_state_label: "Trigger active",
          alert_delivery_label: "Triggered and delivered",
        }),
      ]),
    );
    expect(payload.triggerLinkage.triggered_wards.find((ward: { ward_id: number }) => ward.ward_id === 14)).toBeUndefined();
  });
});
