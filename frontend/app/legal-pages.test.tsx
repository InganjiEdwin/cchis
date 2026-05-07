import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PrivacyPage from "@/app/privacy/page";
import TermsPage from "@/app/terms/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    back: vi.fn(),
  }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

describe("public legal pages", () => {
  it("keeps the privacy policy public and describes cookies and browser storage", () => {
    render(React.createElement(PrivacyPage));

    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText("Last updated: May 2026")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "6. Cookies and Browser Storage" })).toBeInTheDocument();
    expect(screen.getByText("cchis_refresh")).toBeInTheDocument();
    expect(screen.getByText("cchis.current_user")).toBeInTheDocument();
    expect(screen.getByText("cchis.cookie_notice_ack.*")).toBeInTheDocument();
    expect(screen.getByText("Cloudflare Turnstile")).toBeInTheDocument();
    expect(screen.getByText(/public access requests and after repeated failed sign-in attempts/i)).toBeInTheDocument();
  });

  it("keeps the terms page public and covers sign-in security cookies", () => {
    render(React.createElement(TermsPage));

    expect(screen.getByRole("heading", { name: "Terms of Service" })).toBeInTheDocument();
    expect(screen.getByText("Last updated: May 2026")).toBeInTheDocument();
    expect(screen.getByText(/CHIS uses essential sign-in and security cookies/i)).toBeInTheDocument();
    expect(screen.getByText(/Continued dashboard use requires accepting the current Terms and Privacy Policy/i)).toBeInTheDocument();
  });
});
