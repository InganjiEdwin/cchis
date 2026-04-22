import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PageFrame } from "@/components/page-frame";

vi.mock("@/components/trigger-alert-panel", () => ({
  TriggerAlertPanel() {
    return React.createElement("div", null, "Trigger panel mock");
  },
}));

describe("PageFrame", () => {
  it("shows the trigger panel for privileged roles", () => {
    render(
      React.createElement(
        PageFrame,
        { title: "Alerts", summary: "Operational alert management", role: "ADMIN" },
        React.createElement("div", null, "Body content"),
      ),
    );

    expect(screen.getByText("ADMIN")).toBeInTheDocument();
    expect(screen.getByText("Trigger panel mock")).toBeInTheDocument();
    expect(screen.queryByText("Read-only access for this role.")).not.toBeInTheDocument();
  });

  it("shows the read-only state for non-trigger roles", () => {
    render(
      React.createElement(
        PageFrame,
        { title: "System", summary: "Freshness summary", role: "ANALYST" },
        React.createElement("div", null, "Body content"),
      ),
    );

    expect(screen.getByText("ANALYST")).toBeInTheDocument();
    expect(screen.getByText("Read-only access for this role.")).toBeInTheDocument();
    expect(screen.queryByText("Trigger panel mock")).not.toBeInTheDocument();
  });
});
