import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChvOfflinePage from "@/app/chv/page";
import type { CurrentUser } from "@/lib/auth";

const mockReplace = vi.fn();
const mockUseAuth = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

function buildChvUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: 7,
    username: "offline-chv",
    email: "chv@example.com",
    full_name: "Akinyi Omondi",
    phone_number: "+254700000007",
    role: "CHV",
    theme_preference: "SYSTEM",
    ward: 12,
    ward_name: "North Kanyamkago",
    is_active: true,
    ...overrides,
  };
}

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", {
    value,
    configurable: true,
  });
}

function createMemoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(values.keys())[index] ?? null;
    },
    removeItem(key: string) {
      values.delete(key);
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
  };
}

function renderChvPage(user: CurrentUser = buildChvUser()) {
  mockUseAuth.mockReturnValue({
    currentUser: user,
    isAuthenticated: true,
    isHydrating: false,
  });

  window.localStorage.setItem("cchis.chv_offline.device_id", "web-test-device");
  render(React.createElement(ChvOfflinePage));
}

function buildOfflineContractResponse() {
  return {
    contract_version: "chv-offline-v1",
    session_scope: {
      ward_id: 12,
      scope_key: "ward:server-ward:chv:server-chv",
    },
    download_bundle: {
      version: "chv-bundle-live-001",
      generated_at: "2026-05-04T08:00:00Z",
      expires_at: "2026-05-05T08:00:00Z",
      task_bundle: {
        schema_version: "chv-task-bundle-v1",
        tasks: [
          {
            task_public_id: "00000000-0000-4000-8000-000000000111",
            task_type: "preparedness_action",
            action_type: "CHV_FOLLOW_UP",
            status: "ASSIGNED",
            priority: "HIGH",
            ward_id: 12,
            ward_public_id: "ward-public-12",
            due_at: "2026-05-04T12:00:00Z",
            allowed_upload_types: ["task_ack", "prevention_visit"],
            minimum_capture: ["task_public_id", "status", "coded_reason", "recorded_at"],
          },
        ],
      },
      guidance_bundle: {
        schema_version: "chv-guidance-bundle-v1",
        items: [
          {
            guidance_public_id: "guidance-live-1",
            template_key: "cholera.prevention.safe_water",
            language: "en",
            version: 2,
            audience_type: "CHV",
            title: "Live safe water",
            body: "Use treated water and covered storage.",
            public_health_caveats: "Approved CHV bundle copy.",
          },
        ],
      },
      decision_support_rule_bundle: {
        version: "cholera-triage-rules-v1",
      },
    },
    sync_health_record: {
      last_successful_sync_at: null,
      pending_upload_count: 0,
      failed_upload_count: 0,
      sync_health: "OFFLINE",
    },
  };
}

function buildDeviceRegistrationResponse() {
  return {
    public_id: "11111111-1111-4111-8111-111111111111",
    device_id: "web-test-device",
    contract_version: "chv-offline-v1",
    download_bundle_version: "chv-bundle-live-001",
    session_scope: {
      ward_id: 12,
      scope_key: "ward:server-ward:chv:server-chv",
    },
    sync_health_record: {
      last_successful_sync_at: null,
      pending_upload_count: 0,
      failed_upload_count: 0,
      sync_health: "OFFLINE",
    },
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function saveBasicFollowUp() {
  const user = userEvent.setup();

  await screen.findByRole("heading", { name: "CHV follow-up" });
  await user.click(screen.getByRole("button", { name: /start triage/i }));
  await user.click(screen.getByRole("button", { name: "Diarrhea" }));
  await user.click(screen.getByRole("button", { name: "Vomiting" }));
  await user.type(screen.getByLabelText("Short note"), "Loose stool and vomiting");
  await user.click(screen.getByRole("button", { name: /save follow-up/i }));
}

describe("ChvOfflinePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "localStorage", {
      value: createMemoryStorage(),
      configurable: true,
    });
    Object.defineProperty(window, "sessionStorage", {
      value: createMemoryStorage(),
      configurable: true,
    });
    setOnline(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lets a CHV complete a basic assigned follow-up while offline", async () => {
    setOnline(false);
    renderChvPage();

    await saveBasicFollowUp();

    expect(screen.getByText("Follow-up saved on this device.")).toBeInTheDocument();
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /sync now/i })).toBeDisabled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("syncs pending triage when online without sending local-only task fields", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const url = String(_url);
      if (url === "/api/chv/offline/contract") {
        return jsonResponse(buildOfflineContractResponse());
      }
      if (url === "/api/chv/device-registrations") {
        return jsonResponse(buildDeviceRegistrationResponse(), 201);
      }

      const body = JSON.parse(String(init?.body ?? "{}")) as {
        uploads: Array<{
          client_submission_id: string;
          idempotency_key: string;
          upload_type: "symptom_triage" | "prevention_visit" | "task_ack";
        }>;
      };

      return jsonResponse(
        {
          message: "Offline payloads synced successfully.",
          contract_version: "chv-offline-v1",
          processed_count: body.uploads.length,
          sync_health_record: {
            last_successful_sync_at: "2026-05-04T09:00:00Z",
            pending_upload_count: 0,
            failed_upload_count: 0,
            sync_health: "ONLINE",
          },
          results: body.uploads.map((upload) => ({
            client_submission_id: upload.client_submission_id,
            idempotency_key: upload.idempotency_key,
            upload_type: upload.upload_type,
            sync_status: "PROCESSED",
            conflict_state: "NONE",
            replayed: false,
            server_receipt: {
              status: "ACCEPTED",
            },
          })),
        },
        201,
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChvPage();
    await saveBasicFollowUp();
    await userEvent.setup().click(screen.getByRole("button", { name: /sync now/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/chv/sync", expect.any(Object));
    });

    const syncCall = fetchMock.mock.calls.find((call) => String(call[0]) === "/api/chv/sync");
    expect(syncCall).toBeTruthy();
    const requestInit = syncCall?.[1] as RequestInit;
    const syncBody = JSON.parse(String(requestInit.body)) as {
      uploads: Array<{ payload: Record<string, unknown> }>;
      device_registration_id?: string;
    };
    expect(syncBody.device_registration_id).toBe("11111111-1111-4111-8111-111111111111");
    expect(syncBody.uploads[0].payload).toEqual({
      diarrhea: true,
      vomiting: true,
      dehydration: false,
      fever: false,
      text_input: "Loose stool and vomiting",
    });
    expect(syncBody.uploads[0].payload.task_public_id).toBeUndefined();
    expect(await screen.findByText("Sent.")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /tasks/i }));
    expect(screen.getAllByText("Sent").length).toBeGreaterThan(0);
  });

  it("loads live assigned tasks, registers the device, and syncs prevention visits", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const url = String(_url);
      if (url === "/api/chv/offline/contract") {
        return jsonResponse(buildOfflineContractResponse());
      }
      if (url === "/api/chv/device-registrations") {
        return jsonResponse(buildDeviceRegistrationResponse(), 201);
      }

      const body = JSON.parse(String(init?.body ?? "{}")) as {
        uploads: Array<{
          client_submission_id: string;
          idempotency_key: string;
          upload_type: "prevention_visit";
        }>;
      };

      return jsonResponse(
        {
          message: "Offline payloads synced successfully.",
          contract_version: "chv-offline-v1",
          processed_count: body.uploads.length,
          sync_health_record: {
            last_successful_sync_at: "2026-05-04T09:00:00Z",
            pending_upload_count: 0,
            failed_upload_count: 0,
            sync_health: "ONLINE",
          },
          results: body.uploads.map((upload) => ({
            client_submission_id: upload.client_submission_id,
            idempotency_key: upload.idempotency_key,
            upload_type: upload.upload_type,
            sync_status: "PROCESSED",
            conflict_state: "NONE",
            replayed: false,
            server_receipt: {
              status: "ACCEPTED",
            },
          })),
        },
        201,
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChvPage();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/chv/offline/contract", expect.any(Object));
      expect(fetchMock).toHaveBeenCalledWith("/api/chv/device-registrations", expect.any(Object));
    });

    expect(window.localStorage.getItem("cchis.chv_offline.device_registration_id")).toBe(
      "11111111-1111-4111-8111-111111111111",
    );
    await userEvent.setup().click(await screen.findByRole("button", { name: /save prevention visit/i }));
    await userEvent.setup().click(screen.getByRole("button", { name: /sync now/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/chv/sync", expect.any(Object));
    });

    const syncCall = fetchMock.mock.calls.find((call) => String(call[0]) === "/api/chv/sync");
    const requestInit = syncCall?.[1] as RequestInit;
    const syncBody = JSON.parse(String(requestInit.body)) as {
      device_registration_id?: string;
      uploads: Array<{ upload_type: string; payload: Record<string, unknown> }>;
    };
    expect(syncBody.device_registration_id).toBe("11111111-1111-4111-8111-111111111111");
    expect(syncBody.uploads[0]).toMatchObject({
      upload_type: "prevention_visit",
      payload: {
        task_public_id: "00000000-0000-4000-8000-000000000111",
        action_public_id: "00000000-0000-4000-8000-000000000111",
        visit_completed: true,
        households_reached_count: 1,
        messages_delivered_count: 1,
        water_treatment_demo: false,
        soap_or_handwashing_discussed: false,
      },
    });
    expect(await screen.findByText("Sent.")).toBeInTheDocument();
  });

  it("does not mark unrelated pending work rejected when one queued item fails", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const url = String(_url);
      if (url === "/api/chv/offline/contract") {
        return jsonResponse(buildOfflineContractResponse());
      }
      if (url === "/api/chv/device-registrations") {
        return jsonResponse(buildDeviceRegistrationResponse(), 201);
      }

      const body = JSON.parse(String(init?.body ?? "{}")) as {
        uploads: Array<{
          client_submission_id: string;
          idempotency_key: string;
          upload_type: "symptom_triage" | "prevention_visit";
        }>;
      };
      const upload = body.uploads[0];
      if (upload?.upload_type === "prevention_visit") {
        return jsonResponse({ detail: "Preparedness action not found." }, 404);
      }

      return jsonResponse(
        {
          message: "Offline payloads synced successfully.",
          contract_version: "chv-offline-v1",
          processed_count: body.uploads.length,
          sync_health_record: {
            last_successful_sync_at: "2026-05-04T09:00:00Z",
            pending_upload_count: 0,
            failed_upload_count: 0,
            sync_health: "ONLINE",
          },
          results: body.uploads.map((item) => ({
            client_submission_id: item.client_submission_id,
            idempotency_key: item.idempotency_key,
            upload_type: item.upload_type,
            sync_status: "PROCESSED",
            conflict_state: "NONE",
            replayed: false,
            server_receipt: { status: "ACCEPTED" },
          })),
        },
        201,
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChvPage();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/chv/device-registrations", expect.any(Object));
    });
    await saveBasicFollowUp();
    await userEvent.setup().click(screen.getByRole("button", { name: /tasks/i }));
    await userEvent.setup().click(await screen.findByRole("button", { name: /save prevention visit/i }));
    await userEvent.setup().click(screen.getByRole("button", { name: /sync now/i }));

    expect(await screen.findByText("1 sent, 1 rejected. Preparedness action not found.")).toBeInTheDocument();
    const syncCalls = fetchMock.mock.calls.filter((call) => String(call[0]) === "/api/chv/sync");
    expect(syncCalls).toHaveLength(2);
    expect(screen.getAllByText("Rejected").length).toBeGreaterThan(0);
  });

  it("keeps pending work queued when sync fails with a retryable server error", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL) => {
      const url = String(_url);
      if (url === "/api/chv/offline/contract") {
        return jsonResponse(buildOfflineContractResponse());
      }
      if (url === "/api/chv/device-registrations") {
        return jsonResponse(buildDeviceRegistrationResponse(), 201);
      }

      return jsonResponse({ detail: "Backend unavailable." }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChvPage();
    await saveBasicFollowUp();
    await userEvent.setup().click(screen.getByRole("button", { name: /sync now/i }));

    expect(await screen.findByText("0 sent, 1 waiting to retry. Backend unavailable.")).toBeInTheDocument();
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    expect(screen.queryByText("Rejected")).not.toBeInTheDocument();
  });

  it("shows rejected work when online sync is refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "Ward not found." }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    renderChvPage();
    await saveBasicFollowUp();
    await userEvent.setup().click(screen.getByRole("button", { name: /sync now/i }));

    expect((await screen.findAllByText("Ward not found.")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Rejected").length).toBeGreaterThan(0);
  });
});
