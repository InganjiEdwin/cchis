import { existsSync } from "node:fs";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as downloadExport } from "@/app/api/dashboard/sensitive-exports/[publicId]/download/route";
import { POST as requestExport } from "@/app/api/dashboard/sensitive-exports/route";
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

function exportContext() {
  return { params: Promise.resolve({ publicId: "export-123" }) };
}

describe("dashboard sensitive export BFF routes", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("preserves backend 403 payloads when analysts request sensitive exports", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await requestExport(
      new Request("http://localhost/api/dashboard/sensitive-exports", {
        method: "POST",
        headers: {
          cookie: "sessionid=analyst",
          "content-type": "application/json",
        },
        body: JSON.stringify({ export_type: "ward_case_line_list" }),
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/sensitive-exports/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=analyst",
      }),
    );
  });

  it("preserves backend 403 payloads when analysts download sensitive exports", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await downloadExport(
      new Request("http://localhost/api/dashboard/sensitive-exports/export-123/download", {
        headers: { cookie: "sessionid=analyst" },
      }),
      exportContext(),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/sensitive-exports/export-123/download/",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
  });

  it("does not expose a sensitive-export approval BFF route for supervisors", () => {
    expect(existsSync(new URL("./[publicId]/approval/route.ts", import.meta.url))).toBe(false);
    expect(existsSync(new URL("./[publicId]/approve/route.ts", import.meta.url))).toBe(false);
  });
});
