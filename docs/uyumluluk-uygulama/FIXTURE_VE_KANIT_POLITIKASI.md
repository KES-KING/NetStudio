# Fixture ve kabul kanıtı politikası

Bu politika uyumluluk fixture'larının ve kabul artifact'larının repository'ye
alınma koşullarını belirler. [`SECURITY.md`](../../SECURITY.md) daha sıkı bir
sınır koyarsa o sınır uygulanır.

## 1. Kabul edilebilir kaynaklar

- Proje ekibinin kontrollü laboratuvarda ürettiği ve paylaşma yetkisi bulunan
  read-only komut/API/SNMP çıktısı,
- lisansı yeniden dağıtıma açık üretici örnekleri,
- yalnız test amacıyla sentetik üretilmiş çıktı,
- veri sahibi tarafından açıkça izin verilmiş, kapsamı kayıtlı ve temizlenmiş
  çıktı.

Lisansı veya paylaşma yetkisi belirsiz çıktı kabul edilmez. İnternetten bulunan
config/output dosyası kaynak ve lisans doğrulanmadan fixture'a dönüştürülmez.

## 2. Repository'ye girmesi yasak içerik

- parola, token, API anahtarı, SNMP community/auth/privacy sırrı, private key,
  passphrase, session cookie ve gerçek kullanıcı anahtarı,
- tam `running-config`/`startup-config`, yetkilendirme verisi veya secret içeren
  debug/support bundle,
- gerçek müşteri adı, kullanıcı adı, e-posta, hostname, domain, public/private IP,
  MAC, seri numarası, asset/contract ID ve topoloji etiketi,
- gerçek SSH host key/fingerprint veya cihaz sertifikası private materyali,
- paylaşma izni olmayan üretici/müşteri çıktısı,
- fixture testi için gerekli olmayan ham çıktı bölümleri.

## 3. Deterministik temizleme

Temizleme tekrar çalıştırıldığında aynı ilişkiyi koruyan sentetik değerler
üretmelidir. Önerilen değerler:

| Veri | Ayrılmış/sentetik biçim |
|---|---|
| IPv4 | `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` |
| IPv6 | `2001:db8::/32` |
| MAC | Yerel yönetilen sentetik adres, ör. `02:00:00:00:00:01` |
| Hostname/domain | `switch-01.example.test` |
| Kullanıcı | `test-operator` |
| Seri/asset | `TEST-SERIAL-0001`, `TEST-ASSET-0001` |
| Sırlar | Gerçek biçimi taklit etmeyen `test-only-*` belirteci |

Port adı, slot ilişkisi, tablo başlığı, boşluk ve vendor parser'ını etkileyen söz
dizimi korunur. Kimlik alanı çıkarılamıyorsa kararlı sentetik değerle değiştirilir;
boşaltmak parser davranışını değiştiriyorsa bu durum metadata'da açıklanır.

## 4. Ham kanıt ve repository artifact'ı

Ham fiziksel çıktı repository dışında, erişim kontrollü kanıt deposunda tutulur.
Repository'ye yalnız:

1. minimize edilmiş ve temizlenmiş fixture,
2. temizlenmiş artifact'ın SHA-256 hash'i,
3. profil/model/OS/management mode/transport metadata'sı,
4. toplama zamanı ve izin/lisans kaynağı,
5. temizleme yöntemi/sürümü,
6. desteklenen capability ve bilinen istisnalar

girer. Public commit, ham kanıt deposuna erişim bilgisi veya müşteri kimliği
içermez. Hash, ham dosya hash'i değil yayımlanan temizlenmiş artifact hash'idir.

## 5. İnceleme ve tarama kapısı

- Fiziksel cihazdan veya üreticiye ait çıktıdan türeyen artifact, hazırlayandan
  farklı iki inceleyen tarafından veri sızıntısı ve teknik temsil açısından
  onaylanır.
- Secret scanner ve repository'nin mevcut test/lint kontrolleri commit öncesi
  çalıştırılır; bulgu açıklanmadan bypass edilmez.
- Test sırrı yalnız loopback/sentetik fixture bağlamında ve açıkça
  `test-only-*` biçiminde olabilir; production benzeri token/key kabul edilmez.
- Fixture değişikliği parser beklenen çıktısı ve profil revizyonuyla birlikte
  incelenir.
- Existing fixture'lar bu politika öncesi oluşturulduysa geriye dönük onaylanmış
  sayılmaz; yeni destek/physical kabul iddiasında kullanılmadan yeniden denetlenir.

## 6. Katkı kontrol listesi

- [ ] Kaynağın sahibi, paylaşım izni ve lisansı kayıtlı.
- [ ] Yalnız gerekli read-only çıktı bölümü bırakıldı.
- [ ] Sır, kullanıcı, IP, MAC, hostname, seri ve müşteri kimliği temizlendi.
- [ ] Ayrılmış/sentetik değerler kullanıldı; ilişkiler deterministik kaldı.
- [ ] Temizlenmiş artifact SHA-256 ve metadata kaydedildi.
- [ ] Fixture profil/model/OS/mode/transport kapsamına bağlandı.
- [ ] Parser pozitif, eksik alan ve bozuk/kısmi çıktı testleri güncellendi.
- [ ] Secret scanner ve ilgili testler geçti.
- [ ] Gerekli iki bağımsız inceleme tamamlandı.
- [ ] Kanıt süresi ve invalidation koşulu ADR-COMPAT-005'e göre kaydedildi.

## 7. Sızıntı müdahalesi

Şüpheli fixture yayından kaldırılır; ilgili sır derhal döndürülür/revoke edilir,
erişim ve dağıtım kapsamı belirlenir, repository geçmişi ve yayın artifact'ları
olay planına göre temizlenir. Yalnız dosyayı sonraki committe silmek yeterli
değildir. Etkilenen kabul kaydı geçersizleştirilir ve yeniden kanıt üretilir.

