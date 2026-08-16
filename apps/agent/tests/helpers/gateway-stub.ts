/**
 * 测试用 Internal Tool Gateway stub：实现与 FastAPI 网关相同的 HTTP 契约
 * （路由 / internal/agent-tools/v1/*、Bearer token、X-Request-Id、错误信封）。
 * 只用于验证 Agent Service 的 transport / tools / cancel 行为。
 */
import { createServer, type IncomingMessage, type ServerResponse, type Server } from "node:http";

export interface StubRequestContext {
  req: IncomingMessage;
  res: ServerResponse;
  body: Record<string, unknown>;
  requestId: string;
  authorization: string;
}

export interface StubResponse {
  status?: number;
  body?: unknown;
}

export type StubHandler = (context: StubRequestContext) => StubResponse | Promise<StubResponse>;

export interface GatewayStubOptions {
  handlers?: Partial<Record<string, StubHandler>>;
}

export interface GatewayStub {
  handlers: Partial<Record<string, StubHandler>>;
  url: string;
  requests: Array<{ route: string; body: Record<string, unknown>; authorization: string; requestId: string }>;
  abortedRequests: string[];
  server: Server;
  close: () => Promise<void>;
}

export function createGatewayStub(options: GatewayStubOptions = {}): Promise<GatewayStub> {
  const requests: GatewayStub["requests"] = [];
  const abortedRequests: string[] = [];
  const handlers = options.handlers ?? {};

  const defaultHandler: StubHandler = () => ({
    status: 200,
    body: { items: [], total: 0, truncated: false, request_id: "req_stub_default" },
  });

  const server = createServer((req, res) => {
    const route = (req.url ?? "/").split("?")[0] ?? "/";
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      let body: Record<string, unknown> = {};
      try {
        const text = Buffer.concat(chunks).toString("utf8");
        body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
      } catch {
        // 测试 stub 保持宽容。
      }
      const requestId = String(req.headers["x-request-id"] ?? "");
      const authorization = String(req.headers.authorization ?? "");
      requests.push({ route, body, authorization, requestId });
      const context: StubRequestContext = { req, res, body, requestId, authorization };
      const handler = handlers[route] ?? defaultHandler;
      Promise.resolve()
        .then(() => handler(context))
        .then((response) => {
          if (res.writableEnded || res.destroyed) return;
          const status = response?.status ?? 200;
          const payload = response?.body;
          res.statusCode = status;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(payload === undefined ? undefined : JSON.stringify(payload));
        })
        .catch(() => {
          if (!res.writableEnded && !res.destroyed) {
            res.statusCode = 500;
            res.end(JSON.stringify({ code: "TOOL_EXECUTION_ERROR", message: "stub failure", request_id: "req_stub" }));
          }
        });
    });
    req.on("aborted", () => {
      abortedRequests.push(route);
    });
    res.on("close", () => {
      if (!res.writableEnded) abortedRequests.push(route);
    });
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      resolve({
        handlers,
        url: `http://127.0.0.1:${port}`,
        requests,
        abortedRequests,
        server,
        close: () => new Promise<void>((done) => server.close(() => done())),
      });
    });
  });
}

export async function waitFor(condition: () => boolean, timeoutMs = 15_000, label = "condition"): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error(`waitFor timeout: ${label}`);
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

export function gatewayJson(status: number, payload: unknown): StubResponse {
  return { status, body: payload };
}

