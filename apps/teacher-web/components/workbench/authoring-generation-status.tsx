export type AuthoringGenerationStage = "brief" | "agent" | "staging";

const STAGES: Array<{ key: AuthoringGenerationStage; label: string }> = [
  { key: "brief", label: "整理命题要求" },
  { key: "agent", label: "命制题面与解析" },
  { key: "staging", label: "建立私有草稿" },
];

const CURRENT_STAGE_COPY: Record<AuthoringGenerationStage, string> = {
  brief: "正在整理命题要求",
  agent: "Agent 正在命制完整题面与解析",
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
      <p>长题会先锁定完整题面与选项，再生成解析；不会因等待时间较长而截短题目。</p>
    </section>
  );
}
