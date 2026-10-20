export type UpdateCommit = { sha: string; title: string; description: string; author: string; committed_at: string; url: string };
export type UpdateRun = { id: string; revision: string; status: string; error_code: string | null; automatic: boolean; created_at: string; updated_at: string };
export type UpdateState = { repository: string; repository_url: string; branch: string; installed_revision: string | null; latest_revision: string | null;
  available: boolean; automatic: boolean; can_manage: boolean; agent_online: boolean; maintenance: boolean; recovery_required: boolean;
  checked_at: string | null; next_check_at: string | null; error_code: string | null; commits: UpdateCommit[]; runs: UpdateRun[] };
export const updatePhases: Record<string, string> = { queued: "Sırada", building: "İndiriliyor / derleniyor", draining: "Oturumlar bekleniyor",
  backing_up: "Yedek alınıyor", migrating: "Veritabanı hazırlanıyor", deploying: "Kuruluyor", verifying: "Sağlık kontrolü",
  succeeded: "Kuruldu", failed: "Başarısız", recovery_required: "Kurtarma gerekiyor", cancelled: "İptal edildi" };
export const updateErrors: Record<string, string> = {
  github_unavailable: "GitHub kontrolü tamamlanamadı. Son başarılı kayıtlar korunuyor.", github_rate_limited: "GitHub hız sınırına ulaşıldı; belirtilen zamandan önce tekrar istek gönderilmez.",
  update_agent_unavailable: "Sunucu güncelleyicisi bağlı değil. Önce host kurulumunu tamamlayın.", update_revision_unknown: "Kurulu commit doğrulanamadı. Sürüm etiketli imajlar gerekir.",
  update_recovery_required: "Önceki kurulum için sunucuda kurtarma gerekiyor; otomatik kurulum durdu.", update_check_required: "Önce güncel GitHub kontrolü gerekir.",
  update_revision_changed: "Yeni commit değişti. Listeyi yenileyip yeniden onaylayın.", update_confirmation_required: "Kurulum etkisini onaylayın.",
  sessions_busy: "Açık oturum veya işler bitmedi; kurulum yapılmadı.", deployment_contract_changed: "Dağıtım sözleşmesi değişmiş; sunucuda elle geçiş gerekiyor.",
  revision_not_forward: "Commit mevcut sürümün ileri güncellemesi değil.", installation_failed: "Kurulum tamamlanamadı. Sunucudaki güncelleyici durumunu kontrol edin.",
  update_actor_revoked: "Hesabın yetkisi veya otomatik kurulum izni kaldırılmış.", agent_interrupted: "Güncelleyici kesintiye uğradı; sunucuda durum kontrolü gerekiyor.",
};
