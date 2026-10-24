# P4 — SNMPv2c ve protokol sınırları

Bu belge S10 ile uygulanan dar SNMPv2c istisnasının ve doğrudan yönetim
protokolü bulunmayan cihaz profillerinin çalışan sözleşmesidir. Genel bir
SNMPv2c desteği değildir. Normatif güvenlik kararı
[`ADR-COMPAT-003`](adr/ADR-COMPAT-003-snmpv2c-karar-kapisi.md), kaynak kod
kapısı `backend/app/snmp_policy.py` ve güncel katalog `/api/v1/driver-catalog`
çıktısıdır.

## 1. Destek özeti

| Profil | Runtime sonucu | Credential yüzeyi | Kanıt sınırı |
|---|---|---|---|
| `mikrotik_swos` | `implemented` / `transport_lab_validated` / `experimental` | Yalnız kurulum flag'i açıkken superadmin SNMPv2c formu | CSS610-8G-2S+/SwOS 2.19 proje-sentetik fixture ve loopback UDP agent; fiziksel cihaz değil |
| `ubiquiti_unifi_no_snmp` | S08 controller API yolu uygulanmış, SNMP `unsupported_by_protocol` | Controller API; SNMP formu yok | Flex/Ultra ayrımı S08 fixture kapsamı |
| `aruba_instant_on` | `blocked`; genel resmî yönetim API sözleşmesi kanıtlanmadı | Yok | Yeni model/mode kanıtı ve güvenlik kararı olmadan açılmaz |
| `tplink_easy_smart` | `unsupported_by_protocol` | Yok | Exact model/firmware istisnası ayrı profil ve kanıt gerektirir |
| `unmanaged_switch` | `unsupported_by_protocol` | Yok | Komşu LLDP/FDB kaydı yalnız dolaylı görünürlüktür |

Hiçbir satır `supported`, `physical_validated` veya `production_accepted`
değildir. Protokol sunmayan bir cihazda credential istememek bağlantı hatası
değil, açık destek sınırıdır.

## 2. SwOS için iki kapılı etkinleştirme

SNMPv2c aşağıdaki iki koşul aynı anda sağlanmadan seçilemez ve worker tarafından
kullanılamaz:

1. Kurulum sahibi `.env` içinde `NETSTUDIO_ALLOW_SNMP_V2C=1` ayarlar ve API ile
   `collector-worker` servislerini aynı Compose yapılandırmasıyla yeniden
   oluşturur. Değer yoksa, `0` ise veya tam olarak `1` değilse kapı kapalıdır.
2. Superadmin, cihaz detayındaki **Bağlantı bilgileri** ekranında read-only
   community, NetStudio kaynak IP ACL'si, ayrılmış yönetim VLAN/VRF'si ve
   şifrelenmemiş taşıma riskini ayrı ayrı doğrular.

Flag kapalıyken katalog profili bilgi amacıyla görünür fakat
`available=false`, `selectable=false` ve
`availability_reason=snmp_v2c_installation_disabled` döner. İstemci bu kapıyı
atlatsa da cihaz oluşturma, credential yazma ve worker toplaması backend'de
yeniden reddedilir.

Örnek kurulum değişikliği:

```dotenv
NETSTUDIO_ALLOW_SNMP_V2C=1
```

```bash
# Gerçek kurulumun doğrulanmış context/proje/override seçenekleriyle:
docker compose config --quiet
docker compose up -d --build api collector-worker web
```

NetStudio cihaz üzerinde SNMP'yi veya ACL'yi yapılandırmaz. Önce cihazda yalnız
okuma community'si oluşturulmalı, kaynak ACL'si NetStudio worker IP'siyle
sınırlandırılmalı ve trafik ayrılmış yönetim ağına alınmalıdır.

## 3. Sır ve yetki modeli

- `PUT /api/v1/devices/{id}/snmp-v2c-credentials` yalnız
  `credential.manage` yetkili **superadmin** için çalışır.
- Community 8–128 printable ASCII karakterdir; API yalnız güvenli durum alanları
  döndürür.
- Secret `protocol=snmp_v2c` ile, cihaz+protokol bağını içeren ayrı AES-256-GCM
  AAD kapsamında saklanır. v3 `snmp` zarfıyla değiştirilemez veya karıştırılamaz.
- Audit yalnız sürüm, port, dört kontrolün sonucu, aktör ve zamanı taşır;
  community taşımaz.
- Aynı cihazda v2c ve v3 zarfı birlikte bulunursa protokol seçilmez ve toplama
  `snmp_protocol_conflict` ile durur.
- v3 sunan profilde v2c endpoint'i, SwOS profilinde v3 endpoint'i reddedilir;
  otomatik downgrade yoktur.

## 4. Salt-okunur transport sınırı

`PysnmpV2cSession`, `CommunityData(..., mpModel=1)` kullanır; SNMPv1
`mpModel=0` yolu yoktur. Oturumun çağırabildiği operasyon tipi yalnız `get`,
`getnext` ve `getbulk` değerleridir. SET metodu ve serbest MIB/OID girdisi yoktur.
S04'teki sayısal OID allowlist'i, hedef-IP politikası ve şu bütçeler aynen
korunur:

- en çok 128 istek, 4096 satır, 16384 varbind ve 2 MB cevap,
- istek başına 2 saniye; toplama context'i için bounded deadline,
- tek bulk isteğinde en çok 40 tekrar,
- artmayan/tekrarlanan veya allowlist dışına çıkan OID'de fail-closed sonuç,
- ham agent hatasını, community'yi ve ham varbind içeriğini log/audit'e yazmama.

MikroTik'in CSS610 SwOS dokümanı SNMP v1/v2c ile GET, GETNEXT ve GETBULK
okumalarını desteklediğini; yazma ve trap desteği vermediğini belirtir. NetStudio
bu üretici sınırından da dar davranarak yalnız v2c'yi açar. Protokol operasyon
semantiği RFC 3416 ile uyumludur.

## 5. Kimlik ve veri eşleme

Toplama başlamadan `sysDescr` exact MikroTik CSS + SwOS + sürüm biçimine
uymalıdır. RouterOS, serbest açıklama, üreticisi belirsiz SNMP agent veya başka
profil kanıtı `snmp_swos_identity_mismatch` ile reddedilir.

- Sistem kimliği: standard SNMPv2-MIB `sysObjectID`, `sysDescr`, `sysName` ve
  `sysUpTime`.
- Mantıksal arayüz: IF-MIB/IF-X-MIB adı, admin/oper durumu, hız ve 64-bit
  sayaçlar. Kalıcı kimlik cihaz ID'si + normalize arayüz adı hash'idir;
  modelden fiziksel port geometrisi üretilmez.
- VLAN/FDB: BRIDGE-MIB ve Q-BRIDGE-MIB; bridge-port→ifIndex ve güncel
  FID→VLAN zinciri eksikse kayıt kabul edilmez.
- Sağlık, PoE, optik DOM, LLDP ve fiziksel kasa/port envanteri bu profile ait
  kanıt olmadan doldurulmaz.

## 6. Geri çekme ve rollback

Cihaz bazlı **SNMPv2c onayını ve community kaydını kaldır** eylemi şifreli
zarfı siler, bağlantı revizyonunu artırır ve `snmp.v2c.risk_withdrawn` audit
olayı üretir. Kurulum genelinde acil kapatma için flag `0` yapılır ve API/worker
yeniden oluşturulur. Bu işlem kayıtlı zarfı silmez fakat katalog, yeni yazma ve
worker kullanımını durdurur.

Kod rollback'inden önce cihaz bazlı onayların geri çekilmesi önerilir. Migration
eklenmedi; mevcut `protocol_secrets` tablosunun protokol ayrımı kullanıldı.
Eski kod `snmp_v2c` zarfını `snmp`/v3 olarak yorumlamaz. Veritabanı, cihaz,
envanter, SSH host key ve last-good telemetri silinmez.

## 7. Operasyon ve kabul kontrol listesi

- [ ] Exact cihaz modeli ve SwOS sürümü kayıt altına alındı.
- [ ] Cihaz yalnız read-only community sunuyor; yazma erişimi yok.
- [ ] Kaynak ACL yalnız doğrulanmış NetStudio collector IP'sine izin veriyor.
- [ ] SNMP trafiği ayrılmış yönetim VLAN/VRF'sinde.
- [ ] Kurulum flag'i değişikliği ve Compose proje/context'i review edildi.
- [ ] Superadmin cihaz bazlı dört kontrolü onayladı.
- [ ] Bağlantı testi exact SwOS kimliğiyle geçti; yanlış community/kimlik negatif
  sonuçları incelendi.
- [ ] Community read API, audit, log ve ekran görüntülerinde bulunmuyor.
- [ ] Fiziksel kabul kaydı model/firmware/capability tuple'ı için S11 şablonuyla
  üretildi; bu tamamlanmadan `supported` etiketi verilmedi.

## Referanslar

- [MikroTik CSS610 series manual — SNMP](https://help.mikrotik.com/docs/spaces/SWOS/pages/76939305/CSS610%2Bseries%2BManual)
- [MikroTik SwOS overview](https://help.mikrotik.com/docs/spaces/SWOS/overview)
- [RFC 3416 — SNMPv2 Protocol Operations](https://www.rfc-editor.org/info/rfc3416/)
- [`SECURITY.md`](../../SECURITY.md)
- [`collection-automation.md`](../collection-automation.md)

