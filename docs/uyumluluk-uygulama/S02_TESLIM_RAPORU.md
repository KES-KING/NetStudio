# S02 teslim raporu — additive veri modeli, profil çözümü ve API geçişi

| Alan | Sonuç |
|---|---|
| Sprint | S02 — Additive veri modeli, profil çözümü ve API geçişi |
| Tarih | 23 Ekim 2026 |
| Başlangıç kaynak commit | `f13ad30f94a3d322d8e964df1fdfb568f2847773` |
| Tamamlanan backlog | S02-01–S02-09 |
| Migration etkisi | Additive `0010_driver_acceptance`; mevcut payload/sır/envanter/telemetri/job/probe satırları yeniden yazılmaz |
| Yeni cihaz desteği | Yok; profil binding'i veya kabul kaydı yeni parser/transport desteği değildir |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI; S02 kapsamı değil |
| Benchmark | `REQUIRES BENCHMARK` |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — backend/API/migration ve additive frontend tip değişikliği |

## 1. İş paketi teslimleri

| ID | Durum | Uygulama/kanıt |
|---|---|---|
| S02-01 | Tamamlandı | Alembic head `0009_probe_auto_enroll` doğrulandı; kısa revision kimlikli `0010_driver_acceptance` eklendi |
| S02-02 | Tamamlandı | Migration yalnız `devices.payload` okur; cihaz/sır/host key/job/telemetri/probe kayıtlarını değiştirmeden binding backfill eder |
| S02-03 | Tamamlandı | `fortinet` ve kimlik kanıtı bulunmayan `dell_force10`/`extreme_vsp`/`huawei_vrp`, `manual_resolution_required` kalır |
| S02-04 | Tamamlandı | Device create/update/read sözleşmesine `configured_profile_id`, `resolved_profile_id`, `profile_revision`, `management_mode` ve çözüm durumu additive eklendi; `collector` korunur |
| S02-05 | Tamamlandı | [`profile_resolution.py`](../../backend/app/profile_resolution.py) typed evidence, confidence, conflict ve fail-closed auto/alias çözümlemesini uygular |
| S02-06 | Tamamlandı | Profil değişimi `connection_revision` artırır, SSH/capability cache'ini temizler, açık terminali kapatır ve eski queued/running işlerin yazmasını engeller |
| S02-07 | Tamamlandı | Acceptance kayıtlarının katalog özeti ve superadmin salt-okuma modeli yalnız redakte alanları yayımlar; evidence path/reviewer/sır yoktur |
| S02-08 | Tamamlandı | Site kontrollü `GET /api/v1/devices/{id}/compatibility` ve inventory-manage kontrollü `PUT /api/v1/devices/{id}/driver-profile` eklendi |
| S02-09 | Tamamlandı | Manuel profil değişimi, collector çözümü ve güvenilir release-process acceptance kaydı structured audit üretir |

## 2. Kalıcı veri sözleşmesi

`0010_driver_acceptance` aşağıdaki tabloları ekler:

- `device_driver_bindings`: configured/resolved profil, profil revizyonu,
  management mode, çözüm durumu/confidence/çelişki ve redakte kimlik özeti;
- `device_capability_observations_v2`: profil + revision + transport + capability
  bağı, typed durum/reason, expiry ve SHA-256 evidence digest;
- `driver_acceptance_records`: kaynak commit + profil/revision + vendor + model
  ailesi + exact model + hardware revision + OS ailesi/sürümü + mode +
  transport/security profile + capability + parser/test suite revizyonu kabul
  tuple'ı, validation seviyesi, gözlem/kayıt/sona erme zamanı ve değişmez kanıt
  referansı/hash'i.

Yeni profil alanları `devices.payload` içine yazılmaz. API okuma modeli binding
tablosunu payload'a additive olarak birleştirir. Böylece önceki S01 imajı yeni
tabloları görmezden gelerek eski `collector` payload'ını okumaya devam eder.

Başarılı collector/parser sonucu `resolved_profile_id` değerini ve redakte kimlik
özetini günceller. Capability kaydı ham CLI/SNMP çıktısı içermez; yalnız typed
durum, güvenli reason code, zaman, expiry ve digest saklar.

## 3. API ve yetki sınırları

- Eski create/update payload'ları kanonik alan göndermeden çalışır.
- Kanonik profil ile açıkça çelişen legacy `collector`, `409
  driver_profile_collector_conflict` ile reddedilir.
- S02 veri modeli katalog-only binding'i temsil edebilir. S03 seçim kapısı yeni
  cihaz/profil değişiminde bu profili reddeder; S03 öncesi kayıtlar okunabilir ve
  profil değiştirmeyen bağlantı bakımı için geriye uyumlu kalır.
- Uyumluluk okuması cihazın site kapsamını kullanır. Profil değişimi
  `inventory.manage` ister.
- `identity_evidence`, `validation_level` veya `acceptance` HTTP yazma alanı
  değildir; strict request modeli bunları reddeder.
- `GET /api/v1/driver-acceptance` yalnız superadmin içindir ve `evidence_ref`,
  `reviewed_by`, IP, seri, kullanıcı adı ya da secret yayımlamaz.
- Acceptance yazımı için browser endpoint'i yoktur; yalnız güvenilir release
  süreci için internal, typed kayıt fonksiyonu vardır.
- Cihaz/katalog kabul eşleşmesi güncel kaynak commit ve parser sürümünü ister;
  exact model/OS/hardware revision veya management mode uyuşmazsa fail-closed
  davranır. `unknown` management mode joker değildir.
- Fiziksel kayıt `production_accepted` değerini hiçbir zaman kendiliğinden
  `true` yapmaz.

## 4. Migration ve rollback kanıtı

Disposable PostgreSQL 16 üzerinde tek zincirde aşağıdaki sınırlar sınandı:

1. `0001_initial`: minimal gerçek cihaz ve job oluşturuldu.
2. `0006_collection_automation`: aynı cihaza payload, SSH ciphertext, host key,
   SNMP ciphertext ve collection group eklendi.
3. `0009_probe_auto_enroll`: probe-agent kaydı eklendi.
4. `head`: `0010_driver_acceptance` uygulandı; bütün korunan satırlar migration
   öncesi/sonrası serialize değer eşitliğiyle doğrulandı ve legacy binding oluştu.

Uygulama rollback smoke testinde S01 commit'i `f13ad30` kaynak ağacı aynı
migrated PostgreSQL üzerinde başlatıldı; cihaz listeleme/okuma başarılı oldu ve
additive binding tablosu yerinde kaldı. Volume, tablo veya sır silinmedi. Ayrıca
SQLite disposable migration testinde yalnız S02 tablolarının açık downgrade'i
ve eski kayıtların değişmeden kalması doğrulanır. Üretim rollback yöntemi
downgrade değil, worker'ı durdurup önceki imajı additive tablolar yerindeyken
çalıştırmaktır.

## 5. Doğrulama

| Kontrol | Sonuç |
|---|---|
| Backend tam paket | `247 passed, 3 skipped`; 14 bağımlılık/deprecation uyarısı |
| S02 hedefli testler | `14 passed, 1 skipped` normal tur; skip olan PostgreSQL testi ayrı çalıştırıldı |
| Disposable PostgreSQL full migration | PASS; `0001 → 0006 → 0009 → 0010` ve veri eşitliği |
| Önceki S01 imajı rollback smoke | PASS; cihaz okuma/listeleme, additive tablo yerinde |
| Frontend unit | 11 dosya / 60 test PASS |
| Frontend lint | PASS |
| Frontend typecheck | PASS |
| Frontend production build | PASS; 12 route üretildi |
| Compose config | PASS |
| Alembic head | `0010_driver_acceptance` |
| Python compile / whitespace | PASS |

Normal backend turundaki üç skip, ayrı boş PostgreSQL isteyen S02 compatibility,
mevcut user migration ve automation locking testleridir. S02 compatibility testi
bu teslimde disposable PostgreSQL üzerinde ayrıca geçti. Uyarılar mevcut
Starlette/httpx, AsyncSSH/cryptography FFDH ve Alembic yapılandırma deprecation
uyarılarıdır.

## 6. Kalan sınırlar

- S03 katalog tabanlı cihaz formu ve görünür Uyumluluk panelini henüz eklememiştir;
  S02 API'si ve TypeScript device alanları hazırdır.
- Acceptance tablosu boş başlar. Fixture/lab sonucu otomatik olarak
  `physical_validated`, `supported` veya `production_accepted` üretmez.
- Gerçek switch, controller/cloud API, fiziksel kabul ve production rollout
  çalıştırılmadı.
- Kapasite/SLA beyanı yoktur: `REQUIRES BENCHMARK`.
