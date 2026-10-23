# ADR-COMPAT-004 — Controller/cloud API güven modeli

| Alan | Değer |
|---|---|
| Durum | Önerildi — karar bekliyor |
| Karar sahipleri | Güvenlik sahibi; backend API adaptörü sahibi |
| Son tarih | S08 Definition of Ready öncesi |
| Blokladığı sprint | S08 |
| Bloklamadığı sprint | S01 |

## Mevcut güvenli varsayım

NetStudio henüz controller/cloud API adaptörü uygulamaz. Meraki, UniFi,
FortiLink, Instant On veya Omada gibi yönetim düzlemleri CLI/SSH profiline
zorlanmaz ve kullanıcıdan alınan keyfi URL'lere istek gönderilmez.

## Karar verilmesi gerekenler

- izin verilen ürün ve yönetim modu başına sabit endpoint keşfi,
- TLS zinciri, özel CA, hostname doğrulama ve sertifika pinning yaklaşımı,
- SSRF'e karşı host/IP/redirect/DNS yeniden çözümleme sınırları,
- token kapsamı, secret saklama, rotasyon ve log redaksiyonu,
- tenant/site izolasyonu, rate limit, pagination ve bounded response sınırları,
- vendor API sürüm değişiminde fail-closed davranış ve kabul yenileme koşulları.

Bu karar kabul edilmeden HTTP istemcisi, secret şeması veya controller profili
runtime'da seçilebilir yapılmaz. Ertelenen karar S00/S01'i değil S08'i bloklar.

