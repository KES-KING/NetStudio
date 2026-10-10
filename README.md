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

## Geliştirme

```bash
# backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e backend
uvicorn app.main:app --reload --app-dir backend

# web (ayrı terminal)
cd frontend
npm install
npm run dev
```

İsteğe bağlı PostgreSQL:

```bash
docker compose up -d postgres
alembic -c backend/alembic.ini upgrade head
```

Frontend `http://localhost:3000`, API `http://localhost:8000` adresindedir. `NEXT_PUBLIC_API_URL` ile API adresi değiştirilebilir.

## Testler

```bash
pytest backend/tests
cd frontend && npm test
cd frontend && npm run test:e2e
```

Playwright testi gerçek cihazla konuşmaz; fixture ön panelinin 28 fiziksel portu ve port detay akışını doğrular.

## Uygulanan gereksinimler

İlk geliştirme talimatının 1–10 maddeleri için başlangıç kodu; FR-001, FR-002'in secret interface sınırı, FR-003/004/005'in demo gözlem görünümü ve ADR-003/004/005/006/009/012.

## Bilinçli eksikler

Gerçek SNMP/SSH polling transport'u, harici kullanıcı sağlayıcısı, şifreli secret backend'i, topoloji keşfi, metrik deposu, yedekleme ve cihaz üzerinde yazma akışı sonraki dikey dilimlerdir. PostgreSQL repository adapter'ı ve migration'lar hazırdır; `DATABASE_URL` verilmediğinde güvenli bellek repository'si kullanılır. Bu nedenle demo verisi `fixture` kaynağı olarak etiketlenir ve tüm değişiklik kontrolleri kapalıdır.
