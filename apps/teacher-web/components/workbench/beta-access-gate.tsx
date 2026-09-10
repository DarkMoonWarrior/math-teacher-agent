"use client";

import {
  createContext,
  type FormEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  TeacherWorkspaceError,
  PRODUCT_CAPABILITIES,
  type BetaSessionStatus,
  type ProductCapability,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";

type BetaAccessScreenProps = {
  busy: boolean;
  error: string;
  accessCode: string;
  onAccessCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

const DEFAULT_CAPABILITIES = new Set<ProductCapability>(PRODUCT_CAPABILITIES);
const BetaCapabilityContext = createContext<ReadonlySet<ProductCapability>>(DEFAULT_CAPABILITIES);

export type BetaSessionContextValue = {
  busy: boolean;
  canSignOut: boolean;
  displayLabel: string;
  mode: BetaSessionStatus["mode"] | "production_identity";
  signOut: () => Promise<void>;
};

const DEFAULT_SESSION: BetaSessionContextValue = {
  busy: false,
  canSignOut: false,
  displayLabel: "本地教师",
  mode: "local_development",
  signOut: async () => undefined,
};

const BetaSessionContext = createContext<BetaSessionContextValue>(DEFAULT_SESSION);

export function useBetaCapabilities(): ReadonlySet<ProductCapability> {
  return useContext(BetaCapabilityContext);
}

export function useBetaSession(): BetaSessionContextValue {
  return useContext(BetaSessionContext);
}

export function BetaCapabilityBoundary({
  capabilities,
  children,
}: {
  capabilities: readonly ProductCapability[];
  children: ReactNode;
}) {
  const value = useMemo(() => new Set<ProductCapability>(capabilities), [capabilities]);
  return <BetaCapabilityContext.Provider value={value}>{children}</BetaCapabilityContext.Provider>;
}

export function AuthenticatedSessionBoundary({
  capabilities,
  children,
  session,
}: {
  capabilities: readonly ProductCapability[];
  children: ReactNode;
  session: BetaSessionContextValue;
}) {
  const capabilitySet = useMemo(
    () => new Set<ProductCapability>(capabilities),
    [capabilities],
  );
  return (
    <BetaSessionContext.Provider value={session}>
      <BetaCapabilityContext.Provider value={capabilitySet}>
        {children}
      </BetaCapabilityContext.Provider>
    </BetaSessionContext.Provider>
  );
}

export function BetaAccessScreen({
  busy,
  error,
  accessCode,
  onAccessCodeChange,
  onSubmit,
}: BetaAccessScreenProps) {
  return (
    <main className="beta-access">
      <section className="beta-access__card" aria-labelledby="beta-access-title">
        <p className="beta-access__eyebrow">CLOSED BETA</p>
        <h1 id="beta-access-title">进入教师封闭测试</h1>
        <p>输入邀请中提供的访问码。访问码不会保存在浏览器中。</p>
        <form onSubmit={onSubmit}>
          <label htmlFor="beta-access-code">访问码</label>
          <input
            id="beta-access-code"
            type="password"
            autoComplete="one-time-code"
            value={accessCode}
            onChange={(event) => onAccessCodeChange(event.target.value)}
            disabled={busy}
            required
          />
          {error ? <p className="beta-access__error" role="alert">{error}</p> : null}
          <button type="submit" disabled={busy || !accessCode.trim()}>
            {busy ? "正在验证…" : "进入工作区"}
          </button>
        </form>
      </section>
    </main>
  );
}

export function BetaAccessGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BetaSessionStatus | null>(null);
  const [accessCode, setAccessCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const capabilities = useMemo(
    () => new Set<ProductCapability>(status?.capabilities ?? []),
    [status?.capabilities],
  );

  useEffect(() => {
    const controller = new AbortController();
    teacherWorkspace.getBetaSession(controller.signal)
      .then(setStatus)
      .catch(() => setError("暂时无法确认访问状态，请稍后重试。"));
    return () => controller.abort();
  }, []);

  const enter = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setStatus(await teacherWorkspace.startBetaSession(accessCode.trim()));
      setAccessCode("");
    } catch (cause) {
      setError(cause instanceof TeacherWorkspaceError
        ? "访问码无效或已不可用。"
        : "暂时无法进入封闭测试，请稍后重试。");
    } finally {
      setBusy(false);
    }
  };

  const leave = useCallback(async () => {
    setBusy(true);
    try {
      setStatus(await teacherWorkspace.endBetaSession());
      setAccessCode("");
      setError("");
    } finally {
      setBusy(false);
    }
  }, []);

  const session = useMemo<BetaSessionContextValue>(() => ({
    busy,
    canSignOut: status?.mode === "closed_beta",
    displayLabel: status?.display_label || DEFAULT_SESSION.displayLabel,
    mode: status?.mode ?? DEFAULT_SESSION.mode,
    signOut: leave,
  }), [busy, leave, status]);

  if (!status && !error) {
    return <main className="beta-access beta-access--loading" aria-live="polite">正在确认封闭测试访问…</main>;
  }

  if (!status || !status.authenticated) {
    return (
      <BetaAccessScreen
        busy={busy}
        error={error}
        accessCode={accessCode}
        onAccessCodeChange={setAccessCode}
        onSubmit={enter}
      />
    );
  }

  return (
    <BetaSessionContext.Provider value={session}>
      <BetaCapabilityContext.Provider value={capabilities}>
        {children}
      </BetaCapabilityContext.Provider>
    </BetaSessionContext.Provider>
  );
}
