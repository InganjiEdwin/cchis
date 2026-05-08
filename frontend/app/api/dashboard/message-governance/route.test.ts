import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as getMessageGovernance } from "@/app/api/dashboard/message-governance/route";
import { POST as approveTemplate } from "@/app/api/dashboard/message-governance/templates/[publicId]/approval/route";
import { GET as getTemplateDetail } from "@/app/api/dashboard/message-governance/templates/[publicId]/route";
import { POST as approveUssdMenu } from "@/app/api/dashboard/message-governance/ussd-menu-versions/[publicId]/approval/route";
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

function templateContext() {
  return { params: Promise.resolve({ publicId: "template-123" }) };
}

function ussdContext() {
  return { params: Promise.resolve({ publicId: "ussd-123" }) };
}

function approvalRequest(url: string, cookie = "sessionid=supervisor") {
  return new Request(url, {
    method: "POST",
    headers: {
      cookie,
      "content-type": "application/json",
    },
    body: JSON.stringify({ decision: "approve" }),
  });
}

describe("dashboard message-governance BFF routes", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("allows analyst and supervisor read views through backend-owned permissions", async () => {
    mockFetchBackendJson
      .mockResolvedValueOnce({
        summary: {
          pending_approval: 2,
        },
        templates: [],
      })
      .mockResolvedValueOnce({
        public_id: "template-123",
        approval_status: "pending",
      });

    const dashboardResponse = await getMessageGovernance(
      new Request("http://localhost/api/dashboard/message-governance?approval_status=pending&format=json", {
        headers: { cookie: "sessionid=analyst" },
      }),
    );
    const detailResponse = await getTemplateDetail(
      new Request("http://localhost/api/dashboard/message-governance/templates/template-123", {
        headers: { cookie: "sessionid=supervisor" },
      }),
      templateContext(),
    );

    expect(dashboardResponse.status).toBe(200);
    await expect(dashboardResponse.json()).resolves.toMatchObject({ summary: { pending_approval: 2 } });
    expect(detailResponse.status).toBe(200);
    await expect(detailResponse.json()).resolves.toMatchObject({ public_id: "template-123" });
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      1,
      "/message-governance/dashboard/?approval_status=pending",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      2,
      "/message-governance/templates/template-123/",
      expect.objectContaining({ cookieHeader: "sessionid=supervisor" }),
    );
  });

  it("preserves backend 403 payloads when non-admins approve templates", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await approveTemplate(
      approvalRequest("http://localhost/api/dashboard/message-governance/templates/template-123/approval"),
      templateContext(),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/message-governance/templates/template-123/approval/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=supervisor",
      }),
    );
  });

  it("preserves backend 403 payloads when non-admins approve USSD menu versions", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    const response = await approveUssdMenu(
      approvalRequest(
        "http://localhost/api/dashboard/message-governance/ussd-menu-versions/ussd-123/approval",
        "sessionid=analyst",
      ),
      ussdContext(),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(denial);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/message-governance/ussd-menu-versions/ussd-123/approval/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=analyst",
      }),
    );
  });
});
