# Stocc NetStudio

Stocc NetStudio, rapordaki ilk dikey dilimin çalışan iskeletidir. Bu teslimat; salt okunur demo fixture'ları, fiziksel port envanteri ile üretilen SVG ön paneli, erişilebilir port detay modalını ve cihaz bağlantı testi için kalıcı iş sınırını kurar.

## Çalışan kapsam

- Next.js + TypeScript web arayüzü (`frontend/`)
- FastAPI + Pydantic backend (`backend/`)
- Generic read-only ve fixture driver sözleşmesi
- Fiziksel bileşen, fiziksel port, mantıksal interface ve port binding ayrımı
- 24+4 ve 48+4 temsili model fixture'ları (`device-models/`)
- Port durumunda `source`, `observed_at`, `freshness` ve `quality` gösterimi
- Cihaz bağlantı testi ve salt okunur poll işlerinin API içinde SSH çalıştırmadan iş kuyruğuna alınması
- PostgreSQL/Alembic job claim metadata'sı ve observation snapshot migration'ı
- Yüksek kapasiteli sayaç oranı hesabı; reset/discontinuity durumlarında güvenli veri boşluğu
- `/session/me`, site kapsamı RBAC kontrolü ve son gözlem API sözleşmesi
- Site kapsamlı RBAC ve fail-closed secret-store interface'i (`backend/app/security.py`)

Demo profili gerçek ağ bağlantısı açmaz; gerçek cihaz desteği veya yazma capability'si iddia etmez.

## Docker ile tüm sistemi çalıştırma

PostgreSQL, Alembic migration, FastAPI ve Next.js servislerinin tamamı Compose içinde çalışır. İlk kurulum ve sonraki güncellemeler için:

```bash
cp .env.example .env
# Paylaşılan/üretim benzeri ortamda .env içindeki parolayı ve bind adreslerini değiştirin.
make docker-up
```

`docker-up`; imajları üretir, PostgreSQL sağlık kontrolünü bekler, migration'ı tek seferlik çalıştırır, ardından API ve web servislerini sağlık sırasıyla açar. Hazır olduğunda:

- Web: `http://127.0.0.1:3000`
- API sağlık: `http://127.0.0.1:8000/readyz`
- OpenAPI: `http://127.0.0.1:8000/docs`

Durum ve loglar:

```bash
make docker-ps
make docker-logs
make docker-down
```

`make docker-down` container ve ağları kaldırır, `stocc-postgres` volume'ünü korur. Veri kaybını önlemek için normal durdurma/güncelleme akışında `down -v` kullanılmamalıdır.

### Container mimarisi

```text
Tarayıcı :3000
    │
    ▼
Next.js web ── /api/* ──► FastAPI api :8000 ──► PostgreSQL :5432
                              ▲                    ▲
                              │                    │
                         readyz kontrolü      Alembic migrate
```

Tarayıcı API'ye aynı origin üzerinden erişir; Next.js sunucu geçidi isteği Docker iç ağındaki `api` servisine iletir. PostgreSQL ayrı bir iç ağa alınmıştır. Host portları varsayılan olarak yalnızca `127.0.0.1` üzerinde dinler. Uzak erişim gerekiyorsa `.env` içinde örneğin `WEB_BIND_ADDRESS=0.0.0.0` seçilebilir ve ağ güvenlik politikası ayrıca uygulanmalıdır.

`.env.example` geliştirme varsayılanları içerir. `POSTGRES_*` değerleri değiştirildiğinde `DATABASE_URL` de aynı kullanıcı, parola ve veritabanıyla güncellenmelidir. Gerçek ortamda örnek parola kullanılmamalıdır.

## Geliştirme

```bash
# backend
make backend-install
make postgres-up
make backend-migrate
make backend-run

# web (ayrı terminal)
cd frontend
npm install
npm run dev
```

`make` hedefleri komutları doğrudan `.venv/bin` altından çalıştırır; sistem geneline `alembic` veya `uvicorn` kurulması gerekmez. Bu makinede Docker Desktop bağlamı yerine çalışan sistem engine'i kullanılır. Başka bir Docker bağlamı gerekiyorsa `DOCKER_CONTEXT=desktop-linux make postgres-up` biçiminde değiştirilebilir.

PostgreSQL olmadan yalnızca fixture/bellek profiliyle çalıştırmak için:

```bash
make backend-install
make backend-run
```

Frontend `http://localhost:3000`, API `http://localhost:8000` adresindedir. Varsayılan tarayıcı çağrıları aynı-origin `/api` geçidini kullanır; ayrı bir API origin'i gerekiyorsa build sırasında `NEXT_PUBLIC_API_URL` verilebilir.

## Testler

```bash
make backend-test
cd frontend && npm test
cd frontend && npm run test:e2e
```

Playwright testi gerçek cihazla konuşmaz; fixture ön panelinin 28 fiziksel portu ve port detay akışını doğrular.

## Uygulanan gereksinimler

İlk geliştirme talimatının 1–10 maddeleri için başlangıç kodu; FR-001, FR-002'in secret interface sınırı, FR-003/004/005'in demo gözlem görünümü ve ADR-003/004/005/006/009/012.

## Bilinçli eksikler

Gerçek SNMP/SSH polling transport'u, harici kullanıcı sağlayıcısı, şifreli secret backend'i, topoloji keşfi, metrik deposu, yedekleme ve cihaz üzerinde yazma akışı sonraki dikey dilimlerdir. PostgreSQL repository adapter'ı ve migration'lar hazırdır; `DATABASE_URL` verilmediğinde güvenli bellek repository'si kullanılır. Bu nedenle demo verisi `fixture` kaynağı olarak etiketlenir ve tüm değişiklik kontrolleri kapalıdır.
