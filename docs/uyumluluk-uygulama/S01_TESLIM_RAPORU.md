# S01 teslim raporu — typed sürücü registry'si ve katalog v2

| Alan | Sonuç |
|---|---|
| Sprint | S01 — Typed sürücü profili registry'si ve katalog v2 |
| Tarih | 23 Ekim 2026 |
| Başlangıç kaynak commit | `c317eab20ce38f67a3bfa2fdea25b0cb89899b3d` |
| Tamamlanan backlog | S01-01–S01-08 |
| Migration/veritabanı etkisi | Yok |
| Kolektör komut/parser davranışı | Değişmedi |
| Yeni cihaz desteği | Yok; metadata yeni runtime desteği sayılmaz |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI; S01 kapsamı değil |
| Production kabulü | `false` |
| Ana tasarım etkisi | yok — additive API, tip ve iç mimari değişikliği |

## 1. İş paketi teslimleri

| ID | Durum | Uygulama/kanıt |
|---|---|---|
| S01-01 | Tamamlandı | [`driver_profiles.py`](../../backend/app/driver_profiles.py): `DriverProfile`, identity, transport, capability, acceptance, alias ve adapter modelleri |
| S01-02 | Tamamlandı | ID/duplicate/alias döngüsü, capability-transport, implemented plan ve supported kabul doğrulaması |
| S01-03 | Tamamlandı | Altı mevcut runtime kaydı ve on eski planned kayıt typed registry'den türetilen facade'ya taşındı |
| S01-04 | Tamamlandı | S00 ile aynı 38 kanonik profil P0–P4 durumlarıyla kod sahipli registry'ye eklendi |
| S01-05 | Tamamlandı | [`driver_catalog.py`](../../backend/app/driver_catalog.py) eski `DRIVERS`, `PLANNED`, `SUPPORTED`, `GROUPS`, `VERSION` ve `catalog()` sözleşmesini koruyan facade oldu |
| S01-06 | Tamamlandı | `/api/v1/driver-catalog` additive `schema_version=2`, profil, alias, identity, transport, capability ve acceptance alanlarını yayımlar |
| S01-07 | Tamamlandı | `fortinet` hedefi tahmin edilmez; `manual_resolution_required` ve null kanonik hedef döner |
| S01-08 | Tamamlandı | Backend JSON snapshot/contract testi, v1 hash regresyonu, frontend v1/v2 tipleri ve unknown-field testi eklendi |

## 2. Katalog sözleşmesi

| Yüzey | Adet/davranış |
|---|---|
| `drivers` | Önceki sırada 6 available + 10 planned; eski alan/değerler korunur |
| `profiles` | 38 kanonik profil |
| `infrastructure_adapters` | 1; `linux_ssh` |
| `aliases` | 6 karar; 5 hedefli, 1 unresolved |
| `unresolved_aliases` | Yalnız `fortinet` |
| `catalog_revision` | `2026.10.23.1` |
| Kolektör/parser `version` | `2026.10.20.3`; davranış değişmediği için artırılmadı |

Eski katalog cevabının sıralanmış normalize JSON SHA-256 değeri
`e5320b2d86f126aacc9605ba68e529dbd3b95644e22baad95c7b37503a3682b1`
olarak kilitlenmiştir. Bu kontrol komut, capability, etiket, validasyon seviyesi
ve 16 legacy kaydın tamamındaki değer sapmasını yakalar.

`profiles` içindeki `available/selectable`, yalnız `implemented` profillerde
`true` olur. `catalog_only`, `blocked` ve `unsupported_by_protocol` kayıtlar false
kalır. Kanonik profil için mevcut yazma kimliği farklıysa
`runtime_selection_id` eski sözleşmeyi açıkça gösterir; persisted kayıt geçişi
S02'ye bırakılmıştır.

## 3. Güvenlik ve kabul invariant'ları

- Runtime manifest veya kullanıcı yüklemeli parser yoktur; registry kod sahipli
  ve review/test kontrollüdür.
- Capability kaynağı ancak ilgili transport `implemented` ise kabul edilir.
- `implemented` profil adapter, runtime ID ve gerçek command planı olmadan
  registry'ye giremez.
- `supported`; `implemented`, `physical_validated` ve en az bir güncel/eşleşen
  fiziksel kabul kaydı olmadan üretilemez.
- `linux_ssh`, Dell SONiC/Cumulus/genel SONiC profile dönüşmez.
- API/controller transportları ADR-COMPAT-004; SNMPv2c ADR-COMPAT-003 karar kapısı
  arkasında `blocked` kalır.

## 4. Geriye uyumluluk ve rollback

- Mevcut collector literal, cihaz payload'ı, veri tabanı ve migration head'i
  değiştirilmedi.
- Eski frontend `drivers` dizisini aynı biçimde okumaya devam eder.
- Yeni frontend tipleri `profiles` bulunmadığında v1 cevabı boş kanonik listeyle
  güvenle işler ve bilinmeyen additive alanları yok sayar.
- `NETSTUDIO_DRIVER_CATALOG_V2=0`, yalnız additive alanları kapatıp önceki v1
  JSON cevabını döndürür. Volume, cihaz, sır veya envanter değiştirmez.

## 5. Doğrulama

| Kontrol | Sonuç |
|---|---|
| Backend tam paket | `233 passed, 2 skipped`; 14 bağımlılık/deprecation uyarısı |
| Frontend unit | 11 dosya / 60 test PASS |
| Frontend lint | PASS |
| Frontend typecheck | PASS |
| Frontend production build | PASS; 12 route üretildi |
| Compose config | PASS; katalog v2 flag'i API ortamında `1` |
| Legacy katalog değer eşitliği | PASS; önceki kaynak `catalog()` cevabıyla birebir eşit |
| JSON/Markdown/whitespace | PASS |

Backend skip'leri opsiyonel ortam testleridir. Uyarılar Starlette/httpx,
AsyncSSH/cryptography legacy FFDH ve Alembic yapılandırma deprecation
uyarılarıdır; bu sprintte yeni test hatası veya gizlenmiş failure yoktur.

## 6. Kalan sınırlar

- S01 yeni profil seçimini cihaz yazma API'sine eklemez; bu S02 kapsamıdır.
- Katalogdaki planned transport, adapter/parser uygulanmış olduğu anlamına gelmez.
- Fiziksel cihaz, gerçek vendor transportu, migration ve production acceptance
  çalıştırılmamıştır.
- Frontend cihaz formunun katalogdan dinamik seçenek üretmesi sonraki API/geçiş
  sprintiyle birlikte yapılmalıdır; mevcut sekiz güvenli seçenek korunmuştur.
