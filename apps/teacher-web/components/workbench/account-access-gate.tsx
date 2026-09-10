"use client";

import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  type AccountSessionStatus,
  TeacherWorkspaceError,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";

import {
  AuthenticatedSessionBoundary,
  BetaAccessGate,
  type BetaSessionContextValue,
} from "./beta-access-gate";

type AccountAccessMode = "login" | "register";

type AccountAccessScreenProps = {
  busy: boolean;
  error: string;
  mode: AccountAccessMode;
  registrationEnabled: boolean;
  email: string;
  displayLabel: string;
  password: string;
  passwordConfirmation: string;
  onModeChange: (mode: AccountAccessMode) => void;
  onEmailChange: (value: string) => void;
  onDisplayLabelChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onPasswordConfirmationChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function AccountAccessScreen({
  busy,
  error,
  mode,
  registrationEnabled,
  email,
  displayLabel,
  password,
  passwordConfirmation,
  onModeChange,
  onEmailChange,
  onDisplayLabelChange,
  onPasswordChange,
  onPasswordConfirmationChange,
  onSubmit,
}: AccountAccessScreenProps) {
  const registering = mode === "register";
  return (
    <main className="beta-access account-access">
      <section className="beta-access__card" aria-labelledby="account-access-title">
        <p className="beta-access__eyebrow">TEACHER ACCOUNT</p>
        <h1 id="account-access-title">
          {registering ? "创建个人教师账号" : "登录教师工作台"}
        </h1>
        <p>
          {registering
            ? "账号、个人空间与内容归属由系统安全建立，注册后直接进入工作台。"
            : "使用你的教师账号继续访问仅自己可见的资料、私题、教案与试卷。"}
        </p>
        {registrationEnabled ? (
          <div className="account-access__switch" aria-label="登录或注册">
            <button
              aria-pressed={!registering}
              disabled={busy}
              onClick={() => onModeChange("login")}
              type="button"
            >
              登录
            </button>
            <button
              aria-pressed={registering}
              disabled={busy}
              onClick={() => onModeChange("register")}
              type="button"
            >
              注册账号
            </button>
          </div>
        ) : null}
        <form onSubmit={onSubmit}>
          <label htmlFor="account-email">邮箱</label>
          <input
            autoComplete="email"
            disabled={busy}
            id="account-email"
            onChange={(event) => onEmailChange(event.target.value)}
            required
            type="email"
            value={email}
          />
          {registering ? (
            <>
              <label htmlFor="account-display-label">显示名称</label>
              <input
                autoComplete="name"
                disabled={busy}
                id="account-display-label"
                maxLength={80}
                onChange={(event) => onDisplayLabelChange(event.target.value)}
                required
                type="text"
                value={displayLabel}
              />
            </>
          ) : null}
          <label htmlFor="account-password">密码</label>
          <input
            autoComplete={registering ? "new-password" : "current-password"}
            disabled={busy}
            id="account-password"
            minLength={registering ? 12 : undefined}
            onChange={(event) => onPasswordChange(event.target.value)}
            required
            type="password"
            value={password}
          />
          {registering ? (
            <>
              <small>至少 12 个字符。</small>
              <label htmlFor="account-password-confirmation">确认密码</label>
              <input
                autoComplete="new-password"
                disabled={busy}
                id="account-password-confirmation"
                minLength={12}
                onChange={(event) => onPasswordConfirmationChange(event.target.value)}
                required
                type="password"
                value={passwordConfirmation}
              />
            </>
          ) : null}
          {error ? <p className="beta-access__error" role="alert">{error}</p> : null}
          <button disabled={busy} type="submit">
            {busy ? "正在处理…" : registering ? "创建账号并进入" : "登录"}
          </button>
        </form>
        {registering ? (
          <p className="account-access__notice">
            当前仅创建个人教师账号；邮箱验证、账号找回与 MFA 将在后续安全切片完成。
          </p>
        ) : null}
      </section>
    </main>
  );
}

function accountErrorMessage(cause: unknown, mode: AccountAccessMode): string {
  if (!(cause instanceof TeacherWorkspaceError)) {
    return mode === "register" ? "暂时无法创建账号，请稍后重试。" : "暂时无法登录，请稍后重试。";
  }
  if (cause.code === "LOGIN_RATE_LIMITED") return "尝试过多，请稍后再试。";
  if (mode === "login" && cause.code === "HTTP_401") return "邮箱或密码无效。";
  if (cause.code === "ACCOUNT_REGISTRATION_CONFLICT" || cause.code === "HTTP_409") {
    return "无法创建账号，请检查信息或直接登录。";
  }
  return cause.message;
}

export function AccountAccessGate({ children }: { children: ReactNode }) {
  const [backend, setBackend] = useState<"checking" | "account" | "beta" | "error">("checking");
  const [status, setStatus] = useState<AccountSessionStatus | null>(null);
  const [mode, setMode] = useState<AccountAccessMode>("login");
  const [email, setEmail] = useState("");
  const [displayLabel, setDisplayLabel] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    teacherWorkspace.getAccountSession(controller.signal)
      .then((next) => {
        setStatus(next);
        setBackend("account");
      })
      .catch((cause) => {
        if (cause instanceof TeacherWorkspaceError && cause.code === "PRODUCTION_IDENTITY_DISABLED") {
          setBackend("beta");
          return;
        }
        setError("暂时无法确认账号状态，请稍后重试。");
        setBackend("error");
      });
    return () => controller.abort();
  }, []);

  const changeMode = (next: AccountAccessMode) => {
    setMode(next);
    setPassword("");
    setPasswordConfirmation("");
    setError("");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "register" && password !== passwordConfirmation) {
      setError("两次输入的密码不一致。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const next = mode === "register"
        ? await teacherWorkspace.registerAccount({
            email: email.trim(),
            display_label: displayLabel.trim(),
            password,
            password_confirmation: passwordConfirmation,
          })
        : await teacherWorkspace.startAccountSession(email.trim(), password);
      setStatus(next);
      setPassword("");
      setPasswordConfirmation("");
    } catch (cause) {
      setError(accountErrorMessage(cause, mode));
    } finally {
      setBusy(false);
    }
  };

  const leave = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      setStatus(await teacherWorkspace.endAccountSession());
    } catch (cause) {
      setError(accountErrorMessage(cause, "login"));
    } finally {
      setBusy(false);
    }
  }, []);

  const session = useMemo<BetaSessionContextValue>(() => ({
    busy,
    canSignOut: true,
    displayLabel: status?.display_label || "教师",
    mode: "production_identity",
    signOut: leave,
  }), [busy, leave, status?.display_label]);

  if (backend === "beta") return <BetaAccessGate>{children}</BetaAccessGate>;
  if (backend === "checking") {
    return <main className="beta-access beta-access--loading" aria-live="polite">正在确认账号登录状态…</main>;
  }
  if (backend === "error" || !status) {
    return <main className="beta-access"><p className="beta-access__error">{error}</p></main>;
  }
  if (!status.authenticated) {
    return (
      <AccountAccessScreen
        busy={busy}
        displayLabel={displayLabel}
        email={email}
        error={error}
        mode={mode}
        onDisplayLabelChange={setDisplayLabel}
        onEmailChange={setEmail}
        onModeChange={changeMode}
        onPasswordChange={setPassword}
        onPasswordConfirmationChange={setPasswordConfirmation}
        onSubmit={submit}
        password={password}
        passwordConfirmation={passwordConfirmation}
        registrationEnabled={status.registration_enabled}
      />
    );
  }
  return (
    <AuthenticatedSessionBoundary capabilities={status.capabilities} session={session}>
      {children}
    </AuthenticatedSessionBoundary>
  );
}
