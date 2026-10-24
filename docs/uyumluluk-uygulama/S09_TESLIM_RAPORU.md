# S09 teslim raporu — ileri, legacy ve Linux tabanlı NOS profilleri

| Alan | Sonuç |
|---|---|
| Sprint | S09 — P3: İleri, legacy ve Linux tabanlı NOS profilleri |
| Tarih | 24 Ekim 2026 |
| Tamamlanan backlog | S09-01–S09-10; manifest, parser, fixture, katalog/API/UI sözleşmesi |
| Migration etkisi | Yok; cihaz, secret, host key, inventory, telemetry ve job kayıtları korunur |
| Profil revizyonu | Dokuz P3 profilinde `2` |
| Katalog / driver revizyonu | `2026.10.24.4` |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — katalog seçenekleri genişledi; ana yerleşim, tema ve kabuk değişmedi |

## 1. Teslim edilen iş paketleri

| ID | Durum | Kaynak sonucu |
|---|---|---|
| S09-01 | Tamamlandı | `h3c_comware5` bağımsız manifest/gramer kullanır; eski SSH fallback'i yalnız cihaz opt-in'iyle açılır. |
| S09-02 | Tamamlandı | `h3c_comware9`, V7 command planı, parser adı ve fixture kanıtından ayrıdır. |
| S09-03 | Tamamlandı | `huawei_vrp_v600`, `huawei_vrp`/V200 alias-parser yoluna düşmez. |
| S09-04 | Tamamlandı | `juniper_junos_evolved`, klasik Junos'tan ayrı Evolved kimliği, XML/no-more planı ve fixture taşır. |
| S09-05 | Tamamlandı | Dell Enterprise SONiC için Dell distribution+version+platform kanıtı zorunludur; genel SONiC ayrı kalır. |
| S09-06 | Tamamlandı | Cumulus NVUE JSON parser'ı ve kernel/front-panel/breakout ayrımı uygulandı; `linux_ssh` altyapı adapter'ı olarak kaldı. |
| S09-07 | Tamamlandı | NVIDIA Onyx, Cumulus NVUE komutlarından ve kimliğinden bağımsızdır. |
| S09-08 | Tamamlandı | Genel SONiC distribution+image olmadan runtime açmaz; vendor `Unknown` kalır. |
| S09-09 | Tamamlandı | Cisco Business exact CBS+firmware kimliği kullanır; IOS/Meraki komut planına düşmez. |
| S09-10 | Tamamlandı | Dokuz SHA-256 sabitli fixture, cross-profile mismatch, permission/timeout, bozuk çıktı ve katalog/API testleri eklendi. |

## 2. Uygulanan sınırlar

Dokuz profil `ssh=implemented`, `fixture_verified`, `experimental` durumundadır.
Comware, VRP V600, Junos Evolved, Cumulus, Onyx ve Cisco Business profilleri
ortak bounded standard-MIB çekirdeği üzerinden SNMPv3 `authPriv` ilan eder.
Cisco Business için exact model/firmware karar kapısı görünürdür. Dell ve genel
SONiC'te dağıtım-bazlı SNMP sözleşmesi kanıtlanmadığından SNMP `planned` kalır;
API adapter'ları da uygulanmamıştır.

SSH manifestleri yalnız salt-okunur allowlist komutlarını çalıştırır. Kimlik,
interface, 64-bit sayaç, VLAN, FDB, ARP ve LLDP dönüşümü proje-sentetik fixture
kapsamında doğrulanmıştır. Ham çıktı kalıcılaştırılmaz. Eksik sağlık/optik/PoE,
FRR veya vendor-specific SONiC alanı destekleniyormuş gibi gösterilmez.

## 3. Veri doğruluğu ve yanlış eşleşme

- Cumulus `swp` interface, front-panel port ve breakout child üç ayrı kimliktir.
  Bond, bridge ve VRF fiziksel port değildir.
- Dell SONiC ve genel SONiC, distribution/image kanıtlarıyla ayrılır. Genel
  SONiC vendor'ı model metninden tahmin edilmez.
- V5/V7/V9 Comware; V200/V600 VRP; Junos/Junos Evolved; Dell/community SONiC;
  Cumulus/Onyx ve Cisco IOS/Cisco Business arasında parser fallback'i yoktur.
- Yapılandırılmış profil farklı bir implemented kimlik görürse
  `collector_platform_mismatch` ile durur. Zorunlu komut hatası son doğru
  inventory'yi değiştirmez.
- Comware V5 legacy SSH izni cihaz kapsamındadır; V600'e veya aynı vendor'daki
  başka profile taşınmaz.

## 4. Kanıt seviyesi ve açık kapılar

`backend/tests/fixtures/p3/manifest.json`, proje tarafından üretilmiş dokuz
sanitized fixture'ın hash'lerini taşır. Bunlar üretici transcript'i, transport
laboratuvarı veya fiziksel cihaz kanıtı değildir. Bu nedenle profiller
`supported` yapılmamış, acceptance `production_accepted=false` bırakılmıştır.

S11 öncesinde exact model/hardware revision/OS image, gerçek read-only RBAC,
SSH algoritmaları, SNMPv3, Cumulus ASIC/front-panel/breakout eşlemesi, SONiC
distribution varyantları, Junos Evolved multi-routing-engine çıktısı, büyük
FDB/ARP tabloları ve timeout/soak davranışı fiziksel cihazda doğrulanmalıdır.
Performans ve kapasite `REQUIRES BENCHMARK`tır.

## 5. Rollback ve tasarım etkisi

S09 migration eklemez ve mevcut cihaz/binding/secret/host-key/last-good veriyi
dönüştürmez. Kod rollback'i yeni P3 runtime seçimlerini katalogdan kaldırır;
kalıcı veriyi silme gerektirmez. Katalog seçenekleri dinamik API'den geldiği için
formda otomatik görünür. Ana kabuk veya sayfa tasarımı değişmediğinden README
ekran görüntüleri yenilenmemiştir.

## 6. Doğrulama özeti

| Kontrol | Sonuç |
|---|---|
| P3 odaklı backend sözleşmeleri | `45 passed` |
| Tam backend paketi | `399 passed, 3 skipped` |
| Frontend unit/component paketi | `63 passed` |
| Frontend lint / TypeScript | başarılı / başarılı |
| Production frontend build | başarılı; 12 route üretildi |
| İzole Docker Compose sağlık kontrolü | API, worker, probe-agent, web, gateway, updater, PostgreSQL ve SSH lab sağlıklı |
| Gerçek Chrome uyumluluk akışı | `3 passed`; katalog durumları, controller credential binding ve legacy migration/RBAC |
| Compose yapılandırması / Python bytecode / diff kontrolü | başarılı |

Tarayıcı kanıtı `netstudio-s09-qa-20261024` adlı, benzersiz port ve volume
adlarına sahip geçici projede üretildi. Test sonunda yalnız bu proje ve ona ait
geçici hacimler kaldırıldı; önceden çalışan S03 QA projesi sağlıklı kalmıştır.
Fixture ve izole tarayıcı kanıtının fiziksel/production kabule yükseltilmediği
sınır değişmez.
