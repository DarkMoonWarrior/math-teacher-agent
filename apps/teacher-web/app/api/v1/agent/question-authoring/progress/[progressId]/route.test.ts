import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

describe("question authoring progress proxy", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads one owner-bound progress snapshot without caching", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      progress_id: "qap_1234567890abcdefghij",
      stage: "reviewing",
      elapsed_seconds: 12,
    }), { status: 200, headers: { "content-type": "application/json" } })));

    const response = await GET(
      new Request("http://localhost/api/v1/agent/question-authoring/progress/qap_1234567890abcdefghij", {
        headers: { cookie: "teacher=session" },
      }),
      { params: Promise.resolve({ progressId: "qap_1234567890abcdefghij" }) },
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ stage: "reviewing" });
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/agent/question-authoring/progress/qap_1234567890abcdefghij",
      expect.objectContaining({ method: "GET", cache: "no-store" }),
    );
  });
});
