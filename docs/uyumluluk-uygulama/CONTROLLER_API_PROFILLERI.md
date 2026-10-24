# Controller/cloud API profil sözleşmesi

Bu belge S08 ile uygulanan controller/cloud yönetim yolunun kullanıcı ve
operatör sözleşmesidir. Kaynak gerçekleri
`backend/app/controller_api.py`, `backend/app/controller_transport.py`,
`backend/app/controller_schema_v1.py` ve katalog revizyonu `2026.10.24.3`'tür.

## Destek tablosu

| Profil | Runtime | Yönetim kanalı | Durum |
|---|---|---|---|
| `cisco_meraki_ms` | `meraki_dashboard` | Sabit bölge origin'li Dashboard API v1 | `experimental`, fixture doğrulandı |
| `fortinet_fortiswitch_fortilink` | `fortinet_fortilink_api` | Kayıtlı FortiGate IP'si üzerinden FortiLink görünümü | `experimental`, fixture doğrulandı |
| `ubiquiti_unifi_switch` | `unifi_api` | Kayıtlı UniFi Network IP'si ve API key | `experimental`, fixture doğrulandı |
| `ubiquiti_unifi_no_snmp` | `unifi_no_snmp_api` | UniFi API; SNMP açıkça desteklenmez | `experimental`, fixture doğrulandı |
| `tplink_omada_managed` | `tplink_omada_api` | Kayıtlı Omada SDN IP'si ve OAuth access token | `experimental`, fixture doğrulandı |
| `tplink_omada_pro` | `tplink_omada_pro_api` | Ayrı Omada Pro controller kaydı/parser kimliği | `experimental`, fixture doğrulandı |
| `ubiquiti_edgeswitch` | `ubiquiti_edgeswitch` | Standalone SSH + SNMPv3 | `experimental`, fixture doğrulandı |
| `aruba_instant_on` | Yok | Belgelenmiş genel API kanıtı yok | `blocked`, seçilemez |

Hiçbir satır fiziksel cihaz, üretici sandbox'ı veya production kabulü değildir.
Omada ve Omada Pro eşit parser/firmware ailesi sayılmaz. EdgeSwitch, UniFi
firmware veya controller profiline yönlendirilmez.

## Kayıt akışı

1. Cihazı kanonik profili ve doğru `management_mode` ile kaydedin.
2. Cihaz detayında **Bağlantı bilgileri → Üretici / controller API** seçin.
3. Controller'ı NetStudio sitesi, dış controller/organization ID'si ve tek bir
   dış site/network ID'siyle kaydedin. Yerel controller için URL değil literal
   IP ve HTTPS portu girin. Özel CA gerekiyorsa yalnız CA sertifikasını PEM
   biçiminde ekleyin; private key reddedilir.
4. Ekranda gösterilen salt okunur yetkilere sahip üretici kimlik bilgisini
   kaydedin: Meraki/FortiGate için bearer token, UniFi için API key,
   Omada/Omada Pro için OAuth access token. NetStudio'nun sakladığı scope listesi
   bir politika beyanıdır; anahtarın üretici tarafında gerçekten en az yetkili
   oluşturulduğunu operatör ayrıca doğrulamalıdır. Token daha sonra okunamaz.
   Son kullanım zamanı biliniyorsa girin.
5. Controller içindeki cihaz ID'si/seri numarasını NetStudio cihazına bağlayın.
   Aynı site, üretici ve dış cihaz kimliği ikinci kayda bağlanamaz; controller
   kaydını yeniden oluşturmak bu tekillik sınırını aşmaz.
6. Otomatik toplamada `Otomatik` veya `Controller API` kaynağını kullanın.

Controller/site/vendor eşleşmesi bozulursa binding reddedilir. Token iptali,
controller ayarı veya binding değişikliği bağlantı revision'ını artırır; daha
önce başlamış işin sonucu yazılamaz.

## Ağ ve TLS işletim koşulları

- API/worker container'ının yalnız gerekli controller IP'leri ve seçilmiş Meraki
  bölge origin'lerine outbound 443 erişimi olmalıdır.
- Yerel sertifika IP SAN içermelidir; özel CA kaydı yalnız o controller istemci
  context'inde kullanılır. Sertifika doğrulamasını kapatan seçenek yoktur.
- HTTP redirect izlenmez. Pagination aynı origin ve aynı endpoint path'i içinde
  kalır. Serbest URL, hostname, proxy ortam değişkeni ve tarayıcıdan endpoint
  override kabul edilmez.
- İstek/yanıt, sayfa, satır, rate-limit ve ortak transport deadline sınırları
  ADR-COMPAT-004'te normatiftir.

## Alan anlamları ve API uçları

- Meraki kimliği organization devices listesinden, port durumu ise 300 saniyelik
  switch port status penceresinden alınır. `trafficInKbps.recv/sent` alanları
  `rx_bps`/`tx_bps` oranlarına çevrilir; kümülatif octet sayacı gibi saklanmaz.
  İstenen salt-okunur kapsamlar `dashboard:general:config:read`,
  `switch:config:read` ve `switch:telemetry:read`'dir.
- UniFi Network uygulamasında cihaz listesi, cihaz detayı ve son cihaz
  istatistiği ayrı `/proxy/network/integration/v1` GET çağrılarıdır. Port
  bağlantısı/kapasitesi ile CPU, bellek ve uptime alınır; bu uçlardan gelmeyen
  kümülatif port sayacı veya seri numarası türetilmez.
- FortiLink yalnız kayıtlı FortiGate üzerindeki yönetilen-switch görünümüdür;
  standalone FortiSwitch parser'ına düşmez.
- Omada ve Omada Pro access tokenının edinilmesi/yenilenmesi bu sprintin dışında
  kalır. Süresi dolmuş token fail-closed olur; üretici sürümüne özgü token
  yaşam döngüsü S11 fiziksel kabulünde kanıtlanmalıdır.

Sentetik corpus `backend/tests/fixtures/s08/manifest.json` içinde SHA-256 ile
sabitlenmiştir. Bu corpus parser, normalize alan ve negatif transport
sözleşmesini sınar; üretici cevabının birebir kaydı değildir.

## Üretici sözleşme kaynakları

- Meraki API başlangıç/auth ve sabit base URL:
  <https://developer.cisco.com/meraki/api-v1/getting-started/>
- Meraki organization devices:
  <https://developer.cisco.com/meraki/api-v1/get-organization-devices/>
- Meraki switch port statuses:
  <https://developer.cisco.com/meraki/api-v1/get-device-switch-ports-statuses/>
- UniFi official API ve local application API ayrımı:
  <https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API>
- UniFi Network API sürüm dokümanı:
  <https://developer.ui.com/network/v9.4.17>
- UniFi device detail sözleşmesi:
  <https://developer.ui.com/network/v9.4.17/getdevicedetails>
- UniFi API key ve salt-okunur rol rehberi:
  <https://developer.ui.com/site-manager/v1.0.0/gettingstarted>
- FortiGate API token rehberi:
  <https://docs.fortinet.com/document/fortigate/latest/administration-guide/940602/using-apis>
- FortiGate managed FortiSwitch controller modeli:
  <https://docs.fortinet.com/document/fortigate/7.6.2/cli-reference/308952696/config-switch-controller-managed-switch>
- Omada SDN Controller 6.2 kullanıcı kılavuzu:
  <https://static.tp-link.com/upload/manual/2026/202604/20260401/1900002482_Omada%20SDN%20Controller_V6.2_User%20Guide.pdf>
- Omada Pro SDN Controller kullanıcı kılavuzu:
  <https://static.tp-link.com/upload/manual/2025/202512/20251208/Omada%20Pro%20SDN%20Controller_User%20Guide_REV1.0.0.pdf>

Üretici endpoint/yanıt değişikliği fixture'ın güncellenmesiyle otomatik kabul
edilmez. Parser ve profil revizyonu, negatif güvenlik testleri ve S11 fiziksel
tuple kabulü yeniden çalıştırılmalıdır.
