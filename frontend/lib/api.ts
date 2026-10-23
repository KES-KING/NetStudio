import type { Session } from "./contracts";

export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
  ) {
    super(code);
  }
}

let csrf = "";
export function setSessionToken(value: string) {
  csrf = value;
}

export function hasSessionToken() {
  return csrf.length > 0;
}

export function requireLogin(message: string) {
  window.dispatchEvent(new CustomEvent("netstudio-session-expired", { detail: { message } }));
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (typeof init.body === "string" && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method))
    headers.set("X-CSRF-Token", csrf);
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.endsWith("/login"))
      window.dispatchEvent(new Event("netstudio-session-expired"));
    throw new ApiError(
      payload?.detail?.code ?? "api_unavailable",
      response.status,
    );
  }
  return payload as T;
}

export async function fetchSession(): Promise<Session | null> {
  try {
    const value = await api<Session>("/api/v1/session/me");
    setSessionToken(value.csrf_token);
    return value;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

const messages: Record<string, string> = {
  system_maintenance: "Sistem güncelleniyor; yeni değişiklikler ve bağlantılar geçici olarak durduruldu. Ayarlar → Güncellemeler bölümünü inceleyin.",
  host_key_not_trusted: "SSH anahtarı henüz onaylanmadı. Bağlantı bilgileri bölümünden anahtarı bulun ve doğrulayın.",
  host_discovery_rate_limited: "Bu cihaz için anahtar keşfi dakikada bir yapılabilir. Bir dakika sonra tekrar deneyin.",
  host_candidate_expired_or_changed: "Anahtar adayının süresi doldu veya bağlantı ayarları değişti. Anahtarı yeniden bulun.",
  legacy_ssh_not_allowed: "Bu cihazda eski SSH algoritmalarına izin verilmemiş.",
  collector_platform_unsupported: "Cihazın işletim sistemi bu sürücüde desteklenmiyor. Sürücü seçimini ve destek matrisini kontrol edin.",
  driver_profile_collector_conflict: "Seçilen kanonik profil ile eski veri toplayıcı ayarı çelişiyor.",
  driver_profile_management_mode_conflict: "Seçilen yönetim modu bu cihaz profiliyle uyuşmuyor.",
  unknown_driver_profile: "Seçilen cihaz profili katalogda bulunamadı.",
  snmp_read_failed: "SNMPv3 okuması başarısız. Cihaz erişimini ve salt okunur SNMP ayarlarını kontrol edin.",
  snmp_authentication_failed: "SNMPv3 kimlik doğrulaması başarısız; otomatik kanal duraklatıldı.",
  topology_version_conflict: "Yerleşim başka bir sekmede değişti. Taslağınız korunuyor; güncel yerleşimi yükleyip değişikliklerinizi yeniden uygulayın.",
  topology_reference_unavailable: "Bir cihaz veya port artık erişilebilir değil. Gözlemleri yenileyip bu bağlantıyı kaldırın.",
  username_taken: "Bu kullanıcı adı zaten kullanımda.",
  user_not_found: "Kullanıcı bulunamadı; listeyi yenileyin.",
  last_superadmin: "Son aktif superadmin kaldırılamaz veya yetkisi düşürülemez.",
  probe_agent_not_found: "Probe ajanı bulunamadı.",
  probe_agent_update_empty: "Ajan için değiştirilecek bir alan seçilmedi.",
  probe_agent_site_bound: "Ajanın aktif kapsamları varken site değiştirilemez.",
  probe_scope_not_found: "ARP tarama kapsamı bulunamadı.",
  probe_scope_not_active: "ARP tarama kapsamı etkin değil veya yeniden onay bekliyor.",
  probe_agent_offline_or_wrong_site: "Seçilen ajan çevrimdışı veya farklı bir siteye bağlı.",
  probe_proposal_unavailable: "SVI önerisi artık güncel değil, çakışıyor veya yeniden doğrulanmalı.",
  probe_source_not_reported: "Seçilen kaynak IP, ajanın bildirdiği arayüzde bulunmuyor.",
  probe_source_conflicts_with_svi: "Switch SVI adresi probe kaynak adresi olarak kullanılamaz.",
  probe_target_budget_exceeded: "Bir ajan çevriminde en fazla 4096 IPv4 hedefi sorgulanabilir.",
  invalid_probe_target_cidr: "Hedef IPv4 aralığı SVI ağı içinde ve /22 veya daha dar olmalıdır.",
  overlapping_probe_targets: "Aynı kapsam içindeki hedef aralıklar birbiriyle çakışamaz.",
  probe_scope_overlap: "Aynı site, VLAN ve VRF için etkin bir tarama kapsamı bu aralıkla çakışıyor.",
  probe_vrf_confirmation_required: "Switch VRF bilgisini kanıtlamadı; VRF kapsamını açıkça doğrulayın.",
  active_probe_acknowledgement_required: "Aktif ARP broadcast taramasını onaylamanız gerekir.",
  probe_manual_rate_limited: "Bu kapsam için manuel tarama dakikada bir çalıştırılabilir.",
  self_lockout: "Kendi hesabınızı silemez, devre dışı bırakamaz veya rolünüzü düşüremezsiniz.",
  self_password_use_profile: "Kendi parolanızı Hesabım sayfasındaki mevcut parola doğrulamalı formdan değiştirin.",
  confirmation_mismatch: "Silme onayı için kullanıcı adını eksiksiz girin.",
  current_password_invalid: "Mevcut parolanız doğrulanamadı.",
  password_changed_retry: "Parola başka bir işlemde değişti; yeniden giriş yapın.",
  avatar_invalid: "Geçerli bir PNG, JPEG veya WebP görseli seçin. SVG kabul edilmez.",
  avatar_too_large: "Avatar dosyası en fazla 2 MB olabilir.",
  avatar_dimensions_invalid: "Avatar en fazla 2048 × 2048 piksel olmalı; animasyon desteklenmez.",
  request_too_large: "Gönderilen veri boyut sınırını aşıyor.",
  invalid_date_range: "Başlangıç zamanı bitiş zamanından sonra olamaz.",
  invalid_cursor: "Sayfalama bilgisi geçersiz. İlk sayfaya dönüp yeniden deneyin.",
  invalid_credentials: "Kullanıcı adı veya parola hatalı.",
  login_rate_limited:
    "Çok fazla deneme yapıldı. Birkaç dakika sonra tekrar deneyin.",
  session_expired: "Oturumunuz sona erdi. Yeniden giriş yapın.",
  api_unavailable: "Sunucuya ulaşılamıyor. Bağlantınızı kontrol edin.",
  forbidden: "Bu işlem için yetkiniz yok.",
  device_not_found_or_forbidden: "Cihaz bulunamadı veya erişim yetkiniz yok.",
  credentials_missing: "Bu cihaz için bağlantı kimlik bilgileri tanımlanmamış.",
  encryption_key_unavailable:
    "Sır deposunun şifreleme anahtarı hazır değil. Sistem yöneticinize başvurun.",
  credential_decryption_failed:
    "Kayıtlı kimlik bilgileri çözülemedi. Bağlantı durduruldu.",
  credential_secret_required:
    "Seçilen yöntem için parola veya özel anahtar gerekli.",
  host_key_required:
    "SSH host anahtarı henüz doğrulanmamış. Bağlantı bilgileri bölümünden güvenilir anahtarı kaydedin.",
  host_key_changed:
    "Cihazın SSH host anahtarı kayıtlı anahtarla eşleşmiyor. Bağlantı güvenlik nedeniyle durduruldu.",
  host_fingerprint_mismatch:
    "Anahtar ve doğruladığınız SHA256 fingerprint eşleşmiyor.",
  invalid_host_key: "Geçerli bir OpenSSH public host anahtarı girin.",
  host_key_replacement_requires_confirmation:
    "Kayıtlı host anahtarını değiştirmek için açık onay gerekli.",
  target_network_denied:
    "Kayıtlı hedef, kurulumun ek ağ kısıtı tarafından reddedildi. Loopback hedefler ayrıca açık izin gerektirir.",
  invalid_target_network_policy: "Kurulumun ek SSH ağ kısıtı geçersiz; bağlantı güvenli biçimde reddedildi.",
  invalid_management_address: "Bu yönetim IP adresi bağlantı için uygun değil.",
  device_connection_changed: "Cihazın bağlantı ayarları değişti. Görünümü yenileyip tekrar deneyin.",
  legacy_ssh_confirmation_required: "Eski SSH algoritmalarını etkinleştirmek için cihaz bazında açık onay gerekli.",
  ssh_algorithms_incompatible: "Cihaz ile SSH algoritmaları uyuşmuyor. Bağlantı bilgileri bölümündeki Eski VRP profilini değerlendirin.",
  collector_not_huawei_vrp: "Bağlanılan cihazın Huawei VRP sürüm çıktısı doğrulanamadı. Veri kaynağı seçimini kontrol edin.",
  collector_not_cisco_2960x: "Bağlanılan cihazın Cisco Catalyst 2960-X IOS çıktısı doğrulanamadı. Veri kaynağı seçimini kontrol edin.",
  collector_parse_failed: "Cihazın arayüz çıktısı tanınamadı. Son envanter korundu; cihaz sürümünü ve salt okunur komut yetkilerini kontrol edin.",
  collector_command_unsupported: "Veri toplama için gereken salt okunur komut bu cihazda desteklenmiyor.",
  collector_permission_denied: "Cihaz kullanıcısının gerekli salt okunur komutu çalıştırma yetkisi yok.",
  collector_timeout: "Veri toplama zaman aşımına uğradı; son envanter korundu.",
  collector_disconnected: "Veri toplama sırasında SSH oturumu kesildi; son envanter korundu.",
  collector_output_limit: "Cihaz çıktısı güvenli veri toplama boyut sınırını aştı; son envanter korundu.",
  terminal_already_open:
    "Bu cihaz için zaten açık bir terminal oturumunuz var.",
  terminal_limit: "Eşzamanlı terminal sınırına ulaşıldı.",
  authentication_failed: "Cihazda SSH kimlik doğrulaması başarısız.",
  invalid_private_key: "Özel anahtar veya anahtar parolası geçersiz.",
  connection_timeout: "SSH bağlantısı zaman aşımına uğradı.",
  connection_failed: "SSH bağlantısı kurulamadı.",
  external_collector_required:
    "Bu cihaz harici toplayıcıdan veri alır. Yenile, son alınan gözlemleri getirir.",
  collector_busy:
    "Veri toplama işlemleri meşgul. Kısa süre sonra tekrar deneyin.",
  validation_error: "Alanları ve veri biçimini kontrol edin.",
  unknown_interface_id:
    "Gözlemdeki arayüz kimliği cihaz envanterinde bulunmuyor.",
  out_of_order_observation: "Bu gözlem son kayıttan daha yeni olmalı.",
  out_of_order_inventory: "Envanter zamanı son kayıttan daha yeni olmalı.",
  csrf_failed: "Oturum doğrulaması başarısız; sayfayı yenileyin.",
  origin_denied: "Bu uygulama adresinden erişime izin verilmiyor.",
};
export function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? (messages[error.code] ?? `İşlem tamamlanamadı (${error.code}).`)
    : "İşlem tamamlanamadı. Bağlantıyı kontrol edip yeniden deneyin.";
}
