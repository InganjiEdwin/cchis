import { describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/dashboard/facilities/route";

const mockFetchBackendJson = vi.fn();

vi.mock("@/lib/server-api", () => ({
  ServerApiError: class ServerApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  fetchBackendJson: (...args: unknown[]) => mockFetchBackendJson(...args),
}));

describe("dashboard facilities route", () => {
  it("aggregates every backend page while preserving the backend-owned decision summary", async () => {
    mockFetchBackendJson
      .mockResolvedValueOnce({
        count: 102,
        next: "http://backend.test/api/v1/facilities/?page=2&page_size=100&ordering=ward__name,name",
        previous: null,
        results: [
          {
            id: 1,
            public_id: "FAC-001",
            name: "Facility A",
            facility_code: "A",
            ward: 1,
            ward_name: "Ward A",
            sub_county: "Rongo",
            facility_type: "hospital",
            ownership: "public",
            level: "LEVEL_3",
            ward_risk_level: "HIGH",
            ward_risk_score: 0.8,
            is_active: true,
            point: null,
            contact_phone: "",
            updated_at: "2026-04-28T10:00:00Z",
          },
        ],
        decision_summary: {
          state: "REVIEW",
          headline: "Review top readiness priorities",
          body: "Top review priority: Facility Z.",
          confidence: "NORMAL",
          confidence_reason: null,
          top_priorities: [
            {
              facility_id: 102,
              facility_name: "Facility Z",
              ward_id: 2,
              ward_name: "Ward Z",
              priority_rank: 1,
              priority_label: "Top review priority",
              reason_codes: ["HIGH_READINESS_DIFFERENCE"],
              reason_text: "High calculated readiness difference.",
              review_href: null,
            },
          ],
          related_surfaces: {
            has_linked_alerts: false,
            linked_alert_count: 0,
          },
        },
      })
      .mockResolvedValueOnce({
        count: 102,
        next: null,
        previous: "http://backend.test/api/v1/facilities/?page_size=100&ordering=ward__name,name",
        results: [
          {
            id: 102,
            public_id: "FAC-102",
            name: "Facility Z",
            facility_code: "Z",
            ward: 2,
            ward_name: "Ward Z",
            sub_county: "Migori",
            facility_type: "dispensary",
            ownership: "public",
            level: "LEVEL_2",
            ward_risk_level: "HIGH",
            ward_risk_score: 0.9,
            is_active: true,
            point: null,
            contact_phone: "",
            updated_at: "2026-04-28T10:01:00Z",
          },
        ],
      });

    const request = new Request("http://localhost:3000/api/dashboard/facilities");
    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.results).toHaveLength(2);
    expect(payload.results[1].id).toBe(102);
    expect(payload.decision_summary.top_priorities[0].facility_id).toBe(102);
    expect(payload.next).toBeNull();
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      2,
      "/api/v1/facilities/?page=2&page_size=100&ordering=ward__name,name",
      expect.objectContaining({ cookieHeader: "" }),
    );
  });
});
