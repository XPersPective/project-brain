# Project Brain mimari ve davranış denetimi — 2026-10-08

## Karar

Temel mimari amaca uygun: Current, Target ve açık görevlerin ayrılması; geçmişin Git'te tutulması;
mekanik işlemlerin bağımlılıksız Python aracına bırakılması doğru seçimler. Yeni bir servis, veritabanı,
framework veya kapsamlı yeniden yazım gerekmiyor.

Ancak başlangıçtaki sürüme "güvenilir biçimde kaldığı yerden devam eder" demek erken olurdu.
Mevcut testler geçerken bile tamamlanma, mimari güncellik ve geçiş işlemleri yanlış bilgi üretebiliyordu.
Bu denetimde yeniden üretilebilen uygulama hataları ve yürütme talimatlarındaki çelişkiler düzeltildi.
"Her küçük model bunu doğru uygular" iddiası ise bir test sonucu değil; hâlâ ölçülmesi gereken hedef.

## Kapsam ve yöntem

- SKILL.md, SCHEMAS.md, REFERENCE.md, README, geçmiş tasarım kararları, tüm Python kaynakları ve testler okundu.
- Akış uçtan uca izlendi: boot → görev seçimi → uygulama → doğrulama → checkpoint → sonraki oturum.
- `parse_config`, `pb_base`, `staleness`, `history_task_ids`, `parse_task` ve geçiş kodunun çağıranları incelendi.
- Başlangıç testleri çalıştırıldı; ayrıca başlangıç kaynak kodu geçici dizinde yüklenerek öncesi/sonrası karşılaştırıldı.
- Geçici Git depolarında WIP, dış değişiklik, kısmi checkpoint, eksik bağımlılık, Git'siz çalışma ve kesinti sınandı.
- Ayrı bir inceleyici ajan, protokolü dar istek, salt soru, commit yasağı, PLANNED ve kesinti senaryolarıyla okudu.
  Buna ek olarak GPT-6-Luna ile izole bir depoda gerçek hata düzeltme deneyi yapıldı: yanlış toplam düzeltildi,
  üç assertion geçti, P3 backlog görevi çalıştırılmadı, commit sayısı 1 kaldı ve DONE+Evidence korundu.
  Sonuçlar ana ajan tarafından dosya, Git geçmişi ve test çalıştırmasıyla bağımsız doğrulandı.
  İkinci deneyde legacy PROJECT_BRAIN.md bulunan depoda yalnız soru soruldu; model doğru fonksiyonu
  açıkladı, migration başlatmadı, dosya yazmadı ve test çalıştırmadı.
- Kaynak düzeltmeleri GitHub'a push edildi; 2.1.0 kamuya açık release olarak yayımlandı. Skill Manager
  merkezi kopyası ve 41 yönetilen ajan hedefinin altı kaynak dosyası birebir doğrulanarak güncellendi.

## Bulgular ve düzeltmeler

| Önem | Önceki sorun ve etkisi | Düzeltme ve kanıt |
|---|---|---|
| P1 | Son PB ifadesi taşıyan commit tüm mimariyi taze sayıyordu. Auth/billing değişikliğinden sonra yalnız bir kural commit'i her iki değişikliği gizliyordu. | `brain.py:pb_base/staleness` gerçek, WIP olmayan domain checkpoint'lerini kullanıyor. Auth checkpoint'i billing değişikliğini açık bırakıyor. `recovery_checks` bunu sınar. |
| P1 | Dosyası bulunmayan görev, WIP veya terk edilmiş olsa bile tamamlanmış kabul edilebiliyordu. Bilinmeyen PB-999 bağımlılığı çalışmayı engellemiyordu. | `closed_ids` doğrulama trailer'ı ve o commit'te silinme veya DONE+Evidence arıyor. `boot` yalnız kanıtlanmış bağımlıları seçiyor. Başlangıç kodu PB-999 bağımlısını seçerken düzeltilmiş kod seçmiyor. |
| P1 | Görevi commit'ten önce silmek, özellikle yeni/henüz izlenmeyen görevde amaç ve kanıtı kaybedebiliyordu. | Doğrulanmış görev DONE+Evidence olarak kodla birlikte commit edilir; silme başarılı commit'ten sonra olur. Temizlik sonraki yetkili commit'e katılır. Commit beklerken/Git yokken dosya saklanır. `recovery_checks` kayıtlı ve yerel tamamlanmayı sınar. |
| P1 | `Status: DONE` fakat Evidence olmayan görev hem açık hem tamamlanmış sayaçtan düşüyordu. | Böyle kayıtlar açık kalır ve bağımlılarını açmaz. Boş kuyruk/final audit olarak sunulmaz; ayrı regresyon kontrolü var. |
| P1 | Tırnaklı komutların kaçışları çözülmüyor, tırnak içindeki ` #` yorum sanılıyordu. Dönüşüm yalnız test/lint/build komutlarını tutuyordu. | JSON kaçışlı çift tırnak, YAML tek tırnak ve dış yorum ayrımı; özel/boş komutlar ve desteklenen ek alanlar korunuyor. `persistence_checks` tam round-trip yapıyor. Başlangıç sürümünde komut round-trip'i başarısızdı. |
| P1 | Migration şema 4'ü önce yazıyordu; sonraki yazma kesilirse araç "zaten taşınmış" diyebiliyordu. Ham içerik ve görev Priority/Tier kaybolabiliyordu. | Orijinaller `migration-backup/` altında saklanır; Priority/Tier korunur; şema son adımda dosya değiştirmeyle tamamlanır. Enjekte edilmiş yazma hatası ve kesilmiş task dosyasından yeniden çalıştırma test edilir. |
| P1 | Onay statüsü olmayan eski hedef otomatik CONFIRMED yapılıyordu. | Onay yokluğu DRAFT olur. Mevcut açık CONFIRMED/DRAFT bilgisi korunur; ajan eksik onayı kullanıcı niyeti olarak uyduramaz. |
| P1 | Dar bug fix §4 üzerinden ilgisiz tüm backlog'a yayılıyor; salt soru, intake'ten önce migration/commit/test başlatabiliyordu. | Intake önce gelir. Yeni istek ve önkoşulları kapsamı belirler; kuyruk geneli yalnız devam yetkisiyle çalışır. Helper NEXT metinleri de aynı sırayı izler. |
| P1 | Python 3.8+ şartına rağmen `Path.write_text(newline=...)` kullanılıyordu; bu argüman 3.10'da eklenmiştir. | Python 3.8'de bulunan `Path.open(..., newline=...)` kullanılır. 3.8 sözdizimi kontrolü geçti; tam testler ayrıca Python 3.8.20 üzerinde geçti. [Python belgesi](https://docs.python.org/3/library/pathlib.html#pathlib.Path.write_text). |
| P2 | Yeni görev iskeleti READY oluyordu; hiç commit trailer'ı olmayan eski task ID'leri yeniden kullanılabiliyordu. | Yeni iskelet PLANNED. ID rezervasyonu açık dosyalar, Git dosya geçmişi/trailer'ları ve v0 yedeğindeki numaraları kapsar. T99 kapalı eski görevinden sonra PB-100 üretilir. |
| P2 | Domain modunda odak yoksa Current yüklenmeyebiliyor; odak varken global hedef dışarıda kalıyordu. | LOAD global target.md ve hedef parçalarını her zaman, ilgili Current dosyalarını da odak durumuna göre içerir. Global Goal/Status için target.md gereklidir. |
| P2 | `git add <paths>` önceden staged kullanıcı işini sonraki normal commit'ten dışlamaz. | Protokol index incelemesi ve gerektiğinde `git commit --only -- <owned paths>` ister; aynı dosyadaki bilinmeyen değişiklikleri sahiplenmez. |
| P2 | A READY tamamlanınca B PLANNED için aynı oturumdaki seçim döngüsünde terfi adımı eksikti. | Checkpoint sonrası boot ve bağımlılığı çözülmüş görevin şartnamesini tamamlayıp terfi ettirme açıkça tanımlandı. |
| P2 | README yazma etkileri `new` komutunu dışarıda bırakıyordu. | Etki listesine `new` eklendi; migration'ın ham veriyi koruma ile otomatik semantik dönüşüm arasındaki sınırı açıklandı. |

Ek uygulama ayrıntısı: `git_paths` NUL seçeneğini komutun başına geçirir. Böylece `--` pathspec ayırıcısı
olan `ls-tree` çağrısında seçenek dosya adı sayılmaz; birden fazla görev dosyası doğru ayrılır.

## Mimaride korunması gerekenler

**Niyet ve gerçek durum ayrımı:** Hedefi mevcut koddan türetmemek, Current'ı ise hedefe uydurmamak
temel gereklilik. Goal yalnız kullanıcıya ait; karar gerekçesi ADR'de; kanıt test/commit'te kalıyor.

**Tek otorite ve az altyapı:** Dosyalar taşınabilir ve insan tarafından okunabilir. CLI hesapladığı durumu
gösteriyor; otomatik komut yürütme, commit/push, ağ çağrısı veya gizli senkronizasyon servisi eklenmedi.

**Mekanik doğrulama ile anlam doğrulamasını ayırmak:** Script task biçimini ve geçmiş kanıtını denetleyebilir.
"Bu plan gerçekten kullanıcı hedefine hizmet ediyor mu?" sorusunu regex çözemez; ajanın kod okuması gerekir.
Bu nedenle boot/Map başlangıç noktasıdır, kaynak incelemesini yasaklayan bir otorite değildir.

**Test düzeni:** Mevcut assert tabanlı tek dosya yeterliydi; yeni framework veya fixture sistemi eklenmedi.
Kontroller gerçek geçici Git depolarıyla ve migration yazma hatası enjeksiyonuyla davranışı sınar.

## Doğrulama sonuçları

| Kontrol | Sonuç / kapsam |
|---|---|
| `python skills/project-brain/scripts/test_brain.py` | Baseline, migration, checkpoint/dependency recovery ve persistence/kesinti grupları geçti. |
| `python skills/project-brain/scripts/brain.py validate` | Bu deponun planında 0 fail, 0 warn. |
| Skill Creator `quick_validate.py skills/project-brain` | Skill frontmatter geçerli. Davranış doğruluğunu tek başına kanıtlamaz. |
| Python `ast.parse(..., feature_version=(3,8))` | Üç Python dosyası 3.8 sözdizimiyle ayrışıyor. Tam çalışma zamanı doğrulaması 3.8.20 ve 3.11.15 üzerinde. |
| `claude plugin validate .` | Başarılı; beş metadata alanı için uyarı: icon, documentationUrl, supportUrl, privacyPolicyUrl, termsOfServiceUrl. CLI bunları yok saydığını bildiriyor. |
| `git diff --check` | Boşluk/patch hatası yok. |
| Başlangıç koduyla ayrı karşılaştırma | Tırnaklı komut ve bilinmeyen bağımlılık senaryolarında hata önce mevcut, düzeltmeden sonra yok. |

Claude uyarıları geçmişte dizin listelemesi için bilerek eklenmiş metadata'dan geliyor. Bu alanları sırf
yerel yükleyici kullanmıyor diye kaldırmak taşınabilir paketleme amacına aykırı olurdu; korundu.
Kamuya açık GitHub deposundan Codex ve Claude Code'un yerel marketplace komutlarıyla ayrı profillere
kurulum yapıldı; ikisi de 2.1.0 bildirdi. `skills` CLI ile ayrı projeye kurulum da geçti.
Bu kurulum testleri sağlayıcıların resmî katalog onayı anlamına gelmez; Gemini çalışma zamanı sınanmadı.

## Yayın ve kurulum kanıtı

- [2.1.0 GitHub release](https://github.com/XPersPective/project-brain/releases/tag/v2.1.0): herkese açık,
  taslak olmayan yayın; ZIP ve SHA256SUMS indirilebilir.
- ZIP 95.848 bayt; kimlik doğrulaması olmadan indirilen dosyanın SHA256 değeri
  `745ead03e7b59186a4a3ddf78c43c293d874f0912e931711f2e198fd6e1338fd`; yerel paketle aynı.
- Skill Manager mevcut yönetilen kaynağı güncelledi; yeni paralel global kopya oluşturulmadı.
  41 hedef için içerik doğrulaması yapıldı; 41 ayrı ajan çalışma zamanı testi yapıldığı iddia edilmiyor.
- 2026-10-09: Claude resmî katalog başvurusu gönderildi; 2.1.0 algılandı. Güvenlik taraması ve Anthropic
  incelemesi bekleniyor; henüz canlı katalog yayını yok. OpenAI girişi insan doğrulama adımında bekliyor.

## Kalan sınırlar ve ölçülmesi gerekenler

1. **Model davranışı:** GPT-6-Luna dar bug fix + commit yasağı + ilgisiz backlog senaryosunu geçti.
   İki kontrollü senaryo sınandı; farklı üreticiler, karmaşık mimari işler ve uzun kesinti zincirleri için
   genellenemez. Sonraki ölçüm farklı modellerle aynı görevlerin ve devir senaryolarının tekrarlanmasıdır.
2. **Git geçmişi:** Shallow clone, squash sırasında trailer kaybı veya erişilemeyen geçmiş için sınırsız ID
   benzersizliği/kanıt garantisi yok. Araç eksik kanıtı tamamlanma saymaz; REFERENCE uzlaştırma yolunu anlatır.
3. **Legacy fallback:** Eski Current dosyasına son dokunan commit gerçek bir domain doğrulaması olmayabilir.
   İlk takeover'da kaynak kontrolü ve açık checkpoint gerekir.
4. **YAML alt kümesi:** Tam YAML kütüphanesi eklenmedi. Desteklenmeyen biçimler artık sessiz veri kaybı yerine
   açık hata üretir. Böyle bir dosya elle desteklenen skaler biçime dönüştürülmelidir.
5. **Geçişin semantik sınırı:** Ham yedek kayıpsızdır; dönüştürücünün tanımadığı özel notların doğru hedef
   bölüme yerleştiği garanti edilmez. Yedek incelenmeden veya ID rezervasyonu taşınmadan silinmemelidir.
6. **Ölçek ve paralellik:** Geçmiş taramaları Git çağrıları yapar; büyük tarihçe için performans ölçümü yok.
   Ayrı worktree'lerde eşzamanlı ID üretimi hâlâ uzlaştırma gerektirir. Tek dizinde `new`, var olan dosyanın
   üstüne yazmaz; ancak dağıtık ID tahsisi sağlamaz.
7. **Talimat hacmi:** SKILL hâlâ ayrıntılı. Kritik kurtarma kurallarını çıkarmak yerine mevcut destek
   dosyaları kullanıldı. Daha fazla kısaltma ancak davranış deneyiyle, atlanan adımlar ölçülerek yapılmalı.

Değerlendirme: bu düzeltmelerden sonra araç, sınanan yerel kayıt/geri kazanım akışlarında amacına uygun
çalışıyor. Bütün modeli, platformu, Git tarihçesini ve özel legacy biçimini kapsayan mutlak süreklilik
vaadi verilmemeli. En değerli sonraki yatırım daha fazla mimari katman değil, gerçek ajan davranış ölçümüdür.
