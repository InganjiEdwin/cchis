import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardTopbar } from "@/components/dashboard-topbar";

const mockUseAuth = vi.fn();
const mockRefresh = vi.fn();
const mockPush = vi.fn();
const mockFetchTopbarDataViaBff = vi.fn();
const mockFetchNotificationStreamTokenViaBff = vi.fn();
const mockMarkNotificationSeenViaBff = vi.fn();
const mockAcknowledgeNotificationViaBff = vi.fn();
const mockDismissNotificationViaBff = vi.fn();
const mockMarkAllNotificationsSeenViaBff = vi.fn();
const mockWebSocketClose = vi.fn();
const mockWebSocketInstances: Array<{
  url: string;
  protocols?: string | string[];
  close: typeof mockWebSocketClose;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: (() => void) | null;
  onclose: (() => void) | null;
}> = [];

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: mockRefresh,
    push: mockPush,
  }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/lib/freshness", () => ({
  formatRelativeTimestamp: () => "moments ago",
}));

vi.mock("@/lib/dashboard", () => ({
  fetchTopbarDataViaBff: () => mockFetchTopbarDataViaBff(),
  fetchNotificationStreamTokenViaBff: () => mockFetchNotificationStreamTokenViaBff(),
  markNotificationSeenViaBff: (publicId: string) => mockMarkNotificationSeenViaBff(publicId),
  acknowledgeNotificationViaBff: (publicId: string) => mockAcknowledgeNotificationViaBff(publicId),
  dismissNotificationViaBff: (publicId: string) => mockDismissNotificationViaBff(publicId),
  markAllNotificationsSeenViaBff: () => mockMarkAllNotificationsSeenViaBff(),
}));

function renderTopbar() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <DashboardTopbar title="Overview" subtitle="Risk, alerts, and recommended actions" />
    </QueryClientProvider>,
  );
}

describe("DashboardTopbar", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
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
      updateAppearance: vi.fn(),
    });

    mockFetchTopbarDataViaBff.mockResolvedValue({
      notifications: [
        {
          id: 11,
          public_id: "notif-critical",
          external_key: "risk:1",
          type: "WARD_RISK_HIGH",
          category: "trigger_review",
          group_key: null,
          severity: "CRITICAL",
          title: "North Kamagambo requires review",
          body: "A promoted high-risk ward is above the action threshold.",
          source_system: "risk",
          source_object_type: "ward",
          source_object_id: "1",
          href: "/overview?trigger_review=1",
          state: "NEW",
          recipient_scope: "GLOBAL",
          recipient_role: "ANALYST",
          recipient_user: null,
          ward: 1,
          ward_name: "North Kamagambo",
          requires_acknowledgement: true,
          dismissible: false,
          auto_resolve: true,
          pinned_until_actioned: true,
          metadata: {},
          created_at: "2026-04-25T08:15:00Z",
          seen_at: null,
          acknowledged_at: null,
          resolved_at: null,
          dismissed_at: null,
          expires_at: null,
          updated_at: "2026-04-25T08:15:00Z",
        },
        {
          id: 12,
          public_id: "notif-warning",
          external_key: "feed:alerts",
          type: "FEED_STALE",
          category: "system_health",
          group_key: "data_freshness",
          severity: "WARNING",
          title: "Alert log outdated",
          body: "Data is stale and may not reflect current conditions.",
          source_system: "etl",
          source_object_type: "feed",
          source_object_id: "alerts",
          href: "/system",
          state: "SEEN",
          recipient_scope: "GLOBAL",
          recipient_role: "ANALYST",
          recipient_user: null,
          ward: null,
          ward_name: "",
          requires_acknowledgement: false,
          dismissible: true,
          auto_resolve: true,
          pinned_until_actioned: false,
          metadata: { feed_label: "Alert log" },
          created_at: "2026-04-25T08:20:00Z",
          seen_at: "2026-04-25T08:25:00Z",
          acknowledged_at: null,
          resolved_at: null,
          dismissed_at: null,
          expires_at: null,
          updated_at: "2026-04-25T08:25:00Z",
        },
        {
          id: 13,
          public_id: "notif-warning-2",
          external_key: "feed:facilities",
          type: "FEED_STALE",
          category: "system_health",
          group_key: "data_freshness",
          severity: "WARNING",
          title: "Facility records outdated",
          body: "Data is stale and may not reflect current conditions.",
          source_system: "etl",
          source_object_type: "feed",
          source_object_id: "facilities",
          href: "/system",
          state: "NEW",
          recipient_scope: "GLOBAL",
          recipient_role: "ANALYST",
          recipient_user: null,
          ward: null,
          ward_name: "",
          requires_acknowledgement: false,
          dismissible: true,
          auto_resolve: true,
          pinned_until_actioned: false,
          metadata: { feed_label: "Facility records" },
          created_at: "2026-04-25T08:22:00Z",
          seen_at: null,
          acknowledged_at: null,
          resolved_at: null,
          dismissed_at: null,
          expires_at: null,
          updated_at: "2026-04-25T08:22:00Z",
        },
      ],
      unread_count: 2,
      highest_unread_severity: "CRITICAL",
      system_status: "ACTION_REQUIRED",
      feeds: [
        {
          id: "risks",
          label: "Risk feed",
          latest_timestamp: "2026-04-25T08:15:00Z",
          stale: false,
        },
      ],
      freshness: {
        last_model_run_at: "2026-04-25T08:05:00Z",
        last_data_sync_at: "2026-04-25T08:10:00Z",
        last_alert_ingestion_at: "2026-04-25T08:20:00Z",
        prediction_generated_at: "2026-04-25T08:15:00Z",
        freshness_state: "fresh",
      },
    });

    mockFetchNotificationStreamTokenViaBff.mockResolvedValue({
      token: "stream-token",
      websocket_path: "/ws/notifications/stream/",
      expires_in_seconds: 300,
    });
    mockMarkNotificationSeenViaBff.mockResolvedValue({});
    mockAcknowledgeNotificationViaBff.mockResolvedValue({});
    mockDismissNotificationViaBff.mockResolvedValue({});
    mockMarkAllNotificationsSeenViaBff.mockResolvedValue({});
    mockWebSocketClose.mockReset();
    mockWebSocketInstances.length = 0;

    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query.includes("prefers-color-scheme") ? false : true,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    Object.defineProperty(window, "WebSocket", {
      writable: true,
      value: class MockWebSocket {
        url: string;
        protocols?: string | string[];
        close = mockWebSocketClose;
        onmessage: ((event: { data: string }) => void) | null = null;
        onerror: (() => void) | null = null;
        onclose: (() => void) | null = null;

        constructor(url: string, protocols?: string | string[]) {
          this.url = url;
          this.protocols = protocols;
          mockWebSocketInstances.push(this);
        }
      },
    });
  });

  it("renders backend-owned unread counts and notification lifecycle controls", async () => {
    const user = userEvent.setup();

    renderTopbar();

    await waitFor(() => {
      expect(mockFetchTopbarDataViaBff).toHaveBeenCalled();
    });
    expect(mockFetchNotificationStreamTokenViaBff).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Open notifications" }));

    await waitFor(() => {
      expect(screen.getByText("Notifications")).toBeInTheDocument();
    });

    expect(screen.getByText("System status:")).toBeInTheDocument();
    expect(screen.getByText("Action required")).toBeInTheDocument();
    expect(screen.getByText("1 critical alert unread")).toBeInTheDocument();
    expect(screen.getByText("2 unread")).toBeInTheDocument();
    expect(screen.getByText("North Kamagambo requires review")).toBeInTheDocument();
    expect(screen.getByText("Data freshness issue detected")).toBeInTheDocument();
    expect(screen.getByText("2 feeds are stale: Facility records, Alert log.")).toBeInTheDocument();
    expect(screen.queryByText("NEW")).not.toBeInTheDocument();
    expect(screen.queryByText("SEEN")).not.toBeInTheDocument();
    expect(
      screen
        .getAllByRole("link", { name: "Review" })
        .some((link) => link.getAttribute("href") === "/overview?trigger_review=1"),
    ).toBe(true);
    expect(
      screen
        .getAllByRole("link", { name: "Review system state" })
        .some((link) => link.getAttribute("href") === "/system"),
    ).toBe(true);

    await user.click(screen.getByRole("button", { name: "Unread only" }));
    expect(screen.queryByText("Data freshness issue detected")).not.toBeInTheDocument();
    expect(screen.getByText("Facility records outdated")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Unread only" }));

    await user.click(screen.getByRole("button", { name: "Acknowledge" }));
    expect(mockAcknowledgeNotificationViaBff).toHaveBeenCalledWith("notif-critical");

    await user.click(screen.getByRole("button", { name: "Mark seen" }));
    expect(mockMarkNotificationSeenViaBff).toHaveBeenCalledWith("notif-warning-2");

    await user.click(screen.getByRole("button", { name: "More actions for grouped notifications" }));
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(mockDismissNotificationViaBff).toHaveBeenCalledWith("notif-warning");
    expect(mockDismissNotificationViaBff).toHaveBeenCalledWith("notif-warning-2");

    await user.click(screen.getByRole("button", { name: "Mark all seen" }));
    expect(mockMarkAllNotificationsSeenViaBff).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /View details/i }));
    expect(screen.getByText("Data feeds stale")).toBeInTheDocument();
    expect(screen.getByText("Delivery failures")).toBeInTheDocument();
    expect(screen.getByText("Warning signals unread")).toBeInTheDocument();
    expect(screen.getByText("Based on latest feeds and open notifications")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /System status:/i }));
    expect(mockPush).toHaveBeenCalledWith("/system");
  });

  it("reconciles websocket notification events in memory without waiting for a refetch", async () => {
    const user = userEvent.setup();

    renderTopbar();

    await waitFor(() => {
      expect(mockFetchTopbarDataViaBff).toHaveBeenCalledTimes(1);
      expect(mockWebSocketInstances).toHaveLength(1);
    });
    expect(mockWebSocketInstances[0].url).not.toContain("token=");
    expect(mockWebSocketInstances[0].protocols).toEqual(["cchis.notifications", "stream-token"]);

    mockWebSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        event: "notification.connected",
        unread_count: 1,
        highest_unread_severity: "WARNING",
        system_status: "DATA_FRESHNESS_DEGRADED",
        feeds: [
          {
            id: "risks",
            label: "Risk feed",
            latest_timestamp: "2026-04-25T08:15:00Z",
            stale: false,
          },
        ],
        freshness: {
          last_model_run_at: "2026-04-25T08:05:00Z",
          last_data_sync_at: "2026-04-25T08:10:00Z",
          last_alert_ingestion_at: "2026-04-25T08:20:00Z",
          prediction_generated_at: "2026-04-25T08:15:00Z",
          freshness_state: "fresh",
        },
      }),
    });

    await user.click(screen.getByRole("button", { name: "Open notifications" }));

    await waitFor(() => {
      expect(screen.getByText("1 unread")).toBeInTheDocument();
    });

    mockWebSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        event: "notification.created",
        unread_count: 2,
        highest_unread_severity: "CRITICAL",
        system_status: "ACTION_REQUIRED",
        changed_fields: ["state"],
        notification: {
          id: 13,
          public_id: "notif-live",
          external_key: "alert:13",
          type: "ALERT_FAILED",
          category: "alert_delivery",
          group_key: "alert_delivery_failures",
          severity: "CRITICAL",
          title: "Live alert failure",
          body: "A dashboard alert failed and needs review.",
          source_system: "alerts",
          source_object_type: "alert",
          source_object_id: "13",
          href: "/alerts/13",
          state: "NEW",
          recipient_scope: "GLOBAL",
          recipient_role: "ANALYST",
          recipient_user: null,
          ward: null,
          ward_name: "",
          requires_acknowledgement: true,
          dismissible: false,
          auto_resolve: true,
          pinned_until_actioned: true,
          metadata: {},
          created_at: "2026-04-25T08:30:00Z",
          seen_at: null,
          acknowledged_at: null,
          resolved_at: null,
          dismissed_at: null,
          expires_at: null,
          updated_at: "2026-04-25T08:30:00Z",
        },
      }),
    });

    await waitFor(() => {
      expect(screen.getByText("2 unread")).toBeInTheDocument();
    });
    expect(screen.getByText("Live alert failure")).toBeInTheDocument();
    expect(mockFetchTopbarDataViaBff).toHaveBeenCalledTimes(1);

    mockWebSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        event: "notification.updated",
        unread_count: 1,
        highest_unread_severity: "WARNING",
        system_status: "DATA_FRESHNESS_DEGRADED",
        changed_fields: ["state"],
        notification: {
          id: 13,
          public_id: "notif-live",
          external_key: "alert:13",
          type: "ALERT_FAILED",
          severity: "CRITICAL",
          title: "Live alert failure",
          body: "A dashboard alert failed and needs review.",
          source_system: "alerts",
          source_object_type: "alert",
          source_object_id: "13",
          href: "/alerts/13",
          state: "ACKNOWLEDGED",
          recipient_scope: "GLOBAL",
          recipient_role: "ANALYST",
          recipient_user: null,
          ward: null,
          ward_name: "",
          requires_acknowledgement: true,
          dismissible: false,
          auto_resolve: true,
          pinned_until_actioned: true,
          metadata: {},
          created_at: "2026-04-25T08:30:00Z",
          seen_at: "2026-04-25T08:31:00Z",
          acknowledged_at: "2026-04-25T08:31:00Z",
          resolved_at: null,
          dismissed_at: null,
          expires_at: null,
          updated_at: "2026-04-25T08:31:00Z",
        },
      }),
    });

    await waitFor(() => {
      expect(screen.getByText("1 unread")).toBeInTheDocument();
      expect(screen.getByText("ACKNOWLEDGED")).toBeInTheDocument();
    });
    expect(mockFetchTopbarDataViaBff).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Open sync summary" }));

    mockWebSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        event: "topbar.snapshot",
        unread_count: 1,
        highest_unread_severity: "WARNING",
        system_status: "DATA_FRESHNESS_DEGRADED",
        feeds: [
          {
            id: "risks",
            label: "Risk feed",
            latest_timestamp: null,
            stale: true,
          },
        ],
        freshness: {
          last_model_run_at: "2026-04-25T01:00:00Z",
          last_data_sync_at: "2026-04-25T01:15:00Z",
          last_alert_ingestion_at: null,
          prediction_generated_at: null,
          freshness_state: "stale",
        },
      }),
    });

    await waitFor(() => {
      expect(screen.getByText("No data")).toBeInTheDocument();
    });
    expect(mockFetchTopbarDataViaBff).toHaveBeenCalledTimes(1);
  });

  it("shows explicit trust labels for model, data, alerts, predictions, and notification transport", async () => {
    const user = userEvent.setup();

    renderTopbar();

    await waitFor(() => {
      expect(mockFetchTopbarDataViaBff).toHaveBeenCalled();
      expect(mockWebSocketInstances).toHaveLength(1);
    });

    mockWebSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        event: "notification.connected",
        unread_count: 1,
        highest_unread_severity: "WARNING",
        system_status: "DATA_FRESHNESS_DEGRADED",
        feeds: [
          {
            id: "risks",
            label: "Risk feed",
            latest_timestamp: "2026-04-25T08:15:00Z",
            stale: false,
          },
        ],
        freshness: {
          last_model_run_at: "2026-04-25T08:05:00Z",
          last_data_sync_at: "2026-04-25T08:10:00Z",
          last_alert_ingestion_at: "2026-04-25T08:20:00Z",
          prediction_generated_at: "2026-04-25T08:15:00Z",
          freshness_state: "fresh",
        },
      }),
    });

    await user.click(screen.getByRole("button", { name: "Open sync summary" }));

    expect(screen.getByText("Operational trust")).toBeInTheDocument();
    expect(screen.getByText("Model updated")).toBeInTheDocument();
    expect(screen.getByText("Data sync")).toBeInTheDocument();
    expect(screen.getByText("Alerts refreshed")).toBeInTheDocument();
    expect(screen.getByText("Prediction generated")).toBeInTheDocument();
    expect(screen.getByText("Notifications live")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
  });

  it("still groups stale feed notifications when older payloads omit category metadata", async () => {
    const user = userEvent.setup();

    mockFetchTopbarDataViaBff.mockResolvedValueOnce({
      notifications: [
        {
          id: 21,
          public_id: "legacy-feed-a",
          external_key: "feed:facilities",
          type: "FEED_STALE",
          category: "general",
          group_key: null,
          severity: "WARNING",
          title: "Facility records: stale",
          body: "This operational feed is stale and should not be treated as fully fresh dashboard truth.",
          source_system: "etl",
          source_object_type: "feed",
          source_object_id: "facilities",
          href: "/system",
          state: "NEW",
          recipient_scope: "GLOBAL",
          recipient_role: "ANALYST",
          recipient_user: null,
          ward: null,
          ward_name: "",
          requires_acknowledgement: false,
          dismissible: true,
          auto_resolve: true,
          pinned_until_actioned: false,
          metadata: { feed_label: "Facility records" },
          created_at: "2026-04-25T08:20:00Z",
          seen_at: null,
          acknowledged_at: null,
          resolved_at: null,
          dismissed_at: null,
          expires_at: null,
          updated_at: "2026-04-25T08:20:00Z",
        },
        {
          id: 22,
          public_id: "legacy-feed-b",
          external_key: "feed:alerts",
          type: "FEED_STALE",
          category: "general",
          group_key: null,
          severity: "WARNING",
          title: "Alert log: stale",
          body: "This operational feed is stale and should not be treated as fully fresh dashboard truth.",
          source_system: "etl",
          source_object_type: "feed",
          source_object_id: "alerts",
          href: "/system",
          state: "NEW",
          recipient_scope: "GLOBAL",
          recipient_role: "ANALYST",
          recipient_user: null,
          ward: null,
          ward_name: "",
          requires_acknowledgement: false,
          dismissible: true,
          auto_resolve: true,
          pinned_until_actioned: false,
          metadata: { feed_label: "Alert log" },
          created_at: "2026-04-25T08:18:00Z",
          seen_at: null,
          acknowledged_at: null,
          resolved_at: null,
          dismissed_at: null,
          expires_at: null,
          updated_at: "2026-04-25T08:18:00Z",
        },
      ],
      unread_count: 2,
      highest_unread_severity: "WARNING",
      system_status: "DATA_FRESHNESS_DEGRADED",
      feeds: [
        {
          id: "alerts",
          label: "Alert log",
          latest_timestamp: null,
          stale: true,
        },
      ],
      freshness: {
        last_model_run_at: "2026-04-25T08:05:00Z",
        last_data_sync_at: "2026-04-25T08:10:00Z",
        last_alert_ingestion_at: null,
        prediction_generated_at: "2026-04-25T08:15:00Z",
        freshness_state: "stale",
      },
    });

    renderTopbar();

    await waitFor(() => {
      expect(mockFetchTopbarDataViaBff).toHaveBeenCalled();
    });

    await user.click(screen.getByRole("button", { name: "Open notifications" }));

    expect(screen.getByText("Data freshness issue detected")).toBeInTheDocument();
    expect(screen.getByText("2 feeds are stale: Facility records, Alert log.")).toBeInTheDocument();
    expect(screen.queryByText("Facility records: stale")).not.toBeInTheDocument();
  });

  it(
    "reconnects the websocket stream after disconnect",
    async () => {
      renderTopbar();

      await waitFor(() => {
        expect(mockFetchNotificationStreamTokenViaBff).toHaveBeenCalledTimes(1);
        expect(mockWebSocketInstances).toHaveLength(1);
      });

      mockWebSocketInstances[0].onclose?.();

      await waitFor(() => {
        expect(mockFetchNotificationStreamTokenViaBff).toHaveBeenCalledTimes(2);
        expect(mockWebSocketInstances).toHaveLength(2);
      }, { timeout: 7000 });
    },
    10000,
  );
});
