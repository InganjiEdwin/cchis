import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RequestAccessPage from "@/app/request-access/page";

const mockFetchAccessRequestOptions = vi.fn();
const mockSubmitAccessRequest = vi.fn();

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    fetchAccessRequestOptions: (...args: unknown[]) => mockFetchAccessRequestOptions(...args),
    submitAccessRequest: (...args: unknown[]) => mockSubmitAccessRequest(...args),
  };
});

describe("RequestAccessPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchAccessRequestOptions.mockResolvedValue({
      counties: ["Migori", "Kisumu"],
      wards: [
        { id: 1, name: "Suna East", county: "Migori", sub_county: "Suna" },
        { id: 2, name: "Central Sakwa", county: "Kisumu", sub_county: "Bondo" },
      ],
    });
  });

  it("loads public county and ward options", async () => {
    render(React.createElement(RequestAccessPage));

    expect(await screen.findByRole("option", { name: "Migori" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Suna East" })).toBeInTheDocument();
  });

  it("submits the aligned access request payload", async () => {
    const user = userEvent.setup();
    mockSubmitAccessRequest.mockResolvedValue({
      detail: "Access request submitted successfully.",
      review_status: "PENDING",
    });

    render(React.createElement(RequestAccessPage));

    await screen.findByRole("option", { name: "Migori" });
    await user.type(screen.getByLabelText("Full Name"), "Jane Doe");
    await user.type(screen.getByLabelText("Email Address"), "jane@example.com");
    await user.type(screen.getByLabelText("Phone Number"), "+254711000123");
    await user.selectOptions(screen.getByLabelText("Role"), "ANALYST");
    await user.selectOptions(screen.getByLabelText("County"), "Migori");
    await user.selectOptions(screen.getByLabelText("Administrative Ward"), "Suna East");
    await user.type(screen.getByLabelText(/Organization or Facility/i), "Migori County Hospital");
    await user.type(screen.getByLabelText(/Reason for Access/i), "Need situational dashboard access.");
    await user.click(screen.getByRole("button", { name: "Submit Request" }));

    await waitFor(() => {
      expect(mockSubmitAccessRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name: "Jane Doe",
          phone_number: "+254711000123",
          county: "Migori",
          administrative_ward: "Suna East",
          organization: "Migori County Hospital",
          desired_role: "ANALYST",
          contact_email: "jane@example.com",
          message: "Need situational dashboard access.",
          website: "",
          client_started_at_ms: expect.any(Number),
        }),
      );
    });
  });

  it("normalizes a phone number entered with 254 prefix", async () => {
    const user = userEvent.setup();
    mockSubmitAccessRequest.mockResolvedValue({
      detail: "Access request submitted successfully.",
      review_status: "PENDING",
    });

    render(React.createElement(RequestAccessPage));

    await screen.findByRole("option", { name: "Migori" });
    await user.type(screen.getByLabelText("Full Name"), "Jane Doe");
    await user.type(screen.getByLabelText("Email Address"), "jane@example.com");
    await user.type(screen.getByLabelText("Phone Number"), "254711000123");
    await user.selectOptions(screen.getByLabelText("Role"), "ANALYST");
    await user.selectOptions(screen.getByLabelText("County"), "Migori");
    await user.selectOptions(screen.getByLabelText("Administrative Ward"), "Suna East");
    await user.click(screen.getByRole("button", { name: "Submit Request" }));

    await waitFor(() => {
      expect(mockSubmitAccessRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          phone_number: "+254711000123",
        }),
      );
    });
  });

  it("normalizes a phone number entered with 07 prefix", async () => {
    const user = userEvent.setup();
    mockSubmitAccessRequest.mockResolvedValue({
      detail: "Access request submitted successfully.",
      review_status: "PENDING",
    });

    render(React.createElement(RequestAccessPage));

    await screen.findByRole("option", { name: "Migori" });
    await user.type(screen.getByLabelText("Full Name"), "Jane Doe");
    await user.type(screen.getByLabelText("Email Address"), "jane@example.com");
    await user.type(screen.getByLabelText("Phone Number"), "0711000123");
    await user.selectOptions(screen.getByLabelText("Role"), "ANALYST");
    await user.selectOptions(screen.getByLabelText("County"), "Migori");
    await user.selectOptions(screen.getByLabelText("Administrative Ward"), "Suna East");
    await user.click(screen.getByRole("button", { name: "Submit Request" }));

    await waitFor(() => {
      expect(mockSubmitAccessRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          phone_number: "+254711000123",
        }),
      );
    });
  });

  it("shows a field error for an invalid phone number and skips submit", async () => {
    const user = userEvent.setup();

    render(React.createElement(RequestAccessPage));

    await screen.findByRole("option", { name: "Migori" });
    await user.type(screen.getByLabelText("Full Name"), "Jane Doe");
    await user.type(screen.getByLabelText("Email Address"), "jane@example.com");
    await user.type(screen.getByLabelText("Phone Number"), "12345");
    await user.selectOptions(screen.getByLabelText("Role"), "ANALYST");
    await user.selectOptions(screen.getByLabelText("County"), "Migori");
    await user.selectOptions(screen.getByLabelText("Administrative Ward"), "Suna East");
    await user.click(screen.getByRole("button", { name: "Submit Request" }));

    expect(await screen.findByText("Use +254711000123, 254711000123, or 0711000123.")).toBeInTheDocument();
    expect(mockSubmitAccessRequest).not.toHaveBeenCalled();
  });
});
