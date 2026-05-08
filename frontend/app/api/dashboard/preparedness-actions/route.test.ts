import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as getPreparednessAction, PATCH as patchPreparednessAction } from "@/app/api/dashboard/preparedness-actions/[publicId]/route";
import { GET as listPreparednessActions } from "@/app/api/dashboard/preparedness-actions/route";
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

function actionContext() {
  return { params: Promise.resolve({ publicId: "action-123" }) };
}

describe("dashboard preparedness-action BFF routes", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("lets analysts read preparedness actions without exposing mutation behavior", async () => {
    mockFetchBackendJson.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          public_id: "action-123",
          ward_id: 7,
          status: "OPEN",
        },
      ],
    });

    const response = await listPreparednessActions(
      new Request("http://localhost/api/dashboard/preparedness-actions?status=OPEN", {
        headers: { cookie: "sessionid=analyst" },
      }),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.results[0].public_id).toBe("action-123");
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/preparedness-actions/?status=OPEN&page_size=200&ordering=due_at",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
  });

  it("forwards supervisor ward filters so ward scope remains backend-owned", async () => {
    mockFetchBackendJson.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          public_id: "action-123",
          ward_id: 7,
          status: "OPEN",
        },
      ],
    });

    const response = await listPreparednessActions(
      new Request("http://localhost/api/dashboard/preparedness-actions?ward_id=7&status=OPEN", {
        headers: { cookie: "sessionid=supervisor" },
      }),
    );

    expect(response.status).toBe(200);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/preparedness-actions/?ward_id=7&status=OPEN&page_size=200&ordering=due_at",
      expect.objectContaining({ cookieHeader: "sessionid=supervisor" }),
    );
  });

  it("preserves backend 403 payloads when analysts try to mutate preparedness actions", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await patchPreparednessAction(
      new Request("http://localhost/api/dashboard/preparedness-actions/action-123", {
        method: "PATCH",
        headers: {
          cookie: "sessionid=analyst",
          "content-type": "application/json",
        },
        body: JSON.stringify({ status: "DONE" }),
      }),
      actionContext(),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/preparedness-actions/action-123/",
      expect.objectContaining({
        method: "PATCH",
        cookieHeader: "sessionid=analyst",
      }),
    );
  });

  it("preserves backend denial payloads for out-of-scope detail reads", async () => {
    const denial = {
      detail: "Not found.",
      code: "not_found",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(404, "Not found", denial));

    const response = await getPreparednessAction(
      new Request("http://localhost/api/dashboard/preparedness-actions/action-123", {
        headers: { cookie: "sessionid=supervisor" },
      }),
      actionContext(),
    );

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toEqual(denial);
  });
});
