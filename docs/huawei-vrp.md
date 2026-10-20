# Huawei VRP: bağlantı ve salt okunur toplama

## Mevcut cihazı etkinleştirme

1. Engineer veya superadmin olarak cihaz detayındaki **Bağlantı bilgileri** ekranını açın.
2. **Veri kaynağı → Huawei VRP · salt okunur SSH** seçin.
3. Modern SSH ile çalışıyorsa **Standart** profili koruyun. S5700S-28P-LI-AC / VRP 5.120 gibi yalnız eski algoritmalarla bağlanılan cihazda **Eski VRP** seçin ve risk onayını işaretleyin. **Bağlantı ayarlarını kaydet** düğmesine basın.
4. Kimlik bilgilerini tamamlayın; **Anahtarı bul ve bağlantıyı hazırla** ile host anahtarını alın. SHA256 fingerprint'i bağımsız güvenilir kaynaktan karşılaştırıp bir kez onaylayın. Sırlar geri okunmaz; boş sır alanı mevcut kaydı korur. Otomatik ilk güven yoktur.
5. **Bağlantıyı test et**, ardından **Veri topla** kullanın. İş sonucu ve son gözlem zamanını kontrol edin. **SSH** aynı cihaz profilini kullanır.

Cihazın yetkili envanter kaydı kendi yönetim IP/SSH portunun onayıdır; cihaz başına `.env` düzenlenmez. İsteğe bağlı `STOCC_SSH_ALLOWED_CIDRS` doluysa ek kurulum sınırı olarak uygulanır. Loopback açık CIDR izni ister; link-local (metadata servisleri dahil), multicast ve belirsiz hedefler reddedilir. Tarayıcı terminal API'si serbest hedef kabul etmez. Bu değişiklik mevcut global CIDR sınırını veya cihazın bağımsız host güven kaydını silmez.

## Uyumluluk profili

Yeni cihaz formunda `auto` varsayılandır; eski kayıtların `standard` / `huawei_legacy` değerleri korunur. `huawei_legacy`, yalnız seçilen cihazın bağlantısına aşağıdakileri **ekler**, diğer cihazların varsayılanlarını değiştirmez:

- KEX: `diffie-hellman-group-exchange-sha1`, `diffie-hellman-group1-sha1`.
- Sunucu host imzası: `ssh-rsa`.
- Şifre: `aes128-cbc`.

Bunlar eski/zayıf algoritmalardır. Uygunsa cihaz yazılımını ve SSH yapılandırmasını modernleştirip Standart profile dönün. Otomatik profil yalnız cihazda eski algoritma izni varsa sınırlı uyumluluk denemesi yapar; yanlış parola veya değişen host anahtarı deneme gerekçesi değildir. Profil/toplayıcı değişikliği denetlenir ve açık terminalleri kapatır. Ayrıntılar [toplama otomasyonu](collection-automation.md), [AsyncSSH bağlantı seçenekleri](https://asyncssh.readthedocs.io/en/latest/api.html#supported-algorithms) ve [OpenSSH legacy rehberinde](https://www.openssh.org/legacy.html).

## Komut ve veri sözleşmesi

Ayrıştırıcılar `backend/app/huawei.py`, ortak akış `drivers.py`, komut/grup tanımları `driver_catalog.py` içindedir. İnteraktif, sınırlı bir PTY üzerinden aşağıdaki sabit komutlar çalışır. `system-view`, `save`, konfigürasyon okuma/yazma veya kullanıcıdan alınan komut parçaları yoktur. Sayfalama istemine yalnız boşluk gönderir; cihazın kalıcı/session paging ayarını değiştirmez.

| Komut | Veri / hata davranışı |
| --- | --- |
| `display version` | VRP kimliği, yazılım sürümü, ilk cihaz uptime satırı; zorunlu, tanınmazsa işlem başarısız |
| `display interface` | Arayüz adı, fiziksel/idari durum, hız, duplex, açıklama, RX/TX, hata/discard, PVID; zorunlu, tanınmazsa son envanter korunur |
| `display ip interface brief` | Açık prefix içeren IP arayüzleri; opsiyonel, yalnız raporlanan birincil IPv4 adresleri |
| `display mac-address` | MAC + açık VLAN + öğrenilen arayüz; opsiyonel, L2 gözlemidir |
| `display arp all` | IP/MAC + arayüz; opsiyonel, cihazın kendi `I` kayıtları dışlanır |
| `display cpu-usage` | Tanınan genel CPU yüzdesi; opsiyonel, rastgele sağlık eşiği üretilmez |
| `display memory-usage` | Tanınan RAM yüzdesi; opsiyonel, yoksa null/uyarı |

Komut başına 20 saniye / 2 milyon karakter / 512 sayfa, toplama başına 120 saniye sınırı vardır. EOF, aşırı çıktı veya timeout sonrası aynı kanalda sonraki komuta devam edilmez. Desteklenmeyen/yetkisiz opsiyonel komutlar uyarı üretir; temel envanteri silmez. Raw CLI çıktısı ve kimlik bilgileri audit veya iş sonucuna yazılmaz. Ağ okumaları DB transaction'ı dışında, kayıt güncellemesi kısa kilitli transaction içinde yapılır; oturum/yetki veya bağlantı ayarları değişirse sonuç yazılmaz. Snapshot zamanı `display interface` okumasının bitişidir; komutlar ardışık olduğundan sağlık ve uç tabloları aynı anda alınmış sayılmaz (toplam okuma en fazla 120 saniye).

### Port ve trafik anlamı

- S5700 **VRP 5.120 (V200R002C00SPC100)** için paylaşılan, hassas bilgileri çıkarılmış çıktı biçimi testlerde kullanılır. Huawei'nin [`display interface` referansındaki](https://info.support.huawei.com/enterprise/en/doc/EDOC1100333403/cdd85713/basic-interface-configuration-commands) port modu anlamı esas alınır: `COMMON/FORCE COPPER` RJ45 kanıtıdır. `COMMON/FORCE FIBER` ile birlikte GE, XGE/10GE veya 25GE arayüz ailesi görülürse kasa sınıfı SFP/SFP+/SFP28'i kapsayan `sfp` olarak kaydedilir. [S5700S-28P-LI-AC donanım kaydı](https://info.support.huawei.com/info-finder/vue/search-center/en/enterprise/switch/s5700s-28p-li-ac-pid-22347051/hardwarecenter) 24 bakır ve 4 Gigabit SFP arayüzünü doğrular; test fixture'ı bu dağılımı denetler ancak parser model adına göre port üretmez. 40GE/100GE gibi daha hızlı optik arayüzler yalnız çıktıda açık `QSFP`, `QSFP+`, `QSFP28` veya `QSFP-DD` işareti varsa `qsfp` olur; aksi halde tür bilinmiyor kalır. Bu sınıflandırma modülün takılı olduğunu göstermez; transceiver doluluk durumu ayrıca bilinmiyor kalır.
- Model adından 24/28/48 port, uplink veya kasa geometrisi üretilmez. Yalnız tanınan fiziksel Ethernet arayüzleri şematik port olur. VLANIF, loopback, Eth-Trunk ve alt arayüzler fiziksel port sayımına katılmaz. Breakout/stack/slot düzeni bu sürümde keşfedilmez.
- Önceden aktarılan fiziksel envanter, kimlikler ve kaynak/zaman bilgisi korunur. Arayüz adının açık kısaltmaları (`GE`/`GigabitEthernet`) aynı kimliğe eşlenir. Yeni toplayıcının kendi port kimlikleri isimden kararlı üretilir.
- `DOWN` bağlantısız; `Administratively DOWN` idari kapalıdır. PVID, access VLAN/mod kanıtı değildir; `Link-type` yoksa mod bilinmiyor kalır.
- `Last 300 seconds input/output rate … bits/sec` gibi raporlanan hızlar doğrudan **bit/s** olarak alınır. `rate_interval_seconds` ortalama penceresidir; port detayında ve ana trafik açıklamasında belirtilir. RX ve TX ayrı kalır; kapasite bilinmiyorsa oran hesaplanmaz. Bu ölçüm anlık hız değildir.
- Byte sayaçları saklanır ancak VRP çıktısında güvenilir reset/boot epoch olmadığı için eksik hız değerleri sayaç farkından tahmin edilmez (`counter_epoch_known:false`). RX/TX hata ve discard sayaçları ayrı alanlardır; eksik değer null kalır.
- CPU/RAM değerleri cihazın kendi raporudur; sağlık durumu kendiliğinden “sağlıklı” olmaz. Fan, güç, sıcaklık, PoE, transceiver, tam VLAN üyeliği, seri/MAC kimliği veya LLDP topolojisi bu adaptörde doğrulanmış olmadığından üretilmez. Özellikle eski VRP'de RAM komutu desteklenmeyebilir; [Huawei belgesi eski sürümlerde farklı komuta işaret eder](https://info.support.huawei.com/network/ptmngsys/Web/tsrev_s/en/content/s/35_edesk_the_cpu_usage_is_high/edesk_the_cpu_usage_is_higher_desk002.html); toplayıcı diagnostic view'a geçmez.

### IP/MAC ve topoloji

IP ilişkileri yalnız prefix'li [IP arayüz çıktısından](https://info.support.huawei.com/hedex/api/pages/EDOC1000053358/YEF0907R/25/resources/en-us_cliref_0133018113.html) oluşturulur. Tam VRF, IPv6, secondary IP ve LLDP keşfi bu sürümün kapsamında değildir. Brief çıktısında VRF doğrulanmadığından `vrf_known:false` gönderilir; topoloji bunu varsayılan VRF diye sunmaz ve aynı prefix'i farklı arayüzler arasında ortak alt ağ düğümüne birleştirmez.

FDB ile ARP yalnız aynı açık arayüzde veya FDB VLAN'ına karşılık gelen varsayılan-VRF VLANIF üzerinde ilişkilendirilir. Farklı VLAN/VRF'deki aynı MAC gelişigüzel birleştirilmez. ARP'den doğrulanmamış fiziksel kablo/komşu üretilemez; sadece mantıksal uç gözlemleri eklenir. Eksik/parçalı tablo `partial`, tanınmayan çıktı `error`, desteklenmeyen her iki komut `unsupported` döner. En fazla 2048 uç gözlemi tutulur; kırpma kısmi durumdur. Huawei'nin [ARP komutu açıklaması](https://info.support.huawei.com/hedex/api/pages/EDOC1100331440/AZM10131/04/resources/dc/display_arp.html) ile arayüz/VRF kapsamı ve yerel `I` kayıtları ayrılır.

## Dağıtım ve doğrulama sınırı

Eski SSH profilleri ve cihaz JSON kayıtları korunur. Yeni otomasyon için `0006_collection_automation` ek tabloları ve ayrı `collector-worker` gerekir; [geçiş adımlarını](collection-automation.md#geçiş-ve-geri-dönüş) inceleyin. Backend, frontend ve worker imajlarını birlikte build edin. Örneğin doğrulanmış mevcut Desktop kurulumu `stocc-netstudio-fresh` ise aynı repository içinde:

```bash
docker --context desktop-linux compose -p stocc-netstudio-fresh up --build -d --wait
```

Kendi kurulumunuzun context/proje adını ve varsa TLS compose dosyalarını koruyun. Yeni kurulum/volume veya admin sıfırlaması gerekmez. `.env` ve şifreleme anahtarları değiştirilmez.

`backend/tests/test_huawei.py`, temizlenmiş CLI biçimlerini, eski algoritmalara sınırlı gerçek yerel SSH sunucusunu, sayfalamayı, standart profilde reddi, yanlış host key reddini, kayıtlı hedef onayını, rol/site kısıtını, profil iptalini ve başarısız okumada envanter korumasını test eder. Bunlar fiziksel Huawei cihazında kabul testi değildir; gerçek switch üzerinde güvenilir host anahtarı kaydedildikten sonra bağlantı ve toplama ayrıca doğrulanmalıdır.
