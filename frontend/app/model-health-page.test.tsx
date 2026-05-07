import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ModelHealthPage from "@/app/(dashboard)/model-health/page";
import type { ModelOperationsHealthResponse } from "@/lib/dashboard";

const mockUseModelOperationsHealthQuery = vi.fn();
const mockRefetch = vi.fn();

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    lastUpdatedLabel,
  }: {
    title: string;
    subtitle: string;
    lastUpdatedLabel?: string;
  }) => React.createElement("div", null, `${title} | ${subtitle} | ${lastUpdatedLabel ?? "no-label"}`),
}));

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock("@/queries/use-model-health-query", () => ({
  useModelOperationsHealthQuery: () => mockUseModelOperationsHealthQuery(),
}));

function buildDashboard(): ModelOperationsHealthResponse {
  return {
    schema_version: "ward-risk-model-operations-health-v1",
    generated_at: "2026-05-07T08:00:00Z",
    summary: {
      health_state: "no_active_model",
      health_state_label: "No Active Model",
      health_tone: "danger",
      active_model_healthy: false,
      active_model_present: false,
      monitoring_state: "NOT_CONFIGURED",
      drift_warning_count: 0,
      calibration_warning_count: 0,
      rollback_event_count: 0,
      challenger_benchmark_status: "not_configured",
    },
    active_model: null,
    monitoring: {
      state: "NOT_CONFIGURED",
      state_label: "Not Configured",
      latest_monitoring_run_id: null,
      latest_generated_at: null,
      snapshots: [],
      drift_warnings: [],
      calibration_warnings: [],
    },
    challenger_comparison: {
      configured: false,
      benchmark_status: "not_configured",
      comparison_validity: null,
      dashboard_summary: {
        safe_for_dashboard: true,
        challenger_outputs_affect_alerts: false,
        challenger_outputs_update_current_ward_risk: false,
        can_replace_champion_without_phase_4_promotion: false,
      },
      comparison: null,
    },
    rollback_history: [],
    model_states: [
      {
        model_run_id: 1,
        algorithm: "lr",
        algorithm_name: "Logistic regression",
        model_version: "lr-v1",
        status: "success",
        visual_state: "benchmark_only",
        visual_state_label: "Benchmark Only",
        promotion_target: "benchmark_only",
        promotion_state: null,
        registry_promotion_state: null,
        alert_eligible: false,
        run_purpose: "testing",
        started_at: "2026-05-07T06:00:00Z",
        completed_at: "2026-05-07T06:03:00Z",
      },
    ],
    dashboard_policy: {},
  };
}

describe("ModelHealthPage", () => {
  beforeEach(() => {
    mockRefetch.mockReset();
    mockUseModelOperationsHealthQuery.mockReturnValue({
      data: buildDashboard(),
      isPending: false,
      error: null,
      refetch: mockRefetch,
      isFetching: false,
    });
  });

  it("presents model operations as plain forecast readiness", () => {
    render(<ModelHealthPage />);

    expect(
      screen.getByText(/Forecast Readiness \| See whether ward-risk forecasts are ready to guide alerts and planning/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Not ready for operational use")).toBeInTheDocument();
    expect(screen.getByText(/No approved ward-risk forecast is live/i)).toBeInTheDocument();
    expect(screen.getByText("Readiness checklist")).toBeInTheDocument();
    expect(screen.getByText("Current approved forecast")).toBeInTheDocument();
    expect(screen.getAllByText("Quality checks").length).toBeGreaterThan(0);
    expect(screen.getByText("Forecast versions")).toBeInTheDocument();

    expect(screen.queryByText(/Champion/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Challenger/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Phase 4/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Rollback/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Drift warnings/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Calibration warnings/i)).not.toBeInTheDocument();
  });
});
