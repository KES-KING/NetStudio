# Uyumluluk karar kayıtları

Bu dizin, NetStudio uyumluluk programının mimari ve güvenlik kararlarını tutar.
Bir ADR'nin kabul edilmesi tek başına runtime desteği veya fiziksel cihaz kabulü
anlamına gelmez; uygulama ve kanıt kapıları ayrıca geçilmelidir.

| ADR | Konu | Durum | İlgili kapı |
|---|---|---|---|
| [ADR-COMPAT-001](ADR-COMPAT-001-kanonik-profil-ve-durum-modeli.md) | Kanonik profil, alias ve durum modeli | Kabul edildi | S01 |
| [ADR-COMPAT-002](ADR-COMPAT-002-provenance-ve-last-good.md) | Alan bazlı provenance ve last-good | Kabul edildi | S02/S04 |
| [ADR-COMPAT-003](ADR-COMPAT-003-snmpv2c-karar-kapisi.md) | SNMPv2c risk ve opt-in modeli | Kabul edildi; S10 ile uygulandı | Kurulum + superadmin cihaz onayı |
| [ADR-COMPAT-004](ADR-COMPAT-004-controller-api-guven-modeli.md) | Controller/cloud API güven modeli | Kabul edildi; S08 ile uygulandı | URL'siz hedef, TLS, read-only scope, site ve secret sınırı |
| [ADR-COMPAT-005](ADR-COMPAT-005-fiziksel-kabul-ve-yayin-kapisi.md) | Fiziksel kabul ve yayın kapısı | Kabul edildi | Bütün yayınlar |
| [ADR-COMPAT-006](ADR-COMPAT-006-kod-sahipli-manifest.md) | Manifest sahipliği | Kabul edildi | S01 |

Makinece doğrulanabilir S00 kapsamı
[`S00_KAPSAM_KARARLARI.json`](../S00_KAPSAM_KARARLARI.json) dosyasındadır.

