"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import {
  beginTwoFactorEnrollment as beginTwoFactorEnrollmentRequest,
  confirmTwoFactorEnrollment as confirmTwoFactorEnrollmentRequest,
  fetchCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  persistAccessToken,
  persistEnrollmentToken,
  persistPreAuthToken,
  persistRefreshToken,
  readAccessToken,
  readEnrollmentToken,
  readPreAuthToken,
  readRefreshToken,
  refreshAccessToken,
  updateAppearance as updateAppearanceRequest,
  verifyTwoFactor as verifyTwoFactorRequest,
  type CurrentUser,
  type LoginPayload,
  type ThemePreference,
} from "@/lib/auth";

type PendingTwoFactorState = {
  tempToken: string;
};

type PendingEnrollmentState = {
  tempToken: string;
};

type AuthContextValue = {
  accessToken: string | null;
  currentUser: CurrentUser | null;
  pendingTwoFactor: PendingTwoFactorState | null;
  pendingEnrollment: PendingEnrollmentState | null;
  isHydrating: boolean;
  isAuthenticated: boolean;
  login: (payload: LoginPayload) => Promise<CurrentUser | null>;
  verifyTwoFactor: (code: string) => Promise<CurrentUser>;
  beginTwoFactorEnrollment: () => Promise<{
    manual_entry_key: string;
    provisioning_uri: string;
    account_name: string;
    issuer: string;
    two_factor_policy: "REQUIRED" | "OPTIONAL" | "NONE";
    is_totp_enabled: boolean;
  }>;
  updateAppearance: (themePreference: ThemePreference) => Promise<CurrentUser>;
  confirmTwoFactorEnrollment: (code: string) => Promise<CurrentUser>;
  clearPendingEnrollment: () => void;
  clearPendingTwoFactor: () => void;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const THEME_PREFERENCE_KEY = "cchis.theme_preference";

function applyThemePreference(themePreference: ThemePreference | null) {
  if (typeof document === "undefined") {
    return;
  }

  if (!themePreference || themePreference === "SYSTEM") {
    document.documentElement.removeAttribute("data-theme");
    return;
  }

  document.documentElement.setAttribute("data-theme", themePreference.toLowerCase());
}

function persistThemePreference(themePreference: ThemePreference | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (!themePreference || themePreference === "SYSTEM") {
    window.localStorage.removeItem(THEME_PREFERENCE_KEY);
    return;
  }

  window.localStorage.setItem(THEME_PREFERENCE_KEY, themePreference);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [pendingTwoFactor, setPendingTwoFactor] = useState<PendingTwoFactorState | null>(null);
  const [pendingEnrollment, setPendingEnrollment] = useState<PendingEnrollmentState | null>(null);
  const [isHydrating, setIsHydrating] = useState(true);
  const refreshInFlight = useRef<Promise<void> | null>(null);

  useEffect(() => {
    const access = readAccessToken();
    const refresh = readRefreshToken();
    const preAuthToken = readPreAuthToken();
    const enrollmentToken = readEnrollmentToken();

    if (access) {
      setAccessToken(access);
    }

    if (preAuthToken) {
      setPendingTwoFactor({ tempToken: preAuthToken });
    }

    if (enrollmentToken) {
      setPendingEnrollment({ tempToken: enrollmentToken });
    }

    if (!refresh) {
      setIsHydrating(false);
      return;
    }

    const hydrate = async () => {
      try {
        const refreshed = await refreshAccessToken(refresh);
        setAccessToken(refreshed.access);
        persistAccessToken(refreshed.access);
        if (refreshed.refresh) {
          persistRefreshToken(refreshed.refresh);
        }
        persistPreAuthToken(null);
        persistEnrollmentToken(null);
        setPendingTwoFactor(null);
        setPendingEnrollment(null);
        const user = await fetchCurrentUser(refreshed.access);
        setCurrentUser(user);
      } catch {
        persistAccessToken(null);
        persistRefreshToken(null);
        persistPreAuthToken(null);
        persistEnrollmentToken(null);
        setAccessToken(null);
        setCurrentUser(null);
        setPendingTwoFactor(null);
        setPendingEnrollment(null);
      } finally {
        setIsHydrating(false);
      }
    };

    refreshInFlight.current = hydrate();
  }, []);

  useEffect(() => {
    if (currentUser?.theme_preference) {
      applyThemePreference(currentUser.theme_preference);
      persistThemePreference(currentUser.theme_preference);
      return;
    }

    if (!isHydrating && !readRefreshToken()) {
      applyThemePreference(null);
      persistThemePreference(null);
    }
  }, [currentUser?.theme_preference, isHydrating]);

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken,
      currentUser,
      pendingEnrollment,
      pendingTwoFactor,
      isHydrating,
      isAuthenticated: !!accessToken && !!currentUser,
      async login(payload: LoginPayload) {
        const response = await loginRequest(payload);

        if (response.requires_2fa) {
          persistAccessToken(null);
          persistRefreshToken(null);
          setAccessToken(null);
          setCurrentUser(null);
          persistPreAuthToken(response.temp_token);
          persistEnrollmentToken(null);
          const pendingState = { tempToken: response.temp_token };
          setPendingTwoFactor(pendingState);
          setPendingEnrollment(null);
          return null;
        }

        if (response.requires_2fa_enrollment) {
          persistAccessToken(null);
          persistRefreshToken(null);
          setAccessToken(null);
          setCurrentUser(null);
          persistPreAuthToken(null);
          persistEnrollmentToken(response.temp_token);
          setPendingTwoFactor(null);
          setPendingEnrollment({ tempToken: response.temp_token });
          return null;
        }

        persistPreAuthToken(null);
        persistEnrollmentToken(null);
        setPendingTwoFactor(null);
        setPendingEnrollment(null);
        setAccessToken(response.access);
        persistAccessToken(response.access);
        setCurrentUser(response.user);
        persistRefreshToken(response.refresh);
        return response.user;
      },
      async verifyTwoFactor(code: string) {
        if (!pendingTwoFactor?.tempToken) {
          throw new Error("Your verification session expired. Please sign in again.");
        }

        const response = await verifyTwoFactorRequest(pendingTwoFactor.tempToken, code);
        persistPreAuthToken(null);
        setPendingTwoFactor(null);
        setAccessToken(response.access);
        persistAccessToken(response.access);
        setCurrentUser(response.user);
        persistRefreshToken(response.refresh);
        return response.user;
      },
      async beginTwoFactorEnrollment() {
        const token = pendingEnrollment?.tempToken;
        return beginTwoFactorEnrollmentRequest(token, token ? undefined : accessToken ?? undefined);
      },
      async updateAppearance(themePreference: ThemePreference) {
        if (!accessToken) {
          throw new Error("Your session expired. Please sign in again.");
        }

        const user = await updateAppearanceRequest(themePreference, accessToken);
        setCurrentUser(user);
        return user;
      },
      async confirmTwoFactorEnrollment(code: string) {
        const token = pendingEnrollment?.tempToken;
        const response = await confirmTwoFactorEnrollmentRequest(code, token, token ? undefined : accessToken ?? undefined);

        if ("access" in response) {
          persistEnrollmentToken(null);
          setPendingEnrollment(null);
          setAccessToken(response.access);
          persistAccessToken(response.access);
          setCurrentUser(response.user);
          persistRefreshToken(response.refresh);
          return response.user;
        }

        setCurrentUser(response.user);
        return response.user;
      },
      clearPendingEnrollment() {
        persistEnrollmentToken(null);
        setPendingEnrollment(null);
      },
      clearPendingTwoFactor() {
        persistPreAuthToken(null);
        setPendingTwoFactor(null);
      },
      async logout() {
        const refresh = readRefreshToken();

        try {
          if (refresh && accessToken) {
            await logoutRequest(refresh, accessToken);
          }
        } finally {
          persistAccessToken(null);
          persistRefreshToken(null);
          persistPreAuthToken(null);
          persistEnrollmentToken(null);
          persistThemePreference(null);
          applyThemePreference(null);
          setAccessToken(null);
          setCurrentUser(null);
          setPendingTwoFactor(null);
          setPendingEnrollment(null);
        }
      },
    }),
    [accessToken, currentUser, isHydrating, pendingEnrollment, pendingTwoFactor],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }

  return context;
}
