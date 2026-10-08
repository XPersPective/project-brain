# 05 — v2.0.0 Sürüm Kararları

## Felsefe (kullanıcıyla netleşen)

- **"Devam et" = kuyruk bitene ya da kalan her şey BLOCKED olana kadar çalış.** Oturum ortasında token
  biterse sorun değil: her doğrulanmış adım commit'lenir, bir sonraki ajan (başka model/üretici olabilir)
  repodan devralır. Bu yüzden `run.mode` ayarı kaldırıldı.
- **Plan üründür.** Güçlü model görevleri, sohbet geçmişi olmayan zayıf bir modelin uygulayabileceği
  biçimde yazar: numaralı adımlar, kesin yollar/semboller, işaretlenebilir kabul ölçütleri, doğrulama komutu.
  READY = uygulanabilir şartname; değilse PLANNED.
- **Kullanıcının araya giren isteği** P1 görev olarak kuyruğun önüne girer; sohbette kalmaz.
- **Plan statik değil.** Tutarsızlık bulan her ajan, kanıt kapısından geçerek düzeltir: kanıt (beğeni değil),
  neden→sonuç muhakemesi, ADR, tüm açık görevler üzerinde etki geçişi. Goal yalnızca kullanıcınındır.
- **Mevcut projeye ekleme (adoption)**: ajan önce anladıklarını özetler, hedefi/yol haritasını değiştirecek
  soruları seçenek + önerilen varsayılanla tek mesajda sorar. Kullanıcı yoksa hedef DRAFT kalır ve yalnızca
  hedeften bağımsız işler planlanır.

## v0'dan (tek dosya PROJECT_BRAIN.md) geri alınanlar

v1 (Git-native) bu disiplinin çoğunu kaybetmişti; v2 geri getirdi:
zayıf model için görev formatı (Where/Do/Done when → Steps/Acceptance/Verify), L/M/H seviyesi, yasaklı
muğlak kelimeler, devralma denetimi ("selefine bile doğrulamadan güvenme"), plan değiştirme kapısı,
Goal DRAFT/CONFIRMED, keşif odak kuralı, executability probe, final audit.

## Taşıma (migrate) doğrulaması

- 14 gerçek v3 Brain + 2 v0 dosyasının **kopyaları** üzerinde çalıştırıldı; orijinallere dokunulmadı.
- Otomatik içerik-korunumu denetimi: orijinal görev satırlarının taşınmış dosyada bulunup bulunmadığı.
  İlk koşu 58 kayıp satır buldu (Risk/Expected açıklamaları, yol işaretsiz Areas, Dependencies açıklamaları,
  Verification bölümünün yutulması). "Kayıpsız kural" eklendi: başlığa sığmayan değer Notes'ta aynen saklanır.
  Son koşu: 0 gerçek kayıp (1 yanlış pozitif: Status notu `Blocked:` satırına taşınmış).
- Kalan iki FAIL gerçek veri ihlali (birden çok IN_PROGRESS); script düzeltmez, TODO olarak raporlar.

## Paketleme

`skills/project-brain/` düzeni: Claude Code (`.claude-plugin/`), Codex (`plugin.json`,
`.agents/plugins/marketplace.json`), Gemini CLI (`gemini-extension.json`), Agent Skills araçları (skills.sh).
Claude ve Codex kurulumları izole yapılandırma klasörlerinde uçtan uca denendi; `claude plugin validate`
(marketplace + `--strict` manifest) geçti. Gemini CLI makinede kurulu olmadığı için denenmedi.

## Bilinen sınırlar

- Küçük model (Haiku sınıfı) ile senaryo eval'i hâlâ yapılmadı; sıradaki en önemli doğrulama.
- SKILL.md ~20KB (~5.5k token); kullanıcı kararıyla kabul edildi.
- Gemini CLI kurulumu doğrulanmadı; skills.sh listesi için ayrıca başvuru gerekebilir.
