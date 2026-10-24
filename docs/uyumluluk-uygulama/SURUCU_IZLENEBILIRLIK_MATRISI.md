# NetStudio sürücü izlenebilirlik matrisi

| Alan | Değer |
|---|---|
| Belge kimliği | `NETSTUDIO-COMPAT-TRACE-001` |
| Kaynak kapsam | [Switch OS / SSH / SNMP uyumluluk matrisi](../NetStudio_Switch_OS_SSH_SNMP_Uyumluluk_Matrisi.md) |
| Başlangıç kaynak kod tabanı | `fa1a40f` |
| Güncel uygulama | S07, 24 Ekim 2026; katalog `2026.10.24.2`, P0/P1/P2 uygulanan profil revizyonu `2` |
| Kullanım | Her hedef profilin implementasyon, sprint ve kabul izini tutmak |

## 1. Okuma kuralı

Bu tabloda “hedef transport”, üretici/platform kabiliyet matrisinden alınan
uygulama adayıdır; çalışan NetStudio desteği iddiası değildir. “Mevcut durum”
yalnız incelenen kaynak kod gerçeğini anlatır. “Minimum çıkış kanıtı” sağlanmadan
profil `supported` olamaz.

Kısaltmalar:

- `C`: katalog kaydı,
- `I`: adapter/parser uygulanmış,
- `F`: sanitized fixture doğrulanmış,
- `L`: gerçek protokol laboratuvarı doğrulanmış,
- `P`: belirtilen model/OS/mode tuple'ında fiziksel cihaz doğrulanmış,
- `B`: performans/soak benchmark'ı,
- `U`: protokol/politika gereği desteklenmez.

`C→I→F→L→P` ilerlemesi capability başınadır. Bir capability'nin `P` olması
diğerlerini otomatik yükseltmez.

## 2. P0 — Mevcut kod yollarını ayırma ve kabul

| Hedef profil | Eski/mevcut karşılık | Mevcut durum | Hedef transport | Sprint | Minimum destek çıkışı |
|---|---|---|---|---|---|
| `cisco_ios` | Aynı | I+F; bağımsız rev2 manifest, 2960-X/IOS 15.2 fixture ve standard-MIB alanları; `experimental` | SSH + SNMPv3 | S05 tamamlandı, S11 | Exact model/IOS ile interfaces, identity, FDB/VLAN/LLDP/counters için P |
| `cisco_iosxe` | Aynı | I+F; IOS'tan bağımsız rev2 manifest, C9200L/17.12.3 ve C9300/17.9.5 proje-sentetik fixture; `experimental` | SSH + SNMPv3 | S05 tamamlandı, S11 | En az bir Catalyst exact tuple üzerinde fiziksel P |
| `cisco_nxos` | Aynı | I; rev2 JSON interface/resource/FDB/LLDP/inventory eşlemesi ve standard-MIB alanları unit doğrulandı; `experimental` | SSH JSON + SNMPv3 | S05 tamamlandı, S11 | Exact Nexus/NX-OS tuple için P |
| `huawei_vrp_v200` | `huawei_vrp` koşullu alias/runtime | I+F; rev2 S5700/VRP V200 fixture, V600 fail-closed, secret/envanter korunur; `experimental` | SSH + SNMPv3 | S01, S02, S05 tamamlandı, S11 | Exact S5700/VRP tuple için P |
| `juniper_junos` | Aynı | I; rev2 XML interface/FDB/ARP/environment/LLDP/inventory ve standard-MIB alanları unit doğrulandı; Evolved fail-closed; `experimental` | SSH XML + SNMPv3 | S05 tamamlandı, S11 | Exact EX/QFX/Junos tuple için P |

P0'a eşlik eden `linux_ssh`, bir OS profilinden çok genel altyapı adaptörüdür.
Mevcut izole SSH lab kanıtı korunur; Cumulus/SONiC desteği olarak yeniden
etiketlenmez. P0 kanıt ve komut sınırları
[`P0_SURUCU_PROFILLERI.md`](P0_SURUCU_PROFILLERI.md) içinde tutulur. `F` işareti
fiziksel doğrulama değildir; IOS-XE fixture'ları gerçek cihaz kaydı değil,
proje-sentetik parser girdileridir.

## 3. P1 — Yaygın kurumsal platformlar

| Hedef profil | Eski/mevcut karşılık | Mevcut durum | Hedef transport | Sprint | Minimum destek çıkışı |
|---|---|---|---|---|---|
| `aruba_aoscx` | Aynı runtime ID | I+F; rev2 JSON CLI manifesti, JL658A/FL.10.13.1030 sentetik fixture; `experimental` | SSH JSON + SNMPv3; REST uygulanmadı | S06 tamamlandı, S11 | Exact CX tuple'da fiziksel P |
| `aruba_aoss` | `hp_procurve` runtime/alias | I+F; rev2 text manifesti, JL253A/WC.16.11.0016 sentetik fixture; secret/host key koruma testi; `experimental` | SSH + SNMPv3 | S01, S02, S06 tamamlandı, S11 | Exact AOS-S tuple'da fiziksel P |
| `arista_eos` | Aynı runtime ID | I+F; rev2 JSON CLI manifesti, 7050SX3/4.31.2F sentetik fixture; `experimental` | SSH JSON + SNMPv3; eAPI ADR-COMPAT-004 ile kapalı | S06 tamamlandı, S11 | Exact EOS tuple ve API seçilirse güven kapısı P |
| `hpe_comware` | `hp_comware` runtime/alias | I+F; rev2 HPE kimlik sınırı, JH390A/7.1.070 sentetik fixture; `experimental` | SSH + SNMPv3 | S01, S02, S06 tamamlandı, S11 | HPE marka/OS exact tuple fiziksel P |
| `h3c_comware7` | Ayrı kanonik/runtime ID | I+F; rev2 H3C V7 kimliği, S5560X/7.1.070 sentetik fixture; V5/V9 fail-closed; `experimental` | SSH + SNMPv3 | S06 tamamlandı, S11 | H3C V7 exact tuple fiziksel P |
| `mikrotik_routeros` | Aynı runtime ID | I+F; rev2 RouterOS grameri, CRS326/7.15.3 sentetik fixture; Cisco fallback yok; `experimental` | SSH + SNMPv3; API ADR-COMPAT-004 ile kapalı | S06 tamamlandı, S11 | RouterOS v6/v7 ve CRS tuple'ları ayrı fiziksel P |

## 4. P2 — Dell, Extreme, Fortinet ve kampüs ekosistemi

| Hedef profil | Eski/mevcut karşılık | Mevcut durum | Hedef transport | Sprint | Minimum destek çıkışı |
|---|---|---|---|---|---|
| `dell_os10` | Aynı runtime ID | I+F; rev2 S5248F-ON/10.5.6.1 sentetik fixture; OS9/SONiC fail-closed; `experimental` | SSH + SNMPv3 | S07 tamamlandı, S11 | Exact OS10 model/sürüm P |
| `dell_os9` | `dell_force10` | I+F; rev2 S4048-ON/9.14(2.20) sentetik fixture; alias kimlik kanıtı ister; `experimental` | SSH + SNMPv3 | S01, S02, S07 tamamlandı, S11 | FTOS/OS9 banner + exact tuple P |
| `dell_os6` | Ayrı kanonik/runtime ID | I+F; rev2 N3248X-ON/6.8.1.0 sentetik fixture; OS9/10'dan ayrı; `experimental` | SSH + SNMPv3 | S07 tamamlandı, S11 | N-series exact model/OS6 tuple P |
| `extreme_exos` | Aynı runtime ID | I+F; rev2 X465-48T/33.3.1.4 sentetik fixture; EXOS/Switch Engine metadata; `experimental` | SSH + SNMPv3 | S07 tamamlandı, S11 | EXOS/Switch Engine alias ve exact tuple P |
| `extreme_fabric_engine` | `extreme_vsp` | I+F; rev2 5520-48T/9.3.2.0 sentetik fixture; secure-mode SNMP kısıtı; `experimental` | SSH + SNMPv3 koşullu | S01, S02, S07 tamamlandı, S11 | VOSS/Fabric Engine kimliği, security mode ve exact tuple P |
| `extreme_slxos` | Ayrı kanonik/runtime ID | I+F; rev2 SLX 9150-48Y/20.6.3b sentetik fixture; EXOS/VOSS'tan ayrı; `experimental` | SSH + SNMPv3 | S07 tamamlandı, S11 | SLX exact model/sürüm P |
| `fortinet_fortiswitchos` | Yeni runtime ID; `fortinet` unresolved | I+F; rev2 FortiSwitch-124F/7.6.2 standalone sentetik fixture; FortiLink/FortiOS fail-closed; `experimental` | SSH + SNMPv3; API ADR-COMPAT-004 ile kapalı | S01, S02, S07 tamamlandı, S11 | Standalone mode + FortiSwitchOS exact tuple P |
| `fortinet_fortiswitch_fortilink` | Yok | Not implemented | FortiGate/controller API + koşullu SNMP | S08, S11 | Controller/switch identity ayrımı + managed mode P |
| `tplink_omada_managed` | Yok | Not implemented | Controller/SSH + SNMPv3 koşullu | S08, S11 | Exact JetStream/Omada model, firmware ve mode P |
| `tplink_omada_pro` | Yok | Not implemented | Controller/SSH + SNMPv3 koşullu | S08, S11 | Pro firmware/modeli klasik Omada'dan ayrı P |
| `ubiquiti_unifi_switch` | Yok | Not implemented | UniFi controller API + SNMP koşullu | S08, S11 | Destekli exact model/controller/firmware/mode P |
| `ubiquiti_unifi_no_snmp` | Yok | Not implemented; istisna profili | Controller API | S08, S10, S11 | Flex/Ultra istisna kimliği ve API capability P; SNMP U |
| `ubiquiti_edgeswitch` | Yok | Not implemented | SSH + SNMPv3 koşullu | S08, S11 | EdgeSwitch exact model/firmware P |

## 5. P3 — İleri ve legacy NOS profilleri

| Hedef profil | Eski/mevcut karşılık | Mevcut durum | Hedef transport | Sprint | Minimum destek çıkışı |
|---|---|---|---|---|---|
| `h3c_comware5` | Ortak planned Comware dışında ayrı ID yok | Not implemented | Legacy SSH koşullu + SNMPv3 | S09, S11 | Legacy güven izni + exact V5 tuple P |
| `h3c_comware9` | Yok | Not implemented | SSH + SNMPv3 | S09, S11 | V7'den ayrı exact V9 tuple P |
| `huawei_vrp_v600` | `huawei_vrp` ile temsil edilmemeli | Not implemented | SSH + SNMPv3 | S09, S11 | V200 parser'ından ayrı fixture + exact CloudEngine/VRP tuple P |
| `juniper_junos_evolved` | `juniper_junos` ile temsil edilmemeli | Not implemented | SSH XML/NETCONF + SNMPv3 | S09, S11 | Klasik Junos'tan ayrı exact Evolved tuple P |
| `dell_sonic` | `linux_ssh` tam destek değildir | Not implemented | SSH/API + SNMP dağıtıma bağlı | S09, S11 | Dell distribution/image/model exact tuple P |
| `nvidia_cumulus_linux` | Yalnız `linux_ssh` temel fallback | Generic Linux L; NOS capability yok | SSH/NVUE + SNMPv3 | S09, S11 | NVUE/FRR/ASIC port eşlemesi + exact Cumulus tuple P |
| `nvidia_onyx` | Yok | Not implemented | SSH + SNMPv3 | S09, S11 | Exact Onyx model/sürüm P |
| `sonic_nos` | `linux_ssh` tam destek değildir | Not implemented | SSH/API + SNMP image'a bağlı | S09, S11 | Distribution/image/vendor/model tuple ayrı P |
| `cisco_business` | Cisco IOS ile temsil edilmemeli | Not implemented | SSH + SNMP koşullu | S09, S11 | Exact CBS model/firmware tuple P |

## 6. P4 — API/SNMPv2c ve protokol kapsamı dışı profiller

| Hedef profil | Eski/mevcut karşılık | Mevcut durum | Hedef transport | Sprint | Minimum çıkış |
|---|---|---|---|---|---|
| `mikrotik_swos` | Yok | Not implemented; mevcut güvenlik v2c'yi yasaklar | SNMPv2c read-only, ADR'ye bağlı | S10, S11 | ADR kabulü + security test + exact SwOS tuple P; ret halinde policy U |
| `cisco_meraki_ms` | Yok | Not implemented | Dashboard API / koşullu SNMP | S08, S11 | API güven kapısı + exact org/network/model/firmware mode P |
| `aruba_instant_on` | Yok | Not implemented | Local SNMP/web veya cloud API, mode'a bağlı | S08, S10, S11 | Local/cloud mode ve exact model ayrı P veya U |
| `tplink_easy_smart` | Yok | Not implemented | Genel durumda yerel SSH/SNMP yok | S10 | Model bazlı kanıt yoksa U; yanlış credential formu gösterilmez |
| `unmanaged_switch` | Yok | Yönetim adapter'ı mümkün değil | Yok | S10 | `unsupported_by_protocol`; yalnız dolaylı LLDP/FDB görünürlüğü açıklanır |

## 7. Eski kimlik geçiş tablosu

| Eski ID | Kanonik hedef | Otomatik geçiş | Gerekçe |
|---|---|---|---|
| `huawei_vrp` | `huawei_vrp_v200` | Yalnız mevcut/gözlenen kimlik V200 ise | V600 aynı parser sayılmaz |
| `hp_procurve` | `aruba_aoss` | Evet, alias olarak; cihaz kimliği yine doğrulanır | Adlandırma modernizasyonu |
| `hp_comware` | `hpe_comware` | Evet, alias olarak; vendor/OS kanıtı korunur | Marka bağlamı |
| `dell_force10` | `dell_os9` | Koşullu | FTOS/OS9 kanıtı yoksa belirsiz |
| `extreme_vsp` | `extreme_fabric_engine` | Koşullu | VOSS/Fabric Engine sürüm/mode kanıtı gerekir |
| `fortinet` | Yok; yönetici çözümü | **Hayır** | FortiOS, FortiSwitchOS ve FortiLink mode birbirinden farklıdır |

Migration eski ID'yi audit/compatibility alanında tutar; sırları veya envanteri
yeniden yazmaz. Alias, support acceptance kanıtı değildir.

## 8. Capability kabul kapsamı

Her profil için uygulanabilir satırlar ayrı kapatılır:

| Kod | Capability | Asgari doğrulama |
|---|---|---|
| CAP-ID | Vendor/OS/model/version/mode identity | İki kaynak varsa çapraz kontrol; çelişkide fail-closed |
| CAP-IF | Arayüz envanteri ve kalıcı kimlik | Duplicate/rename/ifIndex değişimi negatif test |
| CAP-CTR | 64-bit RX/TX/error/discard | Reboot/wrap/discontinuity ve kaynak değişimi |
| CAP-VLAN | PVID/access/trunk/allowed VLAN | Eksik üyelikte partial; varsayım yok |
| CAP-FDB | VLAN/FID bağlı MAC tablosu | Bridge port→ifIndex kanıtı; MAC→IP tahmini yok |
| CAP-L3 | IP/ARP/NDP/VRF | VRF bilinmiyorsa açık `unknown`; yanlış birleşme yok |
| CAP-LLDP | Yerel port→uzak chassis/port | L2 gözlemi; fiziksel kablo iddiası yok |
| CAP-LAG | LAG ve üye portlar | Trafik toplamında double count yok |
| CAP-PHYS | Chassis/stack/module/port/breakout | Model adından geometri üretme yok |
| CAP-ENV | Fan/PSU/temp/PoE/transceiver/DOM | Yalnız explicit CLI/MIB/API kanıtı |

Bir profil yalnız CAP-ID ve CAP-IF sağlıyorsa diğer capability'ler görünür biçimde
`unsupported` veya `not_tested` kalır; “tam sürücü” etiketi kullanılmaz.

## 9. Kapsam bütünlüğü kontrolü

Kaynak matristeki 38 hedef kimlik bu dosyada bir kez yer almalıdır. CI için
önerilen kontrol:

1. Kaynak matristen backtick içindeki önerilen ID'leri çıkar.
2. Typed registry kanonik ID'lerini çıkar.
3. Bu belgenin satır ID'lerini çıkar.
4. Üç kümenin farkını sıfır bekle; `linux_ssh`, `iproute2`, `snmpd` gibi altyapı
   terimlerini açık allowlist ile hariç tut.
5. Duplicate alias/kanonik ID ve sahipsiz sprint ID'sinde testi başarısız yap.

Bu kontrol profil uygulandığını değil, kapsamın izsiz kaybolmadığını kanıtlar.

