import { NextRequest } from "next/server";

function buildFallbackResponse(pathSegments: string[]): Response | null {
  const path = pathSegments.join("/").toLowerCase();

  if (path === "history") {
    return new Response(
      JSON.stringify({
        count: 0,
        items: [],
        summary: {
          total_predictions: 0,
          correct_predictions: 0,
          wrong_predictions: 0,
          accuracy_percentage: 0,
          weekly_accuracy_percentage: 0,
          total_coupons: 0
        },
        filters: {
          start_date: null,
          end_date: null,
          market_type: null,
          correct: null
        },
        backend_available: false
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json", "x-backend-fallback": "history" }
      }
    );
  }

  if (path === "health") {
    return new Response(
      JSON.stringify({
        status: "degraded",
        supabase_connected: false,
        scheduler: { running: false, jobs: [] },
        api_football_remaining: null,
        the_odds_remaining: null,
        api_keys: {
          api_football: false,
          the_odds: false,
          openweather: false,
          supabase_service: false
        },
        error: "Backend unavailable",
        time: new Date().toISOString(),
        backend_available: false
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json", "x-backend-fallback": "health" }
      }
    );
  }

  if (path === "matches/today") {
    return new Response(
      JSON.stringify({
        count: 0,
        tracked_leagues: 0,
        matches: [],
        backend_available: false
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json", "x-backend-fallback": "matches_today" }
      }
    );
  }

  return null;
}

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

function resolveBackendBaseUrls(): string[] {
  const candidates = [
    process.env.SERVICE_URL_BACKEND,
    process.env.BACKEND_URL,
    process.env.NEXT_PUBLIC_BACKEND_URL,
    process.env.BACKEND_INTERNAL_URL,
    "http://localhost:8000"
  ];

  const resolved = candidates
    .map((raw) => String(raw ?? "").trim())
    .filter((value) => value.length > 0)
    .filter((value) => isAbsoluteHttpUrl(value))
    .map((value) => trimTrailingSlash(value));

  return Array.from(new Set(resolved));
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
  const bases = resolveBackendBaseUrls();
  if (!bases.length) {
    return new Response(JSON.stringify({ detail: "Backend proxy is not configured." }), {
      status: 503,
      headers: { "Content-Type": "application/json" }
    });
  }

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");

  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  const errors: string[] = [];

  for (const base of bases) {
    const targetUrl = buildTargetUrl(request, pathSegments, base);

    try {
      const upstream = await fetch(targetUrl.toString(), {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "manual"
      });

      if (upstream.status >= 500) {
        errors.push(`${base} => HTTP ${upstream.status}`);
        continue;
      }

      const responseHeaders = new Headers(upstream.headers);
      responseHeaders.set("x-backend-upstream", base);
      return new Response(upstream.body, {
        status: upstream.status,
        headers: responseHeaders
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      errors.push(`${base} => ${message}`);
    }
  }

  if (request.method === "GET") {
    const fallback = buildFallbackResponse(pathSegments);
    if (fallback) {
      return fallback;
    }
  }

  return new Response(JSON.stringify({ detail: "Backend proxy error: all upstream targets failed", tried: bases, errors }), {
    status: 502,
    headers: { "Content-Type": "application/json" }
  });
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
