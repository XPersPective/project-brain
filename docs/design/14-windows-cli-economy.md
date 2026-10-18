# Windows CLI, model havuzu ve abonelik bütçesi

## Kullanıcı kapsamı — 18 Ekim 2026

Windows hedeflidir. Kullanıcı dış CLI kullanımını yetkilendirdi; kaliteyi koruyan
ucuz modeller, ilk keşif için gerekirse küçük iç ajan, bütün rotaların ortak havuzu,
eksik seçili CLI kurulumu/giriş, her yeni ana oturumda güncel havuz onayı istedi.
Abonelik yüzdeleri token sayaçlarıyla karıştırılmayacak. Sohbetteki eski işler atlanmayacak.

Proje hafızası Git ve dosyalardır; SQL/veritabanı denetimi kapsamı yoktur.
Ana denetim: dosya ve Git durum tutarlılığı, güvenli yazma, kurtarma/devam,
Windows süreç yönetimi, bozuk girdiler, bağımsız inceleme ve ekonomik CLI orkestrasyonu.

### Sonradan eklenen gereksinimler — ana kapsamın devamı

- [x] Windows uygulama envanteri, PATH ve uygulamayla gelen CLI'leri birlikte keşfet;
  yeni bulunan araçları mevcut keşif listesine ekle, kullanıcı seçimlerini sessizce değiştirme.
  (`runtime_discovery.inventory_apps/windows_app_metadata/bundled_cli`; snapshot keşfi alt süreç
  başlatmaz, uygulama kaydı 0.01 s'de okunur; `test_discovery.py` bağlı.)
- [x] Her aracın kendi abonelik/ücretsiz hakkını araştır; abonelik yokluğunu erişim yokluğu sayma.
  (Doğrulanmamış erişim `unknown` kalır; OpenCode kataloğu `*-free` rotalarını getirir; canlı
  okuma yalnız desteklenen arayüzlerle: Codex RPC, Claude auth, OmniRoute katalog.)
- [x] OmniRoute'un mevcut model havuzunu da keşfet; sunucu kapalıysa otomatik başlat (`ensure_omniroute_server`), ücretli, ücretsiz ve bilinmeyen
  rotaları ayır. Aynı hesabın doğrudan ve yönlendirici rotalarını çift kota sayma.
  (`probe_catalog` + `omniroute api models get-api-models --output json`; sunucu kapalıysa `omniroute serve --daemon --no-open --no-tray` ile başlatılır ve `/api/health` doğrulanır; 118 modelin tamamı kesintisiz okunur (`catalog_status=ok`), worker dispatch için `omniroute chat --stdin --no-history` eklendi.)
- [x] `gemini` CLI Antigravity (`agy`) lehine kaldırıldı (`CLI_SPECS`, `APP_FAMILIES`, worker adapter ve `gemini-extension.json` temizlendi; `skills-manager` üzerinden devre dışı bırakıldı).
- [x] Havuzu sağlayıcı/hesap ve kullanım hakkına göre sun: abonelik, ücretsiz hak,
  ayrı ücretlenen API, yerel veya bilinmiyor; desteklenmeyen kota bilgisini uydurma.
- [x] Keşif ve gruplandırmadan sonra kullanıcıya kullanılacak rotaları sor;
  eksik CLI kurulumunu da seçime sun. Yeni keşif kullanım yetkisi değildir.
- [x] OpenCode için öncelik ücretsiz rotalar; kurulu ZCode gibi yerel sağlayıcı
  araçlarını başka bir yönlendiriciye yeniden bağlamak varsayılan çözüm değildir.
  (Protokol metinlerinde; yönlendirme eş maliyette dış CLI'yi, daha ucuz uygun iç rotayı gizlemez.)

ZCode 3.15.3 Windows uygulama kaydında bulundu. Birlikte gelen
`C:/Program Files/ZCode/resources/glm/zcode.cjs` mevcut Node ile çalıştırıldı;
`--help` başarıyla CLI 0.16.9 döndürdü. Bu, yeni kurulum gerektirmeyen bir CLI'dir.
Hesap, model seçimi ve kota erişimi henüz doğrulanmadı.

## Kabul listesi

- [x] İlk denetimdeki beş düzeltme ve regresyonları korunuyor (rapor 13).
- [x] Windows tam test paketi: test_brain.py çıkış 0; economy kontrolleri dahil.
- [x] Gerçek dış CLI: OpenCode 1.18.35 / opencode/big-pickle ile dosya üretimi ve yerel check.
- [x] İlk iş 180 saniyede zaman aşımı; süreç sonlandırıldı, scaffold okunup başarısız settlement yapıldı.
- [x] İkinci dar görev 49 saniyede tamamlandı; üretilen 300 denemelik test incelendi ve genişletildi.
- [x] Sağlayıcı kullanımını okuma: ikinci iş 101700 total, 7466 input, 667 output,
  1855 reasoning, 91712 cache_read, 0 cache_write; raporlanan cost 0; bunlar abonelik düşümü değildir.
- [x] Bilinen kalite tabanının rol onayıyla aşılması engellendi; ölçülmemiş worker yalnız LOW/L denemeye uygun.
- [x] Eş maliyette dış CLI tercih edilir; daha ucuz uygun iç rota gizlenmez.
- [x] Bozuk registry, iç içe tipler, JSON/Unicode argv, desteklenmeyen effort,
  kullanım sayaçları, kota sorgu arızası ve eski düşük kota için kontroller eklendi.
- [x] Her yeni ana oturumda güncel havuz ve yeni onay; aynı oturum worker'ları havuzu devralır — protokolde.
- [x] Ucuz deterministik keşif / küçük iç ajan bootstrap ve ortak havuz — protokolde.
- [x] Seçili eksik CLI için resmi Windows kurulumu, kullanıcı giriş adımı ve readback — protokolde.
- [x] Abonelik pencerelerini koruyan ve en dar kalan kotayı esas alan ortak kontrol;
  quota_windows ve eski 5h/7d alanları aynı uygunluk/dispatch kontrolüne girer (`_inventory` ve `_pool_status` senkronize edildi).
- [x] OmniRoute 3.8.50 sunucusu (`http://127.0.0.1:20128`) başlatıldı, Windows başlangıç otomatik başlatması (`vbs-startup`) etkinleştirildi, `agents scan` ve `delegate` içine otomatik sunucu başlatma eklendi ve 118 modelin tamamı (`catalog_status=ok`) okundu.
- [ ] Yeni kurulum/giriş akışının gerçek eksik araç/hesap üzerinde uçtan uca kanıtı.
- [ ] Z.AI hesabının bu makinede hangi CLI/profil üzerinden kullanıldığının doğrulanması ve canlı kota.
- [x] Tam regresyon çıkış 0; son pencere gösterimi ekinden sonra economy/pool testleri,
  git diff --check ve gerçek Codex RPC kota sorgusu geçti.
- [x] Regresyon düzeltmesi (18 Ekim, ikinci tur): genişleyen keşif `agents session --new`'i
  makinede 33-70 s'ye çıkarıp işlenmiş 15 s'lik CLI testini kilitliyordu. Kök neden: öneri
  yolu canlı `--version`/kota problarını sırayla ve toplam süresiz çalıştırıyordu. Düzeltme:
  öneri artık alt süreçsüz durum anlık görüntüsü (`snapshot_agents`; kayıt defteri + PATH +
  paketli CLI dosya varlığı, son bilinen sürüm/kota damgalarıyla taşınır) — gerçek makinede
  0.46 s; `agents scan` toplam `deadline` (varsayılan 90 s) aldı, bütçe bitince kalan CLI'ler
  `budget_exhausted`, bekleyen kota sorguları `deferred` olur. 6 s'lik bütçe denemesi 5.5 s'de
  durdu. Regresyon kontrolü `test_economy.py`'de: öneri sırasında hiçbir sonda başlatılamaz.
- [x] Üçüncü tam turdan sonra canlı doğrulama: tam tarama 11 CLI buldu (`zcode`, `codex`,
  `opencode`, `claude`, `agy`, `qwen`, `mcode`, `kimi`, `omniroute`, `lmstudio`, `hermes`; `gemini` CLI kaldırıldı); OpenCode
  kataloğu 430 model (`*-free` rotalar dahil); OmniRoute sunucusu çalışır durumda (`server_running=true`, `catalog_status=ok`, 118 model).

## Kanıt ve sınırlamalar

Canlı deneme geçici kökü: C:/Users/rubicon/AppData/Local/Temp/pb-live-cli-0ledv_0d.
Başarılı worker dosyası fuzz_checks.py; kalıcı genişletilmiş sürüm scripts/test_economy.py.
İki iş sınırı tüketildi; yeni çağrı için bu sınır sessizce sıfırlanmayacak.
İlk denemenin eski sabit log adı ikinci işte yeniden kullanıldı; artık log adında job UUID var.
İlk işin toplam tokenı bu yüzden güvenilir biçimde raporlanamıyor.

Keşifte OpenCode auth metadata'sı OpenAI OAuth, OpenRouter API ve qwen-paytopay API
gösterdi; Z.AI bulunmadı. Bu sonuç kullanıcının Z.AI aboneliği olmadığı anlamına gelmez.
Kimlik bilgisi dosyalarının içeriği okunmadı. Kurulum/giriş kuralları yazılmış olması,
bu adımların gerçek hesapla tamamlandığı anlamına gelmez.

18 Ekim 2026 gerçek Codex CLI RPC readback: plan plus; `primary_5h_remaining_pct` ve `weekly_7d_remaining_pct` pencereleri okunuyor ve en düşük pencere seçimi kısıtlıyor.
Bu sayaç bütün hesap kullanımına aittir, yalnız bu denetimin maliyeti değildir.

Resmi kaynaklar:
- https://docs.z.ai/devpack/tool/opencode (Coding Plan sağlayıcısı için ayrı login seçimi)
- https://docs.z.ai/devpack/extension/usage-query-plugin (Personal plan için resmi kota eklentisi)

## Resume

Next: eksik kurulum/giriş akışını gerçek ihtiyaç olduğunda uçtan uca dene; sırf kutu
işaretlemek için çalışan CLI'yi kaldırma. Z.AI (ZCode CLI) için desteklenen
canlı kota arayüzünü kullanıcı hesabı açıkken doğrula.
Failing: bilinen test başarısızlığı yok; `python -u skills/project-brain/scripts/test_brain.py`
çıkış 0.
Dirty: temiz; 3.2.0 sürümü commit/tag/push ve dağıtım için hazırlandı.
