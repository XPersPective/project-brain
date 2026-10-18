# Kaynak denetimi — 18 Ekim 2026

## İstek ve gerçek kapsam

Kullanıcı: “Bu projeyi baştan sona bir kontrol etsene … SQL düzgün yazılmış mı,
doğru çalışıyor mu, her türlü senaryo için uygun mu”. İncelenen kaynak
`skills/project-brain/`; kurulu skill kopyaları değiştirilmedi.

Bu depo bir Python CLI ve agent skill'idir. Çalıştırılan SQL, `.sql` dosyası,
veritabanı bağlantısı, ORM veya SQL migration bulunmadı. SQL/SQLite eşleşmeleri
kalite rehberi, dosya sınıflandırması ve test örneklerinden ibarettir. Dolayısıyla
SQL sorgularının doğruluğu hakkında bir test sonucu yoktur. Kalıcılık burada
dosyalar, Git, JSON oturum kayıtları ve ZIP kurtarma arşivleriyle sağlanır.

Kaynak deponun tamamlanmış geçici planı yeniden oluşturulmadı. Değişiklikler yerel
kaynak ve testlerdedir; global kayıt, gerçek model hesabı, kurulum ve yayın yapılmadı.

## Uygulanan denetim talimatı

> Önce gerçek mimariyi, giriş noktalarını, kalıcılığı ve depo kurallarını belirle.
> Eski teslim iddialarını güncel kanıt sayma. Mevcut tam test paketini çalıştır.
> CLI → doğrulama → durum değişimi → dosya/alt süreç → yeniden okuma akışlarını
> izle. Eksik/bozuk girdiler, onay/rol/kota sınırları, tekrar çalıştırma, eşzamanlı
> süreçler, zaman aşımı, kaynak/kontrat değişimi, bağlantılı yollar, arşiv ve
> migration kesintilerini sorgula. Her somut bulguyu yeniden üret; ortak kök
> nedeni en küçük değişiklikle düzelt ve hatayı yakalayan çalıştırılabilir kontrol
> bırak. Bağımlılık ekleme. Düzeltmeden sonra tam regresyonu, Python 3.8 sözdizimini,
> sürüm/manifests uyumunu ve diff'i doğrula. Uygulanmayan senaryoyu geçti sayma.

## Bulgular ve düzeltmeler

| Öncelik | Bulgu | Düzeltme ve kanıt |
| --- | --- | --- |
| P1 | Python 3.8–3.11'de `Path.is_junction` yok. Yalnız `is_symlink` ile yapılan kontrol, proje içindeki başka klasöre yönelen Windows junction'ını kabul ediyordu; eski log temizliği ilgili olmayan dosyaları silebilirdi. | `lstat().st_reparse_tag` kullanan ortak `is_link` kontrolü; public path, oturum ve arşiv çağıranlarına uygulandı. Windows'ta gerçek `mklink /J` ile test artık zorunlu; hedef logun değişmediği doğrulanıyor. |
| P2 | `agents merge` için `{"models": []}` girdisi başarılı sayılıp geçerli kayıt dosyasını bozuk biçimle değiştirebiliyordu. | Okuma, kaydetme ve merge sınırlarında şema/koleksiyon yapısı doğrulaması. Sekiz hatalı girdi hem yükleme hem merge için reddediliyor; kayıt dosyasının baytlarının değişmediği test ediliyor. |
| P2 | Migration normal dosyaları doğrudan `w` ile açıyordu; yazma kesintisi mevcut dosyayı yarım bırakabiliyordu. | Mevcut `write_atomic` yeniden kullanıldı; son şema güncellemesi hâlâ en sonda. Replace hatası enjekte edilerek eski task, eski şema ve yedeğin korunduğu; tekrar çalıştırmanın tamamlandığı sınanıyor. |
| P2 | Ortak atomik yazıcı replace öncesinde `fsync` çağırmıyordu. | Flush ve fsync replace öncesine eklendi. Fsync hatasında eski hedefin aynı kaldığı ve geçici dosyanın temizlendiği test ediliyor. Bu fiziksel güç kesintisi garantisi değildir. |
| P2 | Adoption test yardımcısı Python 3.10'da eklenen `Path.write_text(newline=...)` parametresini kullanıyordu; vaat edilen Python 3.8/3.9'da test çalışamazdı. | Aynı işlem desteklenen `Path.open(..., newline=...)` ile yapılıyor. Gerçek Python 3.8 çalıştırma kanıtı ayrıca gerekir. |

## Doğrulama kapsamı

| Alan | İnceleme / yürütülen kontroller |
| --- | --- |
| CLI ve proje durumu | Boot, init, görevler, bağımlılıklar, checkpoint, yarım oturum, geçersiz config ve kaynak deponun NO_BRAIN davranışı |
| Kanıt ve kabul | Kaynak/kontrat değişince eskime, log bütünlüğü, uygulayan kişinin kendini başka alias ile inceleyememesi, yüksek risk için tam test, External readback |
| Model havuzu | Onay/revoke, rol/effort sınırları, billing çelişkisi, bilinmeyen/eski kota, rezerv ve iş limiti, oturum/config değişimi, yarım iş settlement |
| Alt süreçler | Zararsız yerel süreçlerle Windows JobObject, timeout, büyük stdin, quoting, worker tamamlanması ve aynı checkout'ta çift dispatch engeli |
| Adoption | Kaynak/hedef değişimi, kod/özel dosya/bağlantı reddi, arşiv bütünlüğü, instruction korunması, kesintili temizlik ve tekrar çalıştırma |
| Migration ve dosya yazma | Eski verinin yedeği, tekrar başlatma, replace/fsync arızasında hedefin korunması |
| Dağıtım metadata'sı | İki JSON manifest (`plugin.json`, `.claude-plugin/plugin.json`) parse edildi; sürümleri CLI ve `SKILL.md` ile 3.2.0, proje şeması 4 (`gemini-extension.json` kaldırıldı). Referans verilen icon/logo ve SKILL.md mevcut. Mağaza/yayın doğrulaması kapsam dışı. |
| Uyumluluk | 16 Python dosyası Python 3.8 dilbilgisiyle parse edildi. Gerçek çalıştırma Windows / Python 3.11.15 üzerinde. |

Ana tekrar komutu:

```text
python -u skills/project-brain/scripts/test_brain.py
git diff --check
```

Tam test giriş noktası protocol, verify, agents, pool, routing, adoption, economy ve discovery testlerini
de çağırır. Yeni düzeltmeler mevcut testlere eklendi; yeni test framework'ü yok.

## Sonuç ve sınırlar

İlk tam test turu geçtiği hâlde ek adversarial senaryolar yukarıdaki sorunları
ortaya çıkardı. Junction ve bozuk registry davranışları düzeltme öncesi geçici
klasörlerde ayrıca yeniden üretildi. İlk dört düzeltmeden sonraki tam test turu
geçti. Fsync düzeltmesi dahil son tam tur sonucu aşağıda kaydedilir.

Bu denetim tek ajanla yapılmıştır; bağımsız ikinci inceleme iddiası yoktur.
Gerçek sağlayıcı/model çağrıları, canlı ücretlendirme/kota, Linux/macOS ve gerçek
Python 3.8/3.9 runtime bu turda çalıştırılmadı. Dosya korumaları, aynı yetkilerle
dosya sistemini eşzamanlı değiştiren kötü niyetli bir sürece karşı sandbox değildir.
Fsync tek dosyanın içeriğini aktarır; çok dosyalı işlem veya donanım/güç kesintisine
karşı tam transaction garantisi vermez. İnsan gözlemi, semantik migration eşlemesi
ve model seçimi hâlâ insan/host kararlarına bağlıdır. “Her olası senaryoda kusursuz”
sonucu çıkarılamaz; test edilmiş davranış ve kapsam burada açıkça ayrılmıştır.

Son tam doğrulama: Windows / Python 3.11.15 üzerinde
`python -u skills/project-brain/scripts/test_brain.py` çıkış kodu **0**.
Protocol, verification, agents, pool, routing, adoption, economy, discovery ve migration/kurtarma
kontrollerinin tümü geçti. Son kaynakta 16 dosyanın Python 3.8 dilbilgisi kontrolü
ve `git diff --check` de geçti.
