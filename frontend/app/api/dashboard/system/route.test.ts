import { describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/dashboard/system/route";

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

describe("dashboard system route", () => {
  it("loads ward and risk status from the Migori County scope only", async () => {
    mockFetchBackendJson
      .mockResolvedValueOnce({ count: 40, next: null, previous: null, results: [] })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockResolvedValueOnce([]);

    const response = await GET(new Request("http://localhost:3000/api/dashboard/system"));
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.wards.count).toBe(40);
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      1,
      "/wards/?page_size=100&county=Migori",
      expect.objectContaining({ cookieHeader: "" }),
    );
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      2,
      "/risk-score/latest/?county=Migori",
      expect.objectContaining({ cookieHeader: "" }),
    );
  });
});
