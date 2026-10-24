# Çok markalı toplama ve bağlantı otomasyonu

Bu belge kaynak kodun uyguladığı sözleşmeyi ve açık kabul kapılarını tanımlar.
Bir markanın katalogda yer alması bütün modellerinin desteklendiği anlamına gelmez.
`backend/app/driver_profiles.py` typed profil/alias/durum kaynağı,
`backend/app/driver_catalog.py` mevcut kolektörler için geriye uyumlu facade'dır.
`/api/v1/driver-catalog` çalışan kurulumun katalog sözleşmesini yayımlar.

## Kullanım

1. Yeni cihaz formunda kaynak modunu seçin. Kanonik sürücü kullanacaksanız canlı
   katalogdan sırasıyla üretici, işletim sistemi profili ve yönetim modunu seçin;
   planlı/engelli profiller açıklamasıyla görünür fakat seçilemez. Profilin
   uyguladığı SSH/SNMP/API kanallarından birini seçin. Otomatik çözüm açık kanıt
   ister; harici toplayıcı ve altyapı adaptörü ayrı modlardır. Eski API
   istemcilerinin açık olmayan tercihleri için `external` / `standard` okuma
   uyumluluğu korunmuştur.
2. Bağlantı bilgilerinde **Anahtarı bul ve bağlantıyı hazırla** eylemini kullanın.
   Parola gönderilmeden public host anahtarı ve SHA256 fingerprint alınır.
   Fingerprint'i konsol/kurum kaydı üzerinden karşılaştırıp bir kez onaylayın.
3. SSH kimlik bilgilerini kaydedin, **Bağlantıyı test et** ve **Veri topla** ile
   ilk sonucu inceleyin. Kayıtlı anahtar ve kimlik bilgisi hazır olduğunda etkin
   toplama politikası worker tarafından işlenir; tarayıcının açık kalması gerekmez.
4. Cihaz detayında grup bazlı kaynak, son doğru ölçüm, hata/eksik alanlar ve
   istenen–etkin aralık gösterilir. Otomatik toplamayı aynı yerden durdurabilirsiniz.
5. SNMPv3 isteğe bağlıdır. Mevcut salt okunur `authPriv` hesabını girin.
   Cihaz üzerinde SNMP etkinleştirilmez; SNMPv1/v2c kullanılmaz.
6. Controller/API profillerinde cihazı kaydettikten sonra bağlantı bilgilerinden
   site-scoped controller kaydı, read-only token ve controller cihaz kimliği
   eşlemesini tamamlayın. URL/hostname kabul edilmez; ayrıntılar
   [controller/API profil sözleşmesindedir](uyumluluk-uygulama/CONTROLLER_API_PROFILLERI.md).

## Sürücü ve veri doğrulama seviyesi

| Platform | Uygulanan temel okuma | Kanıt / sınır |
| --- | --- | --- |
| Cisco IOS / 2960-X | Bağımsız manifest; port/sayaç/CLI hız penceresi, VLAN/IP, FDB/ARP, CPU/RAM, switchport/LAG/LLDP/PoE/modül | Temizlenmiş 15.2(7)E çıktıları ve yerel eski SSH testi; fiziksel kabul ayrı |
| Huawei VRP V200 | Bağımsız V200 manifesti; port, hız/sayaç, PVID, IP, FDB/ARP, CPU/RAM, sürüm/uptime | S5700 biçimli fixture; V600 bu parser'a düşmez, donanım/DOM/VRF boşlukları açıktır |
| Cisco IOS-XE | IOS'tan bağımsız manifest; doğrulanmış IOS-benzeri read-only alt küme | C9200L/17.12.3 ve C9300/17.9.5 proje-sentetik fixture; deneysel, fiziksel kabul yok |
| Junos | Güvenli XML; arayüz/sayaç/IP, routing-engine ve environment, FDB/ARP, LLDP, sürüm/chassis/modül | Sentetik unit corpus; Junos Evolved fail-closed, fiziksel kabul yok |
| NX-OS | JSON arayüz/sayaç, sürüm/kaynak, FDB, LLDP ve inventory | Sentetik unit corpus; ARP/VLAN CLI capability'si ilan edilmez, fiziksel kabul yok |
| Aruba AOS-CX | Ayrı JSON CLI manifesti; 64-bit sayaç, identity, VLAN/FDB/ARP/LLDP, health/environment ve inventory | JL658A/FL.10.13.1030 proje-sentetik fixture; REST uygulanmadı, fiziksel kabul yok |
| Aruba AOS-Switch | Ayrı text CLI manifesti; 64-bit sayaç, identity, VLAN/FDB/ARP/LLDP ve inventory | JL253A/WC.16.11.0016 proje-sentetik fixture; `hp_procurve` alias korunur, fiziksel kabul yok |
| Arista EOS | SSH içi JSON CLI; 64-bit sayaç, identity, VLAN/FDB/ARP/LLDP, health/environment ve inventory | DCS-7050SX3-48YC8/4.31.2F proje-sentetik fixture; eAPI uygulanmadı, fiziksel kabul yok |
| HPE Comware 7 | Text CLI; 64-bit sayaç, identity, VLAN/FDB/ARP/LLDP, health/environment ve inventory | JH390A/7.1.070 proje-sentetik fixture; H3C kimliğinden ayrı, fiziksel kabul yok |
| H3C Comware V7 | Comware V7 alan mapper'ı ve ayrı H3C kimlik kapısı; V5/V9 fail-closed | S5560X-30C-EI/7.1.070 proje-sentetik fixture; fiziksel kabul yok |
| MikroTik RouterOS | RouterOS `/... print` grameri; 64-bit sayaç, identity, bridge VLAN/FDB, ARP, LLDP, health ve RouterBOARD | CRS326-24G-2S+/7.15.3 proje-sentetik fixture; Cisco fallback/API yok, fiziksel kabul yok |
| Dell SmartFabric OS10 | Ayrı OS10 manifesti; identity, interface/64-bit sayaç, VLAN/FDB/ARP/LLDP | S5248F-ON/10.5.6.1 proje-sentetik fixture; OS9/SONiC fail-closed, fiziksel kabul yok |
| Dell Networking OS9/FTOS | Ayrı OS9 manifesti ve koşullu `dell_force10` çözümü; identity, interface/64-bit sayaç, VLAN/FDB/ARP/LLDP | S4048-ON/9.14(2.20) proje-sentetik fixture; secret/host key korunur, fiziksel kabul yok |
| Dell Networking OS6 | Ayrı N-series komut/parser sözleşmesi; identity, interface/64-bit sayaç, VLAN/FDB/ARP/LLDP | N3248X-ON/6.8.1.0 proje-sentetik fixture; OS9/10 parser fallback'i yok, fiziksel kabul yok |
| ExtremeXOS / Switch Engine | Ayrı EXOS manifesti; interface/64-bit sayaç, VLAN/FDB/ARP/LLDP | X465-48T/33.3.1.4 proje-sentetik fixture; OS alias metadata'sı açık, fiziksel kabul yok |
| Extreme Fabric Engine / VOSS | Ayrı Fabric Engine manifesti ve koşullu `extreme_vsp` çözümü | 5520-48T/9.3.2.0 proje-sentetik fixture; SSH secure mode SNMP kısıtı görünür, fiziksel kabul yok |
| Extreme SLX-OS | EXOS/VOSS'tan ayrı manifest ve CLI grameri; interface/64-bit sayaç, VLAN/FDB/ARP/LLDP | SLX 9150-48Y/20.6.3b proje-sentetik fixture; fiziksel kabul yok |
| FortiSwitchOS standalone | Standalone kimlik kapısı; physical-port sayaçları, VLAN/FDB/ARP/LLDP | FortiSwitch-124F/7.6.2 proje-sentetik fixture; FortiLink/FortiOS ayrıdır, API kapalı, fiziksel kabul yok |
| FortiLink-managed FortiSwitch | FortiGate controller API üzerinden identity, port/sayaç, VLAN ve sınırlı health | Proje-sentetik API fixture; standalone/FortiOS ayrıdır, fiziksel kabul yok |
| Cisco Meraki MS | Sabit bölge origin'li Dashboard API; identity, port durumu/kapasitesi, 300 saniyelik trafik oranı ve VLAN | Proje-sentetik API fixture + TLS/pagination negatifleri; oranlar octet sayacı değildir, SSH yok, fiziksel kabul yok |
| Ubiquiti UniFi Switch | Yerel controller API; identity, port durumu/kapasitesi ve sınırlı health | Normal ve Flex/Ultra no-SNMP profilleri ayrıdır; belgelenmeyen octet/seri alanı türetilmez, fixture kanıtı, fiziksel kabul yok |
| Ubiquiti EdgeSwitch | Standalone SSH grameri + SNMPv3; identity, 64-bit sayaç, VLAN/FDB/ARP/LLDP | ES-48/1.10.4 proje-sentetik fixture; UniFi fallback'i yok, fiziksel kabul yok |
| TP-Link Omada / Omada Pro | OAuth access token kullanan ayrı controller API runtime'ları; identity, port/sayaç, VLAN ve sınırlı health | İki ayrı proje-sentetik fixture; token edinme/yenileme dışarıdadır, standalone/Pro eşitliği yok, fiziksel kabul yok |
| Aruba Instant On | Çalışan transport yok | Resmi genel yönetim API sözleşmesi kanıtlanmadığı için politika gereği kapalı |
| Linux | iproute2 JSON, sayaçlar, IP, ARP/NDP, uptime | Mevcut izole SSH sözleşmesi korunur |

NTC şablonları `ntc-templates==9.3.0` / `textfsm==2.1.0` ile sabittir.
Sadece katalogdaki salt okunur komutlar çalıştırılır; şablon paketinin bütün
komutları otomatik çalıştırılmaz. CLI çıktısı log/API/DB'ye yazılmaz. Kalıcı kayıt
yalnız doğrulanmış alanlar ve güvenli hata kodlarıdır.

### Katalog v2 ve geriye uyumluluk

`GET /api/v1/driver-catalog` additive v2 sözleşmesi döndürür:

- `drivers`, 15 çalışan + 1 çözülmemiş legacy kimliği, komutları ve eski
  alanları korur; legacy listede olmayan `h3c_comware7`, `dell_os6`,
  `extreme_slxos` ve `fortinet_fortiswitchos` kanonik `profiles` dizisinden
  seçilir;
- `profiles`, uyumluluk programındaki 38 kanonik profili ayrı uygulama,
  doğrulama ve yayın durumlarıyla taşır;
- `infrastructure_adapters`, `linux_ssh` değerini NOS profillerinden ayrı tutar;
- `aliases`, otomatik/koşullu eski kimlik kararlarını; `unresolved_aliases` ise
  hedefi güvenle seçilemeyen kayıtları yayımlar;
- `acceptance.production_accepted` varsayılan olarak `false` kalır ve fixture/lab
  sonucundan yükseltilmez.
- capability özetindeki `source_fields`, her alanın SSH/SNMP/API taşıma
  sınırını ayrıca yayımlar; union `fields` tek başına her transportun o alanı
  ürettiği anlamına gelmez.

`fortinet` eski kimliği FortiSwitchOS standalone veya FortiLink profiline
otomatik çevrilmez; `manual_resolution_required` döner. `catalog_only`, `blocked`
ve `unsupported_by_protocol` profilleri `available=false` ve `selectable=false`
kalır. Bu metadata yeni parser veya cihaz desteği eklemez.

Acil cevap uyumluluğu için `NETSTUDIO_DRIVER_CATALOG_V2=0`, yalnız additive v2
alanlarını kaldırıp önceki katalog JSON biçimini döndürür. Kolektör davranışını,
cihaz kayıtlarını, sırları veya veritabanını değiştirmez.

### Kanonik profil binding'i ve uyumluluk API'si

`0010_driver_acceptance` migration'ı cihaz payload'ını yeniden yazmadan üç
additive tablo ekler: `device_driver_bindings`,
`device_capability_observations_v2` ve `driver_acceptance_records`.

- Eski `collector` alanı en az bir uyumluluk dönemi okunup yazılmaya devam eder.
- Device cevapları `configured_profile_id`, `resolved_profile_id`,
  `profile_revision`, `management_mode` ve `profile_resolution_status`
  alanlarını binding tablosundan additive olarak alır.
- `GET /api/v1/devices/{device_id}/compatibility`, yalnız kullanıcının site
  kapsamında redakte çözüm/capability/kabul görünümünü döndürür.
- `PUT /api/v1/devices/{device_id}/driver-profile`, kanonik profil ve management
  mode seçer; profil değişimi connection revision/cache/job fence ve açık SSH
  oturumu iptalini tetikler.
- `GET /api/v1/driver-acceptance`, yalnız superadmin için redakte kayıtları
  döndürür. Browser tarafından acceptance/validation/evidence yazma endpoint'i
  yoktur.

`fortinet` otomatik profile çevrilmez. Kanıtsız `huawei_vrp`, `dell_force10` ve
`extreme_vsp` binding'leri manuel çözüm bekler. Başarılı, kimliği doğrulayan
collector/parser sonucu resolved profili günceller. S07 ile OS9/FTOS ve
Fabric Engine/VOSS kanıtı bulunan eski kayıtların kanonik çözümü mümkün olmuş,
belirsiz kayıt davranışı değişmemiştir. Capability tablosu ham cihaz
çıktısı veya hata metni değil; typed durum/reason, zaman, expiry ve SHA-256 digest
saklar. Acceptance kaydı yoksa katalog veya cihaz görünümü destek seviyesini
kendiliğinden yükseltmez.

### Katalog tabanlı arayüz

Cihaz detayındaki **Uyumluluk** paneli yapılandırılan/çözümlenen profili,
management mode'u, transport ve capability durumlarını, redakte kimlik kanıtını
ve acceptance kapsamını birlikte gösterir. `partial`, `unsupported`, yetki,
parse, timeout, genel hata ve stale kanıt birbirinden ayrılır. Viewer bu alanı
salt okunur görür; `inventory.manage` yetkili kullanıcı legacy/belirsiz kaydı
açık onayla kanonik profile taşıyabilir.

Katalog release değeri `supported` olsa bile cihazın tam tuple'ına uyan,
süresi geçmemiş fiziksel kabul kaydı olmadan arayüz cihazı **Destekleniyor** diye
etiketlemez. Fixture veya izole SSH/SNMP laboratuvarı production kabulü değildir.
Backend, istemci manipülasyonuna karşı `selectable=false` profili bütün cihaz
oluşturma/profil değiştirme yollarında reddeder.

## Veri doğruluğu

- SFP yuvası, takılan bakır modül nedeniyle RJ45'e dönüştürülmez. Modül ortamı ayrı
  `transceiver_media` alanındadır. Geometri yalnız gözlemden üretilir.
- IOS port tablosu bilinmeyen/tekrarlanan/eksik ethernet satırında reddedilir.
  Tam doğrulanmamış envanter mevcut portları silemez. Elle düzenlenmiş fiziksel
  yerleşim korunur. Kalıcı arayüz kimliği mevcut isim eşleştirmesinden korunur.
- `collection.py` cihaz kilidi ve iş sahipliği kontrolünden sonra envanter,
  grup projeksiyonları ve sayısal örnekleri aynı transaction içinde yazar.
  Ağ beklerken veritabanı kilidi tutulmaz.
- Bir grubun başarısız veya kısmi yenilemesi önceki tamamlanmış alanları silmez;
  başarılı capability alanı kendi `field_sources` ve `field_observed_at` kanıtıyla
  birleşirken başarısız alanın son-doğru değeri/kaynağı/saati korunur. Grup saati
  tam yenileme gerçekleşene kadar ilerletilmez; son deneme zamanı ayrıca tutulur.
- SNMP sayaçlarında kaynak, bit genişliği, `sysUpTime`, arayüz adı/ifIndex değişimi
  ve `ifCounterDiscontinuityTime` yeni başlangıç örneği gerektirir. Reset/wrap
  anında negatif fark veya sahte yüksek hız üretilmez.
- CLI'nin 300 saniyelik ortalaması 30 saniyelik örnek gibi sunulmaz. Epoch kanıtı
  olmayan CLI sayaçlarından hız türetilmez. Fiziksel trafik toplamında LAG
  arayüzü ve fiziksel üyeler ikinci kez toplanmaz.
- Eksik ölçümler sıfır değildir. LLDP/L2 ilişkisi ve MAC/IP gözlemi otomatik
  fiziksel kablo kanıtı sayılmaz.
- Q-BRIDGE FDB girdisi ancak FID→VLAN, bridge-port→ifIndex ve ifIndex→kalıcı
  interface zinciri eksiksizse kabul edilir. FID'nin VLAN'a eşit olduğu
  varsayılmaz. `dot1qVlanCurrentFdbId` yalnız TimeFilter `0` güncel snapshot'ı
  üzerinden yürünür; karışık snapshot reddedilir. SNMP FDB'den IP/ARP veya
  kablo ilişkisi üretilmez.

### Profil kimliği ve yeniden çözümleme

SSH toplayıcısı profilin zorunlu inventory kimlik komutunu diğer komutlardan
önce okur. IOS/IOS-XE, VRP V200/V600, klasik Junos/Junos Evolved, NX-OS,
AOS-CX/AOS-Switch, EOS, HPE/H3C Comware, RouterOS, Dell OS6/OS9/OS10/SONiC,
Extreme EXOS/Fabric Engine/SLX ve FortiSwitch standalone/FortiLink/FortiOS
birbirine parser fallback'i yapmaz. H3C V5/V9, V7 parser'ına; RouterOS, Cisco
parser'ına yönlendirilmez.
Gözlenen implemented profil farklıysa gerçek profilin allowlist'i kullanılır ve
yapılandırılmış binding çelişki olarak kaydedilir; catalog-only ailede toplama
`collector_platform_unsupported` ile durur. Tanınabilir SNMP `sysDescr` ayrı
kimlik kanıtıdır; SSH ve SNMP farklı kanonik profil gösterirse
`transport_identity_mismatch` ile fail-closed olur.

Önceden eşleşmiş vendor/model/OS ailesi veya sürümü değiştiğinde, profil
revizyonu değiştiğinde ya da SNMP uptime reboot gösterdiğinde çözüm yeniden
hesaplanır. Yalnız derived komut ve capability cache'i temizlenir; cihaz kaydı,
şifreli sır, host key, envanter, job geçmişi ve last-good grup verisi korunur.

## SSH güven sözleşmesi

`ssh_profiles.py` ve `ssh.py` terminal ve toplayıcı tarafından ortaktır.

- `auto`, `standard`, `huawei_legacy` (**Eski VRP**), `legacy_sha1`,
  `legacy_cbc`, `advanced` desteklenir. Bunlar SSH-2 algoritma kümeleridir;
  SSH-1, Telnet veya şifrelemesiz oturum eklenmez.
- Otomatik seçim en fazla dört el sıkışması/30 saniye; yalnız KEX uyuşmazlığında
  izinli kümeye geçiş yapar. KEX hatasını iletmeden bağlantıyı kapatan eski
  cihazlarda yalnız kimlik doğrulama başlamadan kapanan el sıkışması da
  uyumluluk denemesi olabilir. Yanlış parola, zaman aşımı veya host key değişiminde
  parola tekrar tekrar denenmez. Modern algoritmalar her kümede önce gelir.
- Eski VRP kayıtları önceki açık onaylarıyla çalışır. Diğer otomatik/eski seçimler
  `allow_legacy_ssh` iznine tabidir. Gelişmiş seçenekler çalışan AsyncSSH
  sürümünün izinli kataloğuyla backend'de doğrulanır.
- Keşif adayı kullanıcı/cihaz/bağlantı revision/hedef imzasına bağlıdır, 10 dakika
  geçerli ve tek kullanımlıktır; cihaz başına dakikada bir keşif yapılır.
- Onay kimlik bilgisi gönderilmeden önce gerekir. Anahtar değişimi bağlantıyı
  durdurur. Değiştirme ayrıca açık onay ister. Elle anahtar girişi gelişmiş
  seçenek olarak korunur. Ayar/kimlik bilgisi/anahtar değişimi önbelleği ve eski
  işlerin yazma yetkisini geçersiz kılar.

## Kuyruk ve zamanlama

`collector-worker` aynı backend imajını kullanır. Redis/Celery gerekmez.
`queue.py` kısa transaction, global slot kilidi ve PostgreSQL
`FOR UPDATE SKIP LOCKED` kullanır. Cihaz başına tek çalışan iş, kurulum başına
en fazla sekiz iş; 30 saniyelik lease ve 5 saniyelik heartbeat vardır.
Worker kaybında en fazla üç sahiplenme; eski sahip sonuç yazamaz. API açılışı
artık bekleyen işleri topluca başarısız yapmaz.

Manuel işler kullanıcı oturumunun hash referansıyla yetkiyi yeniden doğrular.
Otomatik işler etkin/sürümü eşleşen kayıtlı cihaz politikasıyla sistem kimliğinde
çalışır; cookie veya kullanıcı parolası kuyrukta tutulmaz. Aynı cihazın yinelenen
istekleri birleştirilir. Çalışan iş istenen grupları kapsıyorsa aynı iş kimliği
döner; hızlı bir işin karşılayamadığı tam manuel okuma için en fazla bir
birleştirilmiş takip işi bekler. Aynı cihaza paralel toplama bağlantısı açılmaz.

| Grup | Hedef |
| --- | --- |
| `fast` | 30 sn; eski SSH 60 sn altına inmez |
| `health` | 120 sn |
| `network` | 300 sn |
| `inventory` | 3600 sn |

Başlangıç dağıtılır; aralığa %10'a kadar sapma eklenir. Minimum/duty-cycle
sınırı negatif sapmayı kısaltabilir. Gözlenen süre ×5 alt sınırı %20 çalışma
oranını korur. İki yeni CPU okuması %80 üstündeyse aralık büyür; beş sağlıklı
okuma kademeli toparlanır. Hata beklemesi en fazla 30 dakikadır. Kaçırılmış
Döngüler biriktirilmez. SSH ve SNMP kimlik/transport hataları yalnız ilgili
kanalda bounded backoff oluşturur; başarılı diğer kanal toplamaya devam eder.
Hedef/etkin aralık farklı alanlardır.

## Saklama ve API

`device_latest_telemetry` son durum; `device_collection_groups` grup son doğru
değerleri; `device_metric_samples` yeni ayrıntılı sayısal örnekler;
`device_metric_rollups` beş dakikalık özetlerdir. Ham örnekler en az 7 gün,
özetler 90 gün saklanır. Özeti henüz üretilemeyen ham veri silinmez.
Temizlik parçalıdır ve eski `device_telemetry` kayıtlarını silmez.
Özetler yalnız geçerli ölçüm süresini ağırlıklandırır, kapsama oranını içerir.
Envanter/ağ tablolarında aynı içerik tekrar tarihçeye kopyalanmaz.

Ek API'ler:

- `GET /api/v1/driver-catalog`, `/api/v1/ssh-profiles`
- `POST /api/v1/devices/{id}/host-key-discoveries`
- `GET /api/v1/devices/{id}/host-key-candidates/{candidate}`
- Mevcut `PUT .../host-key`: elle alanlar veya `candidate_id`
- `GET/PUT .../polling`, `PUT/DELETE .../snmp-credentials`
- `GET .../metrics?hours=1&resolution=auto` (en fazla 2880 nokta)
- `GET .../overview`: yalnız ilgili cihazın ayrıntısı
- `GET /api/v1/overview/summary`, `/api/v1/overview/traffic`: ayrı güncel
  durum ve sınırlı sayısal geçmiş. Dashboard geçmişi 60 sn, güncel durumu 15 sn
  aralıkla ister; tüm cihazların tam telemetri geçmişini 15 sn'de indirmez.

## Geçiş ve geri dönüş

Migration `0006_collection_automation` yalnız ek tablolar/indeksler oluşturur.
Mevcut cihazlar, sırlar, host anahtarları, arayüz/port kimlikleri yeniden
oluşturulmaz. Kullanıcı kurulumunu değiştirmeden önce yedeği ve gerçek Compose
proje/context/TLS override'larını doğrulayın.

```bash
# Mevcut kurulumun DOĞRULANMIŞ proje/context/override seçenekleriyle:
docker compose build api web collector-worker
docker compose run --rm migrate
docker compose up -d api web collector-worker

# Otomatik işi durdurmak için; veri/volume silinmez:
docker compose stop collector-worker
```

API içinde worker varsayılan olarak çalışmaz. `NETSTUDIO_EMBEDDED_WORKER=1`
yalnız açık geliştirme/izole test seçeneğidir. Backend testleri zamanlayıcıyı
devre dışı bırakarak manuel iş semantiğini deterministik çalıştırır.
Eski API'nin yalnız bellekte tuttuğu geçiş öncesi işlerde yeniden manuel tetikleme
gerekebilir; bu işlerde sonradan kullanıcı yetkisi uydurulmaz.

## Kabul durumu ve açık işler

Bu teslim bütün planın tamamlandığı anlamına gelmez:

Üretici/işletim sistemi kapsamını genişletmek için kaynak uyumluluk matrisiyle
eşleştirilmiş [implementasyon raporu, sprintler ve kabul kapıları](uyumluluk-uygulama/README.md)
ayrı uygulama paketinde izlenir. Oradaki hedefler bu bölümdeki çalışan ürün
sözleşmesini kendiliğinden genişletmez.

| Plan adımı | Durum |
| --- | --- |
| SFP/kısmi tablo düzeltmeleri, atomik grup ve alan bazlı son-doğru kaydı | Uygulandı; capability kaynak/saat provenance korunur |
| Typed registry ve additive katalog v2 | Uygulandı; 38 profil sınıflı, eski 16 katalog kaydı geriye uyumlu |
| P0 kanonik manifestleri; IOS/IOS-XE ayrımı, Huawei V200 alias, Junos/NX-OS | Uygulandı; bütün profiller deneysel ve fiziksel kabul bekliyor |
| P1 AOS-CX/AOS-Switch, EOS, HPE/H3C Comware V7 ve RouterOS manifestleri | Uygulandı; proje-sentetik fixture doğrulandı, fiziksel kabul bekliyor |
| S07 Dell OS6/9/10, Extreme EXOS/Fabric/SLX ve standalone FortiSwitchOS | Uygulandı; proje-sentetik fixture doğrulandı, controller/FortiLink ayrı ve fiziksel kabul bekliyor |
| S08 controller/cloud API, UniFi/Omada/FortiLink/Meraki ve EdgeSwitch | Uygulandı; ayrı controller secret/site binding, izole TLS ve sentetik fixture doğrulandı; Instant On politika gereği kapalı, fiziksel kabul bekliyor |
| Host key keşfi/onayı, ortak SSH profilleri | Uygulandı; yerel gerçek SSH ve tarayıcı testi |
| Kalıcı kuyruk, zamanlayıcı, worker, standard MIB SNMPv3 çekirdeği | Uygulandı; ortak fencing/deadline, bounded reader ve yerel gerçek UDP testi |
| Arayüz, kalite tanıları, sınırlı geçmiş, saklama | Uygulandı; gerçek tarayıcı ve yerel saklama testleri |
| Fiziksel pilot, 100 cihaz gerçek 24 saat kabulü | Çalıştırılmadı; kapasite/üretim kabulü değildir |
| İleri/legacy NOS ve sınırlı protokol dalgaları | Planlandı; çalışan sürücü değil |

- Birim/yerel SSH testleri fiziksel cihaz kabulü değildir. 100 cihaz ×24 saat
  hızlandırılmış zamanlayıcı testi gerçek 24 saatlik PostgreSQL/ağ yük testi
  değildir. **1–100 kapasite hedefi REQUIRES BENCHMARK.**
- Cisco/Huawei fiziksel pilot; CPU etkisi, toplama süresi ve çıktı karşılaştırması
  gerçek cihazlarla ayrıca yapılmalıdır. Juniper fiziksel doğrulanmış sayılmaz.
- Sonraki dalga sürücüler, bütün modellerin sürüm çıktıları, tam VRF/NDP/CDP,
  breakout, DOM ve üreticiye özgü fan/PSU biçimleri henüz evrensel kapsama sahip
  değildir; katalog/grup alanları eksikliği gösterir.
- SNMPv3 system, IF/IF-X, BRIDGE/Q-BRIDGE, LLDP ve temel ENTITY/ENTITY-SENSOR
  mapper'ları ile sır saklama yerel testlidir. Geçici yerel agent gerçek
  UDP/SHA-256/AES-128 GET/GETNEXT/GETBULK, auth/context negatifleri ve büyük
  tablo sınırlarını doğrular; fiziksel vendor agent ve üretici MIB sağlık
  ölçümleri ayrıca kabul gerektirir.
- SNMP uptime/counter epoch değişimi envanteri öne alır. SNMP kimlik hatası yalnız
  SNMP kanalını duraklatır; otomatik kaynak seçimi SSH ile devam edebilir ve bunu
  grup tanısında belirtir. Açık SNMP tercihinde başarısız hızlı ölçümün yerine
  SSH ölçümü SNMP etiketiyle yazılmaz.
- Alan bazlı son-doğru birleştirme ve P0 kimlik/reboot yeniden çözümlemesi
  uygulanmıştır. Vendor'a özgü donanım değişikliği kapsamı fiziksel pilotta
  ayrıca doğrulanmalıdır.
- SSH ve SNMP kanal pause/recovery state'i ayrıdır; bir kanalın kimlik hatası
  diğer kanalı durdurmaz ve retry süresi dolunca yalnız hatalı kanal yeniden denenir.

## Üretici/standart referansları

- [Cisco 2960-X operational commands](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst2960x/software/15-2_7_e/command_reference/b_1527_2960x_cr/interface_and_hardware_commands.html)
- [Huawei interface commands](https://info.support.huawei.com/enterprise/en/doc/EDOC1100333403/cdd85713/basic-interface-configuration-commands)
- [Junos XML mapping](https://www.juniper.net/documentation/us/en/software/junos/netconf/junos-xml-protocol/topics/task/junos-xml-protocol-rpcs-and-xml-mapping.html)
- [NX-OS structured output](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/103x/command-reference/show/b_n9k_show_commands_103x/m_show_xml.html)
- [Dell SmartFabric OS10 LLDP CLI](https://www.dell.com/support/manuals/en-us/dell-emc-smartfabric-os10/smartfabric-os-user-guide-10-5-2-6/show-lldp-neighbors?guid=guid-cf4a7765-02fd-4278-9bcb-c49088ba61e5&lang=en-us)
- [Extreme Fabric Engine SSH secure mode](https://documentation.extremenetworks.com/Fabric%20Engine%20v9.3%20User%20Guide/content/documents/Switch_Operating_Systems/VOSS_and_Fabric_Engine/fabric_engine_user_guide/ssh_version_2.shtml)
- [FortiSwitchOS CLI reference](https://docs.fortinet.com/document/fortiswitch/7.6.2/fortiswitchos-cli-reference/896953/get)
- [AsyncSSH API](https://asyncssh.readthedocs.io/en/latest/api.html#asyncssh.get_server_host_key)
- [IF-MIB / RFC 2863](https://www.rfc-editor.org/info/rfc2863/)
- [Q-BRIDGE-MIB / RFC 4363](https://www.rfc-editor.org/info/rfc4363/)
- [TimeFilter uygulama notları / RFC 2021](https://www.rfc-editor.org/info/rfc2021/)
- [PySNMP](https://github.com/lextudio/pysnmp)
- [PostgreSQL row locking](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE)
- [NTC parser test guide](https://github.com/networktocode/ntc-templates/blob/master/docs/dev/dev_parser.md)
