/**
 * Teacher Agent 的 Cordis 插件：在最小组合之上注册
 *   1) 5 个只读 teacher tools（model-visible allowlist 的唯一来源）
 *   2) deterministic mock provider route "test-mock"（仅测试）
 *   3) 日志与安全 guard
 *
 * 真实 DeepSeek provider 由官方 @deepseek-ai/dsh-llm-deepseek 插件负责
 * （cordis.teacher.yml 中挂载，无 key 时禁用）。
 * 本插件不接触任何数据库；不使用任何 Harness 非公开 API。
 */
import type { Plugin } from "@deepseek-ai/cordis";
import { MockLlmAdapter, type MockScript } from "./mock-provider.js";
import { defineTeacherTools, TEACHER_TOOL_ALLOWLIST } from "../tools/teacher-tools.js";
import type { ToolGatewayClient } from "../transport/gateway-client.js";
import { createStructuredLogger, type StructuredLogger } from "../observability/logger.js";

export interface TeacherPluginConfig {
  gateway: ToolGatewayClient;
  mockScript: MockScript;
  logger?: StructuredLogger;
  /** 额外禁止注册的 tool 名（安全测试用）；正常运行为空。 */
  bannedToolNames?: readonly string[];
}

export const teacherAgentPlugin: Plugin.Object<TeacherPluginConfig> = {
  name: "teacher-agent",
  inject: ["tools", "llm"],
  apply(ctx, config) {
    const log = config.logger ?? createStructuredLogger();

    for (const tool of defineTeacherTools({ gateway: config.gateway })) {
      if (config.bannedToolNames?.includes(tool.name)) continue;
      ctx.tools.register(tool);
    }

    ctx.llm.registerAdapter(["test-mock"], new MockLlmAdapter(config.mockScript));

    // 兜底安全 guard：任何非 allowlist 的全局工具调用一律拒绝。
    // allowlist 由 allowlist 测试强制校验；该 guard 是纵深防御的第二层。
    ctx.tools.guard((exec) => {
      if (!TEACHER_TOOL_ALLOWLIST.includes(exec.name)) {
        return `tool ${exec.name} 不在 teacher allowlist 中`;
      }
      return undefined;
    });

    log.info({
      event: "agent_tools_registered",
      runtime: "dsh",
      visible_tool_names: TEACHER_TOOL_ALLOWLIST,
    });
  },
};
