import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InteroperabilityPage from "@/app/(dashboard)/interoperability/page";
import type { InteroperabilityDashboardResponse } from "@/lib/dashboard";

const mockUseInteroperabilityDashboardQuery = vi.fn();
const mockUseInteroperabilityRunDetailMutation = vi.fn();
const mockUseInteroperabilityOrgUnitMappingImportMutation = vi.fn();
const mockUseInteroperabilityExportPreviewMutation = vi.fn();
const mockUseInteroperabilityRetryMutation = vi.fn();
const mockFetchRunDetail = vi.fn();
const mockImport = vi.fn();
const mockExportPreview = vi.fn();
const mockRetry = vi.fn();
const mockRefetch = vi.fn();

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    lastUpdatedLabel,
    lastUpdatedTone,
    children,
  }: {
    title: string;
    subtitle: string;
    lastUpdatedLabel?: string;
    lastUpdatedTone?: string;
    children?: React.ReactNode;
  }) =>
    React.createElement(
      "div",
      null,
      `${title} | ${subtitle} | ${lastUpdatedLabel ?? "no-label"} | ${lastUpdatedTone ?? "no-tone"}`,
      children,
    ),
}));

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock("@/queries/use-interoperability-query", () => ({
  useInteroperabilityDashboardQuery: () => mockUseInteroperabilityDashboardQuery(),
  useInteroperabilityRunDetailMutation: () => mockUseInteroperabilityRunDetailMutation(),
  useInteroperabilityOrgUnitMappingImportMutation: () =>
    mockUseInteroperabilityOrgUnitMappingImportMutation(),
  useInteroperabilityExportPreviewMutation: () => mockUseInteroperabilityExportPreviewMutation(),
  useInteroperabilityRetryMutation: () => mockUseInteroperabilityRetryMutation(),
}));

function buildDashboard(): InteroperabilityDashboardResponse {
  return {
    schema_version: "interoperability-contracts-v1",
    generated_at: "2026-05-04T09:00:00Z",
    exchange_inventory: [
      {
        exchange_type: "ORG_UNIT_MAPPING",
        label: "DHIS2 organisation unit mapping",
        direction: "IMPORT",
        source_owner: "Health records office",
        format: "CSV",
        cadence: "On demand",
        quality_risk: "External codes may be stale.",
        csv_first: true,
      },
      {
        exchange_type: "RISK_SCORE_EXPORT",
        label: "Risk score export",
        direction: "EXPORT",
        source_owner: "CCHIS",
        format: "CSV/API-ready JSON",
        cadence: "Per approved run",
        quality_risk: "Requires active mappings.",
        csv_first: true,
      },
    ],
    csv_templates: {
      org_unit_mapping: {
        filename: "org-unit-mapping.csv",
        columns: [
          "external_identifier",
          "external_display_name",
          "internal_object_type",
          "internal_object_public_id",
          "internal_object_code",
          "mapping_confidence",
          "status",
        ],
        example_row: {
          external_identifier: "OU-001",
          external_display_name: "North Kamagambo",
          internal_object_type: "WARD",
          internal_object_public_id: "ward-public-id",
          internal_object_code: "KE-WARD-1261",
          mapping_confidence: "0.985",
          status: "ACTIVE",
        },
      },
    },
    csv_template_contract_errors: [],
    connector_boundary: {
      schema_version: "interoperability-contracts-v1",
      connector_interface: ["pull_csv", "push_json"],
      auth_config_reference: "settings-managed-secret",
      paging_strategy: "cursor_or_offset",
      retry_policy: {
        max_attempts: 3,
      },
      rate_limit_handling: "backoff_and_retry",
      failure_taxonomy: ["authentication_failed", "mapping_missing", "rate_limited"],
      dry_run_mode: "required_before_confirm",
    },
    connector_boundary_contract_errors: [],
    summary: {
      system_count: 1,
      active_system_count: 1,
      mapping_version_count: 2,
      active_mapping_version_count: 1,
      org_unit_mapping_count: 4,
      active_org_unit_mapping_count: 3,
      run_count: 2,
      failed_run_count: 1,
      latest_run_at: "2026-05-04T08:30:00Z",
      run_status_counts: { FAILED: 1, COMPLETED: 1 },
      audit_status: "fail",
    },
    systems: [{ system_key: "dhis2", display_name: "DHIS2" }],
    mapping_versions: [{ label: "dhis2-v1", status: "ACTIVE" }],
    org_unit_mappings: [
      {
        public_id: "mapping-1",
        system_key: "dhis2",
        mapping_version: "dhis2-v1",
        external_identifier: "OU-001",
        external_display_name: "North Kamagambo",
        internal_object_type: "WARD",
        internal_object_public_id: "ward-public-id",
        internal_object_code: "KE-WARD-1261",
        ward_name: "North Kamagambo",
        facility_name: "",
        mapping_confidence: 0.985,
        status: "ACTIVE",
        effective_date: "2026-05-04",
        retired_date: null,
      },
    ],
    runs: [
      {
        public_id: "run-failed",
        direction: "IMPORT",
        exchange_type: "ORG_UNIT_MAPPING",
        system_key: "dhis2",
        system_name: "DHIS2",
        mapping_version: "dhis2-v1",
        retry_of: null,
        status: "FAILED",
        dry_run: true,
        source_file_name: "org-unit-mapping.csv",
        endpoint_url: "",
        source_reference: "org-unit-mapping.csv",
        records_seen: 2,
        records_accepted: 1,
        records_rejected: 1,
        mapping_coverage: 50,
        operator_username: "admin",
        error_summary: "1 unmapped row requires operator review.",
        dry_run_preview: {
          confirmable: false,
          operator_confirmation_required: true,
          mutation_performed: false,
          next_action: "resolve_unmapped_rows",
          mapping_coverage_report: {
            records_seen: 2,
            records_with_resolved_mapping: 1,
            records_requiring_review: 1,
            coverage_percent: 50,
          },
        },
        export_payload: {},
        started_at: "2026-05-04T08:30:00Z",
        completed_at: "2026-05-04T08:31:00Z",
        created_at: "2026-05-04T08:30:00Z",
        contract_errors: [],
        items: [
          {
            id: 10,
            row_number: 3,
            external_identifier: "OU-404",
            internal_object_type: "WARD",
            internal_object_public_id: "",
            internal_object_code: "MISSING-CODE",
            status: "UNMAPPED",
            action: "NOOP",
            safe_context: {
              external_identifier: "OU-404",
              internal_object_type: "WARD",
              internal_object_code: "MISSING-CODE",
            },
            source_record_ref: "org-unit-mapping.csv:3",
            created_at: "2026-05-04T08:30:30Z",
          },
        ],
        errors: [
          {
            public_id: "error-1",
            item_id: null,
            severity: "ERROR",
            error_code: "mapping_missing",
            field_path: "internal_object_public_id",
            safe_message: "Internal ward was not found.",
            remediation_hint: "Use an active ward public id.",
            created_at: "2026-05-04T08:31:00Z",
          },
        ],
      },
      {
        public_id: "run-completed",
        direction: "EXPORT",
        exchange_type: "RISK_SCORE_EXPORT",
        system_key: "dhis2",
        system_name: "DHIS2",
        mapping_version: "dhis2-v1",
        retry_of: "run-failed",
        status: "COMPLETED",
        dry_run: false,
        source_file_name: "",
        endpoint_url: "cchis://risk-scores/latest",
        source_reference: "cchis://risk-scores/latest",
        records_seen: 1,
        records_accepted: 1,
        records_rejected: 0,
        mapping_coverage: 100,
        operator_username: "admin",
        error_summary: "",
        dry_run_preview: {},
        export_payload: { rows: [] },
        started_at: "2026-05-04T08:40:00Z",
        completed_at: "2026-05-04T08:41:00Z",
        created_at: "2026-05-04T08:40:00Z",
        contract_errors: [],
        items: [],
        errors: [],
      },
    ],
    audit_checks: [
      {
        key: "inactive_org_unit_targets",
        title: "Active mapping to inactive ward/facility",
        status: "FAIL",
        count: 1,
        summary: "1 active mapping points at inactive internal geography.",
      },
      {
        key: "required_data_elements",
        title: "Required risk score data elements",
        status: "PASS",
        count: 0,
        summary: "Required data element mappings are active.",
      },
    ],
  };
}

describe("InteroperabilityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchRunDetail.mockImplementation(async (publicId: string) => {
      const run = buildDashboard().runs.find((item) => item.public_id === publicId);
      return run ?? buildDashboard().runs[0];
    });
    mockImport.mockResolvedValue(buildDashboard().runs[0]);
    mockExportPreview.mockResolvedValue(buildDashboard().runs[0]);
    mockRetry.mockResolvedValue(buildDashboard().runs[0]);
    mockUseInteroperabilityDashboardQuery.mockReturnValue({
      data: buildDashboard(),
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: mockRefetch,
    });
    mockUseInteroperabilityRunDetailMutation.mockReturnValue({
      mutateAsync: mockFetchRunDetail,
      isPending: false,
      error: null,
    });
    mockUseInteroperabilityOrgUnitMappingImportMutation.mockReturnValue({
      mutateAsync: mockImport,
      isPending: false,
    });
    mockUseInteroperabilityExportPreviewMutation.mockReturnValue({
      mutateAsync: mockExportPreview,
      isPending: false,
    });
    mockUseInteroperabilityRetryMutation.mockReturnValue({
      mutateAsync: mockRetry,
      isPending: false,
    });
  });

  it("shows data connection readiness, location matching, transfer review, and plain-language actions", () => {
    render(<InteroperabilityPage />);

    expect(screen.getByText(/Data Connections \| Safely receive files, match locations, and preview data before sharing/i)).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getAllByText("Location matching").length).toBeGreaterThan(0);
    expect(screen.getByText("Active mapping to inactive ward/facility")).toBeInTheDocument();
    expect(screen.getByText("Recent location matches")).toBeInTheDocument();
    expect(screen.getByText(/External ID OU-001/)).toBeInTheDocument();
    expect(screen.getByText("1 unmapped row requires operator review.")).toBeInTheDocument();
    expect(screen.getByText("Internal ward was not found.")).toBeInTheDocument();
    expect(screen.getByText("Transfer review")).toBeInTheDocument();
    expect(screen.getByText("Check result")).toBeInTheDocument();
    expect(screen.getByText("Rows needing review")).toBeInTheDocument();
    expect(screen.getAllByText("OU-404").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MISSING-CODE").length).toBeGreaterThan(0);
    expect(screen.getByText("Fix rows that could not be matched")).toBeInTheDocument();
    expect(screen.getByText("Advanced: available data files")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Download template" })[0]).toHaveAttribute(
      "href",
      "/api/dashboard/interoperability/csv-templates/ward_org_unit_mapping_import",
    );
    expect(screen.getAllByRole("link", { name: "Download rows to fix" })[0]).toHaveAttribute(
      "href",
      "/api/dashboard/interoperability/runs/run-failed/errors.csv",
    );

    expect(screen.queryByText("Connector Boundary")).not.toBeInTheDocument();
    expect(screen.queryByText("CSV Dry-Run")).not.toBeInTheDocument();
    expect(screen.queryByText("Contract Errors")).not.toBeInTheDocument();
  });

  it("submits CSV dry-runs and risk export previews through mutations", async () => {
    render(<InteroperabilityPage />);

    fireEvent.change(screen.getByLabelText("Matching set name"), {
      target: { value: "dhis2-v2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Paste CSV instead" }));
    fireEvent.change(screen.getByLabelText("Location matching CSV"), {
      target: {
        value:
          "external_identifier,external_display_name,internal_object_type,internal_object_public_id,internal_object_code,mapping_confidence,status\nOU-002,Got Kachola,WARD,ward-2,KE-WARD-1262,0.97,ACTIVE\n",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));

    await waitFor(() => {
      expect(mockImport).toHaveBeenCalledWith(
        expect.objectContaining({
          system_key: "dhis2",
          mapping_version_label: "dhis2-v2",
          confirm: false,
          csv_text: expect.stringContaining("OU-002"),
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Preview sharing" }));

    await waitFor(() => {
      expect(mockExportPreview).toHaveBeenCalledWith({
        system_key: "dhis2",
        mapping_version_label: "dhis2-v2",
      });
    });
  });

  it("confirms CSV imports only by referencing the reviewed dry-run", async () => {
    const cleanRun = {
      ...buildDashboard().runs[0],
      public_id: "run-clean",
      status: "READY_FOR_CONFIRMATION" as const,
      records_seen: 1,
      records_accepted: 1,
      records_rejected: 0,
      mapping_coverage: 100,
      error_summary: "",
      dry_run_preview: { confirmable: true, mutation_performed: false },
      items: [],
      errors: [],
    };
    const completedRun = {
      ...cleanRun,
      public_id: "run-confirmed",
      retry_of: "run-clean",
      status: "COMPLETED" as const,
      dry_run: false,
      dry_run_preview: { confirmable: true, mutation_performed: true },
    };
    mockImport.mockResolvedValueOnce(cleanRun).mockResolvedValueOnce(completedRun);
    render(<InteroperabilityPage />);

    fireEvent.click(screen.getByRole("button", { name: "Paste CSV instead" }));
    fireEvent.change(screen.getByLabelText("Location matching CSV"), {
      target: {
        value:
          "external_identifier,external_display_name,internal_object_type,internal_object_public_id,internal_object_code,mapping_confidence,status\nOU-002,Got Kachola,WARD,ward-2,KE-WARD-1262,0.97,ACTIVE\n",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));

    await waitFor(() => {
      expect(mockImport).toHaveBeenCalledWith(expect.objectContaining({ confirm: false }));
    });

    fireEvent.click(screen.getByLabelText("Save approved matches"));
    fireEvent.click(screen.getByRole("button", { name: "Save approved matches" }));

    await waitFor(() => {
      expect(mockImport).toHaveBeenLastCalledWith(
        expect.objectContaining({
          confirm: true,
          retry_of_public_id: "run-clean",
        }),
      );
    });
  });

  it("links failed runs to retry operations", async () => {
    render(<InteroperabilityPage />);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => {
      expect(mockRetry).toHaveBeenCalledWith("run-failed");
    });
  });

  it("loads full run detail when operators select a historical run for review", async () => {
    render(<InteroperabilityPage />);

    fireEvent.click(screen.getAllByRole("button", { name: "Review" })[1]);

    await waitFor(() => {
      expect(mockFetchRunDetail).toHaveBeenCalledWith("run-completed");
    });
    expect(screen.getByText("No rows need review for this transfer.")).toBeInTheDocument();
    expect(screen.getByText("100.0% matched")).toBeInTheDocument();
  });
});
