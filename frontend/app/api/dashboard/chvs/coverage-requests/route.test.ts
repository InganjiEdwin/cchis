import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "@/app/api/dashboard/chvs/coverage-requests/route";
import { ServerApiError } from "@/lib/server-api";

const mockFetchBackendJson = vi.fn();

vi.mock("@/lib/server-api", () => ({
  ServerApiError: class ServerApiError extends Error {
    status: number;
    payload?: Record<string, unknown>;

    constructor(status: number, message: string, payload?: Record<string, unknown>) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
  fetchBackendJson: (...args: unknown[]) => mockFetchBackendJson(...args),
}));

describe("dashboard CHV coverage request route", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("forwards ward filters so supervisor scoping remains backend-owned", async () => {
    mockFetchBackendJson.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          public_id: "CCR-1",
          ward_id: 7,
          ward_name: "North Kadem",
          status: "OPEN",
        },
      ],
    });

    const response = await GET(
      new Request("http://localhost/api/dashboard/chvs/coverage-requests?ward_id=7&status=OPEN", {
        headers: { cookie: "sessionid=supervisor" },
      }),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.results[0].ward_id).toBe(7);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/chv/coverage-requests/?ward_id=7&status=OPEN",
      expect.objectContaining({ cookieHeader: "sessionid=supervisor" }),
    );
  });

  it("preserves backend 403 payloads when analysts try to read CHV coverage requests", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await GET(
      new Request("http://localhost/api/dashboard/chvs/coverage-requests", {
        headers: { cookie: "sessionid=analyst" },
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
  });

  it("preserves backend step-up payloads so the dashboard can prompt for the right purpose", async () => {
    const stepUpPayload = {
      detail: "This action needs a quick security check. Enter your authenticator code to continue.",
      code: "step_up_required",
      purpose: "operational_data",
    };
    mockFetchBackendJson.mockRejectedValueOnce(
      new ServerApiError(403, "This action needs a quick security check.", stepUpPayload),
    );

    const response = await POST(
      new Request("http://localhost/api/dashboard/chvs/coverage-requests", {
        method: "POST",
        headers: {
          cookie: "cchis_access=access",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          ward_id: 1,
          priority: "HIGH",
          reason: "Coverage gap detected.",
          requested_chv_count: 1,
        }),
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(stepUpPayload);
  });
});
