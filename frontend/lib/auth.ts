export type UserRole = "ADMIN" | "SUPERVISOR" | "ANALYST" | "CHV";
export type ThemePreference = "SYSTEM" | "LIGHT" | "DARK";

export type ProfileCapabilities = {
  can_change_password: boolean;
  can_update_appearance: boolean;
  can_manage_totp: boolean;
  can_view_own_activity: boolean;
  can_update_identity: boolean;
  can_review_sessions: boolean;
  can_generate_profile_report: boolean;
  identity_update_mode: "admin_managed" | "totp_step_up";
  mode: "auth_contract_backed_profile";
};

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
  account_created_at?: string;
  last_login_at?: string | null;
  profile_capabilities?: ProfileCapabilities;
};

export function buildDefaultProfileCapabilities(
  user: Pick<CurrentUser, "is_active" | "two_factor_policy" | "is_totp_enabled">,
): ProfileCapabilities {
  const isActive = user.is_active;
  const twoFactorPolicy = user.two_factor_policy ?? "NONE";
  const canUpdateIdentity = isActive && user.is_totp_enabled === true && twoFactorPolicy !== "NONE";

  return {
    can_change_password: isActive,
    can_update_appearance: isActive,
    can_manage_totp: isActive && twoFactorPolicy !== "NONE",
    can_view_own_activity: isActive,
    can_update_identity: canUpdateIdentity,
    can_review_sessions: false,
    can_generate_profile_report: false,
    identity_update_mode: canUpdateIdentity ? "totp_step_up" : "admin_managed",
    mode: "auth_contract_backed_profile",
  };
}

export function normalizeCurrentUser(user: CurrentUser): CurrentUser {
  if (user.profile_capabilities) {
    return user;
  }

  return {
    ...user,
    profile_capabilities: buildDefaultProfileCapabilities(user),
  };
}

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
  second_factor_method?: "totp" | "recovery_code";
  recovery_codes_remaining?: number;
  recovery_codes_low?: boolean;
};
export type RecoveryCodeLoginNotice = {
  remaining_count: number;
  created_at: string;
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
  recovery_codes: string[];
  recovery_codes_generated: boolean;
};

export type ConfirmTwoFactorEnrollmentLoginResponse = {
  user: CurrentUser;
  requires_2fa: false;
  enrollment_completed: true;
  session_established: true;
  recovery_codes: string[];
  recovery_codes_generated: boolean;
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
export type UpdateProfilePayload = Partial<Pick<CurrentUser, "username" | "email" | "full_name" | "phone_number">>;
export type VerifyProfileIdentityTwoFactorResponse = {
  detail: string;
};
export type PasswordResetRequestResponse = {
  detail: string;
};
export type PasswordResetConfirmResponse = {
  detail: string;
};
export type ChangePasswordPayload = {
  current_password: string;
  new_password: string;
};
export type ChangePasswordResponse = {
  detail: string;
};
export type RecoveryCodeStatusResponse = {
  remaining_count: number;
  total_count: number;
  last_generated_at: string | null;
  last_used_at: string | null;
  can_regenerate: boolean;
};
export type RegenerateRecoveryCodesPayload = {
  current_password: string;
  code: string;
};
export type RegenerateRecoveryCodesResponse = RecoveryCodeStatusResponse & {
  recovery_codes: string[];
  recovery_codes_generated: boolean;
};
export type ProfileActivityEvent = {
  id: number;
  event_type: string;
  status: "SUCCESS" | "FAILED" | "FAILURE" | "INFO";
  title: string;
  description: string;
  created_at: string;
};
export type ProfileActivityFilters = {
  page?: number;
  page_size?: number;
  event_type?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  security_only?: boolean;
  include_refresh_events?: boolean;
};
export type ProfileActivityResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ProfileActivityEvent[];
  events?: ProfileActivityEvent[];
  filters: {
    event_type: string;
    status: string;
    date_from: string;
    date_to: string;
    security_only: boolean;
    include_refresh_events: boolean;
    page: number;
    page_size: number;
  };
  capabilities: {
    can_view_own_activity: boolean;
    mode: "self_scoped_auth_activity";
  };
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
const BFF_REQUEST_TIMEOUT_MS = 30000;
const USERNAME_PATTERN = /^[\w.@+-]+$/;

const PRE_AUTH_TOKEN_KEY = "cchis.pre_auth_token";
const ENROLLMENT_TOKEN_KEY = "cchis.enrollment_token";
const CURRENT_USER_KEY = "cchis.current_user";
const RECOVERY_CODE_LOGIN_NOTICE_KEY = "cchis.recovery_code_login_notice";

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

function stringifyErrorValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => stringifyErrorValue(item)).filter(Boolean).join(" ");
  }

  if (value && typeof value === "object") {
    return formatResponseErrorDetail(value as Record<string, unknown>);
  }

  return "";
}

function formatResponseErrorDetail(data: Record<string, unknown>) {
  const errors = data.errors && typeof data.errors === "object" && !Array.isArray(data.errors)
    ? data.errors as Record<string, unknown>
    : data;
  const fieldMessages = Object.entries(errors)
    .filter(([field]) => field !== "detail" && field !== "errors")
    .map(([field, value]) => {
      const message = stringifyErrorValue(value);
      return message ? `${field.replaceAll("_", " ")}: ${message}` : "";
    })
    .filter(Boolean);

  if (fieldMessages.length > 0) {
    return fieldMessages.join(" ");
  }

  return typeof data.detail === "string" ? data.detail : "Request failed.";
}

export function isValidUsername(value: string) {
  return USERNAME_PATTERN.test(value);
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export function persistCurrentUser(user: CurrentUser | null) {
  if (typeof window === "undefined") {
    return;
  }

  const serialized = user ? JSON.stringify(normalizeCurrentUser(user)) : null;
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
    const parsed = normalizeCurrentUser(JSON.parse(source) as CurrentUser);

    if (persistedUser && !sessionUser) {
      writeStorageValue(CURRENT_USER_KEY, JSON.stringify(parsed), window.sessionStorage);
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

export function persistRecoveryCodeLoginNotice(remainingCount: number) {
  if (typeof window === "undefined") {
    return;
  }

  writeStorageValue(
    RECOVERY_CODE_LOGIN_NOTICE_KEY,
    JSON.stringify({
      remaining_count: remainingCount,
      created_at: new Date().toISOString(),
    } satisfies RecoveryCodeLoginNotice),
    window.sessionStorage,
  );
}

export function readRecoveryCodeLoginNotice() {
  if (typeof window === "undefined") {
    return null;
  }

  const rawNotice = readStorageValue(RECOVERY_CODE_LOGIN_NOTICE_KEY, window.sessionStorage);
  if (!rawNotice) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawNotice) as Partial<RecoveryCodeLoginNotice>;
    if (typeof parsed.remaining_count !== "number" || typeof parsed.created_at !== "string") {
      return null;
    }

    return {
      remaining_count: parsed.remaining_count,
      created_at: parsed.created_at,
    } satisfies RecoveryCodeLoginNotice;
  } catch {
    return null;
  }
}

export function clearRecoveryCodeLoginNotice() {
  if (typeof window === "undefined") {
    return;
  }

  writeStorageValue(RECOVERY_CODE_LOGIN_NOTICE_KEY, null, window.sessionStorage);
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
    if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) {
      throw new Error("Request timed out. Please try again.");
    }
    throw error;
  }

  window.clearTimeout(timeoutId);

  if (!response.ok) {
    let detail = "Request failed.";

    try {
      const data = (await response.json()) as Record<string, unknown>;
      detail = formatResponseErrorDetail(data);
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
  const timeoutId = window.setTimeout(() => controller.abort(), BFF_REQUEST_TIMEOUT_MS);
  const bffUrl =
    typeof window === "undefined" ? path : new URL(path.startsWith("/") ? path : `/${path}`, window.location.origin);

  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;

  try {
    response = await fetch(bffUrl, {
      ...init,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (error) {
    window.clearTimeout(timeoutId);
    if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) {
      throw new Error("Request timed out. Please try again.");
    }
    throw error;
  }

  window.clearTimeout(timeoutId);

  if (!response.ok) {
    let detail = "Request failed.";

    try {
      const data = (await response.json()) as Record<string, unknown>;
      detail = formatResponseErrorDetail(data);
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

export async function verifyProfileIdentityTwoFactorViaBff(code: string) {
  return requestBff<VerifyProfileIdentityTwoFactorResponse>("/api/session/profile-identity/verify-2fa", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export async function updateProfileViaBff(payload: UpdateProfilePayload) {
  return requestBff<CurrentUser>("/api/session/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function changePasswordViaBff(payload: ChangePasswordPayload) {
  return requestBff<ChangePasswordResponse>("/api/session/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchProfileActivityViaBff(filters: ProfileActivityFilters = {}) {
  const query = new URLSearchParams();

  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });

  return requestBff<ProfileActivityResponse>(`/api/session/activity?${query.toString()}`, {
    method: "GET",
  });
}

export async function fetchRecoveryCodeStatusViaBff() {
  return requestBff<RecoveryCodeStatusResponse>("/api/session/2fa/recovery-codes", {
    method: "GET",
  });
}

export async function regenerateRecoveryCodesViaBff(payload: RegenerateRecoveryCodesPayload) {
  return requestBff<RegenerateRecoveryCodesResponse>("/api/session/2fa/recovery-codes/regenerate", {
    method: "POST",
    body: JSON.stringify(payload),
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
