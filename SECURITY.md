# Güvenlik politikası

## Özel bildirim

Güvenlik açıklarını public issue veya pull request içinde paylaşmayın.
[Özel güvenlik bildirimi](https://github.com/KES-KING/NetStudio/security/advisories/new) kullanın.
Etkilenen commit/sürümü, ön koşulları, beklenen etkiyi ve kendi izole ortamınızda tekrar üretim adımlarını belirtin.
Parola, özel anahtar, oturum cookie'si, gerçek cihaz verisi veya ham terminal kaydı göndermeyin.

## Kapsam ve güven sınırları

Frontend, backend, bağımlılıklar, CI ve Docker dağıtım yapılandırması inceleme kapsamındadır.
Tarayıcı girdileri, telemetri ve uzak cihaz/terminal çıktıları güvenilmeyen veridir.
Cihaz sırları, şifreleme anahtarları, kullanıcı oturumları ve site bazlı erişim korunmalıdır.

## Korunması gereken özellikler

- Cihaz erişimi ve terminal açma yetkisi backend'de doğrulanmalıdır.
- HTTP mutasyonları ve WebSocket bağlantıları oturum/origin denetimlerini korumalıdır.
- SSH hedefi yalnız yetkili kullanıcı tarafından eklenmiş cihazın güncel yönetim IP/port kaydından gelmelidir. Cihaz ekleme bu hedefin bağlantı onayıdır; tarayıcıdan serbest hedef kabul edilmez.
- `NETSTUDIO_SSH_ALLOWED_CIDRS` isteğe bağlı kurulum geneli ek kısıttır: boşsa kayıtlı hedefler kabul edilir; doluysa bu sınır da uygulanır. Geçersiz kısıt güvenli biçimde reddedilmelidir. Geçersiz, multicast ve link-local hedefler reddedilir; loopback hedefler yalnız açık CIDR izniyle kabul edilir.
- SSH host anahtarı bağımsız doğrulanıp kaydedilmelidir; ilk bağlantıda otomatik güven veya anahtar değişiminde sessiz kabul yapılmaz.
- Eski SSH algoritmaları varsayılan olarak açılmaz. Cihaz bazlı açık izin audit edilir; otomatik profil yalnız bu izin kapsamında en fazla dört el sıkışması/30 saniye deneyebilir. Yanlış parola, host key değişimi veya yetki hatası algoritma deneme gerekçesi değildir. Uyumluluk seçimi host key, oturum veya rol/site kontrolünü kaldırmaz.
- Host key keşfi kimlik bilgisi göndermez; keşif güven onayı değildir. Tek kullanımlık, 10 dakika geçerli aday kullanıcıya/cihaza/bağlantı sürümüne bağlanır. Değiştirme açık kullanıcı onayı gerektirir.
- Zamanlanmış işler etkin cihaz politikasının sürümüne bağlı sistem kimliğiyle; manuel işler güncel kullanıcı/site yetkisiyle çalışır. Worker lease kaybında ağ işlemleri durmalı ve eski sonuç envanteri ezememelidir.
- SNMP yalnız kayıtlı IP'de v3 authPriv ile, sayısal OID allowlist'i içindeki sınırlı GET/GETNEXT/GETBULK okumaları yapar. SNMP sırları protokol ayrımlı AAD ile şifrelenir; v1/v2c veya SET kullanılmaz.
- Cihaz sırları okuma API'lerine, frontend kalıcı depolarına veya genel loglara sızmamalıdır.
- Eksik anahtar, geçersiz oturum veya yetki kaybında ilgili işlem güvenli biçimde reddedilmelidir.

## İnceleme sınırları

Bu metin güvenlik sertifikası veya testlerin bütün kontrolleri kanıtladığı iddiası değildir.
API'nin süreç içi oturum limitleri tek worker varsayar; üretim erişimi HTTPS/WSS gerektirir.
Bilinen sınırlamalar otomatik olarak kabul edilmiş risk veya raporlama istisnası sayılmaz.
Yalnız sahibi olduğunuz veya açıkça test izni aldığınız sistemleri kullanın.
