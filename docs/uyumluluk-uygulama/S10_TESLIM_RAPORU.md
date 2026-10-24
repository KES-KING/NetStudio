# S10 teslim raporu — SNMPv2c opt-in ve protokol kapsamı dışı cihazlar

| Alan | Sonuç |
|---|---|
| Sprint | S10 — P4: SNMPv2c opt-in ve protokol kapsamı dışı cihazlar |
| Tarih | 24 Ekim 2026 |
| Tamamlanan backlog | S10-01–S10-11 |
| Migration etkisi | Yok; mevcut protokol secret tablosu additive protokol kimliğiyle kullanıldı |
| Profil revizyonu | `mikrotik_swos@2` |
| Katalog / driver revizyonu | `2026.10.24.5` |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — katalog/form durumları genişledi; ana yerleşim, tema ve kabuk değişmedi |

## 1. Teslim edilen iş paketleri

| ID | Durum | Kaynak sonucu |
|---|---|---|
| S10-01 | Tamamlandı | `SNMPV2cCredentials` ve ayrı `snmp_v2c` vault AAD'si eklendi; community read modeline girmez. |
| S10-02 | Tamamlandı | `NETSTUDIO_ALLOW_SNMP_V2C=0` varsayılanı API, katalog ve worker'da fail-closed uygulanır. |
| S10-03 | Tamamlandı | Yalnız superadmin dört risk kontrolüyle cihaz onayı verebilir; kabul/geri çekme audit edilir. |
| S10-04 | Tamamlandı | `mpModel=1` v2c oturumu yalnız GET/GETNEXT/GETBULK ve S04 bounded sayısal OID reader'ını kullanır. |
| S10-05 | Tamamlandı | Exact CSS/SwOS kimliği, mantıksal interface ve Q-BRIDGE FDB eşlemesi eklendi. |
| S10-06 | Tamamlandı | UI şifrelenmemiş protokol, ACL, yönetim VLAN/VRF ve read-only onaylarını ayrı gösterir. |
| S10-07 | Tamamlandı | v3 profilde v2c, SwOS'ta v3 ve iki zarfın çakışması fail-closed reddedilir. |
| S10-08 | Tamamlandı | Easy Smart `unsupported_by_protocol`; model istisnası olmadan credential yüzeyi yok. |
| S10-09 | Tamamlandı | Unmanaged profil doğrudan yönetilemez; LLDP/FDB yalnız dolaylı görünürlük olarak açıklanır. |
| S10-10 | Tamamlandı | Protokol dışı profiller katalog/API/UI'da seçilemez ve açık gerekçe/guidance taşır. |
| S10-11 | Tamamlandı | `SECURITY.md`, operatör rehberi, izlenebilirlik matrisi ve ADR aynı karara getirildi. |

## 2. Güvenlik ve veri doğruluğu sonucu

S10 genel SNMPv2c açmamıştır. Profil seçimi yalnız `mikrotik_swos`, management
mode `standalone` ve runtime collector eşliğiyle mümkündür. Kurulum flag'i tam
olarak `1` değilse profil katalogda seçilemez, credential endpoint'i ve worker
transportu kapalıdır. Flag açık olsa bile cihaz bazlı superadmin onayı ve dört
zorunlu doğrulama olmadan community kaydedilemez.

Community AES-256-GCM zarfında cihaz+`snmp_v2c` protokol AAD'sine bağlıdır. API,
device read modeli ve audit yalnız güvenli metadata döndürür. v3 ve v2c
zarflarının aynı cihazda bulunması belirsizlik sayılır; hiçbirine otomatik
öncelik verilmez. SNMPv1 ve SET için runtime operasyonu yoktur.

SwOS kimliği yalnız standard MIB `sysDescr` içindeki explicit MikroTik CSS,
SwOS ve sürüm kanıtından kabul edilir. Logical interface kimliği `ifName`
üzerinden kararlı tutulur; CSS model adından fiziksel port bankası, konnektör
türü veya kasa geometrisi tahmin edilmez. Q-BRIDGE FDB, bridge-port→ifIndex ve
FID→VLAN zinciri tamamlanmadan yayımlanmaz.

## 3. Kanıt seviyesi

`backend/tests/fixtures/p4/mikrotik_swos_css610_2_19.json`, proje tarafından
üretilmiş ve SHA-256 değeri manifestte sabitlenmiş parser/transport girdisidir.
Loopback PySNMP agent testi gerçek UDP v2c message-processing yolunu, exact
kimliği, IF/IF-X sayaçlarını ve FDB zincirini çalıştırır; agent'ın write callback'i
çağrılırsa test başarısız olur. Bunlar üretici cihaz transcript'i, fiziksel
SwOS kabulü veya production kanıtı değildir.

`mikrotik_swos` bu nedenle `transport_lab_validated/experimental` kalır ve
`production_accepted=false` taşır. CSS610 dışındaki CSS/CRS/SwOS Lite
varyantları, fiziksel ACL/izolasyon davranışı, büyük FDB tabloları, reboot sonrası
ifIndex kararlılığı ve uzun süreli yük S11'de ayrı doğrulanmalıdır. Kapasite
iddiası `REQUIRES BENCHMARK`tır.

## 4. Dağıtım, rollback ve tasarım etkisi

Yeni migration yoktur. Compose API ve worker'a aynı
`NETSTUDIO_ALLOW_SNMP_V2C` değerini geçirir; örnek değer `0`'dır. Normal güncelleme
mevcut cihaz, v3/SSH/API secret, host key, inventory, telemetry ve job kayıtlarını
yeniden yazmaz.

Risk istisnası cihaz detayından geri çekilebilir. Kurulum flag'ini `0` yapmak
katalog/yazma/worker kullanımını kapatır; veri silmez. Kod rollback'i öncesi v2c
onaylarının geri çekilmesi önerilir. Ayrıntılı işlem
[`P4_SNMPV2C_VE_PROTOKOL_SINIRLARI.md`](P4_SNMPV2C_VE_PROTOKOL_SINIRLARI.md)
içindedir.

UI değişikliği mevcut katalog seçimleri ve bağlantı modalı içindeki yeni risk
formuyla sınırlıdır. Ana sayfa, cihaz detay kompozisyonu, SSH açık/kapalı
yerleşim, tema, tipografi, ana navigasyon ve genel kabuk değişmedi. Bu nedenle
`Ana tasarım etkisi: yok` ve README'nin üç kanonik ekran görüntüsü
yenilenmemiştir; hedef akış masaüstü/mobil gerçek tarayıcı QA'sında ayrıca
doğrulanır.

## 5. Doğrulama özeti

| Kontrol | Sonuç |
|---|---|
| S10 + katalog/yönetişim odaklı backend | `25 passed` |
| Geniş S04/S08/S09/S10 regresyon paketi | İlk koşu `121 passed, 1 failed`; profil olmayan backtick durum etiketi düzeltildi ve tam paket içinde geçti |
| Tam backend paketi | `408 passed, 3 skipped`; opsiyonel PostgreSQL migration koşulları atlandı |
| Frontend unit/component | `64 passed` |
| Frontend lint / TypeScript | başarılı / başarılı |
| Production frontend build | başarılı; 12 route üretildi |
| Compose yapılandırması | `.env.example` ile başarılı |
| İzole Docker | API, worker, web, gateway, PostgreSQL ve SSH lab sağlıklı; v2c flag API/worker'a aynı değerle geçti |
| Gerçek Chrome uyumluluk akışı | `4 passed`; katalog, SwOS onay/redaksiyon, global kapı kapalı görünüm ve geri çekme, controller ve legacy profil senaryoları |
| Görsel/erişilebilirlik sınırı | 1536×900 ve 390×844; yatay taşma, framework hata katmanı ve beklenmeyen console hatası yok |

Tarayıcı kanıtı `netstudio-s10-qa-20261024` adlı, benzersiz loopback port ve
volume'lere sahip geçici projede üretildi. Browser entegrasyonu bulunmadığından
repository Playwright akışı `/usr/bin/google-chrome` ile çalıştırıldı. Geçici
masaüstü/mobil kareler açılıp görsel olarak incelendi. Test sonunda yalnız bu
proje ve ona ait üç volume kaldırıldı; önceden çalışan
`netstudio-s03-qa-native-20261023` servisleri sağlıklı kaldı.

Starlette/httpx, AsyncSSH FFDH, Alembic ve Vite yapılandırma uyarıları mevcut
bağımlılık geçiş uyarılarıdır; bu sprintte yeni başarısızlık üretmemiştir. İzole
fixture, loopback agent, Docker ve browser sonuçları fiziksel cihaz/production
kabulüne yükseltilmez.

