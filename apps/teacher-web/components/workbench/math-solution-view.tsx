import { MathText } from "@/components/math-text";
import type { QuestionDraftOption } from "@/lib/teacher-workspace/contracts";

type MathSolutionViewProps = {
  className?: string;
  finalAnswer: string;
  method: string;
  options?: QuestionDraftOption[];
  question?: string;
  showHeading?: boolean;
  steps: string[];
};

export function MathSolutionView({
  className = "",
  finalAnswer,
  method,
  options = [],
  question,
  showHeading = true,
  steps,
}: MathSolutionViewProps) {
  return (
    <section className={`math-solution-view ${className}`.trim()}>
      {showHeading && (
        <header className="math-solution-view__head">
          <span>{method}</span>
          <h3>结构化解析</h3>
        </header>
      )}
      {question && <div className="solve-question"><MathText text={question} /></div>}
      {options.length > 0 && (
        <ol className="question-options" aria-label="题目选项">
          {options.map((option) => (
            <li className="question-options__item" key={option.key}>
              <span className="question-option-key">{option.key}</span>
              <MathText text={option.text} />
            </li>
          ))}
        </ol>
      )}
      <ol className="solution-steps">
        {steps.map((step, index) => (
          <li key={`${index}-${step}`}>
            <span className="solution-step-number">{String(index + 1).padStart(2, "0")}</span>
            <MathText text={step} />
          </li>
        ))}
      </ol>
      <section className="final-answer">
        <span>最终答案</span>
        <div className="final-answer__math"><MathText text={finalAnswer} /></div>
      </section>
    </section>
  );
}
