## Amaç ve kapsam

Ne değişti, neden? İlgili issue varsa bağlantısını ekleyin.

## Doğrulama

Çalıştırdığınız komutları ve gerçek sonuçlarını yazın. Çalıştırılmayan kontrolleri ve nedenlerini belirtin. Yerel fixture/QA ile fiziksel cihaz doğrulamasını ayırın.

## Dağıtım ve uyumluluk

API, migration, ortam değişkeni, volume/anahtar deposu veya bağımlılık değişikliği var mı? Varsa mevcut kurulumlara etkisini ve geri dönüş yaklaşımını açıklayın.

## Kontrol listesi

- [ ] `rule.md` kurallarını okudum; yapay zekâ ajanı kullanıldıysa `agent.md` yönergesi de uygulandı.
- [ ] İlgili testleri ve dokümantasyonu güncelledim veya neden gerekmediğini açıkladım.
- [ ] Görsel değişiklik varsa üç README görüntüsü güncel uygulamadan yeniden alındı, incelendi ve bu PR'a dahil edildi; yoksa aşağıda gerekçesini belirttim.
- [ ] Commit, log ve ekran görüntülerinde parola, anahtar, token/cookie veya özel müşteri verisi yok.
- [ ] Metrik kapsamı/birimleri ve eksik/eski veri davranışları korunuyor (uygulanıyorsa).
- [ ] Yetki ve SSH host key/CIDR denetimleri korunuyor (uygulanıyorsa).
- [ ] Katkıyı AGPL-3.0-only kapsamında sunma hakkım var; üçüncü taraf bildirimleri korundu.

## Görsel değişiklikler

Görsel değişiklik var mı? Yoksa görüntü yenilemesinin neden gerekmediğini yazın. Varsa `rule.md` gereği üç dosyanın tamamını güncel koddan yeniden alın:

- `docs/screenshots/dashboard.png` — ana sayfa.
- `docs/screenshots/device-detail.png` — SSH kapalı cihaz detayı.
- `docs/screenshots/device-detail-ssh.png` — aynı cihazda gerçek QA SSH bağlantısı açık.

Yakalama tarihi, QA ortamı, test edilen sürüm/çalışma ağacı, tarayıcı/viewport ve mobil kontrol sonucunu belirtin. Yeniden yakalanıp birebir aynı kalan kare varsa bunu not edin. README bağlantıları, açıklamalar ve alt metinler güncel olmalı; gerçek müşteri verisi veya sır bulunmamalıdır. Yalnız PR'a eklenen veya geçici dizinde bırakılan görüntüler README yenilemesi sayılmaz. Yakalama yapılamadıysa engeli ve eksik kalan görünümü açıkça yazın.
