import { describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/dashboard/chvs/coverage-requests/route";
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
