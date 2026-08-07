"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  acceptPoliciesViaBff,
  beginTwoFactorEnrollment as beginTwoFactorEnrollmentRequest,
  beginTwoFactorEnrollmentViaBff,
  confirmTwoFactorEnrollment as confirmTwoFactorEnrollmentRequest,
  confirmTwoFactorEnrollmentViaBff,
  fetchSession,
  login as loginRequest,
  logoutViaBff,
  normalizeCurrentUser,
  persistCurrentUser,
  persistEnrollmentToken,
  persistPreAuthToken,
  readEnrollmentToken,
  readPreAuthToken,
  requiresPolicyAcceptance as userRequiresPolicyAcceptance,
  updateAppearanceViaBff,
  updateProfileViaBff,
  verifyTwoFactor as verifyTwoFactorRequest,
  type CurrentUser,
  type ConfirmTwoFactorEnrollmentResponse,
  type LoginPayload,
  type PolicyAcceptancePayload,
  type PolicyAcceptanceState,
  type ThemePreference,
  type SessionResponse,
  type UpdateProfilePayload,
  type VerifyTwoFactorResponse,
} from "@/lib/auth";
import { queryKeys } from "@/lib/query-keys";
import { applyThemePreference, persistThemePreference } from "@/lib/theme-preference";
import { useCurrentUserQuery } from "@/queries/use-current-user-query";

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
  requiresPolicyAcceptance: boolean;
  login: (payload: LoginPayload) => Promise<CurrentUser | null>;
  verifyTwoFactor: (code: string) => Promise<VerifyTwoFactorResponse>;
  beginTwoFactorEnrollment: () => Promise<{
    manual_entry_key: string;
    provisioning_uri: string;
    account_name: string;
    issuer: string;
    two_factor_policy: "REQUIRED" | "OPTIONAL" | "NONE";
    is_totp_enabled: boolean;
  }>;
  updateAppearance: (themePreference: ThemePreference) => Promise<CurrentUser>;
  updateProfile: (payload: UpdateProfilePayload) => Promise<CurrentUser>;
  acceptPolicies: (payload: PolicyAcceptancePayload) => Promise<PolicyAcceptanceState>;
  confirmTwoFactorEnrollment: (code: string) => Promise<ConfirmTwoFactorEnrollmentResponse>;
  clearPendingEnrollment: () => void;
  clearPendingTwoFactor: () => void;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

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
  const queryClient = useQueryClient();
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(() => {
    if (initialSession?.authenticated && initialSession.user) {
      return normalizeCurrentUser(initialSession.user);
    }
    // Role and identity must come from a server-verified session, not editable browser storage.
    return null;
  });
  const [pendingTwoFactor, setPendingTwoFactor] = useState<PendingTwoFactorState | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    const token = readPreAuthToken();
    return token ? { tempToken: token } : null;
  });
  const [pendingEnrollment, setPendingEnrollment] = useState<PendingEnrollmentState | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    const token = readEnrollmentToken();
    return token ? { tempToken: token } : null;
  });
  const [isHydrating, setIsHydrating] = useState(initialSession === null && !currentUser);
  const currentUserQuery = useCurrentUserQuery({
    enabled: !pendingTwoFactor && !pendingEnrollment,
    initialSession,
  });

  const adoptEstablishedSession = useCallback(async () => {
    queryClient.removeQueries({ queryKey: queryKeys.auth.me() });

    const session = await queryClient.fetchQuery({
      queryKey: queryKeys.auth.me(),
      queryFn: fetchSession,
      staleTime: 0,
    });

    if (!isEstablishedSession(session)) {
      throw new Error("We could not establish a full dashboard session. Please sign in again.");
    }

    queryClient.setQueryData(queryKeys.auth.me(), session);
    const user = normalizeCurrentUser(session.user);
    setCurrentUser(user);
    persistCurrentUser(user);
    persistPreAuthToken(null);
    persistEnrollmentToken(null);
    setPendingTwoFactor(null);
    setPendingEnrollment(null);

    return user;
  }, [queryClient]);

  useEffect(() => {
    if (currentUserQuery.isPending && !currentUser) {
      setIsHydrating(true);
      return;
    }

    if (pendingTwoFactor || pendingEnrollment) {
      setIsHydrating(false);
      return;
    }

    if (currentUserQuery.data) {
      if (isEstablishedSession(currentUserQuery.data)) {
        persistPreAuthToken(null);
        persistEnrollmentToken(null);
        setPendingTwoFactor(null);
        setPendingEnrollment(null);
        const user = normalizeCurrentUser(currentUserQuery.data.user);
        setCurrentUser(user);
        persistCurrentUser(user);
      } else {
        persistCurrentUser(null);
        setCurrentUser(null);
      }
      setIsHydrating(false);
      return;
    }

    if (currentUserQuery.isError) {
      persistCurrentUser(null);
      setCurrentUser(null);
      setIsHydrating(false);
      return;
    }

    if (currentUser) {
      setIsHydrating(false);
    }
  }, [
    currentUser,
    currentUserQuery.data,
    currentUserQuery.isError,
    currentUserQuery.isPending,
    pendingEnrollment,
    pendingTwoFactor,
  ]);

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
      requiresPolicyAcceptance: userRequiresPolicyAcceptance(currentUser),
      async login(payload: LoginPayload) {
        const response = await loginRequest(payload);

        if (response.requires_2fa) {
          queryClient.setQueryData(queryKeys.auth.me(), {
            authenticated: false,
            user: null,
            access: null,
            session_source: null,
          } satisfies SessionResponse);
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
          queryClient.setQueryData(queryKeys.auth.me(), {
            authenticated: false,
            user: null,
            access: null,
            session_source: null,
          } satisfies SessionResponse);
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

        const response = await verifyTwoFactorRequest(pendingTwoFactor.tempToken, code);
        const user = await adoptEstablishedSession();
        return { ...response, user };
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

        const previousUser = currentUser;
        const optimisticUser = { ...currentUser, theme_preference: themePreference };

        setCurrentUser(optimisticUser);
        persistCurrentUser(optimisticUser);
        applyThemePreference(themePreference);
        persistThemePreference(themePreference);
        queryClient.setQueryData(queryKeys.auth.me(), {
          authenticated: true,
          user: optimisticUser,
          access: null,
          session_source: null,
        } satisfies SessionResponse);

        try {
          const user = normalizeCurrentUser(await updateAppearanceViaBff(themePreference));
          setCurrentUser(user);
          persistCurrentUser(user);
          applyThemePreference(user.theme_preference);
          persistThemePreference(user.theme_preference);
          queryClient.setQueryData(queryKeys.auth.me(), {
            authenticated: true,
            user,
            access: null,
            session_source: null,
          } satisfies SessionResponse);
          return user;
        } catch {
          // Appearance is cosmetic, so keep the local preference usable even if
          // profile persistence is temporarily unavailable.
          setCurrentUser(optimisticUser);
          persistCurrentUser(optimisticUser);
          applyThemePreference(optimisticUser.theme_preference);
          persistThemePreference(optimisticUser.theme_preference);
          queryClient.setQueryData(queryKeys.auth.me(), {
            authenticated: true,
            user: optimisticUser,
            access: null,
            session_source: null,
          } satisfies SessionResponse);
          return optimisticUser;
        }
      },
      async updateProfile(payload: UpdateProfilePayload) {
        if (!currentUser) {
          throw new Error("Your session expired. Please sign in again.");
        }

        const user = normalizeCurrentUser(await updateProfileViaBff(payload));
        setCurrentUser(user);
        persistCurrentUser(user);
        queryClient.setQueryData(queryKeys.auth.me(), {
          authenticated: true,
          user,
          access: null,
          session_source: null,
        } satisfies SessionResponse);
        return user;
      },
      async acceptPolicies(payload: PolicyAcceptancePayload) {
        const policyAcceptance = await acceptPoliciesViaBff(payload);

        if (currentUser) {
          const user = normalizeCurrentUser({
            ...currentUser,
            policy_acceptance: policyAcceptance,
          });
          setCurrentUser(user);
          persistCurrentUser(user);
          queryClient.setQueryData(queryKeys.auth.me(), {
            authenticated: true,
            user,
            access: null,
            session_source: null,
          } satisfies SessionResponse);
        }

        await Promise.all([
          queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() }),
          queryClient.invalidateQueries({ queryKey: queryKeys.auth.policyAcceptance() }),
        ]);

        return policyAcceptance;
      },
      async confirmTwoFactorEnrollment(code: string) {
        const token = pendingEnrollment?.tempToken;
        const response = token
          ? await confirmTwoFactorEnrollmentRequest(code, token)
          : await confirmTwoFactorEnrollmentViaBff(code);

        if (token) {
          const user = await adoptEstablishedSession();
          return {
            ...response,
            user,
            requires_2fa: false,
            enrollment_completed: true,
            session_established: true,
          };
        }

        const user = normalizeCurrentUser(response.user);
        setCurrentUser(user);
        persistCurrentUser(user);
        return { ...response, user };
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
          queryClient.clear();
          queryClient.setQueryData(queryKeys.auth.me(), {
            authenticated: false,
            user: null,
            access: null,
            session_source: null,
          } satisfies SessionResponse);
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
    [adoptEstablishedSession, currentUser, isHydrating, pendingEnrollment, pendingTwoFactor, queryClient],
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
