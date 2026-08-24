import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 360;

const DEFAULT_API_INTERNAL_URL = "http://127.0.0.1:8000";

function authoringUrl(): string {
  const baseUrl = (process.env.MATH_AI_API_INTERNAL_URL ?? DEFAULT_API_INTERNAL_URL).replace(/\/$/, "");
  return `${baseUrl}/api/v1/agent/question-authoring/draft`;
}

function gatewayError(): NextResponse {
  return NextResponse.json(
    {
      error: {
        code: "NETWORK_ERROR",
        message: "无法连接辅助命题服务。请确认 FastAPI 与 Agent Service 已启动。",
        request_id: "",
      },
    },
    { status: 502 },
  );
}

export async function POST(request: Request): Promise<Response> {
  const headers = new Headers({
    Accept: "application/json",
    "Content-Type": request.headers.get("content-type") ?? "application/json",
  });
  for (const name of ["authorization", "cookie", "x-request-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  let upstream: Response;
  try {
    upstream = await fetch(authoringUrl(), {
      method: "POST",
      headers,
      body: await request.text(),
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return gatewayError();
  }

  const responseHeaders = new Headers({
    "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    "Cache-Control": "no-store",
  });
  const requestId = upstream.headers.get("x-request-id");
  if (requestId) responseHeaders.set("X-Request-ID", requestId);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
