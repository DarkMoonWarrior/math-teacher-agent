import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DEFAULT_API_INTERNAL_URL = "http://127.0.0.1:8000";

function progressUrl(progressId: string): string {
  const baseUrl = (process.env.MATH_AI_API_INTERNAL_URL ?? DEFAULT_API_INTERNAL_URL).replace(/\/$/, "");
  return `${baseUrl}/api/v1/agent/question-authoring/progress/${encodeURIComponent(progressId)}`;
}

export async function GET(
  request: Request,
  context: { params: Promise<{ progressId: string }> },
): Promise<Response> {
  const { progressId } = await context.params;
  const headers = new Headers({ Accept: "application/json" });
  for (const name of ["authorization", "cookie", "x-request-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const upstream = await fetch(progressUrl(progressId), {
      method: "GET",
      headers,
      cache: "no-store",
      signal: request.signal,
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "NETWORK_ERROR",
          message: "暂时无法读取命题进度。",
          request_id: "",
        },
      },
      { status: 502 },
    );
  }
}
