# S04 teslim raporu — ortak transport katmanı ve geniş SNMPv3 çekirdeği

| Alan | Sonuç |
|---|---|
| Sprint | S04 — Ortak transport katmanı ve geniş SNMPv3 çekirdeği |
| Tarih | 23 Ekim 2026 |
| Kaynak taban | `8113d3b` üzerine uygulanmış çalışma ağacı |
| Tamamlanan backlog | S04-01–S04-10 |
| Migration etkisi | Yok; mevcut JSON grup/polling state sözleşmeleri additive genişletildi |
| Protokol sınırı | Yalnız SNMPv3 authPriv; SHA-256/SHA-1 + AES-128 |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI; loopback agent fiziksel vendor kabulü değildir |
| Kabul üst sınırı | Generic SNMP çekirdeği `transport_lab_validated`; vendor profilleri otomatik yükseltilmedi |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — backend transport/parser/test/dokümantasyon değişikliği; UI kompozisyonu değişmedi |

## 1. İş paketi teslimleri

| ID | Durum | Uygulama ve kanıt |
|---|---|---|
| S04-01 | Tamamlandı | `transport.py`, SSH/SNMP/gelecek API adaptörleri için tek `TransportAdapter` protokolü ile immutable hedef, toplam deadline ve ağ beklemesi öncesi/sonrası fencing sağlayan `TransportContext` ekler. Worker SSH ve SNMP'yi bu context ile yürütür. |
| S04-02 | Tamamlandı | `snmp_transport.py`, mapper'lardan bağımsız `BoundedSNMPReader` içinde GET/GETNEXT/GETBULK, 128 istek, 4096 satır, 16384 varbind, 2 MB ve 2 saniye/cevap sınırlarını uygular. |
| S04-03 | Tamamlandı | `snmp_mappers/system.py`, sayısal SNMPv2-MIB OID'lerinden typed `sysObjectID`, `sysDescr`, `sysName`, `sysUpTime` üretir; uptime zorunlu, diğer kimlik alanları eksikse `null` kalır. |
| S04-04 | Tamamlandı | IF/IF-X mapper ayrı modüle taşındı; kalıcı kimlikte ifIndex'e güvenmez, duplicate ad/index çelişkisinde fail-closed olur, sysUpTime reboot ve ifCounterDiscontinuity epoch'unu taşır, 64-bit sayacı 32-bit'e tercih eder. |
| S04-05 | Tamamlandı | BRIDGE/Q-BRIDGE mapper VLAN→FID, bridge-port→ifIndex ve PVID üretir; bilinmeyen ifIndex eksik/partial, çelişen bridge map hata olur. |
| S04-06 | Tamamlandı | LLDP mapper yerel portu mevcut arayüz kimliğine bağlar, uzak chassis/port kanıtını `l2` komşuluk olarak saklar; remote device/interface veya fiziksel kablo kimliği tahmin etmez. |
| S04-07 | Tamamlandı | ENTITY/ENTITY-SENSOR mapper explicit class ile modül/fan/PSU/sensör kaydı üretir; bilinmeyen class ve connector `unknown` kalır. |
| S04-08 | Tamamlandı | `collection.py` capability-bazlı kaynak önceliği, field-level merge, `field_sources`/`field_observed_at` provenance ve partial/failure sırasında last-good koruması uygular. Her transport kanıtı capability tablosuna ayrı kaydedilir. |
| S04-09 | Tamamlandı | Polling state içindeki SSH/SNMP kanalları ayrı reason/failure/retry_at taşır. Kanal backoff'u süresiz değildir; başarılı yeniden deneme ilgili kanalı temizler ve diğer transportu global pause'a sokmaz. |
| S04-10 | Tamamlandı | Gerçek loopback UDP agent testi bütün standard mapper'ları, auth/context negatiflerini ve 4097 satır sınırını kapsar; timeout/cancel ile merkezi request/OID/lease sınırları ayrıca doğrulanır. |

## 2. Transport ve güvenlik sözleşmesi

Transport context'i cihazı, store/vault referansını, mutlak monotonic deadline'ı
ve worker'ın mevcut authorization/fencing callback'ini taşır. Callback her ağ
beklemesinden önce ve sonra çalışır. Böylece lease kaybı, session/policy değişimi
ve hedef revizyonu eski worker'ın sonucu yazmasından önce kesilir.

SNMP reader yalnız kodda denetlenen sayısal OID köklerini kabul eder. Runtime MIB
indirme/isim çözümü, community tabanlı v1/v2c, SET ve trap receiver eklenmemiştir.
Uzak agent hata ayrıntısı dışarı taşınmaz; sonuç yalnız sonlu güvenli kodlardan
biridir: `snmp_authentication_failed`, `snmp_context_mismatch`, `snmp_timeout`,
`snmp_read_failed` veya belirli limit/şema hata kodu. Kullanıcı adı, engine ID,
parola ve ham varbind hata metni log/API sonucuna eklenmez.

## 3. Standard MIB veri sözleşmesi

- System identity ham cihaz adını envanter adı olarak otomatik yazmaz; typed
  capability payload'ında kanıt olarak kalır.
- IF-MIB/IF-X-MIB arayüz adıyla mevcut kalıcı interface ID'sini eşler. ifIndex
  yalnız aynı okuma içindeki BRIDGE/LLDP korelasyonu içindir.
- Counter64 düşüşü, Counter32 wrap/düşüşü, discontinuity değişimi, kaynak değişimi
  ve sysUpTime reboot ilk örnekte hız üretmez.
- BRIDGE/Q-BRIDGE verisi FDB/MAC'i IP veya kabloya dönüştürmez.
- LLDP kanıtı `relation=l2` olur; uzak cihaz kaydı yoksa kimlik uydurulmaz.
- ENTITY class açık değilse `unknown`; port entity'sinin connector tipi vendor
  kanıtı olmadan `unknown` kalır.
- Eksik standard tablo grup sonucunu `partial/unsupported` yapar; daha eski tam
  SSH alanını silmez.

## 4. Kaynak birleştirme ve kanal geri kazanımı

Kaynak önceliği global değil grup/capability bağlamındadır. Fast ve standard
network kanıtında SNMP, health/inventory cihaz alanlarında SSH/structured kaynak
önceliklidir. `None`, eksik liste veya başarısız capability bir silme sinyali
değildir. Başarılı alan yeni kaynak ve saatini alırken başarısız alan önceki
`field_sources`, `field_observed_at`, payload ve grup last-good saatini korur.

Polling kanal durumu artık düz, kalıcı bir SNMP hata string'i değildir. Her kanal
bounded exponential retry zamanı taşır. Eski string state ilk S04 scheduler
geçişinde yeniden denenebilir. SSH authentication/KEX hatası SNMP kanalını;
SNMP auth/context/timeout hatası SSH kanalını durdurmaz. Başarılı kanal denemesi
yalnız kendi pause kaydını temizler.

## 5. Doğrulama

| Kontrol | Sonuç |
|---|---|
| S04 + gerçek SSH regresyon hedefleri | `13 passed` |
| Backend tam paket | `257 passed, 3 skipped`; 14 bağımlılık/deprecation uyarısı |
| Gerçek loopback SNMPv3 authPriv | PASS; GET/GETBULK, dört standard mapper ailesi, SHA-256/AES-128 |
| Auth negatifleri | PASS; unknown user, wrong digest ve decryption aynı redakte auth kodu |
| Context/limit negatifleri | PASS; context mismatch, artmayan OID, 4097 satır, 129. istek, malformed/allowlist OID |
| Deadline/fencing | PASS; response timeout, asyncio cancellation ve job lease kaybı |
| Kimlik/sayaç çelişkileri | PASS; duplicate ifName/ifIndex, bridge conflict, Counter32/64 düşüşü, sysUpTime reboot |
| Last-good merge | PASS; partial SNMP VLAN alanı eklenirken CLI FDB/LLDP ve alan saati/kaynağı korundu |
| Frontend/browser | ÇALIŞTIRILMADI; frontend kaynağı ve UI sözleşmesi değişmedi |
| Fiziksel switch/vendor MIB | ÇALIŞTIRILMADI |

Test agent'ı gerçek UDP ve pysnmp v3 authPriv protokol yolunu kullanır; yalnız
sentetik OID verisi sunar ve SET çağrısını testte doğrudan başarısız sayar.
Bu nedenle sonuç generic transport laboratuvar kanıtıdır; Cisco/Huawei/Juniper
model/firmware uyumluluğu veya production kabulü değildir.

## 6. Dağıtım, rollback ve kalan sınırlar

Yeni migration yoktur. Mevcut polling `state` JSON'u geriye uyumlu okunur;
önceki string kanal pause değeri silinmeden yeniden denemeye açılır ve sonraki
sonuçta typed state'e dönüşür. Uygulama rollback'i yeni JSON alanlarını görmezden
gelir; sır, envanter, host key, telemetry veya job tablosu yeniden oluşturulmaz.

Vendor MIB'leri, SNMP trap, write/SET, v2c, fiziksel cihaz testi, production
rollout ve kapasite benchmark'ı S04 kapsamı dışındadır. 4097 satır/129 istek
negatifleri güvenlik sınırını kanıtlar; gerçek filo kapasitesi için sonuç
`REQUIRES BENCHMARK` olarak kalır.
