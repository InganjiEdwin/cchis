import { describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/dashboard/operational-metrics/route";

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

describe("dashboard operational metrics route", () => {
  it("forwards the supported M&E dashboard filters to the backend contract", async () => {
    mockFetchBackendJson.mockResolvedValueOnce({
      schema_version: "operational-kpi-dashboard-v1",
      filters: {},
      available_filters: { wards: [], sub_counties: [], source_channels: [] },
      summary: {},
      panels: {},
      metrics: [],
    });

    const request = new Request(
      "http://localhost:3000/api/dashboard/operational-metrics?date_from=2026-05-01&date_to=2026-05-03&ward_id=7&sub_county=Nyatike&source_channel=SMS&ignored=true",
      {
        headers: { cookie: "sessionid=test" },
      },
    );
    const response = await GET(request);

    expect(response.status).toBe(200);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/operational-metrics/dashboard/?date_from=2026-05-01&date_to=2026-05-03&ward_id=7&sub_county=Nyatike&source_channel=SMS",
      expect.objectContaining({ cookieHeader: "sessionid=test" }),
    );
  });
});
