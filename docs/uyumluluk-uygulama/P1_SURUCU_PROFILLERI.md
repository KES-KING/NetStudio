# P1 kurumsal sürücü profilleri — kullanıcı ve operatör rehberi

Bu belge S06 ile uygulanan `aruba_aoscx`, `aruba_aoss`, `arista_eos`,
`hpe_comware`, `h3c_comware7` ve `mikrotik_routeros` profillerinin çalışan
kaynak sözleşmesini açıklar. Altı profil `fixture_verified/experimental`
durumundadır. Proje-sentetik fixture, fiziksel cihaz veya production kabulü
değildir.

## Ortak işletim ve güvenlik sınırı

1. Cihaz eklerken üretici, kanonik profil ve `standalone` yönetim modu canlı
   katalogdan seçilir. Eski `hp_procurve` ve `hp_comware` değerleri saklanır;
   cihaz kimliği doğrulanınca sırasıyla `aruba_aoss` ve `hpe_comware` binding'i
   çözülür.
2. SSH hesabı yalnız profil allowlist'indeki salt-okunur `show`, `display` veya
   RouterOS `/... print` komutlarına yetkili olmalıdır. Configuration mode,
   shell, dosya yazma veya API token'ı gerekmez.
3. Host key kimlik bilgisi gönderilmeden önce doğrulanır. Timeout, yetki reddi,
   desteklenmeyen komut ve parser hatası ayrı capability sonucu üretir; son doğru
   veri silinmez.
4. SNMP yalnız v3 `authPriv` ve bounded standard-MIB allowlist'i ile çalışır.
   SET, SNMPv1/v2c ve runtime MIB indirme yoktur. SNMP FDB, FID/VLAN ve
   bridge-port/ifIndex zinciri kanıtlanmadan kabul edilmez.
5. AOS-CX/EOS bu sprintte SSH oturumu içindeki yapılandırılmış JSON CLI'ı
   kullanır. REST/eAPI seçilmemiştir; API transportu ADR-COMPAT-004 tamamlanana
   kadar `blocked` kalır.

## Profil ve kimlik matrisi

| Profil | Runtime ID | Fixture tuple | Parser sınırı | Yayın/kabul |
|---|---|---|---|---|
| `aruba_aoscx` | `aruba_aoscx` | JL658A / FL.10.13.1030 | AOS-CX JSON CLI; AOS-S text parser'ı denenmez | `experimental`; fiziksel kabul yok |
| `aruba_aoss` | `hp_procurve` | JL253A / WC.16.11.0016 | ArubaOS-Switch/ProVision text CLI; AOS-CX JSON beklenmez | `experimental`; alias kimliği yeniden doğrulanır |
| `arista_eos` | `arista_eos` | DCS-7050SX3-48YC8 / 4.31.2F | EOS JSON CLI; eAPI kapalı | `experimental`; fiziksel kabul yok |
| `hpe_comware` | `hp_comware` | JH390A / 7.1.070 R6715P06 | Comware 7 ortak alan mapper'ı + zorunlu HPE marka kanıtı | `experimental`; H3C kabulüyle birleşmez |
| `h3c_comware7` | `h3c_comware7` | S5560X-30C-EI / 7.1.070 R6526P01 | Comware 7 mapper'ı + zorunlu H3C/V7 kimliği; V5/V9 reddedilir | `experimental`; ayrı acceptance tuple |
| `mikrotik_routeros` | `mikrotik_routeros` | CRS326-24G-2S+ / 7.15.3 | RouterOS `/... print` dili; Cisco text parser'ı çağrılmaz | `experimental`; REST API kapalı |

Her fixture 64-bit RX/TX sayaçlarını `2^32` üstünde değerlerle doğrular; sayaç
bit genişliği `64`, CLI epoch kanıtı yoksa `counter_epoch_known=false` olur.
Fixture'lar reserved IP/MAC ve `TEST-*` seri değerleri taşır; gerçek cihaz
kaydı veya vendor output uygunluk sertifikası değildir.

## Salt-okunur komut allowlist'leri

### Aruba AOS-CX

```text
show version
show interface | json
show system resource-utilization | json
show environment | json
show vlan | json
show mac-address-table | json
show arp | json
show lldp neighbor-info | json
show inventory | json
```

### Aruba AOS-Switch

```text
show version
show interfaces
show vlans
show mac-address
show arp
show lldp info remote-device
show system information
show modules
```

CLI sağlık alanı ilan edilmez; standard ENTITY-SENSOR yolundaki sıcaklık alanı
SNMP kaynağıyla ayrı capability olarak kalır.

### Arista EOS

```text
show version | json
show interfaces | json
show processes top once | json
show environment all | json
show vlans | json
show mac address-table | json
show arp | json
show lldp neighbors detail | json
show inventory | json
```

Bu komutlar SSH CLI içindedir. eAPI endpoint, TLS/CA veya token yönetimi yoktur;
API kanalı açıkmış gibi gösterilmez.

### HPE Comware 7 ve H3C Comware V7

```text
display version
display interface
display cpu-usage
display memory
display environment
display vlan all
display mac-address
display arp
display lldp neighbor-information
display device manuinfo
```

İki profil yalnız normalize edilmiş Comware V7 alan mapper'ını paylaşır. Banner
önce `HPE Comware Software, Version 7...` veya `H3C Comware Software, Version
7...` olarak doğrulanır. HPE ve H3C runtime ID, vendor kanıtı, fixture ve
acceptance kaydı ayrıdır. H3C V5/V9 görülürse V7 allowlist'i çalıştırılmaz.

### MikroTik RouterOS

```text
/system resource print without-paging
/interface print stats-detail without-paging
/system health print detail without-paging
/interface bridge vlan print detail without-paging
/interface bridge host print detail without-paging
/ip arp print detail without-paging
/ip neighbor print detail without-paging
/system routerboard print without-paging
```

RouterOS satırları kendi key/value grameriyle ayrıştırılır. `show interfaces`
veya başka bir Cisco komutu fallback olarak çalıştırılmaz. SwOS bu profil
değildir ve SNMPv2c karar kapısı nedeniyle ayrı `mikrotik_swos` profili olarak
kapalıdır.

## Capability ve hata davranışı

- Bütün profiller SSH ve standard SNMPv3 kaynaklarından interface/system
  capability'si yayımlar.
- SSH tarafında 64-bit octet/error/discard, model/sürüm/seri, VLAN/FDB/ARP/LLDP
  ve açıkça listelenmiş inventory/health alanları typed sözleşmeye çevrilir.
- Opsiyonel komut yetkisiz veya desteklenmiyorsa grup `partial`; zorunlu kimlik
  ya da interface komutu okunamıyorsa ilgili grup `error` olur. Ham çıktı,
  kullanıcı adı, community/token veya cihaz hata metni API/DB'ye yazılmaz.
- SSH ve tanınan SNMP kimliği farklı kanonik profil gösterirse sonuç
  `transport_identity_mismatch` ile bağlanmaz.
- API/REST/eAPI fallback'i, transport kararı ve güven modeli olmadan devreye
  alınmaz.

## Fiziksel kabul için kalan iş

Her profil, exact model, hardware revision, OS sürümü, management mode,
transport/security profile ve capability kimliğiyle
[`KABUL_VE_KANIT_SABLONU.md`](KABUL_VE_KANIT_SABLONU.md) üzerinden ayrıca
doğrulanmalıdır. Süresi geçmemiş fiziksel kayıt olmadan `supported` veya
`production_accepted=true` yapılamaz. Gerçek cihaz kapasitesi ve büyük tablo
sınırları `REQUIRES BENCHMARK`tır.

