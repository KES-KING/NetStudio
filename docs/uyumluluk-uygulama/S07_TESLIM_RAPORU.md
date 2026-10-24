# S07 teslim raporu — P2 Dell, Extreme ve FortiSwitch standalone

| Alan | Sonuç |
|---|---|
| Sprint | S07 — P2: Dell, Extreme ve FortiSwitch standalone |
| Tarih | 24 Ekim 2026 |
| Tamamlanan backlog | S07-01–S07-08; kod/fixture/UI sözleşmesi |
| Migration etkisi | Yok; cihaz, secret, host key, inventory, telemetry ve job kayıtları korunur |
| Profil revizyonu | Yedi P2 profilinde `2` |
| Katalog / driver revizyonu | `2026.10.24.2` |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — katalog seçenekleri genişledi; ana yerleşim, tema ve kabuk değişmedi |

## 1. Teslim edilen iş paketleri

| ID | Durum | Kaynak sonucu |
|---|---|---|
| S07-01 | Tamamlandı | `dell_os10` ayrı manifest, kimlik ve interface grameri kullanır; OS9 komutlarına düşmez. |
| S07-02 | Tamamlandı | `dell_os9` OS9/FTOS banner'ını zorunlu tutar. `dell_force10` runtime kimliği, secret ve host key değiştirilmeden kanonik profile çözülür. |
| S07-03 | Tamamlandı | `dell_os6` N-series komutları, fixture'ı ve parser sınırı OS9/OS10'dan ayrıdır. |
| S07-04 | Tamamlandı | `extreme_exos`, `ExtremeXOS` ve `Switch Engine` OS adlarını açık alias metadata'sı olarak taşır. |
| S07-05 | Tamamlandı | `extreme_fabric_engine`, `Fabric Engine`/`VOSS` kimliğini doğrular; `extreme_vsp` geçişi koşulludur ve secure mode SNMP kısıtı görünürdür. |
| S07-06 | Tamamlandı | `extreme_slxos` ayrı manifest/fixture/gramer kullanır; EXOS/VOSS fallback'i yoktur. |
| S07-07 | Tamamlandı | Standalone `fortinet_fortiswitchos`, FortiLink-managed switch ve FortiGate/FortiOS'tan fail-closed ayrılır; `fortinet` otomatik alias değildir. |
| S07-08 | Tamamlandı | Ortak SNMPv3 capability'si, katalog/API/UI seçilebilirliği, yedi SHA-256 sabitli fixture ve negatif testler eklendi. |

## 2. Uygulanan transport ve veri kapsamı

Yedi profil `ssh=implemented`, `snmp=implemented` durumundadır. SSH manifestleri
profil bazında identity, interface, 64-bit sayaç, VLAN, FDB, ARP ve LLDP
alanlarını yayımlar. Ortak SNMPv3 çekirdeği system, IF/IF-X, Q-BRIDGE, LLDP ve
sınırlı ENTITY alanlarını sağlar. S07 SSH sözleşmesi fan/PSU/PoE/DOM alanı
uydurmaz.

S07 teslim anında FortiSwitch API transportu ADR-COMPAT-004 beklediği için
`blocked` idi. S08 sonrasında standalone vendor API `planned`, FortiLink-managed
profil ise ayrı controller API runtime'ıyla `experimental` durumundadır. Fabric Engine SSH secure mode
gözlemi `snmp=blocked_by_ssh_secure_mode` transport kısıtı olarak kaydedilir;
uygulama cihaz yapılandırmasını değiştirmez.

## 3. Kimlik ve alias güvenlik sınırları

- Aynı model metni Dell OS10, OS9 ve Enterprise SONiC banner'larıyla ayrı
  sonuçlandırılır. SONiC tanınır fakat uygulanmamış `dell_sonic` profile kapalıdır.
- `dell_force10` yalnız OS9/FTOS kanıtıyla, `extreme_vsp` yalnız Fabric
  Engine/VOSS kanıtıyla kanonik binding'e dönüşür. Dönüşüm şifreli sır, host key,
  cihaz kimliği veya last-good veriyi yeniden yazmaz.
- EXOS, Fabric Engine ve SLX-OS komut aileleri birbirine fallback yapmaz.
- Standalone FortiSwitchOS, FortiLink-managed FortiSwitch ve FortiOS ayrı kimlik
  sonuçlarıdır. Eski `fortinet` kaydı `manual_resolution_required` kalır.
- Yapılandırılmış ve gözlenen profil çelişirse collection sonucu
  `collector_platform_mismatch` olur ve yanlış parser sonucu kalıcılaştırılmaz.

## 4. Fixture ve negatif doğrulama

`backend/tests/fixtures/p2/manifest.json`, yedi proje-sentetik fixture'ın
SHA-256 özetini ve `physical_acceptance=false` /
`production_accepted=false` sınırını taşır. Fixture'lar exact model+sürüm,
farklı stack/slot port adları, `2^32` üstü sayaçlar, VLAN, FDB+ARP korelasyonu,
LLDP ve inventory sözleşmesini doğrular.

Negatif testler şunları kapsar:

- yedi profilde zorunlu interface komutunun timeout/yetki reddi,
- bozuk zorunlu interface çıktısında mevcut inventory'nin korunması,
- aynı model metninde yanlış Dell OS seçiminin engellenmesi,
- Dell Enterprise SONiC'in OS9/OS10'a düşmemesi,
- EXOS/Fabric Engine/SLX kimlik ve komut ayrımı,
- Fabric Engine secure mode SNMP kısıtı,
- standalone FortiSwitchOS/FortiLink/FortiOS ayrımı,
- stack/slot/colon interface adlarının korunması,
- fan/PSU/PoE sağlık alanlarının uydurulmaması,
- legacy alias çözümünde secret ve host key'in korunması,
- katalog/API/UI seçilebilirliği; FortiLink'in kapalı kalması.

## 5. Doğrulama sonucu

| Kontrol | Sonuç |
|---|---|
| S07 parser/fixture paketi | `38 passed` |
| Registry + API + migration/yönetişim odak paketi | `31 passed, 1 skipped` |
| `.venv/bin/pytest -q backend/tests` | `334 passed, 3 skipped`; dependency deprecation uyarıları dışında PASS |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm test -- --run` | 11 dosya, `63 passed` |
| `npm run build` | PASS; Next.js production build |
| `.venv/bin/python -m compileall -q backend/app backend/tests` | PASS |
| `docker compose --env-file .env.example config --quiet` | PASS |
| Fixture bounded hassas-terim taraması | Eşleşme yok; CI secret scanner kanıtı değildir |
| `git diff --check` | PASS |

Üç skip yalnız ayrı, boş ve loopback PostgreSQL test veritabanı isteyen migration
kanıtlarıdır. Mevcut veritabanı veya çalışan Docker servisi değiştirilmedi.
Playwright katalog sözleşmesi S07 seçenekleriyle genişletildi ve lint/typecheck/
build içinde derlendi; bu teslimde izole `NETSTUDIO_QA` browser ortamı
başlatılmadığı için E2E spec'i canlı çalıştırılmadı.

## 6. Açık kabul kapıları ve rollback

Kaynak ve sentetik fixture doğrulaması fiziksel Dell, Extreme veya FortiSwitch
kanıtı değildir. Gerçek cihaz output varyantları, SSH RBAC, SNMPv3 davranışı,
Fabric secure-mode kombinasyonları, stack/virtual-chassis port kimliği, büyük
FDB/ARP tabloları ve performans S11 exact-tuple kabulünde sınanmalıdır. Bu
kapılar geçilmeden profiller `experimental`, acceptance kayıtları
`production_accepted=false` kalır. Kapasite iddiası `REQUIRES BENCHMARK`tır.

Bu sprint migration eklemez. Kod rollback'i cihaz kayıtlarını, sırları, host
key'leri veya last-good gözlemleri dönüştürmez. Profil/katalog revizyonu değiştiği
için eski kabul tuple'ları otomatik geçerli sayılmaz.
