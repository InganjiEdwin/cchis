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
  return render(React.createElement(ChvOfflinePage));
}

function buildOfflineContractResponse(language = "en", resolvedLanguage = language, fallbackUsed = false) {
  return {
    contract_version: "chv-offline-v1",
    requested_language: language,
    resolved_language: resolvedLanguage,
    fallback_used: fallbackUsed,
    language: {
      requested_language: language,
      resolved_language: resolvedLanguage,
      fallback_used: fallbackUsed,
    },
    session_scope: {
      ward_id: 12,
      scope_key: "ward:server-ward:chv:server-chv",
    },
    download_bundle: {
      version: "chv-bundle-live-001",
      generated_at: "2026-05-04T08:00:00Z",
      expires_at: "2026-05-05T08:00:00Z",
      requested_language: language,
      resolved_language: resolvedLanguage,
      fallback_used: fallbackUsed,
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
        requested_language: language,
        resolved_language: resolvedLanguage,
        fallback_used: fallbackUsed,
        content_unavailable: false,
        governance_status: "approved",
        items: [
          {
            guidance_public_id: "guidance-live-1",
            template_key: "cholera.household.prevention_guidance_offline_bundle",
            language: resolvedLanguage,
            requested_language: language,
            resolved_language: resolvedLanguage,
            fallback_used: fallbackUsed,
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
        requested_language: language,
        resolved_language: resolvedLanguage,
        fallback_used: fallbackUsed,
        content_unavailable: false,
        governance_status: "approved",
        missing_recommendation_keys: [],
        recommendations: [
          {
            recommendation_public_id: "recommendation-live-1",
            recommendation_key: "urgent_referral",
            template_key: "cholera.chv.triage.urgent_referral_offline",
            language: resolvedLanguage,
            requested_language: language,
            resolved_language: resolvedLanguage,
            fallback_used: fallbackUsed,
            version: 1,
            audience_type: "chv",
            title: "Live urgent referral",
            body: "Approved urgent referral copy.",
            public_health_caveats: "Approved CHV triage copy.",
            source: "governed_message_template",
            governance_status: "approved",
          },
          {
            recommendation_public_id: "recommendation-live-2",
            recommendation_key: "facility_assessment",
            template_key: "cholera.chv.triage.facility_assessment_offline",
            language: resolvedLanguage,
            requested_language: language,
            resolved_language: resolvedLanguage,
            fallback_used: fallbackUsed,
            version: 1,
            audience_type: "chv",
            title: "Live facility assessment",
            body: "Approved facility assessment copy.",
            public_health_caveats: "Approved CHV triage copy.",
            source: "governed_message_template",
            governance_status: "approved",
          },
          {
            recommendation_public_id: "recommendation-live-3",
            recommendation_key: "ors_and_prevention",
            template_key: "cholera.chv.triage.ors_and_prevention_offline",
            language: resolvedLanguage,
            requested_language: language,
            resolved_language: resolvedLanguage,
            fallback_used: fallbackUsed,
            version: 1,
            audience_type: "chv",
            title: "Live ORS advice",
            body: "Approved ORS and prevention copy.",
            public_health_caveats: "Approved CHV triage copy.",
            source: "governed_message_template",
            governance_status: "approved",
          },
          {
            recommendation_public_id: "recommendation-live-4",
            recommendation_key: "record_symptoms",
            template_key: "cholera.chv.triage.record_symptoms_offline",
            language: resolvedLanguage,
            requested_language: language,
            resolved_language: resolvedLanguage,
            fallback_used: fallbackUsed,
            version: 1,
            audience_type: "chv",
            title: "Live record symptoms",
            body: "Approved record symptoms copy.",
            public_health_caveats: "Approved CHV triage copy.",
            source: "governed_message_template",
            governance_status: "approved",
          },
        ],
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

function buildDeviceRegistrationResponse(language = "en", resolvedLanguage = language, fallbackUsed = false) {
  return {
    public_id: "11111111-1111-4111-8111-111111111111",
    device_id: "web-test-device",
    contract_version: "chv-offline-v1",
    preferred_language: resolvedLanguage,
    requested_language: language,
    resolved_language: resolvedLanguage,
    fallback_used: fallbackUsed,
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

    expect(screen.getByRole("navigation", { name: "CHV offline views" })).toBeInTheDocument();
    expect(screen.getByText("Follow-up saved on this device.")).toBeInTheDocument();
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /sync now/i })).toBeDisabled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("marks local governed content unavailable without claiming an English health fallback", async () => {
    setOnline(false);
    const user = userEvent.setup();
    renderChvPage();

    await screen.findByRole("heading", { name: "CHV follow-up" });
    await user.click(screen.getByRole("button", { name: /start triage/i }));
    await user.click(screen.getByRole("button", { name: "Diarrhea" }));

    expect(screen.getByText("Recommendation unavailable")).toBeInTheDocument();
    expect(screen.getByText("Download the offline bundle before using decision support.")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("English recommendation shown for this item.")).not.toBeInTheDocument();
  });

  it("caches the selected CHV language for offline use", async () => {
    setOnline(false);
    const user = userEvent.setup();
    const view = renderChvPage();

    await screen.findByRole("heading", { name: "CHV follow-up" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), "sw");

    expect(await screen.findByRole("heading", { name: "Ufuatiliaji wa CHV" })).toBeInTheDocument();
    expect(screen.getAllByText("Imerejea Kiingereza").length).toBeGreaterThan(0);
    expect(window.localStorage.getItem("cchis.chv_offline.local.ward-12.user-7")).toContain(
      '"selectedLanguage":"sw"',
    );

    view.unmount();
    renderChvPage();

    expect(await screen.findByRole("heading", { name: "Ufuatiliaji wa CHV" })).toBeInTheDocument();
  });

  it("requests a selected live language bundle and marks missing translation fallback", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const url = String(_url);
      if (url.startsWith("/api/chv/offline/contract")) {
        const language = new URL(`http://localhost${url}`).searchParams.get("language") ?? "en";
        return jsonResponse(language === "sw" ? buildOfflineContractResponse("sw", "en", true) : buildOfflineContractResponse());
      }
      if (url === "/api/chv/device-registrations") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { preferred_language?: string };
        const preferredLanguage = body.preferred_language ?? "en";
        return jsonResponse(
          preferredLanguage === "sw"
            ? buildDeviceRegistrationResponse("sw", "en", true)
            : buildDeviceRegistrationResponse(),
          201,
        );
      }
      return jsonResponse({ detail: "Unexpected request." }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderChvPage();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("language=en"), expect.any(Object));
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), "sw");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("language=sw"), expect.any(Object));
    });
    const registrationCalls = fetchMock.mock.calls.filter((call) => String(call[0]) === "/api/chv/device-registrations");
    const latestRegistrationBody = JSON.parse(String(registrationCalls.at(-1)?.[1]?.body ?? "{}")) as {
      preferred_language?: string;
    };
    expect(latestRegistrationBody.preferred_language).toBe("sw");
    await waitFor(() => {
      expect(screen.getAllByText("Imerejea Kiingereza").length).toBeGreaterThan(0);
    });
  });

  it("renders triage recommendation copy from the governed offline bundle", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL) => {
      const url = String(_url);
      if (url.startsWith("/api/chv/offline/contract")) {
        return jsonResponse(buildOfflineContractResponse());
      }
      if (url === "/api/chv/device-registrations") {
        return jsonResponse(buildDeviceRegistrationResponse(), 201);
      }
      return jsonResponse({ detail: "Unexpected request." }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderChvPage();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("language=en"), expect.any(Object));
    });
    await user.click(screen.getByRole("button", { name: /start triage/i }));
    await user.click(screen.getByRole("button", { name: "Diarrhea" }));

    expect(screen.getByText("Live ORS advice")).toBeInTheDocument();
    expect(screen.getByText("Approved ORS and prevention copy.")).toBeInTheDocument();
  });

  it("syncs pending triage when online without sending local-only task fields", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const url = String(_url);
      if (url.startsWith("/api/chv/offline/contract")) {
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
      if (url.startsWith("/api/chv/offline/contract")) {
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
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(/^\/api\/chv\/offline\/contract/),
        expect.any(Object),
      );
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
      if (url.startsWith("/api/chv/offline/contract")) {
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

    expect(await screen.findByText("1 sent, 1 rejected. Unable to sync offline work.")).toBeInTheDocument();
    const syncCalls = fetchMock.mock.calls.filter((call) => String(call[0]) === "/api/chv/sync");
    expect(syncCalls).toHaveLength(2);
    expect(screen.getAllByText("Rejected").length).toBeGreaterThan(0);
  });

  it("keeps pending work queued when sync fails with a retryable server error", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL) => {
      const url = String(_url);
      if (url.startsWith("/api/chv/offline/contract")) {
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

    expect(await screen.findByText("0 sent, 1 waiting to retry. Unable to sync offline work.")).toBeInTheDocument();
    expect(screen.queryByText("Backend unavailable.")).not.toBeInTheDocument();
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

    expect((await screen.findAllByText("Unable to sync offline work.")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Ward not found.")).not.toBeInTheDocument();
    expect(screen.getAllByText("Rejected").length).toBeGreaterThan(0);
  });
});
