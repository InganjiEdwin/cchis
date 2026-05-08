import { describe, expect, it } from "vitest";

import type { CurrentUser } from "@/lib/auth";
import { hasActionCapability, hasPageCapability } from "@/lib/capabilities";
import { getVisibleNav } from "@/lib/navigation";

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

describe("dashboard capability helpers", () => {
  it("uses conservative legacy fallback capabilities matching the role contract", () => {
    const admin = buildUser("ADMIN");
    const supervisor = buildUser("SUPERVISOR");
    const analyst = buildUser("ANALYST");
    const chv = buildUser("CHV");

    expect(hasPageCapability(admin, "system")).toBe(true);
    expect(hasActionCapability(admin, "use_system_controls")).toBe(true);

    expect(hasPageCapability(supervisor, "chv_operations")).toBe(true);
    expect(hasPageCapability(supervisor, "system")).toBe(false);
    expect(hasActionCapability(supervisor, "trigger_alerts")).toBe(true);
    expect(hasActionCapability(supervisor, "approve_source_data_risky_imports")).toBe(false);

    expect(hasPageCapability(analyst, "system")).toBe(true);
    expect(hasPageCapability(analyst, "chv_operations")).toBe(false);
    expect(hasActionCapability(analyst, "manage_source_data_imports")).toBe(false);
    expect(hasActionCapability(analyst, "read_system_control_status")).toBe(true);

    expect(hasPageCapability(chv, "dashboard")).toBe(false);
  });

  it("builds visible navigation from page capabilities", () => {
    expect(getVisibleNav(buildUser("ADMIN")).map((item) => item.href)).toContain("/system");
    expect(getVisibleNav(buildUser("SUPERVISOR")).map((item) => item.href)).not.toContain("/system");
    expect(getVisibleNav(buildUser("SUPERVISOR")).map((item) => item.href)).toContain("/chvs");
    expect(getVisibleNav(buildUser("ANALYST")).map((item) => item.href)).toContain("/system");
    expect(getVisibleNav(buildUser("ANALYST")).map((item) => item.href)).not.toContain("/chvs");
  });
});
