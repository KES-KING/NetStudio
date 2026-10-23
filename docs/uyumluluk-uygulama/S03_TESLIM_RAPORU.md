# S03 teslim raporu — katalog tabanlı cihaz ve uyumluluk arayüzü

| Alan | Sonuç |
|---|---|
| Sprint | S03 — Katalog tabanlı cihaz ve uyumluluk arayüzü |
| Tarih | 23 Ekim 2026 |
| Başlangıç kaynak commit | `a04f338421a1975f78bb911c68fb1c5b3e2130df` |
| Tamamlanan backlog | S03-01–S03-08 |
| Migration etkisi | Yok; S02'nin additive binding ve acceptance tabloları kullanılır |
| Yeni cihaz/parser desteği | Yok; arayüz katalog gerçeğini gösterir ve seçilemez profilleri engeller |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI; izole fixture/SSH laboratuvarı fiziksel kabul değildir |
| Benchmark | `REQUIRES BENCHMARK` |
| Production kabulü | `false` |
| Ana tasarım etkisi | var — cihaz ekleme, bağlantı ve cihaz detay kompozisyonu maddi değişti |

## 1. İş paketi teslimleri

| ID | Durum | Uygulama/kanıt |
|---|---|---|
| S03-01 | Tamamlandı | `contracts.ts` ve `compatibility.ts`, katalog v2 profil/transport/yönetim modu/durumlarını typed tüketir |
| S03-02 | Tamamlandı | Cihaz ekleme akışı canlı katalogdan **üretici → işletim sistemi profili → yönetim modu** sırasını uygular |
| S03-03 | Tamamlandı | `catalog_only`, engelli ve protokolce/politikaca unsupported profiller açıklamasıyla görünür; HTML seçeneği disabled ve backend seçimi reddeder |
| S03-04 | Tamamlandı | Legacy, çözümlenmemiş veya çelişkili kayıt sessizce taşınmaz; yetkili kullanıcı açık profil seçimi ve bağlantı/job etkisi onayı verir |
| S03-05 | Tamamlandı | Credential yüzeyi profilin uygulanmış SSH/SNMP/API transportlarına göre değişir; ilgisiz sır alanı gösterilmez ve hiçbir sır API cevabından doldurulmaz |
| S03-06 | Tamamlandı | Cihaz detayına profil, revision, mode, çözüm güveni, transport, capability, redakte kanıt ve acceptance kapsamını gösteren **Uyumluluk** paneli eklendi |
| S03-07 | Tamamlandı | `partial`, `unsupported`, `permission_denied`, `parse_error`, `timeout`, `error` ve süresi geçmiş kanıt ayrı metinlerle sunulur |
| S03-08 | Tamamlandı | 320/390 px, kısa viewport, uzun metin, klavye odağı, hata özeti, ekran okuyucu rolleri ve reduced-motion regresyonları doğrulandı |

## 2. Katalog ve seçim sözleşmesi

Form seçeneklerinin kaynağı yalnız `GET /api/v1/driver-catalog` cevabındaki
kanonik `profiles` alanıdır. Frontend sabit bir çalışır sürücü listesi üretmez.
Profilin `selectable` ve `implementation_status` değerleri hem görünür seçenek
durumunu hem de açıklamasını belirler.

İstemci denetimi güvenlik sınırı değildir. Backend aşağıdaki bütün yazma yollarında
aynı seçilebilirlik kontrolünü uygular:

- yeni cihazın açık `configured_profile_id` alanı;
- kanonik profile dönüşen legacy `collector` ile cihaz oluşturma;
- `PUT /devices/{id}/driver-profile`;
- bağlantı ayarlarında doğrudan profil veya collector alias'ı değiştirme.

Bilinmeyen profil `422`, katalogda bulunup uygulanmamış/seçilemez profil `409
driver_profile_not_selectable` döndürür. S02 öncesinde yazılmış katalog-only
binding okunabilir kalır; kullanıcı kaydı değiştirmedikçe geriye dönük bakım
isteği engellenmez. Ancak legacy collector ile seçilemez profile kaçış yapılamaz.

Kanonik uygulanmış profil seçildiğinde runtime collector profilin
`runtime_driver_id` değeriyle eşleşir. Önceki `external` değeri yeni profilin
çalışan collector'ını gölgeleyemez. Profil değişimi S02 sözleşmesi uyarınca
connection revision'ı artırır, capability/SSH cache'ini temizler, açık terminali
kapatır ve eski işlerin sonucunu fence eder.

## 3. Cihaz ekleme ve bağlantı akışı

Yeni cihaz formu dört açık kaynak modu sunar:

1. kanonik sürücü profili;
2. kanıtla otomatik profil çözümü;
3. harici toplayıcı;
4. NOS profili olmayan altyapı adaptörü.

Kanonik akışta üretici seçimi profil listesini daraltır; profil yönetim modu ve
uygulanmış transport seçeneklerini belirler. Planlı/engelli transportlar bilgi
amacıyla görünür fakat credential seçimi olamaz. SSH seçilirse SSH güvenlik ve
kimlik alanları, SNMP seçilirse yalnız authPriv sonraki adımı, API seçilirse
uygulanmış browser credential akışı olmadığına dair açık sınır gösterilir.
Harici toplayıcı modunda NetStudio cihaz sırrı istemez.

Bağlantı dialog'u da aynı katalog profilini kullanır. Kayıtlı sırın varlığı yalnız
`configured` bilgisiyle belirtilir; kullanıcı adı, parola, private key,
passphrase ve SNMP sırları boş açılır. Boş gönderim mevcut şifreli kaydı koruyan
backend sözleşmesini değiştirmez.

## 4. Uyumluluk ve kanıt görünümü

Detay paneli aşağıdaki ayrımları birlikte fakat birbirine dönüştürmeden gösterir:

- yapılandırılan ve collector tarafından çözümlenen profil;
- profil revision'ı, management mode, çözüm durumu/güveni ve çelişkiler;
- katalog release, implementation ve verification düzeyi;
- profil transportlarının gerçek durumu ve sürüm özeti;
- cihaz capability gözlemlerinin durum, transport, zaman ve güvenli reason kodu;
- redakte kimlik kanıtı;
- eşleşen/süresi geçmemiş acceptance kayıt sayısı ve ayrı
  `production_accepted` değeri.

`supported` katalog etiketi tek başına cihaza “Destekleniyor” etiketi vermez.
Arayüz ancak cihazın tam tuple kapsamına uyan, süresi geçmemiş
`physical_validated` acceptance kaydı varsa bu etiketi gösterir. Fixture veya
izole transport laboratuvarı sonucu fiziksel/production desteğine yükseltilmez;
production kabulü ayrıca ve varsayılan olarak **Yok** görünür.

Viewer paneli ve kanıtı salt okunur görür. `inventory.manage` yetkili kullanıcı
profil editörünü görür. Legacy/belirsiz kayıtta açık onay checkbox'ı tamamlanmadan
kayıt düğmesi etkinleşmez; backend RBAC/CSRF/site kapsamı korunur.

## 5. Erişilebilirlik ve responsive davranış

- Dialog açıldığında ilk anlamlı alan odaklanır; hata özeti `role=alert`,
  `tabIndex=-1` ile programatik odağı alır.
- Fieldset/legend, label, status/alert ve region başlıkları form sırasını ve
  ekran okuyucu bağlamını taşır.
- Uzun profil/kanıt/reason metni taşmadan kırılır; yalnız geniş veri tablosu kendi
  yatay kaydırma alanını kullanır.
- Profil/transport grid'i dar ekranda tek kolona iner; dialog yüksekliği viewport
  içinde kalır ve kendi gövdesi kayar.
- Mobil menü arka katmanı ve tam ekran ön panel gerçek viewport genişliğini
  kaplar; scrollbar varlığı tıklanabilir dış alanı veya modal genişliğini daraltmaz.
- Yeni yüzey zorunlu harekete dayanmaz; reduced-motion tarayıcı senaryosu aynı
  işlevi animasyonsuz doğrular.

## 6. Test ve doğrulama

| Kontrol | Sonuç |
|---|---|
| Backend S03 hedefli API testleri | `6 passed`; seçilemez profil, legacy bypass ve runtime collector geçişi dahil |
| Backend tam paket | `248 passed, 3 skipped`; 14 mevcut bağımlılık/deprecation uyarısı |
| Frontend unit | 11 dosya / 63 test PASS; katalog filtreleme, alias uyarısı, acceptance scope ve boş sır taslağı dahil |
| Frontend lint | PASS |
| Frontend typecheck | PASS |
| Frontend production build | PASS; 12 route üretildi |
| Playwright | 52 senaryonun 51'i PASS; açık internet isteyen 1 GitHub kontrolü opt-in olmadığı için SKIP |
| S03 Playwright | 2/2 PASS; katalog durumları, açık migration onayı, viewer/superadmin, boş sırlar, mobil/kısa viewport, reduced-motion, odak ve konsol hatası |
| Gerçek izole SSH regresyonu | PASS; terminal bağlantısı, komut echo, resize/kapatma ve oturum koruma |
| Görsel kanıt | 1536×1024 viewport'tan üç kanonik README görüntüsü aynı çalışma ağacında yenilendi ve görsel incelendi |

Playwright tek 52-test komutunda çalıştırıldığında uygulamanın güvenlik amaçlı,
IP başına 5 dakikada 40 login sınırı son senaryoları `429` ile durdurur. Sınır
gevşetilmedi. Aynı imajlar, aynı izole veritabanı ve aynı kaynak ağacı korunarak
test dosyaları gruplar halinde çalıştırıldı; yalnız izole API süreci gruplar
arasında yeniden başlatıldı. Toplam 51 PASS ve 1 açık opt-in SKIP örtüşmeyen 52
senaryoyu ifade eder; başarısız ilk denemeler başarı olarak sayılmamıştır.

QA projesi `netstudio-s03-qa-native-20261023`, yalnız loopback'e açılan ayrı
PostgreSQL/API/web/SSH-lab portları ve ayrı Compose volume'leri kullandı.
Başlangıçta var olan başka Docker projesi/container'ı değiştirilmedi. QA kanıtı
sentetik envanter ve gerçek izole SSH transportudur; fiziksel switch kanıtı
değildir.

## 7. Çıkış kapısı sonucu ve kalan sınırlar

- Cihaz formu seçenekleri yalnız canlı API kataloğundan gelir: **PASS**.
- İstemci manipülasyonuyla seçilemez profil backend'de reddedilir: **PASS**.
- Fixture/lab sonucu fiziksel veya production destek olarak etiketlenmez:
  **PASS**.
- Gerçek Cisco/Huawei/Juniper cihaz, controller/cloud API, Safari/Firefox,
  production rollout ve kapasite testi: **ÇALIŞTIRILMADI**.
- S04 transport katmanı ve S05 fiziksel vendor kabul işleri bu sprintte
  uygulanmış sayılmaz.

S03 kod/fixture/browser kapsamıyla tamamlanmıştır. Herhangi bir profilin
`physical_validated`, tüm modellerde destekli veya `production_accepted` olduğu
iddia edilmez.
