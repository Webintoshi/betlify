import { NextRequest } from "next/server";

const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  "http://localhost:8000";

function buildTargetUrl(request: NextRequest, pathSegments: string[]): URL {
  const base = BACKEND_INTERNAL_URL.replace(/\/$/, "");
  const path = pathSegments.join("/");
  const target = new URL(`${base}/${path}`);
  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.append(key, value);
  });
  return target;
}

async function proxy(request: NextRequest, pathSegments: string[]): Promise<Response> {
  const targetUrl = buildTargetUrl(request, pathSegments);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");

  try {
    const upstream = await fetch(targetUrl.toString(), {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual"
    });

    const responseHeaders = new Headers(upstream.headers);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    return new Response(JSON.stringify({ detail: `Backend proxy error: ${message}` }), {
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
