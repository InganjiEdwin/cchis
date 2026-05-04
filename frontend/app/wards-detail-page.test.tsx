import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WardDetailPage from "@/app/(dashboard)/wards/[id]/page";

const mockUseAuth = vi.fn();
const mockUseWardDetailQuery = vi.fn();
const mockUseParams = vi.fn();
const mockUseSearchParams = vi.fn();

function buildWardDetailState(overrides: Record<string, unknown> = {}) {
  return {
    wardId: 12,
    name: "North Kamagambo",
    wardName: "North Kamagambo",
    wardCode: "MIG-12",
    county: "Migori",
    subCounty: "Rongo",
    riskLevel: "HIGH",
    triggerState: "REVIEW_PENDING",
    actionRequired: true,
    primaryCtaKind: "REVIEW_TRIGGER",
    riskScore: 86,
    predicted_cases: 12,
    predictedCases: 12,
    updatedAt: "2026-04-22T18:00:00Z",
    lastAlertAt: "2026-04-22T18:05:00Z",
    source: "MODEL",
    modelVersion: "v1",
    modelRunStatus: "COMPLETED",
    freshness: {
      generated_at: "2026-04-22T18:00:00Z",
      is_stale: true,
      stale_threshold_minutes: 120,
      history_count: 2,
      alert_count: 1,
      mode: "timestamp_and_record_availability",
    },
    driverSummaryMode: "derived_from_latest_record",
    guidanceSummaryMode: "static_risk_playbook",
    driverItems: [
      {
        text: "Forecast rainfall is elevated at 92 mm from open-meteo-forecast in the latest record.",
        tone: "critical",
        source_field: "climate.forecast",
      },
    ],
    guidanceItems: [],
    trend: {
      label: "+6 points vs previous run",
      direction: "up",
      delta_points: 6,
      mode: "derived_from_recent_history",
    },
    workflow: {
      public_id: "WF-100",
      status: "REVIEW_PENDING",
      status_label: "Awaiting review",
      recommended_action: "Review active alerts and confirm whether trigger action is still needed.",
      expected_operational_effect: "Clarifies whether escalation or delivery follow-up is required.",
      eligible_actions: ["REVIEW_TRIGGER", "VIEW_ALERT_HISTORY"],
      active_alert_count: 1,
      retry_pending_alert_count: 0,
      failed_alert_count: 0,
      queued_alert_count: 1,
      latest_risk_update_at: "2026-04-22T18:00:00Z",
      updated_at: "2026-04-22T18:03:00Z",
    },
    decisionSummary: {
      action_required: true,
      headline: "Action required. Review active alerts and trigger status.",
      why: "Risk spike detected",
      next_steps: ["Review trigger", "Review full alert history"],
      primary_cta_kind: "REVIEW_TRIGGER",
    },
    headerContext: {
      last_alert_at: "2026-04-22T18:05:00Z",
      latest_record_at: "2026-04-22T18:00:00Z",
      freshness_state: "STALE",
      trigger_state: "REVIEW_PENDING",
      expected_cases_7d: 12,
      risk_score: 86,
    },
    spatialMapFeatures: [],
    spatialEvidence: {
      schema_version: "ward-spatial-evidence-v1",
      ward_id: 12,
      ward_name: "North Kamagambo",
      as_of: "2026-04-22T18:00:00Z",
      summary: {
        neighbor_count: 2,
        high_risk_neighbor_count: 1,
        active_outbreak_neighbor_count: 1,
        neighbor_suspected_case_trend_14d_delta: 4,
        nearest_high_risk_distance: 0.42,
        nearest_facility_distance: 0.03,
        nearest_facility_distance_unit: "source_crs_degrees",
        catchment_facility_count: 1,
        approximate_catchment_count: 1,
        max_catchment_pressure_score: 82,
        water_proximity_available: true,
        water_proximity_value: 0.34,
      },
      neighbors: [
        {
          ward_id: 14,
          ward_name: "North Kadem",
          county: "Migori",
          ward_code: "MIG-14",
          relationship_types: ["adjacent", "same_facility_catchment"],
          relationship_labels: ["Adjacent", "Same Facility Catchment"],
          relationship_refs: ["ward_spatial_relationship:1", "ward_spatial_relationship:2"],
          generation_methods: ["derived_geometry", "derived_facility_catchment"],
          is_approximate_relationship: true,
          approximation_notice: "Same-facility-catchment relationship is derived from FacilityCatchment approximations.",
          confidence: 0.95,
          distance: 0.42,
          distance_unit: "source_crs_degrees",
          geometry_dataset_ref: "migori-geometry:phase3",
          relationship_generated_at: "2026-04-21T18:00:00Z",
          risk_level: "HIGH",
          risk_score: 0.91,
          predicted_cases: 9,
          risk_generated_at: "2026-04-22T15:00:00Z",
          risk_score_ref: "risk_score:88",
          active_outbreak_label: true,
          suspected_cases_28d: 5,
          suspected_case_trend_14d_delta: 5,
          surveillance_record_count_28d: 1,
          latest_surveillance_reporting_period_end: "2026-04-21",
        },
      ],
      high_risk_neighbor_ward_ids: [14],
      active_outbreak_neighbor_ward_ids: [14],
      facility_catchments: [
        {
          catchment_id: 3,
          facility_id: 44,
          facility_name: "Kamagambo Health Centre",
          facility_code: "KAM-001",
          primary_ward_id: 12,
          primary_ward_name: "North Kamagambo",
          covered_ward_ids: [12, 14],
          covered_ward_names: ["North Kadem", "North Kamagambo"],
          catchment_method: "spatial_graph_adjacent_wards",
          catchment_method_label: "Spatial Graph Adjacent Wards",
          source_kind: "approximated",
          source_kind_label: "Approximated",
          is_approximate: true,
          confidence: 0.7,
          population_estimate: 16000,
          generated_at: "2026-04-21T18:00:00Z",
          projected_pressure_score: 82,
          projected_readiness_state: "capacity_concern",
          projected_readiness_label: "Capacity Concern",
          forecast_generated_at: "2026-04-22T16:00:00Z",
          forecast_ref: "facility_forecast:4",
          source_ref: "facility_catchment:3",
        },
      ],
      nearest_facility: {
        facility_id: 44,
        facility_name: "Kamagambo Health Centre",
        facility_code: "KAM-001",
        ward_id: 12,
        ward_name: "North Kamagambo",
        distance: 0.03,
        distance_unit: "source_crs_degrees",
        source_ref: "health_facility:44",
        source_created_at: "2026-04-20T18:00:00Z",
      },
      water_proximity: {
        source_available: true,
        value: 0.34,
        display_caveat: "Water proximity is ward-level exposure context where source data exists.",
      },
      lineage: {},
      caveats: ["Some facility catchments are approximate and should be used as operational context only."],
    },
    operationalEvidence: {
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
        source_label: "Forecast rainfall",
        claimed_forecast_horizon_days: 14,
        forecast_coverage_days: 3,
        forecast_missing_lead_days: [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
        climate_coverage_status: "insufficient_forecast_horizon",
        claimed_lead_time_climate_coverage_sufficient: false,
        issue_time: "2026-04-22T06:00:00Z",
        valid_date: "2026-04-24",
        lead_day: 3,
        fallback_static_rainfall_used: false,
      },
      climate_source: {
        schema_version: "climate-alert-evidence-v1",
        record_type: "forecast",
        source_provider: "open-meteo-forecast",
        observed_vs_forecast_source_label: "Forecast rainfall",
        issue_time: "2026-04-22T06:00:00Z",
        valid_date: "2026-04-24",
        lead_day: 3,
        forecast_horizon_days: 3,
        claimed_forecast_horizon_days: 14,
        forecast_coverage_days: 3,
        forecast_missing_lead_days: [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
        claimed_lead_time_climate_coverage_sufficient: false,
        fallback_static_rainfall_used: false,
        climate_source_confidence: 0.55,
        climate_source_confidence_label: "moderate",
        climate_coverage_status: "insufficient_forecast_horizon",
        climate_coverage_caveats: ["forecast_missing_claimed_lead_days"],
      },
      model_readiness: {
        state: "promoted",
        label: "Promoted",
        tone: "success",
        detail: "The current ward score is attached to the promoted live-baseline model run.",
        evidence: ["model_version=v1", "promotion_target=live_baseline"],
        readiness_caveats: ["forecast_missing_claimed_lead_days"],
      },
      source_badges: [
        {
          id: "source_freshness",
          label: "Source freshness",
          value: "Fresh",
          tone: "success",
          detail: "Current ward data is inside the freshness window.",
        },
        {
          id: "source_confidence",
          label: "Source confidence",
          value: "High",
          tone: "success",
          detail: "Confidence inferred from LIVE and visible surveillance/exposure context.",
        },
        {
          id: "climate_coverage",
          label: "Climate coverage",
          value: "Insufficient Forecast Horizon",
          tone: "warning",
          detail: "Forecast rainfall; missing lead days: 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14.",
        },
        {
          id: "surveillance_truth",
          label: "Surveillance truth",
          value: "Confirmed Surveillance Truth",
          tone: "success",
          detail: "Confirmed surveillance label window is linked.",
        },
      ],
      alert_candidate_review: {
        review_state: "needs_human_review",
        alert_decision: "alert_candidate",
        policy_version: "ward-risk-policy-test",
        risk_level: "HIGH",
        risk_score: 0.86,
        predicted_cases: 12,
        automatic_alert_allowed: true,
        automatic_alert_blockers: [],
        reason_codes: ["score_threshold_crossed"],
        recommended_action: "Review the ward now and decide whether to create an operational alert request.",
        active_alert_count: 1,
      },
      outcome_evaluation: {
        mode: "prediction_vs_surveillance_labels",
        evaluated_count: 2,
        hit_count: 1,
        false_alert_count: 1,
        missed_outbreak_count: 0,
        pending_label_count: 0,
        correct_quiet_count: 0,
        precision_review_note: "Only rows with surveillance label windows are counted as evaluated.",
        rows: [],
      },
      prediction_label_history: [
        {
          risk_score_id: 1,
          prediction_generated_at: "2026-04-22T18:00:00Z",
          forecast_window_start: "2026-04-29",
          forecast_window_end: "2026-05-06",
          risk_level: "HIGH",
          risk_score: 0.86,
          predicted_cases: 12,
          alert_decision: "alert_candidate",
          policy_version: "ward-risk-policy-test",
          observed_label: "ACTIVE",
          observed_truth_level: "confirmed_surveillance",
          observed_suspected_cases: 6,
          observed_confirmed_cases: 2,
          observed_proxy_cases: 0,
          label_window_ref: "surveillance_label_window:1",
          label_dataset_ref: "phase6-labels",
          classification: "hit",
          review_required: false,
          confidence_caveat: "Confirmed surveillance truth",
        },
        {
          risk_score_id: 2,
          prediction_generated_at: "2026-04-20T18:00:00Z",
          forecast_window_start: "2026-04-27",
          forecast_window_end: "2026-05-04",
          risk_level: "HIGH",
          risk_score: 0.8,
          predicted_cases: 10,
          alert_decision: "alert_candidate",
          policy_version: "ward-risk-policy-test",
          observed_label: "NONE",
          observed_truth_level: "confirmed_surveillance",
          observed_suspected_cases: 0,
          observed_confirmed_cases: 0,
          observed_proxy_cases: 0,
          label_window_ref: "surveillance_label_window:2",
          label_dataset_ref: "phase6-labels",
          classification: "false_alert",
          review_required: true,
          confidence_caveat: "Confirmed surveillance truth",
        },
      ],
      outcome_feedback: {
        mode: "alert_to_action_outcome_feedback",
        reference_at: "2026-04-22T18:05:00Z",
        model_quality_state: "prediction_hit",
        response_quality_state: "response_gap",
        attribution: "response_quality_review",
        accountability_note:
          "Prediction outcome and response execution are shown separately so misses are not attributed to the model when alert delivery or CHV action failed downstream.",
        observed_outcome: {
          state: "escalated",
          label: "Outbreak escalated",
          detail: "Observed label is active with 6 suspected and 2 confirmed cases; response quality is response gap.",
          observed_label: "ACTIVE",
          observed_truth_level: "confirmed_surveillance",
          suspected_case_count: 6,
          confirmed_case_count: 2,
        },
        summary: {
          step_count: 9,
          recorded_step_count: 5,
          downstream_failure_count: 1,
          in_progress_step_count: 1,
          review_item_count: 1,
        },
        steps: [
          {
            key: "alert_issued",
            label: "Alert issued",
            status: "recorded",
            tone: "success",
            detail: "1 alert record exists; 0 delivered and 0 failed.",
            occurred_at: "2026-04-22T18:05:00Z",
            evidence_level: "direct",
            evidence_refs: ["alert-7"],
          },
          {
            key: "chv_notified",
            label: "CHV notified",
            status: "recorded",
            tone: "success",
            detail: "Alert-linked coverage request exists as operational proxy evidence.",
            occurred_at: "2026-04-22T18:08:00Z",
            evidence_level: "coverage_request_proxy",
            evidence_refs: ["coverage-1"],
          },
          {
            key: "chv_acknowledged",
            label: "CHV acknowledged",
            status: "recorded",
            tone: "success",
            detail: "1 active CHV assignment exists; assignment start is proxy acknowledgement evidence.",
            occurred_at: null,
            evidence_level: "assignment_proxy",
            evidence_refs: ["coverage-1"],
          },
          {
            key: "household_follow_up_started",
            label: "Household follow-up started",
            status: "in_progress",
            tone: "warning",
            detail: "Household follow-up has started through active CHV assignment or in-progress coverage request.",
            occurred_at: null,
            evidence_level: "assignment_proxy",
            evidence_refs: ["coverage-1"],
          },
          {
            key: "facility_readiness_action_started",
            label: "Facility readiness action started",
            status: "missing",
            tone: "danger",
            detail: "No facility readiness action is visible after the alert.",
            occurred_at: null,
            evidence_level: "direct",
            evidence_refs: [],
          },
          {
            key: "supplies_or_staffing_escalated",
            label: "Supplies or staffing escalated",
            status: "missing",
            tone: "danger",
            detail: "No supply or staffing escalation is visible after the alert.",
            occurred_at: null,
            evidence_level: "direct",
            evidence_refs: [],
          },
          {
            key: "suspected_cases_observed",
            label: "Suspected cases observed",
            status: "recorded",
            tone: "success",
            detail: "6 suspected cases recorded in the matched label window.",
            occurred_at: null,
            evidence_level: "direct",
            evidence_refs: ["surveillance_label_window:1"],
          },
          {
            key: "confirmed_cases_observed",
            label: "Confirmed cases observed",
            status: "recorded",
            tone: "success",
            detail: "2 confirmed cases recorded in the matched label window.",
            occurred_at: null,
            evidence_level: "direct",
            evidence_refs: ["surveillance_label_window:1"],
          },
          {
            key: "outbreak_trajectory",
            label: "Outbreak avoided, reduced, or escalated",
            status: "recorded",
            tone: "success",
            detail: "Observed label is active with 6 suspected and 2 confirmed cases; response quality is response gap.",
            occurred_at: null,
            evidence_level: "direct",
            evidence_refs: ["surveillance_label_window:1"],
          },
        ],
        review_items: [
          {
            category: "response_quality",
            severity: "high",
            title: "Active outbreak with downstream response gap",
            detail:
              "Do not blame this outcome only on the model; alert delivery, CHV acknowledgement, or household follow-up evidence is missing or failed.",
            step_keys: ["household_follow_up_started"],
          },
        ],
        facility_action_evidence: {
          reviews: [],
          update_requests: [],
          escalations: [],
        },
        preparedness_action_evidence: {
          mode: "preparedness_action_ledger_outcome_linkage",
          outcome_ref: "ward_outcome_feedback:12:surveillance_label_window:2",
          reference_at: "2026-04-22T18:05:00Z",
          window_start: "2026-04-22T17:05:00Z",
          related_alert_public_ids: ["alert-7"],
          prediction_risk_score_ids: [1],
          summary: {
            total_count: 1,
            completed_count: 1,
            completed_without_substantive_evidence_count: 0,
            in_progress_count: 0,
            failed_count: 0,
            blocked_count: 0,
            overdue_count: 0,
            completed_with_evidence_count: 1,
            first_action_at: "2026-04-22T18:10:00Z",
            first_acknowledged_at: "2026-04-22T18:20:00Z",
            first_completed_at: "2026-04-22T20:00:00Z",
          },
          response_time_measurements: {
            hours_to_first_action: 0.08,
            hours_to_first_acknowledgement: 0.25,
            hours_to_first_completion: 1.92,
          },
          completion_quality_flags: ["completed", "completion_evidence_present", "completion_reference_present"],
          action_history: [
            {
              public_id: "preparedness-action-401",
              action_type: "field_verification",
              action_type_label: "Field verification",
              status: "COMPLETED",
              outcome_status: "recorded",
              priority: "HIGH",
              ward_id: 12,
              ward_name: "North Kamagambo",
              facility_id: null,
              facility_name: "",
              chv_id: null,
              chv_name: "",
              assigned_to: 1,
              assigned_to_username: "supervisor",
              assigned_to_team: "",
              source_trigger_type: "alert",
              source_trigger_ref: "alert:alert-7",
              risk_score_id: 1,
              model_run_id: 101,
              model_run_version: "v1",
              alert_public_id: "alert-7",
              linked_alert_public_ids: ["alert-7"],
              related_alert_public_ids: ["alert-7"],
              created_at: "2026-04-22T18:10:00Z",
              acknowledged_at: "2026-04-22T18:20:00Z",
              completed_at: "2026-04-22T20:00:00Z",
              due_at: "2026-04-22T22:00:00Z",
              is_overdue: false,
              completion_evidence_present: true,
              completion_quality_flags: ["completed", "completion_evidence_present"],
              response_step_keys: ["household_follow_up_started"],
              outcome_links: {
                outcome_ref: "ward_outcome_feedback:12:surveillance_label_window:2",
                label_window_ref: "surveillance_label_window:2",
                prediction_risk_score_ids: [1],
                alert_public_ids: ["alert-7"],
              },
            },
          ],
          missed_action_review: {
            review_required: false,
            missing_required_action_keys: [],
            overdue_action_public_ids: [],
            blocked_action_public_ids: [],
            cancelled_action_public_ids: [],
            detail: "Preparedness action linkage is present or no response action was required.",
          },
          false_alert_review_context: {
            review_required: true,
            completed_action_public_ids: ["preparedness-action-401"],
            detail:
              "Quiet observed label followed completed preparedness actions; review response effect before treating this as pure model error.",
          },
        },
      },
      false_missed_review: {
        mode: "ward_prediction_outcome_review",
        open_review_count: 1,
        workflow_label: "Outcome review required",
        items: [
          {
            classification: "false_alert",
            risk_score_id: 2,
            prediction_generated_at: "2026-04-20T18:00:00Z",
            label_window_ref: "surveillance_label_window:2",
            observed_label: "NONE",
            recommended_review_action: "Review alert threshold, source confidence, and CHV follow-through for this false alert.",
          },
        ],
      },
      chv_action_status: {
        mode: "chv_coverage_requests_linked_to_alerts",
        summary: {
          visible_request_count: 1,
          active_request_count: 1,
          linked_alert_count: 1,
          latest_status: "IN_PROGRESS",
        },
        requests: [
          {
            public_id: "coverage-1",
            status: "IN_PROGRESS",
            priority: "HIGH",
            trigger_source: "ALERT_DRIVEN",
            created_at: "2026-04-22T18:08:00Z",
            expected_response_by: "2026-04-22T22:08:00Z",
            resolved_at: null,
            linked_alert_public_ids: ["alert-7"],
            linked_alert_statuses: [
              {
                public_id: "alert-7",
                status: "QUEUED",
                channel: "SMS",
                created_at: "2026-04-22T18:05:00Z",
              },
            ],
            assignment_counts: {
              active: 1,
              completed: 0,
              cancelled: 0,
              total: 1,
            },
          },
        ],
      },
    },
    riskHistory: [
      {
        id: 1,
        ward: 12,
        ward_name: "North Kamagambo",
        model_run: 101,
        model_run_status: "COMPLETED",
        model_run_version: "v1",
        score: 86,
        risk_level: "HIGH",
        rainfall_mm: 92,
        flood_indicator: 1,
        predicted_cases: 12,
        source: "MODEL",
        model_version: "v1",
        notes: "",
        generated_at: "2026-04-22T18:00:00Z",
      },
      {
        id: 2,
        ward: 12,
        ward_name: "North Kamagambo",
        model_run: 100,
        model_run_status: "COMPLETED",
        model_run_version: "v1",
        score: 80,
        risk_level: "HIGH",
        rainfall_mm: 81,
        flood_indicator: 1,
        predicted_cases: 10,
        source: "MODEL",
        model_version: "v1",
        notes: "",
        generated_at: "2026-04-22T16:00:00Z",
      },
    ],
    relatedAlerts: [
      {
        id: 7,
        ward: 12,
        ward_name: "North Kamagambo",
        risk_score: 86,
        channel: "SMS",
        recipient: "Supervisor",
        message: "High risk alert",
        status: "QUEUED",
        delivery_backend: "twilio",
        attempt_count: 0,
        max_attempts: 3,
        last_attempted_at: null,
        next_retry_at: null,
        external_id: "",
        sent_at: null,
        created_at: "2026-04-22T18:05:00Z",
        error_message: "",
      },
    ],
    ...overrides,
  };
}

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    lastUpdatedLabel,
    lastUpdatedTone,
  }: {
    title: string;
    subtitle: string;
    lastUpdatedLabel?: string;
    lastUpdatedTone?: string;
  }) =>
    React.createElement(
      "div",
      null,
      `${title} | ${subtitle} | ${lastUpdatedLabel ?? "no-label"} | ${lastUpdatedTone ?? "no-tone"}`,
    ),
}));

vi.mock("@/components/trigger-alert-panel", () => ({
  TriggerAlertPanel: ({
    buttonLabel,
    fixedWard,
  }: {
    buttonLabel?: string;
    fixedWard?: { id: number; name: string } | null;
  }) =>
    React.createElement(
      "div",
      null,
      `Trigger alert mock | ${buttonLabel ?? "no-label"} | ${fixedWard?.id ?? "no-ward"} | ${fixedWard?.name ?? "no-name"}`,
    ),
}));

vi.mock("next/navigation", () => ({
  useParams: () => mockUseParams(),
  useSearchParams: () => mockUseSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/queries/use-ward-detail-query", () => ({
  useWardDetailQuery: (...args: unknown[]) => mockUseWardDetailQuery(...args),
}));

describe("WardDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseParams.mockReturnValue({ id: "12" });
    mockUseSearchParams.mockReturnValue(new URLSearchParams("returnTo=%2Fwards%3Frisk%3DHIGH%26page%3D2"));
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        full_name: "Admin User",
        phone_number: null,
        role: "ADMIN",
        theme_preference: "LIGHT",
        ward: null,
        ward_name: null,
        is_active: true,
      },
    });

    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState(),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("renders the operational ward detail layout with preserved back link state", async () => {
    render(React.createElement(WardDetailPage));

    await waitFor(() => {
      expect(mockUseWardDetailQuery).toHaveBeenCalledWith({
        wardId: 12,
        enabled: true,
      });
    });

    expect(await screen.findByRole("heading", { name: "North Kamagambo" })).toBeInTheDocument();
    expect(screen.getByText("Trigger alert mock | Review trigger | 12 | North Kamagambo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to wards/i })).toHaveAttribute(
      "href",
      "/wards?risk=HIGH&page=2",
    );
    expect(screen.getByText("Risk history")).toBeInTheDocument();
    expect(screen.getByText("Recent alerts")).toBeInTheDocument();
    expect(screen.getByText("Recommended action")).toBeInTheDocument();
  });

  it("renders phase 6 evidence for horizon, confidence, outcomes, review workflow, and CHV follow-through", async () => {
    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("Forecast horizon and evidence")).toBeInTheDocument();
    expect(screen.getAllByText("7 to 14 days").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Promoted").length).toBeGreaterThan(0);
    expect(screen.getByText("14-day climate horizon caveated")).toBeInTheDocument();
    expect(screen.getByText("Climate source truth")).toBeInTheDocument();
    expect(screen.getAllByText("Forecast rainfall").length).toBeGreaterThan(0);
    expect(screen.getByText("open-meteo-forecast")).toBeInTheDocument();
    expect(screen.getByText("3/14 days")).toBeInTheDocument();
    expect(screen.getByText(/Missing forecast lead days: 4, 5, 6, 7, 8, 9, 10, 11 \+3 more/i)).toBeInTheDocument();
    expect(screen.getByText(/Forecast rainfall is elevated at 92 mm from open-meteo-forecast/i)).toBeInTheDocument();
    expect(screen.getByText("High confidence")).toBeInTheDocument();
    expect(screen.getByText("Prediction outcomes")).toBeInTheDocument();
    expect(screen.getByText("False alerts")).toBeInTheDocument();
    expect(screen.getAllByText("False alert").length).toBeGreaterThan(0);
    expect(screen.getByText("Outcome feedback loop")).toBeInTheDocument();
    expect(screen.getAllByText("Response Quality Review").length).toBeGreaterThan(0);
    expect(screen.getByText("Model quality")).toBeInTheDocument();
    expect(screen.getByText("Response quality")).toBeInTheDocument();
    expect(screen.getByText("Active outbreak with downstream response gap")).toBeInTheDocument();
    expect(screen.getByText("Preparedness action outcome history")).toBeInTheDocument();
    expect(screen.getByText("Field verification")).toBeInTheDocument();
    expect(screen.getByText("False-alert context")).toBeInTheDocument();
    expect(screen.getByText("Spatial context")).toBeInTheDocument();
    expect(screen.getByText("Neighboring high-risk wards")).toBeInTheDocument();
    expect(screen.getByText("North Kadem")).toBeInTheDocument();
    expect(screen.getByText("Approximate")).toBeInTheDocument();
    expect(screen.getByText("Approximate link")).toBeInTheDocument();
    expect(screen.getAllByText("Kamagambo Health Centre").length).toBeGreaterThan(0);
    expect(screen.getByText(/facility catchments are approximate/i)).toBeInTheDocument();
    expect(screen.getByText("Alert candidate review")).toBeInTheDocument();
    expect(screen.getByText("CHV action status")).toBeInTheDocument();
    expect(screen.getByText(/linked alerts: alert-7/i)).toBeInTheDocument();
  });

  it("renders a ward-level preparedness action lifecycle timeline", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        preparednessActions: [
          {
            public_id: "preparedness-action-501",
            action_type: "field_verification",
            status: "IN_PROGRESS",
            assigned_to_username: "supervisor",
            assigned_to_team: "",
            due_at: "2026-04-22T22:00:00Z",
            is_overdue: false,
            events: [
              {
                public_id: "preparedness-action-event-1",
                event_type: "CREATED",
                detail: "Preparedness action created.",
                created_at: "2026-04-22T18:10:00Z",
              },
              {
                public_id: "preparedness-action-event-2",
                event_type: "IN_PROGRESS",
                detail: "Started field verification with CHV team.",
                created_at: "2026-04-22T18:30:00Z",
              },
            ],
          },
        ],
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("Preparedness actions")).toBeInTheDocument();
    expect(screen.getByText("Latest lifecycle events")).toBeInTheDocument();
    expect(screen.getByText("Started field verification with CHV team.")).toBeInTheDocument();
  });

  it("shows a read-only recommendation state for non-trigger roles", async () => {
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 2,
        username: "analyst",
        email: "analyst@example.com",
        full_name: "Analyst User",
        phone_number: null,
        role: "ANALYST",
        theme_preference: "LIGHT",
        ward: null,
        ward_name: null,
        is_active: true,
      },
    });
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        relatedAlerts: [],
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(
      await screen.findByText(/recommended action is visible, but this role cannot start or review trigger work from this page/i),
    ).toBeInTheDocument();
    expect(screen.getByText("View full alert history")).toBeInTheDocument();
    expect(screen.queryByText(/Trigger alert mock/)).not.toBeInTheDocument();
  });

  it("keeps the ward summary visible when alerts fail and shows a section warning", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        relatedAlerts: [],
        workflow: {
          public_id: "WF-100",
          status: "FAILED",
          status_label: "Action in progress",
          recommended_action: "Inspect the failed alert record, confirm the recipient path, and decide whether to resend or escalate manually.",
          expected_operational_effect: "Keeps failed delivery from being mistaken for completed operational follow-up.",
          eligible_actions: ["REVIEW_TRIGGER", "VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 1,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-22T18:00:00Z",
          updated_at: "2026-04-22T18:03:00Z",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByRole("heading", { name: "North Kamagambo" })).toBeInTheDocument();
    expect(await screen.findByText("Risk history")).toBeInTheDocument();
    expect(await screen.findByText("Trigger alert mock | Review trigger | 12 | North Kamagambo")).toBeInTheDocument();
    expect(screen.getByText("Recent alerts")).toBeInTheDocument();
    expect(screen.getByText(/no recent alerts for this ward/i)).toBeInTheDocument();
  });

  it("renders explicit trigger state, stale freshness, and action-first controls without scrolling assumptions", async () => {
    render(React.createElement(WardDetailPage));

    expect(await screen.findAllByText("Awaiting review")).toHaveLength(2);
    expect(screen.getByText("Stale data")).toBeInTheDocument();
    expect(screen.getByText("Action required. Review active alerts and trigger status.")).toBeInTheDocument();
    expect(screen.getAllByText("View full alert history")).toHaveLength(2);
    expect(screen.getByText("Data status")).toBeInTheDocument();
    expect(screen.getByText("Trigger alert mock | Review trigger | 12 | North Kamagambo")).toBeInTheDocument();
  });

  it("shows compact operational empty states when signals, history, and alerts are unavailable", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        riskLevel: "LOW",
        triggerState: "NONE",
        actionRequired: false,
        primaryCtaKind: "VIEW_ALERT_HISTORY",
        driverItems: [],
        riskHistory: [],
        relatedAlerts: [],
        workflow: {
          public_id: "WF-102",
          status: "NONE",
          status_label: "No active trigger",
          recommended_action: "Continue routine monitoring and start a new trigger only if conditions change.",
          expected_operational_effect: "Keeps manual trigger initiation available without overstating it as the current primary action.",
          eligible_actions: ["OPEN_TRIGGER_FLOW", "VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 0,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-27T08:00:00Z",
          updated_at: "2026-04-27T08:02:00Z",
        },
        decisionSummary: {
          action_required: false,
          headline: "No decision required at this time.",
          why: "This ward is under routine monitoring.",
          next_steps: ["Review full alert history", "Continue routine surveillance", "Open trigger flow only if conditions change"],
          primary_cta_kind: "VIEW_ALERT_HISTORY",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("Risk signals & trend")).toBeInTheDocument();
    expect(screen.getByText("No active signals or trends detected.")).toBeInTheDocument();
    expect(screen.getByText("This ward is currently under routine monitoring.")).toBeInTheDocument();
    expect(screen.queryByText("Risk history")).not.toBeInTheDocument();
    expect(screen.getByText("No recent alerts for this ward")).toBeInTheDocument();
    expect(screen.getByText(/Latest record:/i)).toBeInTheDocument();
    expect(screen.getByText("Review alert history")).toBeInTheDocument();
    expect(screen.getByText("Continue routine surveillance")).toBeInTheDocument();
    expect(screen.getByText("No decision required at this time.")).toBeInTheDocument();
    expect(screen.getByText("Context: Routine monitoring (no active escalation)")).toBeInTheDocument();
    expect(screen.getByText("Trigger alert mock | Open trigger flow | 12 | North Kamagambo")).toBeInTheDocument();
  });

  it("uses backend freshness state instead of re-deriving staleness from timestamps", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        updatedAt: "2026-04-22T18:00:00Z",
        freshness: {
          generated_at: "2026-04-22T18:00:00Z",
          is_stale: false,
          stale_threshold_minutes: 120,
          history_count: 2,
          alert_count: 1,
          mode: "timestamp_and_record_availability",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText(/ward detail \| migori county ward decision console \| .* \| default/i)).toBeInTheDocument();
    expect(screen.getByText("Fresh data")).toBeInTheDocument();
    expect(screen.queryByText(/ \| stale$/i)).not.toBeInTheDocument();
  });

  it("shows a no-action monitoring state when the workflow is resolved", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        triggerState: "RESOLVED",
        actionRequired: false,
        primaryCtaKind: "VIEW_ALERT_HISTORY",
        freshness: {
          generated_at: "2026-04-27T08:00:00Z",
          is_stale: false,
          stale_threshold_minutes: 120,
          history_count: 2,
          alert_count: 1,
          mode: "timestamp_and_record_availability",
        },
        workflow: {
          public_id: "WF-101",
          status: "RESOLVED",
          status_label: "Resolved",
          recommended_action: "Continue routine monitoring and review recent activity for any early signal changes.",
          expected_operational_effect: "Keeps resolved workflow state explicit without elevating it into active action work.",
          eligible_actions: ["VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 0,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-27T08:00:00Z",
          updated_at: "2026-04-27T08:02:00Z",
        },
        decisionSummary: {
          action_required: false,
          headline: "No active trigger action is required right now.",
          why: "No elevated trigger condition is visible for this ward right now.",
          next_steps: ["Review full alert history", "Open Trigger Flow"],
          primary_cta_kind: "VIEW_ALERT_HISTORY",
        },
        headerContext: {
          last_alert_at: "2026-04-27T08:05:00Z",
          latest_record_at: "2026-04-27T08:00:00Z",
          freshness_state: "FRESH",
          trigger_state: "RESOLVED",
          expected_cases_7d: 12,
          risk_score: 86,
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findAllByText("Resolved")).toHaveLength(2);
    expect(screen.getByText("Fresh data")).toBeInTheDocument();
    expect(screen.getByText("No active trigger action is required right now.")).toBeInTheDocument();
    expect(screen.getByText("Review full alert history")).toBeInTheDocument();
    expect(screen.getByText(/current next step: review alert history\. open trigger flow only if conditions change\./i)).toBeInTheDocument();
    expect(screen.queryByText(/Trigger alert mock/)).not.toBeInTheDocument();
  });

  it("keeps empty recent-alerts guidance aligned with history-first CTA states", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        triggerState: "RESOLVED",
        actionRequired: false,
        primaryCtaKind: "VIEW_ALERT_HISTORY",
        relatedAlerts: [],
        workflow: {
          public_id: "WF-101",
          status: "RESOLVED",
          status_label: "Resolved",
          recommended_action: "Continue routine monitoring and review recent activity for any early signal changes.",
          expected_operational_effect: "Keeps resolved workflow state explicit without elevating it into active action work.",
          eligible_actions: ["VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 0,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-27T08:00:00Z",
          updated_at: "2026-04-27T08:02:00Z",
        },
        decisionSummary: {
          action_required: false,
          headline: "No active trigger action is required right now.",
          why: "No elevated trigger condition is visible for this ward right now.",
          next_steps: ["Review full alert history", "Open Trigger Flow"],
          primary_cta_kind: "VIEW_ALERT_HISTORY",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("No recent alerts for this ward")).toBeInTheDocument();
    expect(screen.getByText("Review full alert history if you need older ward-linked alert activity.")).toBeInTheDocument();
    expect(screen.queryByText(/open trigger flow if a guided response is still needed/i)).not.toBeInTheDocument();
  });

  it("promotes new trigger initiation when the ward is in a genuine none state", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        riskLevel: "LOW",
        triggerState: "NONE",
        actionRequired: false,
        primaryCtaKind: "OPEN_TRIGGER_FLOW",
        workflow: {
          public_id: "WF-102",
          status: "NONE",
          status_label: "No active trigger",
          recommended_action: "Continue routine monitoring and start a new trigger only if conditions change.",
          expected_operational_effect: "Keeps manual trigger initiation available without overstating it as the current primary action.",
          eligible_actions: ["OPEN_TRIGGER_FLOW", "VIEW_ALERT_HISTORY"],
          active_alert_count: 0,
          retry_pending_alert_count: 0,
          failed_alert_count: 0,
          queued_alert_count: 0,
          latest_risk_update_at: "2026-04-27T08:00:00Z",
          updated_at: "2026-04-27T08:02:00Z",
        },
        decisionSummary: {
          action_required: false,
          headline: "No active trigger action is required right now.",
          why: "No elevated trigger condition is visible for this ward right now.",
          next_steps: ["Open Trigger Flow", "Review full alert history"],
          primary_cta_kind: "OPEN_TRIGGER_FLOW",
        },
        headerContext: {
          last_alert_at: null,
          latest_record_at: "2026-04-27T08:00:00Z",
          freshness_state: "FRESH",
          trigger_state: "NONE",
          expected_cases_7d: 1,
          risk_score: 22,
        },
        relatedAlerts: [],
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("Trigger alert mock | Open Trigger Flow | 12 | North Kamagambo")).toBeInTheDocument();
    expect(screen.getAllByText("No active trigger").length).toBeGreaterThan(0);
    expect(screen.getByText("Trigger alert mock | Open Trigger Flow | 12 | North Kamagambo")).toBeInTheDocument();
    expect(screen.getByText("View full alert history")).toBeInTheDocument();
    expect(screen.getByText("No decision required at this time.")).toBeInTheDocument();
  });

  it("shows a routine-monitoring checkpoint instead of an unavailable decision summary in low-signal mode", async () => {
    mockUseWardDetailQuery.mockReturnValue({
      data: buildWardDetailState({
        riskLevel: "LOW",
        triggerState: "NONE",
        actionRequired: false,
        decisionSummary: {
          action_required: false,
          headline: "No decision required at this time.",
          why: "This ward is under routine monitoring.",
          next_steps: ["Review full alert history"],
          primary_cta_kind: "VIEW_ALERT_HISTORY",
        },
      }),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(WardDetailPage));

    expect(await screen.findByText("No decision required at this time.")).toBeInTheDocument();
    expect(screen.getByText("This ward is under routine monitoring.")).toBeInTheDocument();
    expect(screen.getByText("Context: Routine monitoring (no active escalation)")).toBeInTheDocument();
  });
});
