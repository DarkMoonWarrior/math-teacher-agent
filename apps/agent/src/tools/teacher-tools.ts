/**
 * Teacher Tools 的最小只读 allowlist。
 *
 * 每个 tool：
 *   - 输入 typed（DSH defineTool 自动校验 model 生成的参数）。
 *   - 输出 canonical 结构化 JSON（字段直接可解析，绝不要求模型做 NLP）。
 *   - 只通过 ToolGatewayClient 调用 FastAPI 内部网关，绝不访问数据库。
 *   - 转发 exec.signal 到 HTTP 请求（Agent cancel 能中止在途请求）。
 *   - 基础设施错误 throw；业务结果（含网关结构化错误）以结构化 JSON 返回。
 */
import { defineTool, type ToolDefinition, type ToolRunContext, type JsonValue } from "@deepseek-ai/dsh-tools";
import {
  ToolGatewayClient,
  ToolGatewayError,
  type CreateQuestionDraftInput,
  type GatewayRequestOptions,
  type SolutionMode,
} from "../transport/gateway-client.js";
import type { TeacherAgentError } from "../runtime/types.js";


export interface TeacherToolOptions {
  gateway: ToolGatewayClient;
}

const JSON_OUTPUT = (text: string) => [{ type: "text" as const, text }];

function gatewayErrorEnvelope(requestId: string, cause: unknown): { code: string; message: string } {
  if (cause instanceof ToolGatewayError) {
    return { code: cause.error.code, message: cause.error.message };
  }
  return { code: "TOOL_EXECUTION_ERROR", message: "工具执行失败" };
}

function callOptions(exec: ToolRunContext): GatewayRequestOptions {
  return { signal: exec.signal, requestId: `req_${String(exec.callId).replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 96)}` };
}

export function defineTeacherTools(options: TeacherToolOptions): ToolDefinition[] {
  const { gateway } = options;

  const searchQuestions = defineTool({
    name: "search_questions",
    description:
      "在教师题库中按关键词/章节/难度/知识点检索题目。只返回可见且来源合法的题目摘要；限制条数，结果过大时截断。",
    parameters: {
      query: { type: "string", description: "检索关键词（题干关键词或知识点名称）", required: true },
      chapter: { type: "string", description: "章节名称（可选）" },
      difficulty: { type: "integer", description: "难度 1-5（可选）" },
      knowledge_point_id: { type: "string", description: "知识点 ID（可选）" },
      limit: { type: "integer", description: "返回条数，默认 10，最大 20" },
    },
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          items: { type: "array", required: true },
          total: { type: "integer", required: true },
          truncated: { type: "boolean", required: true },
          query_interpretation: { type: "json" },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 30_000,
    async execute(args, exec) {
      const requestId = callOptions(exec).requestId;
      const result = await gateway.searchQuestions(
        { ...args, chapter: args.chapter ?? null, difficulty: args.difficulty ?? null, knowledge_point_id: args.knowledge_point_id ?? null },
        callOptions(exec),
      );
      if (result.ok) {
        return {
          ok: true,
          items: result.data.items.map((item) => ({ ...item })),
          total: result.data.total,
          truncated: result.data.truncated,
          query_interpretation: (result.data.query_interpretation ?? null) as unknown as JsonValue,
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        items: [],
        total: 0,
        truncated: false,
        query_interpretation: null,
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  const getQuestion = defineTool({
    name: "get_question",
    description:
      "按 question_id 读取单道题目的完整内容（题干/答案/解析/验证与来源状态）。只返回经过现有业务门禁允许的内容。",
    parameters: {
      question_id: { type: "string", description: "题目 ID", required: true },
    },
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          question_id: { type: "string", required: true },
          stem: { type: "string", required: true },
          question_type: { type: "string", required: true },
          answer: { type: "json" },
          solution_steps: { type: "array", required: true },
          verification_status: { type: "string", required: true },
          visibility: { type: "string", required: true },
          source_status: { type: "string", required: true },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 30_000,
    async execute(args, exec) {
      const requestId = callOptions(exec).requestId;
      const result = await gateway.getQuestion(args.question_id, callOptions(exec));
      if (result.ok) {
        return {
          ok: true,
          question_id: result.data.question_id,
          stem: result.data.stem,
          question_type: result.data.question_type,
          answer: result.data.answer ?? null,
          solution_steps: result.data.solution_steps ?? [],
          verification_status: result.data.verification_status,
          visibility: result.data.visibility,
          source_status: result.data.source_status,
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        question_id: args.question_id,
        stem: "",
        question_type: "",
        answer: null,
        solution_steps: [],
        verification_status: "unknown",
        visibility: "unknown",
        source_status: "unknown",
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  const solveQuestion = defineTool({
    name: "solve_question",
    description:
      "调用 FastAPI 的可信解题模块。优先返回题库已验证解析；模型新解答始终标记 teacher_review_required，不会自动发布或冒充已验证。",
    parameters: {
      question_text: { type: "string", description: "完整高中数学题目文本", required: true },
      solution_mode: { type: "string", description: "standard 或 alternative" },
      teacher_instruction: { type: "string", description: "教师对讲解方式的补充要求（可选）" },
      capture_grant: { type: "string", description: "FastAPI 为本次确认题面和图片签发的一次性许可；必须原样传递，其他可信字段由服务端解析" },
    },
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          question_text: { type: "string", required: true },
          solution_mode: { type: "string", required: true },
          explanation: { type: "json", required: true },
          knowledge_points: { type: "array", required: true },
          common_mistakes: { type: "array", required: true },
          teaching_notes: { type: "array", required: true },
          confidence_status: { type: "string", required: true },
          math_verification: { type: "json", required: true },
          verification_evidence: { type: "array", required: true },
          provider: { type: "string", required: true },
          model: { type: "string", required: true },
          mode: { type: "string", required: true },
          matched_question_id: { type: "json" },
          matched_question_revision_count: { type: "json" },
          match_score: { type: "json" },
          alternative_available: { type: "boolean", required: true },
          warnings: { type: "array", required: true },
          visual_context: { type: "json" },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 120_000,
    async execute(args, exec) {
      const requestId = callOptions(exec).requestId;
      const result = await gateway.solveQuestion(
        {
          question_text: args.question_text,
          solution_mode: (args.solution_mode ?? "standard") as SolutionMode,
          teacher_instruction: args.teacher_instruction ?? "",
          capture_grant: args.capture_grant,
        },
        { ...callOptions(exec), timeoutMs: 120_000 },
      );
      if (result.ok) {
        return {
          ok: true,
          question_text: result.data.question_text,
          solution_mode: result.data.solution_mode,
          explanation: result.data.explanation as unknown as JsonValue,
          knowledge_points: result.data.knowledge_points,
          common_mistakes: result.data.common_mistakes,
          teaching_notes: result.data.teaching_notes,
          confidence_status: result.data.confidence_status,
          math_verification: result.data.math_verification as unknown as JsonValue,
          verification_evidence: result.data.verification_evidence,
          provider: result.data.provider,
          model: result.data.model,
          mode: result.data.mode,
          matched_question_id: result.data.matched_question_id,
          matched_question_revision_count: result.data.matched_question_revision_count,
          match_score: result.data.match_score,
          alternative_available: result.data.alternative_available,
          warnings: result.data.warnings,
          visual_context: (result.data.visual_context ?? null) as unknown as JsonValue,
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        question_text: args.question_text,
        solution_mode: args.solution_mode ?? "standard",
        explanation: null,
        knowledge_points: [],
        common_mistakes: [],
        teaching_notes: [],
        confidence_status: "teacher_review_required",
        math_verification: {
          status: result.error.code === "VERIFICATION_FAILED" ? "failed" : "inconclusive",
          capability: result.error.code.startsWith("VERIFICATION_") ? "supported" : "unsupported",
          scope: result.error.code.startsWith("VERIFICATION_") ? "matched_question_record" : "generated_solution",
          evidence_source: result.error.code.startsWith("VERIFICATION_") ? "stored_status" : "none",
          method: null,
          computed_answer: null,
          source_answer: null,
          details: [result.error.message],
          verifier_version: null,
        },
        verification_evidence: [],
        provider: "",
        model: "",
        mode: "live_ai",
        matched_question_id: null,
        matched_question_revision_count: null,
        match_score: null,
        alternative_available: false,
        warnings: [],
        visual_context: null,
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  const findSimilarQuestions = defineTool({
    name: "find_similar_questions",
    description: "根据 question_id 检索相似题/变式候选，返回关系类型与置信度。只读取已有相似度计算结果。",
    parameters: {
      question_id: { type: "string", description: "基准题目 ID", required: true },
      limit: { type: "integer", description: "返回条数，默认 10，最大 20" },
    },
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          items: { type: "array", required: true },
          total: { type: "integer", required: true },
          truncated: { type: "boolean", required: true },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 30_000,
    async execute(args, exec) {
      const requestId = callOptions(exec).requestId;
      const result = await gateway.findSimilarQuestions({ question_id: args.question_id, limit: args.limit }, callOptions(exec));
      if (result.ok) {
        return {
          ok: true,
          items: result.data.items.map((item) => ({ ...item })),
          total: result.data.total,
          truncated: result.data.truncated,
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        items: [],
        total: 0,
        truncated: false,
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  const verifyQuestion = defineTool({
    name: "verify_question",
    description: "调用 MathVerifier 对题目做数学正确性验证，返回存档验证状态与独立计算结果。绝不生成未经验证的结论。",
    parameters: {
      question_id: { type: "string", description: "待验证题目 ID", required: true },
    },
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          question_id: { type: "string", required: true },
          stored_status: { type: "string", required: true },
          capability: { type: "string", required: true },
          computed_answer: { type: "json" },
          method: { type: "json" },
          details: { type: "array", required: true },
          fresh_verification: { type: "json" },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 30_000,
    async execute(args, exec) {
      const requestId = callOptions(exec).requestId;
      const result = await gateway.verifyQuestion(args.question_id, callOptions(exec));
      if (result.ok) {
        return {
          ok: true,
          question_id: result.data.question_id,
          stored_status: result.data.stored_status,
          capability: result.data.capability,
          computed_answer: result.data.computed_answer ?? null,
          method: result.data.method ?? null,
          details: result.data.details ?? [],
          fresh_verification: (result.data.fresh_verification ?? null) as unknown as JsonValue,
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        question_id: args.question_id,
        stored_status: "unknown",
        capability: "unknown",
        computed_answer: null,
        method: null,
        details: [],
        fresh_verification: null,
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  const getCurriculumNode = defineTool({
    name: "get_curriculum_node",
    description: "按 node_id 读取教材知识图谱节点（教材/章/知识点结构）。仅返回课程目录中的结构化信息。",
    parameters: {
      node_id: { type: "string", description: "课程节点 ID", required: true },
    },
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          node_id: { type: "string", required: true },
          parent_id: { type: "json" },
          volume: { type: "string", required: true },
          node_type: { type: "string", required: true },
          code: { type: "string", required: true },
          name: { type: "string", required: true },
          description: { type: "string", required: true },
          knowledge_points: { type: "array", required: true },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 30_000,
    async execute(args, exec) {
      const requestId = callOptions(exec).requestId;
      const result = await gateway.getCurriculumNode(args.node_id, callOptions(exec));
      if (result.ok) {
        return {
          ok: true,
          node_id: result.data.node_id,
          parent_id: result.data.parent_id ?? null,
          volume: result.data.volume,
          node_type: result.data.node_type,
          code: result.data.code,
          name: result.data.name,
          description: result.data.description,
          knowledge_points: result.data.knowledge_points ?? [],
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        node_id: args.node_id,
        parent_id: null,
        volume: "",
        node_type: "",
        code: "",
        name: "",
        description: "",
        knowledge_points: [],
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  const inspectPrivateLibrary = defineTool({
    name: "inspect_private_library",
    description:
      "读取当前教师私人资料库的聚合状态。只返回数量、处理状态和文件类型统计，不返回标题、文件名、正文、路径或 owner 标识。",
    parameters: {},
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          total: { type: "integer", required: true },
          pending_review: { type: "integer", required: true },
          confirmed: { type: "integer", required: true },
          needs_ocr: { type: "integer", required: true },
          trashed: { type: "integer", required: true },
          by_file_kind: { type: "json", required: true },
          visibility: { type: "string", required: true },
          content_included: { type: "boolean", required: true },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 30_000,
    async execute(_args, exec) {
      const requestId = callOptions(exec).requestId;
      const result = await gateway.inspectPrivateLibrary(callOptions(exec));
      if (result.ok) {
        return {
          ok: true,
          total: result.data.total,
          pending_review: result.data.pending_review,
          confirmed: result.data.confirmed,
          needs_ocr: result.data.needs_ocr,
          trashed: result.data.trashed,
          by_file_kind: result.data.by_file_kind as unknown as JsonValue,
          visibility: "private",
          content_included: false,
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        total: 0,
        pending_review: 0,
        confirmed: 0,
        needs_ocr: 0,
        trashed: 0,
        by_file_kind: {},
        visibility: "private",
        content_included: false,
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  const searchPrivateLibrary = defineTool({
    name: "search_private_library",
    description:
      "仅凭 FastAPI 为当前教师本次操作签发的一次性许可，检索已确认的私人资料；只返回有界匹配片段及来源版本/权利状态，不返回原文件、路径或完整正文。",
    parameters: {
      query: { type: "string", description: "与许可严格绑定的检索词", required: true },
      consent_token: { type: "string", description: "FastAPI 签发的一次性检索许可", required: true },
      limit: { type: "integer", description: "返回资料数，最大 8", required: true },
    },
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          query: { type: "string", required: true },
          items: { type: "array", required: true },
          total: { type: "integer", required: true },
          truncated: { type: "boolean", required: true },
          content_scope: { type: "string", required: true },
          visibility: { type: "string", required: true },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 30_000,
    async execute(args, exec) {
      const requestId = callOptions(exec).requestId;
      const result = await gateway.searchPrivateLibrary(
        { query: args.query, consent_token: args.consent_token, limit: args.limit },
        callOptions(exec),
      );
      if (result.ok) {
        return {
          ok: true,
          query: result.data.query,
          items: result.data.items.map((item) => ({ ...item })),
          total: result.data.total,
          truncated: result.data.truncated,
          content_scope: "matching_excerpts",
          visibility: "private",
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        query: args.query,
        items: [],
        total: 0,
        truncated: false,
        content_scope: "matching_excerpts",
        visibility: "private",
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  const createQuestionDraft = defineTool({
    name: "create_question_draft",
    description:
      "根据教师原始命题要求生成一份未保存、仅自己可见并附分级可信检查的结构化题目草稿。MathVerifier 不支持时必须明确披露；该工具不能保存、发布、共享或删除题目。",
    parameters: {
      request_text: { type: "string", description: "教师原始命题要求，必须原样传递", required: true },
      grade: { type: "string", description: "高一、高二或高三（可选）" },
      curriculum_node_id: { type: "string", description: "教师明确选择的知识点节点 ID（可选）" },
      knowledge_point_query: { type: "string", description: "知识点名称或查询（可选）" },
      question_type: { type: "string", description: "single_choice、multiple_choice、fill_blank 或 open_response（可选）" },
      target_difficulty: { type: "integer", description: "目标难度 1-5" },
      teaching_purpose: { type: "string", description: "课堂用途" },
      expected_minutes: { type: "integer", description: "预计用时（分钟，可选）" },
      assessed_method: { type: "string", description: "考查方法（可选）" },
      misconception_requirements: { type: "string", description: "易错点或干扰项要求（可选）" },
      additional_constraints: { type: "string", description: "教师补充限制（可选）" },
      reference_question_id: { type: "string", description: "参考母题 ID；当前可信检查未开放时会 fail closed" },
    },
    output: {
      schema: {
        type: "object",
        properties: {
          ok: { type: "boolean", required: true },
          draft: { type: "json" },
          request_id: { type: "string", required: true },
          error: { type: "json" },
        },
        additionalProperties: false,
      },
      render: (_args, value) => JSON_OUTPUT(JSON.stringify(value)),
    },
    timeoutMs: 120_000,
    async execute(args, exec) {
      const requestId = callOptions(exec).requestId;
      const input: CreateQuestionDraftInput = {
        ...args,
        grade: args.grade as CreateQuestionDraftInput["grade"],
        question_type: args.question_type as CreateQuestionDraftInput["question_type"],
      };
      const result = await gateway.createQuestionDraft(
        input,
        { ...callOptions(exec), timeoutMs: 120_000 },
      );
      if (result.ok) {
        return {
          ok: true,
          draft: result.data.draft as unknown as JsonValue,
          request_id: result.data.request_id ?? requestId,
          error: null,
        };
      }
      return {
        ok: false,
        draft: null,
        request_id: result.error.request_id ?? requestId,
        error: gatewayErrorEnvelope(requestId, new ToolGatewayError(result.error)),
      };
    },
  });

  return [
    searchQuestions,
    getQuestion,
    solveQuestion,
    findSimilarQuestions,
    verifyQuestion,
    getCurriculumNode,
    inspectPrivateLibrary,
    searchPrivateLibrary,
    createQuestionDraft,
  ];
}

/** Prompt 2 强制 allowlist：model-visible 工具名必须恰好等于该集合。 */
export const TEACHER_TOOL_ALLOWLIST: readonly string[] = [
  "search_questions",
  "get_question",
  "solve_question",
  "find_similar_questions",
  "verify_question",
  "get_curriculum_node",
  "inspect_private_library",
  "search_private_library",
  "create_question_draft",
];

export type { TeacherAgentError };
