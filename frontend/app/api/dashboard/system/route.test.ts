import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/dashboard/system/route";
import type { CurrentUser } from "@/lib/auth";
import { hasPageCapability } from "@/lib/capabilities";
import { getVisibleNav } from "@/lib/navigation";
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

function buildUser(role: CurrentUser["role"], overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: 1,
    username: `${role.toLowerCase()}-user`,
    email: `${role.toLowerCase()}@example.com`,
    full_name: role,
    phone_number: null,
    role,
    theme_preference: "SYSTEM",
    ward: role === "SUPERVISOR" ? 7 : null,
    ward_name: role === "SUPERVISOR" ? "North Kadem" : null,
    scope_type: role === "SUPERVISOR" ? "WARD" : role === "CHV" ? "NONE" : "BROAD",
    scope_ward_id: role === "SUPERVISOR" ? 7 : null,
    is_active: true,
    ...overrides,
  };
}

describe("dashboard system route", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("loads the full readiness payload for admin-compatible sessions", async () => {
    mockFetchBackendJson
      .mockResolvedValueOnce({
        schema_version: "system-readiness-v1",
        mode: "full_system_readiness_v1",
        visible_wards: 40,
        active_chvs: 384,
        delivery_backends: [
          {
            backend: "SMS",
            queued: 1,
            failed: 0,
            retry_pending: 0,
          },
        ],
      })
      .mockResolvedValueOnce({
        mode: "control_contracts_enabled",
        can_retry_background_jobs: true,
        can_run_manual_risk_scoring: true,
        can_pause_alert_delivery: true,
      });

    const response = await GET(
      new Request("http://localhost:3000/api/dashboard/system", {
        headers: { cookie: "sessionid=admin" },
      }),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.readiness.mode).toBe("full_system_readiness_v1");
    expect(payload.readiness.delivery_backends).toHaveLength(1);
    expect(payload.controlStatus.can_retry_background_jobs).toBe(true);
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      1,
      "/system/readiness/",
      expect.objectContaining({ cookieHeader: "sessionid=admin" }),
    );
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      2,
      "/system/controls/",
      expect.objectContaining({ cookieHeader: "sessionid=admin" }),
    );
  });

  it("loads analyst-safe readiness and control status without calling CHV operations", async () => {
    mockFetchBackendJson
      .mockResolvedValueOnce({
        schema_version: "system-readiness-v1",
        mode: "analyst_safe_system_readiness_v1",
        visible_wards: 40,
        active_chvs: 12,
      })
      .mockResolvedValueOnce({
        mode: "control_contracts_enabled",
        can_retry_background_jobs: false,
        can_run_manual_risk_scoring: false,
        can_pause_alert_delivery: false,
      });

    const response = await GET(new Request("http://localhost:3000/api/dashboard/system"));
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.readiness.visible_wards).toBe(40);
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      1,
      "/system/readiness/",
      expect.objectContaining({ cookieHeader: "" }),
    );
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      2,
      "/system/controls/",
      expect.objectContaining({ cookieHeader: "" }),
    );
    expect(mockFetchBackendJson).not.toHaveBeenCalledWith("/chvs/operations/", expect.anything());
  });

  it("does not advertise the system page to supervisors even though read-only control status is backend-readable", () => {
    const supervisor = buildUser("SUPERVISOR");

    expect(hasPageCapability(supervisor, "system")).toBe(false);
    expect(getVisibleNav(supervisor).map((item) => item.href)).not.toContain("/system");
    expect(supervisor.role).toBe("SUPERVISOR");
  });

  it("preserves backend authorization failures from readiness dependencies", async () => {
    const payload = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };
    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", payload));

    const response = await GET(new Request("http://localhost:3000/api/dashboard/system"));

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(payload);
  });

  it("preserves backend authorization failures from control-status dependencies", async () => {
    const payload = {
      detail: "System control status is not available for this session.",
      code: "permission_denied",
    };
    mockFetchBackendJson
      .mockResolvedValueOnce({
        schema_version: "system-readiness-v1",
        mode: "analyst_safe_system_readiness_v1",
      })
      .mockRejectedValueOnce(new ServerApiError(403, "Forbidden", payload));

    const response = await GET(new Request("http://localhost:3000/api/dashboard/system"));

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(payload);
  });
});
