# S11 teslim raporu — fiziksel kabul, performans, rollout ve destek yayını

| Alan | Sonuç |
|---|---|
| Sprint | S11 — Fiziksel kabul, performans, rollout ve destek yayını |
| Tarih | 24 Ekim 2026 |
| Kaynak commit | Teslim çalışma ağacı; commit/push yapılmadı |
| Katalog / parser revizyonu | `2026.10.24.6` / `2026.10.24.5` |
| Migration | `0012_release_acceptance` — iki additive tablo |
| Fiziksel cihaz kanıtı | **ÇALIŞTIRILMADI** — yetkili hedef verilmedi |
| Benchmark | **REQUIRES BENCHMARK** — gerçek 24 saat koşusu yapılmadı |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — mevcut Uyumluluk paneline koşullu karar ayrıntısı eklendi |

## 1. Backlog sonucu

| ID | Sonuç | Uygulanan/engellenen kapsam |
|---|---|---|
| S11-01 | Altyapı tamam, icra bloklu | Sırsız [`S11_LAB_SCOPE.json`](S11_LAB_SCOPE.json) eklendi; yetkili hedef listesi boş. |
| S11-02 | Tamamlandı | Strict bundle, fiziksel ve benchmark artifact SHA-256 doğrulaması, iki redaksiyon inceleyicisi ve Ed25519 imzası. |
| S11-03 | Otomasyon tamam, fiziksel icra bloklu | Exact tuple ve capability sonuçları kayıt/import kapısına bağlandı; gerçek cihaz çalıştırılmadı. |
| S11-04 | Otomasyon tamam, fiziksel icra bloklu | Transporta özgü negatif test kapıları zorunlu; reboot/firmware/hata senaryoları fiziksel hedefte çalıştırılmadı. |
| S11-05 | Yerel kanıt tamam, canlı tatbikat bloklu | Additive migration veri koruma testi ve mevcut worker/lease/last-good testleri; gerçek rollout rollback'i yapılmadı. |
| S11-06 | Harness tamam, sonuç açık | DB job/queue/veri snapshot komutu eklendi; dış CPU/RSS/IO/cihaz ölçümleri ve 24 saat soak yok. |
| S11-07 | Tamamlandı | 180/90 günlük expiry, commit/profile/parser bağı ve imzalı withdrawal fail-closed uygulanıp test edildi. |
| S11-08 | Tamamlandı | `experimental→candidate→supported` yalnız imzalı karar; dört rol review'u ve production ayrımı. |
| S11-09 | Tamamlandı | Operasyon rehberi, güncel destek yayını, API/UI karar görünümü ve bilinen sınırlar yayımlandı. |
| S11-10 | Mekanizma tamam, canlı rollout yok | Aşama atlama/gerileme engeli, `general` öncesi `candidate` tutma ve kalıcı hata bütçesi düşürmesi uygulandı; canlı aşama verisi yok. |

Sprintin kod/dokümantasyon altyapısı uygulanmıştır. Fiziksel cihaz ve 24 saat
benchmark gerektiren çıkış maddeleri dış girdiler olmadığı için kapatılamaz;
dolayısıyla sprint programının **fiziksel kabul çıkış kapısı geçilmemiştir**.

## 2. Kaynak değişiklikleri

- `release_acceptance.py`: strict karar/withdrawal/rollout sözleşmeleri, imza,
  hash, süre, exact tuple, benchmark ve hata bütçesi doğrulaması.
- `release_cli.py`: offline imza, doğrulama, trust-root kurulumu, import ve
  benchmark snapshot komutları.
- `release_schema_v1.py` + `0012_release_acceptance.py`: signed payload ve
  rollout gözlemi için additive tablolar.
- `profile_resolution.py` + `automation_api.py`: yalnız güvenilen güncel kararın
  katalog/cihaz görünümüne yansıması; withdrawal'da karar-kapsamlı tombstone son
  kayıt olarak kazanır, daha yeni başka kararın kanıtını düşürmez.
- `CompatibilityPanel.tsx`: imzalı exact vendor/model/hardware/OS/mode/transport
  scope'u, hash'i, expiry ve rollout durumunun koşullu görünümü.
- `docker-compose.yml`: normal kurulumdan ayrılmış `release-admin` profili ve
  public trust-root volume'ü; API bu volume'ü read-only kullanır.

## 3. Güvenlik sonucu

- HTTP üzerinden yayın/acceptance yazma endpoint'i yoktur.
- Private imza anahtarı container'a verilmez; CLI `0600` dosya modu ister.
- API kararı her katalog/uyumluluk okumasında güvenilen public key ile yeniden
  doğrular; payload/DB değişikliği imzayı bozar.
- Karar mevcut build SHA, katalog, profil revizyonu ve parser sürümüyle eşleşir.
- Fiziksel, benchmark ve rollout artifact dosyaları import anında SHA-256 ile
  doğrulanır; bütün fiziksel sonuçlar tek redakte kanıta bağlıdır. API artifact
  yolu, signature veya reviewer kimliğini döndürmez.
- Geleceğe tarihli karar/gözlem etkinleşmez; toleransı aşan kayıt importta
  reddedilir.
- Eksik/bozuk trust-root ve imza/payload/DB uyuşmazlığı katalog endpoint'ini
  bozmaz; dinamik desteği fail-closed kapatır.
- Supported için ilan edilen bütün capability'ler, negatif transport testleri,
  migration/E2E, worker restart/lease, last-good, verisiz rollback ve güncel 24
  saat benchmark zorunludur.
- Rollout ihlali aynı karar altında sonradan sağlıklı ölçümle silinmez.
- Fiziksel kabul production kabulüne dönüşmez.
- `release-admin` yalnız public trust-root volume'ünü yazan tek-seferlik UID 0
  süreçtir; capability'leri yoktur, root filesystem salt okunurdur ve keyring,
  private anahtar veya Docker socket görmez. Gerçek Compose import denemesiyle
  atomik trust-root kurulumu doğrulanmıştır.

## 4. Migration ve rollback etkisi

Migration mevcut tablolara kolon eklemez ve backfill yapmaz. Cihaz, SSH/SNMP/API
secret ciphertext, host key, binding, inventory, telemetry, job, probe,
controller ve eski acceptance kayıtları write set dışındadır. Normal rollback
eski uygulama imajı ve aynı volume'lerle yapılır; S11 tabloları bırakılır.

## 5. Doğrulama durumu

Doğrulamalar sentetik/izole ortamda yapılmıştır:

| Kontrol | Sonuç |
|---|---|
| S11 + katalog/yönetişim odaklı backend | `32 passed` |
| Tam backend | `418 passed, 3 skipped` |
| Frontend lint/typecheck/unit/build | başarılı / başarılı / `64 passed` / 12 route başarılı |
| Compose config | normal profilde `release-admin` yok; opt-in güvenlik alanları ve config başarılı |
| İzole PostgreSQL migration | `0012_release_acceptance` head ve iki tablo canlı PostgreSQL'de doğrulandı |
| Release CLI/volume | Public trust-root atomik kuruldu; sentetik snapshot doğru biçimde `REQUIRES BENCHMARK` kaldı; rollout artifact argümanı zorunlu |
| Gerçek Chrome | `/devices/{id} → Uyumluluk → İmzalı yayın kararı` dahil `5 passed` |
| Görsel/responsive | 1536×900 ve 390×844; yatay taşma ve kontrollü kanıt sızıntısı yok |
| Fiziksel cihaz | ÇALIŞTIRILMADI |
| 24 saat benchmark | REQUIRES BENCHMARK |

Chrome kanıtı yalnız loopback portları ve benzersiz volume'leri olan
`netstudio-s11-final-qa-20261024` projesinde `/usr/bin/google-chrome` ile üretildi.
Browser entegrasyonu bulunmadığı için repository Playwright fallback'i
kullanıldı. Test sonrası yalnız bu proje ve dört geçici volume kaldırıldı;
önceden çalışan `netstudio-s03-qa-native-20261023` servisleri sağlıklı kaldı.
Starlette/httpx, AsyncSSH FFDH, Alembic ve Vite mesajları mevcut bağımlılık
uyarılarıdır; başarısızlık üretmedi.

## 6. Destek kararı

İmzalı fiziksel bundle bulunmadığı için tüm uygulanmış profiller statik kanıt
seviyelerinde ve `experimental` kalır. `candidate=0`, `supported=0`,
`production_accepted=false`. Güncel yayımlanabilir kapsam
[`S11_DESTEK_YAYINI.md`](S11_DESTEK_YAYINI.md) içindedir.
