import { NextRequest } from "next/server";

const REQUEST_TIMEOUT_MS = Number.parseInt(process.env.BACKEND_PROXY_TIMEOUT_MS ?? "8000", 10) || 8000;

function trimTrailingSlash(value: string): string {
  return value.replace(/\/$/, "");
}

function isAbsoluteHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function resolveBackendBaseUrl(): string | null {
  const candidates = [
    process.env.BACKEND_INTERNAL_URL,
    process.env.SERVICE_URL_BACKEND,
    process.env.BACKEND_URL,
    process.env.NEXT_PUBLIC_BACKEND_URL,
    "http://localhost:8000"
  ];

  for (const raw of candidates) {
    const value = String(raw ?? "").trim();
    if (!value) {
      continue;
    }
    if (!isAbsoluteHttpUrl(value)) {
      continue;
    }
    return trimTrailingSlash(value);
  }

  return null;
}

function buildTargetUrl(request: NextRequest, pathSegments: string[], base: string): URL {
  const path = pathSegments.join("/");
  const target = new URL(`${base}/${path}`);
  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.append(key, value);
  });
  return target;
}

async function proxy(request: NextRequest, pathSegments: string[]): Promise<Response> {
  const base = resolveBackendBaseUrl();
  if (!base) {
    return new Response(JSON.stringify({ detail: "Backend proxy is not configured." }), {
      status: 503,
      headers: { "Content-Type": "application/json" }
    });
  }

  const targetUrl = buildTargetUrl(request, pathSegments, base);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const upstream = await fetch(targetUrl.toString(), {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    const responseHeaders = new Headers(upstream.headers);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders
    });
  } catch (error) {
    clearTimeout(timeoutId);
    const message = error instanceof Error ? error.message : "unknown error";
    return new Response(JSON.stringify({ detail: `Backend proxy error: ${message}`, upstream: base }), {
      status: 502,
      headers: { "Content-Type": "application/json" }
    });
  }
}

type RouteContext = {
  params: {
    path: string[];
  };
};

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context.params.path ?? []);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context.params.path ?? []);
}

export async function PUT(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context.params.path ?? []);
}

export async function PATCH(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context.params.path ?? []);
}

export async function DELETE(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context.params.path ?? []);
}

export async function OPTIONS(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context.params.path ?? []);
}
