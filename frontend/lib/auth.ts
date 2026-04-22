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
  access: string;
  refresh: string;
  user: CurrentUser;
  requires_2fa: false;
  requires_2fa_enrollment: false;
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
  access: string;
  refresh: string;
  user: CurrentUser;
  requires_2fa: false;
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
  access: string;
  refresh: string;
  user: CurrentUser;
  requires_2fa: false;
  enrollment_completed: true;
};

export type ConfirmTwoFactorEnrollmentResponse =
  | ConfirmTwoFactorEnrollmentAuthenticatedResponse
  | ConfirmTwoFactorEnrollmentLoginResponse;

export type RefreshResponse = {
  access: string;
  refresh?: string;
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

const ACCESS_TOKEN_KEY = "cchis.access_token";
const REFRESH_TOKEN_KEY = "cchis.refresh_token";
const PRE_AUTH_TOKEN_KEY = "cchis.pre_auth_token";
const ENROLLMENT_TOKEN_KEY = "cchis.enrollment_token";

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export function persistAccessToken(token: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (token) {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
    return;
  }

  window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function persistRefreshToken(token: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (token) {
    window.sessionStorage.setItem(REFRESH_TOKEN_KEY, token);
    return;
  }

  window.sessionStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function persistPreAuthToken(token: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (token) {
    window.sessionStorage.setItem(PRE_AUTH_TOKEN_KEY, token);
    return;
  }

  window.sessionStorage.removeItem(PRE_AUTH_TOKEN_KEY);
}

export function persistEnrollmentToken(token: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (token) {
    window.sessionStorage.setItem(ENROLLMENT_TOKEN_KEY, token);
    return;
  }

  window.sessionStorage.removeItem(ENROLLMENT_TOKEN_KEY);
}

export function readRefreshToken() {
  if (typeof window === "undefined") {
    return null;
  }

  return window.sessionStorage.getItem(REFRESH_TOKEN_KEY);
}

export function readAccessToken() {
  if (typeof window === "undefined") {
    return null;
  }

  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function readPreAuthToken() {
  if (typeof window === "undefined") {
    return null;
  }

  return window.sessionStorage.getItem(PRE_AUTH_TOKEN_KEY);
}

export function readEnrollmentToken() {
  if (typeof window === "undefined") {
    return null;
  }

  return window.sessionStorage.getItem(ENROLLMENT_TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}, accessToken?: string): Promise<T> {
  const headers = new Headers(init.headers);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
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
  return request<LoginResponse>("/auth/login/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function refreshAccessToken(refresh: string) {
  return request<RefreshResponse>("/auth/refresh/", {
    method: "POST",
    body: JSON.stringify({ refresh }),
  });
}

export async function fetchCurrentUser(accessToken: string) {
  return request<CurrentUser>("/auth/me/", { method: "GET" }, accessToken);
}

export async function updateAppearance(themePreference: ThemePreference, accessToken: string) {
  return request<UpdateAppearanceResponse>(
    "/auth/me/",
    {
      method: "PATCH",
      body: JSON.stringify({ theme_preference: themePreference }),
    },
    accessToken,
  );
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

export async function logout(refresh: string, accessToken: string) {
  return request<void>(
    "/auth/logout/",
    {
      method: "POST",
      body: JSON.stringify({ refresh }),
    },
    accessToken,
  );
}

export async function verifyTwoFactor(token: string, code: string) {
  return request<VerifyTwoFactorResponse>("/auth/verify-2fa/", {
    method: "POST",
    body: JSON.stringify({ token, code }),
  });
}

export async function beginTwoFactorEnrollment(token?: string, accessToken?: string) {
  return request<BeginTwoFactorEnrollmentResponse>(
    "/auth/2fa/setup/",
    {
      method: "POST",
      body: JSON.stringify(token ? { token } : {}),
    },
    accessToken,
  );
}

export async function confirmTwoFactorEnrollment(code: string, token?: string, accessToken?: string) {
  return request<ConfirmTwoFactorEnrollmentResponse>(
    "/auth/2fa/setup/confirm/",
    {
      method: "POST",
      body: JSON.stringify(token ? { token, code } : { code }),
    },
    accessToken,
  );
}
