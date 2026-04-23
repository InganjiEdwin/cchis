"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import {
  beginTwoFactorEnrollment as beginTwoFactorEnrollmentRequest,
  beginTwoFactorEnrollmentViaBff,
  confirmTwoFactorEnrollment as confirmTwoFactorEnrollmentRequest,
  confirmTwoFactorEnrollmentViaBff,
  fetchSession,
  login as loginRequest,
  logoutViaBff,
  persistCurrentUser,
  persistEnrollmentToken,
  persistPreAuthToken,
  readCurrentUser,
  readEnrollmentToken,
  readPreAuthToken,
  updateAppearanceViaBff,
  verifyTwoFactor as verifyTwoFactorRequest,
  type CurrentUser,
  type LoginPayload,
  type ThemePreference,
  type SessionResponse,
} from "@/lib/auth";

type PendingTwoFactorState = {
  tempToken: string;
};

type PendingEnrollmentState = {
  tempToken: string;
};

type AuthContextValue = {
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

function isEstablishedSession(session: SessionResponse): session is SessionResponse & {
  authenticated: true;
  user: CurrentUser;
} {
  return Boolean(session.authenticated && session.user);
}

export function AuthProvider({
  children,
  initialSession = null,
}: {
  children: React.ReactNode;
  initialSession?: SessionResponse | null;
}) {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(
    initialSession?.authenticated ? initialSession.user : null,
  );
  const [pendingTwoFactor, setPendingTwoFactor] = useState<PendingTwoFactorState | null>(null);
  const [pendingEnrollment, setPendingEnrollment] = useState<PendingEnrollmentState | null>(null);
  const [isHydrating, setIsHydrating] = useState(initialSession === null);
  const refreshInFlight = useRef<Promise<void> | null>(null);

  async function adoptEstablishedSession() {
    const session = await fetchSession();

    if (!isEstablishedSession(session)) {
      throw new Error("We could not establish a full dashboard session. Please sign in again.");
    }

    setCurrentUser(session.user);
    persistCurrentUser(session.user);
    persistPreAuthToken(null);
    persistEnrollmentToken(null);
    setPendingTwoFactor(null);
    setPendingEnrollment(null);

    return session.user;
  }

  useEffect(() => {
    const cachedUser = readCurrentUser();
    const preAuthToken = readPreAuthToken();
    const enrollmentToken = readEnrollmentToken();

    if (!initialSession && cachedUser) {
      setCurrentUser(cachedUser);
    }

    if (!initialSession && cachedUser) {
      setIsHydrating(false);
    }

    if (preAuthToken) {
      setPendingTwoFactor({ tempToken: preAuthToken });
    }

    if (enrollmentToken) {
      setPendingEnrollment({ tempToken: enrollmentToken });
    }

    if (initialSession) {
      if (initialSession.authenticated && initialSession.user) {
        persistCurrentUser(initialSession.user);
        setCurrentUser(initialSession.user);
      } else if (cachedUser) {
        persistCurrentUser(cachedUser);
      }

      setIsHydrating(false);
      return;
    }

    const hydrate = async () => {
      try {
        const session = await fetchSession();

        if (!session.authenticated || !session.user) {
          persistCurrentUser(null);
          setCurrentUser(null);
          return;
        }
        persistPreAuthToken(null);
        persistEnrollmentToken(null);
        setPendingTwoFactor(null);
        setPendingEnrollment(null);
        setCurrentUser(session.user);
        persistCurrentUser(session.user);
      } catch {
        persistCurrentUser(null);
        setCurrentUser(null);
      } finally {
        setIsHydrating(false);
      }
    };

    refreshInFlight.current = hydrate();
  }, [initialSession]);

  useEffect(() => {
    if (currentUser?.theme_preference) {
      applyThemePreference(currentUser.theme_preference);
      persistThemePreference(currentUser.theme_preference);
      return;
    }

    if (!isHydrating) {
      applyThemePreference(null);
      persistThemePreference(null);
    }
  }, [currentUser?.theme_preference, isHydrating]);

  const value = useMemo<AuthContextValue>(
    () => ({
      currentUser,
      pendingEnrollment,
      pendingTwoFactor,
      isHydrating,
      isAuthenticated: !!currentUser,
      async login(payload: LoginPayload) {
        const response = await loginRequest(payload);

        if (response.requires_2fa) {
          persistCurrentUser(null);
          setCurrentUser(null);
          persistPreAuthToken(response.temp_token);
          persistEnrollmentToken(null);
          const pendingState = { tempToken: response.temp_token };
          setPendingTwoFactor(pendingState);
          setPendingEnrollment(null);
          return null;
        }

        if (response.requires_2fa_enrollment) {
          persistCurrentUser(null);
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
        return adoptEstablishedSession();
      },
      async verifyTwoFactor(code: string) {
        if (!pendingTwoFactor?.tempToken) {
          throw new Error("Your verification session expired. Please sign in again.");
        }

        await verifyTwoFactorRequest(pendingTwoFactor.tempToken, code);
        return adoptEstablishedSession();
      },
      async beginTwoFactorEnrollment() {
        const token = pendingEnrollment?.tempToken;
        if (token) {
          return beginTwoFactorEnrollmentRequest(token);
        }
        return beginTwoFactorEnrollmentViaBff();
      },
      async updateAppearance(themePreference: ThemePreference) {
        if (!currentUser) {
          throw new Error("Your session expired. Please sign in again.");
        }

        const user = await updateAppearanceViaBff(themePreference);
        setCurrentUser(user);
        persistCurrentUser(user);
        return user;
      },
      async confirmTwoFactorEnrollment(code: string) {
        const token = pendingEnrollment?.tempToken;
        const response = token
          ? await confirmTwoFactorEnrollmentRequest(code, token)
          : await confirmTwoFactorEnrollmentViaBff(code);

        if (token) {
          return adoptEstablishedSession();
        }

        setCurrentUser(response.user);
        persistCurrentUser(response.user);
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
        try {
          if (currentUser) {
            await logoutViaBff();
          }
        } finally {
          persistCurrentUser(null);
          persistPreAuthToken(null);
          persistEnrollmentToken(null);
          persistThemePreference(null);
          applyThemePreference(null);
          setCurrentUser(null);
          setPendingTwoFactor(null);
          setPendingEnrollment(null);
        }
      },
    }),
    [currentUser, isHydrating, pendingEnrollment, pendingTwoFactor],
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
