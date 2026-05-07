import { NextResponse, type NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const requestHeaders = new Headers(request.headers);
  const currentPath = `${request.nextUrl.pathname}${request.nextUrl.search}`;

  requestHeaders.set("x-cchis-current-path", currentPath);

  return NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
}

export const config = {
  matcher: [
    "/overview/:path*",
    "/wards/:path*",
    "/alerts/:path*",
    "/preparedness-actions/:path*",
    "/chvs/:path*",
    "/facility-readiness/:path*",
    "/operational-metrics/:path*",
    "/source-data/:path*",
    "/message-governance/:path*",
    "/model-health/:path*",
    "/interoperability/:path*",
    "/system/:path*",
    "/profile/:path*",
  ],
};
