<p align="center">
  <img src="frontend/public/branding/netstudio-logo.png" alt="Stocc NetStudio ana logosu" width="300" /><br />
  <img src="docs/Stocc/StoccLogo.png" alt="Stocc ana marka logosu" width="120" />
</p>

# Stocc NetStudio

[![CI](https://github.com/KES-KING/stocc-netstudio/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/KES-KING/stocc-netstudio/actions/workflows/ci.yml)
[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-365A73)](LICENSE)

[Ekran görüntüleri](#ekran-görüntüleri) · [Kurulum](#docker-ile-kurulum) · [Cihaz bağlantısı](#gerçek-cihazı-bağlama) · [Kullanıcı ve audit](#kullanıcı-yönetimi-ve-audit) · [Geliştirme](#geliştirme-ve-doğrulama) · [Proje kuralları](rule.md) · [Katkı rehberi](CONTRIBUTING.md) · [Tartışmalar](https://github.com/KES-KING/stocc-netstudio/discussions) · [Lisans](#lisans)

Ağ cihazlarının envanterini, erişilebilirliğini, fiziksel portlarını, trafik gözlemlerini ve IP ilişkilerini aynı konsolda yönetin. Cihaz detayında açılan SSH terminali, backend üzerinden doğrulanmış cihaz kaydına bağlanır.

Arayüz: Next.js 16 / React 19 / TypeScript, Apache ECharts, xterm.js ve SWR. Backend: FastAPI, SQLAlchemy, PostgreSQL, AsyncSSH, Argon2id ve AES-256-GCM. Varsayılan kurulumda cihaz, kullanıcı veya örnek telemetri **oluşturulmaz**.

## Neler sunar?

- Cihaz adı/IP, tür ve erişilebilirlik kapsamıyla filtrelenen envanter ve operasyon özeti.
- Gerçek envantere bağlı, marka bağımsız fiziksel port panelleri ve IP topolojisi.
- Taralı Topoloji çalışma alanı: kişisel zone’lar, taşınabilir cihazlar, port bağlantısı çizimi ve kaynak/zaman bilgili MAC/IP uç düğümleri.
- Apache ECharts ile RX/TX, port durumu ve kapasite gösterimleri; bilinmeyen/eski verinin açık ayrımı.
- Cihaz detayına entegre SSH terminali; backend tarafında site/rol denetimi ve kayıtlı host key doğrulaması.
- Harici envanter/telemetri aktarımı; Linux, Huawei VRP ve Cisco Catalyst 2960-X IOS için kullanıcı tarafından başlatılan salt okunur SSH toplama işleri.
- Kişisel profil/avatar/parola yönetimi; `viewer`, `engineer`, `superadmin` rolleri ve yalnız superadmin'e açık kullanıcı yönetimi/ayrıntılı audit.
- Docker Compose ile PostgreSQL, migration, sır deposu, API, frontend ve gateway kurulumu.

Bu proje geliştirme aşamasındadır. Fiziksel cihaz/üretim kabulü, çok worker desteği ve üreticiye özgü konfigürasyon uygulama/yedekleme yetenekleri varmış gibi sunulmaz. CI rozeti GitHub'daki gerçek durumu gösterir; aşağıdaki tarihli yerel doğrulama sonuçları onun yerine geçmez.

Marka varlıkları `frontend/public/branding/` içindedir: `netstudio-logo.png` README, giriş ekranı ve masaüstü üst barda, `netstudio-emblem.png` mobil üst bar ve sekme simgesinde kullanılır. Orijinal PNG içerikleri ve şeffaflık korunur; ortak `Brand` bileşeni uygulama içinde yalnız şeffaf kenar boşluklarını görünümde çerçeveler. Logoların arkasında ayrı bir zemin yoktur; üst barın tamamı okunabilirlik için `nav-header` tokenıyla açık gri tutulur. Sekme simgesi `app/icon.tsx` ile amblemden şeffaf zemin üzerinde üretilir. Docker web imajı `public/` dizinini de içerir.

## Ekran görüntüleri

Aşağıdaki üç görüntü çalışan uygulamanın izole QA ortamından alınmıştır. Cihazlar, adresler ve telemetri test verisidir; SSH görüntüsü izole test cihazıyla kurulan gerçek oturumu gösterir. Üretim cihazı bilgisi veya bağlantı sırrı içermez. Varsayılan kurulum bu örnek verileri oluşturmaz.

**Güncellik kuralı:** Her görsel arayüz güncellemesinde aşağıdaki üç görüntünün tamamı güncel koddan yeniden alınır ve aynı değişiklik/PR içinde teslim edilir. İnsanlar ve yapay zekâ için ayrıntılar [rule.md](rule.md#5-her-görsel-güncellemede-readme-görüntülerini-yenile), ajanların uygulama adımları [agent.md](agent.md) içindedir.

Son set: **20 Ekim 2026**, `stocc-cisco-qa-20261020` izole Docker ortamı, sistem Chrome, 1536 × 1024 viewport ve tam sayfa yakalama. Test edilen çalışma ağacı `ea974a7` üzerine Catalyst 2960-X collector ve bağlantı formu değişikliklerini içerir; mevcut `stocc-netstudio-fresh` kurulumu değiştirilmemiştir.

### Ana sayfa

Cihaz filtresi ve zaman aralığıyla aynı kapsamı paylaşan Apache ECharts grafikleri, port kullanımı ve dikey cihaz envanteri.

![NetStudio ana sayfası: QA-Core-01 filtresiyle erişilebilirlik, port, trafik ve kapasite grafikleri ile cihaz envanteri](docs/screenshots/dashboard.png)

### Cihaz detayı — SSH kapalı

Tam genişlikte etkileşimli cihaz ön paneli; kasa üzerinde envanterdeki cihaz adı/modeli, iki yanda şematik rack montaj delikleri, solda RJ45 ve sağda tek sıra SFP/QSFP grupları. İki sıralı RJ45 görünümünde her altı sütundan sonra ölçülü bir banka ayrımı bulunur. Mat grafit/metal yüzeyler marka bağımsızdır; montaj geometrisi ve port yerleşimi üretici kasasının birebir ölçülü çizimi değildir. Altındaki IP topolojisi sabit boyutlu düğümler, kontrollü yakınlaştırma ve kaydırma kullanır; geniş panelde üç, dar panelde iki kolonlu yerleşime geçerek taşmadan çalışır. İlişki türleri lejantta korunur. Sağda teknik bilgiler ve sağlık değerlendirmesi bulunur.

Port yuvalarının yanındaki göstergeler aynı telemetri durumunu kullanır: **UP** yeşil, **DOWN** sönük gri, **ADM** idari kapalı, **?** bilinmiyor. İdari kapalı port arızalı sayılmaz; güncelliğini kaybeden veri aktif LED olarak gösterilmez. Port seçimi dış çerçeveyle ayrıca belirtilir. Dar alanda panel yatay kayar; portlar okunamayacak kadar küçültülmez.

![NetStudio cihaz detayı: isim ve model etiketli rack paneli, yatay SFP portları, UP/DOWN göstergeleri ve taşmayan sabit boyutlu IP topolojisi](docs/screenshots/device-detail.png)

### Cihaz detayı — SSH açık

Aynı cihazın ön paneli ve bağlı SSH terminali yan yana; topoloji ve teknik bilgi alanları alt bölümde korunur.

![NetStudio cihaz detayı: cihaz ön panelinin yanında bağlı SSH terminali ve alt bölümde IP topolojisi ile teknik bilgiler](docs/screenshots/device-detail-ssh.png)

## Katkı ve iletişim

Türkçe veya İngilizce katkı kabul edilir. Başlangıç için [katkı rehberini](CONTRIBUTING.md) okuyun; hata ve özellik talepleri için [issue şablonlarını](https://github.com/KES-KING/stocc-netstudio/issues/new/choose), kullanım soruları için [Discussions](https://github.com/KES-KING/stocc-netstudio/discussions) alanını kullanın. Güvenlik açıklarını public issue yerine [özel güvenlik bildirimi](https://github.com/KES-KING/stocc-netstudio/security/advisories/new) üzerinden iletin; kapsam ve ilkeler [güvenlik politikasında](SECURITY.md) açıklanır.

Tüm katkılarda [ortak proje kuralları](rule.md) geçerlidir. Yapay zekâ ajanları ayrıca [ajan yönergesini](agent.md) izler; [AGENTS.md](AGENTS.md) bu yönergelere giriş noktasıdır.

## Lisans

Copyright (C) 2026 KES-KING ve Stocc NetStudio katkıda bulunanları.

Projenin lisansı **GNU Affero General Public License v3.0 only** (`AGPL-3.0-only`); bağlayıcı tam metin [LICENSE](LICENSE) dosyasındadır. Ticari kullanıma izin verir; değiştirilmiş sürümü ağ üzerinden kullananlara ilgili sürümün kaynak koduna erişim sunma yükümlülüğü dahil lisans koşulları geçerlidir. [AGPLv3 özeti](https://choosealicense.com/licenses/agpl-3.0/).

Dağıtımlarda lisans ve telif bildirimlerini koruyun; bağımlılıklar kendi lisanslarına tabidir. Yazılım garanti verilmeden sunulur. Frontend'deki `private: true` yalnız yanlışlıkla npm yayını yapılmasını engeller; GitHub görünürlüğünü veya kaynak kodun lisansını değiştirmez.

## Docker ile kurulum

Docker Engine veya Docker Desktop ve Compose 2.24.4 veya üzeri gerekir (TLS override dosyasındaki `!override` için). Makinede Make, Python veya Node kurulu olması gerekmez. Aşağıdaki komutları repository kökünde çalıştırın; tüm servisler doğrudan `docker compose` ile yönetilir.

### Docker motorunu seçme

Linux üzerinde Docker Desktop kullanıyorsanız önce uygulamayı açın ve motorun hazır olmasını bekleyin:

```bash
docker context ls
docker context use desktop-linux
docker info
```

Linux sistem Docker Engine'ini kullanmak istiyorsanız bunun yerine `docker context use default` çalıştırın. Sonraki `docker compose` komutları seçili context üzerinde çalışır; repository herhangi bir context'i zorlamaz. Global seçimi değiştirmeden belirli bir komutu Desktop üzerinde çalıştırmak için `docker --context desktop-linux compose ...` kullanılabilir.

**Docker Desktop'ta görünürlük:** Linux'ta `default` ve `desktop-linux` ayrı motorlardır. `default` üzerinde oluşturulan container'lar Docker Desktop'ın container listesinde görünmez; container, imaj ve volume'ler context değiştirince taşınmaz. Desktop üzerinde ilk çalıştırma ayrı bir veritabanı ve anahtar deposu oluşturur. Önceki kayıtlar gerekiyorsa eski motoru ve volume'lerini koruyun; veritabanı ile şifreleme anahtarını birlikte planlanmış bir taşıma kapsamında aktarın. Ayrıntılar: [Docker Desktop Linux belgeleri](https://docs.docker.com/desktop/setup/install/linux/).

Kabukta tanımlı `DOCKER_HOST` veya `DOCKER_CONTEXT` değerleri motor seçimini etkileyebilir. Beklenmedik motora bağlanıyorsanız bunları kontrol edin; yalnız o kabuk için temizlemek üzere `unset DOCKER_HOST DOCKER_CONTEXT` kullanabilirsiniz. Projenin `.env` dosyası Docker CLI context seçimi için kullanılmaz. Motor hatasında başka context'e sessiz geçiş yapılmaz.

### Başlatma

```bash
# .env zaten varsa üzerine yazmayın.
test -f .env || cp .env.example .env
docker compose config --quiet
docker compose up --build -d --wait
docker compose exec api python -m app.admin create-user --username admin --role superadmin --site '*'
```

Son komut ilk yönetici hesabını oluşturur ve parolayı etkileşimli olarak iki kez ister; en az 12 karakter gerekir. Sonraki başlatmalarda hesabı tekrar oluşturmayın. Varsayılan yönetici parolası yoktur. Web: <http://127.0.0.1:3000>. Desktop motoru seçiliyken servisler Docker Desktop'ın Containers ekranında `stocc-netstudio` grubu altında görünür (`COMPOSE_PROJECT_NAME` değiştirilmişse o ad kullanılır).

### İlk yönetici hesabı ve giriş bilgileri

**Hazır bir varsayılan admin hesabı veya ortak parola yoktur.** Boş veritabanında ilk yönetici, yukarıdaki `create-user` komutuyla sizin tarafınızdan oluşturulur. Bu komutun oluşturacağı hesabın bilgileri:

| Alan | Değer |
| --- | --- |
| Giriş adresi | Varsayılan yerel kurulumda <http://127.0.0.1:3000> |
| Kullanıcı adı | `admin` (`--username admin` ile oluşturduğunuzda) |
| Rol | `superadmin` |
| Site kapsamı | `*` — tüm lokasyonlar |
| Parola | Komutun gizli giriş isteminde sizin belirlediğiniz, en az 12 karakterlik parola; hazır bir değer yoktur |

`Kullanıcı oluşturuldu.` mesajından sonra arayüze `admin` ve belirlediğiniz parolayla giriş yapın. Parolayı README'ye, `.env` dosyasına veya komut satırı argümanına yazmayın. Veritabanı bağlantı parolası (`POSTGRES_PASSWORD`) uygulama giriş parolası değildir; QA test kullanıcıları da normal kurulumda oluşturulmaz.

Aynı kullanıcı mevcutsa komut `Kullanıcı zaten var; üzerine yazılmadı.` diyerek durur; parola sıfırlamaz. Mevcut volume ile yeniden başlatmada önceki kullanıcı ve parolalar geçerlidir. Yeni Docker context/projesi ise ayrı veritabanı kullanabilir; hesabın doğru kurulumda oluşturulduğunu kontrol edin.

`POSTGRES_PASSWORD` ve `DATABASE_URL` birbiriyle tutarlı olmalıdır. `.env.example` yalnızca loopback geliştirme varsayılanları içerir. Var olan PostgreSQL volume'ünde ortam değişkenini değiştirmek mevcut veritabanı parolasını değiştirmez.

```text
Tarayıcı
   │ HTTP/WS (yalnız yerel geliştirme) veya HTTPS/WSS
   ▼
Nginx gateway ── / ─────────► Next.js web
   │
   └── /api/* + WebSocket ─► FastAPI api ──► Kayıtlı cihazın SSH portu
                                │
                                ├── PostgreSQL: envanter, kullanıcı, oturum,
                                │   şifreli sır, gözlem, iş ve denetim kaydı
                                └── Ayrı, salt okunur şifreleme anahtarı volume'ü

Başlatma: PostgreSQL healthy → Alembic migrate → API ready → web → gateway
          secrets-init ──────────────────────────┘
```

Gateway WebSocket upgrade ve uzun süreli SSH akışını destekler. API tek Uvicorn süreciyle çalışır; terminal limiti ve oturum köprüsü bu sürece aittir. Birden fazla API worker/replica, ortak broker ve oturum yönlendirmesi eklenmeden kullanılmamalıdır. PostgreSQL ve anahtarlar iki ayrı kalıcı volume'dedir. Anahtar dosyası API kullanıcısına ait, `0600` izinlidir; frontend imajına veya ortam değişkenine girmez.

### Günlük yönetim

```bash
docker compose ps -a                    # Başlatma işleri dahil tüm servisler.
docker compose logs -f --tail=200        # Tüm servislerin logları; Ctrl+C yalnız izlemeyi bitirir.
docker compose logs -f --tail=200 api    # Yalnız API logları.
docker compose stop                     # Container'lar ve volume'ler korunur; Desktop'ta kalır.
docker compose up -d --wait              # Durdurulmuş sistemi tekrar başlatır.
docker compose up --build -d --wait      # Kod/imaj değişikliklerini uygular, migration ve sağlık kontrollerini çalıştırır.
```

İsteğe bağlı, ayrı ayrı çalıştırılabilecek komutlar:

```bash
docker compose build                    # Yalnız imajları oluşturur.
docker compose up --build               # Ön planda çalışır; Ctrl+C servisleri durdurur.
docker compose up -d --build --no-deps web # Yalnız frontend'i günceller; bağımlılıklar zaten hazır olmalıdır.
docker compose run --rm migrate         # PostgreSQL hazır olduğunda migration'ı ayrıca çalıştırır.
docker compose down                     # Container/ağları kaldırır; kalıcı volume'leri silmez.
```

`secrets-init` ve `migrate` tek seferlik başlatma işleridir; başarılı çalışmadan sonra `Exited (0)` görünmeleri normaldir. `down` sonrasında grubun Desktop'ın container listesinden kalkması beklenir; listede tutmak için `stop` kullanın. `COMPOSE_PROJECT_NAME` değerini değiştirmek başka bir proje ve volume kümesi seçer; mevcut kurulumda bu değeri sabit tutun. Makefile yalnız isteğe bağlı yerel geliştirme/test yardımcılarını içerir; Docker hedefleri yoktur.

Mevcut verileri korumak için normal işletimde volume silme komutları kullanmayın. Migration `0003_enterprise_console`, mevcut tabloları/işleri silmeden yeni yönetim tablolarını ekler. Eski fixture kayıtları korunur fakat gerçek envanter olarak sunulmaz.

### Durdurma ve boş veritabanıyla yeniden kurulum ayrımı

`docker compose stop` servisleri durdurur; kullanıcıları, cihazları, veritabanını ve şifreleme anahtarlarını **silmez**. Aynı proje adıyla `up --build` çalıştırmak imajları günceller fakat eski kayıtları sıfırlamaz. Docker motorunu veya başka projelerin servislerini kapatmak gerekmez. Birden fazla context/QA kurulumu varsa her birinin container etiketlerindeki proje ve repository yolunu doğrulayıp yalnız ilgili servisleri durdurun.

Eski verileri silmeden gerçekten boş bir kurulum istiyorsanız, repository'nin varsayılan PostgreSQL/volume düzeninde **daha önce kullanılmamış** ayrı bir Compose proje adı seçin. Örneğin aşağıdaki adı yalnız henüz kullanılmadıysa kullanın; önce eski kurulumun aynı host portlarını serbest bıraktığını doğrulayın:

```bash
docker compose -p stocc-netstudio-fresh config --quiet
docker compose -p stocc-netstudio-fresh up --build -d --wait
docker compose -p stocc-netstudio-fresh exec api python -m app.admin create-user --username admin --role superadmin --site '*'
```

Sonraki `ps`, `stop`, `up` ve `exec` işlemlerinde de aynı `-p stocc-netstudio-fresh` değerini ve Docker context'ini kullanın. Bu örnek yeni PostgreSQL ve anahtar volume'leri oluşturur; eski kurulumu silmez veya taşımaz. Harici `DATABASE_URL` ya da özel/shared volume override'ı kullanıyorsanız yalnız proje adını değiştirmek veriyi izole etmez; önce hedefleri doğrulayın. TLS kurulumunda mevcut `-f docker-compose.yml -f docker-compose.tls.yml` seçeneklerini de koruyun. `down -v` veya volume silme işlemi bu kurulum adımlarının parçası değildir.

## Gerçek cihazı bağlama

1. **Cihaz Ekle** ile yönetim IP'sini, siteyi, SSH portunu ve cihaz türünü kaydedin. İsteğe bağlı olarak SSH kullanıcı adı ve parola ya da özel anahtar/passphrase tanımlayın. Eksik kimlik bilgilerini daha sonra **Bağlantı bilgileri** üzerinden tamamlayabilirsiniz.
2. **Yetkili kullanıcı tarafından cihaz eklenmesi, kayıtlı yönetim IP/SSH portu için bağlantı onayıdır.** Cihaz başına `.env` izni eklenmez. `STOCC_SSH_ALLOWED_CIDRS` yalnız isteğe bağlı kurulum geneli ek sınırdır: boşsa kayıtlı hedefler kabul edilir, doluysa bu CIDR sınırı da uygulanır; geçersiz CIDR bağlantıyı reddeder. Loopback adresler ayrıca açık CIDR izni ister; belirsiz, multicast ve link-local hedefler reddedilir. Mevcut kurulumda tanımlı ek sınırlar otomatik kaldırılmaz.
3. Cihazın OpenSSH **public host anahtarını** ve bağımsız, güvenilir bir kanaldan doğruladığınız SHA256 fingerprint'i **Bağlantı bilgileri** ekranına girin. Bu alan cihazın host anahtarıdır; kullanıcının oturum açma public anahtarı değildir. Anahtarın yalnız ağdan alınması kimliğini doğrulamaz. Otomatik TOFU/`known_hosts=None` kullanılmaz.
4. **Bağlantıyı test et** ile gerçek SSH el sıkışmasını kontrol edin. **SSH** üst paneli böler; cihaz solda, terminal sağda kalır. Dar ekranda iki alan alt alta geçer. Terminal açıkken yeniden tıklamak ikinci oturum oluşturmaz.
5. Veri toplama yöntemini seçin:
   - `Linux · salt okunur SSH`: **Veri topla**, sabit `ip -j -s link show`, `ip -j address show`, `/proc/uptime`, boot ID ve isteğe bağlı `ip -j neigh show` okumalarını gerçekleştirir. İki geçerli sayaç gözlemi trafik hızı için gerekir. Donanım port geometrisi bu çıktılardan tahmin edilmez.
   - `Huawei VRP · salt okunur SSH`: **Veri topla**, VRP sürümünü, arayüzleri/portları, RX/TX hız ve sayaçlarını, IP arayüzlerini, MAC/ARP gözlemlerini ve destekleniyorsa CPU/RAM ölçümlerini okur. VRP 5.120 / S5700 V200R002 biçimi için ayrıştırıcı testleri vardır; [Huawei kurulum ve veri sözleşmesine](docs/huawei-vrp.md) bakın. Model adına bakarak port eklenmez.
   - `Cisco IOS · Catalyst 2960-X salt okunur SSH`: **Veri topla**, IOS/model kimliğini, cihazın raporladığı fiziksel portları, durum/hız/sayaçları, IP arayüzlerini ve MAC/ARP gözlemlerini okur. İlk desteklenen ürün ailesi `WS-C2960X-*`; ayrıntılar [Cisco IOS veri sözleşmesindedir](docs/cisco-ios.md). Nominal model kapasitesinden eksik port üretilmez.
   - `Harici toplayıcı`: Mevcut SNMP/NETCONF/üretici toplayıcınızı aşağıdaki envanter/gözlem API'sine bağlayın. Üretici komutları veya desteklenmeyen telemetri varsayılmaz. **Envanter aktar** doğrulanmış JSON dosyasını kabul eder.

Mevcut bir cihazı yeniden eklemek gerekmez: **Bağlantı bilgileri → Veri kaynağı** alanından toplayıcısını değiştirin. Eski VRP ve açıkça doğrulanmış benzer legacy SSH cihazlarında **SSH uyumluluk profili → Eski VRP** seçeneği, risk onayıyla yalnız bu cihaza SHA-1 KEX / ssh-rsa / aes128-cbc uyumluluğu ekler. Standart profil varsayılandır; otomatik downgrade veya host anahtarı kabulü yoktur. Profil/veri kaynağı değişikliği audit edilir ve açık terminalleri sonlandırır.

**Yenile**, alınmış verileri yeniden okur; cihazı sorguladığı anlamına gelmez. Linux/Huawei/Cisco toplama işleri açık kullanıcı eylemiyle başlar; zamanlanmış SNMP/SSH polling servisi bu sürümde yoktur. Harici toplayıcı kendi zamanlamasını yönetir. Tarayıcı her 15 saniyede ortak görünümü sorgular; bileşenler ayrı telemetri istekleri oluşturmaz.

Diğer üreticiler/sürümler ve fiziksel cihaz kabulü ayrıca gerekir; Huawei/Cisco ayrıştırıcı testleri fiziksel switch kabulü değildir. Önceki sürümde gerçek konfigürasyon uygulama veya yedekleme akışı bulunmuyordu; bu teslimat bu yetenekleri varmış gibi göstermez. SSH terminali salt okunur komut filtresi uygulamaz: uzak cihaz hesabının yetkileri geçerlidir. En az ayrıcalıklı cihaz hesabı kullanın.

## HTTPS ve üretim sınırları

Gerçek cihaz kimlik bilgilerini paylaşılan ağ üzerinden HTTP ile göndermeyin. Yerel geliştirme bağlantıları varsayılan olarak `127.0.0.1` ile sınırlıdır. Ağ erişimini açmadan önce geçerli TLS sertifikasını hazırlayın:

```dotenv
# .env içinde kendi değerlerinizi kullanın.
STOCC_ALLOWED_ORIGINS=https://netstudio.example.org
STOCC_TLS_DIRECTORY=/absolute/protected/tls-directory
TLS_BIND_ADDRESS=0.0.0.0
TLS_PORT=443
```

Sertifika dizininde `fullchain.pem` ve `privkey.pem` bulunmalı; yalnızca gateway kullanıcısının (UID/GID 101) okuyabileceği uygun izinler verilmeli. Özel anahtarı herkes tarafından okunabilir yapmayın. Ardından:

```bash
docker compose -f docker-compose.yml -f docker-compose.tls.yml up --build -d --wait
```

TLS kurulumunda sonraki Compose işlemlerinde de `-f docker-compose.yml -f docker-compose.tls.yml` seçeneklerini birlikte kullanın; yalnız ana dosyayla `up` çalıştırmak HTTP yapılandırmasına döndürür.

TLS override; üretim modunu etkinleştirir, PostgreSQL/API host portlarını kaldırır ve yalnız HTTPS gateway portunu yayımlar. API üretimde HTTP'yi ve terminal WS'yi reddeder; cookie `Secure`, `HttpOnly`, `SameSite=Strict` olur. Proxy, istemcinin gönderdiği forwarded başlıklarını kendi değerleriyle değiştirir. API'nin proxy güveni Docker iç ağına dayanır; API'yi doğrudan internete açmayın veya güvenilmeyen container'ları bu ağa katmayın.

Kimlik doğrulama, yerel Argon2id kullanıcıları ve veritabanındaki iptal edilebilir, 8 saatlik opaque oturumlarla yapılır. Değişiklik isteklerinde exact-origin ve CSRF kontrolü vardır. Roller:

| Rol | Envanter | İş / SSH | Cihaz, sır, envanter / telemetri yönetimi | Kendi profil / avatar / parolası | Kullanıcı yönetimi / audit |
| --- | --- | --- | --- | --- | --- |
| `viewer` | İzinli lokasyonlar | Hayır | Hayır | Evet | Hayır |
| `engineer` | İzinli lokasyonlar | İzinli lokasyonlar | İzinli lokasyonlar | Evet | Hayır |
| `superadmin` | İzinli lokasyonlar | İzinli lokasyonlar | İzinli lokasyonlar | Evet | Global |

Kullanıcı/audit yönetimi yalnız superadmin rolüyle açılır; sadece menü gizlenmez, backend de erişimi reddeder. Superadmin'in cihaz işlemleri dahi kayıtlı lokasyon kapsamına tabidir; `*` tüm lokasyonları kapsar. Konfigürasyon uygulama ve ham yedek dışa aktarma izinleri yalnız superadmin'e ayrılmıştır; bu izinlerin varlığı henüz uygulanmayan cihaz yeteneklerini etkinleştirmez.

```bash
docker compose exec api python -m app.admin create-user --username engineer --role engineer --site merkez
docker compose exec api python -m app.admin disable-user --username engineer
```

Terminal ticket'ı 30 saniye geçerli, tek kullanımlı ve oluşturan oturuma bağlıdır; tek başına bearer token değildir. Hedef host/port tarayıcıdan alınmaz. Kullanıcı başına 3, süreç başına 20 terminal; aynı kullanıcı/cihaz için 1 oturum sınırı vardır. Bağlantı 12 sn, varsayılan boşta kalma 300 sn, toplam oturum 3600 sn; giriş mesajı 16 KiB ve 64 KiB/sn ile sınırlıdır. Süreler `STOCC_SSH_IDLE_SECONDS` / `STOCC_SSH_MAX_SECONDS` backend ortam değişkenleriyle ayarlanabilir. Yetki/oturum iptali en geç izleme döngüsünün yaklaşık 1 saniyelik kontrolünde uygulanır. Bağlantı kurulma aşamasında tekrar doğrulama PTY açılmadan yapılır.

Panel kapanması, sayfadan çıkış, çıkış yapma, kimlik bilgisi değişimi/silinmesi ve host anahtarı değişimi terminali sonlandırır. Uzak PTY boyutu tarayıcı terminaliyle birlikte güncellenir. Terminal çıktısı xterm'e metin olarak iletilir; HTML olarak işlenmez. SSH denetimi kullanıcı, cihaz, oturum kimliği, başlangıç/bitiş, süre ve sonucu kapsar; ham terminal, parola, private key veya cookie loglanmaz.

## Kullanıcı yönetimi ve audit

### Hesabım ve yönetici işlemleri

Üst barın en sağındaki avatar/kullanıcı alanı veya yan menünün altındaki **Hesabım** bağlantısı `/account` sayfasını açar. Her kullanıcı kendi görünen adını, isteğe bağlı avatarını ve mevcut parolasını doğrulayarak yeni parolasını değiştirebilir. Superadmin aynı sayfada kullanıcı oluşturur, arar, rol/lokasyon/aktiflik bilgilerini düzenler, başka kullanıcıların parolasını sıfırlar ve kullanıcı adıyla onaylayarak hesap siler. Kayıtlı parola hiçbir okuma API'sine veya düzenleme formuna geri verilmez; düzenlemede boş parola mevcut hash'i korur.

- Yeni parolalar 12–1024 karakterdir ve Argon2id ile hashlenir. Kişisel parola değişimi mevcut parolayı ister; admin düzenleme ekranı bu kontrolü atlatamaz.
- Rol, lokasyon, kullanıcı adı, aktiflik veya parola değişiminde ilgili kullanıcının tüm uygulama oturumları iptal edilir; SSH oturumları da kapanır. Görünen ad/avatar değişimi oturumu kapatmaz.
- Kendi hesabını silme, devre dışı bırakma veya superadmin rolünü kaldırma engellenir. Son aktif superadmin korunur. Eşzamanlı kullanıcı değişiklikleri ve girişin son adımı PostgreSQL transaction kilidi altında tekrar yetkilendirilir; hesap değişikliği ve audit aynı transaction'a yazılır. Kullanılan kilit mekanizması [PostgreSQL transaction seviyeli advisory lock](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) yaklaşımıdır.
- Avatar yalnız PNG/JPEG/WebP olarak, en fazla 2 MiB ve 2048×2048 piksel yüklenebilir. SVG/animasyon reddedilir. [Pillow](https://pillow.readthedocs.io/en/stable/reference/Image.html) ile tür/çözünürlük doğrulaması, metadata temizliği ve en uzun kenarı en fazla 256 piksel olan PNG'ye yeniden kodlama yapılır. Dosya veritabanında saklanır; harici URL, dosya sistemi yükleme yolu veya public avatar servisi yoktur. Yalnız sahibi ve superadmin okuyabilir; HTTP cache'e alınmaz.
- Hesap silinince profil, avatar ve oturumlar kaldırılır; geçmiş audit satırları ve kayıt anındaki kullanıcı bilgileri korunur.

### Ayrıntılı denetim ve gizlilik sınırı

**Denetim kayıtları** (`/audit`) yalnız superadmin'e açıktır. Kayıtlar kullanıcı adı/kimliği, olay, sonuç, hedef ve tarih aralığıyla filtrelenir; en yeni olaydan başlayarak cursor ile sayfalanır. İlk sayfa 15 saniyede bir yenilenir. Her olayın detayında varsa kullanıcı/rol snapshot'ı, hedef kimliği, UTC zamanı, istek korelasyon kimliği, HTTP yöntemi/route şablonu/durum kodu, kayıt anına kadar geçen süre, uzak adres, istemci tanımı, iş/SSH kimliği ve güvenli değişiklik ayrıntıları görülür. Eski veya arka plan kayıtlarında bulunmayan alanlar sonradan uydurulmaz. İstemci tanımı güvenilmeyen metindir; uzak adres proxy/NAT koşullarına göre gateway adresi olabilir.

Sunucu tarafında giriş/çıkış, kullanıcı CRUD, profil/parola/avatar değişikliği, cihaz/envanter/kimlik bilgisi/host-key işlemleri, telemetri, iş ve SSH yaşam döngüsü, audit görüntüleme ve reddedilen/başarısız API istekleri kaydedilir. Kullanıcı ve profil değişiklikleri güvenli **önce/sonra** değerlerini; cihaz oluşturma izin verilen gönderilmiş alanları içerir. Büyük envanter/telemetri gövdeleri yerine kaynak, zaman ve sayımlar saklanır. Parola/sır işlemlerinin yapıldığı kaydedilir, içerikleri kaydedilmez.

Sayfa görüntüleme, envanter araması/filtreleri, port ve topoloji seçimi ayrıca `client-reported` olarak işaretlenir. Bunlar doğrulanmış sunucu işlemlerinin yerine geçmez; tarayıcı bildirimi engelleyebilir veya değiştirebilir. Arama 1 saniye bekleme sonrası kaydedilir, her tuş vuruşu izlenmez. Kaydetmeden bırakılan form alanları, clipboard ve SSH komutları/giriş/çıktıları toplanmaz.

Audit'e yalnız işlem bazında seçilmiş ve merkezi izin listesinde bulunan alanlar girer; metin/dizi/derinlik sınırları ve ek sır kalıbı maskelemesi uygulanır. Parolalar/hash'ler, private key/passphrase, erişim tokenları, cookie/CSRF, ham HTTP başlık/gövdeleri, avatar bytes/EXIF ve ham terminal içeriği kaydedilmez. Sırları isim/arama gibi sır olmayan alanlara yapıştırmayın; serbest metinde her olası sırrı otomatik tanımak garanti edilemez.

Bu sürümde audit düzenleme/silme API'si, otomatik silme politikası veya kriptografik değişmezlik/WORM iddiası yoktur. Veritabanı yöneticisi kayıtları değiştirebilir. Saklama süresi, korumalı yedekler ve gerekirse bağımsız denetim deposu işletmecinin sorumluluğundadır; ayrıntılı loglama disk kapasitesiyle birlikte izlenmelidir.

### Mevcut kurulumun güncellenmesi

Önce veritabanı ve ayrı anahtar deposunun korumalı yedeğini alın; uygun bir bakım aralığında mevcut Compose projesini güncelleyin:

```bash
docker compose up --build -d --wait
```

Üretim TLS kurulumunda bunun yerine mevcut override'ı koruyun:

```bash
docker compose -f docker-compose.yml -f docker-compose.tls.yml up --build -d --wait
```

`migrate` servisi API'den önce `0004_user_management` migration'ını uygular: `admin → superadmin`, `operator → engineer`, `viewer → viewer`. Engineer artık izinli lokasyonlarda cihaz/envanter/kimlik bilgisi yönetebilir; eski operator hesaplarının kapsamını güncellemeden önce gözden geçirin. ID, parola hash'i, lokasyonlar, cihazlar ve geçmiş audit korunur. Tanınmayan rol kaydı güvenli biçimde devre dışı bırakılır; eski kullanıcının bilinmeyen oluşturulma tarihi `null` kalır. Migration ileri yönlüdür; otomatik downgrade veri silmez, açık hata verir. Geri dönüş planı uygun uygulama sürümü ve onaylanmış yedekten geri yüklemedir. Mevcut volume'leri silmeyin ve dolu kuruluma QA seed çalıştırmayın.

## Sır deposu ve yedekleme

Cihaz parolası/özel anahtar/passphrase hashlenmez; AES-256-GCM ile şifrelenir. Her kayıt güncellemesinde rastgele 12 byte nonce, cihaz kimliği ve key ID içeren AAD kullanılır. Uygulama kullanıcısı parolası ise Argon2id hash'idir. Cihaz okuma API'si sırları döndürmez; tarayıcı sırları kalıcı storage'a veya SWR cache'e yazmaz. Düzenlemede seçili sır alanı boşsa **kayıtlı kimlik bilgilerinin tamamı** korunur; kullanıcı adı/yöntem değişimi yeni sırla birlikte yapılır. Silme ayrı onaylı işlemdir.

Anahtar deposu hazır değilse veya şifre çözme doğrulanamazsa bağlantı reddedilir. Veritabanı yedeği ile anahtar volume'ü yedeğini ayrı, erişimi kısıtlı yerlerde saklayın. Anahtar kaybolursa şifreli cihaz sırları kurtarılamaz. `secrets-init` mevcut anahtar dosyasının üzerine yazmaz.

Kontrollü rotasyon (önce iki deponun korumalı yedeğini alın; rotasyon sırasında kimlik bilgisi yazımlarını durdurun):

```bash
docker compose run --rm secrets-init python -m app.keyring add-key
docker compose exec api python -m app.admin rotate-secrets
```

İlk komut eski anahtarları koruyup yeni aktif anahtar ekler. İkincisi mevcut kayıtları yeni anahtarla tek işlemde yeniden şifreler. API anahtar dosyasını bağlantıda yeniden okur. Eski anahtarları, yedeklerin saklama politikasını ve şifre çözme doğrulamasını tamamlamadan kaldırmayın.

## Veri sözleşmesi ve metrik anlamları

Kaynağın gerçek sözleşmesi [contracts.py](backend/app/contracts.py), [models.py](backend/app/models.py), [telemetry.py](backend/app/telemetry.py), [account_api.py](backend/app/account_api.py), [users.py](backend/app/users.py) ve çalışan API'nin `/openapi.json` çıktısıdır. Tüm aşağıdaki yollar `/api/v1` öneklidir; giriş endpoint'i dışında oturum cookie'si zorunludur. Mutasyonlarda izinli `Origin` ve (giriş dışında) `/session/me` yanıtındaki `csrf_token` ile `X-CSRF-Token` gerekir.

| Yol | İşlev |
| --- | --- |
| `POST /session/login`, `GET /session/me`, `POST /session/logout` | Kimlik doğrulama / oturum |
| `GET, PUT /profile`, `PUT /profile/password` | Kendi profili / mevcut parola doğrulamalı değişiklik |
| `PUT, DELETE /profile/avatar`, `GET /users/{id}/avatar` | Avatar yükleme/kaldırma ve yetkili okuma; yükleme JSON değil binary görseldir |
| `GET, POST /users`, `GET, PATCH, DELETE /users/{id}` | Yalnız superadmin; liste `q`, `role`, `limit`, `cursor` kabul eder; silme gövdesi `confirmation_username` ister |
| `GET, POST /devices`, `GET /devices/{id}` | Site kapsamlı envanter |
| `PUT /devices/{id}/inventory` | Fiziksel bileşen, port, arayüz ve explicit eşlemeler |
| `POST /devices/{id}/observations` | Kaynak ve zaman içeren doğrulanmış gözlem |
| `GET /overview?minutes=60` | Ortak cihaz/port/sağlık/topoloji/zaman serisi görünümü |
| `GET /topology` | Yetkili sitelerin cihazları, son MAC/IP gözlemleri ve açık uzak cihaz kimlikli bağlantıları |
| `GET, PUT /topology/board` | Oturum kullanıcısına ait zone, konum ve elle çizilen port bağlantıları; PUT önceki `version` değerini ister |
| `GET /devices/{id}/observations/latest` | Son ham, normalize edilmiş gözlem |
| `PUT, DELETE /devices/{id}/credentials`, `PUT /devices/{id}/host-key` | Sır / güven kaydı yönetimi |
| `PUT /devices/{id}/connection-settings` | Site yetkili engineer/superadmin; `collector`, `ssh_profile`, legacy etkinleştirmede `legacy_ssh_confirmed:true`; serbest hedef/port kabul etmez |
| `POST /devices/{id}/polls`, `POST /devices/{id}/connection-tests`, `GET /jobs` | Kalıcı iş sonucu |
| `POST /devices/{id}/ssh-sessions`, `DELETE /ssh-sessions/{id}` | Terminal yaşam döngüsü |
| `WS /ssh-sessions/{id}/ws` | Kimliği doğrulanmış giriş/çıktı/resize köprüsü |
| `GET /audit` | Yalnız superadmin; `actor` (tam kullanıcı adı/ID), `event`, `outcome`, `target_id`, `since`, `until`, `limit`, `cursor`; `{items, next_cursor}` |
| `POST /activity` | Sınırlı, kimliği doğrulanmış `client-reported` arayüz olayları; serbest log gövdesi kabul edilmez |

Envanter aktarımı tam snapshot'tır: `components`, `physical_ports`, `interfaces`, `bindings`, `source`, zaman dilimli `observed_at`; opsiyonel `serial`, `os_version`. `Interface` mevcut Observation sözleşmesini korur: `admin_up`, `oper_up`, `speed_mbps` alanlarında `value`, `observed_at`, `stale_after_seconds`, `source`, `quality` gerekir. Bilinmeyen değerde `value:null`, `quality:"unknown"` gönderin. Bunlar port geometrisi değil arayüz gözlemleridir. Envanter içindeki fixture kaynağı kabul edilmez.

Telemetride envanterdeki aynı `interface_id` kullanılır; `rx_bps`, `tx_bps`, `capacity_bps` birimi **bit/s**; `in_octets`, `out_octets` birimi **byte**'tır. Sıfır yalnız ölçülen sıfırı ifade eder. Desteklenmeyen arayüz metriği `quality:"unsupported"`; toplama hatası `error`; eksik ölçüm `null` olmalıdır. `health.status` için `ok/warning/critical` verilirse toplayıcının `evaluation` açıklaması zorunludur; uygulama rastgele eşik/puan üretmez.

- Fiziksel ağ portları sayılır; management/console ve VLAN, loopback, port-channel gibi mantıksal arayüzler sayılmaz. Breakout çocukları üst portla birlikte sayılmaz. Fiziksel eşleme bilinmiyorsa port türü/adedini tahmin etmeyin.
- Aktif port oranı = açık ve link-up fiziksel port / tüm fiziksel ağ portları. Bilinmeyenler ayrıca sayılır ve paydada kalır. Tüm portlar bilinmiyorsa oran yoktur. İdari kapalı port arıza sayılmaz; link-up kablo/modül varlığını kanıtlamaz.
- Sayaçtan hız = `8 × byte farkı / saniye farkı`. İlk örnek, reset/taşma, değişmiş `discontinuity` (boot ID gibi), geçersiz/uzun aralık ve bozuk kalite boşluk üretir. Reset/taşma için tahmini düzeltme yapılmaz. Kaynak reboot/sayaç sürekliliği belirtecini sağlamalıdır.
- RX ve TX kapasiteye ayrı bölünür; iki yönün toplamı tek yön kapasitesine bölünmez. Kapasite yoksa yüzde gösterilmez. Trafik, explicit fiziksel eşlemeli ethernet arayüzlerinin gözlenen toplamıdır; benzersiz ağ trafiği değildir. Yalnız mantıksal arayüz envanteri alınan Linux cihazlarında port/kapasite grafiği boş kalması beklenir.
- `stale_after_seconds` kaynak tarafından belirtilir (varsayılan 120 sn). Eski veri/başarısız güncelleme normal sağlık olarak gösterilmez; son bilinen değerlerin zamanı korunur. Envanter ve telemetri tarihleri ayrı gösterilir.
- IP topolojisi atanmış IP'nin alt ağıyla L3 ilişkisidir. L2/fiziksel komşuluk yalnız açık ilişki türü ve `evidence` kaydıyla eklenir. Yönetim IP'si/MAC listesi fiziksel bağlantıya çevrilmez. Mevcut VRF/VLAN açıklaması korunur.
- Grafik ve liste aynı filtre kapsamını kullanır; 20 satırlık sayfalama üst özetleri daraltmaz. Trafik penceresi 5–1440 dakika; cihaz başına son 2880 örnek sınırı aşıldığında ekranda açık uyarı çıkar. Çizimde LTTB görsel örneklemesi, aralık kesintilerinde null boşluklar kullanılır. Ham veriler değiştirilmez. Büyük filo kapasitesi ölçülmüş değildir; benchmark gerekir.

## Topoloji çalışma alanı

Yan menüdeki **Topoloji**, `/topology` sayfasını açar. Taralı SVG çalışma alanında zone oluşturun; bir cihaz seçip **Zone ataması** yapın veya cihazı zone’un içine sürükleyin. Zone başlığını taşıdığınızda içindeki cihazlar birlikte taşınır. Ad, ton, konum ve boyut seçim panelinden düzenlenir; zone kaldırma cihazları silmez. Cihaz/zone odağında ok tuşları, yakınlaştırma düğmeleri, **Ortala**, arama ve cihaz seçimi sürüklemeye alternatif sunar. Mobilde normal dokunuş sayfayı kaydırır; **Taşıma modu** alan içi sürüklemeyi etkinleştirir. Tarayıcı yakınlaştırması engellenmez.

**Bağlantı ekle**, envanterde gerçekten bulunan iki cihazın portlarını seçtirir. Kesikli kullanıcı çizimi, toplayıcının L2/fiziksel kanıtlı ilişkilerinden ayrıdır; cihaz konfigürasyonuna komut göndermez. Mevcut istatistiksel ECharts grafikleri ve detay sayfasındaki IP topolojisi değişmez. Yeni düzenleme yüzeyi React/SVG’dir; gözlem, geometri ve etkileşim kodları ayrı katmanlardadır.

Yerleşim kullanıcıya özeldir; viewer dahil her rol yalnız **kendi çizimini** düzenleyebilir. Bu yetki cihaz/telemetri yazma yetkisi vermez. Envanterin mevcut sahiplik sınırı **site yetkisi**dir; oluşturana göre sahiplik alanı yoktur. Başkasının board kimliği kabul edilmez. Sunucu her okumada/yazmada site kapsamını denetler; erişimi kaldırılmış cihaz/port başvuruları okurken gizlenir. **Kaydet** PostgreSQL’e yazar, `version` uyuşmazlığında `409` döner ve arayüz taslağı korur. **Yerleşimi yeniden yükle** açık onayla taslağı bırakır. `0005_topology_workspace` migration’ı yalnız yeni tablo ekler; kullanıcı silinince kişisel yerleşimi FK cascade ile silinir, audit korunur. Standart `docker compose up -d --build` migration’ı API’den önce çalıştırır; veri volume’lerini silmeyin.

### MAC/IP uç verisi

Mevcut `POST /api/v1/devices/{id}/observations` gövdesi isteğe bağlı şu alanı kabul eder (adresler yalnız dokümantasyon örneğidir):

```json
{
  "endpoints": {
    "status": "ok",
    "entries": [{
      "id": "vlan10-mac-020000000001-if1",
      "interface_id": "if1",
      "mac": "02:00:00:00:00:01",
      "addresses": ["192.0.2.101"],
      "vlan": 10,
      "discovery": "fdb",
      "state": "unknown",
      "evidence": "FDB ve aynı VLAN kapsamındaki doğrulanmış ARP eşlemesi"
    }]
  }
}
```

Bu parça tek başına tam telemetri isteği değildir; mevcut `observed_at`, `source` ve diğer alanlarla gönderilir. ID toplayıcıda kararlı tutulmalı; arayüz envanterde bulunmalıdır. `status`: `ok`, `partial`, `unknown`, `unsupported`, `error`; alan gönderilmemiş eski gözlemler **henüz toplanmadı**, başarılı boş tablo **kayıt yok** şeklinde ayrılır. Bir snapshot en fazla 2048 uç içerir; kısmi tabloda `partial` gönderin. MAC tekil yayın adresi olarak doğrulanır, IP’ler IPv4/IPv6 olarak ayrıştırılır. `discovery` FDB, ARP veya NDP’dir; `state` komşuluk durumudur, bilgisayarın çevrimiçi olduğunu varsaymaz. Zaman/kaynak ve güncellik telemetri snapshot’ından gelir.

Linux toplayıcısı [iproute2 komşuluk tablosunu](https://github.com/iproute2/iproute2/blob/main/man/man8/ip-neighbour.8) salt okunur biçimde alır; FAILED/INCOMPLETE kayıtları uç olarak çizmez ve NUD STALE durumunu saklar. Bridge/SVI ARP kaydını tahminen fiziksel porta dağıtmaz. FDB/VLAN eşlemesi ve üretici switch tabloları harici toplayıcıdan gelmelidir; otomatik SNMP/LLDP tarayıcısı eklenmemiştir. Yönetim IP’si veya eşleşen cihaz adı üzerinden kablo üretilmez.

Uç düğümlerin bilgisayar sembolü **uç kaydı** anlamındadır, donanım türü kanıtı değildir. IP bilinmiyorsa boşluğu açıkça gösterir. Seçimde MAC, tüm IP’ler, VLAN, arayüz, yalnız explicit eşlenmiş fiziksel port, kaynak, kanıt ve gözlem zamanı görünür. Aynı MAC farklı cihaz/port/VLAN’da gözlenirse kayıtlar birleştirilmez; arada switch/telefon/köprü bulunabilir.

Cihazlar arası gözlenen bağlantı için mevcut `neighbors` kaydına opsiyonel `remote_device_id` ve `remote_interface_id` eklenir. Uzak kimlik erişim kapsamında olmalı; bilinmeyen uzak arayüz port olarak sunulmaz. Sadece `label` olan komşular ayrıntı listesinde eşlenmemiş kalır. L2 gözlemi, fiziksel ilişki ve kullanıcı çizimi ayrı anlam taşır.

Çizimde en fazla 24 cihaz ve cihaz başına 6 uç görünür. Diğer cihazlar arama/odak seçimiyle; **tüm uç kayıtları** seçili cihazın aranabilir, sayfalı listesiyle erişilir. Bu çizim bütçesi veriyi veya toplamları azaltmaz; backend son snapshot’ları tek sorguda getirir, geçmiş trafik yüklenmez. Büyük filo performansı ölçülmüş değildir. Yerleşim sınırları 40 zone, 500 kayıtlı cihaz konumu ve 500 kullanıcı bağlantısıdır. Kaydetme, sürüm/sayımlar ve izinli yerleşim girdileriyle `topology.saved` olarak audit edilir; mevcut audit boyut sınırları geçerlidir. Kaydedilmemiş sürükleme adımları veya tuş vuruşları loglanmaz.

## Geliştirme ve doğrulama

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

API başlatırken migrate edilmiş `DATABASE_URL` gerekir; üretim uygulamasında bellek/fixture fallback yoktur. Yerel Next.js HTTP API proxy'si cookie/origin/CSRF'yi korur ancak WebSocket tüneli değildir; terminal doğrulaması için Docker gateway yolunu kullanın.

Testler SQLite ile izole API/şifreleme/RBAC semantiğini ve geçici gerçek AsyncSSH sunucusuyla terminal el sıkışmasını, parola ve passphrase'li anahtar doğrulamasını, yanlış host anahtarının reddini, PTY resize, mesaj sınırı ve logout kapanmasını denetler. Domain fixture'ları yalnız testlerde kullanılır.

### İzole tarayıcı test ortamı

Mevcut kurulumun project/volume'lerini kullanmayın. Aşağıdaki ortam ayrı test veritabanı ve anahtar deposu oluşturur. QA CIDR izni yalnız bu test ağı içindir; gerçek `.env` dosyasına taşımayın.

```bash
export COMPOSE_PROJECT_NAME=stocc-redesign-qa IMAGE_TAG=redesign-qa
export POSTGRES_DB=stocc_qa POSTGRES_PORT=18432 API_PORT=18000 WEB_PORT=13000
export DATABASE_URL=postgresql+psycopg://stocc:stocc@postgres:5432/stocc_qa
export STOCC_ALLOWED_ORIGINS=http://127.0.0.1:13000 STOCC_SSH_ALLOWED_CIDRS=172.16.0.0/12
docker compose -f docker-compose.yml -f deploy/compose.qa.yml up --build -d --wait
STOCC_TEST_DATABASE_URL=postgresql+psycopg://stocc:stocc@127.0.0.1:18432/stocc_qa .venv/bin/python backend/tests/seed_browser.py
cd frontend
STOCC_QA=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:13000 npm run test:e2e -- --workers=1
```

Playwright Chromium kurulu değilse `npx playwright install chromium` çalıştırın; mevcut Chrome için `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome` kullanılabilir. Seed yalnız loopback `stocc_qa` veritabanını kabul eder; mevcut envanter veya kullanıcı varsa durur, hiçbir hesabın üzerine yazmaz. QA kullanıcı/parolası yalnız `backend/tests/conftest.py` içindeki test fixture'ıdır; üretimde kullanılmaz. SSH test sunucusu üretim imajına kopyalanmaz.

Mevcut QA projesi kullanılıyorsa veya test hesabı değiştirilmişse hesabı sıfırlamayın. Yeni `COMPOSE_PROJECT_NAME` ve boşta olan PostgreSQL/API/web portlarıyla ayrı proje açın. QA SSH anahtar servisinin portu `STOCC_TEST_SSH_KEY_PORT` ile ayrılabilir. Seed sırasında `STOCC_TEST_ORIGIN`, `STOCC_TEST_SSH_KEY_URL`, `STOCC_TEST_SSH_CONTAINER` ve `STOCC_TEST_DATABASE_URL` değerlerini **aynı yeni projeyi** gösterecek şekilde verin; testlerde de `PLAYWRIGHT_BASE_URL` bu origin olmalıdır. Seed varsayılanları sırasıyla `http://127.0.0.1:13000`, `http://127.0.0.1:12223`, `stocc-redesign-qa-ssh-lab-1` adresleridir. Seed seçili Docker context'i kullanır; gerekirse `STOCC_TEST_DOCKER_CONTEXT` ile aynı QA projesinin context'ini açıkça belirtin. Seed HTTP endpoint'leri yalnız loopback olabilir.

Tarayıcı testleri masaüstü/mobil yerleşim, filtre kapsamı, ECharts, klavye ile port seçimi, form akışı, boş sır alanı, inline SSH giriş/kopyalama/yapıştırma/resize/kapanış ve logout senaryolarını gerçek API/gateway üzerinden denetler. Ayrıca sayfa kimliği, framework hata katmanı, konsol ve cookie güvenlik nitelikleri kontrol edilir. Girişten önceki `/session/me` 401 yanıtı beklenen davranıştır. Ekran görüntüleri işletim sisteminin geçici dizinindeki `stocc-netstudio-qa/` altına, başarısız test izleri `stocc-netstudio-playwright/` altına yazılır; otomatik olarak repository'ye eklenmez. Görsel değişikliklerde [görüntü yenileme kuralına](rule.md#5-her-görsel-güncellemede-readme-görüntülerini-yenile) göre incelenmiş üç README görüntüsü ayrıca `docs/screenshots/` altına alınır ve aynı değişiklikle teslim edilir; diğer geçici test kanıtları repository dışında kalır. Bunlar **sentetik QA envanteridir; fiziksel cihaz kanıtı değildir**.

2026-10-19 — kullanıcı yönetimi eklenmeden önceki tasarım/SSH kapsamının tarihsel doğrulama sonuçları:

| Kontrol | Sonuç / kapsam |
| --- | --- |
| Backend | 35 test geçti; RBAC/site, CSRF, şifreleme/rotasyon, metrikler, gerçek yerel SSH el sıkışması ve Linux toplama işleri |
| Frontend birim testleri | 13 test geçti; filtre kapsamı, bilinmeyen/eski veri, breakout sayımı, RX/TX anlamları ve marka varlıkları |
| Lint / TypeScript | Geçti |
| Production build | Yerel Next.js ve Docker web/API imajları oluşturuldu |
| HTTP / WS tarayıcı testi | 4 senaryo geçti; gerçek Nginx → API → PostgreSQL / SSH test sunucusu |
| HTTPS / WSS tarayıcı testi | Aynı 4 senaryo geçti; üretim cookie nitelikleri de doğrulandı |
| Görsel / etkileşim | Chrome 1536×1024 ve 390×844; beyaz/koyu gri yüzeyler, dik köşeler, grafik/listenin sırası, mobil taşma, klavye port seçimi, terminal panosu/resize/logout |
| Kalıcılık / dağıtım | Migration `0003`; PostgreSQL/API/gateway yeniden oluşturulunca cihaz kayıtları ve şifreli kimlik bilgileri korundu; anahtar izinleri `0600`, UID/GID `100:101` |
| Bağımlılık audit'i | `npm audit --omit=dev`: 0; geliştirme araçları dahil: 5 yüksek düzey kayıt |

Browser eklentisi bulunmadığı için repository'nin Playwright akışı ve yerel Chrome kullanıldı. HTTPS testi geçici, kendinden imzalı **QA** sertifikasıyla yapıldı; `STOCC_QA_TLS=1` yalnız bu testte tarayıcının sertifika güven hatasını atlar. Sertifika ayrıca `curl --cacert` ile doğrulandı. Gerçek sertifika otoritesi/kurum ağı için üretim kabulü yapılmadı. Giriş öncesi beklenen 401 dışında test edilen ana ekran/terminal akışlarında konsol hatası veya framework hata katmanı kalmadı.

Geliştirme audit'indeki 5 kayıt, ESLint'in `braces` bağımlılık zincirine aittir; üretim frontend bağımlılıklarında bildirilmiş açık yoktur. Test araçları Starlette/httpx ve Vite yapılandırmasına ilişkin geçiş uyarıları üretir; testler başarılıdır. Bu sonuç genel bir güvenlik veya üretim kabul sertifikası değildir. Fiziksel switch üretici uyumluluğu, kurumsal SSO, gerçek sertifika/ağ erişimi, yüksek yük ve yedekten geri dönüş kabulü bu yerel testin dışındadır.

### Kullanıcı yönetimi doğrulaması — 2026-10-19

| Kontrol | Sonuç / kapsam |
| --- | --- |
| Backend | 57 test geçti; isteğe bağlı PostgreSQL migration testi varsayılan koşuda atlandı, ayrı boş PostgreSQL veritabanıyla ayrıca geçti |
| Migration / eşzamanlılık | PostgreSQL 16 üzerinde `0001 → 0004`; eski rol/hash/lokasyon/audit korunması, tanınmayan rolün reddi ve eşzamanlı iki admin değişikliğinde son superadmin'in korunması doğrulandı |
| Mevcut QA güncellemesi | `0003 → 0004` geçişinde 1 kullanıcı, 16 cihaz, 149 telemetri örneği ve 524 audit kaydı korundu; sonra mevcut hesaptaki kullanıcı değişikliklerine müdahale edilmedi |
| Frontend | 18 birim testi, ESLint, TypeScript ve Docker web/API production build geçti |
| Tarayıcı | Ayrı `stocc-users-qa-20261019` projesinde, `http://127.0.0.1:13001` üzerinden 17 HTTP/WS senaryosu geçti |
| Yeni kullanıcı akışları | Üst/alt hesap bağlantısı; kullanıcı oluştur/düzenle/sil; audit filtresi ve önce/sonra detayı; avatar yükle/yenile/kaldır; parola değişiminde çıkış; viewer/engineer reddi; rol düşürülünce canlı SSH'nin kapanması |
| Görsel / regresyon | Hesap ekranı 1536×1080 ve 390×844; mevcut ekranlar 320–2560 px genişliklerde denetlendi. Sayfa kimliği, dolu içerik, konsol, hata katmanı, taşma, ECharts ve mevcut terminal etkileşimleri geçti |

Kullanıcı/avatar/audit ekranları mevcut ortak panel dili ve SWR oturum/cache akışıyla bütünleştirildi; ECharts değiştirilmedi. Browser eklentisi yoktu; repository Playwright akışı ve `/usr/bin/google-chrome` kullanıldı. Yeni akışların görüntüleri geçici `stocc-netstudio-accounts/` dizinindedir. Testler kendi oluşturdukları geçici kullanıcıları siler; onların audit geçmişini korur. Mevcut QA hesabının adı değiştiğinde ilk toplu regresyon giriş adımında durdu; hesabı değiştirmek yerine ayrı proje/volume'lerde yeniden çalıştırıldı ve 17 senaryo geçti.

PostgreSQL testi için `backend/` altında `STOCC_TEST_MIGRATION_DATABASE_URL` değişkenini yalnız bu test için oluşturulmuş, boş, loopback üzerinde ve adı `stocc_users_test_` ile başlayan bir veritabanına ayarlayıp `../.venv/bin/python -m pytest -q tests/test_user_migration.py` çalıştırın. Test boş olmayan veritabanını reddeder; mevcut QA veya üretim veritabanını kullanmayın. SQLite testi `0003` sonrasından güncel migration'a ilerler; eski `0002` PostgreSQL'e özgü ALTER COLUMN kullanır.

Yeni kullanıcı akışları için HTTPS/WSS, Safari/Firefox, yük testi, yedekten geri dönüş ve üretim kabulü bu koşuda yapılmadı. Önceki TLS sonucu yeni akışların TLS doğrulaması sayılmaz. Starlette/httpx, Alembic yapılandırması ve Vite geçiş uyarıları sürmektedir; başarısız test değildir. Audit değişmezliği ve otomatik retention bu kapsamda uygulanmadı.

### Topoloji çalışma alanı doğrulaması — 2026-10-19

- Backend: 66 test geçti; varsayılan koşuda isteğe bağlı PostgreSQL testi atlandı. Ayrı boş PostgreSQL 16 veritabanında migration/koruma testleri ayrıca geçti (`0001 → 0005`).
- Frontend: 23 birim testi, ESLint, TypeScript ve Docker web/API production build geçti.
- Gerçek Nginx/API/PostgreSQL/SSH fixture zincirinde 21 Playwright senaryosu geçti. Yeni dört senaryo kişisel zone/atama, klavye ve fare taşıması, port bağlantısı, MAC/IP seçimi, kaydetme/yeniden açma, sürüm çakışması, zoom/arama, mobile yerleşim ve zone/çizim silerken cihazların korunmasını kapsar. Mevcut hesap, SSH ve ECharts regresyonları da geçti.
- Test ortamı ayrı `stocc-topology-qa-20261019` Compose projesidir; mevcut kullanıcı kurulumu veya verileri değiştirilmedi. Önceki test koşuları giriş limitine ulaştığında yalnız izole API yeniden başlatıldı; uygulamanın güvenlik limitleri gevşetilmedi. Geçici test kullanıcıları ve onlara ait board’lar test temizliğinde kaldırıldı; audit korundu.
- Browser eklentisi bulunmadığı için mevcut Playwright ve sistem Chromium’u kullanıldı. Yeni sayfa 1536×1000, 1920×1080, 390×844 ve 844×390 boyutlarında incelendi; ekran kanıtları `/tmp/stocc-netstudio-topology/` altındadır, üretim varlığı değildir.
- Testler sentetik envanterle yapıldı. Fiziksel switch FDB/LLDP entegrasyonu, yeni sayfanın HTTPS üzerinde tarayıcı akışı, gerçek dokunmatik cihaz, Firefox/Safari ve büyük filo yük testi bu koşuda doğrulanmadı.

### Huawei VRP ve kayıtlı hedef onayı doğrulaması — 2026-10-19

- Backend: `.venv/bin/pytest -q backend/tests` ile **79 test geçti, 1 isteğe bağlı PostgreSQL migration testi atlandı**. Huawei testleri VRP 5.120 biçimi, iki eski SHA-1 KEX seçeneği, RSA host key, aes128-cbc, gerçek yerel SSH/PTY, sayfalama, rol/site, kayıtlı IP/port onayı, opsiyonel CIDR sınırı, host key reddi, profil değişince oturum kapanması ve başarısız okumada envanter korumasını kapsar. Test sırasında görülen SQLite eşzamanlı bağlantı paylaşımı da giderildi; PostgreSQL pool davranışı değişmedi.
- Frontend: **23 birim testi**, ESLint, TypeScript ve Docker API/web production build geçti. ECharts renderer/seri hesapları korunur; port ölçüm penceresi, PVID ve yönlü sayaçlar gerçek API alanlarından gösterilir.
- `http://127.0.0.1:13003` üzerindeki izole `stocc-huawei-qa-20261019` projesinde **23 Playwright senaryosu geçti**. Huawei/legacy form akışı 1536×1024 ve 390×844 boyutlarında; genel regresyonlar 320–2560 px genişliklerde doğrulandı. Browser eklentisi bulunmadığından mevcut Playwright ve sistem Chrome kullanıldı. Sayfa kimliği/içerik, framework hata katmanı, konsol, klavye/SSH etkileşimi ve görüntüler kontrol edildi; beklenen giriş öncesi 401 dışında ilgili konsol hatası yoktu.
- README'nin üç görüntüsü aynı güncel çalışma ağacından yenilendi. QA'da ek CIDR sınırı boş bırakılarak kayıtlı hedef onayı gerçek SSH zincirinde denendi. Çalışan `stocc-netstudio-fresh` kurulumu, `.env`, kullanıcı kayıtları ve anahtarları değiştirilmedi; yeni özellikler için mevcut kurulumun imajları ayrıca yeniden build edilmelidir. Yeni DB migration gerekmez.
- Fiziksel Huawei switch'e canlı bağlantı, yeni akışta HTTPS/WSS, Firefox/Safari ve yük testi bu koşuda yapılmadı. Gerçek cihazın bağımsız host anahtarı doğrulaması hâlâ gereklidir. Starlette/httpx, Alembic, Vite ve legacy FFDH deprecation uyarıları başarısız test değildir. Kullanım ve ölçüm sınırları [Huawei VRP rehberinde](docs/huawei-vrp.md) açıklanır.

### SFP sınıflandırması ve cihaz detay topolojisi doğrulaması — 2026-10-20

- Backend: **88 test geçti, 1 isteğe bağlı PostgreSQL migration testi atlandı**. Huawei VRP sınıflandırma testleri açık bakır/fiber port modu, GE/XGE/10GE/25GE SFP ailesi, açık QSFP belirteçleri, belirsiz 40GE/100GE ve 24 RJ45 + 4 SFP envanterini kapsar. Model adından port üretilmez; modül takılı kabul edilmez.
- Frontend: ESLint, TypeScript, **30 birim testi** ve Docker production build geçti. Apache ECharts korunur; cihaz detay topolojisi geniş panelde üç kolon, dar panelde iki kolon kullanır. Düğüm boyutu yakınlaştırmadan bağımsızdır; kaydırma, kontrollü yakınlaştırma ve sıfırlama sağlanır.
- İzole `stocc-sfp-topology-qa-20261020` Docker projesinde sistem Chrome ile **26 Playwright senaryosu geçti**. Cihaz detay topolojisi 1536 px ve 390 px genişlikte düğüm sınırları, yatay taşma, yakınlaştırma ve sıfırlama açısından doğrulandı; genel regresyon 320–2560 px aralığını ve gerçek izole SSH oturumunu kapsadı.
- README'nin ana sayfa, SSH kapalı detay ve SSH açık detay görüntülerinin üçü de aynı güncel çalışma ağacından yenilendi. Kullanıcının çalışan `stocc-netstudio-fresh` kurulumu, verileri, anahtarları ve volume'leri değiştirilmedi; QA volume'leri ayrı tutuldu. Yeni DB migration gerekmez.
- Bu koşuda fiziksel Huawei switch'e bağlanılmadı. Otomatik üretilmiş VRP envanteri bir sonraki başarılı veri toplamada yeni kuralla güncellenir; elle aktarılmış cihaz geometrisi korunur. HTTPS/WSS, Firefox/Safari ve büyük filo yük testi bu değişiklik için ayrıca doğrulanmadı. Starlette/httpx, Alembic, Vite ve legacy FFDH deprecation uyarıları başarısız test değildir.

### Cisco Catalyst 2960-X collector doğrulaması — 2026-10-20

- Backend: **102 test geçti, 1 isteğe bağlı PostgreSQL migration testi atlandı**. Yeni testler temizlenmiş `WS-C2960X-48FPD-L` IOS çıktısını, cihazın raporladığı portları model kapasitesinden ayırmayı, bakır/SFP/QSFP sınıflandırmasını, sayaç/VLAN/IP/MAC–ARP ayrıştırmasını, opsiyonel komut eksikliğini, elle aktarılmış geometrinin korunmasını ve gerçek yerel legacy SSH/PTY sayfalamasını kapsar.
- Frontend: ESLint, TypeScript, **30 birim testi** ve production build geçti. Bağlantı formunda `Cisco IOS · Catalyst 2960-X salt okunur SSH` veri kaynağı ile `Eski VRP` etiketi doğrulandı.
- Browser eklentisi bulunmadığından repository Playwright akışı ve sistem Chrome kullanıldı. İzole `stocc-cisco-qa-20261020` Docker projesinde **26/26 Playwright senaryosu geçti**; hedef form akışı 1536×1024 ve 390×844, genel responsive regresyon 320–2560 px aralığında kontrol edildi. Sayfa kimliği, dolu içerik, framework hata katmanı, konsol, gerçek QA SSH oturumu ve yatay taşma kontrolleri geçti.
- README'nin ana sayfa, SSH kapalı detay ve SSH açık detay görüntüleri aynı çalışma ağacından yenilendi ve görsel olarak incelendi. Test verileri sentetiktir; mevcut `stocc-netstudio-fresh` veritabanı, kullanıcıları, anahtarları ve volume'leri değiştirilmedi. Yeni DB migration gerekmez.
- Fiziksel `192.168.1.150` cihazında kullanıcı kimlik doğrulaması ve gerçek `show` çıktılarıyla tam veri toplama bu koşuda yapılmadı. Yerel entegrasyon fiziksel cihaz kabulü değildir; ilk canlı toplamada iş sonucu, model/sürüm, port sayısı ve uyarılar ayrıca kontrol edilmelidir.

Önceki kapsam ve kararların tarihsel kaydı: [ilk uygulama raporu](stocc-netstudio-uygulama-raporu.md). Güncel çalışma sınırları bu README ve kaynak koddaki sözleşmelerdir.
