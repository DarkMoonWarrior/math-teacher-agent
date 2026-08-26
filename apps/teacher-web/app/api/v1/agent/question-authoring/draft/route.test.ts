import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";


describe("question authoring proxy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("preserves a structured model failure instead of collapsing it to HTTP 500", async () => {
    const upstream = {
      status: "error",
      draft: null,
      request_id: "req_authoring_timeout_safe",
      error: {
        code: "MODEL_UNAVAILABLE",
        message: "模型返回内容不完整，请重试。",
        request_id: "req_authoring_timeout_safe",
      },
    };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(upstream), {
      status: 200,
      headers: { "content-type": "application/json" },
    })));

    const request = new Request("http://localhost/api/v1/agent/question-authoring/draft", {
      method: "POST",
      headers: { "content-type": "application/json", "x-request-id": "req_browser" },
      body: JSON.stringify({ brief: { request_text: "给我出一道圆锥曲线压轴题" } }),
    });
    const response = await POST(request);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(upstream);
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/agent/question-authoring/draft",
      expect.objectContaining({ method: "POST", cache: "no-store" }),
    );
  });
});
