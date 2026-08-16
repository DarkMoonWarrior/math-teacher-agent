/**
 * Cancellation E2E（Prompt 2 §26/§42）：
 *   挂起的 Tool HTTP 请求 -> cancel(run_id) -> 请求 aborted -> run 进入 cancelled
 *   -> TeacherAgentRuntime 返回 RUN_CANCELLED，不留下僵尸任务。
 */
import { afterEach, describe, expect, it } from "vitest";
import { waitFor } from "../helpers/gateway-stub.js";
import { createRuntimeHarness, SEARCH_ROUTE, type RuntimeHarness } from "../helpers/runtime-harness.js";

describe("Tool Cancellation E2E", () => {
  let harness: RuntimeHarness;

  afterEach(async () => {
    if (harness) await harness.close();
  });

  it("cancel(run_id) 中止在途工具请求，run 明确进入 cancelled", async () => {
    harness = await createRuntimeHarness({
      // 网关永久挂起，模拟慢业务服务。
      handlers: { [SEARCH_ROUTE]: () => new Promise(() => undefined) },
    });

    const iterator = harness.runtime
      .stream({ user_message: "帮我找题", request_id: "req_cancel_1" })[Symbol.asyncIterator]();

    const first = await iterator.next();
    expect(first.done).toBe(false);
    expect(first.value?.type).toBe("run_started");
    const runId = first.value?.run_id ?? "";
    expect(runId).toMatch(/^run_/);

    // 等待工具请求真正到达网关。
    await waitFor(() => harness.stub.requests.some((r) => r.route === SEARCH_ROUTE));
    expect(harness.stub.abortedRequests).not.toContain(SEARCH_ROUTE);

    const cancelResult = await harness.runtime.cancel(runId);
    expect(cancelResult.run_id).toBe(runId);
    expect(cancelResult.status).toBe("cancelled");
    expect(cancelResult.error?.code).toBe("RUN_CANCELLED");

    // 网关必须观察到 HTTP 请求被中止（不是进程强杀）。
    await waitFor(() => harness.stub.abortedRequests.includes(SEARCH_ROUTE));

    // stream 必须正常结束，且出现 run_cancelled 事件。
    const events: string[] = [];
    while (true) {
      const next = await iterator.next();
      if (next.done) break;
      events.push(next.value?.type ?? "");
    }
    expect(events).toContain("run_cancelled");
    expect(events).not.toContain("run_completed");

    // 无僵尸任务：cancel 之后同一 run 不能再次完成；session 记录 cancelled 状态。
    const session = await harness.runtime.getSession(cancelResult.session_id);
    expect(session.status).toBe("cancelled");
  });

  it("cancel 一个不存在的 run 返回结构化 TOOL_NOT_FOUND", async () => {
    harness = await createRuntimeHarness({});
    const result = await harness.runtime.cancel("run_does_not_exist");
    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("TOOL_NOT_FOUND");
  });
});
