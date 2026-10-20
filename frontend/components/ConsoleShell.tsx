"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, errorMessage, fetchSession, setSessionToken } from "../lib/api";
import type { Session } from "../lib/contracts";
import { Brand } from "./Brand";
import { ConsoleNavigation } from "./ConsoleNavigation";
import { recordActivity } from "../lib/activity";

const SessionContext = createContext<Session | null>(null);
export function useSession() {
  return useContext(SessionContext)!;
}

export function ConsoleShell({ children }: { children: ReactNode }) {
  const { mutate: mutateAll } = useSWRConfig();
  const {
    data: user,
    error,
    mutate,
    isLoading,
  } = useSWR("/api/v1/session/me", fetchSession, {
    refreshInterval: 30000,
    shouldRetryOnError: false,
  });
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [loginNotice, setLoginNotice] = useState("");
  const clear = useCallback((event?: Event) => {
    setLoginNotice(event instanceof CustomEvent ? String(event.detail?.message ?? "") : "");
    setSessionToken("");
    void mutateAll(
      (key) => typeof key === "string" && key.startsWith("/api/"),
      undefined,
      { revalidate: false },
    );
    void mutate(null, { revalidate: false });
  }, [mutateAll, mutate]);
  useEffect(() => {
    window.addEventListener("stocc-session-expired", clear);
    return () => window.removeEventListener("stocc-session-expired", clear);
  }, [clear]);
  async function logout() {
    try {
      await api("/api/v1/session/logout", { method: "POST" });
      clear();
    } catch (e) {
      setLogoutError(errorMessage(e));
    }
  }
  if (isLoading)
    return (
      <div className="auth-page">
        <p role="status">Oturum doğrulanıyor…</p>
      </div>
    );
  if (error)
    return (
      <div className="auth-page">
        <section className="login-panel">
          <div className="login-brand">
            <Brand />
          </div>
          <h1>Bağlantı kurulamadı</h1>
          <p role="alert">{errorMessage(error)}</p>
          <button onClick={() => mutate()}>Yeniden dene</button>
        </section>
      </div>
    );
  if (!user)
    return (
      <Login
        notice={loginNotice}
        onLogin={(value) => {
          setLoginNotice("");
          setSessionToken(value.csrf_token);
          void mutate(value, { revalidate: false });
        }}
      />
    );
  return (
    <SessionContext.Provider value={user}>
      <NavigationAudit />
      <ConsoleNavigation key={user.user_id} user={user} onLogout={logout}>
        {logoutError && (
          <p role="alert" className="notice error">
            {logoutError}
          </p>
        )}
        {children}
      </ConsoleNavigation>
    </SessionContext.Provider>
  );
}

function NavigationAudit() {
  const path = usePathname();
  const user = useSession();
  const previous = useRef("");
  useEffect(() => {
    const key = `${user.user_id}:${path}`;
    if (previous.current === key) return;
    previous.current = key;
    if (path === "/") recordActivity({ action: "page.view", page: "dashboard" });
    else if (path === "/topology") recordActivity({ action: "page.view", page: "topology" });
    else if (path.startsWith("/devices/")) recordActivity({ action: "page.view", page: "device", device_id: path.split("/")[2] });
    else if (path === "/jobs" || path === "/account") recordActivity({ action: "page.view", page: path.slice(1) as "jobs" | "account" });
    else if (path === "/audit" && user.permissions.includes("audit.read")) recordActivity({ action: "page.view", page: "audit" });
  }, [path, user.user_id, user.permissions]);
  return null;
}

function Login({ onLogin, notice }: { onLogin: (user: Session) => void; notice?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const value = await api<Session>("/api/v1/session/login", {
        method: "POST",
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password"),
        }),
      });
      form.reset();
      onLogin(value);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <section className="login-panel">
        <div className="login-brand">
          <Brand />
        </div>
        <h1>Yönetim oturumu</h1>
        <p>Ağ cihazlarınızı ve gözlemlerinizi yönetin.</p>
        {notice && <p className="notice" role="status">{notice}</p>}
        <form onSubmit={submit}>
          <label>
            Kullanıcı adı
            <input
              name="username"
              autoComplete="username"
              required
              maxLength={160}
            />
          </label>
          <label>
            Parola
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
            />
          </label>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy ? "Doğrulanıyor…" : "Giriş yap"}
          </button>
        </form>
      </section>
    </main>
  );
}
