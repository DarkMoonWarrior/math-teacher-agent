/**
 * DeepSeek Harness 启动层：boot 官方最小组合 + 程序化挂载 teacher plugin。
 *
 * 边界约定：
 *   - 本目录（src/dsh/）是本仓库唯一允许 import DeepSeek Harness 类型的地方。
 *   - 只使用官方公开 API：boot / Cordis plugin / ctx.tools / ctx.llm / ctx.agents。
 *   - 不修改、不复制、不 vendor Harness core；不依赖非公开内部 API。
 *   - session root 等运行时配置通过官方 patch 机制覆盖静态 YAML 默认值。
 */
import { fileURLToPath } from "node:url";
import path from "node:path";
import { boot } from "@deepseek-ai/dsh-app-boot";
import type { Context } from "@deepseek-ai/cordis";
import { teacherAgentPlugin, type TeacherPluginConfig } from "./teacher-plugin.js";

const COMPOSITION_PATH = fileURLToPath(new URL("../../config/cordis.teacher.yml", import.meta.url));

export interface HarnessContextOptions {
  /** session 持久化绝对根目录（gitignored）。 */
  sessionRoot: string;
  /** 插件配置（gateway / mock script / logger）。 */
  plugin: TeacherPluginConfig;
}

export async function createHarnessContext(options: HarnessContextOptions): Promise<Context> {
  const ctx = await boot("math-teacher-agent", path.resolve(COMPOSITION_PATH), [
    {
      id: "session-persistence-jsonl",
      config: {
        root: options.sessionRoot,
        compression: "none",
      },
    },
  ]);
  try {
    await ctx.plugin(teacherAgentPlugin, options.plugin);
    return ctx;
  } catch (cause) {
    await ctx.fiber.dispose();
    throw new Error(`math-teacher-agent: teacher plugin failed to load: ${cause instanceof Error ? cause.message : String(cause)}`, { cause });
  }
}
