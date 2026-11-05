# Protokol görüşmesi — devam notu

Güncelleme: 2026-11-05.

Son durum: Kullanıcı uygulamayı onayladı. Aşağıdaki görüşme geçmişinin yerine
güncel karar için [ADR-007](decisions/ADR-007.md), aktif kurallar için kaynak
SKILL.md/WORKFLOW.md esas alınır. Aşağıdaki eski “henüz uygulanmadı” ve “yalnız
görüşmeye devam et” ifadeleri artık yürürlükte değildir.

## Durum ve yetki

Bu dosya kullanıcıyla süren tasarım görüşmesinin tek devam notudur. Yürürlükteki
skill/protokol değildir; uygulama, dağıtım veya yeni ajan çağrısı talimatı vermez.
Kullanıcı önce maddeleri konuşup karar vermek istiyor. Şimdilik yalnız bu notu
koru ve görüşmeye devam et; açık kararları kendin tamamlayıp protokole uygulama.
Kaynak deponun tamamlanmış geliştirme planını veya `.project-brain/` klasörünü
yeniden oluşturma.

Başka bir ajan bu dosyayı okuyarak devam edebilir. Kısa cevap ver; mevcut kodu
tekrar tekrar incelemek yerine olması gereken davranışı kullanıcıyla tartış.

## Amaç ve sunum

- Amaç: yüksek kalite, hızlı tamamlanma ve düşük toplam token/maliyet birlikte
  gözetilir. Kullanıcı hızın çok önemli olduğunu özellikle belirtti.
  Tasarruf; gereksiz bağlam/tekrarları azaltmaktan ve işe uygun ajan/efor
  seçiminden gelmeli, gerekli kalite kontrolünü kaldırmaktan değil.
- Kullanıcıya anlamlı Türkçe adlar ve madde madde seçenekler gösterilmeli.
  İngilizce teknik anahtarlar/kısaltmalar arka planda kalabilir.
- Bir seferde bir kavramı tartış. Kullanıcı mevcut sistemin raporunu veya uzun
  açıklamalar istemiyor; bu görüşme tasarım kararlarını netleştirmek için.
- Paralel sayı bir üst sınırdır: "en fazla 3" sıfır, bir, iki veya üç alt ajan
  kullanılabilmesi demektir. Üç ajan çalıştırma hedefi veya token tasarrufu
  garantisi değildir. Yönetici ihtiyaca göre sayı, model ve efor seçer.

## Netleşen konu: Bağımsız İkinci Görüş

Adı tam olarak **Bağımsız İkinci Görüş**. Kullanıcı bu adı ve aşağıdaki yaklaşımı
benimsedi, ancak sonrasında uygulamayı durdurup önce tartışmanın kaydedilmesini
istedi. Henüz skill/protokole eklenmedi.

- Başlangıçta proje mimarisi/yol haritası planlanırken ve proje sürerken kritik
  bir karar veya görüş ihtiyacı oluştuğunda işletilecek.
- Yönetici kritikliği değerlendirir. Kullanıcının özel olarak "kritik" dediği
  adımlar da bu kapsamdadır.
- Yöneticinin dışında **en az bir** ek görüş alınır. Önceki "iki ek görüş / en az
  üç katılımcı" önerisi geçersizdir.
- Tercih sırası:
  1. Eşdeğer, farklı model.
  2. Bir üst model; yalnız ilgili kritik karar için dar kapsamlı, kısa görev.
  3. Bunlar yoksa bir alt model, yüksek efor. Maksimum efor varsayılan değildir;
     yüksek efor, alt modeli otomatik olarak üst modelle eşdeğer yapmaz.
  4. Son seçenek: aynı model, ayrı ajan/oturum ve temiz bağlam.
- İkinci ajana önce hedef, gereksinimler, kısıtlar ve gerekli olgular verilir;
  yöneticinin tercih ettiği çözüm/kanaat anlatılmaz. Kendi görüşünü oluşturduktan
  sonra öneriler karşılaştırılır; yönetici nihai kararı gerekçelendirir.
- Bu, karar verirken alınan danışmanlıktır. **Denetleyici rolü veya yapılan işin
  bağımsız denetimi değildir.** Denetim yerine geçmez.

## Rol adları ve henüz tartışılan görevler

Üç rol adı kullanılıyor; sabit üç ayrı ajan çalıştırma zorunluluğu kararlaştırılmadı.

- **Yönetici:** Hedef/kapsam, mimari ve planlama; işleri bölme; uygun model ve efor
  seçme; ilerlemeyi takip etme; sonucu kabul etme. Gerektiğinde Bağımsız İkinci
  Görüş alır. Kullanıcı güçlü modelleri bu işlerde kullanmayı tercih ediyor;
  örnek model adları kalıcı bir sıralama veya sabit model listesi sayılmamalı.
- **Uygulayıcı:** İşi/kodu gerçekleştirir, ilgili testleri çalıştırır, kendi
  hatalarını düzeltir ve sonucu kanıtlarıyla teslim eder. Kendi yaptığı testler
  bağımsız denetim sayılmaz.
- **Denetleyici:** Yapılan işin gereksinimlere uygunluğunu, doğruluğunu ve
  testlerini kontrol eder. Bağımsız denetimde uygulayıcıdan farklı olmalıdır.
  Denetleyicinin seçimi, gücü ve yöneticiyle ilişkisinin ayrıntıları henüz
  kararlaştırılmadı; sıradaki görüşme konularından biridir.

Kullanıcının yönelimi: uygun alt ajan varsa işi uygun en ekonomik modele vermek;
havuz seçilmişse havuzu, seçilmemişse kullanılabilir natif ajanları kullanmak;
alt ajan imkânı yoksa yöneticinin kendisinin çalışabilmesi. Bunun kesin kaynak,
kritik iş, yükseltme ve istisna kuralları henüz uygulama kararı değildir.

## Korunacak yedi maddelik soru taslağı

Bu liste örnektir; son biçimi ve seçenekleri henüz onaylanmadı. İlk rol ve
Bağımsız İkinci Görüş görüşmelerindeyiz; kalan maddelere kendiliğinden geçme.

1. **Çalışma önceliği:** En yüksek token tasarrufu / dengeli / hız öncelikli.
2. **Uygulayıcı seçimi:** Yönetici / natif yardımcılar / Ajan Havuzu / kullanıcının
   belirlediği hesap ve modeller.
3. **Denetleyici seçimi:** Uygun bağımsız natif ajan / havuz ajanı / kullanıcının
   belirlediği denetleyici. Ayrıntıları görüşülecek.
4. **Çalışma düzeni:** Varsayılan paralel çoklu ajan çalışma; toplam eşzamanlı
   alt ajan üst sınırı. Kullanıcı "yalnız sen yürüt" derse tek ajan istisnası.
5. **Kota yenilenmesini bekleme:** Aynı hesabın kotasını bekleme; açık/kapalı ve
   kalan kota eşiği.
6. **Yönetici devri:** Başka hazır hesaba devir; açık/kapalı ve kalan kota eşiği.
   Bekleme ve devir iki ayrı soru olarak kalacak.
7. **Yeni yöneticinin seviyesi:** Mevcut yöneticiyle aynı seviye / seçilen seviye /
   belirli hesap ve modeller; yalnız devir açıksa uygulanır.

Türkçe beş soruluk mevcut açılış daha önce uygulanmıştı. Yukarıdaki yedi maddelik
taslak, rol ayrıntıları ve Bağımsız İkinci Görüş bunun devamında tartışılıyor;
bu not onların uygulanmış olduğu anlamına gelmez.

## Toparlanan karar — Kaliteli ve Ekonomik Çalışma

Son kullanıcı isteği: İyi planlanan ve doğru gerçekleştirilen işi düşük toplam
maliyetle tamamlayacak basit kuralları karara bağla. Model adları sabitlenmesin;
her model seçimi için internet araştırması yapılmasın. Aşağıdaki karar metni
görüşmenin bu aşamasını toplar; aktif skill/runtime'a henüz uygulanmadı.

- **Yönetici:** Planlama, iş bölümü, risk değerlendirmesi, otomatik ajan/efor
  seçimi ve nihai kabulü üstlenir. Küçük veya devretme yükü yüksek işleri kendisi
  yapabilir. Net sınırları olan, devretmenin faydalı olduğu işleri uygun en
  ekonomik uygulayıcıya verir. Alt ajan kullanmak başlı başına hedef değildir.
- **Kritik kararlar:** Yukarıdaki Bağımsız İkinci Görüş kuralı uygulanır; en az
  bir ek görüş. Bu, uygulama denetiminin yerine geçmez.
- **Uygulayıcı:** İşi gerçekleştirir, ilgili testleri çalıştırır, kendi hatalarını
  düzeltir ve değişiklik/kanıtları teslim eder. Güç ve efor işe göre seçilir;
  yetersizlik veya tekrarlanan başarısızlıkta görev bölünür ya da model yükseltilir.
- **Denetim:** Sürekli çalışan zorunlu bir üçüncü ajan yerine ihtiyaç oldukça
  verilen görevdir. Rutin teslimleri yönetici inceler. Ayrı denetim gerekiyorsa
  göreve yeterli olmak koşuluyla uygulayıcının bir alt seviyesindeki model başlangıç
  tercihidir; gereken efor seçilir. Kritik/karmaşık işte veya yetersizlikte eşdeğer
  güçlü, bağımsız ajan kullanılır; üst modele yalnız dar kapsamlı ihtiyaç taşınır.
  Yönetici uygulayıcı olduysa kendi kontrolünü bağımsız denetim olarak sunamaz.
- **Tekrarsız kontrol:** Denetim, değişen kodu, gereksinimleri, etkilenen çağrıları
  ve testlerin anlamını kapsar. Yönetici her dosyayı yeniden incelemek yerine
  bulguları/kanıtları değerlendirir, kritik veya şüpheli noktaları ayrıca inceler.
  Planlama aşamasındaki ikinci görüş, uygulamanın doğru yapıldığını garanti etmez.
- **Model seçimi:** Opus/Sonnet/Luna vb. isimler örnektir, protokol kuralı değildir.
  Host/havuzun mevcut model, yetenek, efor ve kota bilgileri kullanılır. Her seçim
  için web araştırması yapılmaz. Bilinmeyen model sıralaması/yeterlilik uydurulmaz;
  bir alt seviye veya yüksek efor otomatik yeterlilik garantisi sayılmaz.
- **Varsayılan çalışma:** Kullanıcı aksini söylemedikçe **paralel çoklu ajan
  çalışma**. Çoklu ajan işlerin ajanlar arasında paylaşılması, paralellik bağımsız
  işlerin aynı anda yürütülmesidir. Yönetici planlama/koordinasyon sorumluluğunu
  korur; mevcut kaynaklarda bağımsız, devredilebilir işler varsa yardımcıları
  paralel çalıştırır. Paralellik için her seferinde kullanıcı talimatı beklemez.
- **Tek ajan istisnası:** Kullanıcının "yalnız sen yürüt", "sadece sen yap"
  talimatı çoklu ajan varsayılanını o kapsamda değiştirir. Yardımcı kaynaklar
  yoksa veya işler birbirine bağımlıysa yapay paralellik üretilmez; sınır belirtilir.
  Tek ajan kontrolü, bağımsız görüş/denetim alınmış gibi gösterilmez.
- **Paralellik sınırı:** Kullanıcının sayısı üst sınırdır; hedef ajan sayısı
  değildir. Yönetici bağımsız iş sayısı, gerçek kapasite, kilitler ve birleştirme
  yüküne göre sayıyı seçer. Sabit iki/üç ajan sınırı veya sürekli 100/500 ajan açma
  zorunluluğu konmaz. Sayısal varsayılan henüz kararlaştırılmadı; uydurma. Daha
  fazla ajan otomatik hız/tasarruf garantisi değildir.
- **Amaç:** Tek ajan çağrısının ucuzluğu yerine toplam tamamlanma maliyeti, süre,
  düzeltme yükü ve kalite gözetilir. Model yükseltmek ve yüksek/maksimum efor
  kullanmak otomatik varsayılan yapılmaz; gerektiğinde gerekçeli seçilir.

## Son gösterim taslağı — ayrı seçimler, işaretli varsayılanlar

Son kullanıcı açıklaması önceki yedi soruluk gösterimi sadeleştirir. Çalışma
düzeni, ajan kullanımı ve ajan kaynağı farklı boyutlardır. "Sadece yönetici"
alt ajan kullanmamak demektir; yöneticinin araçlarla bağımsız işlemleri paralel
yürütmesini yasaklamaz. Çoklu ajan + sıralı çalışma da mümkündür.

Aşağıdaki işaretler önerilen varsayılanları gösterir; bir seçim formu veya yeni
runtime ayarı uygulanmadı. Kullanıcının açık tercihi her zaman üstündür. Kaynak
kimlikleri mevcut host/CLI Agent Pool bilgisinden okunur, kategori uydurulmaz.

1. **Çalışma düzeni:** [x] Paralel; [ ] Sıralı. İş bölünebiliyorsa mümkün olan
   en yüksek faydalı paralellik kullanılır. Üst sınır: otomatik, gerçek kapasite
   ve kullanıcı sınırları içinde; kullanıcı sayı verirse bu tavan olur.
2. **Ajan kullanımı:** [x] Çoklu ajan; [ ] Sadece yönetici.
3. **Ajan kaynağı** (çoklu ajanda): [x] Natif; [ ] Natif + CLI Ajan Havuzu;
   [ ] Yalnız CLI Ajan Havuzu; [ ] Belirlediğim hesap/model.
   Natif, kullanılan uygulamanın sunduğu ajan/modellerdir; aynı model ailesi
   zorunluluğu değildir. Havuz seçeneğinde kullanıcı oluşturduğu havuzları veya
   katalogdan seçimi belirtebilir; örneğin "yalnız medium havuzu" ya da "yalnız
   şu model". Tek model sabitlemesi birden fazla ajan oturumuna engel değildir;
   gerçek bağımsızlık şartlarını sağladığı ayrıca değerlendirilir.
4. **Çalışma hızı:** [x] Dengeli; [ ] Turbo. Dengeli, yüksek kalite ile hız ve
   toplam maliyeti birlikte gözetir. Turbo, aynı kalite/kanıt şartlarıyla süreyi
   öne alır, faydalı paralelliği artırır; daha fazla tüketim doğurabilir. Her işi
   en güçlü modele/maksimum efora vermek anlamına gelmez. Bu iki mod varsayılanı
   bu nottaki öneridir; kullanıcı değiştirebilir.
5. **Kota yenilenmesini bekleme:** [x] Açık, kalan kota %10; [ ] Kapalı.
6. **Yönetici devri:** [x] Açık, kalan kota %10; [ ] Kapalı.
7. **Devirde yönetici seçimi:** [x] CLI havuzunda mevcut yöneticinin dahil
   olduğu havuzdan uygun eşdeğer aday; [ ] Belirttiğim havuz(lar);
   [ ] Katalogdan uygun aday; [ ] Belirttiğim hesap/model listesi.

Denetleyici seçimi ve Bağımsız İkinci Görüş ayrı açılış soruları olarak
tekrarlanmaz; görüşmede belirlenen işe/riskine göre seçim kuralları uygulanır.
Kullanıcı yalnız değiştireceği madde numaralarını ve değerlerini söyleyebilir.
Mevcut oturumda verdiği yanıtlar yeniden istenmez.

### Kota bekleme ve yönetici devrinin birlikte davranışı

- Önerilen eşikler kalan kota içindir: %15'te hedef/ilerleme/kanıtlar/gerçek
  sonraki adım kaydedilerek hazırlık yapılır; %10'da devir veya bekleme başlar.
  Kullanıcı başka devir eşiği seçerse hazırlık eşiği bunun üstünde olmalıdır.
- Devir açıksa önce yalnız izin verilen kaynak/havuz/model sınırları içinde
  hazır ve kotası yeterli halef aranır. Hazır halef varsa bekleme yerine sağlıklı
  devir yapılır. Önceki yönetici üretimi bırakır; halefin baton devralması
  doğrulanmadan devir tamamlandı sayılmaz. İki etkin yönetici oluşturulmaz.
- İzin verilen halef yoksa (tüm kotalar düşük, uygun eşdeğer yok, erişim yok)
  bekleme açıksa kaydedilmiş durumda beklenir. Kota/erişim doğrulanmadan işe
  devam edilmez. Bekleme kapalıysa kayıtlı durumda durulur ve neden bildirilir.
- Devir kapalıysa bekleme eşiğinde bekleme kuralı uygulanır; bekleme de kapalıysa
  otomatik kota kurtarma vaat edilmez. Gizli hesap/model/havuz değiştirme yoktur.
- Aynı havuz üyeliği tek başına eşdeğer yetenek kanıtı değildir. Mevcut model
  uygunluğu bilgisi kullanılır; eşdeğerlik bilinmiyorsa uydurulmaz, belirtilen
  kaynak dışına çıkılmaz. Normal seçimde model başına web araştırması yapılmaz.
- Gerçek bekleme/yeniden başlama ve devir, host/CAP yeteneklerine bağlıdır;
  kullanılamayan mekanizma varmış gibi gösterilmez. Uygulamada bu durum ve
  başarısız devirler açık durumlarla ele alınmalı; belirsiz "çalışıyor" bırakılmamalı.

## Tam kaldığımız nokta

Kullanıcı rol/denetim tartışmasını yukarıdaki sade karara bağladı; ardından hızın
çok önemli olduğunu ve aksini söylemedikçe paralel çoklu ajan çalışmanın
varsayılan olmasını istedi. Bu son tercih önceki Solo/Sıralı taslak varsayılanını
değiştirir; aktif runtime varsayılanı bu notla değiştirilmiş değildir.
Önceki "Yönetici uygulayıcı olabilir mi?" sorusu bu metinde, faydalı
olduğu işlerde yöneticinin doğrudan çalışabilmesi yönünde toparlandı. Son karar
metnini kısa biçimde kullanıcıya sun. Yeni bir onaylı uygulama isteği gelmeden
skill/runtime, çalışma ayarları veya dağıtımları değiştirme. Sonraki oturumda
yukarıdaki son işaretli gösterim ve karar metni üzerinden devam et; eski açık soruyu veya
geçersiz üç-katılımcı şartını yeniden başlangıç noktası yapma.
