import { AccountAccessGate } from "@/components/workbench/account-access-gate";
import { TeacherWorkbench } from "@/components/workbench/teacher-workbench";

export default function HomePage() {
  return <AccountAccessGate><TeacherWorkbench /></AccountAccessGate>;
}
