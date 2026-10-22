# Ayarlar, canlı bildirimler ve güncelleme işletimi

> NetStudio adlandırmasına geçen kurulumlarda önce [ad geçişi rehberini](name-transition.md) izleyin. Compose sözleşmesi değiştiğinden bu sürüme geçiş otomatik host güncellemesine bırakılmaz; mevcut volume/DB/anahtar bağları korunarak operatör tarafından yapılır.

## Kullanıcı akışı

Yan menüde **Ayarlar** bulunur:

- **Hesabım:** mevcut profil, avatar ve parola işlemleri. Eski `/account` bağlantıları çalışmaya devam eder.
- **Kullanıcılar:** yalnız superadmin için hesap oluşturma, rol/site atama, düzenleme ve silme. Mevcut son-superadmin koruması ve oturum iptali korunur.
- **Güncellemeler:** kurulu/main commit, GitHub bağlantılı son 30 commit ve açıklamaları, kontrol zamanları, sunucu güncelleyicisinin durumu ve son 20 kurulum.

Üst barın sol bağlam alanındaki güncelleme işareti `/settings/updates` adresini açar. Kurulu SHA bilinmiyorsa sistem kendisini güncel saymaz; güncelleme karşılaştırması ve kurulum engellenir. Bildirim düğmesi 180 ms aşağı açılan bir paneldir; Escape, dış alana tıklama ve sayfa değişimi kapatır. Azaltılmış hareket tercihinde animasyon yoktur.

Commitlerin görünüp **Güncellemeyi kur** düğmesinin ilerlememesi çoğunlukla iki bağımsız önkoşuldan kaynaklanır: standart geliştirme build'inin `NETSTUDIO_BUILD_REVISION=unknown` olması veya host güncelleyicisinin bağlı olmaması. Güncelleme ekranı artık eksik olan koşulu ayrı gösterir ve resmi checkout için tek seferlik hazırlık komutunu verir.

Bildirimler sunucu audit olaylarının izinli bir izdüşümüdür: yetkili sitelerdeki cihaz olayları, kişinin kendi hesap/SSH olayları ve global güncelleme olayları. Superadmin hesap yönetimi olaylarını da görür. Ham audit ayrıntıları, terminal verisi ve sırlar aktarılmaz. Son 7 gün/30 olay gösterilir; okunmamış sayaç 100 ile sınırlıdır (`99+`). Okunma işareti kullanıcı başına sunucuda kalıcıdır. SSE her 3 saniyede değişiklikleri gönderir; bağlantı 60 saniyede yenilenir ve her çevrimde oturum/yetki yeniden doğrulanır. Sınır API süreci başına kullanıcıda 3, toplamda 100 açık akıştır. Bu bir sınırsız olay arşivi değildir; tam denetim geçmişi ayrı audit ekranındadır.

## Güven sınırı ve varsayılanlar

**Otomatik kurulum varsayılan kapalıdır.** `NETSTUDIO_UPDATES_CHECK_ENABLED=1` yalnız public commit metadata kontrolünü açar; kurulum yapmaz. Kapalıysa zamanlanmış kontrol yapılmaz, superadmin manuel kontrol yapabilir. Kontrol tüm API süreçleri için DB lease ile birleştirilir, 10 dakikadan sık yapılmaz. ETag/304 kullanılır; GitHub hız sınırında bekleme artırılır. Hata halinde son başarılı liste korunur. Sabit hedef `https://api.github.com/repos/KES-KING/NetStudio/commits?sha=main&per_page=30`; yönlendirmeler izlenmez, repository taşınırsa kod/operatör müdahalesi gerekir. [GitHub commits API](https://docs.github.com/en/rest/commits/commits#list-commits), [GitHub REST iyi uygulamalar](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

**main koduna otomatik güvenmek, o repository'ye yazabilen kişilere sunucuda uygulama/migration çalıştırma yetkisi vermektir.** Branch protection, inceleme ve CI politikasını ayrıca yönetin. Bu sürüm imza veya CI check sonucu doğrulamaz; main bir stabil sürüm kanalı olarak kabul edilmez. Arayüz bunun için açık risk onayı ister. Public repository olması kodun güvenli olduğunu kanıtlamaz.

API içinde `git pull`, Docker komutu veya shell çalışmaz; Docker socket API/web/worker'a bağlanmaz. Kurulum ayrı Linux host sürecidir (`python -m app.updater`). Operatörün özel dosyası açık Docker context, proje, Compose/TLS dosyaları, `.env` ve mevcut loopback PostgreSQL bağlantısını belirler. HTTP isteği repository, komut, path veya environment alamaz. Host agent Docker yetkisiyle çalışır; bu hesabı yüksek ayrıcalıklı kabul edin. Agent'ın kendisi bu mekanizma tarafından değiştirilmez; güncel host sürümü ayrıca işletilir.

## Bir defalık host hazırlığı

Bu adımlar operatör içindir; geliştirme testi bunları mevcut kullanıcı kurulumunda otomatik çalıştırmaz. Önce mevcut Docker context/proje, volume'ler, portlar, gerçek veri tabanı ve anahtar deposunu doğrulayın. Üretimde `docker-compose.tls.yml` dahil kullanılan **bütün** override dosyalarını koruyun. Otomatik sistem yalnız mevcut tek API/web/worker/PostgreSQL kurulumunu kabul eder; uzaktaki Docker motoru ve harici PostgreSQL bu sürümde desteklenmez.

### Resmi public checkout için önerilen yol

Resmi repository'nin temiz bir checkout'unda aşağıdaki komut hazırlığın tamamını yapar:

```bash
./netstudio-update setup
```

Komut şu kontrolleri ve işlemleri sıralı yapar:

1. `origin` adresinin resmi public repository olduğunu, çalışma ağacının temiz olduğunu ve mevcut commit'in güncel `origin/main` geçmişinde bulunduğunu doğrular. Fork veya yerel/kirli kaynak resmi sürüm etiketi alamaz.
2. Seçili yerel Docker context'i ve çalışan API container etiketinden gerçek Compose/TLS dosyalarını bulur. Başka proje, uzak Docker endpoint'i veya repository dışı Compose yolu kabul edilmez.
3. Mevcut `.env` değerlerini koruyup yalnız `NETSTUDIO_BUILD_REVISION` değerini doğrulanmış tam SHA'ya getirir; dosyayı `0600` yapar. Aynı proje ve volume kimlikleriyle `docker compose up --build -d --wait` çalıştırır ve API/web/worker imaj etiketlerinin aynı SHA olduğunu yeniden denetler.
4. Ayrı `.updater-venv` ortamına yalnız backend paketini kurar. PostgreSQL'in mevcut açık loopback portunu Compose çıktısından doğrular; özel yapılandırmayı `~/.local/state/netstudio-updater/<proje>/config.json` altında `0600`, state/yedek dizinini `0700` oluşturur.
5. Kullanıcı systemd yöneticisi varsa `netstudio-updater-<proje>.service` birimini etkinleştirir. Kullanıcı systemd'si yoksa ajanı private log/PID ile ayrık süreç olarak başlatır; bu fallback yeniden başlatma sonrası kalıcı değildir ve komutun tekrar çalıştırılması gerekir. Son olarak DB heartbeat üzerinden ajanın gerçekten bağlandığını doğrular.

Bu komut otomatik kurulum politikasını açmaz ve bir güncelleme kuyruğa almaz. Son karar yine superadmin'in risk onayıyla verilir. API, web ve worker'a Docker socket verilmez; Docker yetkisi yalnız açıkça başlatılan host ajanındadır.

İlk kez bu düzeltmeden daha eski bir kurulumdan geliyorsanız repository'yi normal, veri koruyan prosedürünüzle temiz bir resmi commit'e ileri alın ve komutu bir kez çalıştırın. Eski istemci kendi eksik host ajanını tarayıcıdan başlatamaz; bu tek seferlik bootstrap güven sınırıdır.

### Elle/özel kurulum

1. Bu özelliği içeren, gözden geçirilmiş **temiz ve yayınlanmış** commit'i normal bakım prosedürünüzle kurun. Önce mevcut DB ve keyring yedeğini alın; additive `0007_settings_updates` migration'ını çalıştırın. API, collector-worker ve web aynı SHA'dan build edilmelidir. `.env` içinde `NETSTUDIO_BUILD_REVISION=<tam 40 karakter SHA>` kullanın. Bu değişken bir doğrulama imzası değildir: kirli çalışma ağacına HEAD etiketi vermeyin. `unknown` etiketli eski imajlar otomatik kuruluma kabul edilmez. Mevcut cihazları, kullanıcıları veya sırları yeniden oluşturmayın.
2. Host üzerinde Python 3.11+, Git, Docker CLI/Compose ve bu release'in `backend` paketini ayrı bir virtualenv'e kurun. Agent container içinde değil host üzerinde çalışır. Örneğin operator-owned release dizininde `python3 -m venv .updater-venv`, ardından `.updater-venv/bin/pip install ./backend`. Mevcut uygulama virtualenv'ini veya çalışan container'ları değiştirmez.
3. Operatöre ait, modu `0600` olan bir JSON yapılandırması oluşturun. Aşağıdaki yollar/değerler **örnektir**; mevcut kurulumu keşfetmeden kopyalayıp çalıştırmayın. DB parolasını kaynak depoya koymayın. State dizini `0700`, aynı kullanıcıya ait olmalı; yedekler için yeterli disk alanı ayırın.

```json
{
  "project": "netstudio-installation",
  "docker_context": "default",
  "installation_dir": "/srv/netstudio",
  "compose_files": ["/srv/netstudio/docker-compose.yml", "/srv/netstudio/docker-compose.tls.yml"],
  "env_file": "/srv/netstudio/.env",
  "state_dir": "/var/lib/netstudio-updater",
  "database_url": "postgresql+psycopg://netstudio:REPLACE_LOCALLY@127.0.0.1:5432/netstudio",
  "drain_timeout": 900
}
```

PostgreSQL URL, mevcut Compose PostgreSQL servisinin loopback yayın portu, DB adı ve uygulama kullanıcı adı ile eşleşmelidir. Docker context yerel `unix://` endpoint olmalı. Kurulum dizini ve özel yedek dizini ayrıdır. İlgisiz kabuk değişkenleri Compose yapılandırmasını değiştirmesin diye agent yalnız sınırlı bir environment listesi aktarır; **kurulumun bütün Compose parametreleri `env_file` içinde olmalıdır**. Shell'de verilen mevcut parametreleri dosyaya taşırken sırları terminale dökmeyin.

4. Dosya izinlerini doğruladıktan sonra host sürecini başlatın:

```bash
/srv/netstudio/.updater-venv/bin/python -m app.updater --config /etc/netstudio/updater.json
```

Bu açık komut hazırsa kuyruktaki kurulumu işleyebilir. `--once` de gerçek kuyruk işi işler; dry-run değildir. Kalıcılık için aynı komutu operatörün servis yöneticisinde çalıştırın. Örnek systemd unit (kullanıcı/yolları kendi kurulumunuzla değiştirin; Docker context o kullanıcıya ait olmalı):

```ini
[Unit]
Description=NetStudio host updater
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=netstudio-updater
WorkingDirectory=/srv/netstudio
ExecStart=/srv/netstudio/.updater-venv/bin/python -m app.updater --config /etc/netstudio/updater.json
Restart=on-failure
RestartSec=15
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

Servis kullanıcısına mevcut **doğru** Docker motoruna erişim ve özel dosyalara okuma/yazma yetkisi operatör tarafından sağlanır; bu doküman otomatik hesap/yetki oluşturmuyor.

5. Ayarlar → Güncellemeler'de **Sunucu güncelleyicisi: Bağlı**, doğrulanmış kurulu SHA ve kontrol sonucunu görün. Risk kutusunu okuyup **Otomatik kurulumu aç** seçin. Bundan sonra tarayıcı kapalı olsa da yeni main commit'leri kalıcı kuyruğa alınır. Açma anında hazır güncelleme varsa o da sıraya girer. Yalnız superadmin bu politikayı/manuel kurulumu değiştirebilir; yetkisi kaldırılan hesabın bekleyen otomatik işleri çalıştırılmaz.

## Kurulum sırası ve koruma

`queued → building → draining → backing_up → migrating → deploying → verifying → succeeded`

- Agent tekil dosya kilidi ve DB sahipliği/heartbeat kullanır. Aynı kurulum isteği birleştirilir. Ağ/derleme sırasında DB transaction/kilidi açık tutulmaz.
- Otomatik politikayı kapatmak yeni/bekleyen ve henüz bakım aşamasına girmemiş işleri durdurur; bakım aşamasına girmiş migration'ı yarıda kesmez. Yetkilendiren hesabın devre dışı kalması veya superadmin yetkisinin kaldırılması ise her aşamada kontrol edilir.
- Yeni özel staging dizinine sabit public repository klonlanır. SHA tam olarak pinlenir; mevcut SHA → seçili SHA → origin/main ancestry doğrulanır. Force-push/geri sürüm engellenir. Root Compose/TLS veya `deploy/` değişmişse **elle geçiş** gerekir; imaj değiştirerek yeni dağıtım sözleşmesi tahmin edilmez.
- API ve web imajları yeni SHA etiketleriyle hazırlanır. Eski çalışan imajlar üzerine build edilmez; başarısız build uygulamayı durdurmaz.
- Bakım kipinde yeni kalıcı değişiklikler/SSH açma/toplama istekleri durur; okuma, login/logout, okundu işaretleme, otomatik politikayı kapatma ve SSH kapatma kullanılabilir. Worker yeni iş almaz. API varlığı, aktif değişiklikler, açık/bekleyen SSH ve çalışan toplama işleri sessizleşmeden ilerlenmez. Varsayılan bekleme en çok 15 dakikadır; oturumlar zorla kesilmez.
- Özel staging dizininde `database.dump` (PostgreSQL custom format) ve `keyring.json` alınır. Dump katalog yapısı `pg_restore --list` ile; keyring biçimi/anahtar uzunluğu doğrulanır. Bu, tam restore provası değildir. Deployment girdi dosyaları ve önceki image ID'leri de özel dizinde saklanır. Yedekler API'den sunulmaz. **DB yedeği ve keyring birlikte hassastır.** Bu sürüm yedek/release dizinlerini otomatik silmez; saklama/disk kapasitesi operatör sorumluluğudur.
- Doğrulanmış Compose yapılandırmasıyla yalnız aday migration container'ı, sonra `api`, `web`, `collector-worker` servisleri değiştirilir. `--no-deps --no-build --wait` kullanılır; PostgreSQL, gateway ve secrets-init yeniden oluşturulmaz. İmaj SHA, sağlık ve named-volume kimlikleri tekrar kontrol edilir. [Compose up](https://docs.docker.com/reference/cli/docker/compose/up/).
- Başarılı kurulumun tam imaj seçimi özel release dizinindeki `candidate-compose.json` dosyasında saklanır. Docker restart politikası mevcut container imajlarını korur. Sonradan elle `compose up` çalıştırırken bu override'ı aynı temel Compose/TLS dosyalarına son `-f` olarak ekleyin; eski `.env` içindeki `IMAGE_TAG` ile çıplak `up`, eski imaja döndürebilir. Agent operatörün `.env` dosyasını değiştirmez.
- Başarısız aynı SHA otomatik döngüye girmez. Operatör nedeni düzeltip açıkça tekrar isteyebilir; yeni SHA ayrı değerlendirilebilir. Migration öncesi hata bakım kipini kaldırır. Migration belirsiz/yarım kaldıysa ya da schema değiştiyse otomatik DB downgrade/restore **yapılmaz**: `recovery_required` olur ve bakım sürer. Schema değişmeden runtime geçişi başarısızsa önceki immutable imajlar geri başlatılıp sağlık kontrolü yapılır.

## Kesinti ve elle kurtarma

Agent çökerse bakımın süresi dolup kendiliğinden açılmaz. Agent yeniden başladığında yarım aktif iş kurtarma gerektirir. Migration CLI timeout'u container'ın durduğunu kanıtlamaz; `<project>-update-<run-id>` adlı migration container'ını ayrıca inceleyin. Agent'ı durdurun; yalnız doğrulanmış bu kuruluma ait container/job üzerinde operatör müdahalesi yapın. Eski sürüm migration sonrası DB ile uyumlu varsayılmaz.

Gerekirse özel staging yedeğinden **ayrı, boş kurtarma DB'sinde** restore provası yapın; canlı DB üzerine otomatik silme/restore komutu yoktur. Önceki imajlar, Compose/env ve keyring korunmuştur. Veri/schema uyumluluğunu ve mevcut runtime sağlığını bağımsız doğruladıktan sonra bakım kilidini açık operatör onayıyla kaldırabilirsiniz:

```bash
/srv/netstudio/.updater-venv/bin/python -m app.updater \
  --config /etc/netstudio/updater.json \
  --acknowledge-recovery VERIFIED_40_CHARACTER_INSTALLED_SHA
```

Komut sağlıklı mevcut proje, eşleşen imaj SHA'ları, canlı başka agent olmaması ve çalışan migration container'ı bulunmamasını kontrol eder; **schema/iş verisi kabulünün yerine geçmez**. Otomatik kurulum kapalı kalır. Agent'ı yeniden başlatıp arayüzden durumu doğrulayın. Sadece agent'ı kapatmak otomatik kurulumları durdurur, fakat zaten başlayan migration'ı güvenle geri almış sayılmaz.

## API, şema ve doğrulama sınırları

`GET /api/v1/system/updates`; superadmin+CSRF ile `POST .../check`, `PUT .../policy`, `POST .../install`. Bildirimler `GET /api/v1/notifications`, `GET .../stream`, `POST .../read`. Yeni izin `system.update` yalnız superadmin'e aittir. Migration `0007_settings_updates`, yalnız dört yeni tabloyu ekler; mevcut cihaz, sır, anahtar, kullanıcı kimliği ve gözlemleri taşımaz/silmez.

Kaynaklar: `backend/app/updates.py` (metadata/policy), `settings_api.py` (RBAC/CSRF/SSE), `notifications.py` (scope/read cursor), `updater.py` (host işletimi), `system_schema_v1.py` (frozen şema); UI `SettingsLayout`, `UpdatesPage`, `LiveNotifications`.

Host kurulum adımları kontrollü executor testlerinde sınanır; yerel testler gerçek bir main commit'ini canlı kuruluma indirip yükseltme kabulü değildir. Gerçek otomatik yükseltme, geri dönüş/restore tatbikatı, disk dolması, güç kesintisi ve hedef operatör sistemd/Docker ortamı ayrıca izole pilotta doğrulanmalıdır. Bu özellik AGPL, mevcut RBAC/CSRF, SSH host-key ve sır deposu sınırlarını değiştirmez.
