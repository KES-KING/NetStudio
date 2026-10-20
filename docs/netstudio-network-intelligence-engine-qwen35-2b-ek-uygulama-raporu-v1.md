# NetStudio Network Intelligence Engine (NNIE)
## Qwen3.5-2B — Yerel AI Entegrasyonu ve Ek Uygulama Raporu v1.0

| Belge bilgisi | Değer |
|---|---|
| Tarih | 19 Ekim 2026 |
| Proje | `KES-KING/NetStudio` |
| Belge kimliği | `NNIE-IMPL-Q2-001` |
| Durum | Uygulama tasarımı; kod implementasyonu ve donanım benchmark’ı henüz yapılmadı |
| Kesinleşen kullanıcı kararı | **Qwen3.5-2B** |
| Ana mimari | `netstudio-network-intelligence-engine-architecture-v1.md` |
| Bu raporun önerdiği dağıtım | Metin odaklı GGUF, başlangıç kuantizasyonu `Q4_K_M`, sabitlenmiş `llama.cpp` runtime |
| Çalışma ilkesi | CPU zorunlu temel yol; GPU isteğe bağlı hızlandırma |
| Operasyon sınırı | Salt okunur analiz + Structured Intent önerisi; yazma yalnızca ana mimarinin onaylı deterministik yürütücüsünde |

> **Temel karar:** NetStudio, Qwen3.5-2B olmadan da cihazlarını izleyebilen ve yetkili kullanıcıların manuel olarak başlattığı plan/onay akışını çalıştırabilen bir sistemdir. Model bir kullanıcı etkileşimi ve analiz bileşenidir; cihaz sürücüsü, politika otoritesi veya konfigürasyon yürütücüsü değildir.

---

## 1. Belgenin amacı, dayanağı ve değişiklik sınırı

Bu ek rapor, seçilen **Qwen3.5-2B** modelinin mevcut NNIE mimarisine nasıl entegre edileceğini; düşük kaynaklı bilgisayarlarda nasıl işletileceğini; hangi sözleşmeler, modüller, testler ve teslimatlarla uygulanacağını tanımlar.

Ana mimari dosyasının yerine geçmez. Ana dosyadaki Operation Registry, Capability Engine, Change Planner, Policy Engine, Approval Center, JobStore, Change Executor, Verification ve Rollback Strategy Registry korunur. Bu belgede bunların Qwen entegrasyonuyla kesiştiği noktalar açıklanır; cihaz yazma prosedürleri ikinci kez ve farklı kurallarla tanımlanmaz.

### 1.1. Kaynak ve karar sınıfları

- **[A0] Ana mimariden devralınan kurallar:** Özellikle ana belgenin §2–§11 güven sınırları, §12 API taslağı, §13–§14 veri/driver yapısı ve §16–§18 test/ADR kayıtları.
- **[K1] Kullanıcı kararı:** Genel amaçlı yerel model olarak Qwen3.5-2B seçilmiştir. 0.8B, 4B veya başka bir modele otomatik geçiş bu raporun kapsamı değildir.
- **[T] Yeni uygulama tasarımı:** Runtime seçimi, profil değerleri, ek API’ler, dosya adları, iş sırası ve kabul hedefleri bu ek raporun önerileridir; mevcut repository’de uygulanmış oldukları anlamına gelmez.
- **[R1–R4] Haricî teknik doğrulama:** Model ve runtime özellikleri için birincil kaynaklar, son bölümde verilmiştir. Donanım sonuçları bu kaynaklardan türetilmiş ürün garantileri değildir.

19 Ekim incelemesindeki, adlandırma güncellemesinden önceki ana dosyanın tarihsel SHA-256 değeri (güncel dosyanın hash'i değildir):

```text
2719677a98f6407b9b876f258b8e42d28bef8a763dcf49f4ec657aab3d075389
```

İlk raporda ana belge değiştirilmemiştir; sonraki NetStudio adlandırma geçişinde iki belgenin adları, marka/repository atıfları ve NNIE kısaltması güncellenmiştir. Bu teknik tasarımın uygulanmış olduğu anlamına gelmez. Repository’ye ait başlangıç bilgileri [A0] §1’den alınmıştır; bu ek rapor hazırlanırken güncel GitHub dalı yeniden denetlenmemiştir. Geliştirme başladığında güncel çalışma ağacı, `AGENTS.md`, migration zinciri ve API sözleşmeleri kontrol edilmelidir.

### 1.2. Uygulama önceliği

Çelişki halinde ana belgenin güvenlik, onay, capability ve rollback kısıtları geçerlidir. Bu ek, izinleri azaltabilir veya daha sıkı kaynak sınırları koyabilir; model kolay çalışsın diye bir güvenlik kontrolünü kaldıramaz.

Modelin JSON üretmesi `ValidatedChangeIntent` oluşturulduğu anlamına gelmez. `ValidatedChangeIntent` oluşturulması da planın onaylandığı veya uygulanabileceği anlamına gelmez.

---

## 2. Kesinleşen ürün sınırları

| Konu | Uygulama kararı | Gerekçe / kapsam |
|---|---|---|
| Model ailesi | Qwen3.5-2B | Kullanıcı kararı [K1] |
| Kullanım | Metin girdisi ve çıktısı | SNMP/SSH/NETCONF gözlemleri, sınırlı doküman parçaları, operasyon önerileri |
| Görüntü/video | İlk sürümde kapalı | Vision encoder/projector ve görüntü alımı ürün gereksinimi değildir |
| Runtime | `llama.cpp` tabanlı ayrı inference süreci | Önerilen üretim uygulaması [T] |
| Kuantizasyon | Önce `Q4_K_M` değerlendirilecek | Sabitlenmiş GGUF artefaktının kalite/bellek testini geçmesi gerekir |
| CPU yolu | GPU olmadan çalışır dağıtım hedefi | Destek, test edilmiş işletim sistemi ve CPU komut kümesiyle sınırlıdır |
| GPU yolu | Aynı modelin sertifikalı backend ile hızlandırılması | Model ve güvenlik davranışı değişmez |
| Eşzamanlı inference | Başlangıçta `1` | Düşük kaynak tüketimi ve öngörülebilir bellek |
| Varsayılan mod | Non-thinking; açık runtime ayarıyla | Kısa, şemalı çıktılar; [R1] ile uyumlu |
| Çevrimdışı işletim | Model kurulduktan sonra internet gerektirmeyen çalışma | Bulut servisine sessiz fallback yok |
| AI devre dışı | İzleme ve manuel plan/onay akışı sürer | Kontrol düzlemi AI’ya bağımlı değildir |
| Müşteride eğitim | Yok | Fine-tuning ayrı bir ileriki geliştirme çalışmasıdır |

**“Her bilgisayarda çalışır” pazarlama iddiası yerine:** Test edilen CPU/OS matrisi, kaynak kontrolü ve kontrollü `AI unavailable` davranışı yayımlanacaktır. 32-bit işletim sistemi veya sınırsız eski işlemci desteği bu raporla taahhüt edilmez.

---

## 3. Model ve runtime için doğrulanmış teknik çerçeve

Qwen’in model kartı Qwen3.5-2B’yi vision encoder içeren, 2B dil modeli parametreli ve Apache-2.0 lisans etiketli bir model olarak tanımlar. Kart, küçük parametre ölçeği için prototipleme, görev odaklı fine-tuning ve araştırma/geliştirme kullanımını özellikle belirtir. Bu nedenle modelin NetStudio operasyonlarında üretime uygunluğu ayrıca değerlendirilmelidir. [R1]

**Önemli ayrım:** Güncel Qwen3.5-2B kartında non-thinking varsayılandır. Önceki görüşmelerde aile geneli için kullanılan “varsayılan thinking” ifadesi bu modelin güncel kartına uygulanmaz. NetStudio yine de bu davranışı modele bırakmayacak; sürümlü chat template ve adapter ayarıyla non-thinking modunu açıkça doğrulayacaktır. [R1]

`llama.cpp`; CPU ve çeşitli GPU backend’leri, GGUF/kuantize model çalıştırma ve HTTP sunucusu sunar. Sunucu dokümantasyonunda JSON Schema ile kısıtlı çıktı, GPU katmanı seçimi, slot sayısı ve chat-template parametreleri vardır. Bunlar Qwen artefaktı ve seçilen runtime sürümüyle birlikte smoke-test edilecektir. [R2, R3]

### 3.1. Model adı tek başına dağıtım tanımı değildir

Aşağıdaki öğeler birlikte sürümlenmelidir:

```text
upstream_model_id + upstream_revision
+ GGUF_conversion_revision + quantization_recipe
+ GGUF_sha256 + tokenizer/chat_template_digest
+ runtime_commit + backend_build_digest
+ prompt_version + response_schema_digest
+ sampling_profile + context_profile
```

Ollama etiketi, topluluk GGUF’u ve kendi dönüştürdüğümüz GGUF aynı dosya değildir. Önceki görüşmelerdeki boyut veya hız değerleri bu raporda minimum sistem gereksinimi olarak kullanılmamaktadır. Nihai boyut `bytes`, bellek tüketimi ise gerçek paket üzerinde ölçülecektir.

`Q4_K_M` ismi kaliteyi tek başına garanti etmez. Dönüştürme yöntemi, tokenizer/template uyumu ve backend sonucu doğrulanmalıdır. Başarısız testte başka ağırlık dosyasına sessiz geçilmez; yeni bir release candidate hazırlanır.

### 3.2. Lisans ve tedarik kaydı

Dağıtılan modelin lisans metni, varsa bildirimleri, runtime’ın lisansı ve paketlenen bağımlılıkların bildirimleri sürüm paketine eklenir. Bir üçüncü taraf dönüşümü kullanılacaksa kaynağı ayrıca kaydedilir. Resmî model kartındaki lisans etiketi, seçilen üçüncü taraf dosyanın kaynağını doğrulamanın yerine geçmez.

---

## 4. Ana mimariyle izlenebilirlik

| Ana belge | Korunan yapı | Bu ekin tamamladığı uygulama alanı |
|---|---|---|
| [A0] §2 | LLM ile write executor ayrımı | Inference süreci, ağ izolasyonu, ayrı lifecycle |
| [A0] §3 | `AIIntentProposal` / `ValidatedChangeIntent` | Qwen cevap zarfı, strict parsing, hedef çözümleme |
| [A0] §4 | Capability kanıtı ve TTL | Modele yalnızca kapsamlı/izinli özet sağlama |
| [A0] §5 | Değişmez plan ve artefakt bağı | AI provenance kaydı; model çıktısını sonradan yeniden derlememe |
| [A0] §6–§7 | RBAC/ABAC ve onay | `ai.use` ek izni, AI çıktısının onay sayılmaması |
| [A0] §8–§11 | Execute/verify/commit/rollback | AI kaynak baskısının kritik akışı durdurmaması |
| [A0] §12–§13 | API ve PostgreSQL modelleri | AI request, evidence ve runtime release kayıtları |
| [A0] §14 | `DeviceDriver` / `ChangeAdapter` | Aynı sürücüleri kullanan typed read tools |
| [A0] §15–§16 | Tehdit modeli ve testler | Prompt injection, OOM, CPU/GPU fallback ve schema testleri |
| [A0] §17–§18 | Aşamalı açılım ve ADR | CPU-first entegrasyon iş paketleri ve yeni ADR’ler |

---

## 5. Hedef servis mimarisi

Aşağıdaki Mermaid çizimi bir uygulama bileşen görünümüdür; ayrıntılı UML veya mevcut kodun birebir haritası değildir. Yeni bileşenler [T] tasarımına aittir.

```mermaid
flowchart TD
    UI["Next.js: AI Panel ve Plan Merkezi"] --> API["FastAPI: Oturum ve kapsam denetimi"]
    API --> ORCH["NNIE AI Orchestrator"]
    ORCH --> CTX["Context Builder ve Evidence Registry"]
    CTX --> READ["Typed salt okunur araclar"]
    READ --> DRIVER["DeviceDriver / Collector / Observation"]
    CTX --> KB["Yerel bilgi tabani"]
    ORCH --> ADMIT["Kaynak ve kuyruk denetimi"]
    ADMIT --> MANAGER["Runtime Manager"]
    MANAGER --> LLM["llama.cpp + Qwen3.5-2B GGUF"]
    LLM --> VALIDATE["Strict schema ve hedef dogrulama"]
    VALIDATE --> PROPOSAL["Dogrulanmis oneri gorunumu"]
    PROPOSAL --> UI
    UI -->|"Ayri yetkili plan talebi"| PLAN["Ana mimari: Planner ve Policy"]
    PLAN --> APPROVAL["Ayri kullanici onayi"]
    APPROVAL --> EXEC["JobStore ve Change Executor"]
    EXEC --> VERIFY["Verify / Commit / Rollback"]
    VERIFY --> AUDIT["Audit ve kanit kayitlari"]
```

**Metin alternatifi:** AI Orchestrator yalnızca filtrelenmiş gözlem verisini ve izinli operasyon tanımlarını modele gönderir. Model öneri döndürür. Kullanıcı plan oluşturma eylemini ayrıca seçer; ana belgedeki plan, onay, yürütme ve rollback zinciri bundan sonra çalışır. Modelin bu zincire doğrudan çağrı yolu yoktur.

### 5.1. Sorumluluk ayrımı

| Bileşen | Yapacağı iş | Yapmayacağı iş |
|---|---|---|
| `LLMProvider` | İstek/cevap dönüştürme, deadline, iptal, metrik toplama | Cihaz sırrı alma, ağ tarama, SSH çalıştırma |
| `RuntimeManager` | Süreç başlatma, durdurma, readiness, profil seçimi | Cihaz yazma işlemini iptal etme veya devralma |
| `ContextBuilder` | Yetkiyle filtrelenmiş kısa kanıt paketi | Bütün envanteri, sırları veya ham konfigürasyonu gönderme |
| `ReadToolRegistry` | Typed ve sınırlı okuma işlemleri | Serbest CLI, shell, URL fetch veya Python yürütme |
| `ProposalValidator` | Şema, hedef, parametre ve evidence kontrolü | Onay üretme, capability açma |
| `Change Planner` | Ana mimarideki deterministik plan | LLM’yi komut derleyicisi olarak kullanma |
| `Change Executor` | Mühürlü/onaylı artefaktı yürütme | İş sırasında model cevabını bekleme |

AI katmanı için ikinci bir device driver veya bağımsız konfigürasyon motoru yazılmayacaktır.

---

## 6. CPU/GPU profilleri ve kaynak kabul politikası

Aşağıdaki değerler **ilk geliştirme ve benchmark varsayılanlarıdır**. Ölçülmüş model gereksinimi, SLA veya tamamlanmış performans sertifikası değildir.

### 6.1. Çalışma profilleri

| Profil | Context üst sınırı | Çıktı bütçesi | Inference slotu | Çalışma şekli |
|---|---:|---:|---:|---|
| `cpu-constrained` | 2.048 token | Intent 256; analiz 384 | 1 | CPU; kısa bağlam, küçük okuma sonuçları |
| `cpu-standard` | 4.096 token | Intent 384; analiz 768 | 1 | CPU; normal kısa teknik analiz |
| `gpu-standard` | 4.096 token | Intent 384; analiz 768 | 1 | Test edilmiş backend ile GPU offload |
| `manual-only` | — | — | 0 | AI kapalı; ana NetStudio işlevleri açık |

Context bütçesi; sistem mesajı, şema/operasyon açıklaması, chat-template tokenları, kullanıcı mesajı, kanıt ve üretilecek çıktının toplamıdır. “4K context” üzerine ayrıca 4K çıktı eklenmez.

GPU varlığı context’i otomatik olarak büyütmez. Daha uzun bağlam ayrı test ve profil sürümü gerektirir. GPU’dan CPU’ya geçerken aynı Qwen3.5-2B artefaktı kullanılır.

### 6.2. Destek matrisi adayları

| Ortam | Başlangıç yaklaşımı |
|---|---|
| 4 GB sistem RAM’i | AI varsayılan kapalı; tüm uygulama bütçesi doğrulanmadan destek ilan edilmez |
| 8 GB RAM, GPU yok | `cpu-constrained` için hedef test sınıfı; kullanılabilir bellek yeterli olmalı |
| 16 GB RAM, GPU yok | `cpu-standard` için önerilen ilk referans sınıfı |
| Ayrık GPU, 4 GB VRAM | `gpu-standard` adayı; boş VRAM, sürücü ve gerçek tepe kullanım kontrol edilir |
| Ayrık GPU, 6–8 GB VRAM | Aynı profile aday; daha yüksek eşzamanlılık otomatik açılmaz |
| Birleşik bellekli GPU | RAM ve GPU belleği aynı havuz olabilir; kapasiteler toplanarak iki kez sayılmaz |

Bu tablo destek sözü değildir. İlk release matrisi: test edilmiş Linux x86-64 CPU dağıtımı ve isteğe bağlı test edilmiş NVIDIA GPU dağıtımı. Windows/WSL, macOS/Metal, AMD/HIP/Vulkan ve diğer backend’ler ayrı doğrulama satırlarıdır; runtime’ın genel desteği NetStudio paketinin otomatik desteği sayılmaz. Backend seçenekleri için [R2, R4].

### 6.3. Bellek bütçesi

Ölçümde şu alanlar ayrılır:

```text
Model dosyasi boyutu
!= AI surecinin RSS/PSS degeri
!= GPU VRAM kullanimi
!= tum NetStudio servisleri + isletim sistemi bellek ihtiyaci
```

Model ağırlıkları yanında çalışma buffer’ları, context/attention state, backend tahsisleri ve süreç maliyeti ölçülür. Qwen’in hibrit mimarisi için başka bir modelden kopyalanmış basit KV-cache hesabı kapasite sertifikası yerine kullanılamaz.

Yeni bir inference için kabul koşulu:

```text
kalan_etkin_bellek_butcesi >= beklenen_ek_tepe_kullanim + guvenlik_payi
```

`kalan_etkin_bellek_butcesi`, host’un kullanılabilir belleği ile container/cgroup kalan limiti arasında dar olan değerdir. Model yüklüyse yalnızca ek tahsis hesaplanır; ağırlıklar iki kez sayılmaz. Profil için ölçüm yoksa kontrollü bootstrap bütçesi kullanılır ve sonuç `uncalibrated` olarak gösterilir.

Önerilen ilk laboratuvar sınırı: AI süreç grubu için `cpu-constrained` altında 3 GiB, standart profilde 4 GiB hard limit; host için en az 1 GiB ek rezerv. **Bunlar modelin bu miktarda RAM ile kesin çalışacağını göstermez.** Sınırı aşan profile “destekli” etiketi verilmez; bellek limiti otomatik ve sınırsız artırılmaz.

Docker Desktop/WSL kullanılıyorsa fiziksel bilgisayarın RAM’i yanında VM’ye verilen bellek de değerlendirilir.

### 6.4. CPU ve GPU kabul kontrolleri

CPU için mimari, etkin komut kümeleri, fiziksel çekirdek sayısı, cgroup CPU kotası ve kullanılan binary’nin ABI gereksinimleri denetlenir. Başlangıç thread adayı `min(4, kullanılabilir_fiziksel_çekirdek)`; az çekirdekli sistemlerde OS ve collector için kaynak bırakılır. Sabit thread sayısı veya tüm çekirdekleri kullanma varsayılan değildir.

Dağıtım binary’si geliştirici makinesine özel `native` optimizasyonla evrensel paket ilan edilmez. Uyumsuz instruction set ve `SIGILL` benzeri hatalar izole probe sürecinde yakalanır; API süreci çökertilmez.

GPU için backend’in varlığı, sürücü uyumu, kullanılabilir VRAM, model yükleme ve kısa schema üretim testi denetlenir. Kısmi offload, tam offload’dan daha hızlı kabul edilmez; ölçüm sonucu seçilir. CPU yolu ayrıca test edilir; yalnızca GPU üzerinde başarılı bir model release’i yayımlanmaz.

---

## 7. Runtime lifecycle, kuyruk ve hata yönetimi

### 7.1. Süreç modeli

Üretimde model API worker’ının içine gömülmez. Yerel inference ayrı süreç/container sınırında çalışır. `RuntimeManager`, servis yöneticisi veya dar yetkili sidecar supervisor üzerinden bu süreci yönetir; FastAPI’ye Docker socket veya genel root yetkisi verilmez.

Aynı host/model için tek runtime sahibi bulunur. Birden fazla API worker’ı eşzamanlı cold start istediğinde atomik startup kilidi kullanılır; her worker kendi model kopyasını yükleyemez.

### 7.2. Runtime durumları

```mermaid
stateDiagram-v2
    [*] --> DISABLED
    DISABLED --> STOPPED: yonetici etkinlestirir
    STOPPED --> STARTING: kaynak kabul edildi
    STARTING --> READY: integrity ve smoke test basarili
    STARTING --> UNAVAILABLE: uyumsuzluk veya kaynak hatasi
    READY --> BUSY: bir is kabul edilir
    BUSY --> READY: tamamlandi veya kontrollu iptal
    READY --> STOPPING: bos kalma suresi veya bakim
    STOPPING --> STOPPED: surec sonlandi
    BUSY --> UNAVAILABLE: runtime kaybi
    UNAVAILABLE --> STARTING: sinirli yeniden baslatma
    UNAVAILABLE --> DISABLED: hata butcesi doldu
    STOPPED --> DISABLED: yonetici kapatir
```

Metin alternatifi: AI kapalı, durmuş, yükleniyor, hazır, meşgul, durduruluyor veya kullanılamıyor olabilir. Bu durumlar device change transaction durumları değildir.

### 7.3. Önerilen işletim varsayılanları

| Parametre | İlk aday | Not |
|---|---:|---|
| Aktif model instance | 1 | Aynı artefakt için |
| Aktif inference | 1 | Backend’de admission + runtime slot sınırı |
| Bekleyen AI işi | 4 | FIFO; kullanıcı başına en fazla 1 bekleyen iş |
| Kuyruk bekleme deadline | 60 sn | Dolunca `AI_QUEUE_TIMEOUT` |
| Intent üretim deadline | 45 sn | Cold start’tan ayrı ölçülür |
| Analiz üretim deadline | 90 sn | Adımlı okuma bütçesiyle sınırlı |
| Runtime startup deadline | 180 sn | Ürün yanıt süresi garantisi değildir |
| Boşta unload süresi | 300 sn | Yükle/boşalt döngüsü için minimum residence ile |
| Model çıktısı düzeltme | En fazla 1 | Sadece parser/şema hatası; yazma yetkisi doğurmaz |
| Runtime crash restart | 10 dakikada en fazla 2 | Sonra circuit breaker ve görünür hata |

Bu değerler profil konfigürasyonunda sürümlenir. Performans ölçümleri sonunda yeniden değerlendirilebilir.

### 7.4. GPU hatasında CPU fallback

1. Mevcut model üretimi durdurulur; kısmi JSON ve kısmi tool önerileri kullanılmaz.
2. Görevin tamamlanıp tamamlanmadığı AI request kaydından belirlenir. Aynı proposal iki kez yayımlanmaz.
3. GPU süreç/buffer temizliği tamamlanmadan ikinci runtime açılmaz.
4. CPU profilinde admission yeniden yapılır. Yeterli kaynak yoksa `AI_RESOURCE_INSUFFICIENT` dönülür.
5. İzin verilmişse aynı **AI inference** isteği en fazla bir kez CPU’da tekrarlanır. Kullanıcıya çalışma profili değişimi gösterilir.
6. Bu mekanizma `Change Executor.apply` için retry yetkisi değildir. Cihazdaki sonucu bilinmeyen işlem [A0] §8–§11 uyarınca `RECONCILING` akışına aittir.

### 7.5. AI kapatıldığında kaynakların bırakılması

Boşta kapanma yalnızca aktif inference ve sahiplenilmiş AI işi yokken yapılır. Süreç sonlandığında private bellek/VRAM bırakılması ölçülür; işletim sisteminin dosya page cache tutması “model hâlâ çalışıyor” şeklinde yorumlanmaz.

Model durdurulurken yeni istek gelirse lifecycle kilidi altında tek karar verilir. Kullanıcılar arası prompt/KV cache izolasyonu test edilir; ham konuşmalar kalıcı slot dosyalarına varsayılan olarak yazılmaz.

---

## 8. Model artefaktı, tedarik ve çevrimdışı paketleme

### 8.1. Paket yapısı — öneri

```text
snie-ai-package/
├── model/
│   └── netstudio-qwen35-2b-q4_k_m.gguf
├── runtime/
│   └── <os-arch-backend>/llama-server
├── policies/
│   ├── runtime-profiles.json
│   └── prompt-profile.json
├── manifests/
│   ├── model-lock.json
│   ├── runtime-lock.json
│   └── release-manifest.sig
├── licenses/
│   └── <model-runtime-dependency-notices>
└── reports/
    ├── compatibility-matrix.json
    └── acceptance-results.json
```

Dosya adı NetStudio dağıtım takma adıdır; upstream’de bu isimle hazır dosya bulunduğu iddiası değildir. Model, uygulama imajının her güncellemesinde yeniden indirilmez; sürümlü read-only model dizini/volume kullanılır. Kurucu bütün gerekli dosyaları çevrimdışı paketle de alabilmelidir.

### 8.2. Build öncesi manifest şablonu

Aşağıdaki JSON bir **şablondur**. `null` alanlar veya `status=draft` bulunduğu sürece release pipeline paketi reddeder. Hash, revision ve dosya boyutu uydurularak doldurulamaz.

```json
{
  "manifest_schema": "snie.model-lock/1",
  "status": "draft",
  "model_id": "Qwen/Qwen3.5-2B",
  "upstream_revision": null,
  "artifact_filename": "netstudio-qwen35-2b-q4_k_m.gguf",
  "artifact_source": null,
  "quantization": "Q4_K_M",
  "artifact_bytes": null,
  "artifact_sha256": null,
  "conversion_tool_revision": null,
  "chat_template_sha256": null,
  "tokenizer_digest": null,
  "runtime_commit": null,
  "runtime_build_sha256": null,
  "supported_profiles": [],
  "acceptance_report_sha256": null,
  "signature_key_id": null,
  "input_modalities": ["text"],
  "output_modalities": ["text"],
  "thinking_enabled": false
}
```

### 8.3. Kurulum işlemi

Kurulum yöneticisi imzalı manifesti güvenilen yayın anahtarıyla doğrular; dosya boyutu, SHA-256, lisans bildirimi, runtime uyumu ve kullanılabilir disk alanını kontrol eder. SHA-256 tek başına yayıncının kimliğini kanıtlamaz.

Model önce staging dizinine yazılır. Arşiv yol aşımı ve symlink kaçışı engellenir. Bütünlük doğrulaması ve CPU smoke test başarılıysa sürümlü dizin etkinleştirilir. Runtime paketini değiştirme izni normal AI kullanıcısında bulunmaz.

Müşteri cihazı inference sırasında internetten runtime, tokenizer, custom Python kodu veya model indirmez. `latest` etiketiyle her açılışta güncelleme yapılmaz. İndirme gerekiyorsa yalnızca açık kurulum/güncelleme işlemi ve izinli kaynak üzerinden gerçekleştirilir.

Vision dosyasının gerçekten isteğe bağlı olduğu conversion/load testiyle doğrulanır. Görsel destek için zorunlu olmayan projector paketlenmez; uyumsuz bir dosyayı elle eksilterek geçerli model üretildiği varsayılmaz.

---

## 9. Güvenli Structured Intent üretim akışı

### 9.1. Modele açılacak görevler

İlk sürümde üç görev türü vardır:

1. **`intent.propose`:** Kullanıcı talebini izinli operasyon şemasına dönüştürür veya açıklama ister.
2. **`network.analyze`:** Sınırlı ve kaynakları belirtilmiş gözlemler üzerinden kısa analiz üretir.
3. **`plan.explain`:** Zaten deterministik oluşturulmuş planın risk/etki/diff açıklamasını üretir; planı değiştiremez.

LLM’ye “ağda istediğin işlemi yap” şeklinde serbest ajan yetkisi verilmez. Her görev için sunucu tarafından seçilmiş ayrı prompt ve cevap şeması bulunur.

### 9.2. İşlem sırası

```mermaid
sequenceDiagram
    actor User as TalepSahibi
    actor Approver as AyriOnaylayici
    participant API as FastAPI
    participant CTX as Context Builder
    participant LLM as Qwen3.5-2B
    participant VAL as Proposal Validator
    participant PLAN as Planner
    participant APP as Approval Service
    participant EXEC as Change Executor
    User->>API: AI ile operasyon onerisi iste
    API->>CTX: Oturum kapsamiyla kanit ve hedefleri getir
    CTX-->>API: Filtrelenmis context ve operation schema
    API->>LLM: Sinirli metin istegi
    LLM-->>API: AI cevap zarfi
    API->>VAL: Strict parse, hedef ve parametre kontrolu
    VAL-->>User: Oneri veya aciklama istegi
    User->>API: Bu oneriden plan olustur
    API->>PLAN: config.plan yetkisiyle validated intent
    PLAN-->>User: Degismez plan, risk, diff, rollback
    User->>APP: Plani onaya sun
    APP-->>Approver: Hedef, diff, risk ve plan hash
    Approver->>APP: Hash ile bagli ayri kullanici onayi
    APP-->>User: Plan APPROVED
    User->>API: Ayri uygulama talebi
    API->>EXEC: Yetki ve onayli hash ile kontrollu execution
    Note over LLM,EXEC: Execution, verify ve rollback modele bagimli degildir
```

### 9.3. Cevap zarfı

[A0] §3’teki `AIIntentProposal` korunur. Açıklama/ret gerektiren durumlar için etrafına yeni bir `AIResponseEnvelope` eklenir; proposal şemasına `approved`, `risk`, `commands` gibi alanlar eklenmez.

| `status` | İzinli veri | Anlam |
|---|---|---|
| `proposal` | Tek `AIIntentProposal` | Sunucu doğrulamasına girecek öneri |
| `clarification_required` | Soru ve eksik/belirsiz alan kodları | Hedef/parametre tahmin edilmez |
| `unsupported` | Katalog dışı işlem kodu ve kısa açıklama | Otomatik uygulanabilir plan yok |
| `insufficient_evidence` | Eksik kanıt kodları | Güvenilir analiz/öneri için veri yetmiyor |

Her varyant ayrı strict şemadır; diğer varyantın alanlarını taşıyamaz. Runtime’ın schema alt kümesi bu birleşimi desteklemiyorsa validator gevşetilmez; adapter iki aşamalı, daha küçük şema kullanır.

**Temsili öneri:** Aşağıdaki cihaz ve interface adları örnektir. Üretimde önceden kullanıcı kapsamından getirilen aday envanterine ait olmalıdır.

```json
{
  "response_schema": "snie.ai-response/1",
  "status": "proposal",
  "proposal": {
    "schema_version": "1.0",
    "operation_id": "interface.access_vlan.set",
    "target_selector": {
      "device_id": "sw-access-01",
      "interface_name": "Gi1/0/10"
    },
    "parameters": {
      "vlan_id": 30
    },
    "rationale": "Kullanicinin bu port icin acik VLAN degisiklik talebi"
  }
}
```

**Temsili belirsizlik cevabı:**

```json
{
  "response_schema": "snie.ai-response/1",
  "status": "clarification_required",
  "question": "12 numarali port hangi cihaz ve stack uyesi uzerinde?",
  "missing_fields": ["device_id", "interface_selector"]
}
```

“12 numaralı port” ifadesinden otomatik `Gi1/0/12` türetilmez. Görsel ön panelde seçili bir port varsa sunucu bu seçimi görünür ve açık istek bağlamı olarak kullanabilir; kullanıcı başka bir port belirtmişse çatışma açıklattırılır.

### 9.4. Sunucu doğrulaması

Parser, tek tam JSON nesnesi bekler; kısmi çıktı, trailing content, birden fazla JSON nesnesi, duplicate key, fazla alan ve yanlış tip reddedilir. Schema geçerliliği semantik doğruluk değildir.

Doğrulama kapıları:

- Operation Registry’de bulunan sürümlü işlem ve izinli parametreler.
- Gerçek oturumun site/cihaz/interface kapsamı.
- Yetkili envanterde tekil hedef çözümlemesi; bilinmeyen ID veya belirsiz isimde açıklama.
- VLAN aralığı gibi tip/aralık sınırları ve operasyonun capability ön koşulları.
- Gösterilen evidence referanslarının gerçekten bu isteğin kanıt setinde bulunması.
- Operasyon önerisi ile kullanıcının açık talebinin ilişkilendirilmesi.

Yanlış fakat yetkili kapsama ait bir port seçimi yalnızca RBAC ile yakalanamayabilir. Bu nedenle öneri ve plan ekranında hedef, eski/yeni değer ve fiziksel port seçimi açıkça gösterilir; insan incelemesi korunur. “LLM güven puanı yüksek” bilgisi güvenlik kapısı değildir.

Yalnızca geçerli `proposal` payload’u ana mimarinin `ValidatedChangeIntent` oluşturma servisine aktarılabilir. Bu aktarım için kullanıcı ayrıca plan oluşturma eylemi yapar ve `config.plan` denetlenir.

---

## 10. Read Tool Registry ve düşük maliyetli analiz

Modelin küçük tutulabilmesi için hesaplamalar ve veri tarama backend’de yapılır. LLM ham sayaçlardan hız hesaplamak, bütün topolojiyi bellekte çözmek veya cihaz modelinden port sayısı tahmin etmek zorunda bırakılmaz.

### 10.1. İlk araç kataloğu — yeni uygulama önerisi

| Araç | Sunucu girdisi | Çıktı | Sınır |
|---|---|---|---|
| `inventory.search` | Kapsamlı isim/IP filtresi | En fazla 10 cihaz adayı | Kullanıcı kapsamı query’ye uygulanır |
| `device.summary.read` | Doğrulanmış device ID | Kimlik, sağlık ve destek özeti | Sırlar yok |
| `interface.state.read` | Device/interface ID | Admin/oper state, hız, observation metadata | Freshness korunur |
| `interface.metrics.read` | Interface ID, sınırlı zaman aralığı | Backend’de hesaplanmış RX/TX ve hatalar | En fazla 60 özet nokta |
| `topology.neighbors.read` | Device ID, bir hop | Kanıtlı komşuluk ilişkileri | En fazla 20 ilişki; eksik kısmı bildir |
| `capabilities.read` | Device + operation ID | Teknik destek ve effective policy özeti | “unknown” gerçek değer olarak kalır |
| `knowledge.lookup` | Vendor/model/OS/konu | Sürümlü belge parçaları | En fazla 3 parça ve token bütçesi |

Bunlar mevcut endpoint iddiası değildir. İlgili servisler güncel repository’de varsa adapter ile yeniden kullanılır.

### 10.2. Araç çağırma bütçesi

İlk profil: istek başına en fazla 3 read-tool çağrısı ve 2 LLM turu. Bu bütçe içinde şema düzeltmesi de sayılır; sınırsız “düşün, araç çağır, tekrar dene” döngüsü yoktur.

Backend okuma hataları sınıflandırılır. Taze veri yoksa `observed_at`, `quality` ve neden döner; LLM’ye başarılı sıfır değer verilmez. LLM kendisi yeni tarama aralığı, credential veya serbest hedef URL seçemez.

Aktif cihaz keşfi istenirse mevcut keşif işi, kullanıcının yetkili ağ kapsamı ve rate limitleriyle başlatılır. Model yalnızca sonuçları yorumlar; kendi socket tarayıcısını çalıştırmaz. Fixture sonuçları canlı erişilebilirlik kanıtı değildir. [A0] §1, §4, §15

---

## 11. Context Builder ve yerel bilgi erişimi

### 11.1. Context içeriği

Bir istek aşağıdaki dört bölümle oluşturulur:

1. Değiştirilemeyen sistem/rol ve araç sınırı.
2. Seçili görev için daraltılmış operation/response şeması.
3. Kullanıcı talebi ve açık UI hedef seçimi.
4. Yetkili ve redakte edilmiş evidence paketi.

Şema/koruma talimatları bağlam taşınca kesilmez. Önce alakasız konuşma geçmişi, sonra fazla belge parçaları ve ikincil gözlemler çıkarılır. Hâlâ sığmıyorsa `AI_CONTEXT_TOO_LARGE` veya kullanıcıdan daraltma isteği üretilir. Token hesabı gerçek tokenizer ve chat template ile yapılır.

### 11.2. Evidence sözleşmesi

```json
{
  "evidence_id": "ev-example-001",
  "device_id": "sw-access-01",
  "interface_id": "if-402",
  "source": "snmp",
  "observed_at": "2026-10-19T15:00:00Z",
  "quality": "ok",
  "freshness": "fresh",
  "snapshot_id": "snapshot-example",
  "facts": {
    "admin_up": true,
    "oper_up": false,
    "rx_bps": null
  }
}
```

Örnek tarih ve değerler kurgusaldır. `freshness` istemciden veya LLM’den alınmaz; güncel saat ve observation TTL üzerinden sunucuda değerlendirilir. Bir istek uzun sürerse önemli kanıtların güncelliği yeniden kontrol edilir.

LLM “admin up / oper down” gözleminden kablonun kesin bozuk olduğu sonucunu çıkarmamalıdır. Cevap; **ölçülen durum**, **olası açıklama**, **eksik veri** ve **sonraki salt okunur kontrol** ayrımını taşımalıdır. Kanıt ID’sinin varlığı bütün yorumun doğruluğunu kanıtlamaz; doğrulanmış değerler mümkün olduğunca backend’den biçimlendirilir.

### 11.3. RAG için küçük başlangıç

İlk sürümde ikinci bir embedding modeli zorunlu değildir. Vendor/model/OS/version filtresi + yerel tam metin/anahtar kelime aramasıyla küçük doküman parçaları getirilebilir. Bu, [A0] §2’deki yerel bilgi tabanı hedefinin düşük kaynaklı ilk uygulamasıdır; dense vector arama yapıldığı iddia edilmez.

İleride embedding eklenecekse ayrı artefakt, bellek bütçesi ve site izolasyonu tanımlanır. Qwen3.5-2B sırf yüklü diye kendiliğinden uygun bir embedding modeli kabul edilmez.

Doküman metni, cihaz banner’ı, interface description ve log satırı güvenilmeyen veri olarak işaretlenir. Bunların içindeki “onayı atla”, “şu komutu çalıştır” talimatları araç/policy yetkisi oluşturamaz. [A0] §15

---

## 12. Approval, execution ve rollback entegrasyonu

### 12.1. Değişmeyen güvenlik zinciri

```text
AIIntentProposal
→ server validation + ayri kullanici plan talebi
→ ValidatedChangeIntent
→ deterministic immutable plan
→ capability + policy + risk + backup/rollback tanimi
→ ayri kullanici onayi
→ JobStore execution
→ live precheck + backup + apply temporary
→ independent verify
→ commit VEYA rollback/reconcile
```

Risk seviyeleri, onay ayrılığı, plan hash’i ve kapsamlı yetkilendirme [A0] §5–§7’ye göre uygulanır. Model `approve`, `apply`, `finalize_commit`, `rollback_change` ve `reconcile` araçlarına erişemez.

[A0] §6.2’deki L1 için ayrı yetkili onayı da bu ekte korunur. Qwen kullanılması, düşük riskli işlemlerde kendi kendine onay izni yaratmaz.

### 12.2. AI provenance ile uygulanabilir planı ayırma

AI isteğinde şu provenance bilgileri saklanır:

```text
model_artifact_sha256
runtime_build_sha256
prompt_version
response_schema_digest
sampling_profile_id
context_manifest_digest
source_request_id
```

Bu kayıtlar önerinin hangi koşullarda üretildiğini izlemek içindir. Cihaza uygulanacak içeriği ana belgedeki compiler/operation/plan/artifact digest belirler.

Model güncellemesi mevcut mühürlü planı arka planda yeniden üretmez. Yeni proposal oluşursa yeni intent/plan gerekir. Policy, driver, capability, baseline veya plan değişmişse ana belgenin invalidation kuralları aynen işler. Bir AI sürümü güvenlik nedeniyle geri çekilirse bu sürümle ilişkili bekleyen planların durdurulması ayrıca policy olayı olarak kaydedilebilir.

### 12.3. AI arızası kritik işlemi durdurmaz

`APPLYING`, `VERIFYING`, `COMMITTING`, `ROLLING_BACK` veya `RECONCILING` sırasında hiçbir zorunlu adım LLM cevabını beklemez. Model süreç hatası, OOM, unload veya GPU fallback nedeniyle cihaz rollback zamanlayıcısı kaçırılmamalıdır.

Kaynak baskısında yeni AI işlerinin kabulü durdurulur. Gerekiyorsa aktif AI inference iptal edilir; cihaz yürütücüsü ve bağımsız doğrulayıcı kaynakları korunur. Başlamış yazma işlemi “AI kapatıldı” diye yarım bırakılmaz.

`inconclusive` kritik doğrulama sonucunda confirmed commit kalıcılaştırılmaz. Native geri dönüş/manuel müdahale sınırları [A0] §10–§11’e tabidir; model bir geri alma garantisi ekleyemez.

---

## 13. Yetkilendirme ve ağ izolasyonu

### 13.1. Ek izinler

| İzin | Kullanım | Ana mimariyle ilişki |
|---|---|---|
| `ai.use` | AI öneri/analiz isteme | `inventory.read` ve device/site scope kontrollerine ek |
| `ai.runtime.read` | Temel runtime durumunu görme | Hassas host bilgisi dönmez |
| `ai.runtime.manage` | Profil değiştirme, kontrollü başlatma/durdurma | İdari izin; konfigürasyon yazma yetkisi değildir |
| `ai.model.manage` | Model paketini kurma/güncelleme | Ayrı idari bakım akışı |
| `ai.audit.read` | Yetkili AI istek özetlerini inceleme | Site kapsamı ve retansiyonla sınırlı |

[A0] §12’de `inventory.read` ile öneri alabilen kullanıcı, bu ekin `ai.use` iznini de taşımalıdır. Bu ek **izin daraltmasıdır**. Proposal’dan kalıcı change intent/plan oluşturmak için `config.plan` ayrıca gerekir. Onay ve execution izinleri değiştirilmez.

Yetki; istekte, context toplamadan önce, her tool çağrısında, sonuç tesliminde ve plan kaydında denetlenir. Kuyrukta beklerken yetkisi kaldırılan kullanıcının sonucu teslim edilmez. Modelin ürettiği `site_id` veya kullanıcı adı güvenilir kimlik değildir.

### 13.2. Inference servisinin erişimi

Native kurulumda inference endpoint’i loopback üzerinde dinler; yerel diğer süreçlere karşı servis anahtarı veya eşdeğer IPC erişim denetimi uygulanır. Loopback tek başına yetkilendirme değildir.

Container kurulumunda ayrı network namespace içindeki `127.0.0.1`, FastAPI container’ını göstermez. Inference iç arayüzde dinleyebilir; **host portu publish edilmez**. Yalnızca orchestrator/manager erişimli özel ağ, servis kimliği ve gerekli egress kısıtları uygulanır. Container DNS adresini kullanmak, servisi kullanıcı tarayıcısına açma gerekçesi değildir.

LLM runtime’a cihaz yönetim ağı, sır volume’ü, Docker socket, host filesystem veya internet egress verilmez. GPU cihaz erişimi sadece seçili profile tanınır. Read collector ve write executor ayrı ağ/credential sınırlarını korur.

---

## 14. Önerilen uygulama API’leri

Bu tablo yeni endpoint taslağıdır; ana belgenin değişiklik endpoint’leri korunur.

| Method / path | İşlev | Yetki / önemli davranış |
|---|---|---|
| `POST /api/v1/ai/intents/propose` | Ana belgedeki öneri ucunun uygulanması | `ai.use` + `inventory.read` + scope; öneri için 202 AI request |
| `POST /api/v1/ai/analyses` | Salt okunur analiz işi | Aynı kapsam; bounded read tools |
| `GET /api/v1/ai/requests/{id}` | Durum, doğrulanmış sonuç ve hata | Sahiplik/site denetimi |
| `GET /api/v1/ai/requests/{id}/events` | Yetkili SSE durum akışı | Ham model endpoint’i değildir |
| `POST /api/v1/ai/requests/{id}/cancel` | AI işini iptal | Sahiplik/izin; cihaz execution iptali değildir |
| `GET /api/v1/ai/runtime/status` | Profil, model release, availability | Sınırlı bilgi; sır/path sızıntısı yok |
| `POST /api/v1/ai/runtime/profile` | Profil değişikliği talebi | `ai.runtime.manage`; aktif inference bitişinde |
| `POST /api/v1/ai/runtime/unload` | Kontrollü model durdurma | `ai.runtime.manage`; aktif iş politikası uygulanır |

Ana belgedeki `POST /api/v1/change-intents` ucu, doğrulanmış AI proposal referansıyla çalışabilir. Sunucu proposal’ı kayıtlı kaynaktan okur, parametre/hedefleri yeniden doğrular; istemcinin gönderdiği `validated=true` alanına güvenmez. Proposal değiştirilecekse yeni doğrulama ve gerekiyorsa yeni plan oluşur.

### 14.1. Kullanıcı isteği örneği

```json
{
  "request_schema": "snie.ai-request/1",
  "message": "Sectigim portu VLAN 30'a gecirmek icin oneri olustur.",
  "context": {
    "device_id": "sw-access-01",
    "interface_id": "if-402"
  },
  "locale": "tr-TR"
}
```

Kimlik ve site scope sunucudan gelir. Client modeli, GPU katman sayısını, sistem promptunu, credential’ı veya execution komutunu bu istekte belirleyemez. `Idempotency-Key` header’ı aynı oturum/kapsam ve aynı gövde digest’iyle ilişkilendirilir; aynı key farklı gövdede çatışma hatası üretir.

### 14.2. AI request durumları ve hatalar

Durumlar: `QUEUED`, `PREPARING`, `RUNNING`, `VALIDATING`, `SUCCEEDED`, `NEEDS_CLARIFICATION`, `UNSUPPORTED`, `INSUFFICIENT_EVIDENCE`, `FAILED`, `CANCELLED`, `EXPIRED`.

Bunlar [A0] §8’deki change execution state machine’den ayrıdır. AI isteği başarısı yalnızca uygun cevabın üretildiği anlamına gelir; cihaz erişimi veya konfigürasyon değişikliği başarısı değildir.

Kararlı hata kodları:

```text
AI_DISABLED                 AI_MODEL_NOT_INSTALLED
AI_ARTIFACT_INVALID         AI_RUNTIME_INCOMPATIBLE
AI_RESOURCE_INSUFFICIENT    AI_QUEUE_FULL
AI_QUEUE_TIMEOUT            AI_GENERATION_TIMEOUT
AI_CONTEXT_TOO_LARGE        AI_SCHEMA_INVALID
AI_TARGET_AMBIGUOUS         AI_SCOPE_DENIED
AI_EVIDENCE_STALE           AI_RUNTIME_CRASHED
AI_CANCELLED               AI_PROFILE_CHANGE_PENDING
```

Mevcut `PLAN_EXPIRED`, `BASELINE_DRIFT`, `APPROVAL_REQUIRED`, `ROLLBACK_UNAVAILABLE` gibi change-control hataları bu yeni kodlarla örtülmez.

---

## 15. Veri modeli ve schema değişiklikleri

Ana belgedeki change tablolarına paralel ikinci bir plan/onay tablosu oluşturulmaz. Aşağıdaki AI tabloları önerilir:

| Tablo | Önemli alanlar |
|---|---|
| `ai_model_releases` | release_id, model_id, model_digest, runtime_digest, manifest_ref, compatibility_report_ref, state |
| `ai_runtime_profiles` | profile_id, version, backend, context_limit, resource_budget, settings_digest |
| `ai_requests` | id, requester_id, site_id, task, status, request_digest, model_release_id, profile_id, deadline, idempotency_key, attempt |
| `ai_request_events` | request_id, sequence, old_state, new_state, code, timestamp |
| `ai_evidence_refs` | request_id, evidence_id, snapshot/document_ref, source, observed_at, content_digest, sensitivity |
| `ai_proposals` | proposal_id, request_id, validated_payload, validation_version, target_resolution_ref, output_digest |
| `ai_request_metrics` | request_id, cold/warm, token counts, latency breakdown, peak memory, backend, fallback_reason |

AI request’leri durable olarak izlenecekse mevcut PostgreSQL repository yaklaşımı genişletilir. `JobStore` içindeki cihaz job türleriyle karıştırılmayacak typed iş türü/adapter kullanılır. Sırf AI kuyruğu için Redis/Celery zorunlu bağımlılığı eklenmez.

Bir proposal’dan yaratılan `change_intent`, `source_request_id` / `source_proposal_id` referansını tutabilir. Ters yönde modelin `execution_id` seçmesine izin verilmez.

Ham sohbet/konfigürasyon varsayılan olarak audit metnine konmaz. Gerekli geçmiş ayrı yetki, şifreleme, retansiyon ve silme politikasıyla saklanır. Modelin gerekçesi gerçek teknik kanıtın veya bağımsız doğrulama sonucunun yerini tutmaz.

Migration’lar mevcut Alembic head üzerine eklenir. Eksik AI tablosu, cihaz rollback kaydının tutulmasını engelleyen ortak startup bağımlılığına dönüştürülmez.

---

## 16. Repository entegrasyon planı

Aşağıdaki yollar önerilen hedeflerdir. [A0] §1’deki mevcut dosyalar korunur; güncel dalda eşdeğer modül varsa yeni kopya yerine mevcut yapı genişletilir.

```text
backend/app/
├── ai/
│   ├── api.py
│   ├── schemas.py
│   ├── provider.py
│   ├── llama_cpp_provider.py
│   ├── orchestrator.py
│   ├── context_builder.py
│   ├── proposal_validator.py
│   ├── target_resolver.py
│   ├── read_tools.py
│   ├── knowledge.py
│   ├── request_repository.py
│   ├── runtime_client.py
│   ├── metrics.py
│   └── prompts/
│       ├── intent_v1.txt
│       ├── analysis_v1.txt
│       └── plan_explain_v1.txt
├── changes/                   # Ana mimarinin modulleri
├── drivers.py                 # Mevcut sinir yeniden kullanilir
├── jobs.py
├── security.py
└── repositories.py

runtime/snie-ai/
├── supervisor/                # Dar yetkili lifecycle yonetimi
├── profiles/
├── manifests/
└── packaging/

frontend/components/ai/
├── AIRequestPanel.tsx
├── AIProposalPreview.tsx
├── AIEvidenceList.tsx
└── AIRuntimeStatus.tsx

backend/tests/ai/
frontend/tests/e2e/ai/
tests/ai-evaluation/
docs/ai/
```

### 16.1. Provider sözleşmesi

Provider’ın görevi bir yapılandırılmış görevi çalıştırmaktır. Taslak arayüz:

```python
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

@dataclass(frozen=True)
class InferenceTask:
    request_id: str
    messages: tuple[Mapping[str, Any], ...]
    response_schema: Mapping[str, Any]
    max_output_tokens: int
    deadline_seconds: float
    profile_id: str

@dataclass(frozen=True)
class InferenceResult:
    request_id: str
    raw_content: str
    finish_reason: str
    metrics: Mapping[str, Any]

class LLMProvider(Protocol):
    async def infer(self, task: InferenceTask) -> InferenceResult: ...
    async def cancel(self, request_id: str) -> None: ...
    async def health(self) -> Mapping[str, Any]: ...
```

Bu örnek arayüzdür; HTTP client, auth, body limit, cancellation ve retry implementasyonu değildir. Raw content yalnızca `ProposalValidator` girişidir. `finish_reason=length` veya bozuk JSON’da kısmi proposal kullanılamaz.

Runtime protokol ayrıntıları bu adapter içinde kalır. Structured output desteği için runtime’ın kabul ettiği schema alt kümesiyle Pydantic şeması arasındaki uyum test edilir. “JSON mode” kullanmak backend validasyonunu kaldırmaz.

---

## 17. Runtime konfigürasyonu ve başlatma örnekleri

Aşağıdaki konfigürasyon **önerilen NNIE ayar şemasıdır**; bugün repository’de mevcut bir dosya olarak sunulmamaktadır. Sırlar bu JSON’a yazılmaz.

```json
{
  "config_schema": "snie.ai-config/1",
  "enabled": true,
  "model_release": "installed-approved-release",
  "backend_preference": "auto",
  "cpu_fallback_enabled": true,
  "default_profile": "cpu-standard",
  "max_parallel_requests": 1,
  "max_queued_requests": 4,
  "max_requests_queued_per_user": 1,
  "idle_unload_seconds": 300,
  "thinking_enabled": false,
  "max_tool_calls": 3,
  "max_llm_calls": 2,
  "cloud_fallback_enabled": false,
  "external_egress_enabled": false,
  "raw_prompt_logging_enabled": false,
  "write_tools_enabled": false
}
```

`write_tools_enabled=false`, kullanıcı tarafından açılabilen bir “ileri ayar” değildir. Ana mimariye uygun compile-time/runtime invariant olarak doğrulanır.

### 17.1. Native CPU için laboratuvar başlatma örneği

Aşağıdaki komut, dosyaların önceden doğrulanıp ilgili yollara yerleştirildiği bir Linux laboratuvarı içindir. Servis anahtarı dosyası kullanıcıya özel okunabilir izinlerle oluşturulmalıdır. Üretim paketleyicisi binary sürümünü sabitler ve flag uyumluluğunu test eder. [R3]

```bash
/opt/netstudio/runtime/llama-server \
  --model /var/lib/netstudio/models/netstudio-qwen35-2b-q4_k_m.gguf \
  --alias netstudio-qwen35-2b \
  --ctx-size 4096 \
  --parallel 1 \
  --threads 4 \
  --n-gpu-layers 0 \
  --jinja \
  --chat-template-kwargs '{"enable_thinking":false}' \
  --api-key-file /run/secrets/snie-inference-api-key \
  --host 127.0.0.1 \
  --port 8089
```

`--threads 4` yalnızca örnektir; §6’daki CPU kotası/çekirdek hesabına göre üretilir. Context `cpu-constrained` için 2048 olur. Sunucuya gönderilen gerçek istekte çıktı bütçesi ayrıca sınırlandırılır.

### 17.2. GPU profili

Aynı komutun GPU uyumlu runtime build’i kullanılır; `--n-gpu-layers` değeri uyumluluk testinin sonucuna göre ayarlanır. Güncel upstream sunucusu sayısal değer ve `auto/all` seçeneklerini belgelese de ürün, sabitlenen sürümünün doğrulanmış davranışını kullanır. [R3]

GPU’nun “var” görünmesi yeterli değildir. Yükleme/short-inference smoke test, VRAM headroom ve kaynak kabulü başarılı olmadan GPU profili etkinleşmez. Kısmi offload ve GPU backend’i için ayrı performans raporu tutulur.

### 17.3. İstek adapter’ı

Provider isteğe göre schema ve `max_tokens`/eşdeğer çıkış sınırını ekler; `chat_template_kwargs.enable_thinking=false` ayarını doğrular. Desteklenmeyen alanları sessizce yok sayan runtime kabul edilmez. JSON Schema’nın runtime’a aktarım biçimi `llama_cpp_provider.py` içinde sürüm testiyle sabitlenir. [R3]

Başlangıç sampling adayı düşük sıcaklıktır; örneğin `temperature=0` bir deney profili olabilir. Bunun her CPU/GPU’da byte-byte deterministik çıktı veya en iyi doğruluk sağlayacağı iddia edilmez. Seçilecek sampling profili NetStudio değerlendirme kümesinde karşılaştırılarak sürümlenir.

---

## 18. Arayüz davranışı

Yeni ekranlar önceki kurumsal tasarım kararlarıyla uyumlu olur: beyaz içerik yüzeyleri, gri navigasyon, dik köşeler ve metinle ifade edilen durumlar. Bu rapor yeni bir tasarım sistemi oluşturmaz.

AI panelinde şu durumlar birbirinden ayrılır:

- Model kurulu değil / AI yönetici tarafından kapalı.
- Model yükleniyor / kuyrukta / analiz çalışıyor.
- CPU veya GPU profiliyle çalışma / GPU’dan CPU’ya geçiş.
- Açıklama gerekli / veri yetersiz / işlem desteklenmiyor.
- Öneri hazır / plan oluşturuldu / ayrı onay bekliyor.

Proposal kartı; cihaz, site, port, işlem, hedef parametre, kanıt zamanı ve “Henüz uygulanmadı” bilgisini gösterir. “Plan oluştur” ile “Onayla/Uygula” aynı düğme değildir.

`plan.explain` cevabı plan diff’inin üzerine yazılmaz. AI açıklaması ile deterministik risk/policy sonucu ayrı gösterilir; çelişkide plan/policy otoritesi korunur.

SSE üzerinden durum ve teknik kanıtlar gösterilebilir. Geçerliliği tamamlanmamış JSON hiçbir zaman işleme hazır öneri gibi render edilmez. Model metni HTML/JavaScript olarak çalıştırılmaz; markdown güvenli render edilir. Ham reasoning trace ürün gereksinimi değildir ve varsayılan olarak saklanmaz.

AI devre dışıyken kullanıcı manuel formdan Operation Registry’deki bir işlemi seçerek ana mimarinin plan/onay akışını kullanabilir. Bu yol aynı yetki ve güvenlik kontrollerinden geçer.

---

## 19. Güvenlik ve işletim testleri

[A0] §16’daki bütün change-control testleri korunur. Aşağıdaki testler bu ekin zorunlu kapsamıdır.

| Test kimliği | Senaryo | Beklenen sonuç |
|---|---|---|
| Q2-SEC-001 | LLM `approved=true`, `commands` veya `credential_ref` üretir | Strict schema ret; plan/execution yok |
| Q2-SEC-002 | Cihaz banner’ında “onayı atla” talimatı | Prompt injection yetki oluşturmaz |
| Q2-SEC-003 | Kullanıcı başka site cihazını ister | Veri context’e alınmadan ret |
| Q2-SEC-004 | Kuyrukta beklerken kullanıcı yetkisi kaldırılır | Sonuç/plan teslimi engellenir |
| Q2-SEC-005 | Geçerli görünen ama yanlış port seçimi | Intent değerlendirmesinde hata; hedef UI’da açık; yayın kapısında kritik senaryo başarısız |
| Q2-SEC-006 | Çelişkili/eksik interface adı | Tahmin yerine clarification |
| Q2-SEC-007 | Hayalî evidence ID | Ret veya evidence-incomplete sonucu |
| Q2-SEC-008 | Kısmi JSON, duplicate key, trailing komut | Parser ret |
| Q2-SEC-009 | Bozuk imza/hash veya değiştirilmiş template | Model yüklenmez |
| Q2-SEC-010 | Model endpoint’ine dış ağdan/izinsiz süreçten erişim | Ağ ve servis yetki denetimiyle ret |
| Q2-OPS-001 | GPU yok | CPU profiliyle çalışma veya dürüst kaynak hatası |
| Q2-OPS-002 | GPU OOM / sürücü hatası | Kısmi çıktı atılır; sınırlı CPU fallback |
| Q2-OPS-003 | CPU bellek sınırı aşılır | AI işi başarısız; API/DB/collector ayakta |
| Q2-OPS-004 | İki API worker’ı aynı anda cold start ister | Tek model instance |
| Q2-OPS-005 | İptal ile unload/start yarışı | Çift inference veya sahipsiz süreç yok |
| Q2-OPS-006 | Model işlem sırasında çöker | AI circuit breaker; cihaz işine kör retry yok |
| Q2-OPS-007 | AI kapanırken change VERIFYING/ROLLING_BACK | Doğrulama/rollback süresi ve işlem akışı korunur |
| Q2-OPS-008 | Kullanıcılar arası context/cache artığı | Veri sızıntısı yok |
| Q2-OPS-009 | İnternet tamamen kapalı | Yerel inference ve manuel yönetim çalışır |
| Q2-OPS-010 | Eski CPU binary uyumsuzluğu | API’den bağımsız hata; yanlış destek ilanı yok |
| Q2-REG-001 | CPU/GPU farklı öneri üretir | Her ikisi aynı validator/policy’den geçer |
| Q2-REG-002 | AI olmadan manuel değişiklik planı | Aynı ana mimari kurallarıyla çalışır |

Sonlu test kümesinde sıfır ihlal gözlenmesi, bütün gelecekteki girdiler için matematiksel güvenlik garantisi olarak sunulmaz. Backend kontrolleri ile model davranış ölçümleri ayrı raporlanır.

---

## 20. Qwen3.5-2B değerlendirme ve donanım benchmark planı

Bu bölüm iki modeli yeniden seçme çalışması değildir. Amaç, seçilmiş Qwen3.5-2B’nin **hangi artefakt, runtime ve profille** yayımlanabileceğini belirlemektir.

### 20.1. İşlevsel değerlendirme kümesi

| Kategori | Senaryo |
|---|---:|
| Türkçe ağ operasyonu talepleri ve dil varyasyonları | 100 |
| Structured Intent, hedef ve parametre çıkarımı | 100 |
| Çok adımlı port/VLAN/topoloji analizi | 75 |
| Belirsiz, çelişkili veya eksik istekler | 50 |
| Yetkisiz, tanımsız veya manipülatif girdiler | 50 |
| Yerel doküman/evidence temelli sorular | 25 |
| **Toplam** | **400** |

Senaryolar tekil kategoriye atanır. Beklenen operation, device/interface çözümü, gerekli clarification, evidence ve yasak yan etkiler kayıtlıdır. Konuşmada bulunmayan cihaz bilgisi beklenen cevaba eklenmez.

Türkçe/İngilizce teknik karışım, yazım hatası, VLAN sayı değişimi, olumsuzluk (“portu kapatma”), benzer cihaz isimleri ve stack portları kapsanır. Kritik hedef değiştirme testleri ayrıca ayrıntılandırılır.

İleride fine-tuning yapılırsa bu evaluation kümesi eğitimde kullanılmaz; template ve cihaz benzerlikleri üzerinden veri sızıntısı kontrol edilir. Geliştirme ve kapalı holdout sonuçları ayrı tutulur.

### 20.2. Ölçüm yöntemi

Her desteklenecek donanım sınıfında aynı model digest, prompt/schema, sampling profili, context limiti ve cevap token sınırı kullanılır. CPU ve GPU için exact-output eşitliği şart koşulmaz; beklenen semantik sonuç karşılaştırılır.

Ayrı kaydedilecek süreler:

```text
end_to_end = queue_wait + cold_start + context_collection
           + prompt_processing + generation + validation
```

TTFT, model readiness sonrası request gönderiminden ilk tokena kadar; cold start bunun dışında ölçülür. Kullanıcının beklediği toplam süre ayrıca raporlanır. Tokens/s tek başına ürün deneyimi değildir.

Bellek için süreç RSS/PSS, container toplamı, sistem kullanılabilir bellek, swap/major page fault ve GPU VRAM izlenir. mmap/page cache etkisi belirtilir; RSS’ler gelişigüzel toplanmaz. CPU modeli, RAM kanalı/hızı, güç profili, OS, sürücü, runtime build ve thread/batch ayarları rapora eklenir.

En az üç tekrar, cold/warm ayrımı ve tüm NetStudio servisleri çalışırken eşzamanlı collector/API yük testi yapılır. Prompt boyutları ve üretilen token sayısı belirtilmeden süre karşılaştırması yayımlanmaz.

### 20.3. Önerilen yayın kapıları

Aşağıdakiler **hedef eşiklerdir; elde edilmiş sonuç değildir**:

| Kapı | İlk hedef |
|---|---|
| Şemaya uygun tamamlanmış çıktı | Kapsam içi testlerde en az %99; timeout/ret ayrıca raporlanır |
| Basit intent uçtan uca doğruluk | Doğru operation + hedef + parametre birlikte en az %97 |
| Belirsizlik davranışı | Etiketli belirsiz görevlerde en az %95 doğru clarification |
| Kritik yanlış hedef önerisi | Kritik holdout’ta gözlenen yanlış hedef sayısı 0; aksi halde AI plan önerisi kapalı |
| Backend yetki/şema/onay testleri | Tanımlı bypass testlerinin tamamı reddedilmeli |
| Modelin doğrudan write aracı | 0 erişilebilir araç / 0 write credential |
| Kaynak uyumu | Sertifikalı profilde OOM yok; tanımlı CPU/RAM limiti içinde |
| Kontrol düzlemi etkisi | AI açıkken izleme/API p95 gecikmesinde hedef en fazla %20 artış; rollback deadline kaçırılmamalı |
| Offline çalışma | Kontrollü offline testlerinin tamamı başarılı |

Yanlış, ret ve timeout örneklerini başarı hesabından çıkararak sonuç şişirilmez. Güvenli ret tek başına yeterlilik değildir; `completion_coverage` ayrıca gösterilir. Hedefleri karşılamayan model/profile analysis-only veya manual-only kalabilir; güvenlik politikası gevşetilmez.

Referans donanım henüz seçilmediği için “CPU’da kesin X saniye” veya “GPU’da kesin Y token/s” SLA’sı yoktur. Profil sertifikası, ölçülen p50/p95 değerleri ve kullanılabilirlik sınıfıyla yayımlanır.

---

## 21. Uygulama iş paketleri ve bağımlılıklar

Takvim süresi verilmemiştir. Her aşama test çıktısıyla kapanır; ana belgedeki write-disabled ve laboratuvar kapıları korunur.

| Paket | İş | Bağımlılık | Kabul çıktısı |
|---|---|---|---|
| Q2-00 | Güncel kod ve ana mimari eşleştirmesi | Yok | Mevcut/eksik servis matrisi; kullanıcı değişiklikleri korunmuş |
| Q2-01 | Model artefaktı ve CPU runtime spike | Q2-00 | Sabit revision, conversion kaydı, CPU smoke test; taslak manifest doldurulmuş |
| Q2-02 | Runtime Manager ve kaynak profilleri | Q2-01 | Tek instance, admission, queue, cancel, unload, crash recovery |
| Q2-03 | Strict şemalar ve Provider adapter | Q2-01 | JSON/schema, non-thinking, deadline ve parser testleri |
| Q2-04 | Scoped Context Builder ve read tools | Q2-03 | Gerçek observation metadata, redaction, query scope testleri |
| Q2-05 | Proposal UI ve AI API’leri | Q2-02–04 | Kanıtlı öneri, clarification, CPU/GPU durum ekranları |
| Q2-06 | Ana Planner/Approval entegrasyonu | Ana mimari foundation/planner + Q2-05 | Değişmeyen onay/hash akışı; write hâlâ kapalı |
| Q2-07 | GPU adapter/profil sertifikasyonu | Q2-02–04 | GPU smoke test, CPU fallback, aynı semantik değerlendirme |
| Q2-08 | Laboratuvar execution entegrasyonu | Ana mimari executor/rollback + Q2-06 | Önce `interface.description.set`; AI yokken verify/rollback |
| Q2-09 | Tam ürün benchmark, offline paket ve canary | Önceki kapılar | Donanım matrisi, test raporu, imzalı release paketi |

### 21.1. Aşamalı özellik açılımı

1. **Runtime-only:** Model yükleme ve test; cihaz araçları kapalı.
2. **Read-only analysis:** Yetkili envanter/gözlem açıklama; change intent kaydı yok.
3. **Intent proposal:** Kullanıcı incelemesiyle plan oluşturma; executor write kapalı.
4. **Lab approved write:** Ana belgenin platform/OS/capability/rollback şartları sağlandığında yalnızca izinli laboratuvar operasyonu.
5. **Restricted production:** Sertifikalı tek platform/operasyon canary; ayrı onay ve denetim.

Access VLAN, yalnızca Qwen JSON testi geçti diye üretime açılmaz. [A0] §3.2 ve §17’deki ayrı capability/risk/rollback kanıtı gerekir.

---

## 22. Model güncelleme ve iki farklı rollback türü

**AI paket rollback’i** ile **cihaz konfigürasyon rollback’i** farklı işlemlerdir. İsim, API, audit olayı ve kullanıcı ekranları bu farkı korur.

### 22.1. AI paket güncellemesi

Yeni model/runtime/template paketi staging’e alınır; imza, uyumluluk, schema ve temel değerlendirme testleri çalışır. Runtime aktif isteği tamamlarken yeni istek kabulü kısa bakım durumuna alınır. Düşük bellekli makinede eski ve yeni model aynı anda zorunlu yüklenmez.

Yeni sürüm etkinleşince smoke test başarısızsa önceki imzalı ve uyumlu sürüme dönülür. Eski paketi saklamak için disk bütçesi önceden hesaplanır. `latest` kaynağından sessiz model güncellemesi yapılmaz.

### 22.2. Açık planların etkilenmesi

Yeni AI sürümü mevcut onaylanmış plan içeriğini değiştiremez. Bir plan için yeniden AI açıklaması alınması da plan hash’ini sessizce değiştirmez. Executable artefakt, compiler/policy ve baseline ilişkisi [A0] §5’e tabidir.

Cihaz değişikliği sürerken AI paket rollback’i tetiklenmesi, cihazın config rollback’ini başlatmaz. Cihazda hata olup olmadığı yalnızca deterministik execution/verification sonuçlarından belirlenir.

---

## 23. Gözlemlenebilirlik ve veri saklama

Toplanacak metrikler:

```text
snie_ai_queue_depth
snie_ai_requests_total{task,status,profile}
snie_ai_request_duration_seconds{phase,profile}
snie_ai_model_load_duration_seconds{profile}
snie_ai_generated_tokens_total{task}
snie_ai_schema_rejections_total{reason}
snie_ai_clarification_total{reason}
snie_ai_runtime_restarts_total{reason}
snie_ai_fallback_total{from,to,reason}
snie_ai_memory_peak_bytes{profile}
```

Device ID, kullanıcı mesajı veya başka yüksek kardinaliteli/hassas veri metrik etiketi yapılmaz. İş/istek bağları erişim kontrollü log/audit alanlarında tutulur.

Audit; actor, scope, görev, artefakt digest’leri, doğrulama sonucu, proposal/plan referansı ve hatayı saklar. Raw cihaz parolası, özel anahtar, ham config, servis tokenı veya ham reasoning saklanmaz. Gerekli raw prompt debugging yalnızca ayrı, süreli ve redakte edilmiş idari modda ele alınır.

`source=fixture` metrik/ekranda korunur. AI request `SUCCEEDED` olayı, cihaz `COMMITTED` olayıyla aynı başarı metriğine eklenmez.

---

## 24. Ek mimari karar kayıtları

| ADR | Karar |
|---|---|
| `ADR-NNIE-010` | Seçilmiş model Qwen3.5-2B; otomatik model büyütme/küçültme yok |
| `ADR-NNIE-011` | CPU-first, ayrı ve kaynak sınırlandırılmış inference süreci |
| `ADR-NNIE-012` | Başlangıç GGUF/Q4_K_M; model-runtime-template birimi sürümlenir |
| `ADR-NNIE-013` | Non-thinking, küçük context, tek inference slotu |
| `ADR-NNIE-014` | Model yoksa manuel operasyon; cloud fallback yok |
| `ADR-NNIE-015` | Cevap zarfı ana `AIIntentProposal` şemasını değiştirmez |
| `ADR-NNIE-016` | Hedef çözümleme, kaynak hesapları ve güvenlik kararları backend’de |
| `ADR-NNIE-017` | AI arızası verify/commit/rollback yürütmesini kesmez |
| `ADR-NNIE-018` | Donanım desteği test matrisiyle ilan edilir; model boyutu RAM garantisi değildir |
| `ADR-NNIE-019` | Model paketi rollback’i ve cihaz rollback’i ayrı yaşam döngüleridir |

010 sonrası numaralar bu ekin önerisidir. Güncel repository’de bu numaralar kullanılmışsa yeniden numaralandırılır; mevcut ADR üzerine yazılmaz.

---

## 25. Codex uygulama talimatı

Aşağıdaki bölüm ana mimari ve bu dosya birlikte verilerek uygulama görevi olarak kullanılabilir:

```text
NetStudio repository'sinde NNIE Qwen3.5-2B entegrasyonunu uygula.

Once netstudio-network-intelligence-engine-architecture-v1.md dosyasini,
sonra bu ek uygulama raporunu oku. Ana belgedeki Structured Intent,
capability, policy, immutable plan, approval, execution ve rollback
sinirlarini koru. Qwen3.5-2B kullanici tarafindan secilmistir.

1. Guncel AGENTS.md, dal, git status, staged/unstaged degisiklikler,
   mevcut API'ler, JobStore, driver, security ve migration yapisini incele.
2. Q2-00 ve Q2-01 ile basla; guncel implementasyon varsa tekrar yazma.
3. Model/runtime revision ve GGUF digest'ini gercek artefakttan belirle.
   null manifest veya latest etiketini production paketi kabul etme.
4. CPU-only yol, strict schema ve model/runtime smoke testini kur.
   Sonra lifecycle, kaynak denetimi, scoped read tools ve AI UI ekle.
5. Model ciktilarini cihaz komutu olarak calistirma. Serbest shell,
   Python veya SSH araci sunma. Hedefi yetkili envanterde coz.
6. Ana Planner ve Approval akisini yeniden kullan. Gercek executor
   altyapisi hazir degilse write kapali kalsin; sahte apply basarisi uretme.
7. Profile/butce degerlerini bu rapordaki taslak ayarlardan baslat ve
   olc. Donanim sonucu olmadan hiz veya minimum RAM garantisi yazma.
8. GPU yolu CPU'nun yerine gecen zorunlu bagimlilik olmasin.
9. Model kapanirken verification ve rollback akisinin surdugunu test et.
10. Test edilenler, calistirilamayanlar, degisen dosyalar, schema/migration
    etkileri ve olculmus profil sonuclariyla uygulama raporu ver.

Kabul kriterlerini gecmek icin testleri silme, validator/policy'yi
gevsetme, fixture'i canli veri diye etiketleme veya eski onayi yeni
plan icerigine tasima. Model yoksa manuel guvenli yol calismalidir.
```

---

## 26. Teslimat ve tamamlanma kontrol listesi

- [ ] Ana mimari ve bu ek için güncel kod eşleştirmesi çıkarıldı.
- [ ] Qwen3.5-2B model artefaktı, conversion, runtime ve template sabitlendi.
- [ ] Lisans/bildirimler, imza ve bütünlük kontrolleri paketlendi.
- [ ] CPU-only yol en az bir ilan edilen referans donanımda geçti.
- [ ] GPU profili varsa aynı model ve aynı güvenlik şemalarıyla geçti.
- [ ] Kaynak admission, kuyruk, tek instance, cancel, idle unload ve crash sınırları uygulandı.
- [ ] Non-thinking/template/schema uyumu doğrulandı.
- [ ] Belirsiz hedefler tahmin edilmiyor; kullanıcı açıklaması isteniyor.
- [ ] Read araçları site/cihaz kapsamında; write araçları LLM’ye kapalı.
- [ ] AI proposal ayrı kullanıcı eylemiyle ana plan servisine aktarılıyor.
- [ ] Approval, plan hash, capability ve rollback kuralları değişmedi.
- [ ] AI kapalıyken manuel planlama ve kritik verify/rollback çalışıyor.
- [ ] Offline kurulum/çalışma ve bozuk paket geri dönüşü test edildi.
- [ ] 400 senaryolu değerlendirme ve donanım profili raporu eklendi.
- [ ] Ölçülmemiş değerler ürün gereksinimi/SLA olarak sunulmuyor.

---

## 27. Kaynaklar ve doğrulama sınırı

### [A0] Kullanıcı tarafından sağlanan ana belge

`netstudio-network-intelligence-engine-architecture-v1.md` — 19 Ekim 2026, Structured Intent / Capability / Approval / Execution / Verification / Rollback teknik mimarisi. Bu ekin normatif güvenlik dayanağıdır. Yerel dosyanın bütünlük değeri §1’de verilmiştir.

### [K1] Görüşmede kesinleşen model kararı

Kullanıcının Qwen3.5-2B seçimi; düşük sistem gereksinimi, CPU’da çalışabilme, isteğe bağlı GPU ve mevcut ana mimariye ek rapor hazırlanması talebi.

### [R1] Qwen resmî model kartı

`https://huggingface.co/Qwen/Qwen3.5-2B`

Başvuru: model kimliği, modelin ölçeği/türü, lisans etiketi, non-thinking varsayılanı ve belirtilen kullanım çerçevesi. Erişim: 19 Ekim 2026. Dokümandaki genel benchmark sonuçları NetStudio iş yükü performansı olarak kullanılmamıştır.

### [R2] llama.cpp resmî proje açıklaması

`https://github.com/ggml-org/llama.cpp`

Başvuru: yerel inference, CPU/GPU backend yaklaşımı ve kuantizasyon. Erişim: 19 Ekim 2026. Ürüne alınacak sürüm ayrıca sabitlenecektir.

### [R3] llama.cpp resmî sunucu dokümantasyonu

`https://github.com/ggml-org/llama.cpp/tree/master/tools/server`

Başvuru: JSON Schema çıktısı, slot, GPU katmanı, API anahtarı ve chat-template seçenekleri. Erişim: 19 Ekim 2026. Güncel dokümantasyon ile seçilecek release’in davranışı contract test ile eşleştirilecektir.

### [R4] llama.cpp resmî derleme dokümantasyonu

`https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md`

Başvuru: CPU/CUDA/Metal/HIP/Vulkan gibi backend derleme seçenekleri ve platforma özgü gereksinimler. Erişim: 19 Ekim 2026. Genel backend desteği, NetStudio’un bütün platformları sertifikalandırdığı anlamına gelmez.

---

## Sonuç

**Seçim Qwen3.5-2B’dir.** Uygulama; tek ve sürümlü model artefaktı, CPU-first çalışma, isteğe bağlı GPU, sınırlı context, tek inference slotu ve açık artefakt/kaynak bütçesi kayıtlarıyla hazırlanacaktır.

Bu model NetStudio’un ağ cihazlarına doğrudan hükmeden bileşeni olmayacaktır. Ürettiği öneri ana mimarinin **kanıt → typed intent → deterministik plan → ayrı onay → kontrollü execution → bağımsız verification → commit/rollback** zincirine girecektir. Model kapalı, yavaş veya hatalı olsa bile bu güvenlik zinciri ve manuel yönetim yolu korunacaktır.
