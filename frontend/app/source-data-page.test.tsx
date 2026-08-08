import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SourceDataPage from "@/app/(dashboard)/source-data/page";
import type {
  SourceDataFeedTypesResponse,
  SourceDataOperationsResponse,
  SourceDataOverviewResponse,
  SourceDataUploadBatchRecord,
} from "@/lib/dashboard";
import { buildDashboardUser } from "@/test/dashboard-user";

const dashboardMocks = vi.hoisted(() => ({
  runSourceDataDownstreamActionViaBff: vi.fn(),
  invalidateQueries: vi.fn(),
}));
const mockUseSourceDataFeedTypesQuery = vi.fn();
const mockUseSourceDataOverviewQuery = vi.fn();
const mockUseSourceDataOperationsQuery = vi.fn();
const mockUseSourceDataUploadsQuery = vi.fn();
const mockUseSourceDataUploadQuery = vi.fn();
const mockUseAuth = vi.fn();
const mockRefetch = vi.fn();
const mockFeedTypesRefetch = vi.fn();
const mockOverviewRefetch = vi.fn();
const mockOperationsRefetch = vi.fn();
const mockUploadsRefetch = vi.fn();
const mockSelectedUploadRefetch = vi.fn();
const mockMutationRecords: Array<{ mutate: ReturnType<typeof vi.fn>; isPending: boolean; error: Error | null }> = [];

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    onRefresh,
    children,
  }: {
    title: string;
    subtitle: string;
    onRefresh?: () => void;
    children?: React.ReactNode;
  }) =>
    React.createElement(
      "div",
      null,
      `${title} | ${subtitle}`,
      React.createElement("button", { type: "button", "data-testid": "mock-topbar-refresh", onClick: onRefresh }, "Refresh all"),
      children,
    ),
}));

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({
    children,
    pageCapability,
    title,
    message,
  }: {
    children: React.ReactNode;
    pageCapability?: string;
    title: string;
    message: string;
  }) => {
    const currentUser = mockUseAuth().currentUser;
    const hasAccess = pageCapability
      ? Boolean(currentUser?.dashboard_capabilities?.pages?.[pageCapability as "source_data"])
      : true;
    return hasAccess
      ? React.createElement(React.Fragment, null, children)
      : React.createElement("section", null, React.createElement("h3", null, title), React.createElement("p", null, message));
  },
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: { mutationFn?: (value: unknown) => unknown }) => {
    const record = {
      mutate: vi.fn((value: unknown) => options.mutationFn?.(value)),
      isPending: false,
      error: null,
    };
    mockMutationRecords.push(record);
    return record;
  },
  useQueryClient: () => ({ invalidateQueries: dashboardMocks.invalidateQueries }),
}));

vi.mock("@/lib/dashboard", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dashboard")>();
  return {
    ...actual,
    runSourceDataDownstreamActionViaBff: dashboardMocks.runSourceDataDownstreamActionViaBff,
  };
});

vi.mock("@/queries/use-source-data-query", () => ({
  useSourceDataFeedTypesQuery: () => mockUseSourceDataFeedTypesQuery(),
  useSourceDataOverviewQuery: () => mockUseSourceDataOverviewQuery(),
  useSourceDataOperationsQuery: () => mockUseSourceDataOperationsQuery(),
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
        required_metadata: ["source_name", "source_timestamp", "reporting_period_start", "reporting_period_end"],
        adapter_key: "weekly_surveillance_csv",
        adapter_notes: "Weekly aggregate with explicit reporting period.",
        scheduled_supported: true,
        required_any_columns: [["ward_code"]],
        accepted_columns: ["ward_code", "ward_name", "reporting_period_start", "reporting_period_end", "suspected_cases"],
        template_url: "/source-data/templates/surveillance_weekly_aggregate/",
        requires_new_ingestion_path: false,
        default_reporting_granularity: "week",
        feed_policy: {},
        feed_mode: "csv",
        csv_upload_enabled: true,
        connector_status: {
          enabled: true,
          connector_key: "dhis2_surveillance_weekly",
          label: "DHIS2 weekly surveillance",
          configured: true,
          status: "configured",
          last_run_status: "success",
          last_run_at: "2026-05-05T08:00:00Z",
          last_successful_fetch_at: "2026-05-05T08:00:00Z",
          required_settings: ["SOURCE_DATA_DHIS2_BASE_URL"],
          credential_values_exposed: false,
          notes: "Routine weekly source refresh.",
        },
      },
      {
        feed_key: "facility_readiness_snapshot",
        label: "Facility readiness snapshot",
        scope: "mvp",
        domain: "facility_readiness",
        backend_target: "ingest_facility_readiness_snapshot",
        source_type: "readiness_snapshot",
        cadence: "weekly_routine_daily_during_alerts",
        ingestion_family: "facility_readiness",
        downstream_action: "recompute_readiness_truth_then_facility_burden_forecast",
        required_metadata: ["source_name", "source_timestamp"],
        adapter_key: "facility_readiness_snapshot_csv",
        adapter_notes: "Canonical readiness CSV path.",
        scheduled_supported: false,
        required_any_columns: [["facility_code"], ["ward_code"]],
        accepted_columns: ["facility_code", "ward_code", "ward_name", "reported_at"],
        template_url: "/source-data/templates/facility_readiness_snapshot/",
        requires_new_ingestion_path: false,
        default_reporting_granularity: "",
        feed_policy: {},
      },
    ],
    templates: {},
    template_contract_errors: [],
  };
}

function buildOverview(): SourceDataOverviewResponse {
  const sources = [
    {
      key: "system:rainfall",
      feed_key: "",
      label: "Rainfall forecast",
      domain: "climate",
      source_type: "rainfall",
      status: "current" as const,
      truth_state: "api_backed",
      expected_cadence: "daily_where_available",
      last_source_timestamp: "2026-05-05T08:00:00Z",
      last_import_timestamp: "2026-05-05T08:05:00Z",
      current_gap_days: 0,
      record_count: 40,
      recommended_action: "No immediate action required.",
      source_path: "scheduled_api",
    },
    {
      key: "feed:facility_readiness_snapshot",
      feed_key: "facility_readiness_snapshot",
      label: "Facility readiness snapshot",
      domain: "facility_readiness",
      source_type: "readiness_snapshot",
      status: "missing" as const,
      truth_state: "missing",
      expected_cadence: "weekly_routine_daily_during_alerts",
      last_source_timestamp: null,
      last_import_timestamp: null,
      current_gap_days: null,
      record_count: 0,
      recommended_action: "Download the template and upload Facility readiness snapshot.",
      source_path: "new_ingestion_path_required",
    },
  ];

  return {
    schema_version: "source-data-overview-v1",
    generated_at: "2026-05-05T08:10:00Z",
    freshness: {
      schema_version: "source-data-freshness-v1",
      generated_at: "2026-05-05T08:10:00Z",
      state_counts: { current: 1, missing: 1 },
      truth_state_counts: { api_backed: 1, missing: 1 },
      upload_status_counts: {},
      sources,
    },
    feed_statuses: [sources[1]],
    source_gaps: [
      {
        feed_key: "facility_readiness_snapshot",
        label: "Facility readiness snapshot",
        status: "missing",
        truth_state: "missing",
        recommended_action: "Download the template and upload Facility readiness snapshot.",
        template_url: "/source-data/templates/facility_readiness_snapshot/",
      },
    ],
    recent_uploads: [],
    source_matrix_reference: "docs/CCHIS_DATA_SOURCE_FEEDS.md",
  };
}

function buildOperations(): SourceDataOperationsResponse {
  return {
    schema_version: "source-data-operations-v1",
    generated_at: "2026-05-05T08:15:00Z",
    lookback_hours: 24,
    metrics: {
      upload_count: 2,
      recent_upload_count: 1,
      validation_failure_count: 0,
      import_failure_count: 0,
      stale_feed_count: 1,
      duplicate_attempt_count: 0,
      status_counts: { imported: 1 },
    },
    worker_health: {
      status: "current",
      latest_heartbeat_at: "2026-05-05T08:14:00Z",
      latest_task_name: "risk.tasks.record_etl_heartbeat_task",
      latest_status: "OK",
      age_seconds: 60,
      stale_after_seconds: 1800,
    },
    stuck_tasks: {
      stale_after_minutes: 30,
      imports: [],
      validations: [],
    },
    retention: {
      raw_upload_retention_days: 60,
      expired_raw_artifact_count: 0,
      purged_artifact_count: 0,
      next_artifact_expiry_at: "2026-07-04T08:00:00Z",
      cleanup_task_name: "risk.tasks.cleanup_source_data_upload_artifacts_task",
    },
    alerts: [],
    production_controls: {
      backup_restore_reference: "docs/SOURCE_DATA_PRODUCTION_RUNBOOK.md",
      antivirus_scanning_hook: "deployment_ingress_or_object_storage_hook_required_before_pilot_if_policy_requires_av",
      audit_review_reference: "Review source-data upload events weekly.",
    },
  };
}

function buildImportedUpload(): SourceDataUploadBatchRecord {
  return {
    public_id: "4eb3cb9f-55ce-4e91-a572-52db3f9b2a40",
    feed_key: "surveillance_weekly_aggregate",
    domain: "health_surveillance",
    source_type: "weekly_aggregate",
    source_name: "Migori DHIS2 weekly export",
    source_ref: "dhis2-week-18",
    source_timestamp: "2026-05-04T08:00:00Z",
    release_version: "",
    reporting_period_start: "2026-04-27",
    reporting_period_end: "2026-05-04",
    correction_mode: "",
    replacement_reason: "",
    operator_note: "",
    status: "imported",
    validation_status: "passed",
    import_status: "imported",
    row_count: 1,
    accepted_count: 1,
    rejected_count: 0,
    warning_count: 0,
    duplicate_of_public_id: null,
    replaces_upload_public_id: null,
    approval_status: "not_required",
    approval_risk_category: "low",
    approval_requested_by_username: null,
    approval_requested_at: null,
    approved_by_username: null,
    approved_at: null,
    approval_reason: "",
    approval_expires_at: null,
    validation_celery_task_id: "",
    import_celery_task_id: "",
    downstream_celery_task_id: "",
    domain_ingestion_run_type: "surveillance",
    domain_ingestion_run_id: 7,
    surveillance_ingestion_run: 7,
    population_exposure_ingestion_run: null,
    facility_readiness_ingestion_run_id: null,
    created_by_username: "source-data-supervisor",
    confirmed_by_username: "source-data-supervisor",
    confirmed_at: "2026-05-05T08:30:00Z",
    metadata: {},
    validation_summary: {},
    downstream_actions: [
      {
        action_key: "regenerate_surveillance_labels",
        label: "Regenerate surveillance labels",
        supported_ingestion_families: ["surveillance"],
        safe_reason: "Uses only canonical surveillance records created on or before the action snapshot time.",
        mutates_downstream_evidence: true,
        triggers_sms: false,
        promotes_model: false,
        availability_status: "available",
        unavailable_reason: "",
        recommended: true,
        latest_result: null,
      },
    ],
    validation_issues: [],
    events: [],
    created_at: "2026-05-05T08:00:00Z",
    updated_at: "2026-05-05T08:30:00Z",
  };
}

describe("SourceDataPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    dashboardMocks.runSourceDataDownstreamActionViaBff.mockResolvedValue({
      schema_version: "source-data-downstream-actions-v1",
      action_key: "regenerate_surveillance_labels",
      action_label: "Regenerate surveillance labels",
      action_status: "completed",
      requested_by_username: "admin",
      started_at: "2026-05-05T08:31:00Z",
      completed_at: "2026-05-05T08:32:00Z",
      worker_execution: false,
      safe_reason: "Safe cutoff evidence.",
      triggers_sms: false,
      promotes_model: false,
      evidence: {},
      batch: buildImportedUpload(),
    });
    mockMutationRecords.length = 0;
    mockUseAuth.mockReturnValue({
      currentUser: buildDashboardUser("ADMIN", {
        username: "admin",
        email: "admin@example.com",
        full_name: "Admin User",
        theme_preference: "LIGHT",
        ward: null,
        ward_name: null,
      }),
    });
    mockUseSourceDataFeedTypesQuery.mockReturnValue({
      data: buildFeedTypes(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockFeedTypesRefetch,
      isFetching: false,
    });
    mockUseSourceDataOverviewQuery.mockReturnValue({
      data: buildOverview(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockOverviewRefetch,
      isFetching: false,
    });
    mockUseSourceDataOperationsQuery.mockReturnValue({
      data: buildOperations(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockOperationsRefetch,
      isFetching: false,
    });
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 0, results: [] },
      isLoading: false,
      isError: false,
      refetch: mockUploadsRefetch,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: mockSelectedUploadRefetch,
    });
  });

  it("renders a data-readiness workspace with template download links", () => {
    render(<SourceDataPage />);

    expect(screen.getByText("Data Readiness | Check which data is up to date, upload new files, and safely add them to the dashboard")).toBeInTheDocument();
    expect(screen.getByText("What Needs Attention")).toBeInTheDocument();
    expect(screen.getByText("Add Data Safely")).toBeInTheDocument();
    expect(screen.getByText("Source Data Operations")).toBeInTheDocument();
    expect(screen.getByText("Degraded/review needed")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /review update/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /templates/i })).toBeInTheDocument();
    expect(screen.queryByText("Weekly surveillance aggregate")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /templates/i }));

    expect(screen.getAllByText("Weekly surveillance aggregate").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Facility readiness snapshot").length).toBeGreaterThan(0);
    expect(screen.getByText("The downloaded file already lists all 40 Migori wards. Fill the blank cells for each ward.")).toBeInTheDocument();
    expect(screen.getByText("Ward name sits beside ward code so the file is easier to check before upload.")).toBeInTheDocument();
    expect(screen.queryByText("New Path")).not.toBeInTheDocument();
    expect(screen.queryByText("Production Health")).not.toBeInTheDocument();
    expect(screen.queryByText("Worker Current")).not.toBeInTheDocument();

    const links = screen.getAllByRole("link", { name: /download template/i });
    const hrefs = links.map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/api/dashboard/source-data/templates/surveillance_weekly_aggregate");
    expect(hrefs).toContain("/api/dashboard/source-data/templates/facility_readiness_snapshot");
    expect(screen.getByRole("button", { name: /pause manual upload/i })).toBeEnabled();
  });

  it("surfaces backend feed provenance, freshness and connector evidence", () => {
    const overview = buildOverview();
    overview.freshness.sources.push({
      ...overview.freshness.sources[0],
      key: "feed:surveillance_weekly_aggregate",
      feed_key: "surveillance_weekly_aggregate",
      label: "Weekly surveillance aggregate",
      domain: "health_surveillance",
      source_type: "weekly_aggregate",
      status: "current",
      truth_state: "csv_backed",
      expected_cadence: "weekly_minimum",
      last_source_timestamp: "2026-05-05T08:00:00Z",
      recommended_action: "No immediate action required for the weekly file.",
    });
    mockUseSourceDataOverviewQuery.mockReturnValue({
      data: overview,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
      isFetching: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /sources & templates/i }));

    expect(screen.getAllByText("Source truth").length).toBeGreaterThan(0);
    expect(screen.getByText("Manual file")).toBeInTheDocument();
    expect(screen.getAllByText("Up to date").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Last source timestamp").length).toBeGreaterThan(0);
    expect(screen.getByText("Automatic update: DHIS2 weekly surveillance")).toBeInTheDocument();
    expect(screen.getByText("Enabled")).toBeInTheDocument();
    expect(screen.getByText("Configured")).toBeInTheDocument();
    expect(screen.getByText("Last run status: Updated")).toBeInTheDocument();
    expect(screen.getAllByText("No immediate action required for the weekly file.").length).toBeGreaterThan(0);
  });

  it("keeps unconfigured and demo-backed feeds truthfully labelled", () => {
    const response = buildFeedTypes();
    response.feeds = [
      {
        ...response.feeds[0],
        feed_key: "unconfigured_surveillance",
        label: "Unconfigured surveillance feed",
        feed_mode: "api",
        connector_status: {
          ...response.feeds[0].connector_status!,
          connector_key: "dhis2_unconfigured",
          configured: false,
          status: "not_configured",
          last_run_status: "skipped",
        },
      },
      {
        ...response.feeds[1],
        feed_key: "demo_facility_feed",
        label: "Demo facility feed",
        feed_mode: "demo",
        csv_upload_enabled: false,
        connector_status: undefined,
      },
    ];
    mockUseSourceDataFeedTypesQuery.mockReturnValue({
      data: response,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockFeedTypesRefetch,
      isFetching: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /sources & templates/i }));

    expect(screen.getByText("Needs setup")).toBeInTheDocument();
    expect(screen.getByText("Not configured")).toBeInTheDocument();
    expect(screen.getAllByText("Demo data").length).toBeGreaterThan(0);
    expect(screen.getByText("Connector: Not registered")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pause manual upload/i })).toBeDisabled();
  });

  it("renders partial feed metadata without undefined values or crashes", () => {
    const response = buildFeedTypes();
    response.feed_count = 1;
    response.feeds = [
      {
        ...response.feeds[0],
        feed_key: undefined,
        label: undefined,
        domain: undefined,
        adapter_notes: undefined,
        downstream_action: undefined,
        accepted_columns: undefined,
        required_metadata: undefined,
        feed_mode: undefined,
        csv_upload_enabled: undefined,
        connector_status: undefined,
      },
    ] as unknown as SourceDataFeedTypesResponse["feeds"];
    mockUseSourceDataFeedTypesQuery.mockReturnValue({
      data: response,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockFeedTypesRefetch,
      isFetching: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /sources & templates/i }));

    expect(screen.getByText("Unnamed data feed")).toBeInTheDocument();
    expect(screen.getAllByText("Unclassified").length).toBeGreaterThan(0);
    expect(screen.getByText("No required metadata returned.")).toBeInTheDocument();
    expect(screen.getByText("Template not available")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^add data$/i }));
    expect(screen.getByLabelText("Data type")).toBeInTheDocument();
    expect(screen.queryByText("undefined")).not.toBeInTheDocument();
    expect(screen.queryByText("NaN")).not.toBeInTheDocument();
  });

  it("keeps operations failure scoped to its panel and does not claim overall production health", () => {
    mockUseSourceDataOperationsQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Operations endpoint unavailable"),
      refetch: mockRefetch,
      isFetching: false,
    });

    render(<SourceDataPage />);

    expect(screen.getByText("Source Data Operations")).toBeInTheDocument();
    expect(screen.getByText("Operations endpoint unavailable")).toBeInTheDocument();
    expect(screen.getByText("Unavailable / not loaded")).toBeInTheDocument();
    expect(screen.getByText("What Needs Attention")).toBeInTheDocument();
    expect(screen.queryByText(/production health/i)).not.toBeInTheDocument();
  });

  it("shows healthy only when the backend heartbeat is current and blocking counts are clear", () => {
    const operations = buildOperations();
    operations.metrics.stale_feed_count = 0;
    mockUseSourceDataOperationsQuery.mockReturnValue({
      data: operations,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
      isFetching: false,
    });

    render(<SourceDataPage />);

    expect(screen.getByText("Healthy/current")).toBeInTheDocument();
    expect(screen.queryByText("Ready for uploads")).not.toBeInTheDocument();
  });

  it("treats partial operations evidence as degraded instead of green", () => {
    const operations = { ...buildOperations(), metrics: undefined } as unknown as SourceDataOperationsResponse;
    mockUseSourceDataOperationsQuery.mockReturnValue({
      data: operations,
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
      isFetching: false,
    });

    render(<SourceDataPage />);

    expect(screen.getByText("Degraded/review needed")).toBeInTheDocument();
    expect(screen.queryByText("Healthy/current")).not.toBeInTheDocument();
  });

  it("never reports healthy when any required operations metric is missing", () => {
    const requiredMetricKeys = [
      "upload_count",
      "recent_upload_count",
      "validation_failure_count",
      "import_failure_count",
      "stale_feed_count",
      "duplicate_attempt_count",
      "status_counts",
    ];

    for (const metricKey of requiredMetricKeys) {
      const operations = buildOperations();
      const metrics = { ...operations.metrics } as Record<string, unknown>;
      delete metrics[metricKey];
      mockUseSourceDataOperationsQuery.mockReturnValue({
        data: { ...operations, metrics } as unknown as SourceDataOperationsResponse,
        isLoading: false,
        isError: false,
        error: null,
        refetch: mockOperationsRefetch,
        isFetching: false,
      });

      const view = render(<SourceDataPage />);
      expect(screen.getByText("Degraded/review needed"), metricKey).toBeInTheDocument();
      expect(screen.queryByText("Healthy/current"), metricKey).not.toBeInTheDocument();
      view.unmount();
    }
  });

  it("refreshes the feed registry, overview, operations and upload queries together", () => {
    const upload = buildImportedUpload();
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 1, results: [upload] },
      isLoading: false,
      isError: false,
      refetch: mockUploadsRefetch,
      isFetching: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: upload,
      isLoading: false,
      isError: false,
      refetch: mockSelectedUploadRefetch,
      isFetching: false,
    });

    render(<SourceDataPage />);

    fireEvent.click(screen.getByTestId("mock-topbar-refresh"));

    expect(dashboardMocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["source-data"] });
    expect(mockFeedTypesRefetch).toHaveBeenCalledTimes(1);
    expect(mockOverviewRefetch).toHaveBeenCalledTimes(1);
    expect(mockOperationsRefetch).toHaveBeenCalledTimes(1);
    expect(mockUploadsRefetch).toHaveBeenCalledTimes(1);
    expect(mockSelectedUploadRefetch).toHaveBeenCalledTimes(1);
  });

  it("renders safe downstream actions after an imported upload", () => {
    const upload = buildImportedUpload();
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 1, results: [upload] },
      isLoading: false,
      isError: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: upload,
      isLoading: false,
      isError: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /review update/i }));

    expect(screen.getByText("Dashboard use")).toBeInTheDocument();
    expect(screen.getByText("This file is already used by the dashboard.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /use this file on dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Reason for cancelling")).not.toBeInTheDocument();
    expect(screen.getByText("Related dashboard updates")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download full error csv/i })).toBeInTheDocument();
    expect(screen.getByText("Daily refresh 06:00")).toBeInTheDocument();
    expect(screen.getByText("No messages sent")).toBeInTheDocument();
    expect(screen.getByText("No risk score changes")).toBeInTheDocument();
    expect(screen.getByText("Refresh surveillance summaries")).toBeInTheDocument();
    expect(screen.getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByText(/Updates the related surveillance view/)).toBeInTheDocument();
  });

  it("runs downstream actions with sourceCutoffTimestampForUpload instead of browser time", () => {
    const upload = buildImportedUpload();
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 1, results: [upload] },
      isLoading: false,
      isError: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: upload,
      isLoading: false,
      isError: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /review update/i }));
    fireEvent.click(screen.getByRole("button", { name: /^update$/i }));

    expect(dashboardMocks.runSourceDataDownstreamActionViaBff).toHaveBeenCalledWith(
      upload.public_id,
      expect.objectContaining({
        action_key: "regenerate_surveillance_labels",
        as_of: "2026-05-04T08:00:00.000Z",
      }),
    );
  });

  it("renders readiness-specific validation summary", () => {
    const upload = {
      ...buildImportedUpload(),
      feed_key: "facility_readiness_snapshot",
      domain: "facility_readiness",
      source_type: "readiness_snapshot",
      metadata: {
        validation_summary: {
          readiness_summary: {
            facility_coverage_percent: 85,
            facilities_reported: 17,
            stale_report_count: 2,
            stockout_facility_count: 3,
            service_disruption_count: 1,
          },
        },
      },
      downstream_actions: [],
    };
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 1, results: [upload] },
      isLoading: false,
      isError: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: upload,
      isLoading: false,
      isError: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /review update/i }));

    expect(screen.getByText("Facility Coverage")).toBeInTheDocument();
    expect(screen.getByText("85% facilities")).toBeInTheDocument();
    expect(screen.getByText("Old reports")).toBeInTheDocument();
    expect(screen.getByText("Disruptions")).toBeInTheDocument();
  });

  it("does not render undefined, NaN or misleading zero values for missing validation fields", () => {
    const upload = {
      ...buildImportedUpload(),
      status: "validation_failed" as const,
      validation_status: "failed" as const,
      row_count: undefined,
      accepted_count: undefined,
      rejected_count: undefined,
      warning_count: undefined,
      validation_issues: [],
    };
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 1, results: [upload] },
      isLoading: false,
      isError: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: upload,
      isLoading: false,
      isError: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /review update/i }));

    expect(screen.getAllByText("Not available").length).toBeGreaterThan(0);
    expect(screen.queryByText("undefined")).not.toBeInTheDocument();
    expect(screen.queryByText("NaN")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download full error csv/i })).toBeInTheDocument();
  });

  it("validates required fields and rejected files before upload", () => {
    render(<SourceDataPage />);

    fireEvent.click(screen.getAllByRole("button", { name: /add data/i })[0]);
    fireEvent.click(screen.getByRole("button", { name: /upload file/i }));

    expect(screen.getByText("Enter where this file came from.")).toBeInTheDocument();
    expect(screen.getByText("Choose the file date and time.")).toBeInTheDocument();
    expect(screen.getByText("Choose a file saved from the template.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/file/i, { selector: "input[type='file']" }), {
      target: {
        files: [
          new File(["not,csv"], "weekly.xlsx", {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: /upload file/i }));

    expect(screen.getByText("Choose a .csv file. Save Excel workbooks as CSV before upload.")).toBeInTheDocument();
    expect(mockMutationRecords.every((record) => record.mutate.mock.calls.length === 0)).toBe(true);
  });

  it("lets analysts inspect templates and current status without upload controls", () => {
    mockUseAuth.mockReturnValue({
      currentUser: buildDashboardUser("ANALYST", {
        username: "analyst",
        email: "analyst@example.com",
        full_name: "Analyst User",
        theme_preference: "LIGHT",
        ward: null,
        ward_name: null,
      }),
    });

    render(<SourceDataPage />);

    expect(screen.getByText("Data Readiness | Check which data is up to date, upload new files, and safely add them to the dashboard")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add data/i })).not.toBeInTheDocument();
    expect(screen.getByText("Download templates and review current data status. Uploads are limited to operational data managers.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /templates/i }));

    expect(screen.getAllByRole("link", { name: /download template/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /upload file/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pause manual upload/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /allow manual upload/i })).not.toBeInTheDocument();
  });

  it("denies CHV access to the Source Data workspace", () => {
    mockUseAuth.mockReturnValue({
      currentUser: buildDashboardUser("CHV", {
        username: "chv",
        email: "chv@example.com",
        full_name: "Community Health Volunteer",
        theme_preference: "LIGHT",
        ward: 7,
        ward_name: "North Kadem",
      }),
    });

    render(<SourceDataPage />);

    expect(screen.getByText("Data readiness access is restricted")).toBeInTheDocument();
    expect(screen.queryByText("Source Data Operations")).not.toBeInTheDocument();
    expect(screen.queryByText("Data Readiness | Check which data is up to date, upload new files, and safely add them to the dashboard")).not.toBeInTheDocument();
  });

  it("lets supervisors request risky source-data review without admin approval controls", () => {
    const upload = {
      ...buildImportedUpload(),
      status: "ready_for_confirmation" as const,
      validation_status: "passed" as const,
      import_status: "not_started" as const,
      approval_status: "pending" as const,
      approval_risk_category: "high" as const,
      downstream_actions: [],
    };
    mockUseAuth.mockReturnValue({
      currentUser: buildDashboardUser("SUPERVISOR", {
        username: "supervisor",
        email: "supervisor@example.com",
        full_name: "Field Supervisor",
        theme_preference: "LIGHT",
        ward: 7,
        ward_name: "North Kadem",
      }),
    });
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 1, results: [upload] },
      isLoading: false,
      isError: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: upload,
      isLoading: false,
      isError: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /review update/i }));

    expect(screen.getByText("This file needs review before dashboard use.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /request review/i })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /mark reviewed/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reject$/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /templates/i }));

    expect(screen.getByText("Automatic update: DHIS2 weekly surveillance")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pause manual upload/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /allow manual upload/i })).not.toBeInTheDocument();
  });

  it("applies last-used metadata and submits a clean upload payload", () => {
    const upload = buildImportedUpload();
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 1, results: [upload] },
      isLoading: false,
      isError: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: upload,
      isLoading: false,
      isError: false,
    });
    render(<SourceDataPage />);

    fireEvent.click(screen.getAllByRole("button", { name: /add data/i })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Use last details" }));
    expect(screen.getByLabelText("Where did this file come from?")).toHaveValue("Migori DHIS2 weekly export");

    const csvFile = new File(
      [
        "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,diarrheal_count,reporting_granularity,source_ref\n",
        "MIG-WARD-001,2026-04-27,2026-05-03,3,1,8,week,dhis2-weekly-export:row-1\n",
      ],
      "weekly.csv",
      { type: "text/csv" },
    );
    fireEvent.change(screen.getByLabelText(/file/i, { selector: "input[type='file']" }), { target: { files: [csvFile] } });
    fireEvent.click(screen.getByRole("button", { name: /upload file/i }));

    const uploadMutationCall = mockMutationRecords
      .flatMap((record) => record.mutate.mock.calls)
      .find(([payload]) => payload?.feed_key === "surveillance_weekly_aggregate");
    expect(uploadMutationCall?.[0]).toEqual(
      expect.objectContaining({
        feed_key: "surveillance_weekly_aggregate",
        source_name: "Migori DHIS2 weekly export",
        reporting_period_start: "2026-04-27",
        reporting_period_end: "2026-05-04",
        file: csvFile,
      }),
    );
  });

  it("keeps failed imports visible with actionable status context", () => {
    const upload = {
      ...buildImportedUpload(),
      status: "import_failed" as const,
      import_status: "failed" as const,
      metadata: {
        import_summary: {
          error_summary: "Import failed because a referenced ward is missing.",
        },
      },
    };
    mockUseSourceDataUploadsQuery.mockReturnValue({
      data: { schema_version: "source-data-upload-batch-list-v1", count: 1, results: [upload] },
      isLoading: false,
      isError: false,
    });
    mockUseSourceDataUploadQuery.mockReturnValue({
      data: upload,
      isLoading: false,
      isError: false,
    });

    render(<SourceDataPage />);
    fireEvent.click(screen.getByRole("tab", { name: /review update/i }));

    expect(screen.getByText("Import failed because a referenced ward is missing.")).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Data update progress")).toBeInTheDocument();
    expect(screen.getByText("Reason for cancelling")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel update/i })).toBeDisabled();
  });
});
