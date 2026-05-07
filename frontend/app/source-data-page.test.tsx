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

const dashboardMocks = vi.hoisted(() => ({
  runSourceDataDownstreamActionViaBff: vi.fn(),
}));
const mockUseSourceDataFeedTypesQuery = vi.fn();
const mockUseSourceDataOverviewQuery = vi.fn();
const mockUseSourceDataOperationsQuery = vi.fn();
const mockUseSourceDataUploadsQuery = vi.fn();
const mockUseSourceDataUploadQuery = vi.fn();
const mockRefetch = vi.fn();
const mockMutationRecords: Array<{ mutate: ReturnType<typeof vi.fn>; isPending: boolean; error: Error | null }> = [];

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

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    currentUser: {
      id: 1,
      username: "admin",
      full_name: "Admin User",
      role: "ADMIN",
      theme_preference: "LIGHT",
      ward: null,
      ward_name: null,
    },
  }),
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
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
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
    mockUseSourceDataFeedTypesQuery.mockReturnValue({
      data: buildFeedTypes(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
      isFetching: false,
    });
    mockUseSourceDataOverviewQuery.mockReturnValue({
      data: buildOverview(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
      isFetching: false,
    });
    mockUseSourceDataOperationsQuery.mockReturnValue({
      data: buildOperations(),
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

  it("renders a data-readiness workspace with template download links", () => {
    render(<SourceDataPage />);

    expect(screen.getByText("Data Readiness | Check which data is up to date, upload new files, and safely add them to the dashboard")).toBeInTheDocument();
    expect(screen.getByText("What Needs Attention")).toBeInTheDocument();
    expect(screen.getByText("Add Data Safely")).toBeInTheDocument();
    expect(screen.getByText("System Readiness")).toBeInTheDocument();
    expect(screen.getByText("Ready for uploads")).toBeInTheDocument();
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
