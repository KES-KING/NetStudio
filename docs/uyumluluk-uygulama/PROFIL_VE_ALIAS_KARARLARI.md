# S00 kanonik profil ve alias kararları

Bu belgenin makinece doğrulanabilir karşılığı
[`S00_KAPSAM_KARARLARI.json`](S00_KAPSAM_KARARLARI.json) dosyasıdır. Liste bir
hedef kapsam kaydıdır; burada görünmek runtime desteği veya seçilebilirlik vermez.

## 1. Onaylı 38 kanonik profil

| Dalga | Adet | Kanonik kimlikler |
|---|---:|---|
| P0 | 5 | `cisco_ios`, `cisco_iosxe`, `cisco_nxos`, `huawei_vrp_v200`, `juniper_junos` |
| P1 | 6 | `aruba_aoscx`, `aruba_aoss`, `arista_eos`, `hpe_comware`, `h3c_comware7`, `mikrotik_routeros` |
| P2 | 13 | `dell_os10`, `dell_os9`, `dell_os6`, `extreme_exos`, `extreme_fabric_engine`, `extreme_slxos`, `fortinet_fortiswitchos`, `fortinet_fortiswitch_fortilink`, `tplink_omada_managed`, `tplink_omada_pro`, `ubiquiti_unifi_switch`, `ubiquiti_unifi_no_snmp`, `ubiquiti_edgeswitch` |
| P3 | 9 | `h3c_comware5`, `h3c_comware9`, `huawei_vrp_v600`, `juniper_junos_evolved`, `dell_sonic`, `nvidia_cumulus_linux`, `nvidia_onyx`, `sonic_nos`, `cisco_business` |
| P4 | 5 | `mikrotik_swos`, `cisco_meraki_ms`, `aruba_instant_on`, `tplink_easy_smart`, `unmanaged_switch` |

Her profil için başlangıç uygulama/doğrulama/yayın sınıfı JSON kaydında ayrı
alanlardadır. S00 tarihinde hiçbir profil `supported` değildir.

## 2. Profil olmayan kimlikler

| Kimlik | Sınıf | Karar |
|---|---|---|
| `linux_ssh` | Altyapı adaptörü | Genel read-only iproute2 toplama; Dell SONiC, NVIDIA Cumulus veya genel SONiC profili değildir |
| `auto` | Seçim modu | Kimlik kanıtına göre fail-closed profil çözümü hedefidir |
| `external` | Yürütme modu | Harici toplayıcı/envanter aktarımıdır; NOS ailesi değildir |

## 3. Eski kimlik kararları

| Eski kimlik | Hedef | Otomatik mi? | Karar |
|---|---|---:|---|
| `huawei_vrp` | `huawei_vrp_v200` | Hayır | Yalnız V200 kimlik kanıtı varsa çöz; V600'e tahminle taşıma |
| `hp_procurve` | `aruba_aoss` | Evet, kontrollü | Okuma uyumluluk alias'ı; kullanım öncesi cihaz kimliğini yeniden doğrula |
| `hp_comware` | `hpe_comware` | Evet, kontrollü | Okuma uyumluluk alias'ı; H3C/Comware varyantını ayrıca doğrula |
| `dell_force10` | `dell_os9` | Hayır | OS9 kimliği doğrulanmadan OS6/OS10/SONiC'e taşıma |
| `extreme_vsp` | `extreme_fabric_engine` | Hayır | Fabric Engine kimliği ve sürümü doğrulanmadan dönüştürme |
| `fortinet` | Yok | Hayır | FortiSwitchOS ile FortiLink yönetim modu belirsiz; `manual_resolution_required` |

“Otomatik” işaretli iki uyumluluk alias'ı bile runtime'da `supported` sonucu
üretmez; yalnız eski değeri tek kanonik okumaya yönlendirir ve kimlik yeniden
doğrulaması gerektirir. Koşullu kayıtlar migration sırasında asıl değeri
silmeden karantinada tutulmalıdır.

## 4. Alias doğrulama kuralları

- Bir eski ID en fazla bir kanonik hedefe sahiptir.
- Kanonik profiller başka alias'a değil doğrudan profile çözümlenir.
- Döngü, çoklu hedef ve kanıtsız aileler-arası dönüşüm reddedilir.
- `manual_resolution_required` kayıt için kullanıcıya kesin hedef dayatılmaz.
- Migration additive ve geri alınabilir olur; sır, cihaz ID'si ve mevcut payload
  yeniden yazılmaz.
- Alias kararı capability veya model kapsamını genişletmez.

## 5. Uygulama sınırı

Bu kararlar S01 registry ve S02 veri geçişinin girdisidir. S00 kapsamında parser,
API seçilebilirliği veya migration uygulanmamıştır.

