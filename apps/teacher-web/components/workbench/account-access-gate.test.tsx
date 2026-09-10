import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AccountAccessScreen } from "./account-access-gate";

describe("AccountAccessScreen", () => {
  it("renders a real account login form without exposing identity selectors", () => {
    const html = renderToStaticMarkup(
      <AccountAccessScreen
        busy={false}
        error=""
        mode="login"
        registrationEnabled
        email=""
        displayLabel=""
        password=""
        passwordConfirmation=""
        onModeChange={() => undefined}
        onEmailChange={() => undefined}
        onDisplayLabelChange={() => undefined}
        onPasswordChange={() => undefined}
        onPasswordConfirmationChange={() => undefined}
        onSubmit={() => undefined}
      />,
    );

    expect(html).toContain("登录教师工作台");
    expect(html).toContain('type="email"');
    expect(html).toContain('autoComplete="current-password"');
    expect(html).toContain("注册账号");
    expect(html).not.toContain("owner_id");
    expect(html).not.toContain("tenant_id");
  });

  it("collects only email, display name and a confirmed password for registration", () => {
    const html = renderToStaticMarkup(
      <AccountAccessScreen
        busy={false}
        error=""
        mode="register"
        registrationEnabled
        email="teacher@example.com"
        displayLabel="王老师"
        password="password"
        passwordConfirmation="password"
        onModeChange={() => undefined}
        onEmailChange={() => undefined}
        onDisplayLabelChange={() => undefined}
        onPasswordChange={() => undefined}
        onPasswordConfirmationChange={() => undefined}
        onSubmit={() => undefined}
      />,
    );

    expect(html).toContain("创建个人教师账号");
    expect(html).toContain("显示名称");
    expect(html).toContain('autoComplete="new-password"');
    expect(html).toContain("确认密码");
    expect(html).toContain("至少 12 个字符");
    expect(html).not.toContain("管理员");
    expect(html).not.toContain("角色");
  });
});
