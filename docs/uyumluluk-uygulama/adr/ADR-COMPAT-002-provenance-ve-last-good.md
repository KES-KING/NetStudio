# ADR-COMPAT-002 — Alan bazlı provenance ve last-good semantiği

| Alan | Değer |
|---|---|
| Durum | Kabul edildi |
| Tarih | 23 Ekim 2026 |
| Sahip | Backend veri sözleşmesi sahibi |
| Uygulama sprintleri | S02 ve S04 |

## Bağlam

Mevcut toplama sözleşmesi atomik veri grupları için son doğru sonucu korur.
SSH, SNMP ve gelecekteki API kaynakları aynı alanı sağlayabildiğinde yalnız grup
seviyesinde kaynak belirtmek; yeni bir kısmi/başarısız gözlemin eski doğru veriyi
silmesine veya verinin yanlış kaynağa atfedilmesine yol açabilir.

## Karar

Birleştirilebilen her alan en az şu provenance bilgisini taşımalıdır:

| Alan | Anlam |
|---|---|
| `value` | Normalize edilmiş değer |
| `source` | `ssh`, `snmp`, `api` veya açık başka kaynak |
| `observed_at` | Cihaz verisinin gözlem zamanı |
| `received_at` | NetStudio'nun cevabı alma zamanı |
| `quality` | Tam, kısmi, stale veya geçersiz kalite sonucu |
| `profile_id` | Veriyi yorumlayan kanonik profil |
| `profile_revision` | Kullanılan profil/manifest revizyonu |
| `parser_version` | Parser/mapper sürümü |
| `evidence_kind` | Unit, fixture, lab, physical veya production sınıfı |
| `stale_after_seconds` | Alanın stale sayılma eşiği |
| `reason_code` | Eksik, stale veya reddedilmiş sonuç için kararlı kod |

Toplama denemesinin başlangıç/bitiş zamanı, job/attempt kimliği, hata sınıfı ve
transport özeti alan verisinden ayrı tutulur; raw cihaz cevabı bunlara yazılmaz.

Birleştirme kuralları:

1. Daha yeni fakat başarısız/kısmi deneme son doğru değeri silmez ve gözlem
   zamanını ileri taşımaz.
2. Her alan kendi kaynak ve zaman saatini korur; bir grubun yeni olması bütün
   alanları yeni yapmaz.
3. Yalnız tam ve başarılı, alanın sahipliğini açıkça bilen snapshot artık mevcut
   olmayan değeri temizleyebilir; kısmi sonuç temizleyemez.
4. Sayaç kaynağı, sayaç epoch'u veya süreklilik belirteci değişirse hız hesabı
   sıfırlanır; iki farklı kaynak arasında fark alınmaz.
5. Fiziksel port/slot/transceiver kimliği gözlem yoksa üretilmez; `unknown`
   korunur.

## Geçiş

Mevcut grup-seviyesi last-good davranışı S02/S04 tamamlanana kadar korunur. Yeni
alanlar additive migration ile eklenir. Bu ADR hedef sözleşmeyi dondurur; mevcut
veritabanının bugün alan bazlı provenance sunduğunu iddia etmez.

## Sonuçlar

- Stale ve son doğru veri birbirinden ayırt edilebilir.
- Kaynak önceliği alan bazında ve denetlenebilir olur.
- Schema ve payload boyutu artar; süre sonu ve temizlik politikaları S02'de
  ölçülerek uygulanmalıdır.

