# Cisco Catalyst 2960-X: salt okunur IOS toplama

## WS-C2960X-48FPD-L cihazını etkinleştirme

1. Cihaz detayında **Bağlantı bilgileri** ekranını açın.
2. **Veri kaynağı → Cisco IOS · Catalyst 2960-X salt okunur SSH** seçin.
3. `SSH-2.0-Cisco-1.25` gibi yalnız eski anahtar değişimiyle çalışan cihazlarda **SSH uyumluluk profili → Eski VRP** seçeneğini ve cihaz bazlı risk onayını kullanın. Bu profil yalnız bağlantı algoritmalarını genişletir; collector yine Cisco IOS olarak kalır.
4. Ayrı bir güvenilir kanaldan doğrulanmış OpenSSH public host anahtarını ve SHA256 fingerprint'i kaydedin. Otomatik ilk güven uygulanmaz.
5. Önce **Bağlantıyı test et**, ardından **Veri topla** kullanın. İş sonucunu, port sayısını ve son gözlem zamanını kontrol edin.

## Komut ve veri sözleşmesi

Collector yalnız aşağıdaki sabit EXEC komutlarını çalıştırır; kullanıcı girdisini komuta eklemez ve konfigürasyon moduna girmez:

| Komut | Kullanım |
| --- | --- |
| `show version` | Cisco IOS ve Catalyst 2960-X ailesini; model, sürüm, seri ve uptime alanlarını doğrular. |
| `show interfaces` | İdari/operasyonel durum, RX/TX hızları, octet/error sayaçları ve duplex gözlemleri. |
| `show interfaces status` | Cihazın gerçekten raporladığı fiziksel portlar, access/trunk VLAN, hız ve açık medya türü. |
| `show ip interface` | Açık prefix içeren arayüz adresleri; biçim tanınmazsa adres üretilmez. |
| `show mac address-table` | VLAN ve arayüz kapsamlı FDB gözlemleri; fiziksel kablo kanıtı değildir. |
| `show arp` | Yalnız aynı VLAN SVI kapsamındaki FDB kaydıyla MAC/IP ilişkilendirmesi. |

İlk üç komut zorunludur. Kimlik veya port çıktısı tanınmazsa toplama güvenli biçimde başarısız olur ve son başarılı envanter korunur. Diğer üç komut opsiyoneldir; desteklenmeyen ya da yetkisiz çıktı uyarı/`unsupported` durumuyla gösterilir.

## Fiziksel doğruluk ve sınırlar

`WS-C2960X-48FPD-L` model adı port üretmek için kullanılmaz. Fiziksel portlar yalnız `show interfaces status` satırlarından oluşturulur; bakır/SFP/QSFP sınıfı yalnız açık `Type` kanıtından belirlenir. Model kataloğundaki nominal kapasite eksik CLI satırlarını tamamlamaz. Portların kasa üzerindeki birebir mekanik konumu doğrulanmış sayılmaz (`verified_layout=false`).

Collector salt okunurdur; konfigürasyon uygulama, yedekleme, LLDP/CDP kablo ilişkisi, PoE tüketimi, stack üyesi kasa geometrisi ve zamanlanmış polling bu kapsamda değildir. SSH terminalinde ise uzak Cisco hesabının kendi yetkileri geçerlidir; ayrı, en az ayrıcalıklı bir hesap kullanın.
Collector `enable` parolası göndermez; tanımlanan cihaz hesabı yukarıdaki `show` komutlarını doğrudan çalıştırabilmelidir.

Kaynaklar: [Cisco Catalyst 2960-X arayüz komutları](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst2960x/software/15-2_7_e/command_reference/b_1527_2960x_cr/interface_and_hardware_commands.html), [Cisco Catalyst 2960-X ürün ailesi](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst2960x/hardware/installation/guide/b_c2960x_hig/b_c2960x_hig_chapter_01.html).

Parser ve gerçek yerel legacy SSH/PTY sözleşmesi `backend/tests/test_cisco.py` içinde temizlenmiş fixture'larla test edilir. Bu testler fiziksel cihaz kabulü değildir; gerçek switch üzerinde host key doğrulaması, yetkili kullanıcıyla bağlantı ve canlı çıktı uyumu ayrıca doğrulanmalıdır.
