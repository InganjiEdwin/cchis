import { describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/session/activity/route";

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

describe("session activity route", () => {
  it("forwards paginated activity filters to the backend", async () => {
    mockFetchBackendJson.mockResolvedValueOnce({
      count: 0,
      next: null,
      previous: null,
      results: [],
      filters: {
        event_type: "LOGIN_FAILED",
        status: "FAILED",
        date_from: "2026-05-01",
        date_to: "2026-05-02",
        security_only: true,
        include_refresh_events: true,
        page: 2,
        page_size: 25,
      },
      capabilities: {
        can_view_own_activity: true,
        mode: "self_scoped_auth_activity",
      },
    });

    const request = new Request(
      "http://localhost/api/session/activity?page=2&page_size=25&event_type=LOGIN_FAILED&status=FAILED&date_from=2026-05-01&date_to=2026-05-02&security_only=true&include_refresh_events=true&ignored=true",
      {
        headers: {
          cookie: "session=abc",
        },
      },
    );

    const response = await GET(request);

    expect(response.status).toBe(200);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/auth/me/activity/?page=2&page_size=25&event_type=LOGIN_FAILED&status=FAILED&date_from=2026-05-01&date_to=2026-05-02&security_only=true&include_refresh_events=true",
      {
        method: "GET",
        cookieHeader: "session=abc",
      },
    );
  });
});
