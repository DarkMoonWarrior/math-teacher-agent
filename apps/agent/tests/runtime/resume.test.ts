/**
 * Resume 验证（Prompt 2 §27）：
 *   优先使用 DSH 官方公开 API（ctx.agents.resume + JSONL session persistence）。
 *   新 runtime 实例使用同一 sessionRoot 时必须能恢复持久化会话继续运行。
 */
import { afterEach, describe, expect, it } from "vitest";
import { createGatewayStub } from "../helpers/gateway-stub.js";
import { ToolGatewayClient } from "../../src/transport/gateway-client.js";
import { DeepSeekHarnessRuntime } from "../../src/runtime/dsh-runtime.js";
import { makeTestConfig } from "../helpers/test-env.js";
import { createRuntimeHarness, searchResponse, SEARCH_ROUTE, type RuntimeHarness } from "../helpers/runtime-harness.js";

describe("Resume via DSH official session persistence", () => {
  let harness: RuntimeHarness;

  afterEach(async () => {
    if (harness) await harness.close();
  });

  it("同一 sessionRoot 的新 runtime 实例可以 resume 持久化会话", async () => {
    harness = await createRuntimeHarness({
      handlers: { [SEARCH_ROUTE]: () => searchResponse() },
    });

    const first = await harness.runtime.run({
      user_message: "第一轮：找题",
      session_id: "tch_resume_1",
      request_id: "req_resume_1",
    });
    expect(first.status).toBe("completed");
    expect(first.tool_calls.map((c) => c.tool_name)).toEqual(["search_questions"]);

    const sessionRoot = harness.config.sessionRoot;
    await harness.close();

    // 用同一 sessionRoot 建立全新的 runtime（模拟 Agent Service 重启）。
    const stub2 = await createGatewayStub({
      handlers: { [SEARCH_ROUTE]: () => searchResponse() },
    });
    const config2 = makeTestConfig();
    config2.sessionRoot = sessionRoot;
    const runtime2 = new DeepSeekHarnessRuntime({
      config: config2,
      gateway: new ToolGatewayClient({ origin: stub2.url, token: config2.toolGatewayToken, timeoutMs: 10_000 }),
    });
    try {
      const resumed = await runtime2.resume("tch_resume_1", {
        user_message: "第二轮：继续",
        request_id: "req_resume_2",
      });
      expect(resumed.status).toBe("completed");
      expect(resumed.session_id).toBe("tch_resume_1");
      expect(resumed.error).toBeNull();

      // 恢复后会话状态可查询。run_ids 是进程内记录（新进程只包含本次恢复 run；
      // 历史 run 由 DSH session persistence 保存，Prompt 2 不要求跨进程聚合）。
      const session = await runtime2.getSession("tch_resume_1");
      expect(session.status).toBe("idle");
      expect(session.run_ids.length).toBeGreaterThanOrEqual(1);
    } finally {
      await runtime2.dispose();
      await stub2.close();
    }
  });

  it("resume 不存在的会话返回 INTERNAL_ERROR 而不是崩溃", async () => {
    harness = await createRuntimeHarness({});
    const result = await harness.runtime.resume("tch_never_existed", {
      user_message: "hi",
      request_id: "req_resume_3",
    });
    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("INTERNAL_ERROR");
  });
});
