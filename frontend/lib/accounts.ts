import type { UserRole } from "./contracts";

export const roleLabels: Record<UserRole, string> = {
  viewer: "Viewer",
  engineer: "Engineer",
  superadmin: "Superadmin",
};
export const roleDescriptions: Record<UserRole, string> = {
  viewer: "Yetkili lokasyonlardaki envanter, telemetri ve iş geçmişini görüntüler.",
  engineer: "Yetkili lokasyonlarda cihaz, envanter, bağlantı bilgisi, telemetri, işler ve SSH yönetimi yapar.",
  superadmin: "Kullanıcıları ve yetkileri yönetir; ayrıntılı audit kayıtlarını görüntüler.",
};
export function initials(name: string) {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => Array.from(part)[0] ?? "").join("").toLocaleUpperCase("tr-TR") || "?";
}
export function avatarUrl(id: string, version: string) {
  return `/api/v1/users/${encodeURIComponent(id)}/avatar?v=${encodeURIComponent(version)}`;
}
