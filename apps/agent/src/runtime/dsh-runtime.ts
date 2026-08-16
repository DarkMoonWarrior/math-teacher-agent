/**
 * DeepSeekHarnessRuntime（Node 侧实现）。
 *
 * 职责：管理 teacher_agent_session_id / run_id、驱动 Harness agent、
 * 将 DSH 原始事件映射为产品级 TeacherAgentEvent、cancel/resume/session/health。
 *
 * 边界：
 *   - 不直接访问任何数据库；题目数据只通过 ToolGatewayClient 获取。
 *   - 不向调用方泄漏 DSH 类型或堆栈。
 *   - 默认 provider 未配置真实 key 时，run 快速失败 MODEL_UNAVAILABLE。
 */
import { randomUUID } from "node:crypto";
import type { Context } from "@deepseek-ai/cordis";
import { SessionId } from "@deepseek-ai/dsh-session";
import { createUserMessage } from "@deepseek-ai/dsh-llm";
import type { Agent, AgentHandle } from "@deepseek-ai/dsh-agent";
import { createHarnessContext } from "../dsh/harness.js";
import type { AgentServiceConfig } from "../config/env.js";
import { createStructuredLogger, type StructuredLogger } from "../observability/logger.js";
import type { MockScript } from "../dsh/mock-provider.js";
import {
  type TeacherAgentCapabilities,
  type TeacherAgentError,
  type TeacherAgentEvent,
  type TeacherAgentHealth,
  type TeacherAgentRunRequest,
  type TeacherAgentRunResult,
  type TeacherAgentSession,
  type TeacherAgentToolCall,
  type TeacherAgentErrorCode,
  type TeacherAgentRuntime,
} from "./types.js";
import { TEACHER_TOOL_ALLOWLIST } from "../tools/teacher-tools.js";
import type { ToolGatewayClient } from "../transport/gateway-client.js";

export const RUNTIME_NAME = "dsh";
export const RUNTIME_VERSION = "0.1.0";

type EmitEvent = (type: TeacherAgentEvent["type"], data?: Record<string, unknown>) => void;
type IdentityCallback = (sessionId: string, runId: string, requestId: string) => void;

interface RunState {
  runId: string;
  sessionId: string;
  requestId: string;
  status: TeacherAgentRunResult["status"];
  cancelled: boolean;
  error: TeacherAgentError | null;
  finalText: string;
  toolCalls: TeacherAgentToolCall[];
  pendingCalls: Map<string, { toolName: string; input: Record<string, unknown>; startedAt: number }>;
  startedAt: number;
  finishedAt: number;
  modelStartedAt: number | null;
  modelDurationMs: number;
  resolve: (result: TeacherAgentRunResult) => void;
  promise: Promise<TeacherAgentRunResult>;
}

interface SessionState {
  sessionId: string;
  status: TeacherAgentSession["status"];
  createdAt: number;
  updatedAt: number;
  runIds: string[];
  teacherUserId: string | null;
  tenantId: string | null;
  agent: Agent | null;
  handle: AgentHandle | null;
}

export interface DeepSeekHarnessRuntimeOptions {
  config: AgentServiceConfig;
  gateway: ToolGatewayClient;
  logger?: StructuredLogger;
  mockScript?: MockScript;
  now?: () => number;
}

export class DeepSeekHarnessRuntime implements TeacherAgentRuntime {
  readonly runtimeName = RUNTIME_NAME;
  readonly runtimeVersion = RUNTIME_VERSION;

  private readonly config: AgentServiceConfig;
  private readonly gateway: ToolGatewayClient;
  private readonly logger: StructuredLogger;
  private readonly mockScript: MockScript | undefined;
  private readonly now: () => number;

  private ctxPromise: Promise<Context> | null = null;
  private readonly sessions = new Map<string, SessionState>();
  private readonly runs = new Map<string, RunState>();

  constructor(options: DeepSeekHarnessRuntimeOptions) {
    this.config = options.config;
    this.gateway = options.gateway;
    this.logger = options.logger ?? createStructuredLogger();
    this.mockScript = options.mockScript;
    this.now = options.now ?? (() => Date.now());
  }

  private ensureContext(): Promise<Context> {
    this.ctxPromise ??= createHarnessContext({
      sessionRoot: this.config.sessionRoot,
      plugin: {
        gateway: this.gateway,
        mockScript: this.mockScript ?? {
          steps: [{ kind: "tool", toolName: "search_questions", arguments: { query: "x+2=5", limit: 5 } }],
          finalText: "已根据工具返回的结构化结果完成查询。",
        },
        logger: this.logger,
      },
    }).catch((cause) => {
      this.ctxPromise = null;
      throw cause;
    });
    return this.ctxPromise;
  }

  // ---------------------------------------------------------------------
  // run / stream / cancel / resume
  // ---------------------------------------------------------------------

  async run(request: TeacherAgentRunRequest): Promise<TeacherAgentRunResult> {
    const result = await this.drive(request, null);
    this.logger.info({
      event: "agent_run_finished",
      runtime: this.runtimeName,
      request_id: result.request_id,
      teacher_agent_session_id: result.session_id,
      run_id: result.run_id,
      run_status: result.status,
      error_class: result.error?.code,
    });
    return result;
  }

  async *stream(request: TeacherAgentRunRequest): AsyncIterable<TeacherAgentEvent> {
    let sessionId = request.session_id ?? "";
    let runId = "";
    let requestId = request.request_id ?? "";
    let sequence = 0;
    const queue: TeacherAgentEvent[] = [];
    let notify: (() => void) | null = null;
    const push = (event: TeacherAgentEvent) => {
      queue.push(event);
      const wake = notify;
      notify = null;
      wake?.();
    };
    const emit: EmitEvent = (type, data) => {
      push({
        type,
        run_id: runId,
        session_id: sessionId,
        request_id: requestId,
        data: data ?? {},
        sequence: sequence++,
        created_at: this.now(),
      });
    };
    const onIdentity: IdentityCallback = (sid, rid, reqid) => {
      sessionId = sid;
      runId = rid;
      requestId = reqid;
    };

    let done = false;
    const drivePromise = this.drive(request, emit, undefined, onIdentity).then(
      (result) => {
        done = true;
        notify?.();
        return result;
      },
      (cause) => {
        done = true;
        notify?.();
        throw cause;
      },
    );

    try {
      while (!done || queue.length > 0) {
        if (queue.length === 0) {
          await new Promise<void>((resolve) => {
            notify = resolve;
          });
        }
        while (queue.length > 0) {
          yield queue.shift() as TeacherAgentEvent;
        }
      }
      await drivePromise;
    } finally {
      await drivePromise.catch(() => undefined);
    }
  }

  async cancel(runId: string): Promise<TeacherAgentRunResult> {
    const state = this.runs.get(runId);
    if (!state) {
      const requestId = `req_${randomUUID().replaceAll("-", "")}`;
      return {
        run_id: runId,
        session_id: "",
        request_id: requestId,
        runtime: this.runtimeName,
        status: "failed",
        final_text: "",
        tool_calls: [],
        error: { code: "TOOL_NOT_FOUND", message: "run 不存在或已结束", request_id: requestId },
      };
    }
    if (state.status === "running" || state.status === "pending") {
      state.cancelled = true;
      this.sessions.get(state.sessionId)?.agent?.cancel({ kind: "user" });
    }
    const result = await state.promise;
    this.logger.info({
      event: "agent_run_cancel_requested",
      runtime: this.runtimeName,
      request_id: result.request_id,
      teacher_agent_session_id: result.session_id,
      run_id: runId,
      run_status: result.status,
    });
    return result;
  }

  async resume(sessionId: string, request: TeacherAgentRunRequest): Promise<TeacherAgentRunResult> {
    try {
      const ctx = await this.ensureContext();
      let state = this.sessions.get(sessionId);
      if (!state?.agent) {
        const handle = await ctx.agents.resume({
          resumeSessionId: SessionId(sessionId),
          agentOptions: { provider: this.config.provider, model: this.config.model },
        });
        state = {
          sessionId,
          status: "idle",
          createdAt: this.now(),
          updatedAt: this.now(),
          runIds: [],
          teacherUserId: request.teacher_user_id ?? null,
          tenantId: request.tenant_id ?? null,
          agent: handle.agent,
          handle,
        };
        this.sessions.set(sessionId, state);
      }
      return this.drive(request, null, sessionId);
    } catch (cause) {
      const requestId = request.request_id || `req_${randomUUID().replaceAll("-", "")}`;
      const message = cause instanceof Error ? cause.message.slice(0, 500) : String(cause).slice(0, 500);
      this.logger.error({
        event: "agent_resume_failed",
        runtime: this.runtimeName,
        request_id: requestId,
        teacher_agent_session_id: sessionId,
        error_class: "INTERNAL_ERROR",
        message,
      });
      return {
        run_id: `run_${randomUUID().replaceAll("-", "")}`,
        session_id: sessionId,
        request_id: requestId,
        runtime: this.runtimeName,
        status: "failed",
        final_text: "",
        tool_calls: [],
        error: { code: "INTERNAL_ERROR", message: "会话恢复失败", request_id: requestId },
      };
    }
  }

  // ---------------------------------------------------------------------
  // 会话 / health / capabilities
  // ---------------------------------------------------------------------

  async getSession(sessionId: string): Promise<TeacherAgentSession> {
    const state = this.sessions.get(sessionId);
    if (!state) {
      throw new Error(`session ${sessionId} not found`);
    }
    return {
      session_id: state.sessionId,
      runtime: this.runtimeName,
      status: state.status,
      created_at: state.createdAt,
      updated_at: state.updatedAt,
      run_ids: [...state.runIds],
      teacher_user_id: state.teacherUserId,
      tenant_id: state.tenantId,
    };
  }

  async health(): Promise<TeacherAgentHealth> {
    try {
      const ctx = await this.ensureContext();
      const schemas = ctx.tools.schemas();
      return {
        status: "ok",
        runtime: this.runtimeName,
        initialized: true,
        model_configured: Boolean(this.config.deepseekApiKey),
        tool_registry_ready: schemas.length === TEACHER_TOOL_ALLOWLIST.length,
        visible_tool_count: schemas.length,
        runtime_version: this.runtimeVersion,
        dsh_version: this.config.dshVersion,
      };
    } catch {
      return {
        status: "unavailable",
        runtime: this.runtimeName,
        initialized: false,
        model_configured: false,
        tool_registry_ready: false,
        visible_tool_count: 0,
        runtime_version: this.runtimeVersion,
        dsh_version: this.config.dshVersion,
      };
    }
  }

  async capabilities(): Promise<TeacherAgentCapabilities> {
    const ctx = await this.ensureContext().catch(() => null);
    const schemas = ctx?.tools.schemas() ?? [];
    return {
      run: true,
      stream: true,
      cancel: true,
      resume: ctx?.get("sessionPersistence") !== undefined,
      get_session: true,
      health: true,
      model_configured: Boolean(this.config.deepseekApiKey),
      visible_tool_names: schemas.map((schema) => schema.name).sort(),
      runtime_version: this.runtimeVersion,
    };
  }

  /** 进程退出前调用：释放 Harness context。 */
  async dispose(): Promise<void> {
    if (!this.ctxPromise) return;
    try {
      const ctx = await this.ctxPromise;
      await ctx.fiber.dispose();
    } catch {
      // 释放失败不影响进程退出。
    }
    this.ctxPromise = null;
  }

  // ---------------------------------------------------------------------
  // 内部实现
  // ---------------------------------------------------------------------

  private async drive(
    request: TeacherAgentRunRequest,
    emit: EmitEvent | null,
    forcedSessionId?: string,
    onIdentity?: IdentityCallback,
  ): Promise<TeacherAgentRunResult> {
    const sessionId = forcedSessionId ?? request.session_id ?? `tch_${randomUUID().replaceAll("-", "")}`;
    const runId = `run_${randomUUID().replaceAll("-", "")}`;
    const requestId = request.request_id || `req_${randomUUID().replaceAll("-", "")}`;
    let resolveRun: (result: TeacherAgentRunResult) => void = () => undefined;
    const promise = new Promise<TeacherAgentRunResult>((resolve) => {
      resolveRun = resolve;
    });
    const runState: RunState = {
      runId,
      sessionId,
      requestId,
      status: "pending",
      cancelled: false,
      error: null,
      finalText: "",
      toolCalls: [],
      pendingCalls: new Map(),
      startedAt: this.now(),
      finishedAt: 0,
      modelStartedAt: null,
      modelDurationMs: 0,
      resolve: resolveRun,
      promise,
    };
    this.runs.set(runId, runState);
    onIdentity?.(sessionId, runId, requestId);

    const finish = (result: TeacherAgentRunResult) => {
      runState.resolve(result);
    };

    try {
      // 未配置真实 key 时，非 mock provider 直接快速失败，避免依赖内部报错文案。
      if (this.config.provider !== "test-mock" && !this.config.deepseekApiKey) {
        const error: TeacherAgentError = { code: "MODEL_UNAVAILABLE", message: "未配置 DeepSeek API Key，模型不可用", request_id: requestId };
        const result: TeacherAgentRunResult = {
          run_id: runId, session_id: sessionId, request_id: requestId, runtime: this.runtimeName,
          status: "failed", final_text: "", tool_calls: [], error,
        };
        emit?.("run_failed", { error });
        finish(result);
        this.updateSessionAfterRun(sessionId, runId, "failed");
        return result;
      }

      const ctx = await this.ensureContext();
      const { agent, state } = await this.getOrCreateAgent(ctx, request, sessionId, runId);
      runState.status = "running";
      state.status = "running";
      state.updatedAt = this.now();
      emit?.("run_started");

      const off = this.subscribeSessionEvents(ctx, sessionId, runState, emit);

      try {
        const message = createUserMessage({
          content: [{ type: "text", text: request.user_message }],
          source: { kind: "user" },
        });
        const idlePromise = (async () => {
          if (runState.cancelled) return;
          agent.followup(message);
          runState.modelStartedAt = this.now();
          await agent.whenIdle();
          runState.modelDurationMs = this.now() - (runState.modelStartedAt ?? this.now());
        })();

        const hardTimeout = setTimeout(() => {
          agent.cancel({ kind: "user" });
          runState.error = { code: "TOOL_TIMEOUT", message: "run 超过时间上限", request_id: requestId };
        }, this.config.runHardTimeoutMs);
        hardTimeout.unref?.();

        try {
          await idlePromise;
        } finally {
          clearTimeout(hardTimeout);
        }

        try {
          await ctx.parallel("session/flush", agent.session);
        } catch (cause) {
          this.logger.error({
            event: "session_flush_failed",
            runtime: this.runtimeName,
            request_id: requestId,
            teacher_agent_session_id: sessionId,
            run_id: runId,
            error_class: "INTERNAL_ERROR",
            message: cause instanceof Error ? cause.message.slice(0, 240) : "unknown",
          });
        }
      } finally {
        off();
      }

      runState.finishedAt = this.now();
      // 定局顺序：显式 cancel 请求 > 硬超时 error > 正常完成。
      if (runState.cancelled && !runState.error) {
        const error: TeacherAgentError = { code: "RUN_CANCELLED", message: "run 已被取消", request_id: requestId };
        emit?.("run_cancelled", {});
        const result: TeacherAgentRunResult = {
          run_id: runId, session_id: sessionId, request_id: requestId, runtime: this.runtimeName,
          status: "cancelled", final_text: runState.finalText, tool_calls: runState.toolCalls, error,
        };
        finish(result);
        this.updateSessionAfterRun(sessionId, runId, "cancelled");
        return result;
      }
      if (runState.error) {
        emit?.("run_failed", { error: runState.error });
        const result: TeacherAgentRunResult = {
          run_id: runId, session_id: sessionId, request_id: requestId, runtime: this.runtimeName,
          status: "failed", final_text: runState.finalText, tool_calls: runState.toolCalls, error: runState.error,
        };
        finish(result);
        this.updateSessionAfterRun(sessionId, runId, "failed");
        return result;
      }
      emit?.("run_completed", { final_text: runState.finalText });
      const result: TeacherAgentRunResult = {
        run_id: runId, session_id: sessionId, request_id: requestId, runtime: this.runtimeName,
        status: "completed", final_text: runState.finalText, tool_calls: runState.toolCalls, error: null,
      };
      finish(result);
      this.updateSessionAfterRun(sessionId, runId, "idle");
      return result;
    } catch (cause) {
      const message = cause instanceof Error ? cause.message.slice(0, 500) : String(cause).slice(0, 500);
      const code: TeacherAgentErrorCode = /adapter|provider|model|api.?key|MODEL/i.test(message) ? "MODEL_UNAVAILABLE" : "INTERNAL_ERROR";
      runState.finishedAt = this.now();
      if (runState.cancelled) {
        const error: TeacherAgentError = { code: "RUN_CANCELLED", message: "run 已被取消", request_id: requestId };
        emit?.("run_cancelled", {});
        const result: TeacherAgentRunResult = {
          run_id: runId, session_id: sessionId, request_id: requestId, runtime: this.runtimeName,
          status: "cancelled", final_text: runState.finalText, tool_calls: runState.toolCalls, error,
        };
        finish(result);
        this.updateSessionAfterRun(sessionId, runId, "cancelled");
        return result;
      }
      this.logger.error({
        event: "agent_run_error",
        runtime: this.runtimeName,
        request_id: requestId,
        teacher_agent_session_id: sessionId,
        run_id: runId,
        error_class: code,
        message,
      });
      const error: TeacherAgentError = { code, message: code === "MODEL_UNAVAILABLE" ? "模型不可用" : "Agent 运行失败", request_id: requestId };
      emit?.("run_failed", { error });
      const result: TeacherAgentRunResult = {
        run_id: runId, session_id: sessionId, request_id: requestId, runtime: this.runtimeName,
        status: "failed", final_text: runState.finalText, tool_calls: runState.toolCalls, error,
      };
      finish(result);
      this.updateSessionAfterRun(sessionId, runId, "failed");
      return result;
    }
  }

  private async getOrCreateAgent(
    ctx: Context,
    request: TeacherAgentRunRequest,
    sessionId: string,
    runId: string,
  ): Promise<{ agent: Agent; state: SessionState }> {
    const existing = this.sessions.get(sessionId);
    if (existing?.agent) {
      existing.runIds.push(runId);
      return { agent: existing.agent, state: existing };
    }
    const handle = await ctx.agents.create({
      sessionId: SessionId(sessionId),
      meta: { cwd: this.config.cwd },
      agentOptions: { provider: this.config.provider, model: this.config.model },
    });
    const state: SessionState = {
      sessionId,
      status: "idle",
      createdAt: this.now(),
      updatedAt: this.now(),
      runIds: [runId],
      teacherUserId: request.teacher_user_id ?? null,
      tenantId: request.tenant_id ?? null,
      agent: handle.agent,
      handle,
    };
    this.sessions.set(sessionId, state);
    return { agent: handle.agent, state };
  }

  private subscribeSessionEvents(
    ctx: Context,
    sessionId: string,
    runState: RunState,
    emit: EmitEvent | null,
  ): () => void {
    const onEvent = ctx.on("session/event", (session, event) => {
      if (session.id !== sessionId) return;
      switch (event.type) {
        case "assistant/chunk": {
          const chunk = event.data.chunk;
          if (chunk.type === "text-delta") {
            emit?.("assistant_delta", { delta: chunk.text });
          }
          break;
        }
        case "assistant/message": {
          for (const block of event.data.message.content) {
            if (block.type === "text") {
              runState.finalText += block.text;
            }
          }
          break;
        }
        case "tool/call": {
          let input: Record<string, unknown> = {};
          try {
            input = JSON.parse(event.data.arguments) as Record<string, unknown>;
          } catch {
            input = { raw_arguments: event.data.arguments };
          }
          runState.pendingCalls.set(event.data.callId, { toolName: event.data.name, input, startedAt: event.time });
          emit?.("tool_started", { tool_name: event.data.name, input });
          break;
        }
        case "tool/result": {
          const resultBlock = event.data.message.content[0];
          const callId = resultBlock?.toolCallId;
          if (callId) {
            const pending = runState.pendingCalls.get(callId);
            if (pending) {
              runState.pendingCalls.delete(callId);
              let output: Record<string, unknown> | null = null;
              for (const block of resultBlock.content) {
                if (block.type === "text") {
                  try {
                    output = JSON.parse(block.text) as Record<string, unknown>;
                  } catch {
                    output = { text: block.text };
                  }
                }
              }
              const call: TeacherAgentToolCall = {
                tool_name: pending.toolName,
                status: event.data.error || resultBlock.isError ? "error" : "ok",
                input: pending.input,
                output: event.data.error ? null : output,
                error: event.data.error
                  ? { code: "TOOL_EXECUTION_ERROR", message: `${event.data.error.name}: ${event.data.error.code}`.slice(0, 500), request_id: runState.requestId }
                  : null,
                started_at: pending.startedAt,
                finished_at: event.time,
              };
              runState.toolCalls.push(call);
              emit?.("tool_finished", {
                tool_name: pending.toolName,
                output: output ?? undefined,
                status: call.status,
                error: call.error ?? undefined,
              });
            }
          }
          break;
        }
        case "turn/end": {
          const reason = event.data.reason;
          if (reason.kind === "aborted") {
            runState.cancelled = true;
          } else if (reason.kind === "error") {
            runState.error = { code: "MODEL_UNAVAILABLE", message: "模型请求失败", request_id: runState.requestId };
          }
          break;
        }
        default:
          break;
      }
    });
    return () => {
      onEvent();
    };
  }

  private updateSessionAfterRun(sessionId: string, runId: string, status: TeacherAgentSession["status"]): void {
    const state = this.sessions.get(sessionId);
    if (!state) return;
    state.status = status;
    state.updatedAt = this.now();
    if (!state.runIds.includes(runId)) state.runIds.push(runId);
  }
}


