import type { SolveTaskResult } from "@/lib/teacher-workspace/contracts";
import {
  evidenceSourceLabel,
  mathVerificationLabel,
  solutionConfidenceLabel,
  solutionConfidenceTone,
  verificationScopeLabel,
} from "@/lib/teacher-workspace/labels";
import { CheckIcon, ClockIcon } from "./icons";
import { MathSolutionView } from "./math-solution-view";

type SolvePaperProps = {
  page: number;
  result: SolveTaskResult;
};

function TrustMark({ result }: { result: SolveTaskResult }) {
  const solution = result.solution;
  if (!solution) return null;
  const tone = solutionConfidenceTone(solution.confidence_status);
  return (
    <span className={`trust-label trust-label--${tone}`}>
      {tone === "trusted" ? <CheckIcon /> : <ClockIcon />}
      {solutionConfidenceLabel(solution.confidence_status)}
    </span>
  );
}

export function SolvePaper({ page, result }: SolvePaperProps) {
  const solution = result.solution;
  if (!solution) return null;

  if (page === 1) {
    return (
      <article className="solve-paper solve-paper--teaching">
        <header className="solve-paper__head">
          <div>
            <span className="paper-kicker">课堂使用提示</span>
            <h2>把解法讲清楚，也把易错处留下。</h2>
          </div>
          <span className="paper-count">02 / 03</span>
        </header>

        <div className="teaching-ledger">
          <section>
            <h3>知识点</h3>
            {solution.knowledge_points.length > 0 ? (
              <ul className="paper-tags">
                {solution.knowledge_points.map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : <p>暂未标注知识点。</p>}
          </section>
          <section>
            <h3>常见错误</h3>
            {solution.common_mistakes.length > 0 ? (
              <ol>{solution.common_mistakes.map((item) => <li key={item}>{item}</li>)}</ol>
            ) : <p>暂无额外易错提示。</p>}
          </section>
          <section>
            <h3>教学提示</h3>
            {solution.teaching_notes.length > 0 ? (
              <ol>{solution.teaching_notes.map((item) => <li key={item}>{item}</li>)}</ol>
            ) : <p>暂无额外教学提示。</p>}
          </section>
        </div>
      </article>
    );
  }

  if (page === 2) {
    const verification = solution.math_verification;
    const verified = verification.status === "passed" && verification.capability === "supported";
    return (
      <article className="solve-paper solve-paper--verification">
        <header className="solve-paper__head">
          <div>
            <span className="paper-kicker">可信证据</span>
            <h2>{mathVerificationLabel(verification.status, verification.capability)}</h2>
          </div>
          <span className="paper-count">03 / 03</span>
        </header>

        <div className={`verification-ledger${verified ? " is-verified" : " is-review"}`}>
          <div className="verification-ledger__status">
            {verified ? <CheckIcon /> : <ClockIcon />}
            <div>
              <strong>{verificationScopeLabel(verification.scope)}</strong>
              <span>{evidenceSourceLabel(verification.evidence_source)}</span>
            </div>
          </div>
          <dl>
            <div><dt>验证方法</dt><dd>{verification.method ?? "未提供"}</dd></div>
            <div><dt>独立答案</dt><dd>{verification.computed_answer ?? "未提供"}</dd></div>
            <div><dt>来源答案</dt><dd>{verification.source_answer ?? "未提供"}</dd></div>
            <div><dt>验证版本</dt><dd>{verification.verifier_version ?? "未提供"}</dd></div>
          </dl>
          {verification.details.length > 0 && (
            <ol className="verification-evidence">
              {verification.details.map((detail) => <li key={detail}>{detail}</li>)}
            </ol>
          )}
        </div>
        {solution.visual_context && (
          <section className={`visual-evidence${solution.visual_context.image_used ? " is-used" : ""}`}>
            <header>
              <span>图形输入证据</span>
              <strong>{solution.visual_context.image_used ? "原图参与本次推理" : "本次仅使用确认题面"}</strong>
            </header>
            <dl>
              <div><dt>图片版本</dt><dd>REV {solution.visual_context.media_revision}</dd></div>
              <div><dt>题面版本</dt><dd>OCR REV {solution.visual_context.recognition_revision}</dd></div>
              <div><dt>视觉模型</dt><dd>{solution.visual_context.image_used ? `${solution.visual_context.provider} · ${solution.visual_context.model}` : "未调用"}</dd></div>
            </dl>
            <p>图形理解属于模型生成过程，不是 MathVerifier 的独立数学验证证据。</p>
          </section>
        )}
      </article>
    );
  }

  return (
    <article className="solve-paper solve-paper--solution">
      <header className="solve-paper__head">
        <div>
          <span className="paper-kicker">{solution.explanation.method}</span>
          <h2>结构化解析</h2>
        </div>
        <span className="paper-count">01 / 03</span>
      </header>

      <MathSolutionView
        finalAnswer={solution.explanation.final_answer}
        method={solution.explanation.method}
        question={result.question_text}
        showHeading={false}
        steps={solution.explanation.steps}
      />
      <footer className="solve-paper__foot"><TrustMark result={result} /></footer>
    </article>
  );
}

export function SolveResultBrief({ result }: { result: SolveTaskResult }) {
  const solution = result.solution;
  if (!solution) return null;
  const tone = solutionConfidenceTone(solution.confidence_status);
  return (
    <section className="result-brief solve-result-brief">
      <div className="result-brief__line">
        <span className={`trust-label trust-label--${tone}`}>
          {tone === "trusted" ? <CheckIcon /> : <ClockIcon />}
          {solutionConfidenceLabel(solution.confidence_status)}
        </span>
        <p>{result.duration_ms} ms · {result.tool_call_count} 次受控工具调用</p>
      </div>
      <p>{verificationScopeLabel(solution.math_verification.scope)} · {evidenceSourceLabel(solution.math_verification.evidence_source)}</p>
      {solution.visual_context && (
        <p>{solution.visual_context.image_used ? "原图已参与本次视觉推理" : "已绑定教师确认题面"} · 图片 REV {solution.visual_context.media_revision} / OCR REV {solution.visual_context.recognition_revision}</p>
      )}
      {solution.matched_question_id && (
        <p>
          匹配题库记录 · {solution.matched_question_id}
          {solution.matched_question_revision_count !== null
            ? ` · 修订记录 ${solution.matched_question_revision_count} 次`
            : ""}
        </p>
      )}
      {solution.warnings.map((warning) => <p className="result-warning" key={warning}>{warning}</p>)}
    </section>
  );
}
