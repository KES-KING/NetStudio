"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Session } from "../lib/contracts";
import { roleLabels } from "../lib/accounts";
import { Brand } from "./Brand";
import { RepositoryLink } from "./RepositoryLink";
import { UserAvatar } from "./UserAvatar";
import { LiveNotifications, useNotificationFeed } from "./LiveNotifications";

type IconName = "devices" | "topology" | "history" | "audit" | "account" | "panel" | "menu" | "close" | "logout" | "settings";

function NavigationIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    devices: <><rect x="3" y="5" width="18" height="14" /><path d="M6 9h2m3 0h2m3 0h2M6 13h2m3 0h2m3 0h2M6 16h12" /></>,
    topology: <><circle cx="12" cy="5" r="3" /><circle cx="5" cy="19" r="3" /><circle cx="19" cy="19" r="3" /><path d="m10.5 7.5-4 9m7-9 4 9M8 19h8" /></>,
    history: <><path d="M3 10a9 9 0 1 1 1 7M3 4v6h6M12 7v5l3 2" /></>,
    audit: <><path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8m-8 4h8" /></>,
    account: <><circle cx="12" cy="7" r="4" /><path d="M4 21v-3a8 8 0 0 1 16 0v3z" /></>,
    panel: <><rect x="3" y="4" width="18" height="16" /><path d="M9 4v16" /><path className="panel-chevron" d="m16 8-4 4 4 4" /></>,
    menu: <path d="M3 6h18M3 12h18M3 18h18" />,
    close: <path d="m5 5 14 14M5 19 19 5" />,
    logout: <><path d="M9 4H4v16h5m5-13 5 5-5 5M8 12h12" /></>,
    settings: <><path d="M4 6h16M4 12h16M4 18h16" /><rect x="7" y="4" width="3" height="4" /><rect x="14" y="10" width="3" height="4" /><rect x="8" y="16" width="3" height="4" /></>,
  };
  return <svg className="navigation-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

const navigation = [
  { href: "/", label: "Ağ cihazları", description: "Envanter ve portlar", icon: "devices" },
  { href: "/topology", label: "Topoloji", description: "Bağlantı haritası", icon: "topology" },
  { href: "/jobs", label: "İş geçmişi", description: "Toplama işlemleri", icon: "history" },
  { href: "/audit", label: "Denetim kayıtları", description: "Kullanıcı etkinlikleri", icon: "audit" },
  { href: "/settings", label: "Ayarlar", description: "Hesap ve güncellemeler", icon: "settings" },
] as const;

function readCollapsed(key: string) {
  try { return window.localStorage.getItem(key) === "collapsed"; }
  catch { return false; } // Storage can be unavailable in restricted browsers.
}

export function ConsoleNavigation({ user, onLogout, children }: {
  user: Session;
  onLogout: () => void;
  children: ReactNode;
}) {
  const path = usePathname();
  const notification = useNotificationFeed();
  const preferenceKey = `netstudio:sidebar:v1:${user.user_id}`;
  const [collapsed, setCollapsed] = useState(() => readCollapsed(preferenceKey));
  const [mobile, setMobile] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [previousPath, setPreviousPath] = useState(path);
  if (previousPath !== path) {
    setPreviousPath(path);
    setMenuOpen(false);
  }
  const sidebar = useRef<HTMLElement>(null);
  const mobileToggle = useRef<HTMLButtonElement>(null);
  const desktopToggle = useRef<HTMLButtonElement>(null);
  const drawerOpen = mobile && menuOpen;
  const roles = user.roles.map((role) => roleLabels[role] ?? role).join(" · ");
  const currentPage = path.startsWith("/devices/") ? "Cihaz detayı"
    : path.startsWith("/settings") ? path === "/settings/updates" ? "Güncellemeler" : "Ayarlar"
    : path === "/account" ? "Hesabım"
    : navigation.find((item) => item.href === path)?.label ?? "NetStudio";

  useEffect(() => {
    const query = window.matchMedia("(max-width: 700px)");
    const update = () => {
      setMobile(query.matches);
      setMenuOpen(false);
    };
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!drawerOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = sidebar.current!;
    dialog.querySelector<HTMLButtonElement>(".sidebar-close")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
      }
      if (event.key !== "Tab") return;
      const elements = Array.from(dialog.querySelectorAll<HTMLElement>("a[href], button:not([disabled])"))
        .filter((element) => element.getClientRects().length > 0);
      const first = elements[0];
      const last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", keydown);
      const trigger = window.matchMedia("(max-width: 700px)").matches ? mobileToggle : desktopToggle;
      trigger.current?.focus();
    };
  }, [drawerOpen]);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    try { window.localStorage.setItem(preferenceKey, next ? "collapsed" : "expanded"); }
    catch { /* The control remains usable without persistence. */ }
  }

  return (
    <div className={`console-shell${collapsed ? " sidebar-collapsed" : ""}`}>
      <a href="#main-content" className="skip-link" inert={drawerOpen}>İçeriğe geç</a>
      <header className="topbar" inert={drawerOpen}>
        <div className="topbar-brand">
          <Link href="/" className="brand" aria-label="NetStudio — Ağ cihazları">
            <span className="brand-wordmark"><Brand decorative /></span>
            <span className="brand-emblem"><Brand variant="emblem" decorative /></span>
          </Link>
        </div>
        <div className="topbar-context">
          {(notification.feed.update_available || notification.feed.maintenance) && <Link href="/settings/updates" className="topbar-update" aria-label={notification.feed.maintenance ? "Güncelleme sürüyor — güncelleme sayfasını aç" : "Yeni güncelleme var — güncelleme sayfasını aç"} title={notification.feed.maintenance ? "Güncelleme sürüyor" : "Yeni güncelleme var"}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /></svg><span>Güncelleme</span>
          </Link>}
          <button ref={desktopToggle} className="sidebar-toggle" onClick={toggleCollapsed}
            aria-label={collapsed ? "Yan menüyü genişlet" : "Yan menüyü daralt"}
            title={collapsed ? "Yan menüyü genişlet" : "Yan menüyü daralt"}
            aria-expanded={!collapsed} aria-controls="console-sidebar">
            <NavigationIcon name="panel" />
          </button>
          <button ref={mobileToggle} className="mobile-menu" aria-label="Menü"
            aria-expanded={drawerOpen} aria-controls="console-sidebar" onClick={() => setMenuOpen(true)}>
            <NavigationIcon name="menu" /><span>Menü</span>
          </button>
          <div className="topbar-page"><small>Çalışma alanı</small><strong>{currentPage}</strong></div>
        </div>
        <div className="session-nav">
          <LiveNotifications {...notification} />
          <Link href="/settings" className="account-link" aria-label="Hesabım — profil ve kullanıcı yönetimi"
            aria-current={path === "/account" || path === "/settings" ? "page" : undefined}>
            <UserAvatar id={user.user_id} name={user.display_name} version={user.avatar_version} />
            <span className="account-link-text"><strong>{user.display_name}</strong><small>{roles}</small></span>
          </Link>
          <button className="logout-button" onClick={onLogout}><NavigationIcon name="logout" /><span>Çıkış</span></button>
        </div>
      </header>
      <div className="console-layout">
        {drawerOpen && <div className="sidebar-backdrop" aria-hidden="true" onClick={() => setMenuOpen(false)} />}
        <aside ref={sidebar} id="console-sidebar" className={`sidebar${drawerOpen ? " open" : ""}`}
          inert={mobile && !drawerOpen} role={drawerOpen ? "dialog" : undefined}
          aria-modal={drawerOpen ? true : undefined} aria-label={drawerOpen ? "Navigasyon menüsü" : undefined}>
          <div className="sidebar-navigation">
            <div className="sidebar-heading"><span>Çalışma alanı</span>
              <button className="sidebar-close" aria-label="Menüyü kapat" onClick={() => setMenuOpen(false)}><NavigationIcon name="close" /></button>
            </div>
            <nav aria-label="Ana navigasyon">
              {navigation.filter((item) => item.href !== "/audit" || user.permissions.includes("audit.read")).map((item) => (
                <Link key={item.href} href={item.href} prefetch={item.href === "/topology" ? false : undefined} aria-label={item.label} title={item.label}
                  onClick={() => setMenuOpen(false)}
                  aria-current={path === item.href || (item.href === "/settings" && path.startsWith("/settings/")) || (item.href === "/" && path.startsWith("/devices")) ? "page" : undefined}>
                  <NavigationIcon name={item.icon} />
                  <span className="sidebar-label" aria-hidden="true"><strong>{item.label}</strong><small>{item.description}</small></span>
                </Link>
              ))}
            </nav>
          </div>
          <div className="sidebar-footer">
            <div className="sidebar-session">
              <UserAvatar id={user.user_id} name={user.display_name} version={user.avatar_version} />
              <span className="sidebar-label"><strong>{user.display_name}</strong><small>{roles}</small></span>
            </div>
            <div className="sidebar-footer-actions">
              <RepositoryLink />
              <Link href="/settings" className="sidebar-account-link" aria-label="Hesabım — hesap sayfasını aç" title="Hesabım"
                aria-current={path === "/account" || path === "/settings" ? "page" : undefined} onClick={() => setMenuOpen(false)}>
                <NavigationIcon name="account" /><span className="sidebar-label">Hesabım</span>
              </Link>
            </div>
          </div>
        </aside>
        <main id="main-content" className="main-content" inert={drawerOpen} tabIndex={-1}>{children}</main>
      </div>
    </div>
  );
}
