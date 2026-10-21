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

## Otomatik ajan kaydı

`network-probe-agent`, ana Compose kurulumu ile otomatik başlar. İlk açılışta yalnız yerel secret volume içindeki bootstrap yetkisini kullanarak kendine kalıcı, hash'lenmiş ajan tokenı oluşturur; token tarayıcıya, loga veya kullanıcıya gösterilmez. Kullanıcı CLI komutu, token dosyası veya Compose profili kullanmaz.

1. Operatör trunk VLAN alt arayüzlerini ve SVI'dan farklı benzersiz probe IP'lerini ağ altyapısında hazırlar.
2. **Ayarlar → Ağ keşfi** sayfasını açın. Yerel ajan arayüzlerini otomatik bildirir; ajana envanterdeki siteyi arayüzden atayın.
3. Güncel switch SVI önerisinden VLAN/VRF, ajan arayüzü, benzersiz kaynak IP ve hedef CIDR'ı onaylayın.

Onaylı kapsam yokken ajan raw socket açmaz veya ARP paketi göndermez. Ajan iptal edilirse aynı kalıcı düğüm kimliği tekrar otomatik kaydolamaz; bu durum bilinçli bir güvenlik sınırıdır.

Üretimde `NETSTUDIO_PROBE_API_URL`, kurulumun HTTPS gateway origin'i olmalıdır. Varsayılan loopback HTTP adresi yalnız geliştirme içindir; üretim API'si bunu reddeder.

## İşletim ve geri dönüş

- Varsayılan tarama aralığı 15 dakikadır ve zamanlama `%10` jitter kullanır.
- Başarılı aktif tarama ilgili kapsamda önceliklidir. Ajan çevrimdışıysa veya başarılı sonuç iki tarama aralığından eskiyse salt-okunur switch ARP gözlemleri yeniden yedek kaynak olur.
- Switch SVI kanıtı veya ajan kaynak arayüzü değişirse kapsam durdurulur ve `Yeniden onay gerekli` görünür.
- Geri dönüş için kapsamı kapatın veya ajanı arayüzden iptal edin. Ajan kapsamı olmadığı sürece paket üretmez; mevcut switch telemetrisi ve veritabanı kayıtları silinmez.

## Ayrıcalı VLAN laboratuvarı

Standart CI raw socket veya host ağı yetkisi istemez. Linux `network namespace`, `veth` ve 802.1Q ile iki VLAN'da gerçek ARP yanıtı ve VLAN'lar arası sızıntı olmadığı ayrı olarak doğrulanabilir:

```bash
sudo backend/tests/network_probe_vlan_lab.sh
```

Betik rastgele adlı geçici ad alanları oluşturur ve başarılı ya da hatalı çıkışta temizler. Bu laboratuvar fiziksel trunk switch kabulünün yerine geçmez.
