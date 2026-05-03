import { describe, expect, it } from "vitest";

import {
  GENERATED_PASSWORD_LENGTH,
  generateStrongPassword,
  getPasswordPolicyError,
  getPasswordPolicyRequirements,
  isStrongPassword,
} from "@/lib/password-policy";

describe("password policy", () => {
  it("requires the same visible complexity rules the backend enforces", () => {
    const requirements = getPasswordPolicyRequirements("longpasswordonly");

    expect(requirements.find((requirement) => requirement.id === "length")?.isMet).toBe(true);
    expect(requirements.find((requirement) => requirement.id === "lowercase")?.isMet).toBe(true);
    expect(requirements.find((requirement) => requirement.id === "uppercase")?.isMet).toBe(false);
    expect(requirements.find((requirement) => requirement.id === "number")?.isMet).toBe(false);
    expect(requirements.find((requirement) => requirement.id === "symbol")?.isMet).toBe(false);
    expect(getPasswordPolicyError("longpasswordonly")).toContain("uppercase");
  });

  it("accepts a password that satisfies the policy", () => {
    expect(isStrongPassword("NewStrongPass123!")).toBe(true);
    expect(getPasswordPolicyError("NewStrongPass123!")).toBeNull();
  });

  it("generates a strong password with secure random character coverage", () => {
    const generatedPassword = generateStrongPassword();

    expect(generatedPassword).toHaveLength(GENERATED_PASSWORD_LENGTH);
    expect(isStrongPassword(generatedPassword)).toBe(true);
  });
});
