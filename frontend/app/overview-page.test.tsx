import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OverviewPage from "@/app/(dashboard)/overview/page";

const mockUseAuth = vi.fn();
const mockUseOverviewQuery = vi.fn();
const mockPush = vi.fn();
const mockUseSearchParams = vi.fn();

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    children,
  }: {
    title: string;
    subtitle: string;
    children?: React.ReactNode;
  }) => React.createElement("div", null, `${title} | ${subtitle}`, children),
}));

vi.mock("@/components/overview-hotspot-map", () => ({
  OverviewHotspotMap: ({
    features,
    onSelectWard,
  }: {
    features?: Array<{ properties: { name: string; backend_ward_id: number } }>;
    onSelectWard?: (feature: { properties: { name: string; backend_ward_id: number } }) => void;
  }) =>
    React.createElement(
      "div",
      null,
      "Overview hotspot map mock",
      ...(features ?? []).map((feature) =>
        React.createElement(
          "button",
          {
            key: feature.properties.backend_ward_id,
            type: "button",
            onClick: () => onSelectWard?.(feature),
          },
          `Select ${feature.properties.name}`,
        ),
      ),
    ),
}));

vi.mock("@/components/trigger-alert-panel", () => ({
  TriggerAlertPanel: () => React.createElement("div", null, "Trigger alert mock"),
}));

vi.mock("@/components/trigger-review-drawer", () => ({
  TriggerReviewDrawer: ({ trigger }: { trigger: { ward_name: string } | null }) =>
    trigger ? React.createElement("div", null, `Trigger review mock: ${trigger.ward_name}`) : null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockUseSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/queries/use-overview-query", () => ({
  useOverviewQuery: (...args: unknown[]) => mockUseOverviewQuery(...args),
}));

describe("OverviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
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

    mockUseOverviewQuery.mockReturnValue({
      data: {
        wards: [
          {
            id: 1,
            public_id: "ward-1",
            name: "North Kamagambo",
            county: "Migori",
            sub_county: "Rongo",
            ward_code: "MIG-01",
            current_risk_level: "HIGH",
            current_risk_score: 0.91,
            is_active: true,
            updated_at: "2026-04-25T08:00:00Z",
          },
        ],
        totalWards: 5,
        highRiskWards: [
          {
            ward_id: 1,
            ward_name: "North Kamagambo",
            risk_level: "HIGH",
            risk_score: 0.91,
            predicted_cases: 8,
            generated_at: "2026-04-25T08:00:00Z",
          },
        ],
        mediumRiskWards: [
          {
            ward_id: 2,
            ward_name: "North Kadem",
            risk_level: "MEDIUM",
            risk_score: 0.56,
            predicted_cases: 4,
            generated_at: "2026-04-25T08:10:00Z",
          },
        ],
        recentAlerts: [
          {
            id: 7,
            ward: 1,
            ward_name: "North Kamagambo",
            risk_score: 0.91,
            channel: "DASHBOARD",
            recipient: "Ops desk",
            message: "High risk ward review required",
            status: "QUEUED",
            delivery_backend: "dashboard",
            attempt_count: 0,
            max_attempts: 3,
            last_attempted_at: null,
            next_retry_at: null,
            external_id: "alert-7",
            sent_at: null,
            created_at: "2026-04-25T08:15:00Z",
            error_message: "",
          },
        ],
        wardMap: {
          type: "FeatureCollection",
          metadata: {
            county: "Migori",
            geometry_source: "test",
            geometry_feature_count: 1,
            expected_ward_count: 1,
            missing_source_wards: [],
            backend_ward_match_count: 1,
            returned_feature_count: 1,
            backend_wards_without_geometry: [],
            placeholder_geometry_detected: false,
            geometry_note: null,
          },
          features: [
            {
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [
                  [
                    [34.6, -0.9],
                    [34.7, -0.9],
                    [34.7, -1.0],
                    [34.6, -1.0],
                    [34.6, -0.9],
                  ],
                ],
              },
              properties: {
                name: "North Kamagambo",
                ward_code: "MIG-01",
                backend_ward_id: 1,
                centroid: [34.65, -0.95],
                current_risk_level: "HIGH",
                current_risk_score: 0.91,
                risk_level: "HIGH",
                alert_count: 1,
                predicted_cases: 8,
                trend: { label: "Escalating" },
                prediction: {
                  horizon_days: 7,
                  predicted_risk_level: "HIGH",
                  predicted_risk_score: 0.92,
                  predicted_cases: 8,
                  prediction_generated_at: "2026-04-25T08:00:00Z",
                  prediction_model_version: "v0-demo",
                },
              },
            },
            {
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [
                  [
                    [34.3, -1.0],
                    [34.4, -1.0],
                    [34.4, -1.1],
                    [34.3, -1.1],
                    [34.3, -1.0],
                  ],
                ],
              },
              properties: {
                name: "North Kadem",
                ward_code: "MIG-02",
                backend_ward_id: 2,
                centroid: [34.35, -1.05],
                current_risk_level: "MEDIUM",
                current_risk_score: 0.56,
                risk_level: "MEDIUM",
                alert_count: 0,
                predicted_cases: 4,
                trend: { label: "Watch" },
                prediction: {
                  horizon_days: 7,
                  predicted_risk_level: "MEDIUM",
                  predicted_risk_score: 0.58,
                  predicted_cases: 4,
                  prediction_generated_at: "2026-04-25T08:10:00Z",
                  prediction_model_version: "v0-demo",
                },
              },
            },
          ],
        },
        alertsTodayCount: 1,
        deliveredAlertRate: 0,
        latestTimestamp: "2026-04-25T08:15:00Z",
        primaryCountyLabel: "Migori",
        overviewState: {
          system_state: "action_required",
          state_reason: "1 ward currently sits in the high-risk band.",
          system_state_reason: "1 ward currently sits in the high-risk band.",
          trigger_count: 1,
          watch_count: 1,
          action_required_count: 1,
          last_triggered_at: "2026-04-25T08:15:00Z",
          trigger_summary: {
            triggered_wards_count: 1,
            under_watch_wards_count: 1,
            action_required_wards_count: 1,
          },
          risk_state: {
            label: "High-risk wards are visible.",
            high_risk_wards_count: 1,
            under_watch_wards_count: 1,
          },
          alert_state: {
            label: "Visible alert activity is present.",
            visible_alert_count: 1,
            triggered_wards_count: 1,
          },
          action_state: {
            label: "Escalate review and prepare response now.",
            recommended_mode: "act",
            action_required_wards_count: 1,
          },
        },
        decisionSummary: {
          top_priority_ward: {
            ward_id: 1,
            ward_name: "North Kamagambo",
            risk_level: "HIGH",
            risk_score: 0.91,
            predicted_cases: 8,
            alert_count: 1,
            has_active_alert: true,
            generated_at: "2026-04-25T08:00:00Z",
          },
          reason_flagged: "North Kamagambo has unresolved alert activity and still sits in the current decision surface.",
          recommended_action: "Review active alerts, confirm field conditions, and prepare targeted follow-up.",
          decision_mode: "triggered",
          eligible_actions: ["view_alerts", "investigate", "dispatch_chvs"],
          rules_basis: {
            source: "bff_rules_v1",
            rule_id: "unresolved_alert_priority",
            rule_label: "Unresolved alert takes priority",
            inputs: ["unresolved alert activity", "ward remains in visible decision scope"],
          },
        },
        triggerReviewQueue: [
          {
            trigger_id: "ward-trigger:1",
            ward_id: 1,
            ward_name: "North Kamagambo",
            risk_level: "HIGH",
            risk_score: 0.91,
            predicted_cases: 8,
            trend_label: "Alert activity still unresolved",
            trigger_reason_items: [
              {
                label: "Threshold breach",
                detail: "North Kamagambo is currently in the promoted high-risk band.",
                tone: "danger",
              },
            ],
            confidence: "high",
            triggered_at: "2026-04-25T08:15:00Z",
            recommended_action: "Review active alerts, confirm field conditions, and decide whether to reinforce field follow-up.",
            rules_basis: {
              source: "bff_rules_v1",
              rule_id: "trigger_queue_existing_alert_followup",
              rule_label: "Trigger queue with existing alert",
              inputs: ["unresolved alert already exists", "ward remains reviewable in current scope"],
            },
            expected_operational_effect: "Keeps the operator aligned with live alert activity and reduces duplicate escalation.",
            dismissible: false,
            has_active_alert: true,
            alert_count: 1,
            eligible_actions: ["view_alerts", "investigate", "dispatch_chvs"],
            latest_risk_update_at: "2026-04-25T08:00:00Z",
          },
        ],
        freshness: {
          last_model_run_at: "2026-04-25T08:00:00Z",
          last_data_sync_at: "2026-04-25T08:05:00Z",
          last_alert_ingestion_at: "2026-04-25T08:15:00Z",
          prediction_generated_at: "2026-04-25T08:00:00Z",
          freshness_state: "fresh",
        },
        temporalMetrics: {
          high_risk: {
            current_value: 1,
            previous_value: 0,
            delta: 1,
            direction: "up",
            context_label: "vs yesterday",
          },
          medium_risk: {
            current_value: 1,
            previous_value: 2,
            delta: -1,
            direction: "down",
            context_label: "vs yesterday",
          },
          alerts_today: {
            current_value: 1,
            previous_value: 3,
            delta: -2,
            direction: "down",
            context_label: "vs previous 24h",
          },
          delivered_alert_rate: {
            current_value: 0,
            previous_value: 40,
            delta: -40,
            direction: "down",
            context_label: "vs previous 24h",
          },
        },
        missionMetrics: {
          monitored_wards_count: 1,
          workflow_active_wards_count: 1,
          trigger_delivery_concern_count: 0,
          last_trigger_lead_time_hours: 96,
          last_trigger_lead_time_label: "4 d",
          last_triggered_at: "2026-04-25T08:15:00Z",
          last_trigger_risk_signal_at: "2026-04-21T08:15:00Z",
        },
        mapGuidance: {
          top_triggered_ward: {
            ward_id: 1,
            ward_name: "North Kamagambo",
            label: "Top triggered ward",
            reason: "North Kamagambo has the strongest active trigger load in the current scope.",
            risk_level: "HIGH",
            risk_score: 0.91,
            alert_count: 1,
            predicted_cases: 8,
          },
          most_active_alert_ward: {
            ward_id: 1,
            ward_name: "North Kamagambo",
            label: "Most active alert ward",
            reason: "1 visible alert currently cluster in North Kamagambo.",
            risk_level: "HIGH",
            risk_score: 0.91,
            alert_count: 1,
            predicted_cases: 8,
          },
          biggest_recent_escalation: {
            ward_id: 1,
            ward_name: "North Kamagambo",
            label: "Biggest recent escalation",
            reason: "North Kamagambo shows the largest visible risk-score lift versus the prior daily window.",
            risk_level: "HIGH",
            risk_score: 0.91,
            alert_count: 1,
            predicted_cases: 8,
          },
          predicted_highest_risk_ward: {
            ward_id: 1,
            ward_name: "North Kamagambo",
            label: "Predicted highest-risk ward",
            reason: "North Kamagambo currently leads the predicted hotspot surface.",
            risk_level: "HIGH",
            risk_score: 0.91,
            alert_count: 1,
            predicted_cases: 8,
          },
        },
        triggerLinkage: {
          triggered_wards: [
            {
              ward_id: 1,
              ward_name: "North Kamagambo",
              risk_level: "HIGH",
              risk_score: 0.91,
              predicted_cases: 8,
              trigger_reason: "North Kamagambo has a recorded trigger and the alert is still queued for delivery.",
              trigger_severity: "high",
              triggered_at: "2026-04-25T08:15:00Z",
              recommended_response:
                "Watch the queued alert until the first delivery attempt completes and avoid duplicating the response request.",
              rules_basis: {
                source: "bff_rules_v1",
                rule_id: "trigger_delivery_queued_monitor",
                rule_label: "Queued delivery monitoring",
                inputs: ["recorded trigger", "first delivery attempt not complete"],
              },
              workflow_state: "ACTION_IN_PROGRESS",
              workflow_state_label: "Action in progress",
              alert_delivery_state: "triggered_queued",
              alert_delivery_label: "Triggered and queued",
              alert_count: 1,
              delivered_alert_count: 0,
              retry_pending_alert_count: 0,
              failed_alert_count: 0,
              queued_alert_count: 1,
            },
          ],
          active_alert_wards_count: 1,
          delivered_wards_count: 0,
          retry_pending_wards_count: 0,
          failed_wards_count: 0,
          awaiting_review_wards_count: 0,
          delivery_concern_wards_count: 0,
        },
        simulationReadiness: {
          supported: true,
          status_label: "Scenario simulation available",
          status_reason:
            "The dashboard can now run bounded non-production scenarios without touching promoted live outputs.",
          required_contracts: [
            "Rainfall adjustment input contract",
            "Forecast perturbation input contract",
            "Predicted risk recomputation envelope",
            "Safe non-production execution and result-isolation rules",
          ],
          prepared_inputs: {
            rainfall_adjustments:
              "Would need bounded rainfall deltas or uplift factors tied to ward and time windows before recomputing downstream prediction surfaces.",
            forecast_perturbation_inputs:
              "Would need explicit non-production knobs for response delay, delivery latency, or facility pressure assumptions with audit metadata.",
            predicted_risk_recomputation_envelope:
              "Would need a temporary recomputation path that cannot overwrite promoted live outputs or confuse dashboard truth labels.",
            safe_non_production_execution_rules:
              "Would need user-visible non-production labeling, short-lived results, access control, and no persistence into promoted operational records.",
          },
          reserved_scenarios: [
            {
              id: "rainfall_increase",
              label: "What if rainfall increases?",
              prompt: "Explore how a bounded rainfall increase could alter predicted risk without touching live outputs.",
            },
            {
              id: "response_delay",
              label: "What if response is delayed?",
              prompt: "Explore how delayed response or delivery friction could change operational pressure and follow-up needs.",
            },
          ],
        },
        facilityReadiness: {
          facilities_at_risk_count: 2,
          facilities_capacity_concern_count: 1,
          priority_facilities: [
            {
              facility_id: 10,
              facility_name: "North Kamagambo Dispensary",
              ward_id: 1,
              ward_name: "North Kamagambo",
              readiness_state: "capacity_concern",
              readiness_score: 91,
              projected_pressure_score: 91,
              projected_case_burden: 12,
              driving_ward_ids: [1],
              readiness_factors: ["Promoted facility forecast is driving this readiness summary."],
              snapshot_at: "2026-04-25T08:00:00Z",
              generated_at: "2026-04-25T08:00:00Z",
              freshness_state: "FRESH",
              backing_source: "forecast_promoted",
              dashboard_truth_state: "promoted_forecast",
            },
          ],
          ward_capacity_signals: [
            {
              ward_id: 1,
              ward_name: "North Kamagambo",
              facility_capacity_signal: "capacity_concern",
              facility_readiness_tone: "danger",
              facility_count: 1,
              priority_facility_ids: [10],
              priority_facility_names: ["North Kamagambo Dispensary"],
            },
          ],
          honesty_note: "Facility readiness signals shown here are backed by promoted facility-forecast outputs.",
        },
      },
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseSearchParams.mockReturnValue({
      get: vi.fn().mockReturnValue(null),
    });
  });

  it("renders normalized risk, alert, and action vocabulary with the overview state model", () => {
    render(React.createElement(OverviewPage));

    expect(screen.getByText("Early Warning & Action | Predict risk, trigger action, and coordinate response")).toBeInTheDocument();
    expect(screen.getByText("High risk wards")).toBeInTheDocument();
    expect(screen.getAllByText("Workflow-active wards").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Active alerts").length).toBeGreaterThan(0);
    expect(screen.getByText("Last trigger lead time")).toBeInTheDocument();
    expect(screen.getByText("4 d")).toBeInTheDocument();
    expect(screen.getByText("Priority Wards for Action")).toBeInTheDocument();
    expect(screen.getAllByText("Action required").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 ward awaiting review").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Review trigger queue" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Trigger state")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Action" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Action Focus")).toBeInTheDocument();
    expect(screen.getAllByText("North Kamagambo").length).toBeGreaterThan(0);
    expect(screen.getByText("Priority ward")).toBeInTheDocument();
    expect(
      screen.getByText("North Kamagambo has unresolved alert activity and still sits in the current decision surface."),
    ).toBeInTheDocument();
    expect(screen.getByText("Action in progress")).toBeInTheDocument();
    expect(screen.getByText("Delivery status: Triggered and queued")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Focus ward" }).length).toBeGreaterThan(0);
    expect(screen.getByText(/Current baseline|Backend priority/)).toBeInTheDocument();
    expect(screen.getAllByText("Review alerts").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Workflow-active wards").length).toBeGreaterThan(0);
    expect(screen.getByText("Map guidance")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Current" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Predicted (7d)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Workflow-active wards" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delivery concern" })).toBeInTheDocument();
    expect(screen.getByText("+1 vs yesterday")).toBeInTheDocument();
    expect(screen.getByText("-2 vs previous 24h")).toBeInTheDocument();
    expect(screen.queryByText("-40% vs previous 24h")).not.toBeInTheDocument();
  });

  it("switches the map into predicted mode with explicit prediction language", async () => {
    const user = userEvent.setup();

    render(React.createElement(OverviewPage));

    await user.click(screen.getByRole("button", { name: "Predicted (7d)" }));

    expect(screen.getAllByText("Action Focus").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Predicted 7-day/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Predicted 7-day outlook:/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Prediction review:/i).length).toBeGreaterThan(0);
  });

  it("updates the action module from KPI, guidance chip, map, and side tabs", async () => {
    const user = userEvent.setup();

    render(React.createElement(OverviewPage));

    await user.click(screen.getByTitle("Filter map to workflow-active wards"));
    expect(screen.getByRole("tab", { name: "Triggers" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByText("Review trigger queue").length).toBeGreaterThan(0);

    await user.click(screen.getByText("Map guidance"));
    await user.click(screen.getByRole("button", { name: "Most active alert ward" }));
    expect(screen.getAllByText("North Kamagambo").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Select North Kadem" }));
    await user.click(screen.getByRole("tab", { name: "Action" }));
    expect(screen.getByText("Action Focus")).toBeInTheDocument();
    expect(screen.getByText("North Kadem")).toBeInTheDocument();
    expect(screen.getByText("Map selection")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Scenarios" }));
    expect(screen.getByText("Scenario tools")).toBeInTheDocument();
    expect(screen.getByText("What if rainfall increases?")).toBeInTheDocument();
  });

  it("renders the stable empty-state decision surface honestly when no active ward is nominated", () => {
    mockUseOverviewQuery.mockReturnValue({
      data: {
        wards: [],
        totalWards: 0,
        highRiskWards: [],
        mediumRiskWards: [],
        recentAlerts: [],
        wardMap: {
          type: "FeatureCollection",
          metadata: {
            county: "Migori",
            geometry_source: "test",
            geometry_feature_count: 0,
            expected_ward_count: 40,
            missing_source_wards: [],
            backend_ward_match_count: 0,
            returned_feature_count: 0,
            backend_wards_without_geometry: [],
            placeholder_geometry_detected: false,
            geometry_note: null,
          },
          features: [],
        },
        alertsTodayCount: 0,
        deliveredAlertRate: 100,
        latestTimestamp: null,
        primaryCountyLabel: "Migori",
        overviewState: {
          system_state: "stable",
          state_reason: "No active trigger conditions are visible.",
          system_state_reason: "No active trigger conditions are visible.",
          trigger_count: 0,
          watch_count: 0,
          action_required_count: 0,
          last_triggered_at: null,
          trigger_summary: {
            triggered_wards_count: 0,
            under_watch_wards_count: 0,
            action_required_wards_count: 0,
          },
          risk_state: {
            label: "No high-risk wards are visible.",
            high_risk_wards_count: 0,
            under_watch_wards_count: 0,
          },
          alert_state: {
            label: "No alert activity is currently visible.",
            visible_alert_count: 0,
            triggered_wards_count: 0,
          },
          action_state: {
            label: "Continue routine monitoring.",
            recommended_mode: "monitor",
            action_required_wards_count: 0,
          },
        },
        decisionSummary: {
          top_priority_ward: null,
          reason_flagged: "No priority ward is currently nominated by the backend.",
          recommended_action: "Continue routine monitoring.",
          decision_mode: "risk_only",
          eligible_actions: [],
          rules_basis: {
            source: "bff_rules_v1",
            rule_id: "stable_monitor_only",
            rule_label: "Stable monitoring posture",
            inputs: ["no visible high-risk ward", "no unresolved trigger condition"],
          },
        },
        triggerReviewQueue: [],
        freshness: {
          last_model_run_at: null,
          last_data_sync_at: null,
          last_alert_ingestion_at: null,
          prediction_generated_at: null,
          freshness_state: "stale",
        },
        temporalMetrics: {
          high_risk: {
            current_value: 0,
            previous_value: 0,
            delta: 0,
            direction: "flat",
            context_label: "vs yesterday",
          },
          medium_risk: {
            current_value: 0,
            previous_value: 0,
            delta: 0,
            direction: "flat",
            context_label: "vs yesterday",
          },
          alerts_today: {
            current_value: 0,
            previous_value: 0,
            delta: 0,
            direction: "flat",
            context_label: "vs previous 24h",
          },
          delivered_alert_rate: {
            current_value: 100,
            previous_value: 100,
            delta: 0,
            direction: "flat",
            context_label: "vs previous 24h",
          },
        },
        missionMetrics: {
          monitored_wards_count: 0,
          workflow_active_wards_count: 0,
          trigger_delivery_concern_count: 0,
          last_trigger_lead_time_hours: null,
          last_trigger_lead_time_label: "No trigger yet",
          last_triggered_at: null,
          last_trigger_risk_signal_at: null,
        },
        mapGuidance: {
          top_triggered_ward: null,
          most_active_alert_ward: null,
          biggest_recent_escalation: null,
          predicted_highest_risk_ward: null,
        },
        triggerLinkage: {
          triggered_wards: [],
          active_alert_wards_count: 0,
          delivered_wards_count: 0,
          retry_pending_wards_count: 0,
          failed_wards_count: 0,
          awaiting_review_wards_count: 0,
          delivery_concern_wards_count: 0,
        },
        simulationReadiness: {
          supported: true,
          status_label: "Scenario simulation available",
          status_reason: "The dashboard can run bounded non-production scenarios without touching promoted live outputs.",
          required_contracts: [],
          prepared_inputs: {},
          reserved_scenarios: [],
        },
        facilityReadiness: {
          facilities_at_risk_count: 0,
          facilities_capacity_concern_count: 0,
          priority_facilities: [],
          ward_capacity_signals: [],
          honesty_note: "No facility readiness signal is currently available.",
        },
      },
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(OverviewPage));

    expect(screen.getByText("No active triggers")).toBeInTheDocument();
    expect(screen.getByText("System operating normally")).toBeInTheDocument();
    expect(screen.getAllByText("Continue routine monitoring.").length).toBeGreaterThan(0);
    expect(screen.getByText("Action Focus")).toBeInTheDocument();
    expect(screen.getByText("System stable")).toBeInTheDocument();
    expect(screen.getByText("Select a ward for details.")).toBeInTheDocument();
  });
});
