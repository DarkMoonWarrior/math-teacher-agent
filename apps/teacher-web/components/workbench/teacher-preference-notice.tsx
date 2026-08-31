import type { TeacherPlanningPreference } from "@/lib/teacher-workspace/contracts";


function displayValue(value: TeacherPlanningPreference["value"]): string {
  return Array.isArray(value) ? value.join("、") : String(value);
}


export function TeacherPreferenceNotice({ preferences }: { preferences: TeacherPlanningPreference[] }) {
  if (preferences.length === 0) return null;

  return (
    <section className="teacher-preference-notice" aria-label="已应用教师偏好">
      <header>
        <div><strong>已应用教师偏好</strong><span>仅补全未明确的字段</span></div>
        <p>本次直接修改字段即可覆盖，不会改变已保存偏好。</p>
      </header>
      <ul>
        {preferences.map((preference) => (
          <li key={preference.key}>
            <span>{preference.label}</span>
            <b>{displayValue(preference.value)}</b>
            <small>{preference.source.label} · 置信度 {Math.round(preference.source.confidence * 100)}%</small>
          </li>
        ))}
      </ul>
    </section>
  );
}
