# Katkı rehberi

NetStudio'ya kod, dokümantasyon, test ve erişilebilirlik katkıları yapabilirsiniz. Türkçe ve İngilizce issue/PR kabul edilir. Tartışmalarda kişileri değil teknik önerileri değerlendirin; saygılı, somut ve tekrar üretilebilir geri bildirim verin.

Başlamadan önce insanlar ve yapay zekâ için ortak [proje kurallarını](rule.md) okuyun. Kodlama ajanları ayrıca [agent.md](agent.md) yönergesini izlemelidir; ajan giriş dosyası [AGENTS.md](AGENTS.md) bu belgelere yönlendirir.

## Doğru kanalı seçin

- Hatalar ve özellik önerileri: [issue şablonları](https://github.com/KES-KING/NetStudio/issues/new/choose).
- Kurulum ve kullanım soruları: [Discussions](https://github.com/KES-KING/NetStudio/discussions).
- Güvenlik açıkları: [özel bildirim](https://github.com/KES-KING/NetStudio/security/advisories/new); public issue/PR açmayın.

Parola, SSH private key, keyring, cookie/token, gerçek müşteri envanteri veya ham terminal kaydı paylaşmayın. Log ve ekran görüntülerini göndermeden önce hassas alanları temizleyin.

## Geliştirme ortamı

1. Depoyu fork edin ve kendi fork'unuzu clone edin.
2. Anlamlı bir çalışma dalı oluşturun: `git switch -c feat/kisa-aciklama`.
3. [README kurulum adımlarını](README.md#docker-ile-kurulum) izleyin. Docker komutları seçili context üzerinde çalışır; mevcut veritabanı/anahtar volume'lerini silmeyin.
4. Küçük ve tek konuya odaklı değişiklikler yapın. API veya metrik anlamı değişiyorsa test ve dokümantasyonu birlikte güncelleyin.

Yerel testler için Python 3.11+ (CI: 3.12) ve Node.js 22 kullanılır:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'backend[test]'
.venv/bin/pytest backend/tests
cd frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

Yeni kurulum örneğinin Compose kontrolü repository kökünde `docker compose --env-file .env.example config --quiet` ile yapılır. Mevcut kurulumda önce [ad geçişini](docs/name-transition.md) tamamlayıp kendi `.env` ve override dosyalarınızla `docker compose config --quiet` kullanın. WebSocket/SSH tarayıcı testleri için README'deki [izole QA ortamını](README.md#izole-tarayıcı-test-ortamı) kullanın; seed komutunu gerçek kurulumda çalıştırmayın.

## Projeye özgü kurallar

- Eksik, desteklenmeyen veya eski metrikleri sıfır/sağlıklı olarak göstermeyin. Fiziksel port ve mantıksal arayüz kimliklerini koruyun.
- Port türünü, fiziksel bağlantıyı veya üretici özelliğini veriden doğrulanmadıkça tahmin etmeyin.
- Trafik birimlerini ve kapsamını belirtin; RX/TX'i tek yön kapasitesine birlikte bölmeyin.
- Erişim, sır yönetimi ve terminal yetkisini backend'de doğrulayın. Yetkili cihaz kaydı hedef onayıdır; host key doğrulaması ve varsa ek kurulum CIDR sınırı korunur. Legacy SSH yalnız cihaz bazında açık onayla etkinleştirilir; [güvenlik politikasını](SECURITY.md) izleyin.
- `.env`, `.secrets/`, sertifika özel anahtarları veya veritabanı dump'larını commit etmeyin.
- Migration'lar mevcut verileri korumalıdır. Yıkıcı değişiklikler, taşıma ve geri dönüş gereksinimleri açıkça tartışılmalıdır.
- Test fixture'ları üretim veri kaynağı değildir. Yerel/QA sonuçlarını fiziksel cihaz veya üretim doğrulaması olarak raporlamayın.

## Pull request

PR açıklamasında amaç, kapsam, test komutları/sonuçları, çalıştırılmayan kontroller ve dağıtım/migration etkisini belirtin. **Her görsel değişiklikte README'deki üç görüntüyü birlikte yenileyin:** `docs/screenshots/dashboard.png`, `docs/screenshots/device-detail.png`, `docs/screenshots/device-detail-ssh.png`. Güncel uygulamadan, izole QA verisiyle alınan kareler aynı PR'a dahil olmalıdır; yalnız PR açıklamasına görüntü eklemek yeterli değildir. [Yakalama ve gizlilik kurallarını](rule.md#5-her-görsel-güncellemede-readme-görüntülerini-yenile) izleyin; tarih, viewport, test edilen sürüm ve sonucu belirtin. Görünür değişiklik yoksa bu adımın neden gerekmediğini açıklayın. Yeni özellikler için önce kısa bir issue ile kapsamı konuşmak incelemeyi kolaylaştırır.

Katkılar projenin [AGPL-3.0-only lisansı](LICENSE) altında sunulur. Yalnız paylaşmaya yetkili olduğunuz kod ve varlıkları ekleyin; üçüncü taraf lisans/telif bildirimlerini koruyun. Bu rehber ayrıca bir telif devri istemez.
