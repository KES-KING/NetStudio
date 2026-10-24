# ADR-COMPAT-004 — Controller/cloud API güven modeli

| Alan | Değer |
|---|---|
| Durum | Kabul edildi — S08 ile uygulandı |
| Karar sahipleri | Güvenlik sahibi; backend API adaptörü sahibi |
| Karar tarihi | 24 Ekim 2026 |
| Uygulama | `0011_controller_api`, `controller_api.py`, `controller_transport.py` |
| Blokladığı sprint | Yok; S08 kapısı açıldı |
| Bloklamadığı sprint | S01 |

## Karar

Controller ve cloud API erişimi SSH/SNMP'den ayrı bir transport ve sır türüdür.
Kayıt aşağıdaki fail-closed kurallara uyar:

1. Kullanıcıdan URL veya hostname alınmaz. Meraki origin'i seçilen sabit bölge
   allowlist'inden gelir. Yerel UniFi, FortiGate/FortiLink ve Omada kayıtlarında
   yalnız literal IP + HTTPS portu kabul edilir. Loopback yalnız kurulumun açık
   `NETSTUDIO_CONTROLLER_ALLOWED_CIDRS` izniyle kullanılabilir.
2. HTTPS ve sertifika doğrulaması zorunludur. Sistem CA deposu veya kayıtla
   sınırlı özel CA kullanılabilir; `verify=false` yoktur. Redirect izlenmez.
   Yerel hedefte DNS çözümlemesi yapılmadığı için yeniden bağlama alanı yoktur.
3. Controller kaydı tek bir NetStudio sitesi ve tek bir dış site/network ID'si
   taşır. Device binding aynı siteyi ve profil-vendor eşleşmesini zorunlu tutar;
   aynı site + vendor + dış cihaz kimliği, controller kaydı yeniden oluşturulsa
   bile iki NetStudio cihazına bağlanamaz.
4. API tokenı cihaz SSH ve SNMP sırından ayrı tabloda, controller ID'sine ve
   `api` amacına bağlı AES-256-GCM AAD ile saklanır. Okuma API'sinde geri dönmez,
   audit girdisine veya hata gövdesine eklenmez. Değiştirme ve iptal bağlı cihaz
   connection revision'larını artırır; eski iş sonucu yazamaz.
5. Yalnız kodda tanımlı read scope'lar kabul edilir. Bu metadata uygulama
   politikasıdır; üretici tarafındaki gerçek grant/rolün en az yetkili olduğunu
   operatör doğrulamalıdır. Süresi geçmiş token kayıt sırasında ve transportta
   reddedilir. Meraki ve FortiGate bearer token, UniFi `X-API-Key`, Omada ve
   Omada Pro `AccessToken` kimlik doğrulamasını kullanır. Adapter yalnız sabit
   GET uçlarına gider; mutasyon endpoint'i tanımlı değildir.
6. İstek başına 15 saniye, iş başına ortak deadline, 2 MB yanıt, 8.192 satır,
   20 sayfa ve bir adet en fazla 30 saniyelik `Retry-After` tekrar sınırı vardır.
   Pagination aynı origin ve aynı path dışına çıkamaz; loop fail-closed olur.
7. Üretici yanıtı sürüm değişikliğiyle zorunlu kimlik/port alanlarını kaybederse
   parser başka üreticiye veya SSH profiline düşmez; son doğru veri korunur ve
   capability hata/partial olarak işaretlenir.
8. Dağıtım katmanı, gerekli controller/cloud hedefleri dışında outbound egress'i
   ayrıca kısıtlamalıdır. Uygulama allowlist'i ağ politikası yerine geçmez.

## Ürün bazlı sonuç

- Meraki Dashboard API, UniFi Network API, FortiGate üzerinden FortiLink ve
  Omada/Omada Pro controller yolları deneysel/fixture-doğrulanmış olarak açılır.
- Controller profillerinde debug SSH bir yönetim transportu değildir.
- UniFi Flex/Ultra no-SNMP profili ayrı kalır.
- Aruba Instant On için genel, sürümlenmiş ve bu güven modeline bağlanabilir
  resmi yönetim API sözleşmesi kanıtlanmadığından profil
  `unsupported_by_policy`/`vendor_public_api_unavailable` olarak kapalı kalır.
- Vendor sandbox, mock transport ve proje-sentetik fixture sonuçları
  `physical_validated` veya `production_accepted` değildir.

## Doğrulama ve yeniden karar tetikleyicileri

İzole HTTPS testi doğru/yanlış CA'yı; negatif testler redirect, pagination loop,
yanıt boyutu, bounded 429, scope, expiry/revoke, duplicate cihaz kimliği,
multi-site ve API/SNMP provenance çatışmasını kapsar. Cloud origin listesi,
vendor auth şekli, endpoint path'i, token kapsamı veya TLS politikası değişirse
profil revizyonu ve S11 kabul kaydı yenilenmeden `supported` yapılamaz.

