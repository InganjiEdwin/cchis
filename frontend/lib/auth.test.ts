import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthStepUpRequiredError,
  persistEnrollmentToken,
  persistPreAuthToken,
  readEnrollmentToken,
  readPreAuthToken,
  requiresPolicyAcceptance,
  revokeAllProfileSessionsViaBff,
  type CurrentUser,
  type PolicyAcceptanceState,
} from "@/lib/auth";

const currentPolicyAcceptance: PolicyAcceptanceState = {
  required: true,
  is_current: true,
  terms_version: "terms-2026-05",
  privacy_version: "privacy-2026-05",
  cookie_notice_version: "cookies-2026-05",
  accepted_terms_version: "terms-2026-05",
  accepted_privacy_version: "privacy-2026-05",
  accepted_cookie_notice_version: "cookies-2026-05",
  missing_documents: [],
  terms_url: "/terms",
  privacy_url: "/privacy",
  cookie_notice_url: "/privacy#cookies",
};

function buildUser(policy_acceptance?: PolicyAcceptanceState): CurrentUser {
  return {
    id: 1,
    username: "policy-user",
    email: "policy@example.com",
    full_name: "Policy User",
    phone_number: null,
    role: "ADMIN",
    theme_preference: "SYSTEM",
    ward: null,
    ward_name: null,
    is_active: true,
    policy_acceptance,
  };
}

describe("requiresPolicyAcceptance", () => {
  it("requires review when backend policy state is required and not current", () => {
    expect(
      requiresPolicyAcceptance(
        buildUser({
          ...currentPolicyAcceptance,
          is_current: false,
          accepted_terms_version: null,
          missing_documents: ["TERMS"],
        }),
      ),
    ).toBe(true);
  });

  it("does not require review for current, disabled, or missing policy state", () => {
    expect(requiresPolicyAcceptance(buildUser(currentPolicyAcceptance))).toBe(false);
    expect(
      requiresPolicyAcceptance(
        buildUser({
          ...currentPolicyAcceptance,
          required: false,
          is_current: true,
        }),
      ),
    ).toBe(false);
    expect(requiresPolicyAcceptance(buildUser())).toBe(false);
    expect(requiresPolicyAcceptance(null)).toBe(false);
  });
});

describe("temporary login tokens", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("keeps pre-auth and enrollment tokens out of browser-readable storage", () => {
    persistPreAuthToken("pre-auth-secret");
    persistEnrollmentToken("enrollment-secret");

    expect(window.sessionStorage.getItem("cchis.pre_auth_token")).toBeNull();
    expect(window.sessionStorage.getItem("cchis.enrollment_token")).toBeNull();
  });

  it("clears legacy temporary tokens when hydrating auth state", () => {
    window.sessionStorage.setItem("cchis.pre_auth_token", "legacy-pre-auth-secret");
    window.sessionStorage.setItem("cchis.enrollment_token", "legacy-enrollment-secret");

    expect(readPreAuthToken()).toBeNull();
    expect(readEnrollmentToken()).toBeNull();
    expect(window.sessionStorage.getItem("cchis.pre_auth_token")).toBeNull();
    expect(window.sessionStorage.getItem("cchis.enrollment_token")).toBeNull();
  });
});

describe("session BFF step-up errors", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("preserves typed step-up errors so protected session actions can open confirmation", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: "This action needs a quick security check.",
          code: "step_up_required",
          purpose: "security_admin",
        }),
        {
          status: 403,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await expect(revokeAllProfileSessionsViaBff()).rejects.toMatchObject({
      name: "AuthStepUpRequiredError",
      purpose: "security_admin",
    } satisfies Partial<AuthStepUpRequiredError>);
  });
});
