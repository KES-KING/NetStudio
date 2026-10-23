# ADR-COMPAT-006 — Kod sahipli sürücü manifesti

| Alan | Değer |
|---|---|
| Durum | Kabul edildi |
| Tarih | 23 Ekim 2026 |
| Sahip | Backend sürücü registry sahibi |
| Uygulama sprinti | S01 |

## Bağlam

Profil manifestleri komut allowlist'ini, parser seçimini, capability kapsamını ve
güvenlik sınırlarını belirleyecektir. Runtime'da yüklenen imzasız bir manifest bu
sınırları kod incelemesi dışında değiştirebilir.

## Karar

1. İlk sürüm manifestleri repository içinde, typed ve kod sahipli olacaktır.
2. Değişiklikler normal code review, schema validation, unit/fixture testleri ve
   kabul kapılarından geçecektir.
3. `/driver-catalog` bu registry'den türetilir; ayrı elle yazılmış destek kaynağı
   tutulmaz.
4. Kullanıcı kanonik profil seçebilir; keyfi komut, parser modülü, template veya
   manifest yükleyemez.
5. Runtime plugin, uzaktan manifest, imzasız parser/template ve otomatik vendor
   bundle indirme yasaktır.
6. Harici/signed bundle gereksinimi doğarsa imza kökü, revocation, anti-rollback,
   sandbox ve sürüm uyumluluğu ayrı bir ADR ile kabul edilmeden uygulanmaz.

## Sonuçlar

- S01 daha küçük ve denetlenebilir bir saldırı yüzeyiyle uygulanır.
- Yeni profil eklemek kod yayını gerektirir; bu bilinçli güvenlik/mülkiyet
  tercihidir.
- Bu karar mevcut statik kataloğu yeni registry olarak kabul etmez; dönüşüm S01
  kapsamındadır.

