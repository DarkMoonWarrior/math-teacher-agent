/**
 * 最小结构化日志：一行 JSON 输出到 stdout。
 *
 * 隐私红线（Prompt 2 §30）：
 *   - 绝不记录 API key / service token / Authorization。
 *   - 绝不记录教师搜索 query 全文、题目 stem / solution 全文、私人资料正文。
 *   - 只记录 id / duration / status / error_class 等最小字段。
 */

export interface AgentLogFields {
  event: string;
  request_id?: string;
  teacher_agent_session_id?: string;
  run_id?: string;
  runtime?: string;
  tool_name?: string;
  tool_duration_ms?: number;
  tool_status?: string;
  model_duration_ms?: number;
  run_status?: string;
  error_class?: string;
  [key: string]: unknown;
}

/** 字段名黑名单：即使误传也绝不输出。 */
const FORBIDDEN_KEYS = new Set([
  "authorization",
  "token",
  "api_key",
  "apikey",
  "secret",
  "password",
  "credential",
  "query",
  "user_message",
  "stem",
  "solution",
  "answer",
  "content",
]);

function sanitizeValue(value: unknown, depth: number): unknown {
  if (depth > 3) return "[truncated]";
  if (value === null || typeof value !== "object") {
    if (typeof value === "string" && value.length > 240) return `${value.slice(0, 240)}…`;
    return value;
  }
  if (Array.isArray(value)) return value.slice(0, 8).map((item) => sanitizeValue(item, depth + 1));
  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, "_");
    if (FORBIDDEN_KEYS.has(normalized)) continue;
    out[key] = sanitizeValue(item, depth + 1);
  }
  return out;
}

export interface StructuredLogger {
  info(fields: AgentLogFields): void;
  error(fields: AgentLogFields & { error_class: string; message: string }): void;
  child?(scope: Record<string, string>): StructuredLogger;
}

export function createStructuredLogger(
  sink: (line: string) => void = (line) => process.stdout.write(`${line}\n`),
): StructuredLogger {
  const write = (fields: AgentLogFields) => {
    try {
      sink(JSON.stringify(sanitizeValue({ time: new Date().toISOString(), ...fields }, 0)));
    } catch {
      // 日志绝不能因为序列化失败影响业务。
    }
  };
  return {
    info: (fields) => write(fields),
    error: (fields) => write({ level: "error", ...fields }),
  };
}

export const logger = createStructuredLogger();
