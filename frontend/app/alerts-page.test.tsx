import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AlertsPage from "@/app/(dashboard)/alerts/page";

const mockUseAuth = vi.fn();
const mockUseAlertsQuery = vi.fn();
const mockUseRouter = vi.fn();
const mockUseSearchParams = vi.fn();
const mockUseCreateChvCoverageRequestFromAlertMutation = vi.fn();
const mockUseCreateChvCoverageRequestMutation = vi.fn();
const mockUseLiveChvCoverageRequestForWardQuery = vi.fn();
const mockCreateSensitiveExportViaBff = vi.fn();
const mockDownloadSensitiveExportViaBff = vi.fn();
const mockDownloadSensitiveExportFile = vi.fn();

function buildAlert(overrides: Record<string, unknown> = {}) {
  const id = typeof overrides.id === "number" ? overrides.id : 1;

  return {
    id: 1,
    public_id: `00000000-0000-0000-0000-${String(id).padStart(12, "0")}`,
    ward: 12,
    ward_name: "North Kamagambo",
    risk_score: 86,
    channel: "SMS",
    recipient: "Supervisor",
    message: "Pilot alert. Risk level: HIGH. Predicted cases: 18.",
    status: "DELIVERED",
    delivery_backend: "twilio",
    attempt_count: 1,
    max_attempts: 3,
    last_attempted_at: null,
    next_retry_at: null,
    external_id: "",
    sent_at: "2026-04-28T07:50:00Z",
    created_at: "2026-04-28T07:45:00Z",
    error_message: "",
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

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => mockUseRouter(),
  useSearchParams: () => mockUseSearchParams(),
}));

vi.mock("@/queries/use-alerts-query", () => ({
  useAlertsQuery: (...args: unknown[]) => mockUseAlertsQuery(...args),
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

describe("AlertsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseRouter.mockReturnValue({
      push: vi.fn(),
    });
    mockUseSearchParams.mockReturnValue(new URLSearchParams());

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

    mockUseAlertsQuery.mockReturnValue({
      data: [
        buildAlert({
          id: 1,
          ward_name: "North Kamagambo",
          status: "DELIVERED",
          risk_score: 18,
          sent_at: "2026-04-28T05:00:00Z",
          created_at: "2026-04-28T04:58:00Z",
        }),
        buildAlert({
          id: 2,
          ward_name: "Got Kachola",
          status: "RETRY_PENDING",
          risk_score: 61,
          sent_at: null,
          created_at: "2026-04-28T06:00:00Z",
          error_message: "Transport retry still pending.",
        }),
        buildAlert({
          id: 3,
          ward_name: "North Kamagambo",
          status: "FAILED",
          risk_score: 72,
          sent_at: null,
          created_at: "2026-04-28T07:00:00Z",
          error_message: "Delivery failed after final attempt.",
        }),
      ],
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
      public_id: "export-alerts-1",
      approval_state: "APPROVED",
    });
    mockDownloadSensitiveExportViaBff.mockResolvedValue({
      public_id: "export-alerts-1",
      filename: "alerts-monitoring.csv",
      content_type: "text/csv",
      payload: "csv-payload",
      payload_sha256: "sha256",
      expires_at: "2026-05-30T00:00:00Z",
    });
  });

  it("centers the page on alerts that require attention before the inventory table", async () => {
    render(React.createElement(AlertsPage));

    await waitFor(() => {
      expect(mockUseAlertsQuery).toHaveBeenCalledWith({ enabled: true });
    });

    expect(await screen.findByRole("heading", { name: "Requires attention" })).toBeInTheDocument();
    expect(screen.getByText("Retry-pending and failed alerts that still need operator review.")).toBeInTheDocument();
    expect(screen.getByText("Queue status")).toBeInTheDocument();
    expect(screen.queryByText("Alert Record In Focus")).not.toBeInTheDocument();
    expect(screen.queryByText("Alert Pressure By Ward")).not.toBeInTheDocument();
    expect(screen.queryByText("Next alert to review")).not.toBeInTheDocument();
    expect(screen.queryByText("Wards with unresolved alerts")).not.toBeInTheDocument();
    expect(screen.queryByText("Read-path only")).not.toBeInTheDocument();
  });

  it("shows action-oriented summary cards and prioritizes actionable alerts in the table", async () => {
    render(React.createElement(AlertsPage));

    expect(await screen.findByRole("heading", { name: "Requires attention" })).toBeInTheDocument();
    expect(screen.getByText("Delivered successfully")).toBeInTheDocument();
    expect(screen.getByText("Delivery failures")).toBeInTheDocument();
    expect(screen.getByText("Alert records already delivered in the visible scope.")).toBeInTheDocument();

    const rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByText("AL-0003")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Failed")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Needs escalation")).toBeInTheDocument();
    expect(within(rows[2]).getByText("AL-0002")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Retry")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Needs review")).toBeInTheDocument();
  });

  it("hides sensitive CSV export from analyst alert views", async () => {
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

    render(React.createElement(AlertsPage));

    expect(await screen.findByRole("heading", { name: "Requires attention" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Export CSV/i })).not.toBeInTheDocument();
  });

  it("requests and downloads alert CSV through the sensitive export ledger", async () => {
    render(React.createElement(AlertsPage));

    fireEvent.click(await screen.findByRole("button", { name: /Export CSV/i }));

    await waitFor(() => {
      expect(mockCreateSensitiveExportViaBff).toHaveBeenCalledWith({
        export_type: "ALERT_LIST_CSV",
        purpose: "Operator requested alert monitoring CSV for delivery review.",
        filters: { alert_ids: [3, 2, 1] },
      });
    });
    expect(mockDownloadSensitiveExportViaBff).toHaveBeenCalledWith("export-alerts-1");
    expect(mockDownloadSensitiveExportFile).toHaveBeenCalledWith(
      expect.objectContaining({ filename: "alerts-monitoring.csv" }),
    );
    expect(await screen.findByText("Sensitive export downloaded and audited.")).toBeInTheDocument();
  });

  it("uses review language and exposes the selected alert as operational work", async () => {
    render(React.createElement(AlertsPage));

    expect((await screen.findAllByText("Open review")).length).toBeGreaterThan(1);
    expect(screen.getAllByText("Open review").length).toBeGreaterThan(1);
    expect(screen.getAllByText(/delivery failure requires operator review/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/retry pending in the backend still needs review/i)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Open review" })[0]);

    expect(await screen.findByText("Delivery failed after final attempt.")).toBeInTheDocument();
    expect(screen.getByText(/Request CHV coverage only through the real alert-linked workflow/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request CHV coverage" })).toBeInTheDocument();
  });

  it("routes the selected alert through the alert-linked CHV request handoff", async () => {
    const push = vi.fn();
    const prefillMutateAsync = vi.fn().mockResolvedValue({
      mode: "EXISTING_LIVE_REQUEST",
      detail: "A live CHV coverage request already exists for this ward.",
      create_defaults: null,
      existing_request: {
        public_id: "req-existing-1",
      },
    });

    mockUseRouter.mockReturnValue({ push });
    mockUseCreateChvCoverageRequestFromAlertMutation.mockReturnValue({
      mutateAsync: prefillMutateAsync,
      isPending: false,
      error: null,
    });

    render(React.createElement(AlertsPage));

    fireEvent.click((await screen.findAllByRole("button", { name: "Open review" }))[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Request CHV coverage" }));

    await waitFor(() => {
      expect(prefillMutateAsync).toHaveBeenCalledWith({
        alert_public_ids: ["00000000-0000-0000-0000-000000000003"],
      });
    });

    expect(push).toHaveBeenCalledWith("/chvs/requests/req-existing-1");
  });

  it("shows a truthful view CTA when the selected alert already has a live ward request", async () => {
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
        public_id: "req-live-ward",
      },
      isPending: false,
    });

    render(React.createElement(AlertsPage));

    fireEvent.click((await screen.findAllByRole("button", { name: "Open review" }))[0]);

    expect(
      await screen.findByText(
        "A live CHV coverage request already exists for this ward, so this alert should open that request instead of starting a duplicate workflow.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "View CHV coverage request" }));

    expect(push).toHaveBeenCalledWith("/chvs/requests/req-live-ward");
    expect(prefillMutateAsync).not.toHaveBeenCalled();
  });
});
