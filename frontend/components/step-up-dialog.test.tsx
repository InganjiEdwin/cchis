import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StepUpDialogProvider } from "@/components/step-up-dialog";
import { createSensitiveExportViaBff } from "@/lib/dashboard";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("StepUpDialogProvider", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("opens confirmation on step-up_required and retries the original action after verification", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({
        detail: "This action needs a quick security check. Enter your authenticator code to continue.",
        code: "step_up_required",
        purpose: "sensitive_exports",
      }, 403))
      .mockResolvedValueOnce(jsonResponse({
        detail: "Security check confirmed.",
        purpose: "sensitive_exports",
        expires_at: "2026-05-08T12:00:00+03:00",
      }))
      .mockResolvedValueOnce(jsonResponse({ public_id: "export-1" }));
    globalThis.fetch = fetchMock;

    const actionResult = vi.fn();
    render(
      <StepUpDialogProvider>
        <button
          type="button"
          onClick={() => {
            void createSensitiveExportViaBff({
              export_type: "ALERT_LIST_CSV",
              purpose: "Operational review",
            }).then(actionResult);
          }}
        >
          Request export
        </button>
      </StepUpDialogProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Request export" }));

    expect(await screen.findByRole("dialog", { name: "Confirm it is you" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("6-digit code"), "123456");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(actionResult).toHaveBeenCalledWith({ public_id: "export-1" }));
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.any(URL),
      expect.objectContaining({
        body: JSON.stringify({ code: "123456", purpose: "sensitive_exports" }),
        credentials: "include",
        method: "POST",
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/dashboard/sensitive-exports",
      expect.objectContaining({
        credentials: "include",
        method: "POST",
      }),
    );
  });
});
