# Project Brain: ana ajan tüketimini azaltan yürütme yol haritası

Tarih: 2026-10-31
Durum: KAPANIŞ — 2026-11-01 desteklenen kapsam uygulandı; bağımsız denetim ve Windows Python 3.8/3.11 tam regresyonları geçti.
Kaynak temeli: Project Brain 3.6.1, `7f02f02fe8eec022c2215a53bc36abe94c4ea01a`.
Kapsam: mevcut skill'in kontrollü geliştirilmesi; yeni bir ürün/panel inşası değil.

## 1. Yeni bir ajanın okuyacağı ilk bölüm

Kullanıcının son önceliği: **işin hızlı bitmesi ve özellikle ANA AJANIN token
tüketiminin azalması**. Alt ajan tüketimini en aza indirmek birincil hedef değil.
Kalite, kullanıcı işi ve kurtarılabilirlik korunacak. Güçlü bir işçinin daha fazla
token kullanması, ana ajanın tekrar keşif/uygulama/denetim yapmasını önlüyorsa uygundur.
Bu tercih sınırsız harcama, yeni ücretli hesap veya mevcut kota izinlerini aşma izni değildir.

Bu belge istenen yeni geliştirme için tek yol haritasıdır. Eski, tamamlanmış
`.project-brain/` geliştirme planını yeniden oluşturmayın. Kaynak gerçeklerini
`docs/PROJECT-OVERVIEW.md`, doğrulama gerçeklerini `docs/VERIFICATION.md` içinde tutun.
Bu plan gelecekteki tasarımı anlatır; henüz çalışan özellik gibi sunmayın.

Devralma sırası:

1. Repository `AGENTS.md`, bu bölüm, görev tablosu ve devam kaydını okuyun.
2. Git durumunu ve kaynak sürümünü karşılaştırın. Kullanıcının değişikliklerini koruyun.
3. Kullanıcının uygulamayı istediğinden emin olun. Yol haritası hazırlama talebi tek
   başına bütün runtime değişikliklerini başlatma veya dağıtım yetkisi değildir.
4. Uygulama sırasında yalnızca sıradaki kartı, onun kaynak girişlerini ve gerekli
   çağıranlarını okuyun. Bu belgenin tamamını her işçiye göndermeyin.
5. Gerçek bir bağımlılık veya sözleşme değişmedikçe aynı keşfi ana ajanda tekrarlamayın.
6. Durumu yalnızca aşağıdaki görev tablosunda güncelleyin. Kartta kanıt ve devralma
   notu bırakın; başka bir yol haritası veya audit raporu üretmeyin.

**Uygulama durumu:** 3.7.0 opt-in yürütme çekirdeği ve çevrimdışı kontroller mevcut.
Gerçek Pool daemon testi yalnız sentetik CLI kullandı. Gerçek native ajan ve
ana ajan token ölçümü doğrulaması açık; bu oturum SOLO/SERIAL kaldı.

## 2. Boyut, süre ve teslimat sınırı

Bu orta ölçekli bir runtime genişletmesidir. Mevcut görev, doğrulama, Pool taşıması,
atomik yazma ve kurtarma yardımcıları kullanılacak; sıfırdan platform kurulmayacak.
En zor bölüm ajan başlatmak değil, çökme/eşzamanlılık/entegrasyon doğruluğudur.

| Teslimat | İçerik | Tahmini takvim |
| --- | --- | --- |
| A — ilk fayda | Ana ajan ölçümü, görev bağlamı, kısa sonuç ve istisna görünümü; mevcut seri yürütme korunur | 1–3 odaklı iş günü |
| B — güvenilir ilk sürüm | Kalıcı çalıştırmalar, Pool ve bir desteklenen native host için adaptör sözleşmesi, iki işçi, tek entegrasyon yazıcısı, kurtarma ve testler | Başlangıçtan itibaren toplam 5–10 odaklı iş günü |
| C — genişletilmiş destek | Birden çok native host, gelişmiş dil keşfi, ölçüme göre kapasite ayarı ve gerekiyorsa panel | Toplam 2–4 hafta; ayrıca kapsamlandırılır |

Bunlar kod incelemesine dayalı planlama aralıklarıdır; ölçülmüş teslim süresi veya
garanti değildir. Tek deneyimli uygulayıcı, mevcut Pool'un kullanılabilirliği,
odaklı çalışma ve büyük bir backend değişikliği gerekmemesi varsayılır. OR-01
sonunda tahmin güncellenir. Ajanların düşünme hızı; test, kota, süreç bekleme ve
entegrasyon süresini ortadan kaldırmaz. C, B'nin tamamlanma koşulu değildir.

İlk sürüme alınmayacaklar: yeni web sunucusu/PostgreSQL, dağıtık çok makineli
zamanlayıcı, genel ajan framework'ü, kendi kendini çoğaltan ajan ekipleri, vektör
veritabanı, bütün diller için kesin çağrı grafiği ve yayınlama/mağaza otomasyonu.

## 3. Hedef sırası ve ölçüm

Sıra: (1) doğruluk ve kurtarma koşullarını sağla, (2) ana ajan tüketimini azalt,
(3) aynı kaliteyle uçtan uca süreyi azalt. Alt ajan tüketimi izlenir; tek başına
işçi modelini zayıflatma veya denetimi kaldırma gerekçesi olmaz.

Ana ajanın uygulamaya, okumaya ve denetime harcadığı iş; yetkili işçilere taşınır.
LLM kullanmaması gereken kayıt, durum sayımı ve bağımlılık kontrolü koda taşınır.
Her işçiye ikinci bir yönetici eklemek varsayılan çözüm değildir.

| Ölçüt | Tanım ve ölçüm sınırı |
| --- | --- |
| Ana ajan tüketimi | Kabul edilmiş aynı iş kapsamı için ana ajanın bütün turları: planlama, giriş, çıkış, araç sonuçları, tekrar ve devralma dahil. Sağlayıcı toplamı varsa onu kullan; reasoning/cache alt kümelerini iki kez toplama. |
| Ana ajanın bağlam yükü | Ana ajana dönen bayt, okunan kaynak satırı, araç cevabı ve tur sayısı. Gerçek token sayacı yoksa yalnızca vekil ölçüttür. |
| Süre | İlk yönlendirmeden doğrulanmış entegrasyona kadar duvar saati; kuyruk, denetim, yeniden deneme ve oturum kurtarma dahil. |
| Kalite | Aynı kabul testleri, bağımsız bulgular, kaçan hata, yeniden açılan görev ve ilk denemede kabul. |
| Alt ajan tüketimi | Ayrı raporlanır; ana ajan tasarrufu diye toplam tasarruf iddiasında bulunulmaz. |
| Kullanıcı/kota maliyeti | Backend'in gözlenebilir kullanım birimleri; model tokenı ile abonelik kotası eşdeğer varsayılmaz. |

Karşılaştırma aynı başlangıç kaynakları ve aynı kabul ölçütleriyle yapılır: mevcut
akış, A teslimatı ve B teslimatı. Model/sürüm/efor, ortam, cache ve sağlanan bağlam
kaydedilir. Kolay işleri seçerek veya başarısız koşuları çıkararak sonuç iyileştirilmez.

Başlangıç örnekleri: yerel yardımcı değişikliği; iki bağımsız modül ve ortak API;
kalıcılık/kurtarma özelliği; UI akışı; yarıda kesilen işin yeni oturumda devralınması.
Önce her örnekte bir pilot; performans iddiasından önce en az üç tekrar ve dağılım
raporu. Bu küçük örneklem evrensel istatistiksel üstünlük kanıtı değildir.

**Önerilen pilot hedef:** aynı kabul kapsamındaki medyan ana ajan tokenı en az
%50 azalsın; medyan süre mevcut akıştan kötüleşmesin; zorunlu kabul ve kurtarma
kontrolleri geçsin. Bu bir tasarım hedefidir, mevcut sonuç değildir. %50 ölçülemiyorsa
başarılı diye işaretlenmez. Sayaç yoksa `unknown` ve vekil ölçütler raporlanır;
işlevsel sürüm çıkabilir fakat token tasarrufu doğrulanmış sayılmaz.

Ücretli/canlı karşılaştırmalar yalnızca oturumun mevcut kaynak yetkisiyle yapılır.
Çevrimdışı sahte işçiler süreç/kurtarma doğruluğunu sınar; model kalitesini veya
gerçek token tasarrufunu kanıtlamaz.

## 4. Korunacak mevcut altyapı

Yollar repository köküne göredir. İlk okumada bütün dosyaları yüklemek yerine
belirtilen sembollerden başlayın; satır numarası yerine sembolü esas alın.

| Kaynak | Kullanılacak davranış |
| --- | --- |
| `skills/project-brain/scripts/brain.py` | `checkout_lock`, `write_atomic`, görev ayrıştırma, `get_session_modes`, `set_session_modes`, `gc_brain` |
| `skills/project-brain/scripts/runtime_agent_pool.py` | `delegate`, `journal_path`, `get_job`, `print_output`, `select`, RPC ve değiştirilemez istek/kayıp yanıt kurtarması |
| `skills/project-brain/scripts/runtime_agents.py` | `build_worker_prompt`, model kimlikleri, risk/rota kapıları ve `worker_usage` |
| `skills/project-brain/scripts/runtime_session.py` | `orient`, intake ve kayıtlı odak |
| `skills/project-brain/scripts/runtime_protocol.py` | `guard`, `task_digest`, `reconcile`, `handoff`, doğrulama girdileri |
| `skills/project-brain/scripts/runtime_verify.py` | `check`, `review`, `accept`, kaynakla eşleşen kanıtlar ve özel yol korumaları |
| `skills/project-brain/scripts/runtime_pool.py` | Ayrı `direct` uyumluluk yolu; Pool backend'inin yerine taşınmaz |
| `skills/project-brain/POOL.md`, `SKILL.md`, `SCHEMAS.md`, `PROTOCOL.md` | Mevcut yetki, kalite, session ve uyumluluk sözleşmeleri |

Kaynak v3.6.1'de session `parallel/max_parallel` ayarı bir direktör sözleşmesidir;
ortak proje zamanlayıcısı değildir. Pool journal'ı kök yol + görev bazındadır;
çoklu REVIEW/deneme için genel run kimliği yerine kullanılamaz. İşçi istemi bugün
Brain dosyalarını ve `PB check` kullanımını içerir; yeni paket açık bir davranış
değişikliğidir. Mevcut eski akış göç tamamlanana kadar korunur.

## 5. Uygulama için önerilen mimari kararlar

Bu kararlar plan önerileridir; henüz kabul edilmiş ADR veya çalışan özellik değildir.
OR-01'de gerçek çağrı yolları ve backend yetenekleriyle doğrulanır; uygulanan kararlar
uygun ADR'ye geçirilir. Kullanıcının hedefini değiştirmeyen uygulama ayrıntıları için
tekrar tekrar onay istenmez; gerçekten yeni kapsam/yetki gerekiyorsa ayrıştırılır.

### D1 — Ana ajan yalnızca gerektiğinde karar verir

Ana ajanda kalanlar: amaç, belirsiz mimari karar, görev sınırı/bağımlılık onayı,
kapsam dışı istek ve çözülmemiş ciddi bulgu. Gerekirse hedefe ilişkin keşif REVIEW
işçisine verilir; ana ajan kaynak referanslı kısa öneriyi bir kez değerlendirir.

İşçide kalanlar: sınırlı keşif, uygulama, yerel test, ayrıntılı diff/caller incelemesi,
izin verilen sınırlı düzeltme. Ana ajan her başarılı görevi yeniden uygulamaz/denetlemez.
Uygulayan işçi kendi bağımsız denetçisi olamaz. SOLO'nun mevcut açık self-review
istisnası korunur; bağımsız inceleme varmış gibi sunulmaz.

Model seçimi işçi tokenını en aza indirmeye göre değil, işi doğru bitirip ana ajana
en az geri dönüş yaratmasına göre yapılır. İşçi gerektiği kadar ilgili bağlam ve
düşünme bütçesi alabilir. Mikro görevlerle ana ajana sürekli yeni kart yazdırmak
yerine, ölçülebilir tek davranışı kapsayan yeterli büyüklükte işler kullanılır.
Bilinen görev şablonları ve bir kez onaylanmış bağımlılıklar yeniden kullanılır.

Ana ajan başlangıcında da yalnız kısa yönlendirme/otorite sözleşmesi ve ilgili
referanslar yüklenmelidir. Skill girişini kısaltırken zorunlu yetki, kalite ve
kurtarma kuralları kaybolmaz; ayrıntılar role/göreve göre yüklenir. Bu davranış
host'un gerçek skill yükleme biçimiyle ölçülür. Prompt cache varsa ayrıca
raporlanır; cache desteği veya otomatik token indirimi varsayılmaz.

Mekanik ilerleme için LLM mesajı yoktur. Ana ajan yalnızca yeni karar ihtiyacı,
planlanmış kontrol noktası veya tamamlanma özeti alır. Bekleme backend/host aracında
olur; ana ajan kısa aralıklarla durum soran turlar üretmez. Host bunu desteklemiyorsa
sınırlılık gösterilir, olmayan arka plan otonomisi vaat edilmez.

### D2 — Tek görev gerçeği, ayrı ve kalıcı yürütme defteri

Görev tanımı ve kabul ölçütleri mevcut Brain Markdown dosyalarında kalır. Bir görev
çok sayıda REVIEW ve EXECUTE çalıştırmasına sahip olabilir. Her yeni deneme yeni
`run_id` alır. Önceki çalıştırmanın isteği, başlangıç sürümü ve raporu değiştirilmez.

Öneri: yerel özel registry altında, çalışma ağacından bağımsız proje kimliğiyle
adreslenen standart kütüphane `sqlite3` defteri. Run, olay ve bekleyen eylem aynı
transaction'da yazılır. Kısa transaction'lar, sürüm koşullu güncelleme ve benzersiz
anahtarlar kullanılır; Git veya ağ çağrısı sırasında transaction açık tutulmaz.
Network dosya sistemi ve çok makine koordinasyonu ilk sürüm kapsamı değildir.

Bağlı worktree'ler aynı proje kimliğini paylaşır. Farklı klonların çalışma sahipliği
körlemesine birleşmez. Depo taşınması, path normalizasyonu ve kayıt dışa aktarımı
ayrıca sınanır. Defter disposable `.cache` gibi temizlenmez; sırlar tutulmaz.

Her alanın sahibi bellidir: ürün/görev niyeti Brain; gerçek süreç durumu backend;
çalıştırma ve entegrasyon muhasebesi defter; kaynak ve entegrasyon çıktısı Git.
Olaylar denetim ve kurtarma içindir; bütün uygulamayı event-sourcing framework'üne
çevirmek gerekmez. SQLite dosyası Git'e konmaz; taşınabilir devralma özeti ayrıdır.

### D3 — Süreç, doğrulama ve entegrasyon ayrı fakat kurallı durumlar

Örnek süreç durumları: PREPARED, SUBMITTING, RUNNING, SUCCEEDED, FAILED,
CANCEL_REQUESTED, CANCELLED, UNKNOWN. Ayrı doğrulama sonucu PENDING/PASS/FAIL/STALE;
entegrasyon sonucu NOT_APPLICABLE/PENDING/MERGED. Geçersiz kombinasyonlar engellenir.

SUCCEEDED, kabul veya merge demek değildir. REVIEW raporu kaydedilip işlendiğinde
başarıyla kapanır; MERGED beklemez. Zaman aşımı, oturum değişimi veya kaçırılan
heartbeat tek başına işçinin öldüğü anlamına gelmez. UNKNOWN, readback gerektirir.

Gönderimden önce niyet kaydı kalıcıdır. Kayıp cevapta backend destekliyorsa aynı
idempotency key ve aynı istek sorgulanır/yeniden iletilir; yeni çalıştırma açılmaz.
Backend bunu sağlayamıyorsa otomatik tekrar yapılmaz. Genel "exactly once" garantisi
verilmez; desteklenen sınırda tekrar etkisi engellenir ve belirsizlik korunur.

### D4 — POOL / NATIVE / SOLO ile sıra ayrı kavramlar

SOLO mevcut anlamını korur: yalnız ana ajan. Yerleşik alt ajan kaynağı NATIVE'dir.
Kaynak, izin verilen L/M/H kümesi, model/efor ve SERIAL/PARALLEL ayrı kaydedilir.
Eski `pool-medium` gibi seçenekler aynı anlamdaki hazır profillere çevrilir;
HIGH+MEDIUM seçimi sessizce LOW'u açmaz. EXEC ve REV ayrı daraltılabilir.

Seçilen model ile backend'in gerçekten bildirdiği model ayrı tutulur. Gerçek kimlik
bilinmiyorsa uydurulmaz. Host istenen tier/model/araç iznini seçemiyorsa bunu bildirir.
Risk ve bağımsız denetim tabanları kaynak sınırına sığmıyor diye düşürülmez.

Yeni oturum önce açık işleri okur, sonra yeni dispatch politikasını kaydeder.
Mevcut işlerin kaynak/model/başlangıç politikası değişmez. PARALLEL -> SERIAL,
çalışanları sahte INTERRUPTED yapmaz; mevcut işler kapasite tüketmeye devam eder,
sınır sağlanana kadar yeni iş dağıtılmaz. İptal gerçek backend teyidi gerektirir.

### D5 — Adaptör, host'un gerçekten yapabildiğini söyler

Ortak mantıksal sözleşme: capabilities, submit, observe, collect, cancel ve
gerekliyse attach. Pool katalog/kota/auth/süreç otoritesi olarak kalır. Brain bunları
yeniden uygulamaz. Kullanılabilir RPC'ler OR-05'te doğrulanır; varsayımsal Pool
metotları üretime bağlanmaz.

Python, her uygulamanın native alt ajan aracını doğrudan çağıramaz. NATIVE için host
köprüsü/araç çağrısı gerekir. Başlatma ana ajan turu gerektiriyorsa bu ölçüme girer.
Callback, uzun bekleme, oturumlar arası attach veya model seçimi olmayan host'ta
destek sınırlı olarak gösterilir. Yalnız desteklenen yol uygulanır; sessiz Pool veya
ücretli fallback yoktur. B teslimatı bir gerçek native host ile doğrulanır; daha
geniş host kapsamı C'dir. Native host yoksa B'nin bu kısmı açık kalır.

### D6 — İşçi bağlamı ve keşif görevle sınırlı, gerektiğinde genişletilebilir

Paket: görev/sözleşme sürümü, başlangıç kaynakları, kabul ölçütleri, Areas/Inputs,
ilgili kısıt/ADR özeti, çağıranlar, test komutları, yetki ve rapor sözleşmesi.
Brain'in bütün prosedürleri veya ana konuşma geçmişi işçiye taşınmaz. Repository
kuralları yok sayılmaz; ilgili kurallar ve devralınan yetkiler pakette korunur.

İşçi Brain görevini/kanıdını elle değiştirmez ve nested delegation yapmaz. Eksik
bağlamı isimli dosya/simge isteğiyle genişletebilir. Araçlar salt okunur map, search,
symbol, references, tests ve change-summary sunar. İlk sürüm Git/stdlib ile çalışır;
`rg` varsa kullanılır. Dil sunucusu/AST entegrasyonu isteğe bağlıdır.

Her arama kaynak sürümü, satır/yol, sınırlı sonuç ve devam imkânı döndürür. Cache,
commit yanında dirty içerik ve ilgili manifest değişiklikleriyle geçersizleşir.
Yaklaşık metinsel ilişki kesin çağrı grafiği sayılmaz. Keşif betikleri kendiliğinden
proje kodu çalıştırmaz. Bu paketleme erişim sandbox'ı değildir: gerçek dosya/araç
izolasyonu host yeteneğine bağlıdır ve seviyesi açık kaydedilir.

### D7 — Hazır iş kuyruğu, tek entegrasyon yazıcısı

SERIAL aynı motorun toplam aktif alt ajan kapasitesi 1 olan halidir. PARALLEL B'de
en fazla iki aktif işçiyle başlar; incelemeler de toplam kapasiteye dahildir. Ana
ajanın doğrudan yazması ayrıca aynı yazma kaynaklarını rezerve eder. Worker sayısı
ile merge, test cihazı, port ve kota gibi kaynak limitleri ayrı uygulanır.

Bağımlılıklar, görev/sözleşme sürümleri ve write/read etkileriyle hazır küme türetilir.
Aynı Areas veya ortak sözleşme riskinde işler seri yürür veya önce ortak sözleşme
işi tamamlanır. Glob çakışması yalnız string prefix ile çözülmez. Gelecekte oluşacak
dosyalar ve bilinmeyen alanlar ihtiyatlı değerlendirilir. Aktif rezervasyonlar da
hesaplanır. Döngü/bilinmeyen bağımlılık açık hata olur; görev sessizce atılmaz.

Dalgalar görünümdür, ikinci görev tahtası değildir. Bağımlılık gereken kabul/
entegrasyon noktasına ulaşınca yeni iş başlayabilir; ilişkisiz yavaş işi beklemez.
İlk sürümde kod bağımlılığı hedef dala entegre olmadan bağımlı iş başlatılmaz.
Paylaşılan test ortamları için lease/rezervasyon vardır. Android gerektiğinde bu
makinede yalnız `Medium_Phone_API_36.0` kullanılır; başka AVD oluşturulmaz.

### D8 — Kanıtı işçi iddiasından ve merge sonucundan ayır

EXECUTE'a direktörün/yürütme katmanının açtığı worktree/branch atanır; seri işçi de
aynı güvenlik sözleşmesini izler. Ana ajanın doğrudan seri düzenlemesi ayrı, açık
sahiplikte kalabilir. REVIEW mevcut sabit snapshot/commit üzerinde okur; yeni branch
ve worktree yaratmaz. Testler gerektiğinde ayrı geçici koşucu alanında çalışır.

Worker commit yetkili değildir: değişiklik ve rapor döndürür. Yürütme katmanı sonucu
sabitler, kapsam dışı yolları denetler, insan Git kimliğiyle yetkili checkpoint'i
oluşturur. `git.commit: ask` varsa bu gerçek karar sınırı korunur. Squash/merge
stratejisi repository politikasına uyar; sahte merge SHA üretilmez.

Mevcut `check/review/accept` otoritesi korunur. İnceleme snapshot'a ve rapora bağlı
gerçek, yetkili reviewer kaydıyla içe alınır; yalnız farklı bir isim PASS üretmez.
Metadata guard'ları incelemenin semantik kalitesini veya kimliği kriptografik olarak
kanıtlamaz. Ana ajan kayıtları tekrar elle üretmez.

Entegrasyon kilidi bütün bağlı worktree'ler için proje düzeyindedir; yalnız mevcut
checkout kilidi yeterli değildir. Güncel hedef HEAD üzerinde aday birleştirme
hazırlanır, etkilenen testler çalışır, hedef hâlâ aynıysa entegrasyon tamamlanır.
Hedef değişirse aday/kanıt yeniden değerlendirilir. Git ile defter tek transaction
değildir: önce niyet, sonra yan etki, sonra readback/teyit uygulanır. Board güncellemesi
idempotent uzlaştırmadır; çökmede Git'ten tamamlanır, tekrar merge edilmez.

### D9 — Kısa ana ajan görünümü, kayıpsız ayrıntı

İşçi raporu yapılandırılmıştır: run/task, kaynak/çıktı sürümü, değişen dosyalar,
kontroller, bulgular, riskler, kanıt referansları ve `decision_required`. Ayrıntılı
inceleme ve log disk üzerinde kalır. Ana ajana varsayılan yalnız değişen durumlar,
sayısal özet ve gerçekten gereken kararlar gelir.

Başlangıç çıktı bütçesi: başarılı tek iş özeti en fazla 1 KiB, kontrol noktası özeti
en fazla 4 KiB UTF-8. Bunlar token garantisi değildir. Taşan ayrıntı kesilip kaybolmaz:
referans/sayfalama verilir. Ciddi bulgu, eksik kanıt veya UNKNOWN durum hiçbir zaman
başarılı kısa özet içinde gizlenmez. Aynı olay cursor ile iki kez sunulmaz.

Her raporu özetlemek için ikinci bir LLM çağrısı yapılmaz. Başarılı raporu kod
biçimlendirir; semantik uyuşmazlıkta bağımsız REVIEW kullanılır. İşçi sınırlı düzeltme
yapabilir; mevcut tekrar sınırı ve yetki korunur. Tıkanan iş kısa başarısızlık imzası,
denenen yaklaşım ve somut karar ihtiyacıyla yükseltilir; sonsuz onarım döngüsü yoktur.

### D10 — Güvenli bakım ve geriye uyumluluk

Eski session seçenekleri, komutlar, Evidence/Review kayıtları ve immutable Pool
istekleri korunur. Yeni yürütme yolu önce açık etkinleştirilen özellik olur. Eski
akıştan kanıt otomatik yükseltilmez. Aktif eski journal readback ile izlenir;
otomatik göç yeni iş göndermez veya işçiyi tekrar çalıştırmaz.

Özelliği kapatmak yeni dispatch'i durdurabilir fakat aktif işleri unutturamaz.
Eski runtime bilinmeyen yeni durumu destekliyormuş gibi açmaz. Yedek ve non-empty
migration fixture zorunludur. Göçün hangi veriyi sakladığı ve geri dönüşün hangi
işler settle edildikten sonra mümkün olduğu açık olmalıdır.

Temizlikte aktif/UNKNOWN/entegrasyon bekleyen işler ve başvurulan kanıtlar korunur.
Kapanmış işlerde bile backend dedup süresine uygun minimum kimlik/tombstone saklanır.
Worktree'deki untracked/dirty içerik silinmez; temizliği ayrı tamamlanabilir durum
olarak kaydet. Git geçmişi ignore edilmiş yerel defter/logları yedeklemez. Handoff,
gerekli taşınabilir özet ve artifact'leri açıkça dışa aktarır; taşıma tek başına eski
makinedeki işçinin durduğunu veya yeni makinede kanıtın geçerli olduğunu göstermez.

## 6. Görev tahtası ve uygulama sırası

Bu tablo tek durum kaydıdır. 3.7.0 uygulama ve test durumu aşağıda kayıtlıdır.
Durumlar: PLANNED -> IN_PROGRESS -> REVIEW -> DONE; gerekirse BLOCKED. DONE için
kart kabulü, test kanıtı ve ilgili kaynak/docs güncellemesi gerekir.

| ID | Teslimat / çıktı | Bağımlılık | Durum |
| --- | --- | --- | --- |
| OR-01 | A: ölçüm sınırı ve mimari sözleşmeler | — | DONE |
| OR-02 | A: görev bağlamı ve hafif keşif | OR-01 | DONE |
| OR-03 | A: kısa sonuç ve ana ajan karar görünümü | OR-01 | DONE |
| OR-04 | B: kalıcı run defteri ve atomik geçişler | OR-01 | DONE |
| OR-05 | B: Pool adaptörü, immutable gönderim ve kaynak profilleri | OR-03, OR-04 | DONE |
| OR-06 | B: native host köprüsü ve yetenek sınırları | OR-03, OR-04 | DONE |
| OR-07 | B: worktree/snapshot ve proje düzeyi sahiplik | OR-02, OR-04 | DONE |
| OR-08 | B: hazır iş kuyruğu ve aktif kapasite kontrolü | OR-04, OR-05, OR-07 | DONE |
| OR-09 | B: bağımsız denetim ve mevcut kanıt mekanizması | OR-02, OR-03, OR-05, OR-07 | DONE |
| OR-10 | B: tek entegrasyon kuyruğu ve board uzlaştırma | OR-08, OR-09 | DONE |
| OR-11 | B: oturum devri, export, göç ve kontrollü temizlik | OR-05, OR-06, OR-07, OR-10 | DONE |
| OR-12 | B: hata enjeksiyonu, ölçüm ve teslim doğrulaması | OR-01..OR-11 | DONE |

OR-01 sonrası OR-02/03/04 mantıken ayrışır; OR-05/06/07 de alanları ayrılırsa birlikte
ilerleyebilir. Ortak `brain.py` CLI bağlantıları ve `test_brain.py` kayıtları tek
entegrasyon işiyle eklenir. Aynı dosyayı düzenleyen kartlar yalnız isimleri farklı
diye paralel çalıştırılmaz. Bu tablonun kendisi ajan başlatma yetkisi değildir.

İlk dikey teslimat OR-01/02/03'tür: mevcut seri backend'de bir gerçek iş, bir gerçek
inceleme, kısa ana ajan özeti. A için SQLite/scheduler beklenmez. Mevcut yetki ve
kanıt sınırları korunur; A, otonom paralellik veya tam Brain izolasyonu iddia etmez.
B kritik yoluna OR-04 ile başlanır; ilk iki işçi akışı çalışınca kalan kurtarma
senaryoları kapatılır. B'nin kullanılabilirliği OR-12 kapılarına bağlıdır.

## 7. Devredilebilir görev kartları

Kart başındaki kaynaklar başlangıç noktasıdır; doğruluk için gereken çağıranları
izlemek serbesttir. Areas uygulama başlangıcında somutlaştırılır. Aşağıdaki yeni
modül/test adları öneridir; henüz mevcut komut veya dosya gibi kullanılmaz.

### OR-01 — Ölçüm ve sözleşme temeli

- Amaç: ana ajan tüketimi ve teslimat sınırını ölçülebilir hale getir.
- Kaynak: `runtime_agents.worker_usage`, `runtime_session.orient`, mevcut Pool
  protokolü; `test_economy.py`, `test_pool_integration.py`.
- Adımlar: (1) backend/host sayaç ve başlatma yeteneklerini belgele; (2) D1–D10'daki
  belirsiz sözleşmeleri karara bağla; (3) beş fixture senaryosu ve ölçüm şemasını kur.
- Kabul: unknown/partial sayaç ayrılır; reasoning/cache çift sayılmaz; fixture
  kabulü yöntemler arasında aynıdır; gerçekleşmemiş model ölçümü sonuç yazılmaz.
- Kontrol: `python -B skills/project-brain/scripts/test_economy.py`; yeni ölçüm
  fixture'ının eksik/tekrar kayıt sınamaları. Gerekli ADR öneri/karar durumunu açık tut.
- Devralma: destek matrisi, seçilmiş sözleşmeler, kalan gerçek dış bağımlılıklar.

### OR-02 — Bağlam paketi ve küçük keşif araçları

- Amaç: ana ajanın ve işçinin aynı repository keşfini tekrarlamasını azalt.
- Kaynak: `runtime_agents.build_worker_prompt`, `brain.cmd_map/current_slices`,
  `runtime_protocol.inputs/task_digest`; gerekirse `runtime_context.py` ekle.
- Adımlar: (1) paketi görev ve kaynak sürümüne bağla; (2) salt okunur arama/map/test
  keşfini ekle; (3) işçi girişini Brain yönetiminden ayır, ilgili kuralları koru.
- Ana ajan girişi: `SKILL.md` ve ilgili protokol referanslarını kısa başlangıç ve
  gerektiğinde okunan ayrıntı olarak düzenle; host'un otomatik yüklediği içerik
  dahil ölç. Büyük belgeyi yeni bir adla yine baştan sona yükletme.
- Kabul: pakette bütün gerekli kısıtlar bulunur; worker Brain yazmaz; eksik bağlam
  genişletilebilir; dirty değişiklik cache'i geçersizleştirir; gizli/kaçan yol yoktur.
- Kontrol: önerilen `test_context.py`; `test_agents_audit.py` ve ilgili güvenlik
  fixture'ları. `rg` olmayan ortam ve Windows yolları sınanır.
- Devralma: paket sözleşmesi, dosya/girdi sahipliği, yaklaşık keşfin açık sınırları.

### OR-03 — Kısa rapor ve istisna görünümü

- Amaç: ana ajan sadece gerekli özet/kararı okusun; başarılı iş için yeniden keşif yok.
- Kaynak: `runtime_agent_pool.print_output/get_job`, `runtime_session.orient`,
  `runtime_protocol.handoff`; rapor formatını mevcut Pool raporuyla uyumlu genişlet.
- Adımlar: (1) yapısal rapor doğrula; (2) başarılı/karar gereken çıktılarını ayır;
  (3) cursor ve artifact referansıyla bounded görünüm oluştur.
- Kabul: 1/4 KiB görünüm sınırları; ayrıntı kaybı ve gizlenen ciddi bulgu yok;
  bozuk rapor PASS olmaz; unchanged sonuç ana ajana yeniden akmaz; ek özet LLM'i yok.
- Kontrol: `test_pool_modes.py`, `test_handoff_audit.py` ve yeni çıktı fixture'ları.
- Devralma: ana ajanın hangi olayda çağrılacağı; gerçek token sayacı bulunma durumu.

### OR-04 — Run defteri ve geçişler

- Amaç: görevden bağımsız çoklu çalıştırma/deneme/inceleme kaydı tut.
- Alan: önerilen `runtime_runs.py`, private registry çözümleme ve hedefli testler.
- Adımlar: (1) proje/run kimliği ve sqlite şemasını kur; (2) durum+olay+bekleyen
  eylemi atomik yaz; (3) sürüm koşullu güncelleme, yedek ve future-schema reddini ekle.
- Kabul: iki eşzamanlı rezervasyon sınırı aşamaz; çökmede yarım olay yok; REVIEW
  başarıyla kapanır; eski run değiştirilmez; bağlı worktree'ler tek deftere bakar.
- Kontrol: önerilen `test_runs.py`; gerçek iki yerel süreç, restart ve non-empty
  migration fixture. Temp dosya yazmayı transaction başarısı gibi kabul etme.
- Devralma: şema sürümü, durum/guard tablosu, kurtarma ve veri sahipliği sözleşmesi.

### OR-05 — Pool adaptörü ve session profilleri

- Amaç: mevcut Pool'u yeniden yazmadan run temelli, tekrar etkisi önlenen dispatch.
- Kaynak: `runtime_agent_pool.delegate/select/rpc`, `brain` session mode fonksiyonları.
- Adımlar: (1) mevcut RPC yeteneklerini doğrula; (2) kayıt-gönder-gözle-topla
  sınırlarını ayır; (3) kaynak/tier kümelerini eski alias'larla uyumlu bağla.
- Kabul: kayıp cevap aynı istek/key ile çözülür; eski journal korunur; gerçek
  backend durumu kullanılır; kaynak/efor/kota yetkisi genişlemez; güçlü worker seçimi
  düşük token zorunluluğuna bağlanmaz; secret-bearing işin mevcut kısıtı korunur.
- Kontrol: `test_agent_pool.py`, `test_pool_modes.py`; gerekirse mevcut sentetik
  Pool entegrasyonu. Gerçek sağlayıcı kullanımı ayrı gözlem olarak kaydedilir.
- Devralma: doğrulanmış adaptör yetenekleri ve çözülemeyen response_unknown durumları.

### OR-06 — Native host köprüsü

- Amaç: native işçiye aynı run/kanıt sözleşmesini uygulayıp olmayan yeteneği uydurma.
- Alan: ortak run arabirimi, host isteği/receipt sözleşmesi, skill host talimatları.
- Adımlar: (1) host için capabilities bildir; (2) başlatma/sonuç/iptal makbuzunu
  bağla; (3) bir gerçek desteklenen host'ta uçtan uca örnek çalıştır.
- Kabul: Python'un erişemediği araç otomatik var sayılmaz; host veya model kimliği
  belirsizse gösterilir; oturum bitince yaşamayan iş canlı sayılmaz; attach olmayan
  host kör tekrar yapmaz; nested worker yok; başlatma turları ölçüme dahil.
- Kontrol: sahte host contract testleri ve bir gerçek host gözlemi. Canlı host
  kullanılamazsa bu kabul açık kalır; sentetik sonuç gerçek destek diye sunulmaz.
- Devralma: desteklenen host, unsupported yetenekler ve minimum ana ajan etkileşimi.

### OR-07 — Worktree, sabit snapshot ve sahiplik

- Amaç: her delegated EXECUTE'a izole çalışma alanı, REVIEW'e sabit okuma kaynağı ver.
- Kaynak: `brain.checkout_lock`, `runtime_verify.public_path`; önerilen
  `runtime_workspace.py`. Repository Git politikasını koru.
- Adımlar: (1) proje ortak kilidini kur; (2) worktree/branch niyetini ve gerçek Git
  sonucunu eşleştir; (3) REVIEW snapshot ve sonucu sabitleme akışını ekle.
- Kabul: tek checkout'a iki yazıcı yok; worktree oluştururken çökme kurtarılabilir;
  REVIEW yeni branch/worktree açmaz; kapsam dışı değişiklik engellenir/karantinaya
  alınır; dirty veya untracked kullanıcı işi silinmez; sandbox seviyesi açık.
- Kontrol: önerilen `test_workspace.py`; boş/dirty repo, Windows yol/link kaçışı,
  yarım oluşturma, hareketli hedef dal ve insan commit kimliği fixture'ları.
- Devralma: atanmış kaynaklar, mevcut Git durumları ve temizlik önkoşulları.

### OR-08 — Hazır iş planlama ve rezervasyon

- Amaç: aynı motorla SERIAL/PARALLEL; aktif işler dahil güvenli kabul ve hızlı ilerleme.
- Alan: önerilen `runtime_schedule.py`, OR-04 transaction arayüzü; CLI seam ayrı.
- Adımlar: (1) saf hazır-küme hesabı; (2) kaynak/alan rezervasyonu; (3) kapasite
  açıldığında bağımsız işi seç, derived dalga görünümü ver.
- Kabul: aktif iş varken SERIAL ikinci iş başlatmaz; aynı dosya/glob örtüşmesi,
  boş Areas, ortak sözleşme ve cihaz kilidi korunur; REVIEW kapasiteye sayılır;
  döngü ve bilinmeyen bağımlılık görünür; 200+ görev sessizce düşmez.
- Kontrol: önerilen `test_schedule.py`; aynı anda iki dispatcher ve A kısa/B uzun/
  C yalnız A'ya bağımlı örneği. Sanal gelecekte-DONE, gerçek dispatch yetkisi olmaz.
- Devralma: bekleme nedenleri ve kaynak rezervasyonları; ikinci plan tahtası yok.

### OR-09 — Bağımsız inceleme ve kanıt aktarımı

- Amaç: ana ajan bütün diff'i tekrar okumadan güvenilir reviewer ve test sonucunu kullanır.
- Kaynak: `runtime_verify.check/review/accept`, `runtime_protocol.provenance/review_guard`.
- Adımlar: (1) raporu immutable kaynağa bağla; (2) gerçek reviewer görevini kaydet;
  (3) mevcut kanıt otoritesi üzerinden gözlemleri işle ve stale kanıtı reddet.
- Kabul: worker iddiası test kanıtı olmaz; reviewer adı tek başına PASS olmaz;
  uygulayıcı bağımsız reviewer olamaz; mevcut SOLO istisnası açık; source/spec/env
  değişince kanıt yenilenir; ciddi/QUALITY bulgu korunur; UI kaynak okumasıyla kabul edilmez.
- Kontrol: `test_verify_audit.py`, `test_protocol_audit.py`, `test_production.py`
  ve rapor/snapshot uyuşmazlığı fixture'ları.
- Devralma: kanıt konumları, geçerli digest'ler, açık bulgular ve karar ihtiyacı.

### OR-10 — Entegrasyon ve kontrollü görev kapanışı

- Amaç: tek yazıcıyla doğrulanmış sonucu birleştir; board'u tekrar etkisi olmadan uzlaştır.
- Kaynak: OR-07 workspace/lock, OR-09 kanıt; mevcut task kabul ve checkpoint yolları.
- Adımlar: (1) entegrasyon niyetini kaydet; (2) güncel HEAD için aday/test hazırla;
  (3) yetkili merge/checkpoint ve readback yap; (4) görev kapanışını projekte et.
- Kabul: HEAD değişiminde eski PASS ile kapanış yok; iki merge çakışmaz; merge sonrası
  DB/board güncellemesinden önce çökme yeniden merge üretmez; bağımlı iş erken açılmaz;
  kullanıcı değişiklikleri ve `git.commit: ask` korunur.
- Kontrol: önerilen `test_integration_queue.py`; iki dal ayrı ayrı geçerken birlikte
  başarısız örnek, dış commit ve her yan-etki sınırında kill/restart.
- Devralma: entegrasyon commit'i, doğrulanan hedef ve kapanış/temizlik durumu.

### OR-11 — Oturumlar arası kurtarma, göç ve bakım

- Amaç: yeni oturum mevcut işin gerçeğini bulsun; temizleme kurtarma bilgisini kaybetmesin.
- Kaynak: `runtime_session`, `runtime_protocol.handoff`, `brain.gc_brain`, `migrate.py`.
- Adımlar: (1) başlangıçta açık işleri gözle; (2) mod değişimini yeni işlere uygula;
  (3) taşınabilir manifest, eski journal göçü ve temizlik readback'ini ekle.
- Kabul: oturum açmak RUNNING'i değiştirmez; serial drain doğru; eski işçi durmadan
  yeni yazıcı devralmaz; export sır/özel yol sızdırmaz; aktif/UNKNOWN kayıt silinmez;
  dedup kimliği korunur; göç dispatch yapmaz; feature kapatmak açık işleri gizlemez.
- Kontrol: `test_handoff_audit.py`, `test_session.py`, migration testleri; yeni
  makine/klon simülasyonu ve gerekli kanıt bulunmadığında recheck.
- Devralma: kurtarılabilir açık işler, export sınırları ve güvenli geri dönüş koşulları.

### OR-12 — Son kabul ve ölçülmüş teslim

- Amaç: işlevsel doğruluk, ana ajan faydası ve destek kapsamını ayrı kanıtla.
- Alan: ilgili testler, tam `test_brain.py` kaydı, overview/verification ve skill
  belgeleri. Sürümleme yalnız gerçek teslim kapsamına göre güncellenir.
- Adımlar: (1) aşağıdaki hata matrisini tamamla; (2) tam regresyon ve runtime
  uyumluluğu; (3) yetkili canlı/pilot ölçümü; (4) güncel doküman ve kapalı görevleri uzlaştır.
- Kabul: bütün zorunlu işlevsel kapılar geçer; eski kullanım çalışır; measured/
  synthetic/unknown ayrılır; ana ajan tasarrufu ölçülmediyse yüzde iddiası yok;
  sadece toplam alt ajan tüketimine bakarak başarı/başarısızlık kararı verilmez.
- Kontrol: bölüm 8 komutları ve beş örneğin karşılaştırması. Store/push/kurulu
  kopyaları güncelleme otomatik kabul koşulu değildir; ayrı yetki/kapsamdır.
- Devralma: teslim kapsamı, gerçek ölçümler, açık host sınırları ve bakım başlangıcı.

## 8. Doğrulama kapıları

Runtime değişikliklerinden sonra mevcut tam kontrol:

```text
python -B skills/project-brain/scripts/test_brain.py
python -B skills/project-brain/scripts/brain.py --version
git diff --check
```

Kart sırasında hedefli testler, entegrasyon/checkpoint'te tam paket çalışır. Geçerli
kanıt tekrar kullanılır; değişen öncül veya hata yoksa sırf alışkanlıktan aynı test
yeniden koşulmaz. Yeni testler tam girişe eklenir. Python 3.8 dil grameri korunur;
yalnız grammar testi gerçek Python 3.8/POSIX çalıştırma kanıtı sayılmaz. Destek
iddiası genişletilecekse o ortamda gerçekten çalıştırılır.

| Zorunlu senaryo | Gözlenecek sonuç |
| --- | --- |
| Backend kabulünden sonra ACK kaybı | Yeni iş yok; aynı kimlikle readback |
| Aynı anda iki dispatcher | Kapasite, tek uygulama sahipliği ve sıra korunur |
| Yeni oturum sırasında eski worker canlı | Sahte INTERRUPTED yok; eski iş kapasiteye dahil |
| PARALLEL -> SERIAL | Mevcut işler drain olur; yeni dispatch sınırı ihlal etmez |
| Worker durumunun bilinmemesi | Kör retry veya sahte iptal yok |
| REVIEW tamamlanması | Rapor kaynak sürümüyle saklanır; başarılı kapanır |
| Test PASS sonrası kaynak/spec/env değişimi | Eski kanıt kabul edilmez |
| Ayrı ayrı geçen iki değişikliğin birlikte bozulması | Entegrasyon kapanışı engellenir |
| Git merge sonrası kayıt yazılmadan çökme | Readback board/defteri tamamlar; ikinci merge yok |
| Kirli worktree ve untracked kullanıcı dosyası | Temizlik korunacak içeriği silmez |
| Eski 3.6.1 immutable job göçü | İstek/key değişmez; otomatik submit yok |
| Host attach/model seçimi desteklemiyor | Sınır görünür; hayali capability yok |
| Bozuk/çok uzun işçi raporu | Ayrıntı korunur, başarı uydurulmaz, ana çıktı sınırlıdır |
| İlgisiz yavaş iş | Hazır bağımsız iş gereksiz dalga bariyerinde beklemez |
| Proje sonu bakım | Açık işler/kanıt/tombstone korunur; kapanmış ayrıntı kontrollü azalır |

Bu senaryolar runtime güvenilirliğini sınar; ürünün bütün semantik hatalarını
bulduğumuz anlamına gelmez. Son kullanıcı hedefi ayrıca uygun gerçek akışlarla doğrulanır.

## 9. Kısa işçi devri ve devam kaydı

Her işçi başlangıcında bütün belge yerine şu alanlar gönderilir:

```text
Kart: OR-xx | run: <id> | tür: REVIEW/EXECUTE
Amaç ve kabul: <ilgili karttan>
Başlangıç: <commit + gerekirse dirty içerik kimliği>
Areas / Inputs / çağıranlar: <somut liste>
İlgili kararlar ve repository kuralları: <yalnız gerekli dilimler>
Kontroller: <tam komutlar ve gerçek test ortamı>
Çalışma alanı / yetki: <atanmış alan; Brain yazma, nested delegate, commit yok>
Durdurma/yükseltme: <sözleşme belirsizliği, kapsam dışı değişim, tekrar sınırı>
Sonuç: <yapılandırılmış rapor + artifact referansları + gerekli karar>
```

Ana ajanın kontrol noktası ise tamamlanan run'lar, açık ciddi bulgular, gerekli
kararlar, sonraki hazır işler ve kanıt referanslarını içerir. Başarılı işlerin
tam logları/kodu veya diğer işçilerin bütün konuşmaları otomatik yüklenmez.

Kapanış ve sonraki bakım için devam kaydı:

- Aktif uygulama kartı: yok; 12 kartın desteklenen işlevsel kapsamı tamamlandı.
- 2026-11-01 sabit kaynak: Python 3.11.15 ve 3.8.20 üzerinde tam test_brain.py
  exit 0; ayrı gerçek CLI Agent Pool 1.8.1 daemon + sentetik CLI varsayılan protokol
  uygulama/check/accept/integrate testi exit 0. Python 3.8 grameri ve diff temiz.
- Bağımsız denetçi üretim açıklarını yeniden üretti; değişmez sözleşme, gerçek
  işçi kimliği/seviye tabanı, köken oturum yetkisi, commit ve hedef hook değişimi,
  kapanmış görev readback'i ve restore sınırları regresyonla kapatıldı. Son scoped
  denetimde yeniden üretilebilen yayın engeli P1 kalmadı.
- Native kapsam: gerçek Codex salt okunur launch/collect ve çalışan turn'ün
  interrupt/host-state teyidi geçti; model kimliği/sayaç host'ta unknown kaldı.
  Native execute/bağımsız review/kabul akışı protokol-1 host fixture'ında testli.
  Diğer host/model kombinasyonları kendiliğinden sertifikalı sayılmaz.
- Restore: farklı temiz Git klonuna SQLite backup taşındı; özgün RUNNING işi
  değişmedi, yeni kayıt UNKNOWN oldu. Kopya submit/cancel/integrate yetkisi kazanmaz;
  özgün host readback ve gerçek receipt settlement gerekir. Bu bir dağıtık süreç
  taşıma servisi değildir; kayıp uncommitted dosyalar yedekten uydurulmaz.
- Ana ajan tüketimi: skill giriş içeriği LF-normalize UTF-8 olarak 19.877 -> 12.059
  bayt. Gerçek ücretlendirilmiş token veya reasoning tasarrufu ölçülmedi; önerilen
  %50 pilot hedefi gerçekleşmiş diye kapatılmadı. Bu, gerçek sayaç bulunan host'ta
  sonraki performans ölçümüdür; sürümün sayısal pazarlama iddiası değildir.
- Kullanım ve destek sınırları ORCHESTRATION.md'de; kaynak haritası overview ve
  sürdürülen test kanıtı VERIFICATION.md'de. Yeni oturum bu kapanmış planı otomatik
  yeniden başlatmaz veya emekli .project-brain/ geliştirme planını oluşturmaz.
- Dağıtım paketi tools/build_release.py ile yalnız Git-index kaynaklarından
  üretildi. Çıkarılmış CLI smoke, paketten üretim regresyonu, ZIP CRC/SHA-256 ve
  iki ardışık build için aynı hash kontrolü geçti. Yerel yayın paketi hazırdır.
  GitHub/store yayını ve kullanıcı projelerini topluca göç ettirme bu işin parçası değildir.

### Kullanımda otomatik yükseltme — 3.7.1

Kullanıcı talebi: eski proje kayıtlarını ayrı migration istemeden açılışta yükselt.
Uygulama ve doğrulama: ortak startup converter; orient/boot girişleri; Git olmayan
ve henüz commit almamış projeler; ham yedek ve kesintiden toparlanma; salt okunur,
merge/rebase, gelecekteki sürüm ve tanınmayan biçim korumaları. Görev/Resume/External
devamlılığı ve tekrar açılışın idempotentliği regresyonlarla doğrulanacak.

Plan tamamlanınca geçerli mimari kararlar ve destek sınırları overview, verification
ve kabul edilmiş ADR'lere geçirilir. Geçici kart ayrıntıları Git'te kurtarılabilir
biçimde kaldırılabilir; yeni oturumlar tamamlanmış bu yol haritasını aktif iş sanmaz.

### Çalışma seçimi protokolü — tamamlanan bakım (2026-11-01)

Kullanıcı talebi: Pool kategori/servis/effort bilgisini kendi skill'inden kısa
olarak al; yöneticinin çalışma seçeneklerini kullanıcıya sun. Pool katalog/API
tasarımı bu kapsamda değil. Native, en ucuz native ve yalnız yönetici korunur.
İş: giriş ve ilgili oturum referanslarını tutarlı güncelle; sabit eski CLI
kodlarını uyumluluk bilgisi olarak ayır; kısa giriş bütçesi/link/diff kontrolü
ve kurulu becerinin güncellenmesi. Pool'a bu bakımda bağlanılmayacak.
Sonuç: kısa çalışma sorusu/protokolü ve eski adaptör sınırları belgelendi;
giriş bütçesi, referans ve diff kontrolleri geçti. Runtime değişmedi; katalog/API
tasarımı veya canlı Pool bağlantısı yapılmadı. Bu bakımın açık uygulama işi yok.

### Executor Selection Policy — tamamlanan netleştirme (2026-11-01)

Kullanıcı talebi: kaynak adı açık yedi yürütücü seçeneği; kullanıcı tarafından
seçilen native/CAP model listeleri; kalıcı seçim, açık değişiklik isteminde
mevcut tercihlerin gösterilmesi ve ayrı seri/paralel kararı. Kararlaştırılmış
sınırlar ile token ekonomisi zorunlu; sessiz kaynak/model değiştirme yok.
Kapsam: kısa skill girişi ve oturum/Pool referansları, kayıt şablonu ve kurulu
kopyalar. CAP'ın katalog/API tasarımı ve runtime adaptörünü yeniden yazmak kapsamda
değil. Güncel CAP skill'i ve dört satırlık kompakt metadata sayfası okundu; iş
başlatılmadı. Kontrol: giriş bütçesi, referanslar, diff ve dağıtım eşitliği.

### ESP/SP ve güncel CAP uyumu — tamamlanan bakım (2026-11-01)

Kullanıcı talebi: İngilizce Executor Selection Policy (ESP), Scheduling Policy
(SP); Solo ana ajanın çalışmasıdır, yalnız alt ajan görevlendirmesi yoktur.
Yeni implementation oturumunda yarım işi/çalışan job'ları koruyarak iki tercihi
kısa teyit et; aynı oturumdaki soruda tekrar sorma. Token ekonomisi korunur.
Gözlem: CAP güncel metadata formatında legacy policy.taskModes yok; selection
modelId/category/effort ve alternatives sayısı dönüyor, list_models sayfalı nesne.
Mevcut adaptör yeni modeli hatalı eski-sürüm mesajıyla reddediyor.
İş: format uyumunu eski journal/kalite tabanlarını koruyarak düzelt; kompakt gerçek
metadata smoke (job yok), hedefli/tam offline regresyon, giriş bütçesi ve kurulu
kopya kontrolü. ESP/SP JSON'unu runtime uygulama özelliği gibi sunma.
Sonuç: 3.7.3 kompakt CAP uyumu, ESP/SP adlandırması ve yeni oturum teyidi hazır.
Canlı salt okunur seçim, hedefli/tam Python 3.11/3.8 regresyonları ve bağımsız
native inceleme geçti. Sağlayıcıda iş başlatılmadı; otomatik ESP/SP policy parser
bu bakımın parçası değildir. Güncel kapsam overview ve VERIFICATION.md'de.

### Token ekonomisi — tamamlanan bakım (2026-11-01)

Kullanıcı talebi: pahalı yöneticinin ilk tarama, bağlantı hazırlığı ve mekanik iş
tüketimini azalt; araya giren sorularda bağlamı yeniden yükleme; kaliteyi koru.
Mimari karar: önce deterministik araçlar, yetkili düşük seviye işçiye sınırlı keşif,
yöneticiye yalnız mimari/kabul/istisna kararları. İşçi önerisi kanıt değildir;
bekleyen talepler ve belirsiz dış işlemler tasarruf uğruna gizlenmez.

Tamamlanan uygulama ve doğrulama işleri:
- Giriş protokolünü kısalt; ucuz keşif, izin mirası, soru ve yükseltme sınırlarını
  zorunlu kıl. Ayrıntılı kurallar ilgili referanslarda kalır.
- Salt okunur, sınırlı `brief` devam görünümü ekle: FOCUS/Resume, talep sayıları,
  dış işlem uyarıları; göç, oturum sıfırlama veya Pool çağrısı yok.
- Pool discovery seçiminde varsayılan L; seçim çıktısı kısa, tam ayrıntı isteğe bağlı.
  Görev/reviewer kalite tabanları ve mevcut yetki denetimleri korunur.
- Soru/brief yan etkisizliği, taşan çıktı ve discovery/reviewer seçim regresyonları;
  tam test_brain.py, Python 3.8 grameri ve bağımsız inceleme.
- Kurulu becerilerde tekrar eden protokolleri yedekleyerek görünürlükten kaldır;
  Project Brain güncellemesini yönetici üzerinden uygula. Ölçülmeyen token için
  yüzde tasarruf iddiası üretme.

Sonuç: 3.7.2 kaynak ve 42 kurulu dağıtım güncel; Python 3.11.15/3.8.20 tam paket,
bağımsız native inceleme, gramer ve diff kontrolleri geçti. Aktif bakım kartı yok.
Güncel sözleşme/ölçüm sınırları overview ve VERIFICATION.md'de; bu kayıt yeni
oturumda tamamlanmış planı yeniden başlatma yetkisi değildir.
