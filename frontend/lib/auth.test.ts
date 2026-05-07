import { describe, expect, it } from "vitest";

import { requiresPolicyAcceptance, type CurrentUser, type PolicyAcceptanceState } from "@/lib/auth";

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
