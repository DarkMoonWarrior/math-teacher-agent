import type { QuestionAuthoringProgressStage } from "../../lib/teacher-workspace/contracts";

export type AuthoringGenerationStage = QuestionAuthoringProgressStage;

const STAGES: Array<{ key: AuthoringGenerationStage; label: string }> = [
  { key: "brief", label: "整理命题要求" },
  { key: "composing", label: "命制题面" },
  { key: "reviewing", label: "审核题面" },
  { key: "refining", label: "完善题面（按需）" },
  { key: "solving", label: "生成解析" },
  { key: "staging", label: "建立私有草稿" },
];

const CURRENT_STAGE_COPY: Record<AuthoringGenerationStage, string> = {
  brief: "正在整理命题要求",
  composing: "Agent 正在命制完整题面",
  reviewing: "Agent 正在审核题面是否合理",
  refining: "审核发现问题，Agent 正在完善题面并重新审核",
  solving: "题面已通过审核，正在生成解析并据此确定标准答案",
  staging: "题面已生成，正在建立私有草稿",
};

export function formatAuthoringElapsed(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function AuthoringGenerationStatus({
  elapsedSeconds,
  stage,
}: {
  elapsedSeconds: number;
  stage: AuthoringGenerationStage;
}) {
  const activeIndex = STAGES.findIndex((item) => item.key === stage);
  return (
    <section className="authoring-progress" role="status" aria-live="polite" aria-atomic="true">
      <div className="authoring-progress__current">
        <span className="authoring-progress__spinner" aria-hidden="true" />
        <div>
          <strong>{CURRENT_STAGE_COPY[stage]}</strong>
          <span>已处理 {formatAuthoringElapsed(elapsedSeconds)} · 请保持本页打开</span>
        </div>
      </div>
      <ol aria-label="生成步骤">
        {STAGES.map((item, index) => (
          <li data-state={index < activeIndex ? "complete" : index === activeIndex ? "current" : "pending"} key={item.key}>
            <span>{index + 1}</span>{item.label}
          </li>
        ))}
      </ol>
    </section>
  );
}
