# ADR-COMPAT-001 — Kanonik profil, alias ve durum modeli

| Alan | Değer |
|---|---|
| Durum | Kabul edildi |
| Tarih | 23 Ekim 2026 |
| Sahip | Uyumluluk programı teknik sahibi |
| Uygulama sprinti | S01 |

## Bağlam

Mevcut sistemde `Collector` değeri; kullanıcı seçimini, işletim sistemi ailesini,
taşıma biçimini ve parser seçimini aynı alanda temsil eder. Kaynak uyumluluk
matrisi ise 38 hedef platform profili tanımlar. Ayrıca `auto`, `external` ve
`linux_ssh` değerleri birer NOS profili değildir.

## Karar

1. [`S00_KAPSAM_KARARLARI.json`](../S00_KAPSAM_KARARLARI.json) içindeki 38 kimlik
   kanonik profil kümesidir.
2. `linux_ssh`, genel ve salt-okunur bir altyapı adaptörüdür; `dell_sonic`,
   `nvidia_cumulus_linux` veya `sonic_nos` desteği sayılmaz.
3. `auto` ve `external` seçim/yürütme modudur; profil değildir.
4. Profil durumu birbirinden bağımsız üç eksende tutulur:
   - uygulama: `catalog_only`, `implemented`, `blocked`,
     `unsupported_by_protocol`, `unsupported_by_policy`, `retired`;
   - doğrulama: `not_tested`, `unit_verified`, `fixture_verified`,
     `transport_lab_validated`, `physical_validated`;
   - yayın: `hidden`, `experimental`, `candidate`, `supported`.
5. `supported` yalnız `implemented` + `physical_validated` + profil revizyonuyla
   eşleşen ve süresi dolmamış kabul kaydı birlikte varsa kullanılabilir.
6. Alias tek kanonik hedefe gider, döngü oluşturamaz ve kimlik kanıtı gerektiren
   kayıtlar otomatik yeniden sınıflandırılamaz.
7. Capability bilinmiyorsa `unknown` kalır; model isminden port, transceiver,
   PoE veya özellik tahmini yapılmaz.

## Eski kimlik yaklaşımı

Eski kimliklerin ayrıntılı kararı
[`PROFIL_VE_ALIAS_KARARLARI.md`](../PROFIL_VE_ALIAS_KARARLARI.md) belgesindedir.
`fortinet` belirsiz olduğu için otomatik hedefi yoktur. `huawei_vrp`,
`dell_force10` ve `extreme_vsp` ancak cihaz kimliği doğrulanınca çözülür.

## Sonuçlar

- Katalogda görünmek ile seçilebilir/desteklenir olmak ayrılır.
- S01 registry uygulaması mevcut runtime davranışını değiştirmeden başlayabilir.
- Bu ADR hiçbir yeni parser, migration veya fiziksel destek iddiası oluşturmaz.

## Reddedilen seçenekler

- Bütün matris satırlarını doğrudan `supported` yapmak: kanıt zincirini atlar.
- `linux_ssh` ile Linux tabanlı tüm NOS'ları eşitlemek: switch/ASIC semantiğini
  yanlış temsil eder.
- Belirsiz eski kimlikleri toplu migration ile dönüştürmek: yanlış platform
  seçimi ve veri kaybı riski doğurur.

