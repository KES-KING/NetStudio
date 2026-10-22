"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useSession } from "./ConsoleShell";

export function SettingsLayout({ children }: { children: ReactNode }) {
  const path = usePathname(), session = useSession();
  const tabs = [{ href: "/settings", label: "Hesabım", description: "Profil ve oturum güvenliği" },
    ...(session.permissions.includes("user.manage") ? [{ href: "/settings/users", label: "Kullanıcılar", description: "Hesap oluşturma ve yetkiler" }] : []),
    ...(session.permissions.includes("network_probe.manage") ? [{ href: "/settings/network-probes", label: "Ağ keşfi", description: "VLAN ARP probe kapsamları" }] : []),
    { href: "/settings/updates", label: "Güncellemeler", description: "main · sürüm ve kurulum" }];
  return <>
    <div className="page-heading"><div><p className="eyebrow">SİSTEM VE KİŞİSEL TERCİHLER</p><h1>Ayarlar</h1><p>Hesabınızı, erişimleri ve NetStudio güncellemelerini yönetin.</p></div></div>
    <nav className="settings-tabs" aria-label="Ayarlar bölümleri">{tabs.map((tab) => <Link key={tab.href} href={tab.href} transitionTypes={["nav-section"]} aria-current={path === tab.href ? "page" : undefined}><strong>{tab.label}</strong><small>{tab.description}</small></Link>)}</nav>
    <div className="settings-content">{children}</div>
  </>;
}
