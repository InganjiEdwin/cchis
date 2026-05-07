import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MessageGovernancePage from "@/app/(dashboard)/message-governance/page";
import type { MessageGovernanceDashboardResponse, MessageTemplateDetailResponse } from "@/lib/dashboard";

const mockUseAuth = vi.fn();
const mockUseMessageGovernanceDashboardQuery = vi.fn();
const mockUseMessageTemplateDetailQuery = vi.fn();
const mockUseApproveMessageTemplateMutation = vi.fn();
const mockUseApproveUssdMenuVersionMutation = vi.fn();
const mockPush = vi.fn();
const mockRefetch = vi.fn();
const mockMutateAsync = vi.fn();
const mockUssdMutateAsync = vi.fn();

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
  useApproveUssdMenuVersionMutation: () => mockUseApproveUssdMenuVersionMutation(),
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
    schema_version: "message-management-phase-7-v1",
    generated_at: "2026-05-04T10:00:00Z",
    filters: {},
    available_filters: {
      audience_types: ["chv", "household", "facility_contact", "county_operator", "system_operator"],
      channels: ["sms", "ussd", "dashboard", "offline_chv_bundle"],
      languages: ["en", "luo", "sw"],
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
      missing_translation_count: 1,
      placeholder_parity_warning_count: 0,
      translation_review_warning_count: 0,
      missing_translation_issue_count: 1,
      offline_guidance_language_count: 3,
      strict_localization_issue_count: 0,
      localization_fallback_rate_pct: 12.5,
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
        route_tree_preview: [
          {
            route: "",
            route_label: "root",
            node_key: "root",
            response_type: "CON",
            body: "Welcome to CCHIS Health Menu\n1. Flood safety advice",
            response_text: "CON Welcome to CCHIS Health Menu\n1. Flood safety advice",
            character_count: 54,
          },
        ],
        validation_status: "pass",
        validation_messages: [],
      },
    ],
    template_language_coverage: {
      supported_languages: [
        { code: "en", label: "English" },
        { code: "sw", label: "Kiswahili" },
        { code: "luo", label: "Dholuo" },
      ],
      row_count: 1,
      missing_variant_count: 1,
      placeholder_warning_count: 0,
      translation_review_warning_count: 0,
      rows: [
        {
          template_key: "cholera.household.prevent",
          version: 1,
          title: "Household prevention",
          audience_type: "household",
          channel: "sms",
          risk_level: "high",
          owner: "county_health_promotion",
          requires_translation: true,
          present_languages: ["en", "sw"],
          missing_languages: ["luo"],
          missing_language_labels: ["Dholuo"],
          variants: [
            {
              language: "en",
              label: "English",
              exists: true,
              public_id: "template-pending",
              title: "Household prevention",
              approval_status: "pending_review",
              translation_status: "draft",
              placeholder_parity_status: "source",
              warnings: [],
            },
            {
              language: "sw",
              label: "Kiswahili",
              exists: true,
              public_id: "template-sw",
              title: "Household prevention SW",
              approval_status: "draft",
              translation_status: "draft",
              placeholder_parity_status: "pass",
              warnings: [],
            },
            {
              language: "luo",
              label: "Dholuo",
              exists: false,
              public_id: "",
              title: "",
              approval_status: "",
              translation_status: "",
              placeholder_parity_status: "missing",
              warnings: ["Missing Dholuo variant."],
            },
          ],
          placeholder_warnings: [],
          translation_review_warnings: [],
        },
      ],
    },
    missing_translation_dashboard: {
      total_issue_count: 1,
      by_issue_type: { missing_variant: 1 },
      by_severity: { high: 1 },
      items: [
        {
          issue_type: "missing_variant",
          severity: "high",
          template_key: "cholera.household.prevent",
          version: 1,
          title: "Household prevention",
          audience_type: "household",
          channel: "sms",
          language: "luo",
          label: "Dholuo",
          message: "Missing Dholuo variant before rollout.",
        },
      ],
    },
    ussd_route_tree_preview: [
      {
        menu_key: "cholera_health_menu",
        source_menu_version: "ussd-menu-1",
        source_version_label: "builtin-v1",
        source_title: "CCHIS Cholera Health USSD Menu",
        languages: [
          {
            language: "en",
            label: "English",
            exists: true,
            public_id: "ussd-menu-1",
            title: "CCHIS Cholera Health USSD Menu",
            approval_status: "APPROVED",
            translation_status: "approved",
            safe_fallback_copy: "END Invalid option. Please try again.",
            requested_language: "en",
            resolved_language: "en",
            fallback_used: false,
            route_count: 1,
            routes: [
              {
                route: "",
                route_label: "root",
                node_key: "root",
                response_type: "CON",
                body: "Welcome to CCHIS Health Menu\n1. Flood safety advice",
                response_text: "CON Welcome to CCHIS Health Menu\n1. Flood safety advice",
                character_count: 54,
              },
            ],
            warnings: [],
          },
          {
            language: "sw",
            label: "Kiswahili",
            exists: false,
            public_id: "",
            title: "",
            approval_status: "",
            translation_status: "",
            safe_fallback_copy: "END Invalid option. Please try again.",
            requested_language: "sw",
            resolved_language: "en",
            fallback_used: true,
            route_count: 1,
            routes: [
              {
                route: "",
                route_label: "root",
                node_key: "root",
                response_type: "CON",
                body: "Welcome to CCHIS Health Menu\n1. Flood safety advice",
                response_text: "CON Welcome to CCHIS Health Menu\n1. Flood safety advice",
                character_count: 54,
              },
            ],
            warnings: ["Missing active Kiswahili USSD menu; English fallback would be used."],
          },
          {
            language: "luo",
            label: "Dholuo",
            exists: false,
            public_id: "",
            title: "",
            approval_status: "",
            translation_status: "",
            safe_fallback_copy: "END Invalid option. Please try again.",
            requested_language: "luo",
            resolved_language: "en",
            fallback_used: true,
            route_count: 1,
            routes: [
              {
                route: "",
                route_label: "root",
                node_key: "root",
                response_type: "CON",
                body: "Welcome to CCHIS Health Menu\n1. Flood safety advice",
                response_text: "CON Welcome to CCHIS Health Menu\n1. Flood safety advice",
                character_count: 54,
              },
            ],
            warnings: ["Missing active Dholuo USSD menu; English fallback would be used."],
          },
        ],
      },
    ],
    offline_guidance_preview: [
      {
        language: "en",
        label: "English",
        requested_language: "en",
        resolved_language: "en",
        fallback_used: false,
        item_count: 1,
        items: [
          {
            guidance_public_id: "offline-guidance-en",
            template_key: "cholera.household.prevention_guidance_offline_bundle",
            version: 1,
            title: "Core cholera prevention guidance",
            language: "en",
            requested_language: "en",
            resolved_language: "en",
            fallback_used: false,
            audience_type: "chv",
            body: "Use safe water and wash hands with soap.",
            rendered_body: "Use safe water and wash hands with soap.",
            public_health_caveats: "Approved public-health copy.",
          },
        ],
        warnings: [],
      },
      {
        language: "sw",
        label: "Kiswahili",
        requested_language: "sw",
        resolved_language: "en",
        fallback_used: true,
        item_count: 1,
        items: [
          {
            guidance_public_id: "offline-guidance-en",
            template_key: "cholera.household.prevention_guidance_offline_bundle",
            version: 1,
            title: "Core cholera prevention guidance",
            language: "en",
            requested_language: "sw",
            resolved_language: "en",
            fallback_used: true,
            audience_type: "chv",
            body: "Use safe water and wash hands with soap.",
            rendered_body: "Use safe water and wash hands with soap.",
            public_health_caveats: "Approved public-health copy.",
          },
        ],
        warnings: ["Kiswahili guidance uses English fallback."],
      },
      {
        language: "luo",
        label: "Dholuo",
        requested_language: "luo",
        resolved_language: "en",
        fallback_used: true,
        item_count: 1,
        items: [
          {
            guidance_public_id: "offline-guidance-en",
            template_key: "cholera.household.prevention_guidance_offline_bundle",
            version: 1,
            title: "Core cholera prevention guidance",
            language: "en",
            requested_language: "luo",
            resolved_language: "en",
            fallback_used: true,
            audience_type: "chv",
            body: "Use safe water and wash hands with soap.",
            rendered_body: "Use safe water and wash hands with soap.",
            public_health_caveats: "Approved public-health copy.",
          },
        ],
        warnings: ["Dholuo guidance uses English fallback."],
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
      schema_version: "message-governance-phase-7-v1",
      overall_status: "pass",
      strict_localization_issue_count: 0,
      localization_rollout: {
        schema_version: "chv-localization-rollout-phase-7-v1",
        generated_at: "2026-05-04T10:00:00Z",
        supported_languages: ["en", "sw", "luo"],
        default_language: "en",
        chv_preferred_language_counts: [
          { key: "en", count: 1 },
          { key: "sw", count: 1 },
        ],
        active_chv_count: 2,
        device_preferred_language_counts: [
          { key: "en", count: 1 },
        ],
        active_device_count: 1,
        offline_bundle_requests_by_language: {
          surface: "offline_bundle",
          total_count: 1,
          fallback_count: 0,
          fallback_rate_pct: 0,
          by_requested_language: [{ key: "en", count: 1 }],
          by_resolved_language: [{ key: "en", count: 1 }],
          fallback_by_resolved_language: [],
        },
        fallback_metrics: [
          {
            surface: "chv_sms",
            total_count: 2,
            fallback_count: 0,
            fallback_rate_pct: 0,
            by_requested_language: [{ key: "en", count: 2 }],
            by_resolved_language: [{ key: "en", count: 2 }],
            fallback_by_resolved_language: [],
          },
          {
            surface: "offline_bundle",
            total_count: 1,
            fallback_count: 1,
            fallback_rate_pct: 100,
            by_requested_language: [{ key: "sw", count: 1 }],
            by_resolved_language: [{ key: "en", count: 1 }],
            fallback_by_resolved_language: [{ key: "en", count: 1 }],
          },
        ],
        fallback_rate_pct: 12.5,
        ussd_sessions_by_language_and_outcome: [
          { language: "en", outcome: "COMPLETED", count: 1 },
        ],
        chv_sms_deliveries_by_language_and_outcome: [
          { language: "en", outcome: "DELIVERED", count: 1 },
        ],
        missing_translation_count: 1,
        translation_review_age: {
          pending_review_count: 1,
          max_age_days: 2,
          average_age_days: 2,
          oldest_records: [
            {
              model: "risk.MessageTemplate",
              public_id: "template-sw",
              key: "cholera.household.prevent",
              language: "sw",
              status: "draft",
              age_days: 2,
            },
          ],
        },
        rollout_path: [
          { step: "ship_english_audit_with_required_language_gaps", status: "complete" },
          { step: "monitor_fallback_and_failure_rates", status: "active" },
        ],
      },
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
    schema_version: "message-management-phase-7-v1",
    generated_at: dashboard.generated_at,
    template,
    version_history: [nextVersion, template],
    language_variants: dashboard.templates,
    side_by_side_preview: [
      {
        language: "en",
        label: "English",
        exists: true,
        public_id: "template-pending",
        title: "Household prevention",
        approval_status: "pending_review",
        translation_status: "draft",
        source_template: "template-pending",
        source_template_key: "cholera.household.prevent",
        source_template_version: 1,
        body: "Use treated water in {ward_name}.",
        rendered_body: "Use treated water in Kanyasa.",
        delivery_rendered_body: "Use treated water in Kanyasa.",
        requested_language: "en",
        resolved_language: "en",
        fallback_used: false,
        placeholders: ["ward_name"],
        placeholder_parity_status: "source",
        placeholder_warnings: [],
        render_error: "",
      },
      {
        language: "sw",
        label: "Kiswahili",
        exists: true,
        public_id: "template-sw",
        title: "Household prevention SW",
        approval_status: "draft",
        translation_status: "draft",
        source_template: "template-pending",
        source_template_key: "cholera.household.prevent",
        source_template_version: 1,
        body: "Tumia maji salama {ward_name}.",
        rendered_body: "Tumia maji salama Kanyasa.",
        delivery_rendered_body: "Use treated water in Kanyasa.",
        requested_language: "sw",
        resolved_language: "en",
        fallback_used: true,
        placeholders: ["ward_name"],
        placeholder_parity_status: "warning",
        placeholder_warnings: ["Variant is not approved for use; English fallback would be shown to users."],
        render_error: "",
      },
      {
        language: "luo",
        label: "Dholuo",
        exists: false,
        public_id: "",
        title: "",
        approval_status: "",
        translation_status: "",
        source_template: "template-pending",
        source_template_key: "cholera.household.prevent",
        source_template_version: 1,
        body: "",
        rendered_body: "",
        delivery_rendered_body: "Use treated water in Kanyasa.",
        requested_language: "luo",
        resolved_language: "en",
        fallback_used: true,
        placeholders: [],
        placeholder_parity_status: "missing",
        placeholder_warnings: ["Missing Dholuo variant; English fallback would be used."],
        render_error: "",
      },
    ],
    delivery_summary: dashboard.delivery_summary,
  };
}

describe("MessageGovernancePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRefetch.mockResolvedValue({});
    mockMutateAsync.mockResolvedValue({});
    mockUssdMutateAsync.mockResolvedValue({});
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
    mockUseApproveUssdMenuVersionMutation.mockReturnValue({
      mutateAsync: mockUssdMutateAsync,
      isPending: false,
    });
  });

  it("renders communication review, clear attention copy, and grouped details", async () => {
    render(React.createElement(MessageGovernancePage));

    expect(screen.getByText(/Communication Review \| Review the messages people receive/i)).toBeInTheDocument();
    expect(screen.getByText("1 item needs review before rollout")).toBeInTheDocument();
    expect(screen.getAllByText("The Dholuo message is missing. Add it before rollout.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Needs Attention").length).toBeGreaterThan(0);
    expect(screen.getByText("Language Rollout")).toBeInTheDocument();
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /messages/i }));

    expect(screen.getAllByText("Messages").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Household prevention").length).toBeGreaterThan(0);
    await screen.findByText("Message Text");
    expect(screen.getAllByText("Use treated water in Kanyasa.").length).toBeGreaterThan(0);
    expect(screen.getByText("Tumia maji salama Kanyasa.")).toBeInTheDocument();
    expect(screen.getAllByText("Message fields").length).toBeGreaterThan(0);
    expect(screen.getByText("Who Will Receive It")).toBeInTheDocument();
    expect(screen.getByText("Review Trail")).toBeInTheDocument();
    expect(screen.getByText("Past Versions")).toBeInTheDocument();
    expect(screen.getByText("Version 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /languages/i }));
    expect(screen.getByText("Language Readiness")).toBeInTheDocument();
    expect(screen.getByText("CHV Guide Preview")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /sending results/i }));
    expect(screen.getAllByText("Sending Results").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Reach").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Stopped Messages").length).toBeGreaterThan(0);
    expect(screen.getByText("Message Use")).toBeInTheDocument();
    expect(screen.getByText("Phone Menu Use")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /phone menus/i }));
    expect(screen.getByText("Phone Menu Preview")).toBeInTheDocument();
    expect(screen.getByText("Phone Menu Updates")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /reject/i }).length).toBeGreaterThan(0);
    expect(mockUseMessageTemplateDetailQuery).toHaveBeenCalledWith("template-pending");
  });

  it("submits admin approval through the mutation contract", async () => {
    render(React.createElement(MessageGovernancePage));

    fireEvent.click(screen.getByRole("button", { name: /messages/i }));

    await screen.findByText("Message Text");
    fireEvent.change(screen.getByPlaceholderText("Review note"), {
      target: { value: "Approved by county health promotion." },
    });
    fireEvent.click(screen.getAllByRole("button", { name: /approve/i })[0]);

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

  it("submits USSD menu review actions through the mutation contract", async () => {
    render(React.createElement(MessageGovernancePage));

    fireEvent.click(screen.getByRole("button", { name: /phone menus/i }));

    await screen.findByText("Phone Menu Updates");
    fireEvent.click(screen.getAllByRole("button", { name: /reject/i }).at(-1) as HTMLElement);

    await waitFor(() => {
      expect(mockUssdMutateAsync).toHaveBeenCalledWith({
        publicId: "ussd-menu-1",
        payload: {
          action: "reject",
          reason: "Reviewed from the communication review page.",
        },
      });
    });
    expect(mockRefetch).toHaveBeenCalled();
  });
});
