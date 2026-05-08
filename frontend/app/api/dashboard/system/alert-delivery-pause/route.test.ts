import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/dashboard/system/alert-delivery-pause/route";
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

describe("dashboard system alert delivery pause route", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("preserves backend 403 payloads for non-admin pause attempts", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    const body = JSON.stringify({ pause_alert_delivery: true, reason: "maintenance" });
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await POST(
      new Request("http://localhost:3000/api/dashboard/system/alert-delivery-pause", {
        method: "POST",
        headers: {
          cookie: "sessionid=supervisor",
          "content-type": "application/json",
        },
        body,
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/system/controls/alert-delivery-pause/",
      expect.objectContaining({
        method: "POST",
        body,
        cookieHeader: "sessionid=supervisor",
      }),
    );
  });
});
