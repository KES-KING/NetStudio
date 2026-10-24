# NetStudio sürücü kabul ve kanıt şablonu

| Alan | Değer |
|---|---|
| Şablon kimliği | `NETSTUDIO-COMPAT-ACCEPT-001` |
| Kullanım | Profil/capability implementasyonu, laboratuvar ve fiziksel cihaz kabulü |
| Bağlı plan | [Sprint planı](SPRINT_PLANI.md) |
| Bağlı kapsam | [Sürücü izlenebilirlik matrisi](SURUCU_IZLENEBILIRLIK_MATRISI.md) |
| Fixture politikası | [Fixture ve kanıt politikası](FIXTURE_VE_KANIT_POLITIKASI.md) |
| Yayın kapısı | [ADR-COMPAT-005](adr/ADR-COMPAT-005-fiziksel-kabul-ve-yayin-kapisi.md) |

> Bu dosya doldurulmadan önce kopyalanmalıdır. Şablonun varlığı kabul kanıtı
> değildir. Public repository'ye gerçek sır, yönetim IP'si, kullanıcı adı, host
> key, community, API token, müşteri adı, tam seri numarası veya ham terminal/API
> çıktısı konmamalıdır.

## 1. Kanıt paketi kuralları

### 1.1. Public repository'ye girebilenler

- Tamamen sentetik fixture,
- izinle alınmış ve iki kişi tarafından redaksiyonu incelenmiş sanitized fixture,
- beklenen typed JSON sonucu,
- test komutu ve pass/fail özeti,
- model ailesi ve OS sürümü (paylaşım izni varsa),
- evidence dosyalarının SHA-256 değeri,
- sır içermeyen hata kodları ve capability sonuçları.

### 1.2. Public repository'ye giremeyenler

- parola, private key, passphrase, SNMP community/auth/priv parolası,
- bearer/OAuth/API token veya cookie,
- private/kurumsal CA anahtarı,
- gerçek yönetim IP/hostname, kullanıcı adı veya müşteri/site adı,
- tam cihaz seri numarası, inventory asset tag ve hassas MAC/IP envanteri,
- SSH public host key/fingerprint (kurum politikası izin vermedikçe),
- ham running configuration veya ham terminal oturum kaydı,
- üçüncü taraf lisansına aykırı vendor çıktı/corpus'u.

Hassas kanıt gerekiyorsa erişimi kontrollü harici artefakt deposunda tutulur;
repository yalnız değişmez hash, redakte özet ve erişim sınıfını içerir.

## 2. Kabul kayıt üst bilgisi

Aşağıdaki tablo her test tuple'ı için doldurulur:

| Alan | Doldurulacak değer |
|---|---|
| Kayıt kimliği | `COMPAT-<profile>-<date>-<sequence>` |
| Test tarihi/saat dilimi | ISO 8601 |
| Kaynak commit | Tam Git SHA |
| Katalog revizyonu | `catalog_revision` |
| Profil kimliği/revizyonu | Örn. `cisco_ios@1` |
| Parser/template sürümü | Kod ve NTC sürümü |
| Üretici | Redakte edilmesi gerekmeyen marka |
| Model ailesi | Örn. `WS-C2960X`; izin yoksa sınıflandırılmış değer |
| Exact model | Paylaşım politikasına göre redakte |
| OS ailesi/exact sürümü | Kabul kapsamı için zorunlu |
| Management mode | `standalone/controller_managed/cloud_managed/...` |
| Transport | SSH / SNMPv3 / SNMPv2c / vendor API |
| Auth/security profile | Sır olmadan algoritma/security level özeti |
| Test ortamı | Fixture / izole lab / fiziksel lab / production acceptance |
| Test yetkisi | Yetki referansı; müşteri detayı yok |
| Kanıt sınıfı | Unit / fixture / transport lab / physical / benchmark |
| Sonuç | PASS / PARTIAL / FAIL / BLOCKED / NOT_RUN |
| Evidence ref + SHA-256 | Değişmez referans ve hash |
| İnceleyen | Kullanıcı/rol; imza yöntemi |
| Geçerlilik sonu | Politika gereği tarih veya “süresiz değil” |

## 3. Hazırlık kontrolü

- [ ] Test hedefi kullanıcı/kurum tarafından açıkça yetkilidir.
- [ ] Test ağı üretim/müşteri ağından gerekli ölçüde izoledir.
- [ ] Cihazın yedeği/geri dönüş sorumluluğu belirlenmiştir; NetStudio yazma yapmaz.
- [ ] Read-only SSH/SNMP/API hesabı ve minimum yetkiler hazırlanmıştır.
- [ ] SSH host key veya API TLS sertifikası bağımsız güvenilir kanaldan doğrulanmıştır.
- [ ] SNMPv3 authPriv kullanılmıştır; v2c ise ADR, feature flag ve risk onayı vardır.
- [ ] Cihaz üzerindeki erişim ACL/management VLAN/VRF sınırı doğrulanmıştır.
- [ ] Model, OS sürümü ve management mode bağımsız olarak kaydedilmiştir.
- [ ] Test komut/OID/API allowlist'i review edilmiştir.
- [ ] Ham çıktıların saklama/redaksiyon yöntemi belirlenmiştir.
- [ ] Cihaz CPU ve rate-limit izleme yöntemi hazırdır.

Hazırlık maddelerinden güvenlikle ilgili biri başarısızsa teste devam edilmez ve
sonuç `BLOCKED` yazılır.

## 4. Implementasyon ve fixture kabulü

### 4.1. Manifest/registry

- [ ] Kanonik profil ID'si tekil ve izlenebilirlik matrisinde var.
- [ ] Alias'lar döngüsüz; belirsiz eski ID otomatik yanlış profile çevrilmiyor.
- [ ] Vendor, OS family, version, model ve mode seçicileri açık.
- [ ] Transport ve capability durumları ayrı.
- [ ] `implemented` yalnız gerçek adapter/parser kayıtlıysa kullanılıyor.
- [ ] `supported` fiziksel acceptance kaydı olmadan üretilemiyor.
- [ ] Profil revizyonu komut/parser/capability değişikliğinde artmış.

### 4.2. Fixture

- [ ] Fixture exact model ve OS sürümüyle etiketli.
- [ ] Fixture kaynağı ve paylaşım yetkisi kaydedilmiş.
- [ ] Sırlar, kullanıcı/site/IP/seri/host key/müşteri verisi temizlenmiş.
- [ ] Redaksiyon parser semantiğini bozmayacak deterministik değerlerle yapılmış.
- [ ] Fixture içinde ANSI, pager, boş/kısmi/bozuk ve izin hatası örnekleri var.
- [ ] Beklenen typed çıktı ayrıca fixture olarak mevcut.
- [ ] Raw çıktı üretim loguna veya DB'ye yazılmıyor.
- [ ] Secret scanner ve manuel review sonucu PASS.

### 4.3. Parser negatifleri

| Senaryo | Beklenen sonuç | Gerçek sonuç | Durum |
|---|---|---|---|
| Zorunlu tablo boş | `parse_error`, eski envanter korunur |  |  |
| Opsiyonel komut unsupported | İlgili alan `unsupported`, diğer grup korunur |  |  |
| Permission denied | `permission_denied`, parola retry yok |  |  |
| Duplicate interface/port | Fail-closed, kimlik ezilmez |  |  |
| Bilinmeyen connector/module | `unknown`, model tahmini yok |  |  |
| Aşırı satır/byte | Bounded error/partial |  |  |
| Pager/redirect/pagination loop | Limit hatası |  |  |
| Malformed XML/JSON/entity | Güvenli parse_error; external entity yok |  |  |
| Eski job/revision | Sonuç yazamaz |  |  |

## 5. Transport laboratuvar kabulü

### 5.1. SSH

| Kontrol | Beklenti | Sonuç/kanıt |
|---|---|---|
| Kayıtlı hedef | Yalnız cihazın güncel yönetim IP/portu |  |
| Host key ilk güven | Açık kullanıcı onayı, credential öncesi keşif |  |
| Host key değişimi | Bağlantı durur; sessiz kabul yok |  |
| Yanlış parola | Tek auth yolu; legacy profil döngüsü yok |  |
| Legacy KEX | Yalnız cihaz bazlı izin ve audit |  |
| Komut allowlist | Bilinmeyen/serbest komut reddedilir |  |
| Deadline/byte/page | Bütün limitler uygulanır |  |
| Session revision | Ayar değişiminde bağlantı/job iptal olur |  |

### 5.2. SNMP

| Kontrol | Beklenti | Sonuç/kanıt |
|---|---|---|
| Security level | v3 authPriv; v2c yalnız onaylı P4 yolu |  |
| Context | Doğru context; uyuşmazlık typed hata |  |
| OID allowlist | Serbest OID veya SET yok |  |
| Request/row/time limit | 128/4096/deadline veya profilce daha sıkı |  |
| Artmayan OID | Fail-closed |  |
| ifName/ifIndex | Kalıcı ID'ye kanıtlı eşleme |  |
| Uptime/discontinuity | Counter epoch reset |  |
| Auth hatası | Redakte `snmp_authentication_failed` |  |
| Sır temizleme | Memory object temizlenir; API/logda yok |  |

### 5.3. Vendor/controller API

| Kontrol | Beklenti | Sonuç/kanıt |
|---|---|---|
| Controller hedefi | Kayıtlı/izinli URL; serbest SSRF yok |  |
| TLS | Sistem/kurum CA veya pin; verify kapatılamaz |  |
| Redirect/DNS | İzinli hedef dışına çıkmaz; metadata/link-local reddi |  |
| Token scope | Read-only ve site kapsamlı |  |
| Token lifecycle | Expired/revoked typed hata; sır sızıntısı yok |  |
| Rate limit | Bounded retry ve Retry-After üst sınırı |  |
| Pagination | Loop/byte/page limiti |  |
| Multi-site | Başka site verisi karışmaz |  |

## 6. Fiziksel cihaz capability kabulü

Her satır ayrı PASS/PARTIAL/FAIL/NOT_SUPPORTED/NOT_RUN sonucuna sahiptir.

| Capability | Test yöntemi | Beklenen doğruluk | Sonuç | Evidence |
|---|---|---|---|---|
| Sistem kimliği | CLI/SNMP/API çapraz kontrol | Vendor/OS/model/version/mode uyumlu |  |  |
| Uptime/reboot | Kontrollü gözlem/reboot | Epoch değişir; sahte rate yok |  |  |
| Arayüz envanteri | Cihaz çıktısı ile sayım | Mantıksal/fiziksel ayrımı; duplicate yok |  |  |
| Kalıcı arayüz ID | İki poll + restart | İsim değişimi/ifIndex değişimi kontrollü |  |  |
| Port connector | Açık CLI/MIB/API kanıtı | Kanıtsız değer `unknown` |  |  |
| Admin/oper state | Kontrollü port durumu | Null/unknown sıfır/up yapılmaz |  |  |
| Capacity/duplex | Cihaz karşılaştırması | Birim ve unknown doğru |  |  |
| 64-bit RX/TX | İki zamanlı örnek | Yön, interval, reset/wrap doğru |  |  |
| Error/discard | Sayaç karşılaştırması | RX/TX ayrımı korunur |  |  |
| VLAN/PVID/trunk | Cihaz tablosu | VLAN/FID/mode doğru; kısmi açık |  |  |
| FDB | MAC tablosu karşılaştırması | Bridge port→ifIndex doğru |  |  |
| ARP/NDP/VRF | L3 tablo karşılaştırması | FDB ile yanlış birleşme yok |  |  |
| LLDP | Komşu iki uç karşılaştırması | Chassis/port kanıtı; kablo tahmini yok |  |  |
| LAG | Üye/bundle karşılaştırması | Double-count yok |  |  |
| Stack/chassis/module | Fiziksel envanter | Yalnız gözlenen öğeler |  |  |
| Fan/PSU/temp | Cihaz sensörü | Sağlık eşiği uydurulmaz |  |  |
| PoE | Port/controller karşılaştırması | Watt/state yönü doğru |  |  |
| Transceiver/DOM | Modül tak/çıkar senaryosu | Port türü ile modül medyası ayrı |  |  |
| Partial failure | Bir opsiyonel yetki kapalı | Son doğru diğer alanlar korunur |  |  |
| Total failure | Bağlantı kesilir | Eski veri stale/error; silinmez |  |  |

### 6.1. Kimlik ve yeniden başlatma senaryosu

- [ ] İlk poll'da identity evidence kaydedildi.
- [ ] İkinci poll aynı profile/kalıcı ID'lere çözüldü.
- [ ] Worker restart sonrası duplicate cihaz/port/interface oluşmadı.
- [ ] Cihaz reboot sonrası uptime/counter epoch değişti.
- [ ] OS sürümü değişirse capability cache/profile resolution yenilendi.
- [ ] Yanlış profile elle geçiş identity conflict ile durdu.
- [ ] Başarısız refresh son iyi envanteri silmedi.

## 7. UI ve API kabulü

| Kontrol | Beklenti | Sonuç |
|---|---|---|
| Katalog | Backend ve frontend aynı kanonik ID/revizyonu gösterir |  |
| Planlı profil | Açıklamalı disabled; seçilemez |  |
| Deneysel profil | Fiziksel destek gibi görünmez |  |
| Acceptance scope | Yalnız exact/kapsanan tuple supported |  |
| Capability durumları | Partial/unsupported/error/timeout/stale ayrı |  |
| Secret readback | Parola/community/token alanları boş |  |
| RBAC/site | Yetkisiz cihaz 404/forbidden sözleşmesine uygun |  |
| Mobil taşma | Sayfa yatay taşmaz; uzun sürüm/hata kırılır |  |
| Klavye/ekran okuyucu | Label, focus, error summary ve durum metni var |  |
| Console | Framework/React/uncaught hata yok |  |

## 8. Migration ve rollback kabulü

- [ ] Migration güncel gerçek head üzerinden üretildi.
- [ ] Boş disposable PostgreSQL'de full upgrade geçti.
- [ ] Eski migration head'inden upgrade geçti.
- [ ] Mevcut cihaz payload hash'i beklenen additive alanlar dışında korundu.
- [ ] SSH/SNMP/API ciphertext byte'ları değişmedi.
- [ ] Host key, interface ID, physical port ID ve binding ID korundu.
- [ ] Job, telemetry, group ve history satırları korundu.
- [ ] Legacy alias doğru binding oluşturdu.
- [ ] Belirsiz alias otomatik profile taşınmadı.
- [ ] Önceki uygulama imajıyla ileri uyumlu rollback smoke testi geçti.
- [ ] Rollback sırasında volume/tablo/sır silinmedi.

## 9. Performans ve soak şablonu

Performans sonucu yoksa bölüm `REQUIRES BENCHMARK` olarak bırakılır; tahmini sayı
yazılmaz.

### 9.1. Ortam

| Alan | Değer |
|---|---|
| Host CPU/RAM/disk |  |
| Docker/OS sürümü |  |
| PostgreSQL sürümü/depolama |  |
| Worker sayısı/limitleri |  |
| Cihaz sayısı/profil dağılımı |  |
| Transport dağılımı |  |
| Latency/loss dağılımı |  |
| Polling aralıkları |  |
| Test süresi |  |

### 9.2. Sonuçlar

| Metrik | p50 | p95 | p99/max | Kabul eşiği | Sonuç |
|---|---:|---:|---:|---:|---|
| Fast collection süresi |  |  |  | Önceden onaylı |  |
| Network collection süresi |  |  |  | Önceden onaylı |  |
| Inventory collection süresi |  |  |  | Önceden onaylı |  |
| Queue lateness |  |  |  | Önceden onaylı |  |
| Worker CPU/RSS |  |  |  | Önceden onaylı |  |
| PostgreSQL CPU/IO/büyüme |  |  |  | Önceden onaylı |  |
| Cihaz CPU etkisi |  |  |  | Vendor/lab eşiği |  |
| Error/partial oranı |  |  |  | Önceden onaylı |  |

- [ ] En az bir worker restart/lease recovery denendi.
- [ ] Retry/backoff birikmiş fırtına oluşturmadı.
- [ ] Rate-limit yanıtı sınırlı ve jitter'lı yeniden denendi.
- [ ] Retention/rollup veri kaybetmeden çalıştı.
- [ ] Test sonuçları gerçek 24 saat ise öyle, hızlandırılmış sanal süre ise açıkça
  öyle etiketlendi.

## 10. Güvenlik ve gizlilik kapanışı

- [ ] `SECURITY.md` ile çelişen yeni davranış yok veya onaylı policy değişikliği var.
- [ ] SSH host key/TLS/SNMP auth doğrulaması fail-closed.
- [ ] Serbest hedef, serbest komut, serbest OID veya SNMP SET yok.
- [ ] Legacy SSH/SNMPv2c yalnız explicit device scope ve audit ile.
- [ ] Sırlar protocol-separated AAD ile şifreli.
- [ ] API/log/audit/metrics/frontend storage/artefakt secret scan PASS.
- [ ] XML entity, JSON depth/size, terminal escape ve formula/log injection gibi
  güvenilmeyen cihaz çıktısı testleri PASS.
- [ ] Başka site/rol verisi sızmıyor.
- [ ] Test yalnız yetkili hedeflerde gerçekleştirildi.

## 11. Sonuç ve destek kararı

| Karar alanı | Doldurulacak değer |
|---|---|
| Implementation status | `catalog_only/implemented/blocked/unsupported_by_*` |
| Verification status | En yüksek gerçek kanıt seviyesi |
| Release status | `hidden/experimental/candidate/supported` |
| Kabul edilen tuple | Model + exact OS + mode + transport + capability listesi |
| Kabul edilmeyen alanlar | Explicit liste |
| Açık riskler | Risk ID'leri |
| Yeniden test tetikleyicileri | Parser/profile/OS/controller/TLS değişimi vb. |
| Kanıt son kullanma tarihi | Tarih |
| `production_accepted` | Varsayılan `false`; yalnız gerçek yayın/kurulum kabulüyle `true` |
| İmzalı karar | Ed25519 key ID + canonical payload SHA-256; private key runtime'a girmez |
| Rollout politikası | `canary→pilot→general`, error/partial/queue p95 bütçesi ve breach eylemi |

### İmza/review

| Rol | Kimlik | Karar | Tarih |
|---|---|---|---|
| Sürücü geliştiricisi |  |  |  |
| Test/lab sahibi |  |  |  |
| Güvenlik inceleyicisi |  |  |  |
| Release sorumlusu |  |  |  |

Karar metni örneği:

```text
Bu kayıt yalnız <profile>@<revision>, <exact model>, <exact OS>,
<management mode>, <transport> ve PASS olan capability satırlarını kapsar.
Fixture/lab sonucu fiziksel veya production acceptance olarak kullanılmamıştır.
Listelenmeyen model, sürüm ve capability'ler not_tested/unknown kabul edilir.
```

## 12. Makinece okunabilir redakte özet örneği

```yaml
schema_version: 1
record_id: COMPAT-example-YYYYMMDD-01
source_revision: FULL_GIT_SHA
profile:
  id: example_profile
  revision: 1
target:
  vendor: Example
  model_family: EXAMPLE-SERIES
  exact_model: REDACTED_OR_APPROVED_VALUE
  os_family: ExampleOS
  os_version: 1.2.3
  management_mode: standalone
transport:
  kind: ssh
  security_profile: ssh2_host_key_pinned
evidence:
  class: physical_validated
  reference: CONTROLLED_ARTIFACT_REFERENCE
  sha256: 64_HEX_CHARACTERS
  sanitized: true
capabilities:
  system_identity: pass
  interfaces: pass
  counters: pass
  fdb: not_run
  lldp: partial
release:
  status: candidate
  production_accepted: false
  expires_at: YYYY-MM-DD
```

Bu YAML örneği secret veya ham çıktı taşımaz. `physical_validated` değeri yalnız
gerçek fiziksel cihaz testi gerçekten yapıldıysa kullanılmalıdır.

## 13. S11 makine kapısı

Bu şablondaki review tamamlandıktan sonra sırsız alanlar
`backend/app/release_acceptance.py` içindeki strict karar sözleşmesine aktarılır.
Artifact SHA-256 import sırasında gerçek dosyadan yeniden hesaplanır. Karar
offline Ed25519 anahtarıyla imzalanır ve
[`S11_OPERASYON_REHBERI.md`](S11_OPERASYON_REHBERI.md) akışıyla alınır.

- `candidate`: exact fiziksel kimlik+envanter, migration/E2E ve lab+release
  review zorunludur.
- `supported`: bütün bildirilen capability'ler, transport negatifleri,
  worker/lease/last-good/rollback, dört rol review'u ve güncel 24 saat benchmark
  zorunludur; runtime `supported` aktivasyonu ayrıca sıralı ve sağlıklı
  `canary→pilot→general` gözlemlerini gerektirir.
- Süresi dolan veya imzalı withdrawal ile geri çekilen karar destek üretmez.
- Rollout budget breach aynı decision ID altında geri döndürülemez; yeni karar
  gerekir.
