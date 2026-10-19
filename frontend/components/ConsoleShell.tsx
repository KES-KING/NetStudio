"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, errorMessage, fetchSession, setSessionToken } from "../lib/api";
import type { Session } from "../lib/contracts";

const SessionContext = createContext<Session | null>(null);
export function useSession() {
  return useContext(SessionContext)!;
}

export function ConsoleShell({ children }: { children: ReactNode }) {
  const path = usePathname();
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
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const clear = useCallback(() => {
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
          <h1>Bağlantı kurulamadı</h1>
          <p role="alert">{errorMessage(error)}</p>
          <button onClick={() => mutate()}>Yeniden dene</button>
        </section>
      </div>
    );
  if (!user)
    return (
      <Login
        onLogin={(value) => {
          setSessionToken(value.csrf_token);
          void mutate(value, { revalidate: false });
        }}
      />
    );
  return (
    <SessionContext.Provider value={user}>
      <a href="#main-content" className="skip-link">
        İçeriğe geç
      </a>
      <header className="topbar">
        <Link href="/" className="brand">
          Stocc <strong>NetStudio</strong>
        </Link>
        <button
          className="mobile-menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          Menü
        </button>
        <div className="session-nav">
          <span>{user.display_name}</span>
          <button onClick={logout}>Çıkış</button>
        </div>
      </header>
      <div className="console-layout">
        <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
          <nav aria-label="Ana navigasyon">
            <Link
              onClick={() => setMenuOpen(false)}
              aria-current={
                path === "/" || path.startsWith("/devices") ? "page" : undefined
              }
              href="/"
            >
              Ağ cihazları
            </Link>
            <Link
              onClick={() => setMenuOpen(false)}
              aria-current={path === "/jobs" ? "page" : undefined}
              href="/jobs"
            >
              İş geçmişi
            </Link>
            {user.permissions.includes("audit.read") && (
              <Link
                onClick={() => setMenuOpen(false)}
                aria-current={path === "/audit" ? "page" : undefined}
                href="/audit"
              >
                Denetim kayıtları
              </Link>
            )}
          </nav>
          <div className="sidebar-footer">
            Ağ yönetimi
            <br />
            <span>
              {user.roles
                .map(
                  (r) =>
                    ({
                      admin: "Yönetici",
                      operator: "Operatör",
                      viewer: "Gözlemci",
                    })[r] ?? r,
                )
                .join(" · ")}
            </span>
          </div>
        </aside>
        <main id="main-content" className="main-content">
          {logoutError && (
            <p role="alert" className="notice error">
              {logoutError}
            </p>
          )}
          {children}
        </main>
      </div>
    </SessionContext.Provider>
  );
}

function Login({ onLogin }: { onLogin: (user: Session) => void }) {
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
          Stocc <strong>NetStudio</strong>
        </div>
        <h1>Yönetim oturumu</h1>
        <p>Ağ cihazlarınızı ve gözlemlerinizi yönetin.</p>
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
