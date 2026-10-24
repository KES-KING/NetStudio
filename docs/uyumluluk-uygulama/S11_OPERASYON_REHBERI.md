# S11 fiziksel kabul, benchmark ve rollout operasyon rehberi

Bu rehber yalnız sahibi olunan veya açık test yetkisi bulunan cihazlarda
uygulanır. NetStudio cihaz konfigürasyonu yazmaz. Ham CLI/API/SNMP çıktısı,
parola, key, token, community, gerçek yönetim adresi, tam seri numarası veya
müşteri/site bilgisi public repository'ye alınmaz.

## 1. Güven modeli

S11 yayın zinciri aşağıdaki sırayı uygular:

```text
yetkili lab scope
  → redakte fiziksel artifact + SHA-256
  → exact tuple capability/negatif/operasyon sonuçları
  → 24 saat benchmark (supported için)
  → dört rol review'u
  → offline Ed25519 imzası
  → yerel release-admin doğrulama/import
  → API'de her okumada imza+commit+profil+parser+expiry doğrulaması
  → canary → pilot → general gözlemleri
```

Private imza anahtarı repository'ye, Docker volume'üne veya çalışan API'ye
verilmez. `release-admin` yalnız imzalı bundle, public trust-root ve redakte
artifact okur; keyring volume'ünü mount etmez. API public trust-root volume'ünü
salt okunur kullanır. Düz SQL ile eklenen veya sonradan değiştirilen karar,
geçerli imza olmadan katalog statüsünü yükseltemez.

Docker named volume'ü root-owned oluştuğu için `release-admin` tek-seferlik UID
0 çalışır; `cap_drop: ALL`, `no-new-privileges`, salt-okunur root filesystem,
DB ağı ve yalnız input/public-state mount'larıyla sınırlıdır. Docker socket,
private imza anahtarı ve uygulama keyring'i bu serviste yoktur.

## 2. Lab scope hazırlığı — S11-01

[`S11_LAB_SCOPE.json`](S11_LAB_SCOPE.json) kopyalanıp kontrollü kabul deposunda
şu sırsız bilgilerle doldurulur:

- yetki referansı ve geçerlilik sonu,
- üretici, exact model, hardware revision, OS ailesi/exact sürümü,
- standalone/controller/cloud/local management mode,
- test edilecek SSH/SNMP/API transportu,
- read-only hesap ve ağ izolasyonu kontrol sonucu,
- yedek/geri dönüş sorumlusu,
- ham kanıtın erişim sınıfı ve redaksiyon sorumluları.

Güvenlik maddelerinden biri eksikse hedef `BLOCKED` kalır. `unknown`, `*` veya
redakte exact tuple ile fiziksel yayın kararı oluşturulamaz.

## 3. Kanıt ve capability çalışması — S11-02–S11-04

Her exact tuple için [`KABUL_VE_KANIT_SABLONU.md`](KABUL_VE_KANIT_SABLONU.md)
doldurulur. En az şu sonuçlar ayrı kanıtlanır:

- `system_identity`, `fast`, `health`, `network`, `inventory` içinden profilin
  gerçekten bildirdiği capability grupları,
- interface adı/kalıcı ID/ifIndex, fiziksel port, 64-bit sayaç ve reset epoch'u,
- VLAN/PVID/trunk, FDB, ARP/NDP, LLDP ve LAG yalnız uygulanabildiği kapsamda,
- reboot, firmware değişimi, credential reddi, SSH host-key değişimi, API TLS
  hatası, SNMP auth hatası, timeout, kısmi/bozuk çıktı ve kimlik çelişkisi,
- ham çıktı/sır sızıntısı olmaması ve cihaz CPU/poll süresi.

Redakte artifact iki farklı kişi tarafından incelenir ve yerel olarak hash'lenir:

```bash
sha256sum artifacts/release/physical-evidence.json
```

Bundle içindeki `physical_evidence.sha256` ile bütün capability/gate
`evidence_sha256` alanları aynı redakte fiziksel artifact hash'ine bağlanır.
Uygulama import sırasında fiziksel ana artifact dosyasını yeniden hash'ler;
farklı hash kullanan sonuçlar reddedilir.

## 4. Benchmark — S11-05/S11-06

DB'deki iş süreleri, queue lateness ve veri satırları için başlangıç snapshot'ı:

```bash
docker compose --profile release-admin run --rm release-admin \
  benchmark-snapshot \
  --since 2026-10-24T00:00:00+03:00 \
  --until 2026-10-25T00:00:00+03:00
```

Bu çıktı tek başına PASS değildir. Aşağıdaki dış ölçümler aynı 24 saatlik pencere
ve transport/topoloji dağılımıyla eklenmeden `metrics_complete=true` yazılmaz:

- API/DB/worker CPU ve RSS,
- PostgreSQL IO, depolama büyümesi ve retention/rollup sonucu,
- düşük/orta/yüksek latency ve loss dağılımı,
- SSH/SNMP/API cihaz sayısı ve poll aralıkları,
- cihaz CPU etkisi, rate-limit, error ve partial oranları,
- worker restart/lease recovery ve DB bakım zamanları.

Benchmark kanıtı en fazla 90 gün; fiziksel kanıt ve yayın kararı en fazla 180 gün
geçerlidir. “100 cihaz” veya başka kapasite sayısı, aynı yük şekli gerçekten
ölçülmedikçe yayımlanmaz.

## 5. İmzalama, doğrulama ve import — S11-07/S11-08

Karar payload'ı `backend/app/release_acceptance.py` içindeki strict sözleşmeye
uymalıdır. `candidate` için kimlik+envanter, migration/E2E ve iki rol review'u;
`supported` için bütün ilan edilen capability'ler, negatif/operasyon kapıları,
24 saat benchmark ve dört rol review'u zorunludur.

İmzalama, private key'in bulunduğu kontrollü offline makinede yapılır:

```bash
PYTHONPATH=backend .venv/bin/python -m app.release_cli sign-decision \
  --payload decision.json \
  --private-key /protected/release-ed25519.pem \
  --key-id release-2026 > signed-decision.json
```

Private key dosyası `0600` değilse komut reddeder. Public trust-root ve bundle
önce doğrulanır, sonra normal kurulumu etkilemeyen profilli servisle import edilir:

Önce `/readyz` yanıtındaki `revision` alanının karar payload'ındaki 40 haneli
`source_revision` ile aynı olduğunu doğrulayın. `unknown`, farklı commit veya
geçersiz trust-root runtime desteğini fail-closed kapalı tutar. Resmî updater
kurulum sırasında `NETSTUDIO_BUILD_REVISION` değerini seçilen commit'e yazar;
elle image üreten operatör aynı build argümanını açıkça vermelidir.

```bash
mkdir -p artifacts/release
# Bu dizine yalnız redakte fiziksel/benchmark artifact'ları, imzalı bundle ve public trust-root koyun.
docker compose --profile release-admin run --rm release-admin \
  install-trust-roots --source /run/release-input/trust-roots.json
docker compose --profile release-admin run --rm release-admin \
  verify-decision --bundle /run/release-input/signed-decision.json \
  --trust-roots /run/release-input/trust-roots.json
docker compose --profile release-admin run --rm release-admin \
  import-decision --bundle /run/release-input/signed-decision.json \
  --trust-roots /run/release-input/trust-roots.json \
  --artifact /run/release-input/physical-evidence.json \
  --benchmark-artifact /run/release-input/benchmark-evidence.json \
  --actor release:CHANGE-REFERENCE
```

`supported` kararı için benchmark artifact'ı da dosyadan yeniden hash'lenir ve
`benchmark.evidence_sha256` ile eşleşmek zorundadır. `candidate` payload'ında
benchmark kanıtı yoksa `--benchmark-artifact` verilmez. Geleceğe tarihli karar
ve rollout gözlemleri saat kayması toleransını aşarsa reddedilir; henüz zamanı
gelmemiş imzalı satır runtime durumunu yükseltmez.

`artifacts/` Git tarafından yok sayılır. Import; mevcut cihazı, secret'ı, host
key'i, envanteri veya işi değiştirmez. Aynı karar kimliğinin üzerine yazmaz.
Trust-root kurulumu public anahtar volume'ünü atomik değiştirir; API bu volume'ü
salt okunur görür.

Geri çekme ayrı `action=withdraw` payload'ı ve security+release review imzası
ister. Geri çekme süresi asıl kararın sonuna kadar uzanmalıdır. Signed withdrawal
aynı `verify-decision` ve `import-decision` komutlarıyla içeri alınır; artifact
parametresi gerekmez. Import, hedef kararın capability kayıtlarına karar-kapsamlı
`withdrawn` tombstone'ları yazar; daha yeni bağımsız bir kararın acceptance
kayıtları etkilenmez.

## 6. Rollout ve hata bütçesi — S11-10

Karar şu sıralı aşamaları taşır: `canary → pilot → general`. Her aşama için
iş sayısı, error/partial sayısı, queue lateness p95, cihaz sayısı ve kanıt hash'i
içeren rollout payload'ı offline imzalanır ve alınır:

```bash
PYTHONPATH=backend .venv/bin/python -m app.release_cli sign-rollout \
  --payload rollout.json --private-key /protected/release-ed25519.pem \
  --key-id release-2026 > signed-rollout.json
docker compose --profile release-admin run --rm release-admin \
  import-rollout --bundle /run/release-input/signed-rollout.json \
  --trust-roots /run/release-input/trust-roots.json \
  --artifact /run/release-input/rollout-evidence.json \
  --actor release:CHANGE-REFERENCE
```

Import, rollout artifact dosyasını yeniden hash'ler ve imzalı payload içindeki
`evidence_sha256` ile eşleşmeyen gözlemi reddeder.

Bir aşama atlanamaz veya geriye alınamaz; sonraki aşama için önceki aşamanın
minimum süre ve hata bütçesini geçen imzalı gözlemi gerekir. İmzalı `supported`
kararı `general` tamamlanana kadar runtime kataloğunda `candidate` kalır. Error
oranı, partial oranı, queue lateness p95, minimum süre veya aşama sırası ihlal
edilirse profil `experimental` seviyesine iner. Aynı karar altındaki sonraki
sağlıklı ölçüm bu ihlali silmez; yeni fiziksel/release review kararı gerekir.
`production_accepted` yine `false` kalır.

## 7. Migration ve rollback

`0012_release_acceptance` yalnız `driver_release_decisions` ve
`driver_rollout_observations` tablolarını ekler. Normal application rollback'i
önceki imajı çalıştırır ve bu tabloları/verileri yerinde bırakır. Volume, tablo,
credential veya kanıt silinmez. Alembic downgrade yalnız boş/disposable QA için
test edilir.

Rollout geri alma sırası:

1. yeni aşamayı durdur ve yeni cihaz ekleme/poll genişletmesini askıya al,
2. imzalı withdrawal kararı al; katalog statüsünün düştüğünü doğrula,
3. gerekiyorsa önceki uygulama imajını aynı DB/keyring/volume'lerle çalıştır,
4. cihaz, secret ciphertext, host key, binding, last-good envanter, job ve audit
   hash/count kontrollerini karşılaştır,
5. yeni karar için kök neden, düzeltme ve yeniden kabul planı aç.

`docker compose down -v`, volume silme veya mevcut keyring'i yeniden oluşturma
bu rollback'in parçası değildir.
