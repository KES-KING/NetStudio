"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, requireLogin } from "../lib/api";
import { formatTime } from "../lib/metrics";

type Notice = { id: string; title: string; description: string; href: string; occurred_at: string; unread: boolean; severity: string };
type Feed = { items: Notice[]; unread_count: number; latest_id: string | null; update_available: boolean; maintenance: boolean };
const empty: Feed = { items: [], unread_count: 0, latest_id: null, update_available: false, maintenance: false };

export function useNotificationFeed() {
  const [feed, setFeed] = useState<Feed>(empty), [connected, setConnected] = useState(false);
  useEffect(() => {
    const source = new EventSource("/api/v1/notifications/stream");
    source.addEventListener("notifications", (event) => {
      try { setFeed(JSON.parse((event as MessageEvent).data)); setConnected(true); }
      catch { setConnected(false); }
    });
    source.addEventListener("revoked", () => { source.close(); requireLogin("Oturumunuz sona erdi. Yeniden giriş yapın."); });
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    return () => source.close();
  }, []);
  return { feed, connected };
}

export function LiveNotifications({ feed, connected }: ReturnType<typeof useNotificationFeed>) {
  const [open, setOpen] = useState(false), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const path = usePathname(), [previousPath, setPreviousPath] = useState(path);
  const root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null);
  if (previousPath !== path) { setPreviousPath(path); setOpen(false); }
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", key); };
  }, [open]);
  async function acknowledge() {
    if (!feed.latest_id) return;
    setBusy(true); setError("");
    try { await api("/api/v1/notifications/read", { method: "POST", body: JSON.stringify({ through_id: feed.latest_id }) }); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <div ref={root} className={`notification-center${open ? " is-open" : ""}`}>
    <button ref={trigger} className="notification-toggle" aria-label={`Bildirimler${feed.unread_count ? ` (${feed.unread_count >= 100 ? "99+" : feed.unread_count} okunmamış)` : ""}`} aria-expanded={open} aria-controls="notification-panel" title="Canlı bildirimler" onClick={() => setOpen(!open)}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zm5 3h4M12 2v2" /></svg>
      {feed.unread_count > 0 && <span className="notification-count" aria-hidden="true">{feed.unread_count >= 100 ? "99+" : feed.unread_count}</span>}
    </button>
    <div className="notification-dropdown" id="notification-panel" aria-hidden={!open} inert={!open}>
      <div className="notification-clip"><section className="notification-surface" aria-label="Canlı bildirimler">
        <div className="notification-heading"><div><h2>Bildirimler</h2><span className={connected ? "feed-connected" : "feed-disconnected"}>{connected ? "Canlı · sunucu olayları" : "Bağlantı bekleniyor · son alınan olaylar"}</span></div><button aria-label="Bildirimleri kapat" onClick={() => { setOpen(false); trigger.current?.focus(); }}>×</button></div>
        <div className="notification-list">{!feed.items.length ? <p className="notification-empty">{connected ? "Son 7 günde bu kapsamda bildirim yok." : "Bildirim akışına bağlanılıyor…"}</p> : feed.items.map((item) => <Link key={item.id} href={item.href} onClick={() => setOpen(false)} className={`notification-item ${item.unread ? "unread" : ""} ${item.severity}`}>
          <strong>{item.title}</strong><span>{item.description}</span><time dateTime={item.occurred_at}>{formatTime(item.occurred_at)}</time>
        </Link>)}</div>
        <div className="notification-footer"><span>Son 30 olay · yetkili kapsam</span><button disabled={busy || !feed.unread_count} onClick={() => void acknowledge()}>Okundu olarak işaretle</button></div>
        {error && <p role="alert" className="notice error">{error}</p>}
      </section></div>
    </div>
  </div>;
}
