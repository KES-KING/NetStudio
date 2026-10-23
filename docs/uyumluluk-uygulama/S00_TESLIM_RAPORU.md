# S00 teslim raporu — kapsam, kararlar ve kanıt politikası

| Alan | Sonuç |
|---|---|
| Sprint | S00 — Kapsam dondurma, karar kayıtları ve kanıt politikası |
| Tarih | 23 Ekim 2026 |
| İncelenen kaynak commit | `fa1a40f3476e2207599d2b62415d9fc25b423d02` |
| Tamamlanan backlog | S00-01–S00-08 |
| Runtime/parser/migration etkisi | Yok |
| Yeni profil desteği | Yok |
| Fiziksel cihaz kanıtı | ÇALIŞTIRILMADI; S00 kapsamı değil |
| Production kabulü | `false` |
| Benchmark | REQUIRES BENCHMARK; S00 kapasite iddiası yapmaz |
| Ana tasarım etkisi | yok — dokümantasyon ve yönetişim testi |

## 1. İş paketi teslimleri

| ID | Durum | Teslim ve kanıt |
|---|---|---|
| S00-01 | Tamamlandı | [`BASLANGIC_UYUMLULUK_RAPORU.md`](BASLANGIC_UYUMLULUK_RAPORU.md): katalog 16/6/10, `Collector` 18, frontend 8, migration head ve kaynak hash'leri |
| S00-02 | Tamamlandı | [`PROFIL_VE_ALIAS_KARARLARI.md`](PROFIL_VE_ALIAS_KARARLARI.md): 38 kanonik profil, `linux_ssh` altyapı adaptörü ve seçim modları |
| S00-03 | Tamamlandı | [ADR-COMPAT-001](adr/ADR-COMPAT-001-kanonik-profil-ve-durum-modeli.md): uygulama, doğrulama ve yayın durum sözlükleri |
| S00-04 | Tamamlandı | [ADR-COMPAT-002](adr/ADR-COMPAT-002-provenance-ve-last-good.md): alan bazlı provenance ve last-good kuralları |
| S00-05 | Tamamlandı | [ADR-COMPAT-005](adr/ADR-COMPAT-005-fiziksel-kabul-ve-yayin-kapisi.md): kabul tuple'ı, kanıt ömrü ve release kapısı |
| S00-06 | Tamamlandı | [ADR-COMPAT-006](adr/ADR-COMPAT-006-kod-sahipli-manifest.md): ilk sürüm için kod sahipli manifest kararı |
| S00-07 | Tamamlandı | [`FIXTURE_VE_KANIT_POLITIKASI.md`](FIXTURE_VE_KANIT_POLITIKASI.md): temizleme, ham kanıt, secret scan ve iki inceleyen kapısı |
| S00-08 | Tamamlandı | [`PROFIL_VE_ALIAS_KARARLARI.md`](PROFIL_VE_ALIAS_KARARLARI.md): legacy ID'ler için otomatik/koşullu/manual karar |

Kapsamın makinece doğrulanabilir normatif kaydı
[`S00_KAPSAM_KARARLARI.json`](S00_KAPSAM_KARARLARI.json) dosyasıdır. Bu JSON'un
belge türü özellikle `s00_governance_scope_not_runtime_manifest` olarak
işaretlenmiştir; S01 registry'si yerine kullanılamaz.

## 2. Çıkış kapısı

| Kriter | Sonuç | Açıklama |
|---|---|---|
| ADR 001 kabulü | PASS | Profil/alias ve üç eksenli durum modeli donduruldu |
| ADR 002 kabulü | PASS | Provenance/last-good semantiği donduruldu |
| ADR 005 kabulü | PASS | Fiziksel kabul ve `supported` invariant'ı donduruldu |
| ADR 006 kabulü | PASS | Kod sahipli manifest seçildi |
| 38 profil sınıflandırması | PASS | Kaynak matris ve izlenebilirlik matrisiyle tam küme eşitliği test edildi |
| Alias güvenliği | PASS | Tek hedef, döngüsüz grafik ve belirsiz Fortinet manual çözümü test edildi |
| SNMPv2c karar sahibi/son tarihi | PASS | Güvenlik + backend transport sahibi; S10 DoR öncesi |
| Controller API karar sahibi/son tarihi | PASS | Güvenlik + backend API adaptörü sahibi; S08 DoR öncesi |

[ADR-COMPAT-003](adr/ADR-COMPAT-003-snmpv2c-karar-kapisi.md) ve
[ADR-COMPAT-004](adr/ADR-COMPAT-004-controller-api-guven-modeli.md) bilinçli
olarak “karar bekliyor” durumundadır. İlki S10'u, ikincisi S08'i bloklar; ikisi de
S01 typed registry çalışmasını bloklamaz. Karar verilene kadar mevcut güvenli
varsayım korunur: SNMPv2c açılmaz ve controller/cloud API runtime yolu eklenmez.

## 3. Otomatik doğrulama

| Kontrol | Komut/sonuç |
|---|---|
| Kapsam, ADR ve relative link testi | `.venv/bin/pytest -q backend/tests/test_compatibility_governance.py` → **6 passed**, 1 bağımlılık deprecation uyarısı |
| JSON sözdizimi | `.venv/bin/python -m json.tool docs/uyumluluk-uygulama/S00_KAPSAM_KARARLARI.json` → PASS |
| Relative Markdown bağlantıları | Yerel link denetimi → PASS |
| Whitespace/patch kontrolü | `git diff --check` → PASS |

Yönetişim testi şunları fail-closed doğrular:

- kaynak matris, izlenebilirlik belgesi ve S00 JSON'unda aynı 38 tekil profil,
- bütün durumların kabul edilmiş sözlüklerde bulunması,
- kabul kaydı olmadan hiçbir kaydın `supported` olamaması,
- alias hedeflerinin kanonik olması ve döngü oluşturmaması,
- dört kabul edilmiş ADR'nin ve iki bekleyen kararın durum/sahip/son tarihleri,
- `linux_ssh` değerinin NOS profili değil altyapı adaptörü kalması.

## 4. Kalan işler ve açık sınırlar

- S01 typed registry, katalog v2 ve mevcut katalog facade'sını uygulayacaktır.
- S02 additive migration ve koşullu/manual legacy çözümünü uygulayacaktır.
- ADR-COMPAT-002'nin alan bazlı veri modeli S02/S04'te kodlanacaktır.
- S08 başlamadan ADR-COMPAT-004; S10 başlamadan ADR-COMPAT-003 sonuçlanmalıdır.
- Mevcut fixture'lar yeni politikaya göre geriye dönük kabul edilmiş sayılmaz;
  yeni destek iddiasında yeniden denetlenir.
- Fiziksel cihaz, gerçek transport, migration, frontend veya production kabulü
  S00 kapsamında çalıştırılmamıştır.
