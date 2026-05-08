import { describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/dashboard/operational-metrics/me-export/route";
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

describe("dashboard operational metric M&E export route", () => {
  it("forwards export filters without using DRF's reserved format parameter", async () => {
    mockFetchBackendJson.mockResolvedValueOnce({
      schema_version: "operational-kpi-me-export-v1",
      format: "csv",
      payload: "metric_key\n",
      filename: "operational-kpi-me-export.csv",
      content_type: "text/csv",
      filters: {},
    });

    const request = new Request(
      "http://localhost:3000/api/dashboard/operational-metrics/me-export?date_from=2026-05-01&date_to=2026-05-03&ward_id=7&sub_county=Nyatike&source_channel=SMS&export_format=csv&format=csv",
      {
        headers: { cookie: "sessionid=test" },
      },
    );
    const response = await GET(request);

    expect(response.status).toBe(200);
    expect(mockFetchBackendJson).toHaveBeenCalledWith(
      "/operational-metrics/me-export/?date_from=2026-05-01&date_to=2026-05-03&ward_id=7&sub_county=Nyatike&source_channel=SMS&export_format=csv",
      expect.objectContaining({ cookieHeader: "sessionid=test" }),
    );
  });

  it("preserves backend step-up payloads for protected M&E export downloads", async () => {
    const stepUpPayload = {
      detail: "This action needs a quick security check. Enter your authenticator code to continue.",
      code: "step_up_required",
      purpose: "sensitive_export_download",
    };
    mockFetchBackendJson.mockRejectedValueOnce(
      new ServerApiError(403, "This action needs a quick security check.", stepUpPayload),
    );

    const response = await GET(
      new Request("http://localhost:3000/api/dashboard/operational-metrics/me-export?export_format=csv", {
        headers: { cookie: "sessionid=test" },
      }),
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(stepUpPayload);
  });
});
