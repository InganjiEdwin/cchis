import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SourceDataPage from "@/app/(dashboard)/source-data/page";
import type { SourceDataFeedTypesResponse } from "@/lib/dashboard";

const mockUseSourceDataFeedTypesQuery = vi.fn();
const mockUseSourceDataUploadsQuery = vi.fn();
const mockUseSourceDataUploadQuery = vi.fn();
const mockRefetch = vi.fn();

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    children,
  }: {
    title: string;
    subtitle: string;
    children?: React.ReactNode;
  }) =>
    React.createElement(
      "div",
      null,
      `${title} | ${subtitle}`,
      children,
    ),
}));

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/queries/use-source-data-query", () => ({
  useSourceDataFeedTypesQuery: () => mockUseSourceDataFeedTypesQuery(),
  useSourceDataUploadsQuery: () => mockUseSourceDataUploadsQuery(),
  useSourceDataUploadQuery: () => mockUseSourceDataUploadQuery(),
}));

function buildFeedTypes(): SourceDataFeedTypesResponse {
  return {
    schema_version: "source-data-feed-registry-v1",
    phase_contract_schema_version: "source-data-ops-phase0-v1",
    generated_at: "2026-05-05T08:00:00Z",
    scope: "mvp",
    feed_count: 2,
    feeds: [
      {
        feed_key: "surveillance_weekly_aggregate",
        label: "Weekly surveillance aggregate",
        scope: "mvp",
        domain: "health_surveillance",
        backend_target: "ingest_surveillance",
        source_type: "weekly_aggregate",
        cadence: "weekly_minimum",
        ingestion_family: "surveillance",
        downstream_action: "regenerate_surveillance_label_windows_then_rebuild_feature_datasets",
        required_metadata: ["source_name", "source_timestamp"],
        adapter_key: "weekly_surveillance_csv",
        adapter_notes: "Weekly aggregate with explicit reporting period.",
        scheduled_supported: true,
        required_any_columns: [["ward_code"]],
        accepted_columns: ["ward_code", "reporting_period_start", "reporting_period_end", "suspected_cases"],
        template_url: "/source-data/templates/surveillance_weekly_aggregate/",
        requires_new_ingestion_path: false,
        default_reporting_granularity: "week",
        feed_policy: {},
      },
      {
        feed_key: "facility_readiness_snapshot",
        label: "Facility readiness snapshot",
        scope: "mvp",
        domain: "facility_readiness",
        backend_target: "new_readiness_snapshot_ingestion_path",
        source_type: "readiness_snapshot",
        cadence: "weekly_routine_daily_during_alerts",
        ingestion_family: "facility_readiness",
        downstream_action: "recompute_readiness_truth_then_facility_burden_forecast",
        required_metadata: ["source_name", "source_timestamp"],
        adapter_key: "facility_readiness_snapshot_csv",
        adapter_notes: "Canonical readiness CSV path.",
        scheduled_supported: false,
        required_any_columns: [["facility_code"], ["ward_code"]],
        accepted_columns: ["facility_code", "ward_code", "reported_at"],
        template_url: "/source-data/templates/facility_readiness_snapshot/",
        requires_new_ingestion_path: true,
        default_reporting_granularity: "",
        feed_policy: {},
      },
    ],
    templates: {},
    template_contract_errors: [],
  };
}

describe("SourceDataPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSourceDataFeedTypesQuery.mockReturnValue({
      data: buildFeedTypes(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
      isFetching: false,
    });
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 0, results: [] },
      isLoading: false,
      isError: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
  });

  it("renders source-data feed cards with template download links", () => {
    render(<SourceDataPage />);

    expect(screen.getByText("Source Data | Versioned CSV feed contracts and source intake templates")).toBeInTheDocument();
    expect(screen.getAllByText("Weekly surveillance aggregate").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Facility readiness snapshot").length).toBeGreaterThan(0);
    expect(screen.getByText("New Path")).toBeInTheDocument();

    const links = screen.getAllByRole("link", { name: /template/i });
    const hrefs = links.map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/api/dashboard/source-data/templates/surveillance_weekly_aggregate");
    expect(hrefs).toContain("/api/dashboard/source-data/templates/facility_readiness_snapshot");
  });
});
