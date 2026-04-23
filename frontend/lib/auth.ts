export type UserRole = "ADMIN" | "SUPERVISOR" | "ANALYST" | "CHV";
export type ThemePreference = "SYSTEM" | "LIGHT" | "DARK";

export type CurrentUser = {
  id: number;
  username: string;
  email: string;
  full_name: string;
  phone_number: string | null;
  role: UserRole;
  theme_preference: ThemePreference;
  ward: number | null;
  ward_name: string | null;
  scope_type?: "BROAD" | "WARD" | "NONE";
  scope_ward_id?: number | null;
  two_factor_policy?: "REQUIRED" | "OPTIONAL" | "NONE";
  is_totp_enabled?: boolean;
  is_active: boolean;
};

export type LoginSuccessResponse = {
  user: CurrentUser;
  requires_2fa: false;
  requires_2fa_enrollment: false;
  session_established: true;
};

export type LoginTwoFactorResponse = {
  requires_2fa: true;
  requires_2fa_enrollment: false;
  temp_token: string;
};

export type LoginEnrollmentResponse = {
  requires_2fa: false;
  requires_2fa_enrollment: true;
  temp_token: string;
  detail: string;
};

export type LoginResponse = LoginSuccessResponse | LoginTwoFactorResponse | LoginEnrollmentResponse;
export type LoginPayload = {
  username: string;
  password: string;
  turnstile_token?: string;
};

export type VerifyTwoFactorResponse = {
  user: CurrentUser;
  requires_2fa: false;
  session_established: true;
};

export type BeginTwoFactorEnrollmentResponse = {
  manual_entry_key: string;
  provisioning_uri: string;
  account_name: string;
  issuer: string;
  two_factor_policy: "REQUIRED" | "OPTIONAL" | "NONE";
  is_totp_enabled: boolean;
};

export type ConfirmTwoFactorEnrollmentAuthenticatedResponse = {
  detail: string;
  user: CurrentUser;
  enrollment_completed: true;
};

export type ConfirmTwoFactorEnrollmentLoginResponse = {
  user: CurrentUser;
  requires_2fa: false;
  enrollment_completed: true;
  session_established: true;
};

export type ConfirmTwoFactorEnrollmentResponse =
  | ConfirmTwoFactorEnrollmentAuthenticatedResponse
  | ConfirmTwoFactorEnrollmentLoginResponse;

export type SessionResponse = {
  authenticated: boolean;
  user: CurrentUser | null;
  access: string | null;
  session_source: "access" | "refresh" | null;
};

export type UpdateAppearanceResponse = CurrentUser;
export type PasswordResetRequestResponse = {
  detail: string;
};
export type PasswordResetConfirmResponse = {
  detail: string;
};
export type PasswordResetValidateResponse = {
  detail: string;
  valid: boolean;
};
export type AccessRequestOptionsResponse = {
  counties: string[];
  wards: Array<{
    id: number;
    name: string;
    county: string;
    sub_county: string;
  }>;
};
export type AccessRequestPayload = {
  full_name: string;
  phone_number?: string;
  county: string;
  administrative_ward: string;
  organization?: string;
  desired_role: UserRole;
  contact_email: string;
  message?: string;
  website?: string;
  client_started_at_ms?: number;
  turnstile_token?: string;
};
export type AccessRequestResponse = {
  detail: string;
  review_status: "PENDING" | "APPROVED" | "REJECTED";
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000/api/v1";
const REQUEST_TIMEOUT_MS = 10000;

const PRE_AUTH_TOKEN_KEY = "cchis.pre_auth_token";
const ENROLLMENT_TOKEN_KEY = "cchis.enrollment_token";
const CURRENT_USER_KEY = "cchis.current_user";

function readStorageValue(key: string, storage: Storage) {
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorageValue(key: string, value: string | null, storage: Storage) {
  try {
    if (value) {
      storage.setItem(key, value);
      return;
    }

    storage.removeItem(key);
  } catch {
    // Ignore storage write failures in constrained browser contexts.
  }
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export function persistCurrentUser(user: CurrentUser | null) {
  if (typeof window === "undefined") {
    return;
  }

  const serialized = user ? JSON.stringify(user) : null;
  writeStorageValue(CURRENT_USER_KEY, serialized, window.localStorage);
  writeStorageValue(CURRENT_USER_KEY, serialized, window.sessionStorage);
}

export function persistPreAuthToken(token: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  writeStorageValue(PRE_AUTH_TOKEN_KEY, token, window.sessionStorage);
}

export function persistEnrollmentToken(token: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  writeStorageValue(ENROLLMENT_TOKEN_KEY, token, window.sessionStorage);
}

export function readCurrentUser() {
  if (typeof window === "undefined") {
    return null;
  }

  const persistedUser = readStorageValue(CURRENT_USER_KEY, window.localStorage);
  const sessionUser = readStorageValue(CURRENT_USER_KEY, window.sessionStorage);
  const source = persistedUser ?? sessionUser;

  if (!source) {
    return null;
  }

  try {
    const parsed = JSON.parse(source) as CurrentUser;

    if (persistedUser && !sessionUser) {
      writeStorageValue(CURRENT_USER_KEY, persistedUser, window.sessionStorage);
    }

    return parsed;
  } catch {
    writeStorageValue(CURRENT_USER_KEY, null, window.localStorage);
    writeStorageValue(CURRENT_USER_KEY, null, window.sessionStorage);
    return null;
  }
}

export function readPreAuthToken() {
  if (typeof window === "undefined") {
    return null;
  }

  return readStorageValue(PRE_AUTH_TOKEN_KEY, window.sessionStorage);
}

export function readEnrollmentToken() {
  if (typeof window === "undefined") {
    return null;
  }

  return readStorageValue(ENROLLMENT_TOKEN_KEY, window.sessionStorage);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (error) {
    window.clearTimeout(timeoutId);
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw error;
  }

  window.clearTimeout(timeoutId);

  if (!response.ok) {
    let detail = "Request failed.";

    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail ?? detail;
    } catch {
      // Ignore parse failures and keep the generic message.
    }

    throw new Error(detail);
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

async function requestBff<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;

  try {
    response = await fetch(path, {
      ...init,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (error) {
    window.clearTimeout(timeoutId);
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw error;
  }

  window.clearTimeout(timeoutId);

  if (!response.ok) {
    let detail = "Request failed.";

    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail ?? detail;
    } catch {
      // Ignore parse failures and keep the generic message.
    }

    throw new Error(detail);
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function login(payload: LoginPayload) {
  return requestBff<LoginResponse>("/api/session/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchSession() {
  return requestBff<SessionResponse>("/api/session", { method: "GET" });
}

export async function updateAppearanceViaBff(themePreference: ThemePreference) {
  return requestBff<UpdateAppearanceResponse>("/api/session/me", {
    method: "PATCH",
    body: JSON.stringify({ theme_preference: themePreference }),
  });
}

export async function requestPasswordReset(identifier: string) {
  return request<PasswordResetRequestResponse>("/auth/password-reset/request/", {
    method: "POST",
    body: JSON.stringify({ identifier }),
  });
}

export async function validatePasswordResetToken(token: string) {
  const query = new URLSearchParams({ token });
  return request<PasswordResetValidateResponse>(`/auth/password-reset/confirm/?${query.toString()}`, {
    method: "GET",
  });
}

export async function confirmPasswordReset(token: string, newPassword: string) {
  return request<PasswordResetConfirmResponse>("/auth/password-reset/confirm/", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function fetchAccessRequestOptions() {
  return request<AccessRequestOptionsResponse>("/auth/access/request/options/", {
    method: "GET",
  });
}

export async function submitAccessRequest(payload: AccessRequestPayload) {
  return request<AccessRequestResponse>("/auth/access/request/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function logoutViaBff() {
  return requestBff<void>("/api/session/logout", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function verifyTwoFactor(token: string, code: string) {
  return requestBff<VerifyTwoFactorResponse>("/api/session/verify-2fa", {
    method: "POST",
    body: JSON.stringify({ token, code }),
  });
}

export async function beginTwoFactorEnrollment(token?: string) {
  return requestBff<BeginTwoFactorEnrollmentResponse>("/api/session/2fa/setup", {
    method: "POST",
    body: JSON.stringify(token ? { token } : {}),
  });
}

export async function beginTwoFactorEnrollmentViaBff() {
  return beginTwoFactorEnrollment();
}

export async function confirmTwoFactorEnrollment(code: string, token?: string) {
  return requestBff<ConfirmTwoFactorEnrollmentResponse>("/api/session/2fa/setup/confirm", {
    method: "POST",
    body: JSON.stringify(token ? { token, code } : { code }),
  });
}

export async function confirmTwoFactorEnrollmentViaBff(code: string) {
  return confirmTwoFactorEnrollment(code);
}
