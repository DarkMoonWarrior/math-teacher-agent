/**
 * Agent Service HTTP 入口（node:http，无任何 Web 框架）。
 *
 * 仅服务 machine-to-machine 请求：
 *   FastAPI DeepSeekHarnessRuntime -> 本服务（Authorization: Bearer <MATH_AI_AGENT_SERVICE_TOKEN>）
 *   本服务 -> FastAPI Internal Tool Gateway（Authorization: Bearer <MATH_AI_TOOL_GATEWAY_TOKEN>）
 *
 * 路由：
 *   POST /v1/run              JSON 结果
 *   POST /v1/stream           SSE TeacherAgentEvent
 *   POST /v1/cancel           取消 run
 *   POST /v1/resume           恢复持久化会话
 *   GET  /v1/sessions/:id     会话状态
 *   GET  /health              健康检查
 *   GET  /capabilities        能力报告
 *
 * 所有端点都要求 service token；未配置 token 时 fail closed。
 */
import { createServer, type IncomingMessage, type ServerResponse, type Server } from "node:http";
import { pathToFileURL } from "node:url";
import { randomUUID } from "node:crypto";
import { loadAgentServiceConfig } from "./config/env.js";
import { ToolGatewayClient } from "./transport/gateway-client.js";
import { DeepSeekHarnessRuntime, type DeepSeekHarnessRuntimeOptions } from "./runtime/dsh-runtime.js";
import { createStructuredLogger, type StructuredLogger } from "./observability/logger.js";
import type { TeacherAgentError, TeacherAgentEvent, TeacherAgentRunRequest } from "./runtime/types.js";

export interface AgentServiceOptions {
  env?: NodeJS.ProcessEnv;
  runtime?: DeepSeekHarnessRuntime;
  logger?: StructuredLogger;
  runtimeOptions?: Partial<DeepSeekHarnessRuntimeOptions>;
}

export interface AgentService {
  server: Server;
  runtime: DeepSeekHarnessRuntime;
  url: string;
  close: () => Promise<void>;
}

const MAX_BODY_BYTES = 1_000_000;

function sendError(
  res: ServerResponse,
  status: number,
  code: string,
  message: string,
  requestId: string,
): void {
  if (res.headersSent) {
    res.destroy();
    return;
  }
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify({ error: { code, message, request_id: requestId } }));
}

function sendJson(res: ServerResponse, status: number, payload: unknown): void {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

function requestIdOf(req: IncomingMessage): string {
  const raw = req.headers["x-request-id"];
  const value = Array.isArray(raw) ? raw[0] : raw;
  return (value ?? "").trim().slice(0, 160) || `req_${randomUUID().replaceAll("-", "")}`;
}

function readBody(req: IncomingMessage, maxBytes: number): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > maxBytes) {
        const error = new Error("body too large");
        (error as Error & { code?: string }).code = "BODY_TOO_LARGE";
        reject(error);
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      const text = Buffer.concat(chunks).toString("utf8");
      if (!text.trim()) {
        resolve({});
        return;
      }
      try {
        const parsed = JSON.parse(text) as unknown;
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          reject(new Error("body must be a JSON object"));
          return;
        }
        resolve(parsed as Record<string, unknown>);
      } catch (cause) {
        reject(new Error("invalid JSON body"));
      }
    });
    req.on("error", reject);
  });
}

export function createAgentService(options: AgentServiceOptions = {}): AgentService {
  const log = options.logger ?? createStructuredLogger();
  const config = loadAgentServiceConfig(options.env ?? process.env);
  const gateway = new ToolGatewayClient({
    origin: config.apiInternalUrl,
    token: config.toolGatewayToken,
    timeoutMs: config.toolTimeoutMs,
  });
  const runtime = options.runtime ?? new DeepSeekHarnessRuntime({
    config,
    gateway,
    logger: log,
    ...options.runtimeOptions,
  });

  const validateRunRequest = (body: Record<string, unknown>): { ok: true; request: TeacherAgentRunRequest } | { ok: false; message: string } => {
    const userMessage = body.user_message;
    if (typeof userMessage !== "string" || userMessage.trim().length === 0 || userMessage.length > 8000) {
      return { ok: false, message: "user_message 必须为 1-8000 字符的字符串" };
    }
    const sessionId = body.session_id;
    if (sessionId !== undefined && sessionId !== null && (typeof sessionId !== "string" || sessionId.length > 160)) {
      return { ok: false, message: "session_id 格式无效" };
    }
    const requestId = body.request_id;
    if (requestId !== undefined && requestId !== null && (typeof requestId !== "string" || requestId.length > 160)) {
      return { ok: false, message: "request_id 格式无效" };
    }
    const teacherUserId = body.teacher_user_id;
    const tenantId = body.tenant_id;
    return {
      ok: true,
      request: {
        user_message: userMessage,
        session_id: (sessionId as string | null | undefined) ?? null,
        request_id: (requestId as string | undefined) ?? "",
        teacher_user_id: typeof teacherUserId === "string" ? teacherUserId : null,
        tenant_id: typeof tenantId === "string" ? tenantId : null,
      },
    };
  };

  const server = createServer(async (req, res) => {
    const requestId = requestIdOf(req);
    const route = `${req.method ?? "GET"} ${(req.url ?? "/").split("?")[0]}`;

    try {
      // ---- 认证：所有端点 fail closed ----
      const expected = config.agentServiceToken;
      if (!expected) {
        log.error({ event: "agent_service_token_not_configured", request_id: requestId, error_class: "TOOL_UNAUTHORIZED", message: "missing MATH_AI_AGENT_SERVICE_TOKEN" });
        sendError(res, 401, "TOOL_UNAUTHORIZED", "Agent Service 未配置 service token", requestId);
        return;
      }
      const authorization = req.headers.authorization;
      if (!authorization || !authorization.startsWith("Bearer ")) {
        sendError(res, 401, "TOOL_UNAUTHORIZED", "缺少 service token", requestId);
        return;
      }
      const provided = authorization.slice("Bearer ".length).trim();
      let providedValid = false;
      if (provided.length > 0) {
        const a = Buffer.from(provided);
        const b = Buffer.from(expected);
        providedValid = a.length === b.length && a.every((byte, index) => byte === (b[index] ?? 0));
      }
      if (!providedValid) {
        sendError(res, 401, "TOOL_UNAUTHORIZED", "service token 不正确", requestId);
        return;
      }

      if (route === "GET /health") {
        sendJson(res, 200, await runtime.health());
        return;
      }
      if (route === "GET /capabilities") {
        sendJson(res, 200, await runtime.capabilities());
        return;
      }
      if (route === "POST /v1/run" || route === "POST /v1/resume") {
        const body = await readBody(req, MAX_BODY_BYTES);
        const parsed = validateRunRequest(body);
        if (!parsed.ok) {
          sendError(res, 400, "TOOL_VALIDATION_ERROR", parsed.message, requestId);
          return;
        }
        parsed.request.request_id = parsed.request.request_id || requestId;
        const sessionId = typeof body.session_id === "string" && body.session_id ? body.session_id : null;
        const result = route === "POST /v1/resume"
          ? await runtime.resume(sessionId ?? "", parsed.request)
          : await runtime.run(parsed.request);
        sendJson(res, 200, result);
        return;
      }
      if (route === "POST /v1/cancel") {
        const body = await readBody(req, MAX_BODY_BYTES);
        const runId = body.run_id;
        if (typeof runId !== "string" || runId.length === 0 || runId.length > 160) {
          sendError(res, 400, "TOOL_VALIDATION_ERROR", "run_id 格式无效", requestId);
          return;
        }
        sendJson(res, 200, await runtime.cancel(runId));
        return;
      }
      if (route === "POST /v1/stream") {
        const body = await readBody(req, MAX_BODY_BYTES);
        const parsed = validateRunRequest(body);
        if (!parsed.ok) {
          sendError(res, 400, "TOOL_VALIDATION_ERROR", parsed.message, requestId);
          return;
        }
        parsed.request.request_id = parsed.request.request_id || requestId;
        res.statusCode = 200;
        res.setHeader("content-type", "text/event-stream; charset=utf-8");
        res.setHeader("cache-control", "no-cache");
        res.setHeader("connection", "keep-alive");
        res.flushHeaders?.();
        let cancelled = false;
        let currentRunId = "";
        const onClose = () => {
          if (!cancelled && currentRunId) {
            void runtime.cancel(currentRunId);
          }
        };
        req.on("close", onClose);
        try {
          for await (const event of runtime.stream(parsed.request)) {
            if (event.run_id) currentRunId = event.run_id;
            res.write(`data: ${JSON.stringify(event)}\n\n`);
          }
          res.end();
        } catch (cause) {
          const error: TeacherAgentError = {
            code: "INTERNAL_ERROR",
            message: "stream 处理失败",
            request_id: requestId,
          };
          const failedEvent: TeacherAgentEvent = {
            type: "run_failed",
            run_id: currentRunId,
            session_id: parsed.request.session_id ?? "",
            request_id: requestId,
            data: { error },
            sequence: 0,
            created_at: Date.now(),
          };
          res.write(`data: ${JSON.stringify(failedEvent)}\n\n`);
          res.end();
        } finally {
          req.off("close", onClose);
        }
        return;
      }
      if (route.startsWith("GET /v1/sessions/")) {
        const sessionId = decodeURIComponent(route.slice("GET /v1/sessions/".length));
        try {
          sendJson(res, 200, await runtime.getSession(sessionId));
        } catch {
          sendError(res, 404, "TOOL_NOT_FOUND", "会话不存在", requestId);
        }
        return;
      }
      sendError(res, 404, "TOOL_NOT_FOUND", "路由不存在", requestId);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      log.error({ event: "agent_service_request_failed", request_id: requestId, error_class: "INTERNAL_ERROR", message: message.slice(0, 240) });
      sendError(res, 500, "INTERNAL_ERROR", "内部错误", requestId);
    }
  });

  return {
    server,
    runtime,
    url: "",
    close: async () => {
      await new Promise<void>((resolve) => server.close(() => resolve()));
      await runtime.dispose();
    },
  };
}

/** 监听 Agent Service；port=0 时使用随机端口并返回实际地址。 */
export async function listenAgentService(
  service: AgentService,
  host: string = "127.0.0.1",
  port = 0,
): Promise<string> {
  await new Promise<void>((resolve, reject) => {
    service.server.once("error", reject);
    service.server.listen(port, host, () => resolve());
  });
  const address = service.server.address();
  const boundPort = typeof address === "object" && address ? address.port : port;
  const url = `http://${host}:${boundPort}`;
  (service as { url: string }).url = url;
  return url;
}

// ---- 直接运行入口（pnpm --filter @math-teacher-agent/agent dev） ----
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const config = loadAgentServiceConfig(process.env);
  const service = createAgentService();
  const listen = async () => {
    const port = config.port;
    const host = config.host;
    await new Promise<void>((resolve, reject) => {
      service.server.once("error", reject);
      service.server.listen(port, host, () => resolve());
    });
    const address = service.server.address();
    const boundPort = typeof address === "object" && address ? address.port : port;
    process.stdout.write(`AGENT_SERVICE_LISTENING ${JSON.stringify({ host, port: boundPort })}\n`);
  };
  const shutdown = async () => {
    await service.close();
    process.exit(0);
  };
  process.on("SIGINT", () => void shutdown());
  process.on("SIGTERM", () => void shutdown());
  listen().catch((cause) => {
    process.stderr.write(`agent service failed to start: ${cause instanceof Error ? cause.message : String(cause)}\n`);
    process.exit(1);
  });
}

