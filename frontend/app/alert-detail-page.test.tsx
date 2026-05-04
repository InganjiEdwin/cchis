import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AlertDetailPage from "@/app/(dashboard)/alerts/[id]/page";

const mockUseAuth = vi.fn();
const mockUseAlertDetailQuery = vi.fn();
const mockUseParams = vi.fn();
const mockUseRouter = vi.fn();
const mockUseCreateChvCoverageRequestFromAlertMutation = vi.fn();
const mockUseCreateChvCoverageRequestMutation = vi.fn();
const mockUseLiveChvCoverageRequestForWardQuery = vi.fn();
const mockCreateSensitiveExportViaBff = vi.fn();
const mockDownloadSensitiveExportViaBff = vi.fn();
const mockDownloadSensitiveExportFile = vi.fn();

function buildAlertDetailData(overrides: Record<string, unknown> = {}) {
  return {
    alert: {
      id: 2,
      public_id: "00000000-0000-0000-0000-000000000002",
      ward: 12,
      ward_name: "Got Kachola",
      risk_score: 61,
      channel: "SMS",
      recipient: "Dashboard",
      message: "Retry pending follow-up alert",
      status: "RETRY_PENDING",
      delivery_backend: "twilio",
      attempt_count: 1,
      max_attempts: 3,
      last_attempted_at: null,
      next_retry_at: null,
      external_id: "",
      sent_at: null,
      created_at: "2026-04-28T06:00:00Z",
      error_message: "Transport retry still pending.",
    },
    ward_detail: {
      id: 12,
      name: "Got Kachola",
      code: "MIG-12",
      county: "Migori",
      sub_county: "Rongo",
      current_risk_level: "LOW",
      current_risk_score: 22,
      updated_at: "2026-04-28T06:00:00Z",
    },
    classification: {
      icon_key: "shield-alert",
      tone: "amber",
      label: "Alert record",
      mode: "recorded_signal",
      trigger_source: "Backend workflow",
    },
    risk_context: {
      level_label: "Low risk",
      trend_label: "Stable ward conditions",
      recorded_risk_score: 22,
      threshold: 50,
    },
    lifecycle: {
      status: "monitoring",
      status_label: "Monitoring",
      summary: "Retry is still pending and the safest next move is continued review.",
    },
    delivery: {},
    delivery_summary: {
      channel_label: "Dashboard",
      audience_label: "Recorded recipient",
      recipient_count: 1,
    },
    message_source: {
      label: "Message source unavailable",
      mode: "unavailable",
      summary: "Message-source detail is not available for this alert yet.",
      preview_text: "",
      trigger_type: "",
    },
    climate_evidence: {
      schema_version: "climate-alert-evidence-v1",
      record_type: "fallback_static",
      source_provider: "static-default",
      observed_vs_forecast_source_label: "Fallback static rainfall",
      issue_time: null,
      valid_date: null,
      lead_day: null,
      forecast_horizon_days: 0,
      claimed_forecast_horizon_days: 14,
      forecast_coverage_days: 0,
      forecast_missing_lead_days: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
      claimed_lead_time_climate_coverage_sufficient: false,
      fallback_static_rainfall_used: true,
      climate_source_confidence: 0.2,
      climate_source_confidence_label: "low",
      climate_coverage_status: "insufficient_forecast_horizon",
      climate_coverage_caveats: ["forecast_missing_claimed_lead_days", "fallback_static_rainfall_present_not_live_forecast"],
    },
    chv_response_summary: {
      coverage_label: "No field response recorded",
      summary: "No CHV response summary is available.",
      response_count: 0,
    },
    facility_response_summary: {
      status_label: "No facility signal available",
      summary: "No facility response summary is available.",
      response_count: 0,
    },
    recommended_next_action: {
      label: "Send follow-up SMS",
      detail: "Retry is pending, so a follow-up communication path may be needed if delivery remains blocked.",
      blocked: true,
      blocked_reason:
        "This page cannot send a follow-up message yet. Keep tracking delivery and use the alerts workflow if escalation is needed.",
      mode: "not_available_from_alert_detail",
    },
    last_updated_at: "2026-04-28T06:00:00Z",
    current_state: [
      { label: "Delivery still in progress", tone: "warning" },
      { label: "Retry is still pending", tone: "warning" },
      { label: "No high ward-risk threshold recorded", tone: "neutral" },
    ],
    freshness: {
      updated_at: "2026-04-28T06:00:00Z",
      is_stale: false,
    },
    timeline: [
      {
        id: "delivery-status",
        category: "communication",
        tone: "warning",
        title: "Recorded delivery outcome",
        actor: "Backend",
        event_type: "delivery_status",
        timestamp: "2026-04-28T06:00:00Z",
        description: "Retry pending on the recorded SMS path.",
        message: "",
        meta: "",
        details: [],
      },
    ],
    capabilities: {},
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

vi.mock("next/navigation", () => ({
  useParams: () => mockUseParams(),
  useRouter: () => mockUseRouter(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/queries/use-alert-detail-query", () => ({
  useAlertDetailQuery: (...args: unknown[]) => mockUseAlertDetailQuery(...args),
}));

vi.mock("@/queries/use-create-chv-coverage-request-from-alert-mutation", () => ({
  useCreateChvCoverageRequestFromAlertMutation: () => mockUseCreateChvCoverageRequestFromAlertMutation(),
}));

vi.mock("@/queries/use-create-chv-coverage-request-mutation", () => ({
  useCreateChvCoverageRequestMutation: () => mockUseCreateChvCoverageRequestMutation(),
}));

vi.mock("@/queries/use-live-chv-coverage-request-for-ward-query", () => ({
  useLiveChvCoverageRequestForWardQuery: (...args: unknown[]) =>
    mockUseLiveChvCoverageRequestForWardQuery(...args),
}));

vi.mock("@/lib/dashboard", () => ({
  createSensitiveExportViaBff: (...args: unknown[]) => mockCreateSensitiveExportViaBff(...args),
  downloadSensitiveExportViaBff: (...args: unknown[]) => mockDownloadSensitiveExportViaBff(...args),
  downloadSensitiveExportFile: (...args: unknown[]) => mockDownloadSensitiveExportFile(...args),
}));

describe("AlertDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseParams.mockReturnValue({ id: "2" });
    mockUseRouter.mockReturnValue({
      push: vi.fn(),
    });
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

    mockUseAlertDetailQuery.mockReturnValue({
      data: buildAlertDetailData(),
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseCreateChvCoverageRequestFromAlertMutation.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseCreateChvCoverageRequestMutation.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseLiveChvCoverageRequestForWardQuery.mockReturnValue({
      data: null,
      isPending: false,
    });
    mockCreateSensitiveExportViaBff.mockResolvedValue({
      public_id: "export-alert-detail-1",
      approval_state: "APPROVED",
    });
    mockDownloadSensitiveExportViaBff.mockResolvedValue({
      public_id: "export-alert-detail-1",
      filename: "al-0002-report.csv",
      content_type: "text/csv",
      payload: "csv-payload",
      payload_sha256: "sha256",
      expires_at: "2026-05-30T00:00:00Z",
    });
  });

  it("promotes one top next action and routes execution through the ward workflow", async () => {
    render(React.createElement(AlertDetailPage));

    await waitFor(() => {
      expect(mockUseAlertDetailQuery).toHaveBeenCalledWith({
        alertId: 2,
        enabled: true,
      });
    });

    expect(await screen.findByText("Next action")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Send follow-up SMS" })).toBeInTheDocument();
    expect(screen.getByText(/Reason: Retry is pending/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Continue in ward workflow/i })).toHaveAttribute("href", "/wards/12");
    expect(screen.queryByText("Dispatch Additional CHVs Unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Send Follow-up SMS Unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Action Unavailable")).not.toBeInTheDocument();
  });

  it("uses decision-context wording and hides empty message-source detail", async () => {
    render(React.createElement(AlertDetailPage));

    expect(await screen.findByRole("heading", { name: "Decision Context" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Operational Status" })).not.toBeInTheDocument();
    expect(screen.getByText("Awaiting retry")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Climate Source Evidence" })).toBeInTheDocument();
    expect(screen.getAllByText("Fallback static rainfall").length).toBeGreaterThan(0);
    expect(screen.getByText("0/14 days")).toBeInTheDocument();
    expect(screen.getByText(/Fallback source warning: static rainfall is present/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing forecast lead days: 1, 2, 3, 4, 5, 6, 7, 8 \+6 more/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Message Source" })).not.toBeInTheDocument();
    expect(screen.queryByText("Message source unavailable")).not.toBeInTheDocument();
  });

  it("hides sensitive alert export controls from analyst views", async () => {
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

    render(React.createElement(AlertDetailPage));

    expect(await screen.findByRole("heading", { name: "Decision Context" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Export Report/i })).not.toBeInTheDocument();
  });

  it("shows sensitive alert privacy context on detail views", async () => {
    const alertDetailData = buildAlertDetailData();
    mockUseAlertDetailQuery.mockReturnValue({
      data: {
        ...alertDetailData,
        alert: {
          ...alertDetailData.alert,
          recipient: "+254******1001",
          privacy_context: {
            classification: "sensitive_contact_data",
            redacted: true,
            reason: "Direct contact identifiers are masked for this role.",
          },
        },
      },
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    render(React.createElement(AlertDetailPage));

    expect(await screen.findByText(/Sensitive contact details are redacted for this view/i)).toBeInTheDocument();
    expect(screen.getByText(/Direct contact identifiers are masked for this role/i)).toBeInTheDocument();
  });

  it("requests and downloads alert detail report through the sensitive export ledger", async () => {
    render(React.createElement(AlertDetailPage));

    fireEvent.click(await screen.findByRole("button", { name: /Export Report/i }));

    await waitFor(() => {
      expect(mockCreateSensitiveExportViaBff).toHaveBeenCalledWith({
        export_type: "ALERT_DETAIL_REPORT",
        purpose: "Operator requested alert detail report for delivery review.",
        filters: { alert_id: 2 },
      });
    });
    expect(mockDownloadSensitiveExportViaBff).toHaveBeenCalledWith("export-alert-detail-1");
    expect(mockDownloadSensitiveExportFile).toHaveBeenCalledWith(
      expect.objectContaining({ filename: "al-0002-report.csv" }),
    );
    expect(await screen.findByText("Sensitive export downloaded and audited.")).toBeInTheDocument();
  });

  it("switches the CHV handoff CTA to view mode when a live request already exists", async () => {
    const push = vi.fn();
    const prefillMutateAsync = vi.fn();

    mockUseRouter.mockReturnValue({ push });
    mockUseCreateChvCoverageRequestFromAlertMutation.mockReturnValue({
      mutateAsync: prefillMutateAsync,
      isPending: false,
      error: null,
    });
    mockUseLiveChvCoverageRequestForWardQuery.mockReturnValue({
      data: {
        public_id: "req-live-12",
      },
      isPending: false,
    });

    render(React.createElement(AlertDetailPage));

    const button = await screen.findByRole("button", { name: "View CHV coverage request" });
    expect(button).toBeInTheDocument();
    expect(
      screen.getByText("A live CHV coverage request already exists for this ward, so this alert links to that request."),
    ).toBeInTheDocument();

    fireEvent.click(button);

    expect(push).toHaveBeenCalledWith("/chvs/requests/req-live-12");
    expect(prefillMutateAsync).not.toHaveBeenCalled();
  });
});
