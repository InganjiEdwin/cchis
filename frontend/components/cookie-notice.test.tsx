import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CookieNotice, getCookieNoticeStorageKey } from "@/components/cookie-notice";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

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

describe("CookieNotice", () => {
  const testStorageKeys = [
    getCookieNoticeStorageKey("cookies-2026-05"),
    getCookieNoticeStorageKey("cookies-2026-06"),
  ];

  function removeTestStorageKeys() {
    testStorageKeys.forEach((key) => {
      window.localStorage.removeItem(key);
    });
  }

  beforeEach(() => {
    Object.defineProperty(window, "localStorage", {
      value: createMemoryStorage(),
      configurable: true,
    });
    removeTestStorageKeys();
  });

  afterEach(() => {
    removeTestStorageKeys();
  });

  it("renders until dismissed and stores acknowledgement under the current version", async () => {
    const user = userEvent.setup();
    const storageKey = getCookieNoticeStorageKey("cookies-2026-05");

    render(React.createElement(CookieNotice, { version: "cookies-2026-05" }));

    expect(await screen.findByRole("region", { name: "Cookie notice" })).toBeInTheDocument();
    expect(screen.getByText(/We do not use advertising cookies/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy#cookies");

    await user.click(screen.getByRole("button", { name: "Got it" }));

    await waitFor(() => {
      expect(screen.queryByRole("region", { name: "Cookie notice" })).not.toBeInTheDocument();
    });
    expect(window.localStorage.getItem(storageKey)).toBe("true");
  });

  it("does not render after the current version has already been acknowledged", async () => {
    window.localStorage.setItem(getCookieNoticeStorageKey("cookies-2026-05"), "true");

    render(React.createElement(CookieNotice, { version: "cookies-2026-05" }));

    await waitFor(() => {
      expect(screen.queryByRole("region", { name: "Cookie notice" })).not.toBeInTheDocument();
    });
  });

  it("reappears when the cookie notice version changes", async () => {
    window.localStorage.setItem(getCookieNoticeStorageKey("cookies-2026-05"), "true");

    render(React.createElement(CookieNotice, { version: "cookies-2026-06" }));

    expect(await screen.findByRole("region", { name: "Cookie notice" })).toBeInTheDocument();
    expect(window.localStorage.getItem(getCookieNoticeStorageKey("cookies-2026-06"))).toBeNull();
  });
});
