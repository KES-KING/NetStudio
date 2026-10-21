# VLAN bilinçli aktif ARP probe

NetStudio, switch FDB tablosunda görülen MAC adresleri için IPv4 eşleştirmesini ayrı ve kısıtlı bir probe ajanıyla doğrulayabilir. API ve collector raw socket açmaz. Ajan yalnız yönetici tarafından onaylanan switch SVI ağı içinde ARP gönderir; switch SVI adresini kaynak olarak taklit etmez.

## Güven ve ağ sınırı

- V1 yalnız IPv4 ARP kullanır. IPv6/NDP aktif taraması yoktur.
- Ajan tek siteye kayıtlıdır; veritabanına, Docker socket'e, SSH anahtarlarına veya cihaz parolalarına erişmez.
- Container yalnız `NET_RAW` capability alır. `NET_ADMIN` verilmez; VLAN arayüzlerini ve adreslerini operatör önceden oluşturur.
- Her CIDR `/22` veya daha dardır. Bir görev en fazla 4096 hedefe ve saniyede 64 ARP isteğine izin verir.
- Yalnız görevin güncel FDB izin listesindeki MAC yanıtları API'ye gönderilir. Diğer cihaz kimlikleri saklanmaz; yalnız toplam bilinmeyen yanıt sayısı raporlanır.
- Ajan tokenı `0600` dosyadadır. Üretim API URL'si HTTPS olmalıdır; düz HTTP yalnız açıkça izin verilen localhost geliştirmesinde kabul edilir.

## Host trunk hazırlığı

Örnekte NetStudio hostunun trunk taşıyan fiziksel arayüzü `enp1s0`, VLAN'lar 10 ve 20'dir. Adresler switch SVI adresinden farklı, bu probe'a ayrılmış benzersiz adresler olmalıdır:

```bash
sudo ip link add link enp1s0 name enp1s0.10 type vlan id 10
sudo ip address add 192.0.2.254/24 dev enp1s0.10
sudo ip link set enp1s0.10 up

sudo ip link add link enp1s0 name enp1s0.20 type vlan id 20
sudo ip address add 198.51.100.254/24 dev enp1s0.20
sudo ip link set enp1s0.20 up
```

Bu komutları kalıcı ağ yapılandırmanıza uyarlayın. NetStudio arayüz oluşturmaz ve hostun mevcut yönetim ağını değiştirmez.

## Ajan kaydı

1. **Ayarlar → Ağ keşfi** sayfasında ajan adı ve site için tek kullanımlık kayıt tokenı oluşturun.
2. Yapılandırmayı hazırlayın ve tokenları git dışında tutun:

```bash
cp deploy/network-probe.toml.example deploy/network-probe.toml
install -m 700 -d .secrets
install -m 600 /dev/null .secrets/network-probe.enrollment
# UI'da yalnız bir kez gösterilen tokenı dosyaya yazın; kabuk geçmişine koymayın.
```

3. Kalıcı ajan tokenını üretin. Aşağıdaki komut veritabanı veya raw-socket yetkisi kullanmaz:

```bash
docker run --rm --network host --cap-drop ALL \
  -v "$PWD/deploy/network-probe.toml:/etc/netstudio/network-probe.toml:ro" \
  -v "$PWD/.secrets:/run/secrets:rw" \
  netstudio-api:${IMAGE_TAG:-local} \
  python -m app.network_probe_agent --config /etc/netstudio/network-probe.toml \
  enroll --enrollment-token-file /run/secrets/network-probe.enrollment
rm .secrets/network-probe.enrollment
```

4. Ajanı başlatın:

```bash
docker compose --profile network-probe up -d network-probe-agent
docker compose --profile network-probe logs -f --tail=100 network-probe-agent
```

Heartbeat sonrasında ajan arayüzleri UI'da görünür. Güncel switch SVI önerisinden site/VLAN/VRF, ajan arayüzü, benzersiz kaynak IP ve hedef CIDR onaylanmadan hiçbir ARP paketi gönderilmez.

## İşletim ve geri dönüş

- Varsayılan tarama aralığı 15 dakikadır ve zamanlama `%10` jitter kullanır.
- Başarılı aktif tarama ilgili kapsamda önceliklidir. Ajan çevrimdışıysa veya başarılı sonuç iki tarama aralığından eskiyse salt-okunur switch ARP gözlemleri yeniden yedek kaynak olur.
- Switch SVI kanıtı veya ajan kaynak arayüzü değişirse kapsam durdurulur ve `Yeniden onay gerekli` görünür.
- Geri dönüş için kapsamı kapatın veya ajanı iptal edin, ardından `docker compose --profile network-probe stop network-probe-agent` çalıştırın. Mevcut switch telemetrisi ve veritabanı kayıtları silinmez.

## Ayrıcalı VLAN laboratuvarı

Standart CI raw socket veya host ağı yetkisi istemez. Linux `network namespace`, `veth` ve 802.1Q ile iki VLAN'da gerçek ARP yanıtı ve VLAN'lar arası sızıntı olmadığı ayrı olarak doğrulanabilir:

```bash
sudo backend/tests/network_probe_vlan_lab.sh
```

Betik rastgele adlı geçici ad alanları oluşturur ve başarılı ya da hatalı çıkışta temizler. Bu laboratuvar fiziksel trunk switch kabulünün yerine geçmez.
