import { BetaAccessGate } from "@/components/workbench/beta-access-gate";
import { TeacherWorkbench } from "@/components/workbench/teacher-workbench";

export default function HomePage() {
  return <BetaAccessGate><TeacherWorkbench /></BetaAccessGate>;
}
