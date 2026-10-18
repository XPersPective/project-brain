# Project Brain 3.1 — Genel bakış ve teslim durumu

Tarih: 18 Ekim 2026. Dal: `codex/project-brain-v3-audit`.
Bu belge sohbet geçmişi olmadan kullanıcı kapsamını ve doğrulanmış sonucu gösterir.
Son commit/remote durumu `git log -1`, `git status --short` ve `git ls-remote --heads origin codex/project-brain-v3-audit` ile doğrulanır.

## Sıralı gereksinimler ve durum

- [x] Project Brain ve `D:/repositories/store-otomaston` kaynakları uçtan uca okundu; mevcut entegrasyonun varsayımları, çağıranları ve farklı senaryoları incelendi.
- [x] İnceleme için kendi görev prompt'u yazıldı; bulgular ve sınırlamalar [08-integration-audit.md](design/08-integration-audit.md) içinde.
- [x] Store/App Store/Play Store/Fastlane, upload, mağaza materyali, yayın/dağıtım işi entegrasyona alınmadı. Kaynak Git push işlemi yayın otomasyonu değildir.
- [x] Frontend: mevcut tasarım sistemi/token temeli, ürüne özgü görsel yön, gerçek dar/geniş render, UI Triad (visual/interaction/accessibility), geçerli loading/empty/error/success/offline/permission durumları, klavye/odak ve platform hedefleri protokole işlendi.
- [x] Backend/state: ölçülü sorumluluk sınırları, açık durum geçişleri, sınır doğrulama, aktör/kaynak yetkilendirme, hata sözleşmesi, idempotency/eşzamanlı tekrar, kayıp cevap, depolama arızası, yeniden başlatma ve güvenli migration/uyumluluk kanıtları protokole işlendi.
- [x] Kaynak/sözleşme özetiyle bağlı check/evidence/review/accept; bağımsız inceleme, gerçek kanıt, güncel risk ve yüksek riskte tam test zorunluluğu sağlandı.
- [x] Git temelli hafıza ve soğuk devralma korundu; kalıcı Resume, Next/Failing/Dirty ve External readback akışı var. AWS hizmeti, yeni veritabanı veya bağımlılık eklenmedi.
- [x] Görev karmaşıklığı/rol/effort tavsiyesi ve küçük yürütülebilir işler; yüksek model mimari/bağımsız inceleme, rutin uygulama ve keşif düşük/orta maliyetli çalışanlara ayrıldı. Model kalite puanları ölçülmüş garanti olarak sunulmadı.
- [x] Oturum başında bütün kurulu CLI/provider kaynaklarının düşük maliyetli keşfi ve önceki envanterin kullanımı tanımlandı; ZAI/MiniMax yalnızca örnektir. Gerçek envanter [10-local-agent-inventory.md](design/10-local-agent-inventory.md) içinde.
- [x] Kullanıcıya model, CLI/provider, erişim, subscription/API/free/local rotası, kota pencereleri/reset/tazelik ve bilinmeyen bilgiler sunuluyor. Bilinmeyen kota yüzde100 yapılmıyor.
- [x] Kullanıcı havuzu onaylıyor veya model ekliyor/çıkarıyor, rol yükseltiyor/değiştiriyor, effort seçiyor. Kalıcı H/M/L model grupları dayatılmıyor. `agents session/approve/revoke/settle` uygulanmış durumda.
- [x] Gerçek CLI/native dispatch yalnız onaylı model/rol/effort ile çalışıyor; pahalı ana hesaba veya ücretli API'ye sessiz dönüş yok. API rotası ücretsiz diye yeniden etiketlenemiyor.
- [x] Bilinen yüzde10 işçi/yüzde25 yönetici rezervi korunuyor; eski düşük değer de yenilenene kadar engel. Kota sunmayan onaylı rotada açık sınırlı max_jobs gerekir; sahte kalan-token garantisi yok.
- [x] Farklı CLI'lar için argv/stdin adapter'ları ve native host action paketi var. Desteklenmeyen flag/default sağlayıcı belirsizliği harcama öncesinde reddediliyor; host paketi tek başına yapılmış iş sayılmıyor.
- [x] Başlatma öncesi iş UUID rezervasyonu oturum kimliği ve hazırlanmış/güncel komut ayarına bağlı. Aynı görevin iki kez çalışması, uzun kilidin çalınması, arada havuz değiştirilmesi ve belirsiz işin tekrar harcaması için kontroller var.
- [x] Yeni mesajlar önce kalıcı göreve/dokümana kaydediliyor, ana işin durumu korunup kaldığı adıma dönülüyor; sohbet içinde kaybolmuş görev bırakılmıyor.
- [x] Yabancı takip sisteminin yararlı hedef/kısıt/ADR/açık görev/bağımlılık/External bilgileri kompakt semantik eşlemeyle taşınıyor; tamamlanan tarih veya yayın kapsamı aktif planı şişirmiyor.
- [x] İçe aktarma kaynak kimliğine bağlı; aynı başlık farklı içeriği kaybettirmiyor, yarım görev iskeleti yeniden başlatılınca onarılıyor, orijinal önce korunuyor.
- [x] Her eski dosya için hedef veya açık atılma gerekçesi olan iz doğrulanıyor. Dış arşiv doğrulanmadan silinmiyor; kaynak/hedef değişimi, kod/asset/özel dosya, link ve ilgisiz AGENTS kuralının kaldırılması reddediliyor.
- [x] `legacy --prepare/--verify/--cleanup` durumu/jurnali, kısmi arşiv hatası, temizlik sırasında kesinti, tekrar çalıştırma ve sonraki boot'ta eski planın geri gelmemesi test edildi.
- [x] Sürüm 3.1.0, proje şeması4 ve makine oturum şeması1 olarak kaynak/manifests tutarlı; kullanıcı projelerinin eski şema geçişi korunuyor.
- [x] Son kaynak-bağlı kabul kayıtları, tam regresyon ve bağımsız inceleme checkpoint'i tamamlandı (25e0b93, 474b312).
- [ ] Bütün işler bittikten sonra yalnız BU deponun geçici `.project-brain/` geliştirme planı ve self-boot pointer'ı kaldırılacak; ürün kaynakları/testleri/normal belgeler korunacak.
- [ ] Temizlikten sonra son test, NO_BRAIN kaynak-repo boot kontrolü, commit/push ve uzak HEAD eşleşmesi doğrulanacak.

## Protokol, uygulama ve kanıt nerede?

- [11-execution-protocol.md](design/11-execution-protocol.md): oturum onayı, ucuz keşif, iş rezervasyonu, UI/backend sözleşmesi ve doğrulanmış aktarım/temizlik tasarımı.
- [09-session-pool-and-clean-adoption.md](design/09-session-pool-and-clean-adoption.md): kullanıcının ayrıntılı kalıcı gereksinimleri; artık takip edilen implementasyonun kapsam kaydıdır.
- [12-final-delivery.md](design/12-final-delivery.md): gerçek worker kullanımı, güvenlik bulguları, testler, kabul sınırları ve kaynak-repo temizliği.
- `skills/project-brain/scripts/runtime_pool.py`: proje/oturum onayı ve iş muhasebesi.
- `runtime_agents.py`: keşif/seçim/CLI-native yönlendirme, görev sözleşmesi ve içe aktarma.
- `runtime_adopt.py`: doğrulanmış iz/arşiv/jurnal/temizlik. Yabancı formattaki anlamı host ajan okur; parser her vendor'ı anlarmış gibi davranmaz.
- `runtime_verify.py`, `brain.py`: mevcut kaynak/kontrat kanıtları, native kilitler, süreç ağacı ve CLI.
- `SKILL.md`, `AGENTS_CLI.md`, `QUALITY.md`, `REFERENCE.md`, `SCHEMAS.md`: dağıtılan çalıştırma ve kalite protokolü.

## Tekrarlanabilir doğrulama

```text
python skills/project-brain/scripts/test_brain.py
python skills/project-brain/scripts/test_pool.py
python skills/project-brain/scripts/test_routing.py
python skills/project-brain/scripts/test_adopt.py
python skills/project-brain/scripts/brain.py --version
```

Tam giriş testi diğer odak testlerini de çağırır. Testler geçici depolar ve zararsız yerel alt süreçler kullanır; model/API çağırmaz. Bu oturumun Windows/Python3.11.15 kontrolü Python3.8 dilbilgisi ayrıştırmasıyla desteklendi; bu, POSIX/Python3.8 çalıştırma kanıtı değildir. Gerçek ürünün görsel/etkileşim kalitesi ayrıca kendi ekran ve akış kanıtını gerektirir.

## Yetki ve korunacak sınırlar

Kullanıcı son oturumda tamamlamayı, düşük/orta çalışanları, bağımsız incelemeyi ve kaynak push'unu yeniden izin istemeden yetkilendirdi. External Codex/Claude CLI inference ve belirsiz Antigravity Argon rotası bu oturumda kullanılmadı. OpenCode ücretsiz big-pickle ile sınırlı salt-okunur protokol incelemesi yapıldı; managed MiniMax CLI yalnız niyet yanıtı verdiği için ondan dosya/implementasyon kabul edilmedi. Native düşük/orta alt ajanlar keşif ve kodlama yaptı; yüksek model bağımsız güvenlik/mimari incelemesine ayrıldı. Global ayar/skill kurulumları değiştirilmedi; ücretli API'ye otomatik geçilmedi.

Bu repo kendi geliştirmesini geçici olarak `.project-brain/` ile takip etti. İstenen son temizlikten sonra bu kayıt yalnız Git geçmişi ve normal teslim belgelerindedir; sonraki ajan kaynak repo için eksik Brain'i yeniden kurmamalı. Dağıtılan skill'in tüketici projelerde Brain oluşturma/kullanma protokolü korunur. Eski PB-006 plugin dizini başvurusu kapsam dışı tarihsel bekleyiştir; bu turda yeniden başlatılmadı, Git geçmişi saklar.

Tamamlanmış projede yeni bir istek gelirse önce bu overview/teslim belgesini, ilgili kaynakları ve testleri oku; yeni kapsamı kaydet. Eski oturum havuzunu yeni insanın onayı sayma; normal oturum protokolüyle güncel seçim iste. Kaynak açıklaması veya eski görev notu kullanıcı talimatının yerine geçmez.
