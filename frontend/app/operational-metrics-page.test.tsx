import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OperationalMetricsPage from "@/app/(dashboard)/operational-metrics/page";
import type { OperationalKpiDashboardResponse } from "@/lib/dashboard";

const mockUseOperationalMetricsQuery = vi.fn();
const mockPush = vi.fn();
const mockRefetch = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({ title, subtitle }: { title: string; subtitle: string }) =>
    React.createElement("div", null, `${title} | ${subtitle}`),
}));

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock("@/queries/use-operational-metrics-query", () => ({
  useOperationalMetricsQuery: (...args: unknown[]) => mockUseOperationalMetricsQuery(...args),
}));

function buildOperationalDashboard(): OperationalKpiDashboardResponse {
  return {
    schema_version: "operational-kpi-dashboard-v1",
    generated_at: "2026-05-04T10:00:00Z",
    filters: {
      date_from: "2026-05-01",
      date_to: "2026-05-04",
      ward_id: null,
      ward_name: "",
      sub_county: "",
      source_channel: "",
    },
    available_filters: {
      wards: [],
      sub_counties: [],
      source_channels: [],
    },
    summary: {
      metric_count: 0,
      snapshot_count: 0,
      latest_snapshot_date: null,
      complete_metric_count: 0,
      evaluable_metric_count: 0,
      warning_count: 1,
      threshold_alert_count: 0,
      critical_threshold_alert_count: 0,
      warning_threshold_alert_count: 0,
      status_counts: {},
      operational_health: "warning",
      model_metric_count: 0,
    },
    panels: {
      operational_overview: [],
      sla: [],
      adoption_coverage: [],
      response_time_trends: [],
      facility_preparedness_trends: [],
      ussd_completion_trends: [],
      model_vs_operations: {
        separation_statement: "Operational KPIs are separate from model artifacts.",
        operational_metric_family: "OPERATIONAL",
        model_metric_family: "MODEL",
        latest_model_run: {
          model_version: null,
          status: null,
          started_at: null,
          completed_at: null,
          evaluation_metrics: {},
        },
        operational_metric_groups: [],
      },
      source_coverage_warnings: [
        {
          metric_key: "interoperability_mapping_coverage",
          warning: "latest_interoperability_run_not_clean",
          snapshot_key: "run-partial",
          snapshot_date: "2026-05-04",
          status: "PARTIAL",
        },
      ],
      threshold_alerts: [],
      interoperability_contracts: {
        schema_version: "interoperability-operational-kpi-feed-v1",
        generated_at: "2026-05-04T10:00:00Z",
        audit_status: "fail",
        latest_mapping_coverage: 75,
        latest_run: {
          public_id: "run-partial",
          direction: "EXPORT",
          exchange_type: "aggregate_report_export",
          system_key: "dhis2",
          system_name: "DHIS2",
          mapping_version: "dhis2-v1",
          retry_of: null,
          status: "PARTIAL",
          dry_run: true,
          source_file_name: "",
          endpoint_url: "cchis://risk-scores/latest",
          source_reference: "cchis://risk-scores/latest",
          records_seen: 4,
          records_accepted: 3,
          records_rejected: 1,
          mapping_coverage: 75,
          operator_username: "admin",
          error_summary: "1 export issue requires review.",
          dry_run_preview: {},
          export_payload: {},
          started_at: "2026-05-04T09:00:00Z",
          completed_at: "2026-05-04T09:01:00Z",
          created_at: "2026-05-04T09:00:00Z",
          contract_errors: [],
          items: [],
          errors: [],
        },
        active_mapping_version_count: 1,
        active_org_unit_mapping_count: 3,
        failed_run_count: 1,
        audit_failures: [
          {
            key: "required_data_element_mapping_missing",
            title: "Data-element mapping missing for required field",
            status: "FAIL",
            count: 1,
            summary: "Required aggregate export fields must have active external data-element mappings.",
          },
        ],
        source_coverage_warnings: [
          {
            metric_key: "interoperability_mapping_coverage",
            warning: "latest_interoperability_run_not_clean",
            snapshot_key: "run-partial",
            snapshot_date: "2026-05-04",
            status: "PARTIAL",
          },
        ],
      },
    },
    metrics: [],
  };
}

describe("OperationalMetricsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseOperationalMetricsQuery.mockReturnValue({
      data: buildOperationalDashboard(),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });
  });

  it("surfaces interoperability coverage as an operational KPI contract panel", () => {
    render(<OperationalMetricsPage />);

    expect(screen.getByText("Interoperability Contracts")).toBeInTheDocument();
    expect(screen.getByText("75.0%")).toBeInTheDocument();
    expect(screen.getByText("Data-element mapping missing for required field")).toBeInTheDocument();
    expect(screen.getByText(/Aggregate Report Export/)).toBeInTheDocument();
    expect(screen.getByText("Latest Interoperability Run Not Clean")).toBeInTheDocument();
  });
});
