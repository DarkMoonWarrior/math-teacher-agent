import { MathText } from "../math-text";
import type {
  QuestionAuthoringProgressStage,
  QuestionAuthoringStatementPreview,
} from "../../lib/teacher-workspace/contracts";

type PreviewMode = "active" | "preserved";

export function AuthoringLivePreview({
  mode,
  revision,
  stage,
  statement,
  statementState,
  onDiscard,
}: {
  mode: PreviewMode;
  revision: number;
  stage: QuestionAuthoringProgressStage;
  statement: QuestionAuthoringStatementPreview | null;
  statementState: "pending" | "approved" | "adjusting";
  onDiscard?: () => void;
}) {
  if (!statement) {
    return (
      <section className="authoring-live-preview is-pending" aria-live="polite">
        <span className="authoring-live-preview__spinner" aria-hidden="true" />
        <p>题面生成中</p>
        <h2>通过独立审核后，题面会立即出现在这里。</h2>
        <span>左侧继续显示全部命题阶段和已处理时间。</span>
      </section>
    );
  }

  const adjusting = mode === "active" && statementState === "adjusting";
  const statusTitle = mode === "preserved"
    ? "已停止生成解析 · 题面已保留"
    : adjusting
      ? "题面正在调整"
      : "题面已通过审核 · 解析生成中";

  return (
    <section className="authoring-live-preview has-statement" aria-label="命题实时结果">
      <header>
        <div>
          <span>{mode === "preserved" ? "PAUSED STATEMENT" : "LIVE AUTHORING"}</span>
          <h2>{statusTitle}</h2>
        </div>
        <strong>题面 REV {Math.max(1, revision)}</strong>
      </header>
      <div className="authoring-live-preview__statement">
        <MathText text={statement.stem_latex || statement.stem_plain} />
      </div>
      {statement.options.length > 0 && (
        <ol className="authoring-live-preview__options">
          {statement.options.map((option) => (
            <li key={option.key}>
              <b>{option.key}</b>
              <MathText text={option.text} />
            </li>
          ))}
        </ol>
      )}
      <aside data-state={adjusting ? "adjusting" : mode}>
        {mode === "active" && !adjusting && <span className="authoring-live-preview__spinner" aria-hidden="true" />}
        <div>
          <strong>{statusTitle}</strong>
          <p>
            {mode === "preserved"
              ? "当前只保留审核通过的题面，没有标准答案和解析（均显示为“无”）；你可以将它保存到私有题库，稍后再补充解析。"
              : adjusting
                ? "完整求解发现题面仍需完善；新题面重新审核通过后会自动替换当前版本。"
                : stage === "regenerating_solution"
                  ? "题面保持不变，Agent 正在重新生成并审核解析。"
                  : "Agent 正在后台生成解析，完成后会在本区域自动补全标准答案与解析。"}
          </p>
        </div>
        {mode === "preserved" && onDiscard && (
          <button type="button" onClick={onDiscard}>不再保留题面</button>
        )}
      </aside>
    </section>
  );
}
