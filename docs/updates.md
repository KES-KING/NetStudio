# Ayarlar, bildirimler ve Docker güncelleyicisi

> Bu Compose sözleşmesini içermeyen eski bir kurulum önce repository’yi veri
> koruyan normal prosedürüyle bu sürüme getirmeli ve bir kez `docker compose up
> --build -d --wait` çalıştırmalıdır. `--build`, eski `local` imajlarının yeni
> kaynakla karıştırılmasını önler. Eski kod henüz var olmayan updater
> container’ını kendi kendine oluşturamaz. NetStudio ad geçişi yapılmadıysa önce
> [ad geçişi rehberini](name-transition.md) uygulayın; volume, veritabanı,
> kullanıcı veya anahtarları yeniden oluşturmayın.

## Sıfır hazırlıklı ilk kurulum

Resmî repository’nin temiz Git checkout’unda veya GitHub’dan indirilmiş değişmemiş
kaynak ZIP/tar arşivinde gereken uygulama komutları yalnızca:

```bash
docker compose up -d --wait
docker compose exec api python -m app.admin create-user --username admin --role superadmin --site '*'
```

`.env` kopyalamak, commit SHA yazmak, Python virtualenv hazırlamak, systemd unit
kurmak veya ayrı bootstrap scripti çalıştırmak gerekmez. `.env.example` yalnız
isteğe bağlı port/TLS/veritabanı/ağ özelleştirmeleri içindir. Docker Compose
2.37.2 veya üzeri gerekir.

İlk komutla ayrı `updater` servisi de başlar. Servis:

1. Kendi container etiketlerinden gerçek Compose proje adını, çalışma dizinini
   ve kullanılan base/TLS override dosyalarını bulur.
2. Salt okunur bağlanan Git checkout’un kirli olmadığını, `origin` adresinin
   resmî repository olduğunu ve HEAD commit’inin güncel `origin/main` geçmişinde
   bulunduğunu doğrular. `.git` içermeyen GitHub arşivinde ise ignore edilmeyen
   dosya yolu/içeriklerinin tamamını `origin/main` commit ağaçlarıyla karşılaştırır;
   yalnız birebir eşleşen resmî commit kabul edilir.
3. Kaynak `.env` dosyası varsa değiştirmeden özel state volume’üne kopyalar;
   yoksa Compose varsayılanlarından özel bir runtime env üretir. Doğrulanmış SHA
   ve proje adı yalnız bu `0600` dosyaya yazılır.
4. İlk build’in `unknown` etiketli imajlarını doğrulanmış SHA ile eşlerken üç
   immutable image ID’sini özel state volume’üne bağlar. Yalnız kaynak klasörünü
   ileri almak bu bağı değiştirmez; imajların da rebuild edilmesi gerekir.
5. PostgreSQL migration’ı ve API/web/worker sağlık kontrollerinden sonra kurulu
   SHA’yı kaydeder ve kalıcı güncelleme kuyruğunu dinler.

Özel durum, yedekler ve salt-okunur container’ın ihtiyaç duyduğu özel Docker
istemci çalışma dizini `${COMPOSE_PROJECT_NAME}_netstudio-updater-state`
volume’ündedir. `docker compose stop` veya normal `down` bunu silmez. Normal
işletimde `down -v` kullanmayın.

## Kullanıcı akışı

**Ayarlar → Güncellemeler** ekranı kurulu/main commit’i, GitHub’daki son 30
commit’i, kontrol zamanlarını, updater bağlantısını ve son 20 kurulum işlemini
gösterir. Üst bardaki güncelleme işareti bu sayfayı açar.

Public commit kontrolü varsayılan açıktır. Yeni kodu otomatik **kurma** ise
varsayılan kapalıdır. Yalnız superadmin:

- **Güncellemeleri kontrol et** ile public metadata kontrolü yapabilir.
- Risk metnini onaylayıp tek güncellemeyi kurabilir.
- Aynı açık onayla otomatik kurulumu açıp kapatabilir.

Otomatik politika açılınca tarayıcı kapalı olsa da yeni commit kalıcı kuyruğa
alınır. Yetkilendiren hesap devre dışı kalır veya superadmin rolünü kaybederse
bekleyen/çalışan iş güvenli biçimde durdurulur. Başarısız aynı SHA otomatik
döngüye alınmaz.

## Güven sınırı

`use_api_socket: true`, seçili yerel Docker Engine socket’ini yalnız `updater`
container’ına aktarır. Compose’un sunduğu host registry kimlik bilgileri update
işleminde yeniden kullanılmaz; Docker/BuildKit public imajlar için updater’ın
özel state volume’ündeki temiz ve yazılabilir istemci dizinini kullanır. Engine
socket’i pratikte Docker motoru üzerinde yönetici yetkisidir. API, web,
collector-worker ve network probe bu socket’i veya updater state volume’ünü
mount etmez. HTTP istekleri repository, komut, dosya yolu veya environment
belirleyemez; yalnız önceden GitHub’dan doğrulanmış `main` SHA’sını kuyruğa
alabilir.

Updater container’ı ayrıca salt-okunur root filesystem, `no-new-privileges` ve
tüm Linux capability’leri düşürülmüş biçimde çalışır. Engine socket yetkisi bu
önlemlerle daraltılamaz; updater imajı ve resmî repository yazma yetkileri yüksek
güven sınırıdır. `main` koduna güvenmek, bu repository’ye yazabilen kişilerin
sunucuda uygulama ve migration kodu çalıştırabilmesine güvenmek demektir. Public
repository olması tek başına güvenlik kanıtı değildir; branch protection,
inceleme ve CI politikasını ayrıca yönetin.

Yalnız yerel Unix-socket Docker context ve aynı Compose projesindeki tek
API/web/worker/PostgreSQL kurulumu kabul edilir. Uzak Docker motoru, Windows
container engine ve harici PostgreSQL otomatik yolun kapsamı dışındadır. Özel
kurulumlar `python -m app.updater --config ...` host işletimini kullanabilir,
ancak standart kullanıcı için bu adım gerekmez.

## Commit doğrulaması ve kurulum sırası

İlk yerel Compose build’inde Git SHA build argümanı bulunmayabilir. Updater bu
`unknown` üçlü imajı yalnız şu koşulların tamamında doğrulanmış checkout HEAD’i
ile bağlar: runtime container’ları aynı Compose projesindedir, API/web/worker
sağlıklıdır, checkout temizdir, origin resmîdir ve SHA `origin/main` geçmişinde
yer alır. Karışık veya kısmen etiketli runtime reddedilir. Updater’ın hazırladığı
sonraki aday imajların üçünde de tam SHA OCI etiketi zorunludur.

Kurulum evreleri:

`queued → building → draining → backing_up → migrating → deploying → verifying → succeeded`

- Hedef SHA geçici özel dizine sabitlenmiş public klonla alınır. Kurulu SHA →
  hedef SHA → `origin/main` ancestry zinciri doğrulanır; geri sürüm/force-push
  kabul edilmez.
- Compose/TLS/deploy veya updater’ın kendi güven sözleşmesi değişmişse otomatik
  imaj değiştirme yapılmaz ve `deployment_contract_changed` döner. Bu tür sürüm
  `git pull --ff-only` sonrası `docker compose up --build -d --wait` komutuyla
  operatör tarafından uygulanır.
- API ve web aday imajları kesin SHA etiketiyle hazırlanır. Derleme başarısızsa
  çalışan uygulama durdurulmaz.
- Bakım kipinde yeni kalıcı mutasyonlar, SSH açma ve toplama istekleri durur.
  Açık oturumlar ve çalışan işler zorla kesilmez; en fazla 15 dakika beklenir.
- Özel release dizinine PostgreSQL custom dump, keyring, deployment girdileri ve
  önceki immutable image ID’leri alınır. Dump kataloğu ve keyring biçimi
  doğrulanır; bu tam restore provası değildir. DB yedeği ile keyring birlikte
  hassastır ve API’den sunulmaz.
- Yalnız migration adayı ile `api`, `web`, `collector-worker` değiştirilir.
  PostgreSQL, gateway, secrets-init, volume kimlikleri ve kullanıcı verileri
  korunur. Son imaj SHA’ları ve sağlık tekrar doğrulanır. Başarılı adaylar temel
  Compose imaj etiketlerine de bağlanır; sonraki düz `docker compose up` eski
  ilk-build imajına dönmez. Başarısız geri dönüşte eski alias’lar da geri alınır.

Migration başlamadan önceki hata bakım kipini kaldırır. Migration’ın tamamlanıp
tamamlanmadığı belirsizse veya schema değiştiyse otomatik downgrade/restore
yapılmaz; durum `recovery_required` olur ve yazmalar kapalı kalır.

## Sorun giderme

```bash
docker compose ps -a
docker compose logs --tail=200 updater
docker compose logs --tail=200 api
```

Yaygın updater hata kodları:

| Kod | Anlamı |
| --- | --- |
| `update_setup_clean_checkout_required` | Checkout’ta commitlenmemiş veya untracked kaynak var. |
| `update_setup_official_remote_required` | `origin`, resmî repository değil. |
| `update_setup_public_source_required` | `.git` içermeyen kaynak hiçbir resmî `main` commit’iyle birebir eşleşmedi. |
| `revision_not_forward` | HEAD/hedef güncel `origin/main` ileri geçmişinde değil. |
| `local_docker_context_required` | Seçili motor yerel Unix socket değil. |
| `project_identity_mismatch` | Updater başka/eksik Compose projesi etiketleri gördü. |
| `database_project_mismatch` | PostgreSQL ve uygulama aynı proje/DB kimliğine bağlı değil. |
| `bootstrap_binding_invalid` | İlk imaj/commit bağı bozuk; state volume’ünü silmeden log ve dosya izinlerini inceleyin. |
| `deployment_contract_changed` | Compose/deploy/updater değişikliği için elle ileri alma gerekiyor. |

Updater geçici GitHub veya Engine hatasında container’ı yeniden kurdurmadan 30
saniye arayla tekrar dener. Checkout’u düzeltmek için mevcut veritabanını,
volume’leri, kullanıcıları veya anahtarları silmeyin.

## Kesinti ve elle kurtarma

Updater bakım/migration sırasında kesilirse bakım kilidi süre dolunca kendiliğinden
açılmaz. `<project>-update-<run-id>` migration container’ını, updater state
volume’ündeki release/yedekleri, schema’yı ve çalışan immutable imajları bağımsız
inceleyin. Canlı DB üzerine otomatik restore komutu yoktur; restore provasını ayrı
boş veritabanında yapın. Veri/schema kabulü tamamlanmadan `recovery_required`
durumunu kaldırmayın.

## API ve kaynaklar

`GET /api/v1/system/updates`; superadmin+CSRF ile `POST .../check`,
`PUT .../policy`, `POST .../install`. Bildirimler `GET /api/v1/notifications`,
`GET .../stream`, `POST .../read`. `system.update` yalnız superadmin’e aittir.
`0007_settings_updates` migration’ı mevcut cihaz, sır, anahtar veya kullanıcıları
silmeden güncelleme/bildirim tablolarını ekler.

Kaynaklar: `backend/app/update_runtime.py` (Compose bootstrap),
`backend/app/updater.py` (kurulum/yedek/kurtarma), `backend/app/updates.py`
(metadata/policy), `backend/app/settings_api.py` (RBAC/CSRF),
`backend/app/notifications.py` ve `frontend/components/UpdatesPage.tsx`.

Yerel unit/E2E testleri gerçek bir hedef bilgisayarda güç kesintisi, disk dolması,
restore tatbikatı veya production kabulünün yerine geçmez.
