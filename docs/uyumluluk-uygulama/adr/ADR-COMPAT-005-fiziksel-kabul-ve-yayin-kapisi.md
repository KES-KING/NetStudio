# ADR-COMPAT-005 — Fiziksel kabul, kanıt ömrü ve yayın kapısı

| Alan | Değer |
|---|---|
| Durum | Kabul edildi |
| Tarih | 23 Ekim 2026 |
| Sahip | Sürüm ve uyumluluk kabul sahipleri |
| Uygulama alanı | Bütün profil ve capability yayınları |
| Uygulama | S11 ile `release_acceptance.py`, `release_cli.py`, `0012_release_acceptance` |

## Karar

Fiziksel kabul kaydı en az şu tuple ile bağlanır:

```text
profile_id + profile_revision + vendor + model + hardware_revision
+ os_family + os_version + management_mode + transport
+ capability + parser_version + evidence_hash + observed_at
```

Firmware aralığı ancak test edilen alt/üst sınırlar ve aradaki semantik eşdeğerlik
kanıtlandıysa kullanılabilir; aksi halde kesin sürüm kaydedilir. Bilinmeyen model,
hardware revision veya özellik kapsamı genişletilmez.

## Kanıt geçerliliği

| Kanıt | Azami takvim ömrü | Daha erken geçersiz kılan değişiklik |
|---|---:|---|
| Unit/fixture | Takvim süresi yok | Profil, parser, template veya beklenen çıktı değişimi |
| Transport laboratuvarı | 180 gün | Transport bağımlılığı veya güvenlik politikası değişimi |
| Fiziksel cihaz | 180 gün | Profil/model/OS/mode/transport/parser kapsam değişimi |
| Benchmark | 90 gün | Runtime, kaynak limiti, topoloji veya yük şekli değişimi |
| Production kabulü | Sürüm ve kurulum özel | Sürüm, ortam veya güvenlik sınırı değişimi |

Süresi dolan kanıt sessizce uzatılamaz. İlgili capability `supported` kapısını
kaybeder; gerekiyorsa `candidate`/`experimental` seviyesine düşürülür ve UI/API
bu durumu açıkça gösterir.

## Yayın kapısı

`supported` yayın durumu için şu koşulların tümü zorunludur:

1. Uygulama durumu `implemented` olmalıdır.
2. Doğrulama `physical_validated` olmalıdır.
3. Yukarıdaki tuple ile mevcut profil/parser revizyonuna uyan, süresi dolmamış ve
   incelenmiş kabul kaydı bulunmalıdır.
4. Fixture/lab kanıtı fiziksel doğrulama yerine kullanılamaz.
5. `production_accepted` ayrı, sürüm+kurulum özel bir kapıdır; varsayılanı
   `false` olur ve fiziksel kabulden türetilmez.
6. Karar güvenilen Ed25519 anahtarıyla offline imzalanır; çalışan build SHA,
   katalog, profil ve parser revizyonu runtime'da yeniden doğrulanır.
7. `supported` için veri/sır silmeyen rollback kanıtı ve süresi dolmamış gerçek
   24 saat benchmark zorunludur.
8. Rollout hata bütçesi ihlali yayın seviyesini fail-closed düşürür ve aynı karar
   altındaki sonraki sağlıklı örnek ihlali temizlemez.
9. İmzalı `supported` kararı, sıralı ve sağlıklı `canary→pilot→general`
   gözlemleri tamamlanana kadar runtime kataloğunda `candidate` kalır.

Her kabul kaydı kanıt türü, test sonucu, redakte artifact hash'i, inceleyenler,
istisnalar ve geçerlilik bitişini içerir. Ham cihaz çıktısı public repository'ye
konmaz.

## Uygulama sonucu

S11 yayın kapısı kaynak kodda uygulanmıştır. Public trust-root ayrı kalıcı
volume'de tutulur ve API tarafından salt okunur açılır; private imza anahtarı
runtime'a girmez. Karar/import HTTP yüzeyi yoktur. İmzalı withdrawal önceki
kararın sonuna kadar etkili olur; expiry, commit/profil/parser değişimi ve payload
tamperi desteği otomatik düşürür.

24 Ekim 2026 itibarıyla yetkili fiziksel hedef ve gerçek 24 saat benchmark
sağlanmadığından aktif `candidate/supported` kararı yoktur. Bu uygulama sonucu
tek başına fiziksel veya production kabulü değildir.

## Sonuçlar

- Tek model/firmware kanıtı bütün ürün ailesine yayılmaz.
- Profil veya parser değişiminde eski kanıt yanlışlıkla geçerli kalmaz.
- Üretim kabulü yalnız kaynak/fixture testinden çıkarılamaz.

