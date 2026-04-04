import { NextRequest } from "next/server";

const REQUEST_TIMEOUT_MS = 5000;
const RETRYABLE_GATEWAY_STATUSES = new Set([502, 503, 504]);

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

function resolveBackendCandidates(): string[] {
  const candidates = [
    process.env.SERVICE_URL_BACKEND,
    process.env.BACKEND_INTERNAL_URL,
    process.env.BACKEND_URL,
    process.env.NEXT_PUBLIC_BACKEND_URL,
    "http://backend:8000",
    "http://backend",
    "http://api:8000",
    "http://api",
    "http://127.0.0.1:8000",
    "http://localhost:8000"
  ];

  return Array.from(
    new Set(
      candidates
        .map((value) => String(value ?? "").trim())
        .filter((value) => value.length > 0)
        .filter((value) => isAbsoluteHttpUrl(value))
        .map((value) => trimTrailingSlash(value))
    )
  );
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
  const bases = resolveBackendCandidates();
  const errors: string[] = [];
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");

  const body =
    request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();

  for (const base of bases) {
    const targetUrl = buildTargetUrl(request, pathSegments, base);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const upstream = await fetch(targetUrl.toString(), {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "manual",
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (RETRYABLE_GATEWAY_STATUSES.has(upstream.status)) {
        const responseText = await upstream.text();
        const compact = responseText.length > 180 ? `${responseText.slice(0, 180)}...` : responseText;
        errors.push(`${base} => upstream ${upstream.status}${compact ? `: ${compact}` : ""}`);
        continue;
      }

      const responseHeaders = new Headers(upstream.headers);
      responseHeaders.set("x-backend-target", base);
      return new Response(upstream.body, {
        status: upstream.status,
        headers: responseHeaders
      });
    } catch (error) {
      clearTimeout(timeoutId);
      const message = error instanceof Error ? error.message : "unknown error";
      errors.push(`${base} => ${message}`);
    }
  }

  return new Response(
    JSON.stringify({
      detail: "Backend proxy error: all upstream targets failed",
      tried: bases,
      errors
    }),
    {
      status: 502,
      headers: { "Content-Type": "application/json" }
    }
  );
}

export const dynamic = "force-dynamic";

type RouteContext = {
  params: {
    path: string[];
  }
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
