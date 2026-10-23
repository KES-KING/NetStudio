# NetStudio uyumluluk uygulama paketi

Bu klasör, [`NetStudio_Switch_OS_SSH_SNMP_Uyumluluk_Matrisi.md`](../NetStudio_Switch_OS_SSH_SNMP_Uyumluluk_Matrisi.md)
belgesindeki platformları mevcut NetStudio kaynak koduna uyarlamak için uygulanabilir
teknik planı içerir. Belgeler 23 Ekim 2026 tarihinde başlayan `fa1a40f` kaynak tabanı
incelenerek hazırlanmıştır.

> Bu paket bir destek sertifikası veya tamamlanmış sürücü listesi değildir. Bir
> platformun üretici tarafında SSH/SNMP sunması, NetStudio sürücüsünün uygulanmış ya
> da fiziksel cihazda kabul edilmiş olduğu anlamına gelmez. Güncel çalışan sözleşme
> her zaman kaynak kod, `/api/v1/driver-catalog` ve
> [`collection-automation.md`](../collection-automation.md) ile birlikte okunmalıdır.

## Okuma sırası

1. [S02 teslim raporu](S02_TESLIM_RAPORU.md) — additive veri modeli, güvenli
   profil çözümü, API/RBAC, migration ve rollback kanıtı.
2. [S01 teslim raporu](S01_TESLIM_RAPORU.md) — typed registry, additive katalog
   v2, geriye uyumluluk ve test kanıtı.
3. [S00 teslim raporu](S00_TESLIM_RAPORU.md) — dondurulan kapsam, kabul edilen
   kararlar, açık karar kapıları ve doğrulama sonucu.
4. [Başlangıç uyumluluk raporu](BASLANGIC_UYUMLULUK_RAPORU.md) — katalog,
   sözleşme, frontend ve migration kaynak snapshot'ı.
5. [Profil ve alias kararları](PROFIL_VE_ALIAS_KARARLARI.md) ve
   [makinece doğrulanabilir S00 kaydı](S00_KAPSAM_KARARLARI.json) — 38 kanonik
   profil, altyapı adaptörleri ve eski kimlik davranışı.
6. [ADR dizini](adr/README.md) — kabul edilen ve bekleyen mimari/güvenlik
   kararları.
7. [Fixture ve kanıt politikası](FIXTURE_VE_KANIT_POLITIKASI.md) — fixture
   temizleme, ham kanıt, inceleme ve secret tarama kapısı.
8. [Implementasyon raporu](IMPLEMENTASYON_RAPORU.md) — mevcut durum, boşluklar,
   hedef mimari, veri/API/UI sözleşmeleri, güvenlik, migration ve yayın yaklaşımı.
9. [Sprint planı](SPRINT_PLANI.md) — bağımlılık sıralı sprintler, iş paketleri,
   testler, kabul kapıları ve teslim kanıtları.
10. [Sürücü izlenebilirlik matrisi](SURUCU_IZLENEBILIRLIK_MATRISI.md) — kaynak
   matristeki her hedef sürücü kimliğinin mevcut karşılığı, hedef sprinti ve kabul
   gereksinimi.
11. [Kabul ve kanıt şablonu](KABUL_VE_KANIT_SABLONU.md) — fixture, taşıma
   laboratuvarı, fiziksel cihaz ve performans kabulünde doldurulacak kayıt.

## Belge statüleri

| Belge | Statü | Kod uygulanmış mı? |
|---|---|---|
| S02 teslim raporu | Uygulanmış additive binding/capability/acceptance modeli ve API geçişi | Evet; yeni parser/fiziksel destek eklemez |
| S01 teslim raporu | Uygulanmış typed registry ve katalog v2 | Evet; yeni cihaz parser'ı/desteği eklemez |
| S00 teslimi, kapsam JSON'u ve ADR'lar | S00 yönetişim kararı | Hayır; runtime desteği eklemez |
| Başlangıç uyumluluk raporu | `fa1a40f` tarihsel snapshot | Hayır; mevcut kaynak gerçeğini kaydeder |
| Fixture ve kanıt politikası | Kabul edilmiş katkı kapısı | Hayır; yeni kanıtların review koşuludur |
| Implementasyon raporu | Hedef tasarım | Hayır; mevcut ve önerilen yapılar ayrı işaretlenmiştir |
| Sprint planı | Uygulanabilir backlog | Hayır; her sprint kendi çıkış kapısını geçmelidir |
| Sürücü izlenebilirlik matrisi | Kapsam ve bağımlılık kaydı | Yalnız “mevcut” sütununda kaynak kod kanıtı vardır |
| Kabul ve kanıt şablonu | Test/inceleme sözleşmesi | Şablonun doldurulması tek başına kabul değildir |

## Normatif öncelik

Çelişki halinde sıralama şöyledir:

1. [`SECURITY.md`](../../SECURITY.md), [`rule.md`](../../rule.md) ve çalışan kaynak
   kodun güvenlik sınırları,
2. migration ve API sözleşmeleri,
3. [`collection-automation.md`](../collection-automation.md),
4. bu klasördeki hedef tasarım,
5. üretici kabiliyetlerini kataloglayan kaynak uyumluluk matrisi.

Matristeki “Evet” ifadesi üretici protokol kabiliyetidir; NetStudio üretim desteği
değildir. Bu klasörde “tam uyumluluk” şu anlama gelir: matristeki her satırın
uygulanmış, açıkça koşullu, güvenlik politikasıyla reddedilmiş veya protokol
kapsamı dışında olarak izlenmesi ve desteklenen her yeteneğin kanıtlı kabul
kapısından geçmesi. Bütün model ve firmware kombinasyonlarını koşulsuz destekleme
iddiası değildir.

## Değişiklik yönetimi

- Yeni sürücü/özellik, izlenebilirlik matrisindeki satır ve ilgili sprint kabul
  kriteri güncellenmeden `supported` ilan edilmez.
- Fixture veya simülatör sonucu `physical_validated` ya da `production_accepted`
  yapılmaz.
- Fiziksel cihaz çıktısı public repository'ye ham biçimde konmaz;
  [`FIXTURE_VE_KANIT_POLITIKASI.md`](FIXTURE_VE_KANIT_POLITIKASI.md) uygulanır.
- Süre ve kapasite hedefleri gerçek ölçüm olmadan tahmin edilmez. Bu belgelerdeki
  ölçülmemiş performans işleri `REQUIRES BENCHMARK`, takvim/ekip büyüklüğü ise
  `REQUIRES ESTIMATION` durumundadır.
