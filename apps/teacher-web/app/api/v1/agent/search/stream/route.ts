import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DEFAULT_API_INTERNAL_URL = "http://127.0.0.1:8000";

function searchStreamUrl(): string {
  const baseUrl = (process.env.MATH_AI_API_INTERNAL_URL ?? DEFAULT_API_INTERNAL_URL).replace(/\/$/, "");
  return `${baseUrl}/api/v1/agent/search/stream`;
}

function gatewayError(message: string): NextResponse {
  return NextResponse.json(
    {
      error: {
        code: "NETWORK_ERROR",
        message,
        request_id: "",
      },
    },
    { status: 502 },
  );
}

export async function POST(request: Request): Promise<Response> {
  const headers = new Headers({
    Accept: "text/event-stream",
    "Content-Type": request.headers.get("content-type") ?? "application/json",
  });
  for (const name of ["authorization", "cookie", "x-request-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  let upstream: Response;
  try {
    upstream = await fetch(searchStreamUrl(), {
      method: "POST",
      headers,
      body: await request.text(),
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return gatewayError("无法连接业务服务。请确认 FastAPI 已启动。");
  }

  const responseHeaders = new Headers();
  responseHeaders.set(
    "Content-Type",
    upstream.headers.get("content-type") ?? "application/octet-stream",
  );
  responseHeaders.set("Cache-Control", "no-cache, no-transform");
  responseHeaders.set("X-Accel-Buffering", "no");

  const requestId = upstream.headers.get("x-request-id");
  if (requestId) responseHeaders.set("X-Request-ID", requestId);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
