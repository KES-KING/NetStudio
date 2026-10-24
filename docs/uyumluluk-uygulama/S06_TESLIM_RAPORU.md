# S06 teslim raporu — P1 yaygın kurumsal platformlar

| Alan | Sonuç |
|---|---|
| Sprint | S06 — P1: Yaygın kurumsal platformlar |
| Tarih | 24 Ekim 2026 |
| Tamamlanan backlog | S06-01–S06-07; kod/fixture/UI sözleşmesi |
| Migration etkisi | Yok; mevcut cihaz, secret, host key, inventory, telemetry ve job tabloları korunur |
| Profil revizyonu | Altı P1 profilinde `2` |
| Katalog / driver revizyonu | `2026.10.24.1` |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — katalogdan türeyen seçenekler genişledi; ana yerleşim, tema ve kabuk değişmedi |

## 1. Teslim edilen iş paketleri

| ID | Durum | Kaynak sonucu |
|---|---|---|
| S06-01 | Tamamlandı | `aruba_aoscx` ayrı manifest ve JSON CLI parser'ı kullanır; AOS-Switch text gramerine veya REST'e düşmez. |
| S06-02 | Tamamlandı | `aruba_aoss` runtime uyumluluk ID'si `hp_procurve` olarak korunur. Toplama kimliği kanonik profile çözer; test secret, host key ve cihaz kimliğinin korunmasını doğrular. |
| S06-03 | Tamamlandı | EOS yapılandırılmış JSON çıktısı SSH üzerinden ayrıştırılır. eAPI seçilmedi; API transportu ADR-COMPAT-004 ile `blocked` kalır. |
| S06-04 | Tamamlandı | HPE Comware ayrı vendor kimliği, runtime ID, fixture ve acceptance tuple'ı taşır. |
| S06-05 | Tamamlandı | H3C Comware V7 ayrı profildir; V5/V9 banner'ı ayrı catalog-only profile tanınır ve V7 parser'ı çalıştırılmaz. |
| S06-06 | Tamamlandı | RouterOS yalnız `/... print` allowlist'i ve key/value parser'ı kullanır; Cisco parser çağrısı negatif testle yasaklanmıştır. |
| S06-07 | Tamamlandı | Altı SHA-256 sabitli exact-tuple fixture, bağımsız catalog durumu, API cihaz oluşturma ve katalog-tabanlı UI seçilebilirlik testi eklendi. |

## 2. Uygulanan veri ve transport kapsamı

Altı profil `ssh=implemented`, `snmp=implemented` durumundadır. Ortak SNMPv3
çekirdeği system, IF/IF-X, Q-BRIDGE FDB/VLAN, LLDP ve sınırlı ENTITY alanlarını
sağlar. SSH manifestleri profil bazında interface, 64-bit sayaç, identity,
VLAN/FDB/ARP/LLDP ve yalnız açıkça eşlenen inventory/health alanlarını yayımlar.

Arista EOS ve RouterOS API; AOS-CX REST bu sprintte uygulanmamıştır. API secret,
TLS/CA, scope veya endpoint modeli eklenmedi. Bunun sonucu CLI/SNMP çalışırken
API transportunun kapalı görünmesi tasarlanmış davranıştır.

## 3. Fixture ve doğrulama sınırı

`backend/tests/fixtures/p1/manifest.json`, altı proje-sentetik dosyanın SHA-256
özetini, izin/sanitization sınıfını, capability kapsamını ve
`physical_acceptance=false` / `production_accepted=false` sınırını taşır.
Fixture'lar her profilde exact model+sürüm, kimlik, bir fiziksel interface,
`2^32` üstü RX/TX sayaçları, VLAN, FDB+ARP korelasyonu, LLDP ve inventory
çıktısını doğrular.

Negatif testler şunları kapsar:

- altı profilde bozuk zorunlu interface çıktısının `collector_parse_failed`
  olması ve mevcut inventory'yi değiştirmemesi,
- zorunlu komut için yetki reddi ve timeout'un ayrı diagnostics üretmesi,
- AOS-CX/AOS-Switch parser ayrımı,
- HPE/H3C marka çelişkisi ile H3C V5/V9 fail-closed davranışı,
- RouterOS'un Cisco parser'ına yönlenmemesi,
- `hp_procurve` alias çözümünde secret ve host key'in korunması,
- altı profil için bağımsız katalog seçilebilirliği.

## 4. Doğrulama sonucu

| Kontrol | Sonuç |
|---|---|
| `.venv/bin/pytest -q backend/tests` | `296 passed, 3 skipped`; dependency deprecation uyarıları dışında PASS |
| S06 + registry + yönetişim odak paketi | `47 passed` |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm test -- --run` | 11 dosya, `63 passed` |
| `npm run build` | PASS; Next.js production build |
| `python -m compileall -q backend/app backend/tests` | PASS |
| `docker compose --env-file .env.example config --quiet` | PASS |
| Fixture bounded hassas-terim taraması | Eşleşme yok; CI secret scanner kanıtı değildir |
| `git diff --check` | PASS |

Üç skip yalnız ayrı, boş ve loopback PostgreSQL test veritabanı isteyen migration
kanıtlarıdır; mevcut bir veritabanı veya çalışan Docker servisi değiştirilmedi.
Güncellenen Playwright UI sözleşmesi lint/typecheck/build içinde derlendi; bu
teslimde izole `NETSTUDIO_QA` browser ortamı başlatılmadığı için E2E spec'i canlı
çalıştırılmadı.

## 5. Açık kabul kapıları

Kaynak ve sentetik fixture doğrulaması tamamlanmıştır; fiziksel Aruba, Arista,
HPE, H3C veya MikroTik cihazına bağlanılmamıştır. Dolayısıyla bütün profiller
`fixture_verified/experimental`, acceptance kayıtları `production_accepted=false`
kalır. Gerçek cihaz çıktı varyantları, SSH RBAC davranışı, standard MIB kapsamı,
büyük FDB/ARP tabloları ve performans `S11` fiziksel tuple kabulünde ayrı
kanıtlanmalıdır. Kapasite iddiası `REQUIRES BENCHMARK`tır.

Rollback için migration yoktur. Profil ve katalog revizyonu eski acceptance
tuple'larının otomatik geçerli sayılmasını engeller. Kod rollback'i cihaz
kayıtlarının, sırların veya önceki last-good gözlemlerin dönüştürülmesini
gerektirmez.
