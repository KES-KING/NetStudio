# P0 kanonik sürücü profilleri — kullanıcı ve operatör rehberi

Bu belge S05 ile uygulanan `cisco_ios`, `cisco_iosxe`, `cisco_nxos`,
`huawei_vrp_v200`, `juniper_junos` profilleri ile `linux_ssh` altyapı
adaptörünün gerçek kaynak sözleşmesini açıklar. Katalog veya fixture durumu
fiziksel cihaz ya da production kabulü değildir.

## Ortak kullanım ve güvenlik sınırı

1. Cihaz formunda kanonik profili ve doğru management mode'u seçin. Eski
   `huawei_vrp` kaydı veri uyumluluğu için korunur; V200 kimliği cihazdan
   doğrulanınca `huawei_vrp_v200` olarak çözülür.
2. SSH hedefi kayıtlı yönetim IP/portudur. Host key, kimlik bilgisi
   gönderilmeden önce ayrı kanaldan doğrulanıp onaylanmalıdır.
3. SSH hesabı yalnız aşağıdaki profil allowlist'inde bulunan `show`/`display`
   komutlarını çalıştırabilmelidir. Configuration mode, shell ve yazma yetkisi
   gerekmez.
4. SNMP kullanılıyorsa yalnız v3 `authPriv`, SHA-256 (açık legacy onayıyla
   SHA-1) ve AES-128 kabul edilir. SET, v1/v2c ve runtime MIB indirme yoktur.
5. Eksik yetki veya desteklenmeyen opsiyonel komut ilgili capability'yi
   `permission_denied`/`unsupported`/`partial` yapar; son doğru veri silinmez.

## Profil matrisi

| Profil | SSH parser/komut biçimi | SNMPv3 ortak alanları | Kanıt ve bilinen sınır |
|---|---|---|---|
| `cisco_ios` | IOS text; interface/status, CPU/RAM/environment, IP, FDB/ARP, switchport, LAG, LLDP, PoE, inventory | System, IF/IF-X, Q-BRIDGE FDB/VLAN, LLDP, ENTITY | 2960-X/15.2 fixture; fiziksel kabul yok |
| `cisco_iosxe` | Ayrı IOS-XE manifesti; mevcut adapter yalnız açıkça listelenen IOS-benzeri alt kümeyi paylaşır | Aynı standard MIB çekirdeği | C9200L 17.12.3 ve C9300 17.9.5 proje-sentetik fixture; fiziksel kabul yok |
| `cisco_nxos` | NX-OS JSON; interface, resources, FDB, LLDP, version, inventory | Aynı standard MIB çekirdeği | Sentetik JSON unit corpus; ARP/VLAN CLI eşlemesi ilan edilmez |
| `huawei_vrp_v200` | VRP V200 text; interface, CPU/RAM, IP, FDB/ARP, version | Aynı standard MIB çekirdeği | S5700/VRP V200 fixture; V600 bu parser'a düşmez |
| `juniper_junos` | Klasik Junos XML; interface, routing-engine/environment, FDB/ARP, LLDP, version/hardware | Aynı standard MIB çekirdeği | Sentetik XML unit corpus; Junos Evolved bu parser'a düşmez |
| `linux_ssh` | `iproute2` JSON ve `/proc`; NOS profili değildir | Uygulanmadı | İzole SSH transport lab; Cumulus/SONiC desteği sayılmaz |

Standard SNMP alanları profil manifestinde transport bazında ayrıca yayımlanır.
SNMPv2-MIB system identity ham cihaz adı olarak envantere yazılmaz; profil
kimliğini destekleyen kanıt olarak kalır. SSH ve tanınan SNMP işletim sistemi
kimliği çelişirse toplama sonucu profile bağlanmaz. IF/IF-X; admin/oper state,
kapasite, sayaçlar ve hata/discard alanlarını sağlar.
Q-BRIDGE FDB satırı ancak FID→VLAN, bridge-port→ifIndex ve mevcut kalıcı
interface kimliği birlikte çözülebiliyorsa kabul edilir. ARP, NDP, VRF, modelden
port geometrisi ve fiziksel kablo SNMP'den tahmin edilmez.

## Salt-okunur SSH komut allowlist'leri

### Cisco IOS

```text
show version
show interfaces
show interfaces status
show processes cpu
show memory statistics
show power inline
show environment all
show ip interface
show mac address-table
show arp
show interfaces switchport
show etherchannel summary
show lldp neighbors detail
show inventory
```

### Cisco IOS-XE

IOS-XE kendi manifestine sahiptir. Bugünkü reviewed alt küme IOS ile aynı komut
metinlerini içerir; iki tuple birbirini import/miras almaz. Bir profile yeni
komut eklemek diğerini değiştirmez.

### Cisco NX-OS

```text
show version | json
show interface | json
show system resources | json
show lldp neighbors detail | json
show mac address-table | json
show inventory | json
```

### Huawei VRP V200

```text
display version
display interface
display cpu-usage
display memory-usage
display ip interface brief
display mac-address
display arp all
```

Eski KEX/host-key algoritması gerekiyorsa yalnız cihaz bazlı açık legacy SSH
onayı kullanılır. `huawei_vrp` etiketi V600'e otomatik genişletilmez.

### Juniper Junos OS

```text
show version | display xml
show interfaces extensive | display xml
show chassis routing-engine | display xml
show chassis environment | display xml
show lldp neighbors | display xml
show ethernet-switching table | display xml
show arp no-resolve | display xml
show chassis hardware | display xml
```

XML external entity/DOCTYPE işlenmez. Junos Evolved banner'ı görülürse klasik
Junos profiliyle devam edilmez.

## Kimlik yeniden çözümü ve işletim davranışı

- Kimlik komutu, diğer profil komutlarından önce çalışır.
- IOS ve IOS-XE, VRP V200 ve V600, klasik Junos ve Junos Evolved ile NX-OS
  birbirine varsayımla eşitlenmez.
- Önceden eşleşmiş cihazın vendor/model/OS ailesi/sürümü değişirse profil binding'i
  yeniden hesaplanır. Çelişkide durum `conflict`, catalog-only yeni ailede
  `unsupported` olur.
- SNMP `sysUpTime` geriye giderse reboot kabul edilir; çözülmüş kimlik ve derived
  command/capability cache geçersizleşir, inventory yeniden planlanır.
- Bu işlem cihaz kaydını, envanteri, sırları, host key'i, telemetry last-good
  verisini veya job geçmişini silmez.

## Yayın ve kabul sınırı

Beş P0 profilinin release durumu `experimental` kalır. Repository fixture/unit
ve loopback transport kanıtları `physical_validated`, `supported` veya
`production_accepted` üretmez. Fiziksel pilot için model, hardware revision,
kesin OS sürümü, management mode, transport ve capability bazında
[`KABUL_VE_KANIT_SABLONU.md`](KABUL_VE_KANIT_SABLONU.md) doldurulmalıdır.

