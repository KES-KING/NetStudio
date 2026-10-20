# Cisco Catalyst 2960-X: salt okunur IOS toplama

## WS-C2960X-48FPD-L cihazını etkinleştirme

1. Cihaz detayında **Bağlantı bilgileri** ekranını açın.
2. **Veri kaynağı → Cisco IOS · Catalyst 2960-X salt okunur SSH** seçin.
3. Yeni cihazlarda **Otomatik** SSH seçilidir. Eski algoritmalar gerekiyorsa cihaz bazlı izni açın; **Eski VRP**, SHA-1 ve CBC/Group1 profilleri elle de seçilebilir. Profil yalnız bağlantı algoritmalarını değiştirir; collector Cisco IOS olarak kalır.
4. **Anahtarı bul ve bağlantıyı hazırla** eylemiyle anahtarı getirin; fingerprint'i ayrı güvenilir kanaldan karşılaştırıp onaylayın. Otomatik ilk güven uygulanmaz.
5. Önce **Bağlantıyı test et**, ardından **Veri topla** kullanın. İş sonucunu, port sayısını ve son gözlem zamanını kontrol edin.

## Komut ve veri sözleşmesi

Ortak `drivers.py` akışı aşağıdaki temel sabit EXEC komutlarını kullanır; kullanıcı girdisini komuta eklemez ve konfigürasyon moduna girmez. Güncel tam komut listesi, veri grupları ve doğrulama seviyeleri `driver_catalog.py` / [otomasyon sözleşmesindedir](collection-automation.md).

| Komut | Kullanım |
| --- | --- |
| `show version` | Cisco IOS ve Catalyst 2960-X ailesini; model, sürüm, seri ve uptime alanlarını doğrular. |
| `show interfaces` | İdari/operasyonel durum, RX/TX hızları, octet/error sayaçları ve duplex gözlemleri. |
| `show interfaces status` | Cihazın gerçekten raporladığı fiziksel portlar, access/trunk VLAN, hız ve açık medya türü. |
| `show ip interface` | Açık prefix içeren arayüz adresleri; biçim tanınmazsa adres üretilmez. |
| `show mac address-table` | VLAN ve arayüz kapsamlı FDB gözlemleri; fiziksel kablo kanıtı değildir. |
| `show arp` | Yalnız aynı VLAN SVI kapsamındaki FDB kaydıyla MAC/IP ilişkilendirmesi. |

Envanter grubunda `show version`, hızlı grupta iki arayüz komutu zorunludur. Kimlik veya port çıktısı tanınmazsa ilgili grup başarısız olur ve son doğru envanter korunur. CPU/RAM, PoE, çevre, switchport, LAG, LLDP ve modül komutları ek yeteneklerdir; desteklenmeyen/yetkisiz/ayrıştırılamayan sonuçlar ayrı tanılarla gösterilir. Envanter ve ölçümler atomik kaydedilir.

## Fiziksel doğruluk ve sınırlar

`WS-C2960X-48FPD-L` model adı port üretmek için kullanılmaz. Fiziksel portlar yalnız `show interfaces status` satırlarından oluşturulur; bakır/SFP/QSFP sınıfı yalnız açık `Type` kanıtından belirlenir. Model kataloğundaki nominal kapasite eksik CLI satırlarını tamamlamaz. Portların kasa üzerindeki birebir mekanik konumu doğrulanmış sayılmaz (`verified_layout=false`).

Collector salt okunurdur; konfigürasyon uygulama, yedekleme ve doğrulanmamış stack kasa geometrisi üretmez. LLDP L2 gözlemidir, fiziksel kablo kanıtı değildir. Zamanlanmış toplama ayrı worker üzerinden yürür; migration `0006_collection_automation` gerekir. SSH terminalinde uzak Cisco hesabının kendi yetkileri geçerlidir; ayrı, en az ayrıcalıklı bir hesap kullanın.
Collector `enable` parolası göndermez; tanımlanan cihaz hesabı yukarıdaki `show` komutlarını doğrudan çalıştırabilmelidir.

Kaynaklar: [Cisco Catalyst 2960-X arayüz komutları](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst2960x/software/15-2_7_e/command_reference/b_1527_2960x_cr/interface_and_hardware_commands.html), [Cisco Catalyst 2960-X ürün ailesi](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst2960x/hardware/installation/guide/b_c2960x_hig/b_c2960x_hig_chapter_01.html).

Parser ve gerçek yerel legacy SSH/PTY sözleşmesi `backend/tests/test_cisco.py` içinde temizlenmiş fixture'larla test edilir. Bu testler fiziksel cihaz kabulü değildir; gerçek switch üzerinde host key doğrulaması, yetkili kullanıcıyla bağlantı ve canlı çıktı uyumu ayrıca doğrulanmalıdır.

## IOS 15.2(7)E: Fa0 ve bulunmayan donanım satırları

Ayrıştırıcı `2026.10.20.2`, `Fa0` / `FastEthernet0` arayüzünü yönetim arayüzü
olarak tanır; ön panel için fazladan port üretmez. Cisco bu arayüzü
[Ethernet yönetim portu](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst2960x/software/15-2_7_e/configuration_guide/b_1527e_consolidated_2960x_cg/m_int_emp_cg.html)
olarak tanımlar.

`show interfaces`, `show interfaces status` tablosunda bulunmayan arayüzler
raporlayabilir. Yalnız kendi ayrıntı bloğunda açıkça `Hardware is not present`
yazan ve oper durumu down olan arayüz, fiziksel tablo eşitliği kontrolünden
çıkarılır. Arayüz kimliği ve gözlemleri korunur; fiziksel yuva veya başka bir
arayüzle eşleşme uydurulmaz. Model adı, port numarası, down durumu veya
`media type is Not Present` tek başına bu istisna için yeterli değildir.
Diğer eksik, kesilmiş, yinelenmiş ve çelişkili satırlar yine reddedilir; son
doğru envanter korunur.

Bir status ayrıştırma hatası artık `show version` ve `show interfaces`
komutlarını da hatalı olarak işaretlemez; grup tanısında ilgili komut belirtilir.
Zorunlu komutların ayrıştırma hataları zamanlayıcının artan beklemesi altında
yeniden denenir. Desteklenmeyen/yetkisiz komutlar ve isteğe bağlı komutların
ayrıştırma hataları cihaz yükünü sınırlamak için önbellekte tutulur.
Başarılı okuma ilgili eski olumsuz kaydı kaldırır.

Bu düzeltme için yeni migration gerekmez. API ve worker aynı güncel imajla
çalışmalıdır; sürüm artışı eski hatalı yetenek önbelleğini otomatik geçersiz
kılar. Cihazı, kimlik bilgilerini veya onaylı host anahtarını silip yeniden
eklemeyin. Temel envanter başarılı olsa da desteklenmeyen çevre komutları veya
henüz tanınmayan LLDP/LAG çıktı biçimleri genel işi **Kısmi** bırakabilir;
grup tanıları ayrıca değerlendirilmelidir.
