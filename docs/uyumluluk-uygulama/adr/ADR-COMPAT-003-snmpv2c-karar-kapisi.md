# ADR-COMPAT-003 — SNMPv2c karar kapısı

| Alan | Değer |
|---|---|
| Durum | Önerildi — karar bekliyor |
| Karar sahipleri | Güvenlik sahibi; backend transport sahibi |
| Son tarih | S10 Definition of Ready öncesi |
| Blokladığı sprint | S10 |
| Bloklamadığı sprint | S01 |

## Mevcut güvenli varsayım

Karar kabul edilene kadar NetStudio'nun mevcut politikası değişmez: SNMPv1 ve
SNMPv2c desteklenmez; SNMP SET yapılmaz; uygulanmış yol yalnız SNMPv3 `authPriv`
ve kayıtlı hedef için sınırlandırılmış okumadır.

## Karar verilmesi gerekenler

- v2c için açık kurulum ve cihaz bazlı risk onayı gerekip gerekmeyeceği,
- community sırrının saklama, rotasyon ve redaksiyon modeli,
- güvenilmeyen ağ, timeout, istek/satır bütçesi ve rate limit sınırları,
- audit olayları ve UI'da kalıcı risk göstergesi,
- rollback ve eski kimlik bilgisi temizleme koşulları.

Bu maddeler onaylanmadan v2c formu, secret alanı, worker yolu veya migration
eklenmez. Ertelenen karar S00/S01'i değil yalnız S10'un v2c işlerini bloklar.

