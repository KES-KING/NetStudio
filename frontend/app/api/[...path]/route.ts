import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = { params: { path: string[] } };

const forwardedRequestHeaders = ["accept", "authorization", "content-type", "x-stocc-user"];
const forwardedResponseHeaders = ["content-type", "location", "retry-after"];

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const apiBaseUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const encodedPath = context.params.path.map(encodeURIComponent).join("/");
  const upstreamUrl = new URL(`/api/${encodedPath}`, apiBaseUrl);
  upstreamUrl.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of forwardedRequestHeaders) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
    });
    const responseHeaders = new Headers();
    for (const name of forwardedResponseHeaders) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return Response.json(
      { detail: { code: "api_unavailable", message: "API servisine ulaşılamıyor" } },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;

