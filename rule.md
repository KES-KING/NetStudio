# Proje kuralları

Bu dosya Stocc NetStudio üzerinde çalışan insanlar ve yapay zekâ araçları için ortak proje kurallarını tanımlar. Katkıya başlamadan önce bu dosyayı, [katkı rehberini](CONTRIBUTING.md) ve [güvenlik politikasını](SECURITY.md) okuyun. Ajanların çalışma ve teslim adımları [agent.md](agent.md) içindedir.

## 1. Mevcut çalışmayı koru

- Önce ilgili kaynak kodu, API sözleşmelerini, testleri ve çalışma ağacındaki değişiklikleri inceleyin. Kullanıcıya ait değişiklikleri geri almayın veya üzerlerine yazmayın.
- Kapsamı sınırlı tutun; çalışan cihaz, hesap, yetkilendirme, SSH ve veri toplama akışlarını koruyun.
- Kodda bulunmayan endpoint, alan, cihaz özelliği veya üretim yeteneği varsaymayın. Önemli varsayımları ve doğrulanamayan noktaları teslimde belirtin.

## 2. Görsel tasarım dili

- Ana içerik beyaz; yan menü ve gerekli navigasyon yüzeyleri gri/koyu gri olmalıdır. Renkleri mevcut ortak tokenlarla yönetin.
- Panel, buton, form, sekme ve modal köşelerinde temel kural `border-radius: 0` olmalıdır. Neon, parıltı, dekoratif gradyan, cam efekti ve yoğun gölge eklemeyin.
- Şeffaf NetStudio logolarının arkasına ayrı beyaz panel koymayın; gerekirse üzerinde bulundukları ortak yüzeyi okunabilirlik için açın.
- Mevcut istatistiksel grafiklerde Apache ECharts korunmalıdır; başka grafik kütüphanesiyle değiştirmeyin. Yeni düzenleme/şema yüzeyleri mevcut grafikleri ortadan kaldırmamalıdır.
- Ana sayfada grafikler cihazların dikey listesinden önce gelmelidir. Masaüstü yan menüsü ekran yüksekliği içinde sabit kalmalı; içerik gereksiz dış boşluklar olmadan kullanılabilir alanı doldurmalıdır.
- Yeni metinlerde mevcut Türkçe arayüz dilini koruyun. Açık eylem etiketleri, görünür klavye odağı, okunabilir kontrast ve mobil kullanım sağlayın.
- Cihaz/port çizimleri marka bağımsız ve envantere bağlı olmalıdır. Uydurma port, LED veya donanım özelliği eklemeyin; teknik sembollerde tutarlı SVG geometrisi kullanın.

## 3. Veri doğruluğu ve erişim

- Yükleniyor, veri yok, desteklenmiyor, toplama hatası, eski veri ve erişilemiyor durumlarını ayırın. Eksik veriyi sıfır veya sağlıklı durum olarak sunmayın.
- Fiziksel port, mantıksal arayüz ve breakout kimliklerini koruyun. Aktif bağlantıyı fiziksel olarak kablo takılı olmasıyla eşitlemeyin.
- Trafik birimini, yönünü ve kapsamını belirtin; RX/TX toplamını tek yön kapasitesine bölmeyin.
- MAC/IP gözlemi, L2 komşuluk, doğrulanmış fiziksel ilişki ve elle çizilen topoloji bağlantısını ayrı gösterin. MAC tablosundan kablo veya uç cihaz türü tahmin etmeyin.
- Üretim ekranlarına sabit/rastgele örnek değer bağlamayın. Fixture'lar yalnız izole test ortamına aittir.
- Rol/site, oturum, CSRF/origin, kayıtlı SSH hedefi ve host key kontrollerini backend'de koruyun. Yetkili cihaz ekleme kayıtlı IP/port için onaydır; cihaz başına `.env` izni gerekmez. Varsa kurulum geneli ek CIDR kısıtı uygulanır. Eski SSH algoritmaları yalnız cihaz bazında açık onayla seçilir. Ayrıntılar için [SECURITY.md](SECURITY.md) geçerlidir.
- Sırları, özel anahtarları, token/cookie'leri, gerçek müşteri verisini veya ham terminal içeriğini kaynak koda, loglara ya da public belgelere koymayın.

## 4. Docker ve mevcut veriler

- Başlatma, güncelleme ve işletim adımlarını doğrudan `docker compose` komutlarıyla anlatın; Make hedeflerini Docker kullanımının ön koşulu yapmayın.
- İşlemden önce Docker context, Compose proje adı, portlar ve volume hedeflerini doğrulayın. Çalışan kurulumları veya global context seçimini habersiz değiştirmeyin.
- Mevcut veritabanı, kullanıcılar, envanter, anahtarlar ve yedekler korunmalıdır. Normal geliştirme/test için `docker compose down -v` kullanmayın.
- QA seed'i mevcut veya üretim veritabanına uygulamayın; test için ayrı proje, port ve volume kullanın. Erişim sorununu aşmak için mevcut kullanıcıyı sıfırlamayın veya güvenlik kontrollerini gevşetmeyin.
- Migration ve dağıtım etkisini belgeleyin; kullanılan TLS override dosyalarını koruyun.

## 5. Her görsel güncellemede README görüntülerini yenile

**Arayüzde görünen her değişiklikte README'deki üç temel ekran görüntüsü güncel koddan yeniden alınmalıdır. Görüntü yenilemesi aynı değişiklik/PR kapsamının zorunlu parçasıdır; sonraki işe bırakılamaz.** Bu kural insanlar ve yapay zekâ ajanları için aynıdır.

Yeni sayfa veya bileşen, navigasyon, yerleşim, tema, logo, tipografi, görünen metin, grafik, port paneli, terminal veya responsive davranış değişikliği bu kuralı tetikler. Yalnız backend/iç refactor ya da dokümantasyon değişikliğinde görünür sonuç değişmiyorsa görüntü yenilemesi gerekmez; gerekçesini teslimde/PR'da belirtin.

| Zorunlu görünüm | Repository dosyası | Beklenen durum |
| --- | --- | --- |
| Ana sayfa | `docs/screenshots/dashboard.png` | Grafikler üstte, cihaz listesi altta; veriler yüklenmiş |
| Cihaz detayı — SSH kapalı | `docs/screenshots/device-detail.png` | Cihaz ön paneli, IP topolojisi ve teknik bilgiler görünür |
| Cihaz detayı — SSH açık | `docs/screenshots/device-detail-ssh.png` | Aynı cihazda gerçek, bağlı QA SSH oturumu; cihaz ve terminal yan yana |

1. [README'deki izole QA akışını](README.md#izole-tarayıcı-test-ortamı) kullanın. Üretim/müşteri cihazı yerine açıkça test verisi olan envanter ve izole SSH cihazı kullanın.
2. Son kodla çalışan uygulamayı gerçek tarayıcıda açın. Grafiklerin ve verilerin yüklenmesini, SSH açık görünümünde bağlantının gerçekten kurulmasını bekleyin.
3. Üç görüntüyü tutarlı masaüstü viewport, tarayıcı ölçeği ve cihaz bağlamıyla yeniden yakalayın. Değişen yüzeyi ayrıca mobil boyutta doğrulayın; mobil QA kanıtı bu üç dosyanın yerine geçmez.
4. Görüntüleri açıp inceleyin: kırpılmış/üst üste binen içerik, yükleme iskeleti, hata katmanı, eksik varlık veya hassas bilgi bulunmamalıdır. Görüntü üretimi, çizim/mockup veya eski kareyi yeniden adlandırma, çalışan uygulama ekran görüntüsünün yerine geçmez.
5. İncelenen son görüntüleri yukarıdaki dosyalara alın; README bağlantılarını, açıklamaları ve alternatif metinleri görünümle tutarlı tutun. Dosyalar aynı değişiklik/PR içinde yer almalıdır. Yeniden alınan bir kare birebir aynıysa yapay dosya farkı üretmeyin; yeniden doğrulandığını raporlayın.
6. Yakalama tarihi, test edilen sürüm/çalışma ağacı, QA ortamı, viewport ve test sonucunu PR/teslim açıklamasına yazın. Ek bir sayfanın görüntüsü, zorunlu üçlü setin yerini tutmaz.

Testlerin geçici dizine ürettiği ekran görüntüleri README'yi otomatik güncellemez. İncelenmiş üç PNG'nin `docs/screenshots/` altına alınması ayrı ve zorunlu adımdır. Gereken QA/SSH ortamı kurulamıyorsa engeli açıkça yazın; sahte görüntü kullanmayın ve görsel işi tamamlandı olarak bildirmeyin.

## 6. Doğrulama ve teslim

- Değişikliğe uygun test, lint, typecheck ve build kontrollerini çalıştırın; güncel komutlar [README](README.md#geliştirme-ve-doğrulama) ve [CONTRIBUTING.md](CONTRIBUTING.md) içindedir.
- Arayüz değişikliğinde build tek başına yeterli değildir: gerçek tarayıcıda ana etkileşimi, masaüstü/mobil yerleşimi ve konsol hatalarını kontrol edin.
- Çalıştırılan kontrolleri gerçek sonuçlarıyla, çalıştırılmayanları nedenleriyle raporlayın. Yerel/sentetik QA kanıtını fiziksel cihaz veya üretim kabulü olarak sunmayın.
- Görsel değişiklik için README görüntüleri kontrolünü teslim öncesi tamamlayın. Bu bir katkı/inceleme kuralıdır; otomatik CI zorlaması varmış gibi sunmayın.
- Kurallar değiştiğinde bu dosyayı esas alın; ajan yönergesi ve katkı/PR bağlantılarının tutarlı kaldığını doğrulayın.
