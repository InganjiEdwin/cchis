export const CSRF_REJECTION_CODE = "cross_site_request_rejected";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const SHARED_ENVIRONMENTS = new Set(["staging", "production"]);

function getEnvironment() {
  return (process.env.CCHIS_ENVIRONMENT ?? process.env.NEXT_PUBLIC_CCHIS_ENVIRONMENT ?? "local")
    .trim()
    .toLowerCase();
}

export function isUnsafeMethod(method: string) {
  return UNSAFE_METHODS.has(method.toUpperCase());
}

export function getOriginFromUrl(value: string | null | undefined) {
  const trimmedValue = value?.trim();
  if (!trimmedValue) {
    return "";
  }

  try {
    return new URL(trimmedValue).origin;
  } catch {
    return "";
  }
}

function getFrontendAppOrigin() {
  return getOriginFromUrl(
    process.env.FRONTEND_APP_URL ?? process.env.NEXT_PUBLIC_FRONTEND_APP_URL ?? "http://localhost:3000",
  );
}

function getAllowedRequestOrigins(requestOrigin: string) {
  const origins = new Set<string>();
  const frontendOrigin = getFrontendAppOrigin();
  if (frontendOrigin) {
    origins.add(frontendOrigin);
  }

  if (!SHARED_ENVIRONMENTS.has(getEnvironment()) && requestOrigin) {
    origins.add(requestOrigin);
  }

  return origins;
}

function getHeaderOrigin(headers: Headers) {
  const origin = getOriginFromUrl(headers.get("origin"));
  if (origin) {
    return origin;
  }

  return getOriginFromUrl(headers.get("referer"));
}

export function validateBffUnsafeRequest({
  method,
  pathname,
  headers,
  requestOrigin,
}: {
  method: string;
  pathname: string;
  headers: Headers;
  requestOrigin: string;
}) {
  if (!pathname.startsWith("/api/") || !isUnsafeMethod(method)) {
    return null;
  }

  if ((headers.get("sec-fetch-site") ?? "").toLowerCase() === "cross-site") {
    return {
      detail: "Cross-site requests are not allowed for this action.",
      code: CSRF_REJECTION_CODE,
    };
  }

  const requestHeaderOrigin = getHeaderOrigin(headers);
  if (!requestHeaderOrigin) {
    return {
      detail: "Origin or referer is required for this action.",
      code: CSRF_REJECTION_CODE,
    };
  }

  if (!getAllowedRequestOrigins(requestOrigin).has(requestHeaderOrigin)) {
    return {
      detail: "Request origin is not allowed for this action.",
      code: CSRF_REJECTION_CODE,
    };
  }

  return null;
}

function getBackendOrigins() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";
  const backendOrigin = getOriginFromUrl(apiBaseUrl);
  const websocketOrigin = backendOrigin ? backendOrigin.replace(/^http/, "ws") : "";
  return { backendOrigin, websocketOrigin };
}

export function shouldApplyProductionCsp() {
  return SHARED_ENVIRONMENTS.has(getEnvironment()) || process.env.CCHIS_CSP_ENABLED === "true";
}

export function buildContentSecurityPolicy(nonce?: string) {
  const { backendOrigin, websocketOrigin } = getBackendOrigins();
  const connectSrc = ["'self'", backendOrigin, websocketOrigin].filter(Boolean).join(" ");
  const scriptSrc = nonce ? `script-src 'self' 'nonce-${nonce}'` : "script-src 'self' 'unsafe-inline'";
  const directives = [
    "default-src 'self'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "img-src 'self' data: blob:",
    `connect-src ${connectSrc}`,
    "font-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    scriptSrc,
    "form-action 'self'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
  ];

  if (getEnvironment() === "production") {
    directives.push("upgrade-insecure-requests");
  }

  return directives.join("; ");
}

export function createCspNonce() {
  return crypto.randomUUID().replaceAll("-", "");
}

export function applySecurityHeaders(headers: Headers, nonce?: string) {
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Referrer-Policy", "same-origin");
  headers.set("X-Frame-Options", "DENY");

  if (shouldApplyProductionCsp()) {
    headers.set("Content-Security-Policy", buildContentSecurityPolicy(nonce));
  }
}
