# NetStudio — Switch İşletim Sistemi, SSH ve SNMP Uyumluluk Matrisi

**Hazırlanma tarihi:** 21 Ekim 2026  
**Kapsam:** Cisco, HPE Aruba Networking, Huawei, Arista, Juniper, Dell, H3C, Extreme Networks, Fortinet, MikroTik, Ubiquiti, TP-Link, NVIDIA Networking (13 üretici).  
**Hedef:** NetStudio için işletim sistemi ailesi bazlı sürücü ve protokol destek planı.  
**NetStudio kaynak deposu:** https://github.com/KES-KING/NetStudio  
**Mevcut ürün sözleşmesi:** https://github.com/KES-KING/NetStudio/blob/main/docs/collection-automation.md

> **Not:** Bu tablo üretici yazılımının SSH/SNMP kabiliyetini gösterir; NetStudio'da o platformun tüm modellerinin desteklendiğini iddia etmez. Sürüm, lisans, model, yönetim modu ve yapılandırmaya göre özellikler değişebilir. SSH/SNMP genellikle güvenlik nedeniyle cihaz üzerinde ayrıca etkinleştirilmelidir. Bir marka tek bir işletim sistemi kullanmaz.

## Durum anahtarı

- **Evet:** Üretici/platform ailesinde ilgili yönetim protokolü mevcuttur; cihazda etkin ve erişilebilir olması gerekir.
- **Koşullu:** Model, firmware, lisans veya yönetim moduna bağlıdır; kesin destek için cihaz belgesiyle doğrulayın.
- **Hayır:** Belirtilen seri/çalışma modunda ilgili yerel yönetim protokolü yoktur.
- **Temel:** NetStudio'da ilgili aile için temel okuma/test mevcuttur; gerçek donanım kabulü garanti değildir.
- **Deneysel:** NetStudio'da kısmi/deneysel sürücü mevcuttur.
- **Katalogda planlı:** `driver_catalog.py` içinde `available=false` sınıfında; çalışan sürücü değildir.
- **Yeni adaptör:** Mevcut belgelerde ayrı ve doğrulanmış NetStudio sürücüsü belirtilmiyor; geliştirme gerektirir.

## 1. Marka × işletim sistemi × SSH × SNMP matrisi

| Marka | İşletim sistemi / cihaz ailesi | SSH (22/TCP) | SNMP (161/UDP) | NetStudio (belgelenen durum) | Önerilen sürücü kimliği | Teknik not / sınır | Üretici belgesi |
|---|---|---|---|---|---|---|---|
| Cisco | **IOS** (eski Catalyst, ör. 2960-X) | Evet, SSHv2 | v1/v2c/v3 | **Temel** (2960-X ayrıştırıcı testli) | `cisco_ios` | Model ve IOS sürümüne göre CLI farklılıkları | [Cisco](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9300/software/release/17-17/configuration_guide/sec/b_1717_sec_9300_cg/secure_shell_version_2_support.html) |
| Cisco | **IOS XE** (Catalyst 9xxx vb.) | Evet, SSHv2 | v1/v2c/v3 | **Deneysel** | `cisco_iosxe` | IOS komutlarıyla ortak alanlar var; IOS ile aynı parser kabul edilmeyin | [Cisco](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9300/software/release/17-17/configuration_guide/sec/b_1717_sec_9300_cg/secure_shell_version_2_support.html) |
| Cisco | **NX-OS** (Nexus) | Evet, SSHv2 | v1/v2c/v3 | **Deneysel** | `cisco_nxos` | NX-OS JSON/CLI çıktısı ve interface adları farklı | [Cisco](https://www.cisco.com/c/en/us/td/docs/switches/datacenter/sw/5_x/nx-os/system_management/configuration/guide/sm_nx_os_cg/sm_9snmp.html) |
| Cisco | **Cisco Business switch firmware** (CBS250/CBS350 vb.) | Koşullu; yönetilebilir modellerde evet | Koşullu; CBS350'de v1/v2c/v3 | **Yeni adaptör** | `cisco_business` | Cisco IOS değildir; Meraki ile de karıştırılmamalı | [Cisco](https://www.cisco.com/c/en/us/td/docs/switches/lan/csbms/CBS_250_350/Administration-Guide/cbs-350/cbs_350_chapter_17.html) |
| Cisco | **Meraki MS / bulut-yönetimli firmware** | **Hayır** (standart cihaz CLI/SSH yönetimi) | Koşullu; Dashboard üzerinden SNMP | **Yeni API/SNMP adaptörü** | `cisco_meraki_ms` | Dashboard API veya SNMP; klasik SSH sürücüsü değil | [Meraki](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Monitoring_and_Reporting/Meraki_Device_Reporting_-_Syslog%2C_SNMP%2C_and_API) |
| HPE Aruba Networking | **AOS-CX** (CX 6xxx/8xxx vb.) | Evet | v1/v2c/v3 | **Katalogda planlı** | `aruba_aoscx` | REST API/NETCONF olan modeller için ikinci yönetim kanalı düşünülebilir | [Aruba](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.16/HTML/fundamentals_6300-6400/Content/Chp_SNMP/cnf-snm.htm) |
| HPE Aruba Networking | **AOS-Switch / ArubaOS-Switch (ProVision)** | Evet | v1/v2c/v3 (sürüme göre) | **Katalogda planlı** | `aruba_aoss` | AOS-CX ile CLI ve çıktı biçimleri uyumsuz olabilir | [Aruba](https://arubanetworking.hpe.com/techdocs/AOS-S/16.11/ASG/WC/content/common%20files/cnf-swi-ssh-ope.htm) |
| HPE Aruba Networking | **Comware / FlexNetwork** (HPE eski switch ürünleri) | Evet | v1/v2c/v3 | **Comware ailesi katalogda planlı** | `hpe_comware` | H3C Comware ile akraba; vendor ve sürüm imzasıyla eşleştirilmeli | [H3C](https://www.h3c.com/en/Products_and_Solutions/InterConnect/Operating_System/Comware_V7/) |
| HPE Aruba Networking | **Instant On switch firmware** (1830/1930/1960 vb.) | **Hayır** (kullanıcı CLI/SSH sunucusu) | Koşullu; yerel yönetimde özellikle 1930 ailesinde destek | **Yeni SNMP/web adaptörü** | `aruba_instant_on` | Bulut modu ile yerel mod aynı yetenekleri sunmayabilir | [Instant On](https://community.instant-on.hpe.com/discussion/aruba-instant-on-1960) |
| Huawei | **VRP V200 / VRP 5.x** (eski S serisi) | Evet (STelnet/SSHv2) | v1/v2c/v3 | **Temel** (S5700/VRP 5 biçimi testli) | `huawei_vrp_v200` | Eski SSH algoritması gereksinimi cihaz bazlı izinle yönetilmeli | [Huawei](https://support.huawei.com/enterprise/en/doc/EDOC1100468733/f596198f/configuring-a-device-to-communicate-with-an-nms-through-snmpv3-usm-user) |
| Huawei | **VRP V600 / yeni CloudEngine yazılımı** | Evet (STelnet/SSHv2) | v1/v2c/v3; güvenli kurulumda v3 | **Yeni sürüm profili / cihaz kabulü gerekli** | `huawei_vrp_v600` | V200 parser'ı otomatik uyumlu varsayılmamalı | [Huawei](https://support.huawei.com/enterprise/de/doc/EDOC1100246292/7fd9af89/management-plane-security-level-1) |
| Arista Networks | **EOS / Arista EOS** | Evet | v1/v2c/v3 | **Katalogda planlı** | `arista_eos` | eAPI ve komut JSON çıktıları kullanılabilir | [Arista](https://www.arista.com/en/um-eos/eos-snmp) |
| Juniper Networks | **Junos OS** (EX/QFX vb.) | Evet | v1/v2c/v3 | **Deneysel** | `juniper_junos` | XML/RPC veya NETCONF ile parser kararlılığı artırılabilir | [Juniper](https://www.juniper.net/documentation/us/en/software/junos/network-mgmt/topics/topic-map/configure-snmp-in-junos-os.html) |
| Juniper Networks | **Junos OS Evolved** (seçili platformlar) | Evet | v1/v2c/v3 (platform/sürüme göre) | **Yeni sürüm profili** | `juniper_junos_evolved` | Standart Junos ile aynı şablonları otomatik varsaymayın | [Juniper](https://www.juniper.net/documentation/us/en/software/junos/user-access-evo/user-access/topics/topic-map/junos-software-remote-access-overview.html) |
| Dell Technologies | **SmartFabric OS10 / OS10** | Evet | v1/v2c/v3 | **Katalogda planlı** | `dell_os10` | Sunucu leaf/spine ve kampüs şablonları ayrılmalı | [Dell](https://www.dell.com/support/manuals/en-us/smartfabric-os10-emp-partner/smartfabric-os-user-guide-10-5-6/snmp-server-user?guid=guid-f9c36bdb-eefa-4744-b754-982214de1718&lang=en-us) |
| Dell Technologies | **Dell Networking OS9 / FTOS** | Evet | v1/v2c/v3 (model/sürüme göre) | **Katalogda planlı** | `dell_os9` | OS10'dan farklı CLI | [Dell](https://www.dell.com/support/home/en-us) |
| Dell Technologies | **Dell Networking OS6** (N serisi) | Evet | v1/v2c/v3 | **Yeni adaptör** | `dell_os6` | Ayrı CLI; N serisi için özel parser | [Dell](https://www.dell.com/support/kbdoc/en-uk/000133707/how-to-configure-snmpv3-on-dell-emc-networking-n-series-switches) |
| Dell Technologies | **Dell Enterprise SONiC** | Evet | v2c/v3; v1 varsayılmamalı | **Yeni adaptör** | `dell_sonic` | Linux tabanlı NOS; `SNMP SET` desteği varsayılmamalı | [Dell](https://www.dell.com/support/kbdoc/en-in/000222508/dell-networking-sonic-how-to-configure-snmp-v2c) |
| H3C | **Comware V5** | Evet | v1/v2c/v3 (sürüme göre) | **Comware ailesi katalogda planlı** | `h3c_comware5` | Legacy çıktı ve SSH farkları | [H3C](https://www.h3c.com/en/Products_and_Solutions/InterConnect/Operating_System/Comware_V7/) |
| H3C | **Comware V7** | Evet | v1/v2c/v3 | **Katalogda planlı** | `h3c_comware7` | En geniş kurumsal switch profillerinden biri | [H3C](https://www.h3c.com/en/Products_and_Solutions/InterConnect/Operating_System/Comware_V7/) |
| H3C | **Comware V9** | Evet | v1/v2c/v3 | **Yeni sürüm profili** | `h3c_comware9` | V7 ile birebir CLI/özellik eşitliği varsayılmamalı | [H3C](https://www.h3c.com/en/Products_and_Solutions/InterConnect/Operating_System/Comware_V9/) |
| Extreme Networks | **ExtremeXOS (EXOS) / Switch Engine** | Evet | v1/v2c/v3 | **Katalogda planlı** | `extreme_exos` | Aynı OS ailesi farklı ürün/sürüm adlarıyla sunulabiliyor | [Extreme](https://documentation.extremenetworks.com/Switch%20Engine%20v33.3.1%20User%20Guide/repositories/master/content/documents/Switch_Operating_Systems/Switch_Engine/User_Guide/extremexos_switch_management_overview.shtml) |
| Extreme Networks | **VOSS / Fabric Engine** | Evet | v1/v2c/v3 (güvenlik moduna göre) | **Yeni adaptör** | `extreme_fabric_engine` | Bazı `ssh secure` modları SNMP'yi devre dışı bırakabilir | [Extreme](https://documentation.extremenetworks.com/Fabric%20Engine%20v9.3%20User%20Guide/content/documents/Switch_Operating_Systems/VOSS_and_Fabric_Engine/fabric_engine_user_guide/ssh_version_2.shtml) |
| Extreme Networks | **SLX-OS** (veri merkezi) | Evet | v1/v2c/v3 (model/sürüme göre) | **Yeni adaptör** | `extreme_slxos` | EXOS/VOSS ile ayrı komut ailesi | [Extreme](https://documentation.extremenetworks.com/Extreme%20SLX-OS%2020.6.3b%20Management%20Configuration%20Guide/DatacenterNetworking/SLX-OS/Master-Source/extreme_slx_os_management_configuration_guide/vrf_reachability_for_device_initiated_services_slxc.shtml) |
| Fortinet | **FortiSwitchOS**, bağımsız (standalone) | Evet | v1/v2c/v3 | **Katalogdaki `FortiOS` girdisi gözden geçirilmeli; FortiSwitchOS adaptörü gerekli** | `fortinet_fortiswitchos` | Switch OS adı **FortiSwitchOS**; **FortiOS**, FortiGate içindir | [Fortinet](https://docs.fortinet.com/document/fortiswitch/8.0.0/fortiswitchos-administration-guide/261585/snmp) |
| Fortinet | **FortiSwitchOS**, FortiLink/FortiGate yönetiminde | Koşullu; erişim yönetim politikasına bağlı | Koşullu; FortiLink/FortiGate üzerinden konfigürasyon gerekebilir | **Yeni yönetim-modu adaptörü** | `fortinet_fortiswitch_fortilink` | Standalone ve managed kipler arasında yönetim/kimlik ayrımı var | [Fortinet](https://community.fortinet.com/fortigate-3/troubleshooting-tip-configure-snmp-for-managed-fortiswitch-using-custom-command-98102) |
| MikroTik | **RouterOS v6/v7** (CRS vb.) | Evet | v1/v2c/v3 | **Katalogda planlı** | `mikrotik_routeros` | `RouterOS` terminal dili Cisco benzeri değil | [MikroTik](https://help.mikrotik.com/docs/spaces/ROS/pages/8978519/SNMP) |
| MikroTik | **SwOS / SwOS Lite** (CSS, bazı CRS) | **Hayır** | **Yalnız v1/v2c; v3 yok** | **Yeni SNMPv2c salt-okunur adaptör** | `mikrotik_swos` | SNMP GET/GETNEXT/GETBULK; SET ve trap yok | [MikroTik](https://help.mikrotik.com/docs/spaces/SWOS/pages/76415036/CRS3xx%2Band%2BCSS3xx%2Bseries%2BManual) |
| Ubiquiti | **UniFi switch firmware** (USW genel ailesi) | Koşullu; cihaz SSH/Debug erişimi var, esas yönetim yöntemi değil | v1/v2c/v3 (uyumlu modeller) | **Yeni SNMP/UniFi API adaptörü** | `ubiquiti_unifi_switch` | SSH yolunu sürekli yönetim API'si gibi ele almayın | [Ubiquiti](https://help.ui.com/hc/en-us/articles/33502980942615-SNMP-Monitoring-in-UniFi-Network) |
| Ubiquiti | **UniFi USW Flex / Ultra** istisnaları | Koşullu; debug/firmware | **Hayır** (resmî SNMP istisnası) | **UniFi Controller/API adaptörü gerekli** | `ubiquiti_unifi_no_snmp` | Bu cihazları genel UniFi SNMP profilinde eşleştirmeyin | [Ubiquiti](https://help.ui.com/hc/en-us/articles/33502980942615-SNMP-Monitoring-in-UniFi-Network) |
| Ubiquiti | **EdgeSwitch firmware / EdgeSwitch OS** | Evet | v1/v2c/v3 (yönetilen modeller) | **Yeni adaptör** | `ubiquiti_edgeswitch` | UniFi ailesiyle aynı cihaz protokolü sayılmamalı | [Ubiquiti](https://www.ui.com/edgemax/edgeswitch/) |
| TP-Link | **Omada / JetStream Managed Switch firmware** | Evet (model/sürüme göre) | v1/v2c/v3 (model/sürüme göre) | **Yeni adaptör** | `tplink_omada_managed` | Controller ile yönetiliyorsa SSH yalnız belirli işlemlere açık olabilir | [TP-Link](https://www.tp-link.com/id/business-networking/managed-switch/tl-sg3428/v2.20/) |
| TP-Link | **Omada Pro switch firmware** | Evet (model/sürüme göre) | v1/v2c/v3 (model/sürüme göre) | **Yeni adaptör** | `tplink_omada_pro` | Kurumsal ürünleri klasik JetStream parser'ından ayrı test edin | [TP-Link](https://www.tp-link.com/id/business-networking/omada-pro-switch-poe/s5500-24f4xf/) |
| TP-Link | **Easy Smart switch firmware** | **Hayır** (çoğunda SSH CLI yok) | **Hayır** (çoğunda SNMP yok) | **Protokol kapsamı dışında** | `tplink_easy_smart` | Model bazlı istisna doğrulanmadıkça SSH/SNMP desteği vaat etmeyin | [TP-Link](https://www.tp-link.com/tr/support/faq/1150/) |
| TP-Link | **Unmanaged / yönetilemeyen switch** | **Hayır** | **Hayır** | **Yönetim adaptörü mümkün değil** | `unmanaged_switch` | Yalnız komşu cihaz LLDP/FDB gözlemiyle dolaylı görünürlük | [TP-Link](https://www.tp-link.com/sg/support/faq/4043/) |
| NVIDIA Networking | **Cumulus Linux** (Spectrum Ethernet) | Evet | v1/v2c/v3 (`snmpd` etkinse) | **Mevcut jenerik Linux SSH sınırlı; NOS adaptörü yeni** | `nvidia_cumulus_linux` | NVUE/FRR/ASIC port yapılarını salt `iproute2` verisinden çıkarmayın | [NVIDIA](https://docs.nvidia.com/networking-ethernet-software/cumulus-linux-518/System-Configuration/Authentication-Authorization-and-Accounting/SSH-for-Remote-Access/) |
| NVIDIA Networking | **Onyx / önceki Mellanox Onyx OS** | Evet | v1/v2c/v3 | **Yeni adaptör** | `nvidia_onyx` | Cumulus Linux ile CLI komutları aynı değil | [NVIDIA](https://networking-docs.nvidia.com/onyxum/3.10.4800/network-management-interfaces) |
| NVIDIA Networking | **SONiC (Spectrum üzerinde, seçili dağıtımlar)** | Evet | **Dağıtıma/image'a bağlı**; v2c/v3 yaygın | **Yeni adaptör** | `sonic_nos` | SONiC, bir NVIDIA donanım modeli değil; OS ve dağıtım ayrıca tespit edilmeli | [Dell SONiC örneği](https://www.dell.com/support/kbdoc/en-in/000222508/dell-networking-sonic-how-to-configure-snmp-v2c) |

**Genel yorum:** Cisco IOS, IOS XE ve NX-OS; Aruba AOS-CX ve AOS-Switch; Huawei VRP; Arista EOS; Junos; Dell OS; H3C Comware; Extreme EXOS/VOSS; FortiSwitchOS; RouterOS; TP-Link Omada gibi yönetilebilir platformlar SSH ve SNMP yeteneği sunar. Ancak **Meraki bulut modu**, **SwOS**, **UniFi istisna modelleri**, **Aruba Instant On'un bazı yönetim modları**, **TP-Link Easy Smart** ve **unmanaged switch'ler** için bu cümle genellenemez.

## 2. NetStudio'nun mevcut fiilî kapsamı (repo belgesine göre)

| Seviye | İşletim sistemleri | Mevcut kanıt / sınır |
|---|---|---|
| Temel sürücü/test | Cisco IOS (özellikle 2960-X), Huawei VRP (özellikle S5700 / VRP 5) | Örnek çıktı/ayrıştırıcı testleri var; gerçek cihazdan genel kabul iddia edilmiyor |
| Deneysel | Cisco IOS XE, Cisco NX-OS, Juniper Junos | Cihaz/sürüm bazlı kabul eksik |
| Genel Linux | Linux SSH salt-okunur kolektörü | Cumulus/SONiC için tam NOS özelliği anlamına gelmez |
| Katalogda, kapalı | Aruba AOS-CX/AOS-Switch, Comware, Arista EOS, MikroTik RouterOS, FortiOS, Dell OS9/10, Extreme | `available=false`, üretime hazır sürücü değil |
| Kaynak protokol | SSH ve opsiyonel **SNMPv3 authPriv** (IF-MIB) | Bugün **SNMPv1/v2c kullanılmıyor** |

Kaynak: [NetStudio koleksiyon otomasyon dokümanı](https://github.com/KES-KING/NetStudio/blob/main/docs/collection-automation.md), [NetStudio README](https://github.com/KES-KING/NetStudio).

**Terminoloji düzeltmesi:** Fortinet switch işletim sistemi **FortiSwitchOS**'tur; **FortiOS** FortiGate güvenlik duvarı işletim sistemidir. Mevcut katalogdaki `FortiOS` planı switch desteği açısından yeniden adlandırılmalı veya ayrı tutulmalıdır.

## 3. Önerilen tasarım: SSH/SNMP özelliklerini sürücüden ayırın

Cihaz desteğini yalnız `vendor` ile değil, `vendor + os_family + os_version + model + management_mode` ile eşleştirin. SSH sunucusu bulunması bir SSH CLI sürücüsünün o cihazdan doğru FDB/VLAN/port verisi okuyabildiğini **göstermez**.

```yaml
# Örnek: sürücü kataloğu metaverisi — doğrudan mevcut NetStudio şeması değildir.
id: mikrotik_swos
vendor: MikroTik
os_family: SwOS
management_mode: standalone
transport:
  ssh:
    supported: false
  snmp:
    supported: true
    versions: [v1, v2c]
    preferred: v2c
    read_only: true
    traps: false
features:
  system_identity: true
  interfaces: true
  counters_if_mib: true
  fdb_bridge_mib: true
  lldp: conditional
  vlan_inventory: conditional
  configuration_write: false
netstudio:
  implementation: planned
  acceptance: not_tested
```

Aynı örüntüde her driver için **protokol erişimi**, **metrik kapsaması**, **uygulanma durumu** ve **cihaz üstünde kabul durumu** ayrı alanlar olmalıdır.

### Öncelikli toplama kapsamı

| Veri ailesi | Öncelikli standart | Ek kontrol |
|---|---|---|
| Sistem kimliği | SNMPv2-MIB: `sysObjectID`, `sysDescr`, `sysName`, `sysUpTime` | Üretici/OS/model doğrulama, CLI `show version` ile çapraz kontrol |
| Port envanteri ve sayaç | IF-MIB / IF-X-MIB | `ifHighSpeed`, 64-bit `ifHCInOctets` ve `ifHCOutOctets`, wrap/reboot koruması |
| MAC/FDB | BRIDGE-MIB, Q-BRIDGE-MIB | VLAN/FID, bridge port → `ifIndex` eşlemesi; MAC → IP çıkarımı doğrudan yapılmamalı |
| Fiziksel modüller | ENTITY-MIB, ENTITY-SENSOR-MIB ve vendor MIB | Stack, PSU/fan, transceiver, PoE modele göre değişir |
| LLDP komşuluk | LLDP-MIB / üretici CLI | Yerel port → uzaktaki chassis/port eşleşmesinin kanıtı saklanmalı |
| VLAN, STP, LAG, ACL | IEEE MIB'leri + CLI/REST/NETCONF/üretici MIB | Evrensel tek parser değildir; alan bazlı capability gerekir |

## 4. SNMP güvenlik ve sürüm stratejisi

1. **Varsayılan:** SNMPv3 `authPriv` ve salt-okunur kullanıcı. Mevcut NetStudio yaklaşımını koruyun.
2. **Geriye dönük uyumluluk:** SNMPv2c **yalnız açık kullanıcı etkinleştirmesi**, kaynak IP ACL'si, yönetim VLAN/VRF'si ve erişim denetimiyle kullanılabilir. SwOS gibi SNMPv3 sunmayan cihazlar için zorunlu alternatif olabilir. SNMPv1'ı ancak ayrı ve yüksek riskli uyumluluk profili olarak değerlendirin.
3. **Kimlik doğrulama / şifreleme:** SNMPv2c topluluk dizesi gizli sanılmamalı; şifreleme sağlamaz. SNMPv3 desteklenen aygıtlarda SHA/AES türevleri ve güçlü kimlik bilgileri tercih edilmeli.
4. **Salt-okunur:** Polling için SNMP `GET`, `GETNEXT`, `GETBULK` yeterlidir. `SET` ve üretim konfigürasyon değişikliği otomatik açılmamalı.
5. **SSH:** SSHv2 ve host-key pinning varsayılan. Eski KEX/şifre kümeleri yalnız açık cihaz bazlı istisnayla; bilinmeyen anahtar sessizce kabul edilmesin.
6. **Portlar:** SSH varsayılan TCP/22; SNMP polling UDP/161; SNMP trap/inform çoğunlukla UDP/162. Portların açık olması protokol yeteneği anlamına gelmez.

## 5. Geliştirme sprint sıralaması

| Dalga | Driver ailesi | Çıktı / kabul kriteri |
|---|---|---|
| P0 | Cisco IOS, IOS XE, NX-OS; Huawei VRP; Junos | Mevcut sürücüler için fixture testleri + kontrollü fiziksel cihaz kabulü; sürüm ailelerine ayrım |
| P1 | Aruba AOS-CX / AOS-Switch; Arista EOS; Comware V7; MikroTik RouterOS | CLI SSH kimlik doğrulama, sistem/port/MAC/VLAN/LLDP/sayaç ayrıştırması, SNMPv3 fallback |
| P2 | Dell OS10/OS9/OS6, FortiSwitchOS, Extreme EXOS/VOSS, TP-Link Omada/JetStream, Ubiquiti UniFi/EdgeSwitch | Her OS/model için parser; UniFi ve FortiLink yönetim modları ayrıca |
| P3 | H3C Comware V5/V9, Huawei V600, Junos Evolved, Dell SONiC, NVIDIA Cumulus/Onyx/SONiC, Cisco Business | İleri düzey NOS ve legacy sistem doğrulama, üretici API/CLI alternatifleri |
| P4 | MikroTik SwOS, Meraki MS, Aruba Instant On, TP-Link'in sınırlı yönetilen aileleri | SNMPv2c için açık opt-in veya üretici API; SSH/SNMP olmayanları `unsupported-by-protocol` olarak işaretleme |

**Kabul testlerinde:** Cihaz modeli, yazılım versiyonu, `sysObjectID`, SSH erişimi, SNMP protokolü, `ifIndex`–arayüz adı eşlemesi, VLAN/FDB, LLDP komşuluk, RX/TX 64-bit sayaç, yeniden başlatma sonrası kimlik, erişim hataları, eksik/pars edilemeyen alanların güvenli raporlanması ve performans ölçümleri ayrı ayrı sınanmalı. Çalışmayan sürücü üretime hazır olarak listelenmemeli.

## 6. Üretici kaynakları ve kararları

- [NetStudio güncel sürücü ve SNMP kapsamı](https://github.com/KES-KING/NetStudio/blob/main/docs/collection-automation.md).
- [Arista EOS SNMP yapılandırması](https://www.arista.com/en/um-eos/eos-snmp).
- [Juniper Junos SNMP yönetimi](https://www.juniper.net/documentation/us/en/software/junos/network-mgmt/topics/topic-map/configure-snmp-in-junos-os.html).
- [MikroTik SwOS SNMP v1/v2c sınırları](https://help.mikrotik.com/docs/spaces/SWOS/pages/76415036/CRS3xx%2Band%2BCSS3xx%2Bseries%2BManual).
- [MikroTik RouterOS SNMP](https://help.mikrotik.com/docs/spaces/ROS/pages/8978519/SNMP).
- [UniFi desteklenen SNMP sürümleri ve Flex/Ultra istisnası](https://help.ui.com/hc/en-us/articles/33502980942615-SNMP-Monitoring-in-UniFi-Network).
- [TP-Link Easy Smart yönetim ayrımı](https://www.tp-link.com/tr/support/faq/1150/).
- [FortiSwitchOS SNMP](https://docs.fortinet.com/document/fortiswitch/8.0.0/fortiswitchos-administration-guide/261585/snmp).
- [NVIDIA Onyx yönetim protokolleri](https://networking-docs.nvidia.com/onyxum/3.10.4800/network-management-interfaces).

**Sonuç:** 13 markayı tek bir “marka sürücüsü” yerine **işletim sistemi ailesi ve çalışma modu** üzerinden yönetmek gerekir. NetStudio'nun sürücü kataloğu buna uygun bir başlangıçtır; bu matris ise geliştirilecek profilleri ve SSH/SNMP'nin bulunmadığı istisnaları birbirinden ayırır.
