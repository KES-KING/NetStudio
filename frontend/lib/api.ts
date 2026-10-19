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
  window.dispatchEvent(new CustomEvent("stocc-session-expired", { detail: { message } }));
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
      window.dispatchEvent(new Event("stocc-session-expired"));
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
  topology_version_conflict: "Yerleşim başka bir sekmede değişti. Taslağınız korunuyor; güncel yerleşimi yükleyip değişikliklerinizi yeniden uygulayın.",
  topology_reference_unavailable: "Bir cihaz veya port artık erişilebilir değil. Gözlemleri yenileyip bu bağlantıyı kaldırın.",
  username_taken: "Bu kullanıcı adı zaten kullanımda.",
  user_not_found: "Kullanıcı bulunamadı; listeyi yenileyin.",
  last_superadmin: "Son aktif superadmin kaldırılamaz veya yetkisi düşürülemez.",
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
    "Bu yönetim adresi sunucunun izin verilen SSH ağları kapsamında değil.",
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
