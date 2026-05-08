import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as getChvDirectory } from "@/app/api/dashboard/chvs/route";
import { GET as getChvOperations } from "@/app/api/dashboard/chvs/operations/route";
import { GET as getOfflineMonitoring } from "@/app/api/dashboard/chvs/offline-monitoring/route";
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

describe("dashboard CHV BFF routes", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("preserves backend 403 payloads when analysts request the CHV directory", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await getChvDirectory(
      new Request("http://localhost/api/dashboard/chvs", {
        headers: { cookie: "sessionid=analyst" },
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/chvs/?page_size=100&ordering=name",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
  });

  it("preserves backend 403 payloads when analysts request CHV operations", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await getChvOperations(
      new Request("http://localhost/api/dashboard/chvs/operations", {
        headers: { cookie: "sessionid=analyst" },
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/chvs/operations/",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
  });

  it("keeps supervisor CHV operations backend-scoped instead of widening in the BFF", async () => {
    mockFetchBackendJson.mockResolvedValueOnce([
      {
        ward_id: 7,
        ward_name: "North Kadem",
        active_chvs: 18,
      },
    ]);

    const response = await getChvOperations(
      new Request("http://localhost/api/dashboard/chvs/operations", {
        headers: { cookie: "sessionid=supervisor" },
      }),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toEqual([
      expect.objectContaining({
        ward_id: 7,
        ward_name: "North Kadem",
      }),
    ]);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/chvs/operations/",
      expect.objectContaining({ cookieHeader: "sessionid=supervisor" }),
    );
  });

  it("preserves backend 403 payloads for analyst offline monitoring attempts", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await getOfflineMonitoring(
      new Request("http://localhost/api/dashboard/chvs/offline-monitoring", {
        headers: { cookie: "sessionid=analyst" },
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/chv/offline/monitoring/",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
  });
});
