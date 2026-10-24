# NetStudio destek yayını — S11 başlangıç durumu

| Alan | Güncel değer |
|---|---|
| Katalog revizyonu | `2026.10.24.6` |
| Yayın tarihi | 24 Ekim 2026 |
| `supported` exact tuple | **Yok** |
| `candidate` exact tuple | **Yok** |
| Fiziksel lab kapsamı | `blocked_no_authorized_targets` |
| 24 saat benchmark | `REQUIRES BENCHMARK` |
| Production kabulü | `false` |

Bu sayfa ürün ailesi adına genel uyumluluk iddiası değildir. Çalışan API'deki
`/api/v1/driver-catalog`, imzalı karar ve geçerlilik durumunu runtime'da yeniden
doğrular. Bu belgeden daha yeni bir karar varsa exact model, donanım revizyonu,
OS sürümü, management mode, transport ve capability kapsamı API'deki
`release_decision` ve cihazın `/compatibility` yanıtıyla birlikte okunmalıdır.

## Güncel yayın sınıfları

| Statik durum | Profil sayısı | Kapsam |
|---|---:|---|
| `implemented / experimental / fixture_verified` | 32 | P0–P4 içinde fixture'ı bulunan SSH/API profilleri |
| `implemented / experimental / unit_verified` | 2 | `cisco_nxos`, `juniper_junos` |
| `implemented / experimental / transport_lab_validated` | 1 | `mikrotik_swos`; fiziksel SwOS kabulü değildir |
| `blocked / hidden / not_tested` | 1 | `aruba_instant_on` |
| `unsupported_by_protocol / hidden / not_tested` | 2 | `tplink_easy_smart`, `unmanaged_switch` |

Tek bir fiziksel tuple kabul edildiğinde profil satırı `candidate` veya
`supported` görünebilir; bu, profil ailesinin bütün modellerini kapsamaz. Cihaz
detayındaki **Uyumluluk → Yayın ve kanıt** alanı exact cihaz tuple'ı kayıtla
eşleşmiyorsa “kabul kapsamı dışında” göstermeye devam eder.

## Destek yükseltme kapısı

- `candidate`: exact fiziksel kimlik+envanter PASS, migration ve tarayıcı E2E
  PASS, lab ve release review.
- `supported`: bildirilen bütün capability grupları ve transporta özgü negatif
  testler PASS, worker/lease/last-good/rollback PASS, dört ayrı review rolü,
  güncel 24 saat benchmark ve sırası atlanmadan tamamlanmış, hata bütçesi içinde
  `canary→pilot→general` rollout.
- `production_accepted`: yukarıdakilerden türetilmez; belirli release ve kurulum
  için ayrıca kabul edilmedikçe daima `false`.

İmzalı `supported` kararı rollout başlamadan veya `general` aşamasına ulaşmadan
dinamik katalogda `candidate` kalır. Karar süresi dolarsa, profil/parser/kaynak
commit değişirse, imza güvenilmiyorsa ya da rollout sıra/hata bütçesi ihlali
olursa seviye fail-closed biçimde `experimental` olur. Önceki kanıt sessizce
uzatılamaz.

## Açık blokajlar

1. [`S11_LAB_SCOPE.json`](S11_LAB_SCOPE.json) içinde yetkili fiziksel hedef yok.
2. Exact model/OS/mode/transport capability kabulü çalıştırılmadı.
3. Cihaz reboot/firmware/credential/host-key/TLS bozulma senaryoları fiziksel
   hedefte çalıştırılmadı.
4. Gerçekçi transport dağılımıyla 24 saat soak ve cihaz CPU/rate-limit ölçümü
   yapılmadı.
5. Canlı canary/pilot/general rollout gözlemi yok.

Bu blokajlar çözülmeden dokümantasyon, sentetik fixture, loopback transport veya
yerel test sonucu `candidate`, `supported` ya da production kabulü üretemez.
