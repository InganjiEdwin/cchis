import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MessageGovernancePage from "@/app/(dashboard)/message-governance/page";
import type { MessageGovernanceDashboardResponse, MessageTemplateDetailResponse } from "@/lib/dashboard";

const mockUseAuth = vi.fn();
const mockUseMessageGovernanceDashboardQuery = vi.fn();
const mockUseMessageTemplateDetailQuery = vi.fn();
const mockUseApproveMessageTemplateMutation = vi.fn();
const mockPush = vi.fn();
const mockRefetch = vi.fn();
const mockMutateAsync = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-topbar", () => ({
  DashboardTopbar: ({
    title,
    subtitle,
    lastUpdatedLabel,
    children,
  }: {
    title: string;
    subtitle: string;
    lastUpdatedLabel?: string;
    children?: React.ReactNode;
  }) => React.createElement("div", null, `${title} | ${subtitle} | ${lastUpdatedLabel ?? "no-label"}`, children),
}));

vi.mock("@/components/role-gate", () => ({
  RoleGate: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock("@/queries/use-message-governance-query", () => ({
  useMessageGovernanceDashboardQuery: (...args: unknown[]) => mockUseMessageGovernanceDashboardQuery(...args),
  useMessageTemplateDetailQuery: (...args: unknown[]) => mockUseMessageTemplateDetailQuery(...args),
  useApproveMessageTemplateMutation: () => mockUseApproveMessageTemplateMutation(),
}));

function buildDashboard(): MessageGovernanceDashboardResponse {
  const pendingTemplate = {
    public_id: "template-pending",
    template_key: "cholera.household.prevent",
    audience_type: "household" as const,
    channel: "sms" as const,
    language: "en",
    version: 1,
    title: "Household prevention",
    body: "Use treated water in {ward_name}.",
    placeholders: ["ward_name"],
    approval_status: "pending_review" as const,
    approved_by: null,
    approved_by_username: "",
    approved_at: null,
    retired_at: null,
    owner: "county_health_promotion",
    risk_level: "high" as const,
    public_health_caveats: "Requires consent.",
    lineage_metadata: {
      approval_events: [
        {
          action: "request_review",
          actor_username: "analyst",
          created_at: "2026-05-04T09:00:00Z",
        },
      ],
    },
    created_by: 2,
    created_by_username: "analyst",
    created_at: "2026-05-04T08:00:00Z",
    updated_at: "2026-05-04T09:00:00Z",
    preview: {
      context: { ward_name: "Kanyasa" },
      rendered_body: "Use treated water in Kanyasa.",
      declared_placeholders: ["ward_name"],
      discovered_placeholders: ["ward_name"],
      render_error: "",
    },
    audience_preview: {
      audience_type: "household" as const,
      channel: "sms" as const,
      risk_level: "high",
      scope: "household_prevention_scope",
      consent_requirement: "consent_or_approved_lawful_basis",
      emergency_override_allowed: true,
      public_health_caveats: "Requires consent.",
    },
    usage_summary: {
      alert_count: 0,
      chv_message_count: 0,
      facility_update_request_count: 0,
      total_delivery_count: 0,
    },
  };

  return {
    schema_version: "message-management-phase-5-v1",
    generated_at: "2026-05-04T10:00:00Z",
    filters: {},
    available_filters: {
      audience_types: ["chv", "household", "facility_contact", "county_operator", "system_operator"],
      channels: ["sms", "ussd", "dashboard", "offline_chv_bundle"],
      languages: ["en", "sw"],
      approval_statuses: ["draft", "pending_review", "approved", "rejected", "retired"],
    },
    summary: {
      template_count: 2,
      approved_template_count: 1,
      pending_review_template_count: 1,
      draft_template_count: 0,
      retired_template_count: 0,
      language_count: 2,
      languages: ["en", "sw"],
      audience_counts: { household: 1, chv: 1 },
      channel_counts: { sms: 2 },
      approval_status_counts: { approved: 1, pending_review: 1 },
      unapproved_high_risk_template_count: 1,
      delivery_record_count: 2,
      communication_reach_count: 1,
      delivery_failure_count: 1,
      delivery_success_rate_pct: 50,
      opt_out_count: 1,
      opt_out_blocked_count: 1,
      template_usage_version_count: 1,
      ussd_total_sessions: 3,
      ussd_completion_rate_pct: 33.333333,
      ussd_invalid_input_rate_pct: 33.333333,
      ussd_abandonment_rate_pct: 33.333333,
      ussd_menu_version_count: 1,
      active_ussd_menu_version_count: 1,
      audit_status: "pass",
    },
    templates: [
      pendingTemplate,
      {
        ...pendingTemplate,
        public_id: "template-sw",
        language: "sw",
        title: "Household prevention SW",
        approval_status: "draft",
        preview: {
          ...pendingTemplate.preview,
          rendered_body: "Tumia maji salama Kanyasa.",
        },
      },
    ],
    ussd_menu_versions: [
      {
        public_id: "ussd-menu-1",
        menu_key: "cholera_health_menu",
        version_label: "builtin-v1",
        language: "en",
        title: "CCHIS Cholera Health USSD Menu",
        approval_status: "APPROVED",
        approved_by: 1,
        approved_by_username: "admin",
        approved_at: "2026-05-04T08:00:00Z",
        retired_at: null,
        is_active: true,
        safe_fallback_copy: "END Invalid option. Please try again.",
        lineage_metadata: {},
        created_by: 1,
        created_by_username: "admin",
        created_at: "2026-05-04T08:00:00Z",
        updated_at: "2026-05-04T08:00:00Z",
        route_count: 6,
        node_count: 6,
        validation_status: "pass",
        validation_messages: [],
      },
    ],
    delivery_summary: {
      total_count: 2,
      successful_count: 1,
      failed_count: 1,
      success_rate_pct: 50,
      by_audience_channel_status: [
        {
          audience_type: "chv",
          channel: "sms",
          status: "DELIVERED",
          count: 1,
          latest_at: "2026-05-04T09:30:00Z",
        },
      ],
      by_template: [
        {
          template_key: "cholera.household.prevent",
          template_version: 1,
          count: 2,
          statuses: { DELIVERED: 1, FAILED: 1 },
          latest_at: "2026-05-04T09:30:00Z",
        },
      ],
      template_usage_by_version: [
        {
          template_key: "cholera.household.prevent",
          template_version: 1,
          count: 2,
          statuses: { DELIVERED: 1, FAILED: 1 },
          latest_at: "2026-05-04T09:30:00Z",
        },
      ],
      reach_by_audience_channel: [
        {
          audience_type: "chv",
          channel: "sms",
          message_count: 2,
          unique_recipient_count: 1,
          successful_count: 1,
          failed_count: 1,
          success_rate_pct: 50,
          latest_at: "2026-05-04T09:30:00Z",
        },
      ],
      opt_out_summary: {
        total_current_opt_out_count: 1,
        total_blocked_opt_out_event_count: 1,
        by_audience_channel: [
          {
            audience_type: "chv",
            channel: "sms",
            current_opt_out_count: 1,
            blocked_opt_out_event_count: 1,
            latest_opt_out_at: "2026-05-04T09:20:00Z",
            latest_blocked_at: "2026-05-04T09:30:00Z",
          },
        ],
      },
      recent_records: [],
    },
    ussd_analytics: {
      schema_version: "ussd-menu-governance-phase-3-v1",
      total_logs: 4,
      total_sessions: 3,
      completed_sessions: 1,
      invalid_input_sessions: 1,
      abandoned_sessions: 1,
      safe_fallback_sessions: 0,
      completion_rate_pct: 33.333333,
      invalid_input_rate_pct: 33.333333,
      abandonment_rate_pct: 33.333333,
      by_outcome: [],
      by_language: [],
      by_menu_version: [
        {
          menu_key: "cholera_health_menu",
          menu_version_label: "builtin-v1",
          language: "en",
          log_count: 4,
          session_count: 3,
          completed_count: 1,
          invalid_input_count: 1,
          abandoned_count: 1,
          latest_at: "2026-05-04T09:30:00Z",
        },
      ],
      recent_logs: [],
    },
    audit: {
      schema_version: "message-governance-phase-0-5-v1",
      overall_status: "pass",
      checks: [],
    },
  };
}

function buildTemplateDetail(dashboard: MessageGovernanceDashboardResponse): MessageTemplateDetailResponse {
  const template = dashboard.templates[0];
  const nextVersion = {
    ...template,
    public_id: "template-pending-v2",
    version: 2,
    approval_status: "approved" as const,
    approved_by: 1,
    approved_by_username: "admin",
    approved_at: "2026-05-04T10:00:00Z",
    updated_at: "2026-05-04T10:00:00Z",
  };

  return {
    schema_version: "message-management-phase-5-v1",
    generated_at: dashboard.generated_at,
    template,
    version_history: [nextVersion, template],
    language_variants: dashboard.templates,
    delivery_summary: dashboard.delivery_summary,
  };
}

describe("MessageGovernancePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRefetch.mockResolvedValue({});
    mockMutateAsync.mockResolvedValue({});
    const dashboard = buildDashboard();
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        full_name: "Admin User",
        phone_number: null,
        role: "ADMIN",
        theme_preference: "DARK",
        ward: null,
        ward_name: null,
        is_active: true,
      },
    });
    mockUseMessageGovernanceDashboardQuery.mockReturnValue({
      data: dashboard,
      isPending: false,
      error: null,
      refetch: mockRefetch,
      isFetching: false,
    });
    mockUseMessageTemplateDetailQuery.mockImplementation((publicId: string | null) => ({
      data: publicId ? buildTemplateDetail(dashboard) : undefined,
      isPending: false,
      error: null,
    }));
    mockUseApproveMessageTemplateMutation.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    });
  });

  it("renders template review, delivery outcomes, and USSD analytics", async () => {
    render(React.createElement(MessageGovernancePage));

    expect(screen.getByText(/Message Governance \| Templates, public-health copy approval/i)).toBeInTheDocument();
    expect(screen.getByText("Template List")).toBeInTheDocument();
    expect(screen.getAllByText("Household prevention").length).toBeGreaterThan(0);
    await screen.findByText("Language Preview");
    expect(screen.getByText("Use treated water in Kanyasa.")).toBeInTheDocument();
    expect(screen.getByText("Audience Preview")).toBeInTheDocument();
    expect(screen.getByText("Attribution")).toBeInTheDocument();
    expect(screen.getByText("Version History")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("Delivery Outcome Summary")).toBeInTheDocument();
    expect(screen.getByText("Communication Reach")).toBeInTheDocument();
    expect(screen.getByText("Opt-Out Monitoring")).toBeInTheDocument();
    expect(screen.getByText("Template Usage by Version")).toBeInTheDocument();
    expect(screen.getByText("USSD Session Analytics")).toBeInTheDocument();
    expect(screen.getByText("USSD Menu Versions")).toBeInTheDocument();
    expect(mockUseMessageTemplateDetailQuery).toHaveBeenCalledWith("template-pending");
  });

  it("submits admin approval through the mutation contract", async () => {
    render(React.createElement(MessageGovernancePage));

    await screen.findByText("Language Preview");
    fireEvent.change(screen.getByPlaceholderText("Review note"), {
      target: { value: "Approved by county health promotion." },
    });
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        publicId: "template-pending",
        payload: {
          action: "approve",
          reason: "Approved by county health promotion.",
        },
      });
    });
    expect(mockRefetch).toHaveBeenCalled();
  });
});
