# P2 Dell, Extreme ve FortiSwitch sürücü profilleri

Bu belge S07 ile uygulanan `dell_os10`, `dell_os9`, `dell_os6`,
`extreme_exos`, `extreme_fabric_engine`, `extreme_slxos` ve
`fortinet_fortiswitchos` profillerinin çalışan kullanıcı/operatör sözleşmesini
açıklar. Yedi profil `fixture_verified/experimental` durumundadır. Proje-sentetik
fixture, üretici çıktısı uygunluk kanıtı, fiziksel cihaz kabulü veya production
kabulü değildir.

## Ortak işletim ve güvenlik sınırı

1. Cihaz eklerken canlı katalogdan üretici, kanonik işletim sistemi profili ve
   `standalone` yönetim modu seçilir. `dell_force10` ve `extreme_vsp` eski
   runtime kimlikleri korunur; kanonik profile geçiş ancak cihaz kimliği
   doğrulandıktan sonra kaydedilir.
2. SSH hesabı yalnız profil manifestindeki salt-okunur komutlara yetkili
   olmalıdır. Configuration mode, shell, dosya yazma veya ayrıcalıklı değişiklik
   komutu kullanılmaz.
3. SSH host key kimlik bilgisi gönderilmeden önce doğrulanır. Zorunlu kimlik veya
   interface komutunda timeout, yetki reddi, bozuk çıktı ya da yanlış OS kanıtı
   fail-closed sonuç üretir; son doğru envanter silinmez.
4. SNMP yalnız v3 `authPriv` ve bounded standard-MIB allowlist'i ile çalışır.
   SNMPv1/v2c, SET ve runtime MIB indirme yoktur. Fabric Engine SSH secure mode
   SNMP'yi kapatabiliyorsa bu durum açık transport kısıtı olarak yayımlanır.
5. Fan, PSU, PoE, DOM veya transceiver alanları model isminden türetilmez.
   S07'nin SSH manifestleri bu sağlık alanlarını ilan etmez; yalnız kanıtlı
   standard ENTITY-SENSOR sıcaklık yolu SNMP capability'si olarak kalır.

## Profil ve kimlik matrisi

| Profil | Runtime ID | Fixture tuple | Parser/kimlik sınırı | Yayın/kabul |
|---|---|---|---|---|
| `dell_os10` | `dell_os10` | S5248F-ON / 10.5.6.1 | SmartFabric OS10 banner'ı; OS9/OS6/SONiC parser'ına düşmez | `experimental`; fiziksel kabul yok |
| `dell_os9` | `dell_force10` | S4048-ON / 9.14(2.20) | OS9 veya FTOS kanıtı; aynı modelde OS10/SONiC reddedilir | `experimental`; alias yeniden doğrulanır |
| `dell_os6` | `dell_os6` | N3248X-ON / 6.8.1.0 | N-series OS6 komut ve interface grameri ayrıdır | `experimental`; fiziksel kabul yok |
| `extreme_exos` | `extreme_exos` | X465-48T / 33.3.1.4 | `ExtremeXOS` ve `Switch Engine` açık OS alias metadata'sıdır | `experimental`; fiziksel kabul yok |
| `extreme_fabric_engine` | `extreme_vsp` | 5520-48T / 9.3.2.0 | `Fabric Engine`/`VOSS`; secure mode SNMP kararını etkileyebilir | `experimental`; alias yeniden doğrulanır |
| `extreme_slxos` | `extreme_slxos` | SLX 9150-48Y / 20.6.3b | SLX-OS, EXOS/VOSS komut ailesine düşmez | `experimental`; fiziksel kabul yok |
| `fortinet_fortiswitchos` | `fortinet_fortiswitchos` | FortiSwitch-124F / 7.6.2 | Yalnız standalone FortiSwitchOS; FortiLink ve FortiOS ayrıdır | `experimental`; fiziksel kabul yok |

Fixture interface adları `ethernet1/1/1`, `TenGigabitEthernet1/0/1`,
`Gi1/0/1`, `1:1`, `1/1`, `Ethernet 1/0/1` ve `port1` biçimlerini kapsar.
Stack/slot/virtual-chassis kimliği normalize edilerek kaybedilmez. Her fixture
`2^32` üstü RX/TX sayaçlarını 64-bit olarak doğrular; sayaç epoch kanıtı yoksa
`counter_epoch_known=false` kalır.

## Salt-okunur SSH komut allowlist'leri

### Dell SmartFabric OS10

```text
show version
show interface
show vlan
show mac address-table
show ip arp
show lldp neighbors
```

### Dell Networking OS9 / FTOS

```text
show version
show interfaces
show vlan
show mac-address-table
show arp
show lldp neighbors
```

### Dell Networking OS6 / N-series

```text
show version
show interfaces
show vlan
show mac address-table
show arp
show lldp remote-device all
```

Dell profilleri yalnız bounded alan dönüştürücüleri paylaşır. Kimlik, interface
ve komut sözleşmeleri ayrıdır. `Dell Enterprise SONiC` tanınır fakat S09'daki
`dell_sonic` profili uygulanana kadar P2 parser'larından hiçbirine bağlanmaz.

### ExtremeXOS / Switch Engine

```text
show version
show ports statistics no-refresh
show vlan
show fdb
show iparp
show lldp neighbors
```

### Extreme Fabric Engine / VOSS

```text
show sys-info
show interfaces
show vlan members
show mac-address-table
show ip arp
show lldp neighbor
```

`SSH Secure Mode: Enabled` kimlik çıktısı görüldüğünde inventory payload'ı
`snmp=blocked_by_ssh_secure_mode` kısıtını taşır. Bu gözlem cihaz üzerinde SNMP
ayarını değiştirmez ve SSH sonucundan SNMP erişiminin başarılı olduğunu varsaymaz.

### Extreme SLX-OS

```text
show version
show interface
show vlan brief
show mac-address-table
show arp
show lldp neighbors detail
```

### FortiSwitchOS standalone

```text
get system status
diagnose switch physical-ports list
get switch vlan
diagnose switch mac-address list
get system arp
diagnose lldprx neighbor summary
```

`get system status` standalone yönetim modunu kanıtlamalıdır. FortiLink-managed
switch `fortinet_fortiswitch_fortilink` olarak tanınır ama S08 tamamlanana kadar
toplanmaz. FortiGate/FortiOS aynı sürücü değildir. Eski `fortinet` kimliği bu üç
olasılıktan birine otomatik çevrilmez ve yönetici çözümü ister. API transportu
TLS/CA, token scope ve controller modeli tanımlayan ADR-COMPAT-004 tamamlanana
kadar `blocked` kalır.

## Capability ve hata davranışı

- SSH kimlik/model/sürüm/seri, interface, 64-bit sayaç, VLAN, FDB, ARP ve LLDP
  alanlarını yalnız parse edilen kanıtla yayımlar. Ortak SNMPv3 çekirdeği system,
  IF/IF-X, Q-BRIDGE, LLDP ve sınırlı ENTITY alanlarını sağlayabilir.
- FDB ile ARP yalnız aynı VLAN ve MAC kanıtıyla uç noktaya bağlanır. Eksik VLAN,
  port veya adres tahmin edilmez.
- Opsiyonel network komutu eksikse grup `partial`; zorunlu identity/interface
  komutu okunamıyorsa ilgili grup `error` olur. Ham CLI, kullanıcı adı veya cihaz
  hata metni API/DB'ye yazılmaz.
- Yapılandırılmış profil ile gözlenen kanonik kimlik farklıysa parser fallback
  yapmaz ve `collector_platform_mismatch` üretir. SSH ile SNMP kimliği
  çelişirse ortak transport katmanı `transport_identity_mismatch` ile durur.
- `fortinet_fortiswitch_fortilink`, `dell_sonic` ve FortiOS tanınsa da bu S07
  runtime'larına yönlendirilmez.

## Fiziksel kabul için kalan iş

Her profil exact model, hardware revision, OS sürümü, management mode,
transport/security profile ve capability kimliğiyle
[`KABUL_VE_KANIT_SABLONU.md`](KABUL_VE_KANIT_SABLONU.md) üzerinden S11'de ayrıca
doğrulanmalıdır. Gerçek cihaz SSH çıktı varyantları, minimum RBAC, SNMPv3,
stack/virtual-chassis port kimliği, büyük FDB/ARP tabloları ve performans henüz
kanıtlanmamıştır. Süresi geçmemiş fiziksel kayıt olmadan `supported` veya
`production_accepted=true` yapılamaz; kapasite iddiası `REQUIRES BENCHMARK`tır.

## Üretici referansları

- [Dell SmartFabric OS10 LLDP CLI](https://www.dell.com/support/manuals/en-us/dell-emc-smartfabric-os10/smartfabric-os-user-guide-10-5-2-6/show-lldp-neighbors?guid=guid-cf4a7765-02fd-4278-9bcb-c49088ba61e5&lang=en-us)
- [Dell Networking OS6 CLI reference](https://dl.dell.com/manuals/common/n-series-v663_cli_en-us.pdf)
- [Extreme Switch Engine port configuration](https://documentation.extremenetworks.com/Switch%20Engine%20v33.5.1%20User%20Guide/repositories/master/content/documents/Switch_Operating_Systems/Switch_Engine/User_Guide/show_ports_configuration.shtml)
- [Extreme Fabric Engine SSH secure mode](https://documentation.extremenetworks.com/Fabric%20Engine%20v9.3%20User%20Guide/content/documents/Switch_Operating_Systems/VOSS_and_Fabric_Engine/fabric_engine_user_guide/ssh_version_2.shtml)
- [FortiSwitchOS `get` command reference](https://docs.fortinet.com/document/fortiswitch/7.6.2/fortiswitchos-cli-reference/896953/get)
- [FortiSwitchOS `diagnose` command reference](https://docs.fortinet.com/document/fortiswitch/7.6.2/fortiswitchos-cli-reference/452179/diagnose)
