import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PrivateLibraryWorkspace } from "./private-library-workspace";
import {
  AccountSettingsPopover,
  getWorkspaceVisibility,
  TeacherWorkbench,
} from "./teacher-workbench";
import { BetaCapabilityBoundary } from "./beta-access-gate";
import { BetaValidationPanel } from "./beta-validation-panel";

describe("core workspace split layouts", () => {
  it("keeps the authoring workspace mutually exclusive from the library workspace", () => {
    expect(getWorkspaceVisibility("library", true)).toEqual({
      authoring: true,
      lesson: false,
      library: false,
      paper: false,
      searchSolve: false,
    });
  });

  it("renders Search and Solve through the shared resizable task-and-result shell", () => {
    const html = renderToStaticMarkup(<TeacherWorkbench />);

    expect(html).toContain('class="resizable-split-pane search-solve-split"');
    expect(html).toContain('aria-label="调整搜题要求与结果区域宽度"');
    expect(html).toContain('role="separator"');
    expect(html).toContain('data-pane="primary"');
    expect(html).toContain('data-pane="secondary"');
    expect(html).toContain('data-workspace-view="search-solve"');
    expect(html).toContain('data-workspace-view="authoring"');
    expect(html).toContain('data-workspace-view="library"');
    expect(html).toContain('data-workspace-view="lesson"');
    expect(html).toContain('data-workspace-view="paper"');
  });

  it("separates private upload controls from owner-scoped search and review results", () => {
    const html = renderToStaticMarkup(<PrivateLibraryWorkspace />);

    expect(html).toContain('class="resizable-split-pane library-workbench-split"');
    expect(html).toContain('aria-label="调整资料上传与资料详情区域宽度"');
    expect(html).toContain("library-workbench-pane--upload");
    expect(html).toContain("library-workbench-pane--results");
    expect(html).toContain('role="separator"');
    expect(html).toContain("当前教师私人空间");
  });

  it("does not mount workspaces that the current beta session cannot use", () => {
    const html = renderToStaticMarkup(
      <BetaCapabilityBoundary capabilities={["search", "teacher_memory"]}>
        <TeacherWorkbench />
      </BetaCapabilityBoundary>,
    );

    expect(html).toContain('aria-label="搜题，已开放"');
    expect(html).toContain('aria-label="组卷，封闭测试暂未开放"');
    expect(html).not.toContain('data-workspace-view="authoring"');
    expect(html).not.toContain('data-workspace-view="library"');
    expect(html).not.toContain('data-workspace-view="lesson"');
    expect(html).not.toContain('data-workspace-view="paper"');
  });

  it("groups the current user, teacher preferences and sign out under Settings", () => {
    const html = renderToStaticMarkup(
      <AccountSettingsPopover
        error=""
        onOpenBetaValidation={() => undefined}
        onOpenTeacherPreferences={() => undefined}
        onSignOut={() => undefined}
        session={{
          busy: false,
          canSignOut: true,
          displayLabel: "测试教师",
          mode: "closed_beta",
          signOut: async () => undefined,
        }}
        teacherPreferencesAvailable
      />,
    );

    expect(html).toContain('aria-label="设置中的用户项目"');
    expect(html).toContain("测试教师");
    expect(html).toContain("封闭测试用户");
    expect(html).toContain("教师偏好");
    expect(html).toContain("封闭测试与数据");
    expect(html).toContain("退出登录");
  });

  it("explains that closed-beta metric collection is optional and content-free", () => {
    const html = renderToStaticMarkup(
      <BetaValidationPanel open onClose={() => undefined} />,
    );

    expect(html).toContain("封闭测试与数据");
    expect(html).toContain("由你决定是否参与");
    expect(html).toContain("数据验证默认关闭");
    expect(html).toContain("不含题面、答案、解析或教师输入正文");
  });
});
