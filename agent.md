# Yapay zekâ ajanı çalışma yönergesi

Bu dosya NetStudio üzerinde çalışan kodlama ajanları içindir. İnsanlar ve ajanlar için ortak kuralların esas kaynağı [rule.md](rule.md) dosyasıdır; bu yönerge onları uygulama sırasına dönüştürür. Kök [AGENTS.md](AGENTS.md), ajanların bu iki dosyayı bulabilmesi için giriş noktasıdır.

## Başlamadan önce

1. `rule.md`, `CONTRIBUTING.md`, `SECURITY.md` ve çalışılacak dizinlerde varsa ek `AGENTS.md` talimatlarını okuyun.
2. `git status --short` ile mevcut değişiklikleri belirleyin. Kullanıcı değişikliklerini koruyun; önceki test veya ortam bilgilerini güncel gerçek olarak varsaymayın.
3. İlgili frontend/backend kodunu, API ve veri sözleşmelerini, testleri ve dağıtım yapılandırmasını inceleyin. Henüz var olmayan endpoint veya cihaz özelliğine dayanmayın.
4. Kullanıcıya kapsamı ve kısa yaklaşımı belirtin. Kanonik görünümlerde ana tasarım etkisi varsa **README'deki üç ekran görüntüsünü yenileme** adımını çalışma planına baştan ekleyin; küçük işlevsel UI değişikliğinde geçici tarayıcı QA kanıtı planlayın.

## Uygularken

- Mevcut tasarım tokenlarını, ortak bileşenleri ve veri getirme yapısını kullanın. Apache ECharts'ı, beyaz içerik/koyu navigasyon dilini ve şeffaf marka varlıklarını koruyun.
- Eksik veriyi üretmeyin; fiziksel port ve topoloji ilişkilerini yalnız doğrulanmış envanter/gözlemden türetin.
- Yetki, sır ve SSH güvenlik sınırlarını koruyun. Kayıtlı cihaz ekleme hedef onayıdır; cihaz başına `.env` izni eklemeyin. Testi geçirmek için kimlik doğrulama, origin/CSRF, host key veya yapılandırılmış ek CIDR sınırını devre dışı bırakmayın. Eski algoritmalar yalnız cihaz bazlı açık izinle kullanılabilir. Otomatik profil de aynı izne tabidir; izinsiz algoritma düşürme, yanlış parola veya host key hatasında profil deneme döngüsü yapmayın.
- Docker işlemlerinden önce context/proje/port/volume hedeflerini doğrulayın. Doğrudan `docker compose` kullanın; çalışan kullanıcı ortamını test fixture'ıyla değiştirmeyin.
- Dosya değişikliği talebini kendiliğinden commit, push, PR açma, üretim dağıtımı veya veri silme izni saymayın.

## Ana tasarım değişikliği için zorunlu kapanış adımları

Ortak kuralın ayrıntısı: [README görüntülerini yenileme](rule.md#5-ana-tasarım-değişikliğinde-readme-görüntülerini-yenile).

Önce `Ana tasarım etkisi: var/yok — gerekçe` sınıflandırmasını yapın. Yalnız `var` ise aşağıdaki üçlü yenileme zorunludur; `yok` ise hedef UI akışını gerçek tarayıcıda doğrulayın ve geçici kanıtı teslimde belirtin.

1. Son kodu izole QA ortamında çalıştırın; mevcut kullanıcıları, verileri veya anahtarları sıfırlamayın.
2. Gerçek tarayıcıda hedef akışı ve masaüstü/mobil yerleşimi doğrulayın. Sayfa kimliği, anlamlı içerik, yükleme durumu, konsol, taşma ve hata katmanını kontrol edin.
3. Aşağıdaki üç görünümü **ana tasarım değişikliğinde yeniden yakalayın**:
   - Ana sayfa → `docs/screenshots/dashboard.png`.
   - Aynı QA cihazının SSH kapalı detayı → `docs/screenshots/device-detail.png`.
   - Aynı QA cihazının gerçek SSH bağlantısı açık detayı → `docs/screenshots/device-detail-ssh.png`.
4. Üç dosyayı görsel olarak inceleyin; sır, gerçek müşteri bilgisi veya hassas terminal çıktısı içermediğini doğrulayın. SSH bağlantısını sahte terminal metniyle taklit etmeyin.
5. İncelenmiş kareleri repository'deki bu üç dosyaya alın; README açıklamaları/alt metinleri ve yollarını kontrol edin. Yalnız `/tmp` altında ekran kanıtı bırakmak veya sohbete resim eklemek bu gereksinimi karşılamaz.
6. `git diff --stat` ve `git status --short` ile görüntü güncellemelerinin teslimata dahil olduğunu kontrol edin. Yeniden yakalanıp birebir aynı kalan kare varsa sonucu açıkça not edin; yapay PNG farkı oluşturmayın.
7. QA/SSH bağlantısı sağlanamıyorsa engeli ve eksik kalan görüntüyü bildirin. Bu koşulda görsel işi tamamlandı diye raporlamayın; eski görselleri yeniymiş gibi sunmayın.

Backend/API/migration/test/dokümantasyon, hata/veri doğruluğu düzeltmesi, küçük metin/ikon/kontrol/durum değişikliği veya kanonik görüntülerde bulunmayan yeni alt sayfada üçlü yenilemeyi uygulamayın; ana tasarımı etkilememe gerekçesini belirtin.

## Teslim kontrol listesi

- [ ] İlgisiz kullanıcı değişiklikleri ve mevcut çalışma ortamı korundu.
- [ ] İlgili testler ve statik kontroller çalıştırıldı; başarısız/atlanmış kontroller açıklandı.
- [ ] `Ana tasarım etkisi: var/yok — gerekçe` kaydedildi; `var` ise üç README görüntüsü güncel koddan yeniden alındı, incelendi ve teslimata dahil edildi.
- [ ] README bağlantıları, görüntü açıklamaları ve alt metinleri kontrol edildi.
- [ ] Yakalama ortamı, tarih, viewport ve sürüm/çalışma ağacı bilgisi raporlandı; test verisi olduğu belirtildi.
- [ ] Görüntü yenilemesi gerekmiyorsa ana tasarımı neden etkilemediği açıklandı; değişen UI geçici tarayıcı kanıtıyla doğrulandı.
- [ ] Kalan sınırlamalar, migration/dağıtım etkisi ve çalıştırılmayan doğrulamalar belirtildi.

Son yanıtta yapılan işi, doğrulama sonuçlarını ve varsa engelleri kısa ve somut biçimde aktarın. Test etmediğiniz akış için başarı iddiasında bulunmayın.
