import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as refreshConnector } from "@/app/api/dashboard/source-data/connectors/[connectorKey]/refresh/route";
import { GET as getFeedTypes } from "@/app/api/dashboard/source-data/feed-types/route";
import { GET as getOverview } from "@/app/api/dashboard/source-data/overview/route";
import { GET as getTemplate } from "@/app/api/dashboard/source-data/templates/[feedKey]/route";
import { GET as getUploadErrors } from "@/app/api/dashboard/source-data/uploads/[publicId]/errors.csv/route";
import { POST as approveUpload } from "@/app/api/dashboard/source-data/uploads/[publicId]/approval/route";
import { POST as confirmUpload } from "@/app/api/dashboard/source-data/uploads/[publicId]/confirm/route";
import { POST as triggerDownstream } from "@/app/api/dashboard/source-data/uploads/[publicId]/downstream-actions/route";
import { POST as validateUpload } from "@/app/api/dashboard/source-data/uploads/[publicId]/validate/route";
import { POST as uploadSourceData } from "@/app/api/dashboard/source-data/uploads/route";
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

function uploadContext() {
  return { params: Promise.resolve({ publicId: "upload-123" }) };
}

function connectorContext() {
  return { params: Promise.resolve({ connectorKey: "dhis2_surveillance_weekly" }) };
}

function jsonPost(url: string, payload: Record<string, unknown> = {}, cookie = "sessionid=analyst") {
  return new Request(url, {
    method: "POST",
    headers: {
      cookie,
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

function sourceDataFormRequest() {
  const formData = new URLSearchParams({
    feed_key: "weekly_cases",
    source_name: "DHIS2",
  });

  return new Request("http://localhost/api/dashboard/source-data/uploads", {
    method: "POST",
    headers: {
      cookie: "sessionid=analyst",
      "content-type": "application/x-www-form-urlencoded",
    },
    body: formData,
  });
}

async function expectForbidden(response: Response, expectedPayload: Record<string, unknown>) {
  expect(response.status).toBe(403);
  await expect(response.json()).resolves.toEqual(expectedPayload);
}

describe("dashboard source-data BFF routes", () => {
  beforeEach(() => {
    mockFetchBackendJson.mockReset();
  });

  it("allows analyst-safe source-data reads through the BFF", async () => {
    mockFetchBackendJson
      .mockResolvedValueOnce({
        summary: {
          uploads_waiting: 0,
          issues_to_fix: 0,
        },
      })
      .mockResolvedValueOnce({
        feed_types: [
          {
            key: "weekly_cases",
            label: "Weekly cases",
          },
        ],
      })
      .mockResolvedValueOnce({
        payload: "ward_code,cases\n",
        filename: "weekly cases template.csv",
        content_type: "text/csv",
        payload_sha256: "abc123",
        row_count: 1,
        feed_key: "weekly_cases",
      })
      .mockResolvedValueOnce({
        payload: "row,error\n2,Invalid ward\n",
        filename: "errors.csv",
        content_type: "text/csv",
        payload_sha256: "def456",
        row_count: 1,
      });

    const overviewResponse = await getOverview(
      new Request("http://localhost/api/dashboard/source-data/overview", {
        headers: { cookie: "sessionid=analyst" },
      }),
    );
    const feedTypesResponse = await getFeedTypes(
      new Request("http://localhost/api/dashboard/source-data/feed-types", {
        headers: { cookie: "sessionid=analyst" },
      }),
    );
    const templateResponse = await getTemplate(
      new Request("http://localhost/api/dashboard/source-data/templates/weekly_cases", {
        headers: { cookie: "sessionid=analyst" },
      }),
      { params: Promise.resolve({ feedKey: "weekly_cases" }) },
    );
    const errorsResponse = await getUploadErrors(
      new Request("http://localhost/api/dashboard/source-data/uploads/upload-123/errors.csv", {
        headers: { cookie: "sessionid=analyst" },
      }),
      uploadContext(),
    );

    expect(overviewResponse.status).toBe(200);
    await expect(overviewResponse.json()).resolves.toMatchObject({ summary: { uploads_waiting: 0 } });
    expect(feedTypesResponse.status).toBe(200);
    await expect(feedTypesResponse.json()).resolves.toMatchObject({ feed_types: [{ key: "weekly_cases" }] });
    expect(templateResponse.status).toBe(200);
    expect(templateResponse.headers.get("Content-Disposition")).toContain("weekly_cases_template.csv");
    await expect(templateResponse.text()).resolves.toBe("ward_code,cases\n");
    expect(errorsResponse.status).toBe(200);
    await expect(errorsResponse.text()).resolves.toBe("row,error\n2,Invalid ward\n");
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      1,
      "/source-data/overview/",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      2,
      "/source-data/feed-types/",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      3,
      "/source-data/templates/weekly_cases/",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
    expect(mockFetchBackendJson).toHaveBeenNthCalledWith(
      4,
      "/source-data/uploads/upload-123/errors.csv/",
      expect.objectContaining({ cookieHeader: "sessionid=analyst" }),
    );
  });

  it("preserves backend 403 payloads when analysts try source-data mutations", async () => {
    const denial = {
      detail: "You do not have permission to perform this action.",
      code: "permission_denied",
    };

    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));
    await expectForbidden(await uploadSourceData(sourceDataFormRequest()), denial);
    expect(mockFetchBackendJson).toHaveBeenLastCalledWith(
      "/source-data/uploads/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=analyst",
      }),
    );

    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));
    await expectForbidden(
      await validateUpload(jsonPost("http://localhost/api/dashboard/source-data/uploads/upload-123/validate"), uploadContext()),
      denial,
    );
    expect(mockFetchBackendJson).toHaveBeenLastCalledWith(
      "/source-data/uploads/upload-123/validate/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=analyst",
      }),
    );

    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));
    await expectForbidden(
      await confirmUpload(
        jsonPost("http://localhost/api/dashboard/source-data/uploads/upload-123/confirm", {
          confirmation: "confirm",
        }),
        uploadContext(),
      ),
      denial,
    );
    expect(mockFetchBackendJson).toHaveBeenLastCalledWith(
      "/source-data/uploads/upload-123/confirm/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=analyst",
      }),
    );

    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));
    await expectForbidden(
      await approveUpload(
        jsonPost("http://localhost/api/dashboard/source-data/uploads/upload-123/approval", {
          decision: "approve",
        }),
        uploadContext(),
      ),
      denial,
    );
    expect(mockFetchBackendJson).toHaveBeenLastCalledWith(
      "/source-data/uploads/upload-123/approval/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=analyst",
      }),
    );

    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));
    await expectForbidden(
      await triggerDownstream(
        jsonPost("http://localhost/api/dashboard/source-data/uploads/upload-123/downstream-actions", {
          action: "publish",
        }),
        uploadContext(),
      ),
      denial,
    );
    expect(mockFetchBackendJson).toHaveBeenLastCalledWith(
      "/source-data/uploads/upload-123/downstream-actions/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=analyst",
      }),
    );
  });

  it("preserves backend 403 payloads when supervisors try admin connector controls", async () => {
    const denial = {
      detail: "Only admins can refresh source-data connectors.",
      code: "permission_denied",
    };

    mockFetchBackendJson.mockRejectedValueOnce(new ServerApiError(403, "Forbidden", denial));

    await expectForbidden(
      await refreshConnector(
        jsonPost(
          "http://localhost/api/dashboard/source-data/connectors/dhis2_surveillance_weekly/refresh",
          { force: true },
          "sessionid=supervisor",
        ),
        connectorContext(),
      ),
      denial,
    );
    expect(mockFetchBackendJson).toHaveBeenLastCalledWith(
      "/source-data/connectors/dhis2_surveillance_weekly/refresh/",
      expect.objectContaining({
        method: "POST",
        cookieHeader: "sessionid=supervisor",
      }),
    );
  });
});
