import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/dashboard/system/retry/route";
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

describe("dashboard system retry route", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("queues admin retry controls through the admin-only backend endpoint", async () => {
    mockFetchBackendJson.mockResolvedValueOnce({
      status: "queued",
      queued_jobs: ["failed-alert-deliveries"],
    });

    const body = JSON.stringify({ queue: "failed-alert-deliveries" });
    const response = await POST(
      new Request("http://localhost:3000/api/dashboard/system/retry", {
        method: "POST",
        headers: {
          cookie: "sessionid=admin",
          "content-type": "application/json",
        },
        body,
      }),
    );
    const payload = await response.json();

    expect(response.status).toBe(202);
    expect(payload.status).toBe("queued");
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/system/controls/retry/",
      expect.objectContaining({
        method: "POST",
        body,
        cookieHeader: "sessionid=admin",
      }),
    );
  });

  it("preserves backend 403 payloads for non-admin write attempts", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await POST(
      new Request("http://localhost:3000/api/dashboard/system/retry", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ queue: "all" }),
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
  });
});
