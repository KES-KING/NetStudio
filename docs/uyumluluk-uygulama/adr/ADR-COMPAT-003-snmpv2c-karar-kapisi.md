# ADR-COMPAT-003 — SNMPv2c karar kapısı

| Alan | Değer |
|---|---|
| Durum | Kabul edildi — S10 ile uygulandı |
| Karar sahipleri | Güvenlik sahibi; backend transport sahibi |
| Son tarih | S10 Definition of Ready öncesi |
| Blokladığı sprint | S10 |
| Bloklamadığı sprint | S01 |

## Karar

SNMPv2c yalnız SNMPv3 sunmadığı üretici belgesiyle doğrulanan
`mikrotik_swos` profilinde, iki bağımsız açık onayla kabul edilmiştir:

1. Kurulum sahibi API ve worker'da `NETSTUDIO_ALLOW_SNMP_V2C=1` ayarını açar.
2. Superadmin aynı cihaz için şifrelenmemiş protokol, salt-okunur erişim,
   NetStudio kaynak IP ACL'si ve ayrılmış yönetim VLAN/VRF kontrol listesini
   onaylar.

Her iki kapıdan biri kapalıysa backend isteği ve worker toplaması fail-closed
reddeder. SNMPv1, SET, trap alıcısı ve v3 destekleyen profile otomatik v2c
downgrade kapsam dışıdır.

## Uygulama sınırları

- Community `snmp_v2c` protokol kimliğiyle ayrı AES-256-GCM AAD kapsamında
  saklanır; read API, audit detayı, log ve UI'ya geri verilmez.
- Transport yalnız sayısal OID allowlist'i içinde GET, GETNEXT ve GETBULK
  üretir. Kod sözleşmesinde SET operasyonu ve v1 `mpModel=0` yoktur.
- v3 ile aynı request, varbind, satır, byte, deadline ve yanıt süresi bütçeleri
  kullanılır. Scheduler minimum toplama aralıkları ek rate sınırıdır.
- Onay `snmp.v2c.risk_accepted`, geri çekme
  `snmp.v2c.risk_withdrawn` audit olayı üretir. Geri çekme community zarfını
  siler ve bağlantı revizyonunu artırır.
- Feature flag'in kapatılması saklı sırrı okumadan runtime toplamasını durdurur;
  tekrar açma cihaz onayını yeniden üretmez.

## Gerekçe ve kanıt sınırı

MikroTik SwOS dokümanı v1/v2c ile GET, GETNEXT ve GETBULK yanıtlarını; yazma ve
trap desteğinin olmadığını belirtir. NetStudio yalnız v2c istisnasını uygular.
Proje-sentetik CSS610/2.19 fixture'ı ve izole loopback v2c agent testi fiziksel
cihaz ya da production kabulü değildir; profil `experimental` ve
`production_accepted=false` kalır.

## Rollback

Kurulum flag'ini `0` yapmak yeni toplama ve credential yazımını anında kapatır.
Cihaz bazlı geri çekme endpoint'i şifreli community kaydını siler. Kod rollback'i
öncesinde v2c onaylarının API'den geri çekilmesi önerilir; eski sürüm
`snmp_v2c` protokol satırını okuyamaz ve v3 olarak yorumlamaz.

