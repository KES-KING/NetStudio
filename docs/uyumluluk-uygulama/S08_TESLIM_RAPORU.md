# S08 teslim raporu — Controller/cloud API ve kampüs ekosistemi

| Alan | Sonuç |
|---|---|
| Sprint | S08 — Controller/cloud API ve kampüs ekosistemi |
| Tarih | 24 Ekim 2026 |
| Katalog / driver revizyonu | `2026.10.24.3` |
| Migration | `0011_controller_api` — yalnız yeni controller/secret/binding tabloları |
| Kabul seviyesi | Fixture + izole HTTPS transport; fiziksel cihaz/production kabulü değil |
| Ana tasarım etkisi | Yok; README ekran görüntüleri yenilenmedi |

## Backlog sonucu

| ID | Durum | Kaynak kanıtı ve sınır |
|---|---|---|
| S08-01 | Tamamlandı | URL kabul etmeyen site-scoped controller CRUD, controller'a özel AES-GCM secret, TLS doğrulamalı bounded HTTP adapter ve worker kanalı eklendi. |
| S08-02 | Tamamlandı | `cisco_meraki_ms` yalnız API runtime'ıyla seçilebilir; klasik SSH yoktur. Dashboard API origin'i bölge allowlist'indedir. |
| S08-03 | Politika gereği kapalı | Instant On local/cloud mode katalogda korunur; bu güven modeline bağlanabilecek belgelenmiş genel API olmadığı için `vendor_public_api_unavailable` ve seçilemezdir. |
| S08-04 | Tamamlandı | FortiLink switch, standalone FortiSwitch ve FortiGate kimliklerinden ayrıdır; controller FortiGate kaydı ile switch binding'i ayrı saklanır. |
| S08-05 | Tamamlandı | UniFi API yolu ve koşullu/planlı SNMP metadata'sı vardır; debug SSH uygulanmış management transportu değildir. |
| S08-06 | Tamamlandı | Flex/Ultra istisnası ayrı runtime ve model pattern taşır; SNMP `unsupported_by_protocol` kalır. |
| S08-07 | Tamamlandı | EdgeSwitch'in ayrı SSH komut manifesti, grameri, runtime ID'si, SNMPv3 capability'si ve proje-sentetik fixture'ı vardır. |
| S08-08 | Tamamlandı | Omada managed yalnız `controller_managed` modunda API runtime'ına çözülür; standalone kanıtı varsayılmaz. |
| S08-09 | Tamamlandı | Omada Pro ayrı profil/runtime/fixture kimliği kullanır; klasik Omada kabulü Pro'ya taşınmaz. |
| S08-10 | Tamamlandı | Doğru/yanlış CA, redirect, pagination loop, response limit, bounded 429, scope, expiry/revoke, site/vendor, duplicate binding ve API/SNMP conflict provenance testleri eklendi. |

## Güvenlik ve veri modeli

`api_controllers`, `api_controller_secrets` ve `device_controller_bindings`
tabloları cihaz payload'ı, SSH `device_secrets` veya SNMP
`device_protocol_secrets` kayıtlarını değiştirmez. Controller secret AAD'si
`netstudio:controller:{controller_id}:{key_id}:api` biçimindedir. Liste ve
binding API'leri tokenı döndürmez; validation exception'ları request body'sini
serialize etmez. Credential/binding/controller değişiklikleri bağlı cihazların
connection revision'ını artırır ve kuyruktaki eski sonucu fence eder.

Yerel hedef literal IP'dir. Meraki hedefi kod içi bölge origin map'inden gelir.
Redirect yok, pagination origin/path sabittir, HTTP proxy environment'ı
kullanılmaz. Response 2 MB, tablo 8.192 kayıt, pagination 20 sayfa, request 15
saniye ve Retry-After 30 saniye/bir tekrar ile sınırlıdır.

## Toplama ve provenance

Worker, profilin `implemented` transport listesini esas alır. API-only profilde
SSH credential bulunsa bile SSH yönetim kanalı açılmaz. API, SNMP ve SSH
kanıtları capability önceliğiyle birleştirilir; aynı alan farklı değer taşıyorsa
ham değer yazmadan `conflict:{field}` tanısı ve `partial` kalite üretilir. Kazanan
alanın `field_sources` provenance'ı korunur.

## Doğrulama kapsamı

| Kontrol | Sonuç |
|---|---|
| Backend tam regresyon | `354 passed, 3 skipped`; 14 bağımlılık/deprecation uyarısı, hata yok |
| S08 hedefli regresyon | Meraki/UniFi/Omada auth ve endpointleri, scope/CIDR, TLS/CA, pagination/rate-limit, migration upgrade+downgrade ve duplicate identity geçti |
| Frontend unit | 11 dosya / 63 test geçti |
| Frontend statik/üretim | ESLint, TypeScript ve 12 rotalı Next.js production build geçti |
| Compose | `.env.example` ile config doğrulandı; temiz PostgreSQL'de head `0011_controller_api` |
| Docker servisleri | API, worker, web, gateway, PostgreSQL ve SSH lab sağlıklı; migration/secrets-init başarılı çıktı |
| Gerçek tarayıcı | Sistem Chrome + Playwright: 3/3; controller oluşturma, redacted credential, binding ve legacy izin görünümü |
| Responsive görünüm | 1536×900 ve 390×844; yatay taşma/framework overlay yok, mobil modal dikey kaydırılabilir |
| Fixture bütünlüğü | Manifest SHA-256 eşleşti; bounded private-key/certificate/known-token kalıp taraması temiz |
| Diff hijyeni | `git diff --check` geçti |

Browser plugin bu çalışma ortamında sunulmadığı için gerçek tarayıcı kontrolü
Playwright'ın sistemdeki Google Chrome binary'siyle yapıldı. Seçili
`desktop-linux` Docker context'i HTTP 500 verdiğinden, sağlıklı `default`
context kullanıldı. Kanıt alındıktan sonra yalnız geçici
`netstudio-s08-qa-20261024` projesi ve yeniden üretilebilir sentetik volume'leri
kaldırıldı; başka Compose projeleri değiştirilmedi.

Fixture'lar `project_generated_test_fixture`, `physical_acceptance=false` ve
`production_accepted=false` sınırını taşır. İzole TLS sunucusu gerçek sertifika
zinciri doğrulamasını; mock transportlar sabit GET yolları, auth header'ı ve
normalize alan anlamlarını sınar. Bunlar üretici controller/switch davranışı
veya kapasite kanıtı değildir. Docker build sırasında `app.driver_manifests` ve
`app.snmp_mappers` alt paketlerini dışarıda bırakan setuptools paket keşfi de
düzeltilmiş, temiz worker imajında import ve sağlık kontrolüyle doğrulanmıştır.

## Açık kabul kapıları

- Her profil için exact controller sürümü + switch model/firmware fiziksel S11
  kaydı ve capability karşılaştırması gerekir.
- Omada access-token üretim/yenileme davranışı controller sürümüne göre fiziksel
  kabulde kanıtlanmalıdır; süresi geçen token fail-closed olur.
- FortiGate/UniFi/Omada gerçek response varyantları fixture eşlemesinden önce
  sanitized kanıt politikasıyla incelenmelidir.
- Kapasite, rate-limit ve çoklu controller davranışı `REQUIRES BENCHMARK`tır.
- Aruba Instant On ancak resmi/sürümlenmiş API veya güvenli yerel protokol kanıtı
  ve yeni karar kaydıyla açılabilir.
