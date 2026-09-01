import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PrivateLibraryWorkspace } from "./private-library-workspace";
import { getWorkspaceVisibility, TeacherWorkbench } from "./teacher-workbench";

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
});
