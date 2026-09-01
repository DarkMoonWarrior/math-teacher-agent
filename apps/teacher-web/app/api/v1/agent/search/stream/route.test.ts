import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Search stream route", () => {
  it("forwards the upstream event stream without changing its payload", async () => {
    vi.stubEnv("MATH_AI_API_INTERNAL_URL", "http://api.internal/");
    const upstreamFetch = vi.fn(async () => new Response(
      'data: {"type":"run_started"}\n\n',
      {
        status: 200,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "X-Request-ID": "req_stream",
        },
      },
    ));
    vi.stubGlobal("fetch", upstreamFetch);
    const request = new Request("http://teacher.local/api/v1/agent/search/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Cookie: "math_beta_session=opaque" },
      body: JSON.stringify({ query: "找椭圆题", session_id: "tch_1" }),
    });

    const response = await POST(request);

    expect(upstreamFetch).toHaveBeenCalledWith(
      "http://api.internal/api/v1/agent/search/stream",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ query: "找椭圆题", session_id: "tch_1" }),
        cache: "no-store",
        signal: request.signal,
      }),
    );
    expect(response.status).toBe(200);
    const upstreamCall = upstreamFetch.mock.calls[0] as unknown as [string, RequestInit];
    const upstreamHeaders = upstreamCall[1].headers as Headers;
    expect(upstreamHeaders.get("cookie")).toBe("math_beta_session=opaque");
    expect(response.headers.get("content-type")).toBe("text/event-stream; charset=utf-8");
    expect(response.headers.get("cache-control")).toBe("no-cache, no-transform");
    expect(response.headers.get("x-accel-buffering")).toBe("no");
    expect(response.headers.get("x-request-id")).toBe("req_stream");
    await expect(response.text()).resolves.toBe('data: {"type":"run_started"}\n\n');
  });

  it("returns a stable product error when FastAPI cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("connection refused");
    }));
    const request = new Request("http://teacher.local/api/v1/agent/search/stream", {
      method: "POST",
      body: JSON.stringify({ query: "找题", session_id: "tch_2" }),
    });

    const response = await POST(request);

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      error: {
        code: "NETWORK_ERROR",
        message: "无法连接业务服务。请确认 FastAPI 已启动。",
        request_id: "",
      },
    });
  });
});
