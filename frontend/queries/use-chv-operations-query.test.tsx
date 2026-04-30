import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useChvOperationsQuery } from "@/queries/use-chv-operations-query";

const mockFetchChvOperationsDataViaBff = vi.fn();
const mockFetchWardRiskDataViaBff = vi.fn();
const mockFetchAlertsDataViaBff = vi.fn();
const mockFetchWardMapViaBff = vi.fn();
const mockFetchChvCoverageRequestsViaBff = vi.fn();

vi.mock("@/lib/dashboard", async () => {
  const actual = await vi.importActual<typeof import("@/lib/dashboard")>("@/lib/dashboard");
  return {
    ...actual,
    fetchChvOperationsDataViaBff: (...args: unknown[]) => mockFetchChvOperationsDataViaBff(...args),
    fetchWardRiskDataViaBff: (...args: unknown[]) => mockFetchWardRiskDataViaBff(...args),
    fetchAlertsDataViaBff: (...args: unknown[]) => mockFetchAlertsDataViaBff(...args),
    fetchWardMapViaBff: (...args: unknown[]) => mockFetchWardMapViaBff(...args),
    fetchChvCoverageRequestsViaBff: (...args: unknown[]) => mockFetchChvCoverageRequestsViaBff(...args),
  };
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe("useChvOperationsQuery", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("includes coverage requests and derives ward workflow summaries", async () => {
    mockFetchChvOperationsDataViaBff.mockResolvedValueOnce([
      {
        id: 1,
        ward: 12,
        ward_name: "North Kamagambo",
        name: "Akinyi",
        phone_number: "+254700000001",
        language: "en",
        is_active: true,
        created_at: "2026-04-28T08:00:00Z",
        last_sync_at: "2026-04-28T08:30:00Z",
        last_activity_at: "2026-04-28T08:25:00Z",
        operational_status: "ACTIVE",
        sync_health: "ONLINE",
        triage_sessions_24h: 2,
        referrals_24h: 1,
        sync_payloads_24h: 1,
        ussd_sessions_24h: 0,
        ward_alerts_total: 2,
        ward_alerts_delivered: 1,
      },
    ]);
    mockFetchWardRiskDataViaBff.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      latestRisks: [
        {
          ward_id: 12,
          ward_name: "North Kamagambo",
          risk_level: "HIGH",
          risk_score: 0.82,
          predicted_cases: 10,
          generated_at: "2026-04-28T08:00:00Z",
        },
      ],
      results: [],
    });
    mockFetchAlertsDataViaBff.mockResolvedValueOnce({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    mockFetchWardMapViaBff.mockResolvedValueOnce({
      type: "FeatureCollection",
      metadata: {
        county: "Migori",
        geometry_source: "test",
        geometry_feature_count: 1,
        expected_ward_count: 1,
        missing_source_wards: [],
        backend_ward_match_count: 1,
        returned_feature_count: 1,
        backend_wards_without_geometry: [],
        placeholder_geometry_detected: false,
        geometry_note: null,
      },
      features: [],
    });
    mockFetchChvCoverageRequestsViaBff.mockResolvedValueOnce({
      count: 2,
      next: null,
      previous: null,
      results: [
        {
          public_id: "req-1",
          ward: 12,
          ward_name: "North Kamagambo",
          ward_public_id: "ward-12",
          requested_by: 3,
          requested_by_username: "supervisor",
          status: "OPEN",
          priority: "HIGH",
          trigger_source: "MANUAL",
          linked_alert_public_ids: [],
          linked_alerts_summary: [],
          reason: "Coverage gap",
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
          request_age: 1200,
          is_overdue: true,
          sla_status: "OVERDUE",
          assignments: [],
          events: [],
          created_at: "2026-04-28T08:00:00Z",
          updated_at: "2026-04-28T08:00:00Z",
        },
        {
          public_id: "req-2",
          ward: 12,
          ward_name: "North Kamagambo",
          ward_public_id: "ward-12",
          requested_by: 3,
          requested_by_username: "supervisor",
          status: "IN_PROGRESS",
          priority: "HIGH",
          trigger_source: "MANUAL",
          linked_alert_public_ids: [],
          linked_alerts_summary: [],
          reason: "Assignment active",
          requested_chv_count: 1,
          notes: "",
          assigned_to_user: null,
          assigned_to_username: null,
          assigned_to_team: "",
          reviewed_by: 1,
          reviewed_by_username: "admin",
          reviewed_at: "2026-04-28T09:00:00Z",
          review_decision_reason: "",
          expected_response_by: "2026-04-28T15:00:00Z",
          resolved_at: null,
          request_age: 600,
          is_overdue: false,
          sla_status: "ON_TRACK",
          assignments: [
            {
              public_id: "assign-1",
              coverage_request: 2,
              ward: 12,
              ward_name: "North Kamagambo",
              ward_public_id: "ward-12",
              chv: 1,
              chv_name: "Akinyi",
              chv_phone_number: "+254700000001",
              assigned_by: 1,
              assigned_by_username: "admin",
              status: "ACTIVE",
              start_at: "2026-04-28T09:10:00Z",
              end_at: null,
              notes: "",
              created_at: "2026-04-28T09:10:00Z",
              updated_at: "2026-04-28T09:10:00Z",
            },
          ],
          events: [],
          created_at: "2026-04-28T09:00:00Z",
          updated_at: "2026-04-28T09:10:00Z",
        },
      ],
    });

    const { result } = renderHook(() => useChvOperationsQuery(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockFetchChvCoverageRequestsViaBff).toHaveBeenCalledWith({});
    expect(result.current.data?.coverageRequests).toHaveLength(2);
    expect(result.current.data?.coverageByWard[12]).toMatchObject({
      wardId: 12,
      liveRequestCount: 2,
      overdueRequestCount: 1,
      activeAssignmentCount: 1,
    });
    expect(result.current.data?.coverageByWard[12].latestRequest?.public_id).toBe("req-2");
  });

  it("aggregates coverage requests across paginated pages", async () => {
    mockFetchChvOperationsDataViaBff.mockResolvedValueOnce([]);
    mockFetchWardRiskDataViaBff.mockResolvedValueOnce({
      count: 0,
      next: null,
      previous: null,
      latestRisks: [],
      results: [],
    });
    mockFetchAlertsDataViaBff.mockResolvedValueOnce({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    mockFetchWardMapViaBff.mockResolvedValueOnce({
      type: "FeatureCollection",
      metadata: {
        county: "Migori",
        geometry_source: "test",
        geometry_feature_count: 0,
        expected_ward_count: 0,
        missing_source_wards: [],
        backend_ward_match_count: 0,
        returned_feature_count: 0,
        backend_wards_without_geometry: [],
        placeholder_geometry_detected: false,
        geometry_note: null,
      },
      features: [],
    });
    mockFetchChvCoverageRequestsViaBff
      .mockResolvedValueOnce({
        count: 2,
        next: "/api/dashboard/chvs/coverage-requests?page=2",
        previous: null,
        results: [
          {
            public_id: "req-1",
            ward: 12,
            ward_name: "North Kamagambo",
            ward_public_id: "ward-12",
            requested_by: 3,
            requested_by_username: "supervisor",
            status: "OPEN",
            priority: "HIGH",
            trigger_source: "MANUAL",
            linked_alert_public_ids: [],
            linked_alerts_summary: [],
            reason: "Coverage gap",
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
            request_age: 1200,
            is_overdue: false,
            sla_status: "ON_TRACK",
            assignments: [],
            events: [],
            created_at: "2026-04-28T08:00:00Z",
            updated_at: "2026-04-28T08:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        count: 2,
        next: null,
        previous: "/api/dashboard/chvs/coverage-requests?page=1",
        results: [
          {
            public_id: "req-2",
            ward: 18,
            ward_name: "South Kamagambo",
            ward_public_id: "ward-18",
            requested_by: 3,
            requested_by_username: "supervisor",
            status: "APPROVED",
            priority: "MEDIUM",
            trigger_source: "MANUAL",
            linked_alert_public_ids: [],
            linked_alerts_summary: [],
            reason: "Awaiting assignment",
            requested_chv_count: 1,
            notes: "",
            assigned_to_user: null,
            assigned_to_username: null,
            assigned_to_team: "",
            reviewed_by: 1,
            reviewed_by_username: "admin",
            reviewed_at: "2026-04-28T09:00:00Z",
            review_decision_reason: "",
            expected_response_by: "2026-04-28T14:00:00Z",
            resolved_at: null,
            request_age: 600,
            is_overdue: false,
            sla_status: "ON_TRACK",
            assignments: [],
            events: [],
            created_at: "2026-04-28T09:00:00Z",
            updated_at: "2026-04-28T09:00:00Z",
          },
        ],
      });

    const { result } = renderHook(() => useChvOperationsQuery(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockFetchChvCoverageRequestsViaBff).toHaveBeenNthCalledWith(1, {});
    expect(mockFetchChvCoverageRequestsViaBff).toHaveBeenNthCalledWith(2, { page: 2 });
    expect(result.current.data?.coverageRequests).toHaveLength(2);
    expect(result.current.data?.coverageByWard[12]?.liveRequestCount).toBe(1);
    expect(result.current.data?.coverageByWard[18]?.liveRequestCount).toBe(1);
  });
});
