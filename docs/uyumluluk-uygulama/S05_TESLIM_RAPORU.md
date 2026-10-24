# S05 teslim raporu — P0 kanonik profiller ve sürücü sertleştirme

| Alan | Sonuç |
|---|---|
| Sprint | S05 — P0: Mevcut sürücüleri kanonik profillere ayırma ve sertleştirme |
| Tarih | 23 Ekim 2026 |
| Kaynak taban | `3298ed8` üzerine uygulanmış çalışma ağacı |
| Tamamlanan backlog | S05-01–S05-09 |
| Migration etkisi | Yok; mevcut binding, secret, inventory ve telemetry tabloları korunur |
| Profil revizyonu | Beş P0 profilinde `2`; `linux_ssh` adaptöründe `2` |
| Katalog revizyonu | `2026.10.23.3` |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — backend parser/manifest/test ve dokümantasyon değişikliği; UI kompozisyonu değişmedi |

## 1. İş paketi teslimleri

| ID | Durum | Kaynak ve kabul sonucu |
|---|---|---|
| S05-01 | Tamamlandı | `huawei_vrp` runtime/legacy değeri korunurken parser kanıtı yalnız V200/5.x banner'ını `huawei_vrp_v200` profiline çözer. V600 kimliği ayrı catalog-only profil olarak fail-closed kalır. Persist testi legacy collector ve envanterin yeniden yazılmadığını doğrular. |
| S05-02 | Tamamlandı | `driver_manifests/cisco_ios.py` ve `cisco_iosxe.py` bağımsız komut/capability tuple'larıdır. IOS-XE, IOS tuple'ını import etmez; profil-bazlı parser adları ve profile revision kullanır. |
| S05-03 | Tamamlandı | C9200L/17.12.3 ve C9300/17.9.5 için iki proje-sentetik, temizlenmiş JSON fixture eklendi. SHA-256 değerleri fixture manifestinde sabitlendi. Bunlar fiziksel cihaz kaydı değildir; release `experimental` kalır. |
| S05-04 | Tamamlandı | NX-OS `show mac address-table | json`, `show lldp neighbors detail | json` ve `show inventory | json` çıktıları typed FDB/LLDP/module alanlarına eşlenir. Manifestte ilan edilmeyen ARP/VLAN CLI capability'si eklenmez. |
| S05-05 | Tamamlandı | Junos FDB+ARP korelasyonu, environment temperature/fan/PSU, LLDP ve hardware XML eşlemesi eklendi. Manifestteki bütün sekiz komut mapped; malformed XML/entity ve eksik kimlik fail-closed kalır. |
| S05-06 | Tamamlandı | Standard SNMP system/IF/LLDP akışına Q-BRIDGE FDB port/status eklendi. FID→VLAN ve bridge-port→ifIndex→kalıcı interface zinciri kanıtlanmadan MAC satırı kabul edilmez; ARP/IP/kablo tahmini yapılmaz. Her capability özeti transport-bazlı `source_fields` yayımlar. Tanınan SNMP `sysDescr` ile SSH profil kimliği çelişirse binding `transport_identity_mismatch` ile fail-closed olur. |
| S05-07 | Tamamlandı | Kimlik komutu komut planının başına alındı. Daha önce eşleşmiş vendor/model/OS değişimi, profil revizyonu veya reboot derived command/capability cache'ini geçersizleştirir ve çözümü yeniler. Secret, host key, inventory ve last-good grup verisi korunur. |
| S05-08 | Tamamlandı | Mevcut Cisco 2960-X ve Huawei S5700 corpus'u, SSH lab, port kimliği, connector, pagination ve last-good regresyonları korunmuştur. MAC normalizasyonu nokta/iki-nokta/tire biçimlerini güvenli doğrular. |
| S05-09 | Tamamlandı | [`P0_SURUCU_PROFILLERI.md`](P0_SURUCU_PROFILLERI.md) kullanıcı/operatör komutlarını, minimum read-only yetkiyi, transport alanlarını ve bilinen boşlukları belgeler. |

## 2. Manifest ve parser sözleşmesi

Kanonik P0 deklarasyonları `backend/app/driver_manifests/` altında profil başına
ayrıdır. Registry her capability için union `fields` yanında `source_fields`
taşır. Validator; source/transport eşleşmesini, alan union'ını, duplicate komutu,
geçersiz grubu ve zorunlu inventory identity komutunu reddeder. Legacy katalog
facade yeni manifestleri yayımlar; runtime collector ID'leri ve eski
`huawei_vrp` kayıt değeri korunur.

IOS ile IOS-XE ortak yardımcı parser fonksiyonlarını kullanabilir, ancak bu
paylaşım kimlik, komut veya capability eşitliği değildir. NX-OS yalnız JSON,
Junos yalnız güvenli XML, VRP V200 yalnız doğrulanmış V200/5.x kimliği ile kendi
profile bağlanır.

## 3. Fixture ve kanıt kaydı

| Fixture | Sınıf | SHA-256 | Kabul sınırı |
|---|---|---|---|
| `cisco_iosxe_c9200l_17_12_3.json` | Proje-sentetik ve temizlenmiş | `ca4c61a60de04fcc18c5f5a922d10f312c5576acb6511242ec88c17e01edc220` | Parser/manifest fixture; fiziksel değil |
| `cisco_iosxe_c9300_17_9_5.json` | Proje-sentetik ve temizlenmiş | `7dbea65079fba205115f23f302c62db845bd60f21d6e6c32306a3995abf73689` | Parser/manifest fixture; fiziksel değil |

Fixture'lar ayrılmış hostname/MAC ve `TEST-SERIAL-*` kullanır; parola, kullanıcı,
host key, SNMP sırrı veya gerçek müşteri verisi içermez. Kaynakları gerçek cihaz
kaydı değil proje tarafından üretilmiş parser fixture'ıdır. Manifest üretim
zamanını, kaynak iznini, deterministik üretim yöntemini, capability kapsamını ve
bilinen istisnaları; her fixture da beklenen typed sonucu taşır. Bu yüzden profil
`fixture_verified/experimental` üstüne çıkarılmaz.

## 4. Kimlik, cache ve veri koruma

Toplayıcı her bağlantıda profile ait zorunlu inventory identity komutunu önce
okur. Gözlenen implemented profil seçilenden farklıysa yalnız gerçek gözlenen
runtime planına geçilir ve configured binding `conflict` olur. Gözlenen profil
V600/Junos Evolved gibi uygulanmamış bir profile aitse başka parser denenmeden
`collector_platform_unsupported` sonucu yazılır.

İlk başarılı resolution, aynı okumada öğrenilen negatif komut capability
sonucunu silmez. Yalnız önceden `matched` olan kimliğin değişmesi, reboot veya
profile revision değişimi cache invalidation üretir. Silinenler
`device_command_capabilities` ve güncel `device_capability_observations_v2`
satırlarıdır; cihaz payload'ı, şifreli sır, host key, collection group/history ve
latest telemetry korunur.

## 5. Doğrulama ve açık kabul kapıları

| Kontrol | Sonuç |
|---|---|
| `.venv/bin/pytest -q backend/tests` | `265 passed, 3 skipped`; yalnız dependency deprecation uyarıları |
| Nihai P0 + profil + SNMP + merge/API odak paketi | `41 passed` |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm test -- --run` | `11` dosya, `63 passed` |
| `npm run build` | PASS; Next.js production build |
| `docker compose --env-file .env.example config --quiet` | PASS |
| `git diff --check` | PASS |

Üç skip, yalnız açıkça ayrılmış boş loopback PostgreSQL URL'leri verilince çalışan
migration testleridir; SQLite migration/regresyon yolları tam pakette geçmiştir.

Odak testleri; iki IOS-XE fixture hash/beklenen typed sonuç/parser akışını,
NX-OS FDB/LLDP/inventory, Junos FDB/ARP/environment/LLDP, Huawei alias
çözümünü, Q-BRIDGE FDB ile reboot/OS sürümü/model ve profil çelişkisi cache
invalidation davranışını kapsar. Repository'de yapılandırılmış ayrı bir secret
scanner bulunmadığı için fixture'larda bounded hassas-terim taraması yapıldı ve
eşleşme bulunmadı; bu kontrol CI secret scanner kanıtı olarak sunulmaz.

Fiziksel WS-C2960X, Catalyst IOS-XE, Nexus, S5700 veya EX/QFX testi; production
rollout ve filo benchmark'ı çalıştırılmamıştır. Profil release değerleri
`experimental`, acceptance `production_accepted=false` kalır. Kapasite sonucu
`REQUIRES BENCHMARK`tır.

Rollback için migration yoktur. Önceki uygulama additive `source_fields`
alanını görmezden gelir; profil/adapter revision artışı eski acceptance tuple'ını
geçerli saymaz. Kod rollback'i cihaz verisi veya sır dönüşümü gerektirmez.

