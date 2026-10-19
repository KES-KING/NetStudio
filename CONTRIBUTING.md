# Katkı rehberi

Stocc NetStudio'ya kod, dokümantasyon, test ve erişilebilirlik katkıları yapabilirsiniz. Türkçe ve İngilizce issue/PR kabul edilir. Tartışmalarda kişileri değil teknik önerileri değerlendirin; saygılı, somut ve tekrar üretilebilir geri bildirim verin.

## Doğru kanalı seçin

- Hatalar ve özellik önerileri: [issue şablonları](https://github.com/KES-KING/stocc-netstudio/issues/new/choose).
- Kurulum ve kullanım soruları: [Discussions](https://github.com/KES-KING/stocc-netstudio/discussions).
- Güvenlik açıkları: [özel bildirim](https://github.com/KES-KING/stocc-netstudio/security/advisories/new); public issue/PR açmayın.

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

Compose yapılandırma kontrolü repository kökünde `docker compose config --quiet` ile yapılır. WebSocket/SSH tarayıcı testleri için README'deki [izole QA ortamını](README.md#izole-tarayıcı-test-ortamı) kullanın; seed komutunu gerçek kurulumda çalıştırmayın.

## Projeye özgü kurallar

- Eksik, desteklenmeyen veya eski metrikleri sıfır/sağlıklı olarak göstermeyin. Fiziksel port ve mantıksal arayüz kimliklerini koruyun.
- Port türünü, fiziksel bağlantıyı veya üretici özelliğini veriden doğrulanmadıkça tahmin etmeyin.
- Trafik birimlerini ve kapsamını belirtin; RX/TX'i tek yön kapasitesine birlikte bölmeyin.
- Erişim, sır yönetimi ve terminal yetkisini backend'de doğrulayın. Host key ve CIDR kontrollerini gevşetmeyin.
- `.env`, `.secrets/`, sertifika özel anahtarları veya veritabanı dump'larını commit etmeyin.
- Migration'lar mevcut verileri korumalıdır. Yıkıcı değişiklikler, taşıma ve geri dönüş gereksinimleri açıkça tartışılmalıdır.
- Test fixture'ları üretim veri kaynağı değildir. Yerel/QA sonuçlarını fiziksel cihaz veya üretim doğrulaması olarak raporlamayın.

## Pull request

PR açıklamasında amaç, kapsam, test komutları/sonuçları, çalıştırılmayan kontroller ve dağıtım/migration etkisini belirtin. Arayüz değişikliklerinde sır içermeyen ekran görüntüleri ekleyin. Yeni özellikler için önce kısa bir issue ile kapsamı konuşmak incelemeyi kolaylaştırır.

Katkılar projenin [AGPL-3.0-only lisansı](LICENSE) altında sunulur. Yalnız paylaşmaya yetkili olduğunuz kod ve varlıkları ekleyin; üçüncü taraf lisans/telif bildirimlerini koruyun. Bu rehber ayrıca bir telif devri istemez.
