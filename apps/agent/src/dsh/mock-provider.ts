/**
 * Deterministic mock model provider（仅用于自动化测试）。
 *
 * 不调用任何真实模型 API；根据对话历史中已存在的 assistant 消息数选择
 * 脚本步骤，保证同一会话内每轮输出完全确定。步骤索引按会话内 assistant
 * 消息计数推导，天然支持并发会话互不干扰（只要每个会话顺序推进）。
 *
 * 自动化测试 / CI 绝不使用真实 DeepSeek API（Prompt 2 §28）。
 */
import {
  CallId,
  LlmAdapter,
  type GenerateOptions,
  type LlmModelInfo,
  type LlmProviderInfo,
  type LlmResolvedModelInfo,
  type StreamChunk,
  type ToolCallBlock,
} from "@deepseek-ai/dsh-llm";
import type { ContentBlock } from "@deepseek-ai/dsh-llm";

export type MockStep =
  | { kind: "tool"; toolName: string; arguments: Record<string, unknown> }
  | { kind: "text"; text: string };

export interface MockScript {
  /** 按顺序执行的步骤；超出后返回 finalText。 */
  steps: readonly MockStep[];
  finalText: string;
}

export const DEFAULT_MOCK_SCRIPT: MockScript = {
  steps: [
    {
      kind: "tool",
      toolName: "search_questions",
      arguments: { query: "x+2=5", limit: 5 },
    },
  ],
  finalText: "已根据工具返回的结构化结果完成查询。",
};

function messageText(message: GenerateOptions["messages"][number]): string {
  const content = (message as { content?: unknown }).content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((block) => {
      if (typeof block === "string") return block;
      if (block && typeof block === "object" && "text" in block) {
        const text = (block as { text?: unknown }).text;
        return typeof text === "string" ? text : "";
      }
      return "";
    })
    .join("\n");
}

function currentUserText(messages: GenerateOptions["messages"]): string {
  const currentUserMessage = messages.findLast(
    (message) => message.role === "user" && message.source.kind === "user",
  );
  return currentUserMessage ? messageText(currentUserMessage) : "";
}

function defaultScriptFor(messages: GenerateOptions["messages"]): MockScript {
  const conversation = currentUserText(messages);
  if (conversation.includes("search_private_library")) {
    const query = conversation.match(/检索查询：([^\n]+)/)?.[1]?.trim() || "函数";
    const limit = Number(conversation.match(/返回上限：(\d+)/)?.[1] || "5");
    const consentToken = conversation.match(/检索许可：([^\n]+)/)?.[1]?.trim() || "missing";
    return {
      steps: [{ kind: "tool", toolName: "search_private_library", arguments: { query, limit, consent_token: consentToken } }],
      finalText: "已返回本次授权范围内的私人资料匹配片段。",
    };
  }
  if (!conversation.includes("solve_question")) return DEFAULT_MOCK_SCRIPT;

  const question = conversation.match(/题目：([\s\S]+)$/)?.[1]?.trim() || "解方程 2x-4=0。";
  const solutionMode = conversation.match(/solution_mode：([^\n]+)/)?.[1]?.trim() || "standard";
  const captureGrant = conversation.match(/capture_grant：([^\n]+)/)?.[1]?.trim();
  const arguments_: Record<string, unknown> = { question_text: question, solution_mode: solutionMode };
  if (captureGrant) {
    arguments_.capture_grant = captureGrant;
  }
  return {
    steps: [
      {
        kind: "tool",
        toolName: "solve_question",
        arguments: arguments_,
      },
    ],
    finalText: "已返回受控工具生成的结构化解题结果。",
  };
}

const MOCK_MODEL_ID = "mock-model";

function assistantMessageCount(messages: GenerateOptions["messages"]): number {
  return messages.filter((message) => message.role === "assistant").length;
}

function assistantMessageCountInCurrentTurn(messages: GenerateOptions["messages"]): number {
  const lastUserIndex = messages.findLastIndex(
    (message) => message.role === "user" && message.source.kind === "user",
  );
  return messages
    .slice(lastUserIndex + 1)
    .filter((message) => message.role === "assistant").length;
}

function textChunk(text: string): StreamChunk[] {
  const block: ContentBlock = { type: "text", text };
  return [
    { type: "block-start", index: 0, blockType: "text" },
    { type: "text-delta", index: 0, text },
    { type: "block-end", index: 0, block },
    { type: "usage", usage: { inputTokens: 1, outputTokens: 1 } },
    { type: "finish", reason: { kind: "stop" } },
  ];
}

function toolCallChunk(toolName: string, args: Record<string, unknown>, stepIndex: number): StreamChunk[] {
  const id = CallId(`mock-call-${stepIndex}`);
  const argumentsText = JSON.stringify(args);
  const block: ToolCallBlock = { type: "tool-call", id, name: toolName, arguments: argumentsText };
  return [
    { type: "block-start", index: 0, blockType: "tool-call" },
    { type: "tool-call-delta", index: 0, id, name: toolName, argumentsDelta: argumentsText },
    { type: "block-end", index: 0, block },
    { type: "finish", reason: { kind: "tool-calls" } },
  ];
}

/**
 * 只注册 provider route "test-mock"。
 * stream() 决定：
 *   - assistant 消息数 < steps.length：执行对应脚本步骤（tool call 或文本）。
 *   - 否则：返回 finalText。
 * 始终遵守 options.signal：中止后立即停止产出。
 */
export class MockLlmAdapter extends LlmAdapter {
  constructor(readonly script?: MockScript) {
    super();
  }

  providerInfo(provider: string): LlmProviderInfo {
    return { id: provider, name: "Deterministic mock provider (tests only)" };
  }

  listModels(provider: string): Promise<readonly LlmModelInfo[]> {
    return Promise.resolve([{ id: MOCK_MODEL_ID, name: "mock-model", provider }]);
  }

  resolveModel(provider: string, model: string): Promise<LlmResolvedModelInfo> {
    return Promise.resolve({ id: model, name: model, provider });
  }

  async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const script = this.script ?? defaultScriptFor(options.messages);
    const stepIndex = this.script
      ? assistantMessageCount(options.messages)
      : assistantMessageCountInCurrentTurn(options.messages);
    const step = stepIndex < script.steps.length ? script.steps[stepIndex] : undefined;
    const chunks = step === undefined
      ? textChunk(script.finalText)
      : step.kind === "text"
        ? textChunk(step.text)
        : toolCallChunk(step.toolName, step.arguments, stepIndex);
    for (const chunk of chunks) {
      if (options.signal?.aborted) return;
      yield chunk;
    }
  }
}
