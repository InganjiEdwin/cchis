import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/dashboard/system/risk-scoring/route";
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

describe("dashboard system manual risk scoring route", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("preserves backend 403 payloads for non-admin scoring attempts", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    const body = JSON.stringify({ ward_id: 7 });
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await POST(
      new Request("http://localhost:3000/api/dashboard/system/risk-scoring", {
        method: "POST",
        headers: {
          cookie: "sessionid=analyst",
          "content-type": "application/json",
        },
        body,
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/system/controls/manual-risk-scoring/",
      expect.objectContaining({
        method: "POST",
        body,
        cookieHeader: "sessionid=analyst",
      }),
    );
  });
});
