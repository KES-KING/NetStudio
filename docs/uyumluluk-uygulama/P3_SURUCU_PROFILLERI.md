# P3 ileri, legacy ve Linux tabanlı NOS sürücü profilleri

Bu belge S09 ile uygulanan `h3c_comware5`, `h3c_comware9`,
`huawei_vrp_v600`, `juniper_junos_evolved`, `dell_sonic`,
`nvidia_cumulus_linux`, `nvidia_onyx`, `sonic_nos` ve `cisco_business`
profillerinin çalışan sözleşmesini açıklar. Dokuz profil
`fixture_verified/experimental` durumundadır. Proje-sentetik fixture, fiziksel
cihaz veya production kabulü değildir.

## Kimlik, transport ve kabul matrisi

| Profil | Exact sentetik tuple | SSH sınırı | SNMP/API sınırı |
|---|---|---|---|
| `h3c_comware5` | S5500-28C-EI / 5.20 R2222P02 | V5'e özel gramer; eski algoritma yalnız cihaz opt-in'i | Standard-MIB SNMPv3; fiziksel kabul yok |
| `h3c_comware9` | S6520X-30HC-HI / 9.1 R9126P01 | V7 fixture/parser'ı kullanılmaz | Standard-MIB SNMPv3; fiziksel kabul yok |
| `huawei_vrp_v600` | S5735-L24P4XE-A-V2 / V600R023C10 | V200 alias'ı ve parser'ı değildir | Standard-MIB SNMPv3; fiziksel kabul yok |
| `juniper_junos_evolved` | QFX5130-48C / 23.4R2-EVO | Evolved kimliği ve `no-more` XML planı | Standard-MIB SNMPv3; NETCONF uygulanmadı |
| `dell_sonic` | S5248F-ON / Dell Enterprise SONiC 4.4.0 | Dell distribution satırı zorunlu | SNMPv3 dağıtım kanıtı ve API adapter'ı planlı |
| `nvidia_cumulus_linux` | SN3700C / Cumulus Linux 5.14.0 | NVUE JSON; `linux_ssh` ile eşdeğer değil | Standard-MIB SNMPv3; NVUE API planlı |
| `nvidia_onyx` | SN2700 / Onyx 3.10.4404 | Onyx CLI; NVUE komutlarına düşmez | Standard-MIB SNMPv3; fiziksel kabul yok |
| `sonic_nos` | Community SONiC 202405 + image tuple | Distribution ve image zorunlu; vendor `Unknown` | SNMP/API dağıtım kanıtı gelene kadar planlı |
| `cisco_business` | CBS350-24T-4G / 3.4.0.17 | Cisco Business CLI; IOS/Meraki değildir | SNMPv3 exact model/firmware kanıtına koşullu |

Her profil ayrı `runtime_driver_id`, manifest, zorunlu kimlik komutu, interface
grameri ve tested-version kaydı taşır. Benzer banner görüldüğünde komut/parser
fallback'i yapılmaz. Yapılandırılan ve gözlenen profil farklıysa
`collector_platform_mismatch`; SSH ve SNMP kimliği çelişirse
`transport_identity_mismatch` üretilir.

## Legacy SSH sınırı

Comware V5 profili SSH-2 kullanır. `auto` bağlantı önce modern `standard`
algoritmaları dener. SHA-1/CBC/Group1 denemeleri ancak aynı cihaz kaydında
`allow_legacy_ssh=true` açıkça seçilmişse devreye girer. Bu izin profil veya
vendor seviyesinde paylaşılmaz; yeni VRP V600 ya da başka cihaz varsayılan olarak
yalnız `standard` dener. Global AsyncSSH/OpenSSH ayarı değiştirilmez.

## Linux, front-panel ve breakout kimliği

`linux_ssh`, iproute2 kullanan genel salt-okunur altyapı adaptörüdür; SONiC veya
Cumulus desteği anlamına gelmez. Cumulus profili NVUE'nin interface `type`
alanını doğrular:

- yalnız `type=swp` ve açık `front_panel_port` eşlemesi fiziksel port üretir;
- bond, bridge, VRF, loopback ve management nesneleri fiziksel port değildir;
- kernel interface ID'si, front-panel physical-port ID'si ve breakout child ID'si
  ayrı tutulur;
- breakout child, kanıtlı parent portuna `parent_port_id` ile bağlanır; modelden
  port geometrisi tahmin edilmez.

Fixture `swp1s0`, `bond1`, `br_default` ve `BLUE` nesneleriyle bu sınırı test
eder. FRR routing tabloları bu sprintte capability olarak ilan edilmez.

## SONiC dağıtım sınırı

Dell Enterprise SONiC yalnız Dell distribution, software version, platform ve
service-tag kanıtı birlikteyken Dell runtime'ına bağlanır. Genel SONiC için
distribution, software version, platform ve image kimliği zorunludur. Genel
profile vendor adı model/platform metninden tahmin edilmez ve `Unknown` kalır.
Dell ve genel SONiC SNMP/API kanalları dağıtım-bazlı sözleşme kanıtı gelene kadar
`planned` durumundadır; yalnız SSH fixture'ı bu kanalları açmaz.

## Junos Evolved, VRP ve Cisco Business ayrımı

- Junos Evolved, klasik Junos'a benzer CLI/XML yüzeyi taşısa bile ayrı kimlik,
  command plan ve fixture kullanır. Bu teslim NETCONF adapter'ı uygulamaz.
- VRP V600, `huawei_vrp` legacy alias'ına veya V200 parser'ına çevrilmez. V200
  cihazındaki legacy SSH izni V600'e aktarılmaz.
- Cisco Business model adı tek başına yeterli değildir; CBS system description
  ile firmware version birlikte gerekir. Profilin command allowlist'i IOS veya
  Meraki komut planını açmaz.

## Hata ve veri koruma davranışı

- Zorunlu kimlik/interface komutunda timeout, yetki reddi veya parse hatası ilgili
  grubu fail-closed yapar; son doğru inventory silinmez.
- 64-bit sayaçlar korunur, ancak güvenilir epoch/poll aralığı yoksa hız
  türetilmez.
- FDB/ARP/LLDP ancak mevcut interface kimliğine bağlanabiliyorsa kabul edilir;
  eksik port, VLAN, vendor veya kablo ilişkisi tahmin edilmez.
- Ham CLI/XML/JSON çıktısı API, log veya veritabanına yazılmaz.
- SNMP yalnız v3 `authPriv`, bounded standard-MIB allowlist ve read-only işlemle
  çalışır; SET veya runtime MIB indirme yoktur.

## Kanıt ve fiziksel kabul

`backend/tests/fixtures/p3/manifest.json` dokuz fixture'ın SHA-256 özetini,
`physical_acceptance=false` ve `production_accepted=false` sınırını taşır.
Fixture metinleri proje tarafından üretilmiş parser girdileridir; üretici
cihazından alınmış transcript değildir. Gerçek çıktı varyantı, RBAC, SSH
algoritması, SNMPv3, breakout/ASIC mapping, büyük tablo ve performans S11'de exact
tuple ile doğrulanmalıdır. Kapasite/ölçek iddiası `REQUIRES BENCHMARK`tır.

## Üretici ve upstream referansları

- [H3C `display interface` command reference](https://www.h3c.com/en/Support/Resource_Center/EN/Home/Public/00-Public/Technical_Documents/Reference_Guides/Command_References/H3C_CR-24948/03/202502/2364078_294551_0.htm)
- [Huawei CloudEngine V600 product documentation index](https://info.support.huawei.com/info-finder/vue/en/enterprise/openSearch?keyword=CloudEngine%20V600R023)
- [Junos OS Evolved ile Junos OS farkları](https://www.juniper.net/documentation/us/en/software/junos/overview-evo/topics/concept/evo-how-it-differs-from-junos.html)
- [Junos `show interfaces extensive`](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/command/show-interfaces-extensive.html)
- [Dell Enterprise SONiC management-framework CLI](https://infohub.delltechnologies.com/en-us/l/enterprise-sonic-distribution-by-dell-technologies-lifecycle-management/management-framework-cli/)
- [NVIDIA Cumulus NVUE interface show commands](https://docs.nvidia.com/networking-ethernet-software/nvue-reference/Show-Commands/Interface/)
- [NVIDIA NVUE breakout davranışı](https://docs.nvidia.com/networking-ethernet-software/knowledge-base/Setup-and-Getting-Started/NVUE-Cheat-Sheet/)
- [NVIDIA Onyx command reference](https://docs.nvidia.com/networking/display/onyxv3104006/commands)
- [SONiC user manual](https://github.com/sonic-net/SONiC/blob/master/doc/user-manual/SONiC-User-Manual.md)
- [Cisco Business 350 interface commands](https://www.cisco.com/c/en/us/td/docs/switches/lan/csbms/CBS_250_350/CLI/cbs-350-cli-/ethernet-configuration-commands.html)
- [Cisco Business 350 system commands](https://www.cisco.com/c/en/us/td/docs/switches/lan/csbms/CBS_250_350/CLI/cbs-350-cli-/system-management-commands.html)
