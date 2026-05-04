import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChvsPage from "@/app/(dashboard)/chvs/page";

const mockUseAuth = vi.fn();
const mockUseChvOperationsQuery = vi.fn();
const mockUseCreateChvCoverageRequestMutation = vi.fn();
const mockUseAssignChvCoverageRequestMutation = vi.fn();
const mockUseChvCoverageRequestDetailQuery = vi.fn();
const mockUseChvActivityQuery = vi.fn();
const mockUseChvMessagesQuery = vi.fn();
const mockUseCreateChvMessageMutation = vi.fn();

function buildChv(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    public_id: "chv-1",
    ward: 12,
    ward_name: "North Kamagambo",
    name: "Akinyi Omondi",
    phone_number: "+254700000001",
    language: "Kiswahili",
    operational_status: "ACTIVE",
    sync_health: "ONLINE",
    created_at: "2026-04-28T08:00:00Z",
    last_activity_at: "2026-04-28T09:00:00Z",
    last_sync_at: "2026-04-28T09:10:00Z",
    triage_sessions_24h: 2,
    referrals_24h: 1,
    ward_alerts_total: 3,
    ward_alerts_delivered: 2,
    can_message: true,
    message_mode: "SEND",
    message_delivery_kind: "SIMULATED",
    can_view_activity: true,
    ...overrides,
  };
}

function buildFeature(overrides: Record<string, unknown> = {}) {
  return {
    type: "Feature",
    geometry: null,
    properties: {
      name: "North Kamagambo",
      ward_code: "KE-WARD-1261",
      backend_ward_id: 12,
      has_backend_ward: true,
      active_chv_count: 1,
      chv_count: 2,
      risk_level: "HIGH",
      predicted_cases: 12,
      alert_count: 2,
      facility_count: 1,
      ...overrides,
    },
  };
}

function buildOfflineMonitoring(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "chv-offline-monitoring-v1",
    generated_at: "2026-04-28T09:15:00Z",
    scope: {
      ward_ids: [12, 13],
      ward_count: 2,
      window_hours: 24,
      audit_window_days: 7,
    },
    metrics: {
      registered_chv_devices: 3,
      active_chv_devices: 2,
      successful_syncs_24h: 8,
      failed_syncs_24h: 1,
      pre_validation_rejections_24h: 1,
      pending_uploads: 2,
      stale_guidance_bundles: 1,
      conflict_count_7d: 1,
      offline_task_completion_latency_minutes: 42,
    },
    audit_checks: [
      {
        key: "out_of_assignment_data",
        title: "CHV data outside assignment",
        status: "PASS",
        count: 0,
        summary: "No offline CHV action audit events were outside the actor assignment.",
        sample_records: [],
      },
      {
        key: "repeated_rejected_uploads",
        title: "Repeated rejected uploads",
        status: "WARN",
        count: 1,
        summary: "1 rejected upload came from devices crossing the repeat threshold.",
        sample_records: [{ source_device_id: "field-device-003", rejected_count: 1 }],
      },
      {
        key: "pre_validation_rejections",
        title: "Rejected before sync persistence",
        status: "WARN",
        count: 1,
        summary: "1 CHV sync submission was rejected before sync persistence.",
        sample_records: [{ source_device_id: "field-device-prevalidation", rejection_stage: "PII_MINIMIZATION" }],
      },
    ],
    sync_health_by_ward: [
      {
        ward_id: 12,
        ward_name: "North Kamagambo",
        registered_device_count: 2,
        active_device_count: 1,
        successful_syncs_24h: 6,
        pending_upload_count: 1,
        failed_upload_count_24h: 1,
        pre_validation_rejection_count_24h: 1,
        conflict_count_7d: 1,
        last_successful_sync_at: "2026-04-28T09:10:00Z",
        sync_health: "DELAYED",
      },
      {
        ward_id: 13,
        ward_name: "Got Kachola",
        registered_device_count: 1,
        active_device_count: 1,
        successful_syncs_24h: 2,
        pending_upload_count: 0,
        failed_upload_count_24h: 0,
        pre_validation_rejection_count_24h: 0,
        conflict_count_7d: 0,
        last_successful_sync_at: "2026-04-28T09:00:00Z",
        sync_health: "ONLINE",
      },
    ],
    recent_sync_decisions: [
      {
        id: 14,
        created_at: "2026-04-28T09:12:00Z",
        processed_at: "2026-04-28T09:12:30Z",
        ward_id: 12,
        ward_name: "North Kamagambo",
        upload_type: "prevention_visit",
        status: "PROCESSED",
        decision: "ACCEPTED",
        conflict_state: "NONE",
        client_submission_id: "visit-001",
        idempotency_key: "visit-idem-001",
        download_bundle_version: "bundle-current",
        domain_record: { type: "preparedness_action" },
        explanation: "Accepted prevention_visit and linked it to preparedness_action.",
      },
      {
        id: 13,
        created_at: "2026-04-28T09:11:00Z",
        processed_at: "2026-04-28T09:11:30Z",
        ward_id: 12,
        ward_name: "North Kamagambo",
        upload_type: "task_ack",
        status: "FAILED",
        decision: "REJECTED",
        conflict_state: "SCOPE_MISMATCH",
        client_submission_id: "ack-001",
        idempotency_key: "ack-idem-001",
        download_bundle_version: "bundle-old",
        domain_record: {},
        explanation: "Preparedness action not found.",
      },
    ],
    recent_rejected_submission_audits: [
      {
        public_id: "audit-prevalidation-1",
        created_at: "2026-04-28T09:13:00Z",
        ward_id: 12,
        ward_name: "North Kamagambo",
        source_device_id: "field-device-prevalidation",
        client_submission_id: "unsafe-001",
        idempotency_key: "unsafe-idem-001",
        upload_type: "symptom_triage",
        contract_version: "chv-offline-v1",
        rejection_stage: "PII_MINIMIZATION",
        error_code: "chv_offline_pii_minimization_failed",
        safe_error_summary: "Rejected before sync persistence during pii_minimization.",
        field_paths: ["uploads.0.payload.household_name"],
        status_code: 400,
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

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock("@/components/migori-ward-map", () => ({
  MigoriWardMap: ({
    features,
    onSelectWard,
  }: {
    features: Array<{ properties: { name: string } }>;
    onSelectWard?: (feature: { properties: { name: string } }) => void;
  }) =>
    React.createElement(
      "div",
      null,
      features.map((feature) =>
        React.createElement(
          "button",
          {
            key: feature.properties.name,
            type: "button",
            onClick: () => onSelectWard?.(feature),
          },
          `Select ${feature.properties.name}`,
        ),
      ),
    ),
}));

vi.mock("@/queries/use-chv-operations-query", () => ({
  useChvOperationsQuery: (...args: unknown[]) => mockUseChvOperationsQuery(...args),
}));

vi.mock("@/queries/use-create-chv-coverage-request-mutation", () => ({
  useCreateChvCoverageRequestMutation: (...args: unknown[]) => mockUseCreateChvCoverageRequestMutation(...args),
}));

vi.mock("@/queries/use-assign-chv-coverage-request-mutation", () => ({
  useAssignChvCoverageRequestMutation: (...args: unknown[]) => mockUseAssignChvCoverageRequestMutation(...args),
}));

vi.mock("@/queries/use-chv-coverage-request-detail-query", () => ({
  useChvCoverageRequestDetailQuery: (...args: unknown[]) => mockUseChvCoverageRequestDetailQuery(...args),
}));

vi.mock("@/queries/use-chv-activity-query", () => ({
  useChvActivityQuery: (...args: unknown[]) => mockUseChvActivityQuery(...args),
}));

vi.mock("@/queries/use-chv-messages-query", () => ({
  useChvMessagesQuery: (...args: unknown[]) => mockUseChvMessagesQuery(...args),
}));

vi.mock("@/queries/use-create-chv-message-mutation", () => ({
  useCreateChvMessageMutation: (...args: unknown[]) => mockUseCreateChvMessageMutation(...args),
}));

describe("ChvsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

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

    mockUseChvOperationsQuery.mockReturnValue({
      data: {
        chvs: [
          buildChv(),
          buildChv({
            id: 2,
            ward: 12,
            name: "Brian Ooko",
            operational_status: "OFFLINE",
            sync_health: "OFFLINE",
            last_sync_at: null,
          }),
          buildChv({
            id: 3,
            ward: 13,
            ward_name: "Got Kachola",
            name: "Clare Auma",
            operational_status: "IDLE",
            sync_health: "DELAYED",
            triage_sessions_24h: 0,
            last_sync_at: "2026-04-27T06:00:00Z",
          }),
        ],
        latestRisks: [
          {
            ward_id: 12,
            ward_name: "North Kamagambo",
            risk_level: "HIGH",
            predicted_cases: 12,
            generated_at: "2026-04-28T08:00:00Z",
          },
          {
            ward_id: 13,
            ward_name: "Got Kachola",
            risk_level: "LOW",
            predicted_cases: 1,
            generated_at: "2026-04-28T08:00:00Z",
          },
        ],
        alerts: [
          {
            id: 1,
            ward: 12,
            created_at: "2026-04-28T08:00:00Z",
            status: "DELIVERED",
          },
          {
            id: 2,
            ward: 12,
            created_at: "2026-04-28T08:10:00Z",
            status: "RETRY_PENDING",
          },
        ],
        wardMap: {
          metadata: {
            geometry_feature_count: 2,
            expected_ward_count: 2,
            missing_source_wards: [],
            geometry_note: "",
          },
          features: [
            buildFeature(),
            buildFeature({
              name: "Got Kachola",
              ward_code: "KE-WARD-1262",
              backend_ward_id: 13,
              active_chv_count: 0,
              chv_count: 1,
              risk_level: "LOW",
              predicted_cases: 1,
              alert_count: 0,
            }),
          ],
        },
        coverageRequests: [
          {
            public_id: "req-12-open",
            ward: 12,
            ward_name: "North Kamagambo",
            ward_public_id: "ward-12",
            requested_by: 1,
            requested_by_username: "admin",
            status: "OPEN",
            priority: "HIGH",
            trigger_source: "MANUAL",
            linked_alert_public_ids: [],
            linked_alerts_summary: [],
            reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
            requested_chv_count: 1,
            notes: "",
            assigned_to_user: null,
            assigned_to_username: null,
            assigned_to_team: "",
            reviewed_by: null,
            reviewed_by_username: null,
            reviewed_at: null,
            review_decision_reason: "",
            expected_response_by: "2026-04-28T12:00:00Z",
            resolved_at: null,
            request_age: 600,
            is_overdue: false,
            sla_status: "ON_TRACK",
            assignments: [],
            events: [],
            created_at: "2026-04-28T08:00:00Z",
            updated_at: "2026-04-28T08:00:00Z",
          },
        ],
        coverageByWard: {
          12: {
            wardId: 12,
            liveRequestCount: 1,
            overdueRequestCount: 0,
            activeAssignmentCount: 0,
            latestRequest: {
              public_id: "req-12-open",
              ward: 12,
              ward_name: "North Kamagambo",
              ward_public_id: "ward-12",
              requested_by: 1,
              requested_by_username: "admin",
              status: "OPEN",
              priority: "HIGH",
              trigger_source: "MANUAL",
              linked_alert_public_ids: [],
              linked_alerts_summary: [],
              reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
              requested_chv_count: 1,
              notes: "",
              assigned_to_user: null,
              assigned_to_username: null,
              assigned_to_team: "",
              reviewed_by: null,
              reviewed_by_username: null,
              reviewed_at: null,
              review_decision_reason: "",
              expected_response_by: "2026-04-28T12:00:00Z",
              resolved_at: null,
              request_age: 600,
              is_overdue: false,
              sla_status: "ON_TRACK",
              assignments: [],
              events: [],
              created_at: "2026-04-28T08:00:00Z",
              updated_at: "2026-04-28T08:00:00Z",
            },
          },
        },
        offlineMonitoring: buildOfflineMonitoring(),
      },
      isPending: false,
      error: null,
    });

    mockUseCreateChvCoverageRequestMutation.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseAssignChvCoverageRequestMutation.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseChvCoverageRequestDetailQuery.mockReturnValue({
      data: null,
      isPending: false,
      error: null,
    });
    mockUseChvActivityQuery.mockReturnValue({
      data: [],
      isPending: false,
      error: null,
    });
    mockUseChvMessagesQuery.mockReturnValue({
      data: [
        {
          public_id: "msg-history-1",
          channel: "SMS",
          message_body: "Historical check-in",
          status: "SENT",
          delivery_kind: "SIMULATED",
          delivery_backend: "stub",
          provider_reference: "stub-xyz",
          failure_reason: "",
          sent_by: 1,
          sent_by_username: "admin",
          created_at: "2026-04-28T09:10:00Z",
          updated_at: "2026-04-28T09:10:00Z",
        },
      ],
      isPending: false,
      error: null,
    });
    mockUseCreateChvMessageMutation.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
  });

  it("uses operations-focused metrics and insights instead of mixed dashboard cards", () => {
    render(React.createElement(ChvsPage));

    expect(mockUseChvOperationsQuery).toHaveBeenCalledWith({ enabled: true });
    expect(screen.getByText("Coverage gaps")).toBeInTheDocument();
    expect(screen.getByText("Active today")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Operational Insights" })).toBeInTheDocument();
    expect(screen.queryByText("Alert delivery rate")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Planning Summary" })).not.toBeInTheDocument();
    expect(screen.getByText(/Gap = 0 active CHVs/i)).toBeInTheDocument();
  }, 20000);

  it("renders offline sync monitoring metrics and backend decisions", () => {
    render(React.createElement(ChvsPage));

    expect(screen.getByRole("heading", { name: "Offline Sync Health" })).toBeInTheDocument();
    expect(screen.getByText("Active devices")).toBeInTheDocument();
    expect(screen.getByText("Successful syncs (24h)")).toBeInTheDocument();
    expect(screen.getByText("Pre-validation rejects")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Offline Sync Audit" })).toBeInTheDocument();
    expect(screen.getByText("Repeated rejected uploads")).toBeInTheDocument();
    expect(screen.getByText("Rejected before sync persistence")).toBeInTheDocument();
    expect(screen.getByText("Accepted prevention_visit and linked it to preparedness_action.")).toBeInTheDocument();
    expect(screen.getByText("Latest rejection: Preparedness action not found.")).toBeInTheDocument();
    expect(screen.getByText("Latest pre-validation rejection: Rejected before sync persistence during pii_minimization.")).toBeInTheDocument();
  }, 20000);

  it("lets map selection drive the selected ward actions and registry view", () => {
    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getByRole("button", { name: "Select Got Kachola" }));

    expect(screen.getByText("Registry filtered to Got Kachola from the ward coverage view.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request coverage" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assign CHV" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View related alerts" })).toHaveAttribute("href", "/alerts?ward_id=13");
    expect(screen.getByRole("link", { name: "Open Ward Detail" })).toHaveAttribute("href", "/wards/13");
    expect(screen.getByRole("link", { name: "Review visible CHVs" })).toHaveAttribute("href", "#chv-registry");
    expect(screen.getByText("Clare Auma")).toBeInTheDocument();
    expect(screen.queryByText("Akinyi Omondi")).not.toBeInTheDocument();
  }, 20000);

  it("shows the live request state before inviting a duplicate request", () => {
    render(React.createElement(ChvsPage));

    expect(screen.getByText("Coverage request open")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View request" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request coverage" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Assign CHV" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View related alerts" })).toHaveAttribute("href", "/alerts?ward_id=12");
  }, 20000);

  it("opens a real request modal with a prefilled reason for a gap ward", async () => {
    render(React.createElement(ChvsPage));

    fireEvent.click(await screen.findByRole("button", { name: "Select Got Kachola" }));
    fireEvent.click(screen.getByRole("button", { name: "Request coverage" }));

    expect(await screen.findByText("Create a real CHV coverage request for this ward.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Coverage gap detected: 0 active CHVs recorded in this ward.")).toBeInTheDocument();
  }, 20000);

  it("shows a single activity summary plus messaging in the CHV detail drawer instead of duplicated activity actions", () => {
    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getAllByRole("button", { name: "Open" })[0]!);

    expect(screen.getByRole("button", { name: "Message CHV" })).toBeInTheDocument();
    expect(screen.getByText("Latest activity")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View activity history" })).not.toBeInTheDocument();
    expect(screen.queryByText("This screen currently supports CHV profile and sync review only.")).not.toBeInTheDocument();
    expect(screen.queryByText("Messaging unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Reassignment unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Activity history unavailable")).not.toBeInTheDocument();
  }, 20000);

  it("keeps drawer actions visible when older CHV payloads omit explicit capability fields", () => {
    mockUseChvOperationsQuery.mockReturnValue({
      data: {
        chvs: [
          buildChv({
            can_message: undefined,
            message_mode: undefined,
            message_delivery_kind: undefined,
            can_view_activity: undefined,
          }),
        ],
        latestRisks: [
          {
            ward_id: 12,
            ward_name: "North Kamagambo",
            risk_level: "HIGH",
            predicted_cases: 12,
            generated_at: "2026-04-28T08:00:00Z",
          },
        ],
        alerts: [],
        wardMap: {
          metadata: {
            geometry_feature_count: 1,
            expected_ward_count: 1,
            missing_source_wards: [],
            geometry_note: "",
          },
          features: [buildFeature()],
        },
        coverageRequests: [],
        coverageByWard: {},
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getAllByRole("button", { name: "Open" })[0]!);

    expect(screen.getByRole("button", { name: "Message CHV" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View activity history" })).not.toBeInTheDocument();
    expect(screen.queryByText("This screen currently supports CHV profile and sync review only.")).not.toBeInTheDocument();
  }, 20000);

  it("falls back to the compact review-only note when activity capability is unavailable", () => {
    mockUseChvOperationsQuery.mockReturnValue({
      data: {
        chvs: [buildChv({ can_view_activity: false, can_message: false, message_mode: "UNAVAILABLE", message_delivery_kind: "UNAVAILABLE" })],
        latestRisks: [
          {
            ward_id: 12,
            ward_name: "North Kamagambo",
            risk_level: "HIGH",
            predicted_cases: 12,
            generated_at: "2026-04-28T08:00:00Z",
          },
        ],
        alerts: [],
        wardMap: {
          metadata: {
            geometry_feature_count: 1,
            expected_ward_count: 1,
            missing_source_wards: [],
            geometry_note: "",
          },
          features: [buildFeature()],
        },
        coverageRequests: [],
        coverageByWard: {},
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getAllByRole("button", { name: "Open" })[0]!);

    expect(screen.getByText("This screen currently supports CHV profile and sync review only.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View activity history" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Message CHV" })).not.toBeInTheDocument();
  }, 20000);

  it("opens a message modal with mode-truthful send controls", () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      public_id: "msg-1",
      channel: "SMS",
      message_body: "Hello Akinyi",
      status: "SENT",
      delivery_kind: "SIMULATED",
      delivery_backend: "stub",
      provider_reference: "stub-1",
      failure_reason: "",
      sent_by: 1,
      sent_by_username: "admin",
      created_at: "2026-04-28T09:20:00Z",
      updated_at: "2026-04-28T09:20:00Z",
    });
    mockUseCreateChvMessageMutation.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });

    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getAllByRole("button", { name: "Open" })[0]!);
    fireEvent.click(screen.getByRole("button", { name: "Message CHV" }));

    expect(screen.getByText("CHV messaging")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeInTheDocument();
    expect(screen.getByText("Test mode")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check in" }));
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(mutateAsync).toHaveBeenCalled();
  }, 20000);

  it("highlights the selected CHV message template pill", () => {
    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getAllByRole("button", { name: "Open" })[0]!);
    fireEvent.click(screen.getByRole("button", { name: "Message CHV" }));

    const alertTemplate = screen.getByRole("button", { name: "Alert follow-up" });
    fireEvent.click(alertTemplate);

    expect(alertTemplate).toHaveAttribute("aria-pressed", "true");
  }, 20000);

  it("switches the submit label to queue mode when live send is unavailable", () => {
    mockUseChvOperationsQuery.mockReturnValue({
      data: {
        chvs: [buildChv({ can_message: true, message_mode: "QUEUE_ONLY", message_delivery_kind: "QUEUE_ONLY" })],
        latestRisks: [
          {
            ward_id: 12,
            ward_name: "North Kamagambo",
            risk_level: "HIGH",
            predicted_cases: 12,
            generated_at: "2026-04-28T08:00:00Z",
          },
        ],
        alerts: [],
        wardMap: {
          metadata: {
            geometry_feature_count: 1,
            expected_ward_count: 1,
            missing_source_wards: [],
            geometry_note: "",
          },
          features: [buildFeature()],
        },
        coverageRequests: [],
        coverageByWard: {},
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getAllByRole("button", { name: "Open" })[0]!);
    fireEvent.click(screen.getByRole("button", { name: "Message CHV" }));

    expect(screen.getByRole("button", { name: "Queue message" })).toBeInTheDocument();
  }, 20000);

  it("does not label a request as alert-driven in the drawer without stored linked alerts", () => {
    mockUseChvCoverageRequestDetailQuery.mockReturnValue({
      data: {
        public_id: "req-12-open",
        ward: 12,
        ward_name: "North Kamagambo",
        ward_public_id: "ward-12",
        requested_by: 1,
        requested_by_username: "admin",
        status: "OPEN",
        priority: "HIGH",
        trigger_source: "ALERT_DRIVEN",
        linked_alert_public_ids: [],
        linked_alerts_summary: [],
        reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
        requested_chv_count: 1,
        notes: "",
        assigned_to_user: null,
        assigned_to_username: null,
        assigned_to_team: "",
        reviewed_by: null,
        reviewed_by_username: null,
        reviewed_at: null,
        review_decision_reason: "",
        expected_response_by: "2026-04-28T12:00:00Z",
        resolved_at: null,
        request_age: 600,
        is_overdue: false,
        sla_status: "ON_TRACK",
        assignments: [],
        events: [],
        created_at: "2026-04-28T08:00:00Z",
        updated_at: "2026-04-28T08:00:00Z",
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getByRole("button", { name: "View request" }));

    expect(screen.getByText("Manual")).toBeInTheDocument();
    expect(screen.getByText("This request was opened without stored alert-linked context.")).toBeInTheDocument();
    expect(screen.queryByText("This request was opened from alert context.")).not.toBeInTheDocument();
  }, 20000);

  it("describes manual requests with stored linked alerts as later-linked context in the drawer", () => {
    mockUseChvCoverageRequestDetailQuery.mockReturnValue({
      data: {
        public_id: "req-12-open",
        ward: 12,
        ward_name: "North Kamagambo",
        ward_public_id: "ward-12",
        requested_by: 1,
        requested_by_username: "admin",
        status: "OPEN",
        priority: "HIGH",
        trigger_source: "MANUAL",
        linked_alert_public_ids: ["alert-1"],
        linked_alerts_summary: [
          {
            alert_id: 22,
            alert_public_id: "alert-1",
            ward_id: 12,
            ward_name: "North Kamagambo",
            status: "DELIVERED",
            channel: "SMS",
            created_at: "2026-04-28T07:30:00Z",
            sent_at: "2026-04-28T07:31:00Z",
            risk_score: 77,
          },
        ],
        reason: "Coverage gap detected: 0 active CHVs recorded in this ward.",
        requested_chv_count: 1,
        notes: "",
        assigned_to_user: null,
        assigned_to_username: null,
        assigned_to_team: "",
        reviewed_by: null,
        reviewed_by_username: null,
        reviewed_at: null,
        review_decision_reason: "",
        expected_response_by: "2026-04-28T12:00:00Z",
        resolved_at: null,
        request_age: 600,
        is_overdue: false,
        sla_status: "ON_TRACK",
        assignments: [],
        events: [],
        created_at: "2026-04-28T08:00:00Z",
        updated_at: "2026-04-28T08:00:00Z",
      },
      isPending: false,
      error: null,
    });

    render(React.createElement(ChvsPage));

    fireEvent.click(screen.getByRole("button", { name: "View request" }));

    expect(screen.getByText("Manual")).toBeInTheDocument();
    expect(screen.getByText("This request was opened manually and later linked to alert context.")).toBeInTheDocument();
    expect(screen.getByText("Alert alert-1")).toBeInTheDocument();
  }, 20000);
});
