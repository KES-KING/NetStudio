# NetStudio adına geçiş

Kanonik depo: [KES-KING/NetStudio](https://github.com/KES-KING/NetStudio). Yeni kurulum, paket, Docker imajı, browser başlığı ve ayar adları NetStudio kullanır. Kaynak dizinini yeniden adlandırmak gerekmez; IDE, bind mount ve host güncelleyici yolları kendiliğinden değiştirilmez.

## Mevcut kurulum: önce veriyi koruyun

Bu bir yeniden kurulum veya veritabanı taşıma işlemi değildir. `.env` dosyanızı `.env.example` ile ezmeyin. Çalışan proje/DB/kullanıcı/volume adını yalnız marka değişti diye değiştirmeyin. `down -v`, volume silme, seed veya kullanıcı sıfırlama çalıştırmayın. Bu sürümün Compose sözleşmesi değiştiği için otomatik güncelleyici geçişi reddeder; operatör geçişi gerekir.

1. Aynı Docker context ve mevcut Compose projesini bulun: `docker context show` ve `docker compose ls`. Aşağıdaki örneklerde `MEVCUT_CONTEXT`, `MEVCUT_PROJE`, `POSTGRES_CONTAINER` ve `API_CONTAINER` yer tutucularını **doğruladığınız** hedeflerle değiştirin. Başka bir projenin kaynaklarını kullanmayın.

   ```bash
   docker --context MEVCUT_CONTEXT ps --filter label=com.docker.compose.project=MEVCUT_PROJE
   docker --context MEVCUT_CONTEXT inspect --format '{{range .Mounts}}{{println .Destination .Name}}{{end}}' POSTGRES_CONTAINER API_CONTAINER
   ```

2. Mevcut DB, anahtar dosyası, özel `.env` ve bütün Compose/TLS override dosyalarının korumalı yedeğini alın. Sırları terminale/loglara dökmeyin. Eski immutable imaj kimliklerini kaydedin. Host güncelleyiciyi duraklatın. `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` ve `DATABASE_URL` değerlerini **aynı bırakın**.

3. Mevcut `.env` içindeki `STOCC_` önekli ayarların adlarını `NETSTUDIO_` olarak değiştirin; **değerlerini değiştirmeyin**. Özellikle production kipi, izinli origin, CIDR sınırı, TLS dizini ve güncelleme ayarı korunmalıdır. Backend doğrudan eski ortamla başlatılırsa eski adları okuyabilir; yeni Compose yalnız yeni adları aktarır. Hem eski hem yeni ad varsa yeni ad (boş değer dahil) önceliklidir.

4. `.env` içine aşağıdakileri ekleyin. Fiziksel volume adlarını 1. adımdaki mount çıktısından alın. `external=true` sayesinde yanlış/eksik volume sessizce oluşturulmaz; Compose hata verir. Proje adını **değiştirmeyin**.

   ```dotenv
   COMPOSE_PROJECT_NAME=MEVCUT_PROJE
   NETSTUDIO_POSTGRES_VOLUME=MEVCUT_VERITABANI_VOLUME_ADI
   NETSTUDIO_KEYRING_VOLUME=MEVCUT_ANAHTAR_VOLUME_ADI
   NETSTUDIO_EXTERNAL_VOLUMES=true
   NETSTUDIO_CONFIG_VERSION=1
   ```

   Bu onay işareti olmadan yeni Compose yapılandırması durur. Yeni kurulumda `.env.example` bu işareti içerir. Bind mount / harici PostgreSQL kullanan kurulumlarda mevcut override'ı koruyup bağları ayrıca doğrulayın; yukarıdaki named-volume örneğini doğrudan uygulamayın.

5. Mevcut override dosyalarının eski servis ortamı, imaj veya volume anahtarlarını yeni Compose sözleşmesine uyarlayın; fiziksel hedefleri değiştirmeyin. Aynı context/proje ve **bütün** mevcut `-f` seçenekleriyle `docker compose config --quiet` çalıştırın. Render edilmiş yapılandırma sır içerebilir; paylaşmayın. Her iki volume ve DB hedefinin eskisiyle aynı olduğunu doğrulamadan `up` çalıştırmayın. Sonrasında aynı proje üzerinde `up --build -d --wait` uygulanabilir. Bu kaynak değişikliği çalışan kurulumlarda bu adımı kendiliğinden çalıştırmaz.

6. Mount adlarını yeniden karşılaştırın; eski kullanıcıyla giriş, cihaz/port kimlikleri, host anahtarları, credential çözme, manuel toplama ve worker sağlığını kontrol edin. Yeni cookie `netstudio_session` olduğu için tarayıcıda bir kez yeniden giriş gerekir; eski cookie kabul edilmez. Parola/hesap/oturum tablosu silinmez.

## Eski şifreli veriler ve anahtarlar

`backend/app/legacy_compat.py` yalnız eski ayar adlarını, `stocc-keyring.json` dosya adını ve AES-GCM `stocc:` AAD etiketini okumak için eski metni barındırır. Bunları topluca silmek mevcut cihaz parolalarını okunamaz hale getirir. Yeni sırlar `netstudio:` AAD ile, yeni keyring ise `netstudio-keyring.json` adıyla yazılır. Eski volume'de yalnız eski dosya varsa aynı dosya kullanılır; ikinci bir anahtar üretilmez. İki dosya birden varsa seçim belirsizdir ve işlem durur; doğrulanmış dosyayı servis ortamındaki `NETSTUDIO_KEYRING_FILE` ile açıkça belirtin (secrets-init, API ve worker için birlikte).

UID/GID `100:101` değişmedi; kullanıcı adı değişikliği anahtar volume izinlerini bozmaz. Şema migration'ı ve toplu yeniden şifreleme bu adlandırma değişikliği için gerekmez. Eski sırın okunması DB'ye yazmaz; cihaz/anahtar/protokol AAD bağları ve bütünlük doğrulaması aynen uygulanır.

Yeni sürümde kaydedilmiş sırlar eski sürüm tarafından okunamaz. Geri dönüşte yalnız eski imajı başlatmak yeterli sayılmaz: güncel credential yazımları varsa operatör kontrollü, birbiriyle uyumlu **DB + anahtar** yedeği gerekir. Otomatik veri silme/geri yükleme yoktur.

## Kapsam dışındaki eski adlar

Git geçmişi, kişisel `user-notes.md`, yerel `.env`, workspace klasörü ve çalışan Docker kaynakları yeniden yazılmaz. Önceki QA raporlarında proje/dizin adları yeni dokümantasyon yazımına uyarlanmıştır; bu geçmiş runtime kaynaklarının yeniden adlandırıldığı anlamına gelmez. Marka dışındaki zorunlu eski değerler yalnız uyumluluk modülü, bunun regresyon testleri ve bu geçiş açıklamasında tutulur.
