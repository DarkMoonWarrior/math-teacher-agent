/**
 * Prompt 2 强制安全门禁：
 *  1. model-visible tools 必须恰好等于 6 个受控只读 teacher tools（自动测试，不只靠文档）。
 *  2. 组合（cordis.teacher.yml）不得包含 bash / filesystem / web / subagent / workflow 等能力。
 *  3. apps/agent 源码不得直接访问任何数据库（sqlite3 / SQL / postgres / ORM 等）。
 */
import { afterEach, describe, expect, it } from "vitest";
import { mkdtempSync, readFileSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHarnessContext } from "../../src/dsh/harness.js";
import { TEACHER_TOOL_ALLOWLIST } from "../../src/tools/teacher-tools.js";
import { ToolGatewayClient } from "../../src/transport/gateway-client.js";
import { makeTestConfig } from "../helpers/test-env.js";
import type { Context } from "@deepseek-ai/cordis";

async function bootContext(): Promise<Context> {
  const config = makeTestConfig();
  const gateway = new ToolGatewayClient({
    origin: config.apiInternalUrl,
    token: config.toolGatewayToken,
    timeoutMs: 5000,
  });
  return createHarnessContext({
    sessionRoot: config.sessionRoot,
    plugin: {
      gateway,
      mockScript: {
        steps: [{ kind: "tool", toolName: "search_questions", arguments: { query: "x+2=5", limit: 5 } }],
        finalText: "完成。",
      },
    },
  });
}

function listFiles(root: string): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = path.join(dir, entry);
      const stat = statSync(full);
      if (stat.isDirectory()) {
        if (entry === "node_modules" || entry === "dist") continue;
        walk(full);
      } else {
        out.push(full);
      }
    }
  };
  walk(root);
  return out;
}

describe("Teacher Agent least-capability 安全门禁", () => {
  let ctx: Context | null = null;

  afterEach(async () => {
    if (ctx) {
      await ctx.fiber.dispose();
      ctx = null;
    }
  });

  it("model-visible tools 恰好等于 6 个受控只读 teacher tools", async () => {
    ctx = await bootContext();
    const names = ctx.tools.schemas().map((schema) => schema.name).sort();
    expect(names).toEqual([...TEACHER_TOOL_ALLOWLIST].sort());
  });

  it("配置真实 DeepSeek key 时 composition 能装载官方 provider", async () => {
    const previous = process.env.MATH_AI_DEEPSEEK_API_KEY;
    process.env.MATH_AI_DEEPSEEK_API_KEY = "sk-test-composition-only";
    try {
      ctx = await bootContext();
      expect(ctx.tools.schemas()).toHaveLength(TEACHER_TOOL_ALLOWLIST.length);
    } finally {
      if (previous === undefined) {
        delete process.env.MATH_AI_DEEPSEEK_API_KEY;
      } else {
        process.env.MATH_AI_DEEPSEEK_API_KEY = previous;
      }
    }
  });

  it("不存在 bash/fs/web/subagent/workflow/terminal 等任何额外能力", async () => {
    ctx = await bootContext();
    const names = ctx.tools.schemas().map((schema) => schema.name);
    const banned = [
      "bash",
      "shell",
      "powershell",
      "cmd",
      "exec",
      "run_command",
      "filesystem",
      "fs",
      "read_file",
      "write_file",
      "edit_file",
      "web_search",
      "web_fetch",
      "web",
      "browser",
      "subagent",
      "workflow",
      "terminal",
      "mcp",
      "code_execution",
    ];
    for (const name of banned) {
      expect(names).not.toContain(name);
    }
  });

  it("composition YAML 不挂载 dsh-base，且不包含危险能力条目", async () => {
    const yamlPath = fileURLToPath(new URL("../../config/cordis.teacher.yml", import.meta.url));
    const yaml = readFileSync(yamlPath, "utf8");
    // 只检查实际生效条目（去掉文档注释），注释中允许解释为什么不使用 dsh-base。
    const effective = yaml
      .split("\n")
      .filter((line) => !line.trimStart().startsWith("#"))
      .join("\n");
    expect(effective).not.toContain("dsh-base");
    for (const forbidden of ["bash", "filesystem", "subagent", "web-search", "web_search", "workflow", "terminal", "shell"]) {
      expect(effective).not.toContain(forbidden);
    }
  });

  it("apps/agent 源码不包含任何数据库直接访问（sqlite3 / SQL / postgres / ORM）", () => {
    const srcRoot = fileURLToPath(new URL("../../src", import.meta.url));
    const configRoot = fileURLToPath(new URL("../../config", import.meta.url));
    const files = [...listFiles(srcRoot), ...listFiles(configRoot)];
    expect(files.length).toBeGreaterThan(0);

    const forbidden = [
      { pattern: /from\s+["']node:sqlite["']/, label: "node:sqlite" },
      { pattern: /require\(["']sqlite3["']\)|from\s+["']sqlite3["']/, label: "sqlite3 package" },
      { pattern: /sqlalchemy|create_engine/i, label: "SQLAlchemy" },
      { pattern: /\bpostgres(ql)?\b/i, label: "postgres" },
      { pattern: /\bsequelize\b|\btypeorm\b|\bprisma\b|\bknex\b/i, label: "ORM" },
      { pattern: /createPool\(|createConnection\(/, label: "connection pool" },
      { pattern: /["'][^"']*\.(db|sqlite|sqlite3)["']/, label: "database file path" },
    ];

    for (const file of files) {
      const content = readFileSync(file, "utf8");
      for (const { pattern, label } of forbidden) {
        expect(pattern.test(content), `${file} 包含禁止的数据库访问：${label}`).toBe(false);
      }
    }
  });

  it("Tool allowlist 常量与注册顺序无关，是唯一可见工具来源", () => {
    expect(new Set(TEACHER_TOOL_ALLOWLIST).size).toBe(6);
    for (const name of TEACHER_TOOL_ALLOWLIST) {
      expect(name).toMatch(/^[a-z_]+$/);
    }
  });
});
