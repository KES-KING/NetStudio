# S00 başlangıç uyumluluk raporu

| Alan | Snapshot değeri |
|---|---|
| Kaynak revision | `fa1a40f3476e2207599d2b62415d9fc25b423d02` |
| Commit zamanı | `2026-10-23T14:30:46+03:00` |
| Commit konusu | `Refactor update setup process and enhance Docker updater service` |
| Snapshot tarihi | 23 Ekim 2026 |
| Migration head | `0009_probe_auto_enroll` |
| Katalog sürümü | `2026.10.20.3` |
| NTC template sürümü | `9.3.0` |

> Bu belge S00 başlangıç durumunun tarihsel snapshot'ıdır. Güncel runtime destek
> sertifikası değildir. Sonraki kaynak değişiklikleri bu kaydı geriye dönük
> değiştirmez; yeni bir baseline kaydı gerektirir.

## 1. İncelenen kaynakların bütünlük izi

| Kaynak | SHA-256 |
|---|---|
| `backend/app/contracts.py` | `4120e5c1cca47bbb4c982e02d180cd85a32b1b9bc01c8daf6d800f0f7b70ede2` |
| `backend/app/driver_catalog.py` | `11fc0689e1da9ccfe37f9dc685eb4e635d379198c62a34b463ca0b146fffd7f4` |
| `backend/app/drivers.py` | `da029dc5a9e01b6c514ec1455dbabd448c01a15937aa77285a64ae05e414c821` |
| `frontend/components/DeviceForms.tsx` | `39c3ef8e48e5f6e0af819ade1602b5458d070b9aa2242ab15b6b0c28791936a8` |
| `backend/migrations/versions/0009_network_probe_auto_enrollment.py` | `4d556f511bb587f0b98daef23bf04479f4406429c1f6d59bbd064574207e614b` |
| `SECURITY.md` | `71d9e2d94b3d9ae66d0288130cc46dd31308fccd691c598268dd9b0144fcfc96` |
| `docs/collection-automation.md` | `1d39754c7b1bdfeaa851ef0438c79db3266a16d7bb542a26836425fce585bc1f` |

Bu hash'ler değişiklik algılama içindir; bir dosyanın güvenli veya fiziksel olarak
doğrulanmış olduğunu tek başına kanıtlamaz.

## 2. `/driver-catalog` kaynak snapshot'ı

`backend/app/driver_catalog.py`, 16 kayıt üretir: 6 kayıt `available: true`, 10
kayıt `available: false` ve `driver_not_implemented` nedenlidir.

| Kimlik | Available | Mevcut doğrulama etiketi | Komut | Capability alanı | Sınır |
|---|---:|---|---:|---:|---|
| `cisco_ios` | Evet | `fixture_tested` | 14 | 29 | 2960-X/IOS 15.2(7)E temizlenmiş fixture |
| `cisco_iosxe` | Evet | `experimental` | 14 | 29 | IOS planını paylaşır; ayrı fixture yok |
| `huawei_vrp` | Evet | `fixture_tested` | 7 | 21 | S5700/VRP V200 temizlenmiş fixture |
| `juniper_junos` | Evet | `experimental` | 8 | 18 | Sınırlı XML parser |
| `cisco_nxos` | Evet | `experimental` | 6 | 18 | Sınırlı JSON parser |
| `linux_ssh` | Evet | `lab_validated` | 0 | 9 | Genel iproute2 adaptörü; NOS profili değil |

Planlı ve seçilemez kayıtlar:

```text
aruba_aoscx, hp_procurve, hp_comware, arista_eos, mikrotik_routeros,
fortinet, dell_force10, dell_os10, extreme_exos, extreme_vsp
```

Katalog etiketleri yeni S00 üç-eksen durum modeliyle aynı sözlük değildir. S01
uygulaması yapılana kadar mevcut API cevabı davranışın kanonik runtime kaynağıdır.

## 3. `Collector` sözleşmesi snapshot'ı

`backend/app/contracts.py` tam 18 değer kabul eder:

```text
external, auto, linux_ssh, huawei_vrp, cisco_ios, cisco_iosxe,
cisco_nxos, juniper_junos, arista_eos, aruba_aoscx, hp_procurve,
hp_comware, mikrotik_routeros, fortinet, dell_os10, dell_force10,
extreme_exos, extreme_vsp
```

Bu listede bulunmak sürücünün uygulanmış veya seçilebilir olduğunu kanıtlamaz.
`auto` ve `external` profil değil çalışma modudur.

## 4. Frontend snapshot'ı

`frontend/components/DeviceForms.tsx` içinde sekiz seçenek elle yazılmıştır:

```text
auto, external, linux_ssh, huawei_vrp, cisco_ios, cisco_iosxe,
cisco_nxos, juniper_junos
```

Form `/api/v1/ssh-profiles` çağrısını SSH algoritma seçenekleri için kullanır;
sürücü seçeneklerini `/driver-catalog` üzerinden üretmez. Backend literal,
runtime katalog ve frontend seçenekleri bu nedenle üç ayrı değişiklik yüzeyidir.

## 5. Migration ve güvenlik snapshot'ı

- Alembic head `0009_probe_auto_enroll` revizyonudur; dosya
  `0009_network_probe_auto_enrollment.py` içindedir.
- SSH komutları kod içi read-only allowlist ile sınırlıdır; keyfi kullanıcı
  komutu sürücü toplama yoluna verilmez.
- SNMP uygulaması yalnız v3 `authPriv` yolundadır; v1/v2c ve SET politika gereği
  kapalıdır.
- Host-key, site/RBAC, hedef ve legacy SSH kontrolleri mevcut güvenlik sınırıdır.
- Ham cihaz çıktısı ve sırlar log/audit/fixture'a kontrolsüz yazılamaz.

## 6. Başlangıç uyumsuzlukları

| Alan | Snapshot bulgusu | Sonraki kapı |
|---|---|---|
| Kimlik | Katalog 16, `Collector` 18, frontend 8 değer taşır | S01 typed registry |
| Hedef kapsam | Kaynak matris 38 profil, runtime katalog 16 kayıt taşır | S01 katalog v2 |
| Eski ID | Altı kayıt için kanonik/koşullu/manual karar gerekir | S00 kararı, S02 migration |
| Kanıt | Hiçbir profil S00 anlamında `supported` değildir | ADR-COMPAT-005 |
| Provenance | Mevcut sözleşme grup seviyeli last-good kullanır | S02/S04 |
| API/controller | Güven modeli kabul edilmemiştir | ADR-COMPAT-004 / S08 |
| SNMPv2c | Mevcut politikada yasaktır | ADR-COMPAT-003 / S10 |

Bu snapshot yeni bir profile runtime desteği vermez ve mevcut fiziksel/üretim
kabulü bulunduğunu iddia etmez.

