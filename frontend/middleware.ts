import { NextResponse, type NextRequest } from "next/server";

import {
  applySecurityHeaders,
  buildContentSecurityPolicy,
  createCspNonce,
  shouldApplyProductionCsp,
  validateBffUnsafeRequest,
} from "@/lib/request-security";

export function middleware(request: NextRequest) {
  const requestHeaders = new Headers(request.headers);
  const currentPath = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  const cspNonce = shouldApplyProductionCsp() ? createCspNonce() : undefined;

  requestHeaders.set("x-cchis-current-path", currentPath);
  if (cspNonce) {
    requestHeaders.set("x-nonce", cspNonce);
    requestHeaders.set("Content-Security-Policy", buildContentSecurityPolicy(cspNonce));
  }

  const validationError = validateBffUnsafeRequest({
    method: request.method,
    pathname: request.nextUrl.pathname,
    headers: request.headers,
    requestOrigin: request.nextUrl.origin,
  });

  if (validationError) {
    const response = NextResponse.json(validationError, { status: 403 });
    applySecurityHeaders(response.headers, cspNonce);
    return response;
  }

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
  applySecurityHeaders(response.headers, cspNonce);
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|.*\\..*).*)",
  ],
};
