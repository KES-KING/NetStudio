# Stocc NetStudio

Ağ cihazlarının envanterini, erişilebilirliğini, fiziksel portlarını, trafik gözlemlerini ve IP ilişkilerini aynı konsolda yönetin. Cihaz detayında açılan SSH terminali, backend üzerinden doğrulanmış cihaz kaydına bağlanır.

Arayüz: Next.js 16 / React 19 / TypeScript, Apache ECharts, xterm.js ve SWR. Backend: FastAPI, SQLAlchemy, PostgreSQL, AsyncSSH, Argon2id ve AES-256-GCM. Varsayılan kurulumda cihaz, kullanıcı veya örnek telemetri **oluşturulmaz**.

Marka varlıkları `frontend/public/branding/` içindedir: `netstudio-logo.png` giriş ekranı ve masaüstü üst barda, `netstudio-emblem.png` mobil üst bar ve sekme simgesinde kullanılır. Orijinal PNG içerikleri korunur; ortak `Brand` bileşeni yalnız şeffaf kenar boşluklarını görünümde çerçeveler. Logoların arkasında ayrı bir zemin yoktur; üst barın tamamı okunabilirlik için `nav-header` tokenıyla açık gri tutulur. Sekme simgesi `app/icon.tsx` ile amblemden şeffaf zemin üzerinde üretilir. Docker web imajı `public/` dizinini de içerir.

## Docker ile kurulum

Docker Engine ve Compose v2 gerekir. TLS override dosyasındaki `!override` için Compose 2.24.4 veya üzerini kullanın. Makinede Python veya Node kurulu olması gerekmez.

```bash
# .env zaten varsa üzerine yazmayın.
test -f .env || cp .env.example .env
make docker-up
make user-create USERNAME=admin
```

Son komut parolayı etkileşimli olarak iki kez ister; en az 12 karakter gerekir. Varsayılan yönetici parolası yoktur. Web: <http://127.0.0.1:3000>. `make` varsayılan olarak `default` Docker context'ini kullanır; gerektiğinde `DOCKER_CONTEXT=...` verin.

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

```bash
make docker-ps
make docker-logs
make docker-down        # Volume'leri silmez.
make docker-up          # Migration ve hazır olma kontrollerini tekrar çalıştırır.
```

Mevcut verileri korumak için normal işletimde volume silme komutları kullanmayın. Migration `0003_enterprise_console`, mevcut tabloları/işleri silmeden yeni yönetim tablolarını ekler. Eski fixture kayıtları korunur fakat gerçek envanter olarak sunulmaz.

## Gerçek cihazı bağlama

1. **Cihaz Ekle** ile yönetim IP'sini, siteyi, SSH portunu ve cihaz türünü kaydedin. İsteğe bağlı olarak SSH kullanıcı adı ve parola ya da özel anahtar/passphrase tanımlayın. Eksik kimlik bilgilerini daha sonra **Bağlantı bilgileri** üzerinden tamamlayabilirsiniz.
2. `.env` içindeki `STOCC_SSH_ALLOWED_CIDRS` değerine yalnızca izin verilen yönetim ağlarını yazın; örneğin kendi ağınıza ait belirli bir CIDR. **Boş değer tüm dış SSH bağlantılarını reddeder.** Değişiklikten sonra `make docker-up` çalıştırın.
3. Cihazın OpenSSH **public host anahtarını** ve bağımsız, güvenilir bir kanaldan doğruladığınız SHA256 fingerprint'i **Bağlantı bilgileri** ekranına girin. Bu alan cihazın host anahtarıdır; kullanıcının oturum açma public anahtarı değildir. Anahtarın yalnız ağdan alınması kimliğini doğrulamaz. Otomatik TOFU/`known_hosts=None` kullanılmaz.
4. **Bağlantıyı test et** ile gerçek SSH el sıkışmasını kontrol edin. **SSH** üst paneli böler; cihaz solda, terminal sağda kalır. Dar ekranda iki alan alt alta geçer. Terminal açıkken yeniden tıklamak ikinci oturum oluşturmaz.
5. Veri toplama yöntemini seçin:
   - `Linux · salt okunur SSH`: **Veri topla**, sabit `ip -j -s link show`, `ip -j address show`, `/proc/uptime` ve boot ID okumalarını gerçekleştirir. İki geçerli sayaç gözlemi trafik hızı için gerekir. Donanım port geometrisi bu çıktılardan tahmin edilmez.
   - `Harici toplayıcı`: Mevcut SNMP/NETCONF/üretici toplayıcınızı aşağıdaki envanter/gözlem API'sine bağlayın. Üretici komutları veya desteklenmeyen telemetri varsayılmaz. **Envanter aktar** doğrulanmış JSON dosyasını kabul eder.

**Yenile**, alınmış verileri yeniden okur; cihazı sorguladığı anlamına gelmez. Linux toplama işleri açık kullanıcı eylemiyle başlar; zamanlanmış SNMP/SSH polling servisi bu sürümde yoktur. Harici toplayıcı kendi zamanlamasını yönetir. Tarayıcı her 15 saniyede ortak görünümü sorgular; bileşenler ayrı telemetri istekleri oluşturmaz.

Switch/router üreticilerine özgü sürücüler ve fiziksel cihaz kabulü ayrıca gerekir. Önceki sürümde gerçek konfigürasyon uygulama veya yedekleme akışı bulunmuyordu; bu teslimat bu yetenekleri varmış gibi göstermez. SSH terminali salt okunur komut filtresi uygulamaz: uzak cihaz hesabının yetkileri geçerlidir. En az ayrıcalıklı cihaz hesabı kullanın.

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
docker --context default compose -f docker-compose.yml -f docker-compose.tls.yml up --build -d --wait
```

TLS override; üretim modunu etkinleştirir, PostgreSQL/API host portlarını kaldırır ve yalnız HTTPS gateway portunu yayımlar. API üretimde HTTP'yi ve terminal WS'yi reddeder; cookie `Secure`, `HttpOnly`, `SameSite=Strict` olur. Proxy, istemcinin gönderdiği forwarded başlıklarını kendi değerleriyle değiştirir. API'nin proxy güveni Docker iç ağına dayanır; API'yi doğrudan internete açmayın veya güvenilmeyen container'ları bu ağa katmayın.

Kimlik doğrulama, yerel Argon2id kullanıcıları ve veritabanındaki iptal edilebilir, 8 saatlik opaque oturumlarla yapılır. Değişiklik isteklerinde exact-origin ve CSRF kontrolü vardır. Roller:

| Rol | Envanter | İş başlatma | Terminal | Sır / envanter yönetimi | Denetim |
| --- | --- | --- | --- | --- | --- |
| Gözlemci | İzinli siteler | Hayır | Hayır | Hayır | Hayır |
| Operatör | İzinli siteler | Evet | Evet | Hayır | Hayır |
| Yönetici | İzinli siteler | Evet | Evet | Evet | Yalnız global site yetkisiyle |

```bash
docker --context default compose exec api python -m app.admin create-user --username operator --role operator --site merkez
docker --context default compose exec api python -m app.admin disable-user --username operator
```

Terminal ticket'ı 30 saniye geçerli, tek kullanımlı ve oluşturan oturuma bağlıdır; tek başına bearer token değildir. Hedef host/port tarayıcıdan alınmaz. Kullanıcı başına 3, süreç başına 20 terminal; aynı kullanıcı/cihaz için 1 oturum sınırı vardır. Bağlantı 12 sn, varsayılan boşta kalma 300 sn, toplam oturum 3600 sn; giriş mesajı 16 KiB ve 64 KiB/sn ile sınırlıdır. Süreler `STOCC_SSH_IDLE_SECONDS` / `STOCC_SSH_MAX_SECONDS` backend ortam değişkenleriyle ayarlanabilir. Yetki/oturum iptali en geç izleme döngüsünün yaklaşık 1 saniyelik kontrolünde uygulanır. Bağlantı kurulma aşamasında tekrar doğrulama PTY açılmadan yapılır.

Panel kapanması, sayfadan çıkış, çıkış yapma, kimlik bilgisi değişimi/silinmesi ve host anahtarı değişimi terminali sonlandırır. Uzak PTY boyutu tarayıcı terminaliyle birlikte güncellenir. Terminal çıktısı xterm'e metin olarak iletilir; HTML olarak işlenmez. Denetim kaydı yalnız kullanıcı, cihaz, oturum kimliği, başlangıç/bitiş zamanı ve sonucu içerir; ham terminal, parola, private key veya cookie loglanmaz.

## Sır deposu ve yedekleme

Cihaz parolası/özel anahtar/passphrase hashlenmez; AES-256-GCM ile şifrelenir. Her kayıt güncellemesinde rastgele 12 byte nonce, cihaz kimliği ve key ID içeren AAD kullanılır. Uygulama kullanıcısı parolası ise Argon2id hash'idir. Cihaz okuma API'si sırları döndürmez; tarayıcı sırları kalıcı storage'a veya SWR cache'e yazmaz. Düzenlemede seçili sır alanı boşsa **kayıtlı kimlik bilgilerinin tamamı** korunur; kullanıcı adı/yöntem değişimi yeni sırla birlikte yapılır. Silme ayrı onaylı işlemdir.

Anahtar deposu hazır değilse veya şifre çözme doğrulanamazsa bağlantı reddedilir. Veritabanı yedeği ile anahtar volume'ü yedeğini ayrı, erişimi kısıtlı yerlerde saklayın. Anahtar kaybolursa şifreli cihaz sırları kurtarılamaz. `secrets-init` mevcut anahtar dosyasının üzerine yazmaz.

Kontrollü rotasyon (önce iki deponun korumalı yedeğini alın; rotasyon sırasında kimlik bilgisi yazımlarını durdurun):

```bash
docker --context default compose run --rm secrets-init python -m app.keyring add-key
docker --context default compose exec api python -m app.admin rotate-secrets
```

İlk komut eski anahtarları koruyup yeni aktif anahtar ekler. İkincisi mevcut kayıtları yeni anahtarla tek işlemde yeniden şifreler. API anahtar dosyasını bağlantıda yeniden okur. Eski anahtarları, yedeklerin saklama politikasını ve şifre çözme doğrulamasını tamamlamadan kaldırmayın.

## Veri sözleşmesi ve metrik anlamları

Kaynağın gerçek sözleşmesi [contracts.py](backend/app/contracts.py), [models.py](backend/app/models.py), [telemetry.py](backend/app/telemetry.py) ve çalışan API'nin `/openapi.json` çıktısıdır. Tüm aşağıdaki yollar `/api/v1` öneklidir; oturum cookie'si zorunludur. Mutasyonlarda izinli `Origin` ve `/session/me` yanıtındaki `csrf_token` ile `X-CSRF-Token` gerekir.

| Yol | İşlev |
| --- | --- |
| `POST /session/login`, `GET /session/me`, `POST /session/logout` | Kimlik doğrulama / oturum |
| `GET, POST /devices`, `GET /devices/{id}` | Site kapsamlı envanter |
| `PUT /devices/{id}/inventory` | Fiziksel bileşen, port, arayüz ve explicit eşlemeler |
| `POST /devices/{id}/observations` | Kaynak ve zaman içeren doğrulanmış gözlem |
| `GET /overview?minutes=60` | Ortak cihaz/port/sağlık/topoloji/zaman serisi görünümü |
| `GET /devices/{id}/observations/latest` | Son ham, normalize edilmiş gözlem |
| `PUT, DELETE /devices/{id}/credentials`, `PUT /devices/{id}/host-key` | Sır / güven kaydı yönetimi |
| `POST /devices/{id}/polls`, `POST /devices/{id}/connection-tests`, `GET /jobs` | Kalıcı iş sonucu |
| `POST /devices/{id}/ssh-sessions`, `DELETE /ssh-sessions/{id}` | Terminal yaşam döngüsü |
| `WS /ssh-sessions/{id}/ws` | Kimliği doğrulanmış giriş/çıktı/resize köprüsü |
| `GET /audit` | Sır içermeyen denetim olayları |

Envanter aktarımı tam snapshot'tır: `components`, `physical_ports`, `interfaces`, `bindings`, `source`, zaman dilimli `observed_at`; opsiyonel `serial`, `os_version`. `Interface` mevcut Observation sözleşmesini korur: `admin_up`, `oper_up`, `speed_mbps` alanlarında `value`, `observed_at`, `stale_after_seconds`, `source`, `quality` gerekir. Bilinmeyen değerde `value:null`, `quality:"unknown"` gönderin. Bunlar port geometrisi değil arayüz gözlemleridir. Envanter içindeki fixture kaynağı kabul edilmez.

Telemetride envanterdeki aynı `interface_id` kullanılır; `rx_bps`, `tx_bps`, `capacity_bps` birimi **bit/s**; `in_octets`, `out_octets` birimi **byte**'tır. Sıfır yalnız ölçülen sıfırı ifade eder. Desteklenmeyen arayüz metriği `quality:"unsupported"`; toplama hatası `error`; eksik ölçüm `null` olmalıdır. `health.status` için `ok/warning/critical` verilirse toplayıcının `evaluation` açıklaması zorunludur; uygulama rastgele eşik/puan üretmez.

- Fiziksel ağ portları sayılır; management/console ve VLAN, loopback, port-channel gibi mantıksal arayüzler sayılmaz. Breakout çocukları üst portla birlikte sayılmaz. Fiziksel eşleme bilinmiyorsa port türü/adedini tahmin etmeyin.
- Aktif port oranı = açık ve link-up fiziksel port / tüm fiziksel ağ portları. Bilinmeyenler ayrıca sayılır ve paydada kalır. Tüm portlar bilinmiyorsa oran yoktur. İdari kapalı port arıza sayılmaz; link-up kablo/modül varlığını kanıtlamaz.
- Sayaçtan hız = `8 × byte farkı / saniye farkı`. İlk örnek, reset/taşma, değişmiş `discontinuity` (boot ID gibi), geçersiz/uzun aralık ve bozuk kalite boşluk üretir. Reset/taşma için tahmini düzeltme yapılmaz. Kaynak reboot/sayaç sürekliliği belirtecini sağlamalıdır.
- RX ve TX kapasiteye ayrı bölünür; iki yönün toplamı tek yön kapasitesine bölünmez. Kapasite yoksa yüzde gösterilmez. Trafik, explicit fiziksel eşlemeli ethernet arayüzlerinin gözlenen toplamıdır; benzersiz ağ trafiği değildir. Yalnız mantıksal arayüz envanteri alınan Linux cihazlarında port/kapasite grafiği boş kalması beklenir.
- `stale_after_seconds` kaynak tarafından belirtilir (varsayılan 120 sn). Eski veri/başarısız güncelleme normal sağlık olarak gösterilmez; son bilinen değerlerin zamanı korunur. Envanter ve telemetri tarihleri ayrı gösterilir.
- IP topolojisi atanmış IP'nin alt ağıyla L3 ilişkisidir. L2/fiziksel komşuluk yalnız açık ilişki türü ve `evidence` kaydıyla eklenir. Yönetim IP'si/MAC listesi fiziksel bağlantıya çevrilmez. Mevcut VRF/VLAN açıklaması korunur.
- Grafik ve liste aynı filtre kapsamını kullanır; 20 satırlık sayfalama üst özetleri daraltmaz. Trafik penceresi 5–1440 dakika; cihaz başına son 2880 örnek sınırı aşıldığında ekranda açık uyarı çıkar. Çizimde LTTB görsel örneklemesi, aralık kesintilerinde null boşluklar kullanılır. Ham veriler değiştirilmez. Büyük filo kapasitesi ölçülmüş değildir; benchmark gerekir.

## Geliştirme ve doğrulama

```bash
make backend-install
make backend-test
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
docker --context default compose -f docker-compose.yml -f deploy/compose.qa.yml up --build -d --wait
STOCC_TEST_DATABASE_URL=postgresql+psycopg://stocc:stocc@127.0.0.1:18432/stocc_qa .venv/bin/python backend/tests/seed_browser.py
cd frontend
STOCC_QA=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:13000 npm run test:e2e -- --workers=1
```

Playwright Chromium kurulu değilse `npx playwright install chromium` çalıştırın; mevcut Chrome için `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome` kullanılabilir. Seed yalnız loopback `stocc_qa` veritabanını kabul eder ve dolu envanterin üzerine yazmaz. QA kullanıcı/parolası yalnız `backend/tests/conftest.py` içindeki test fixture'ıdır; üretimde kullanılmaz. SSH test sunucusu üretim imajına kopyalanmaz.

Tarayıcı testleri masaüstü/mobil yerleşim, filtre kapsamı, ECharts, klavye ile port seçimi, form akışı, boş sır alanı, inline SSH giriş/kopyalama/yapıştırma/resize/kapanış ve logout senaryolarını gerçek API/gateway üzerinden denetler. Ayrıca sayfa kimliği, framework hata katmanı, konsol ve cookie güvenlik nitelikleri kontrol edilir. Girişten önceki `/session/me` 401 yanıtı beklenen davranıştır. Ekran görüntüleri işletim sisteminin geçici dizinindeki `stocc-netstudio-qa/` altına, başarısız test izleri `stocc-netstudio-playwright/` altına yazılır; repository'ye eklenmez. Bunlar **sentetik QA envanteridir; fiziksel cihaz kanıtı değildir**.

2026-10-19 doğrulama sonuçları:

| Kontrol | Sonuç / kapsam |
| --- | --- |
| Backend | 35 test geçti; RBAC/site, CSRF, şifreleme/rotasyon, metrikler, gerçek yerel SSH el sıkışması ve Linux toplama işleri |
| Frontend birim testleri | 11 test geçti; filtre kapsamı, bilinmeyen/eski veri, breakout sayımı ve RX/TX anlamları |
| Lint / TypeScript | Geçti |
| Production build | Yerel Next.js ve Docker web/API imajları oluşturuldu |
| HTTP / WS tarayıcı testi | 4 senaryo geçti; gerçek Nginx → API → PostgreSQL / SSH test sunucusu |
| HTTPS / WSS tarayıcı testi | Aynı 4 senaryo geçti; üretim cookie nitelikleri de doğrulandı |
| Görsel / etkileşim | Chrome 1536×1024 ve 390×844; beyaz/koyu gri yüzeyler, dik köşeler, grafik/listenin sırası, mobil taşma, klavye port seçimi, terminal panosu/resize/logout |
| Kalıcılık / dağıtım | Migration `0003`; PostgreSQL/API/gateway yeniden oluşturulunca cihaz kayıtları ve şifreli kimlik bilgileri korundu; anahtar izinleri `0600`, UID/GID `100:101` |
| Bağımlılık audit'i | `npm audit --omit=dev`: 0; geliştirme araçları dahil: 5 yüksek düzey kayıt |

Browser eklentisi bulunmadığı için repository'nin Playwright akışı ve yerel Chrome kullanıldı. HTTPS testi geçici, kendinden imzalı **QA** sertifikasıyla yapıldı; `STOCC_QA_TLS=1` yalnız bu testte tarayıcının sertifika güven hatasını atlar. Sertifika ayrıca `curl --cacert` ile doğrulandı. Gerçek sertifika otoritesi/kurum ağı için üretim kabulü yapılmadı. Giriş öncesi beklenen 401 dışında test edilen ana ekran/terminal akışlarında konsol hatası veya framework hata katmanı kalmadı.

Geliştirme audit'indeki 5 kayıt, ESLint'in `braces` bağımlılık zincirine aittir; üretim frontend bağımlılıklarında bildirilmiş açık yoktur. Test araçları Starlette/httpx ve Vite yapılandırmasına ilişkin geçiş uyarıları üretir; testler başarılıdır. Bu sonuç genel bir güvenlik veya üretim kabul sertifikası değildir. Fiziksel switch üretici uyumluluğu, kurumsal SSO, gerçek sertifika/ağ erişimi, yüksek yük ve yedekten geri dönüş kabulü bu yerel testin dışındadır.

Önceki kapsam ve kararların tarihsel kaydı: [ilk uygulama raporu](stocc-netstudio-uygulama-raporu.md). Güncel çalışma sınırları bu README ve kaynak koddaki sözleşmelerdir.
