# Project Brain 3.0 — Master Prompt & Mimari Tasarım Belgesi

> Historical design proposal, not an implementation report. The implemented wire format
> remains schema 4. `WAITING_USER` uses BLOCKED; `READBACK_FIRST` is a boot result;
> `FIX` is not a persisted status. Discovery/adapters, quotas and model scores have the
> limitations in AGENTS_CLI.md. Quality needs real observations and independent review;
> no runtime can guarantee beautiful UI or an unexhausted subscription. The current
> acceptance prompt and verified audit results are in `08-integration-audit.md`.

Tarih: 2026-10-17  
Kapsam: `D:\repositories\project-brain` (Project Brain v2.1.0) ve `D:\repositories\store-otomaston` (Store Automation v4.2.0 + v2.4 CLI/Kota mirası) sentezlenerek **Project Brain 3.0 (Schema 5)** mimarisinin oluşturulması. Mağaza yayın/dağıtım (Play Store / App Store / Fastlane) katmanı kapsam dışıdır (ayrı bir yayın skill'i olarak tutulacaktır).

---

## 1. Kendimize (veya Başka Bir Üst Düzey Yapay Zekaya) Yazılacak Master Prompt

Aşağıdaki prompt, bu hedefi sıfırdan veya mevcut iki repodan alıp eksiksiz gerçekleştirmek için tasarlanmış **Master Sistem Promptu**dur:

```markdown
# ROL VE HEDEF: PROJECT BRAIN 3.0 MİMARİ DÖNÜŞÜMÜ

Sen kıdemli bir sistem mimarı, tasarım sistemi mühendisi ve çok-ajanlı (multi-agent) çalışma zamanı geliştiricisisin.
Görevin, `D:\repositories\project-brain` (Project Brain v2.1) reposunu incelemek, `D:\repositories\store-otomaston` (Store Automation v4.2) içindeki en güçlü state/kanıt/kalite/model-havuzu mekanizmalarını (mağaza yayın/dağıtım kısımları HARİÇ) buraya sentezlemek ve sistemi **kota dostu, CLI alt-ajan orkestrasyonlu, UI ve Backend kalitesini garanti altına alan Project Brain 3.0 (Schema 5)** seviyesine çıkarmaktır.

## ÇÖZÜLECEK 4 TEMEL SORUN

1. **Frontend / UI Kalitesizliği Sorunu:**
   - Ajanlar doğrudan ekran kodlamaya geçtiğinde şablon (generic) görünümlü, tutarsız renk/boşluk/tipografi kullanan, eksik durumlu (empty/loading/error/skeleton/offline olmayan) arayüzler üretiyor.
   - **Çözüm:**
     - UI içeren her projede ilk UI milestone'unda **Design System & Token Foundation** (renk rolleri, tipografi ölçeği, 4/8px spacing ritmi, radius, elevation, motion token'ları, 2-3 alternatif görsel yön ve ADR kararı) zorunlu kılınacak.
     - UI görevlerinde **UI Doğrulama Üçlüsü (Triad)** zorunlu olacak: `[visual]` (dar ve geniş ekran gerçek render/ekran görüntüsü kanıtı, sadece token kullanımı, açık/koyu tema uyumu), `[interaction]` (boş/yükleniyor/hata/başarı/çevrimdışı durumları, kullanıcı dilinde anlamlı hata mesajı, hata anında girdi koruma, çift tıklama/idempotency koruması), `[accessibility]` (klavye/odak sırası, minimum 48dp/44px dokunma alanı, WCAG AA kontrast ve %200 metin büyütmede taşmama).
     - `validate` ve `score` komutları UI dosyalarına (`*.tsx`, `*.jsx`, `*.vue`, `*.svelte`, `*.css`, `lib/**/ui/**`, `lib/**/presentation/**`, `lib/**/widgets/**` vb.) dokunan görevleri otomatik tespit edecek ve bu kriterler eksikse uyaracak/engelleyecek.
     - İnceleme (`review`) aşamasında şablon görünüm, ham hata mesajı veya token dışı sabit değerler `QUALITY` bulgusu olarak görevi doğrudan bloklayacak (`BLOCKED`).

2. **Backend ve State Mimarisi Sorunu:**
   - Dağınık katmanlar, boolean karmaşası (`isLoading && !isError`), yarış durumları (race condition), N+1 sorgular ve kırılgan hata yönetimi.
   - **Çözüm:**
     - Kesin katman sınırı: **Domain** (saf iş mantığı, sıfır framework bağımlılığı, fonksiyonel hata tipleri `Result`/`Either`), **Data** (repository implementasyonları, DTO/mapper, atomik transaction ve migration), **Presentation/State** (sealed state machine: `Initial | Loading | Loaded | Refreshing | Error | Empty | OfflineQueued`).
     - Backend/State görevlerinde zorunlu kanıtlar: sınırda şema/girdi doğrulama, yapılandırılmış hata sözleşmesi (`{"error": {"code", "message", "correlation_id"}}`), idempotency ve eşzamanlı tekrar (concurrent retry / `409 Conflict`), commit sonrası yanıt kaybı / depolama hatası kurtarma, sayfalama (pagination) + sıfır N+1 testi ve ileri/geri (up/down) migration doğrulaması.

3. **Kusursuz State, Kanıt Bağlama (Evidence-Binding) ve Soğuk Devralma (Cold Handoff):**
   - Herhangi bir ajan (Claude, Codex, Gemini, OpenCode, Qwen vb.) sohbet geçmişi olmadan sadece repodan işi devralabilmeli.
   - `store-otomaston` v4.2'deki en iyi mekanizmalar `.project-brain/` (`PB-NNN`, `PB-*` trailer'ları) kimliğiyle entegre edilecek:
     - Görev yaşam döngüsü: `PLANNED -> READY -> IN_PROGRESS -> REVIEW (MEDIUM/HIGH veya UI/Mimari) -> DONE` ve `BLOCKED` / `WAITING_USER`.
     - Boot durumları: `NO_BRAIN`, `LEGACY`, `RESUME`, `INTERRUPTED` (yalnız aktif görevin `Areas` dosyalarında commit'lenmemiş değişiklik varsa), `DIRTY` (aktif görev dışı kirli dosyalar), `ADVANCED` (domain bazlı checkpoint farkı, hızlı `git cat-file --batch` ile), `CONFLICTED`, `READBACK_FIRST` (`## External` altında `sent` veya `response_unknown` dış işlem varsa), `NO_GIT`, `INVALID`.
     - Mekanik kanıt ve sözleşme özeti: `start` (`Owner`, `--takeover`, `.cache/writer.lock`, `- ready by <id>:` kontrolü, `- start by <owner> | risk=<R> | contract=<hex>` kaydı), `check` (`ProcessTree` izolasyonu, temiz `PYTHONPYCACHEPREFIX`, secret env temizliği, `.cache/runs/` log hash doğrulaması), `evidence` (`--criterion`, `--file`, görsel/etkileşim kanıt zorunluluğu), `review` (`Reviewer != Owner` ve alias bağımsızlığı, `BLOCKER|MAJOR|QUALITY|MINOR` denetimi), `accept` (tüm kutular, güncel `areas_digest` ve `contract` özeti eşleşmesi, trailer üretimi).

4. **Görev Zorluk Ölçümü, Sistem CLI Ajan Taraması ve Kota Gözetimli Alt-Ajan Orkestrasyonu:**
   - **Zorluk ve Karmaşıklık Ölçümü (`PB score`):**
     - Her görevin zorluğu mekanik olarak 0–100 arasında puanlanacak (`complexity_score`), `computed_tier` (`L`, `M`, `H`), `recommended_effort` (`low`, `medium`, `high`) ve `risk_floor` (`LOW`, `MEDIUM`, `HIGH`) hesaplanacak.
     - Ölçütler: `Areas` dosya/glob sayısı, `Domains` (tek/çoklu alan), `Steps` sayısı, yüksek risk anahtar kelimeleri (auth, crypto, migration, concurrency, state-machine, payment vb.), UI/güvenlik/entegrasyon kriterleri ve belirsizlik/şablon eksikleri.
   - **Rol Dağılımı (Kotayı Bitirmeme İlkesi):**
     - **Yüksek Modeller (`Tier H`, `high` efor — Yürütücü / Mimar / Denetçi):** Sadece Genesis/kullanıcı görüşmesi, `target.md` + UI/Backend mimari kurgusu (`ADR`), işleri küçük ve sıfır belirsizlikli `Tier L/M` görevlere bölme, riskli görevlere `- ready by <id>:` onayı verme, gerçek `Tier H` çekirdek mimari dilimleri çözme ve alt ajanların bitirdiği işleri `PB review` / `PB accept` ile denetleme işini yapar.
     - **Düşük/Orta Modeller (`Tier L` + `low` efor, `Tier M` + `medium` efor — CLI Alt Ajanlar):** İyi tanımlanmış `READY` görevleri uygular, test/doğrulama koşularını ve özetlemeleri yapar.
   - **Sistem CLI Tarayıcı ve Kota/Abonelik Havuzu (`PB agents`):**
     - Kullanıcının sistemini tarayarak (`PB agents scan`) kurulu CLI ajanlarını (`codex`, `claude`, `gemini`, `opencode`, `agy`, `qwen`, `aider`, `kilocode`, `mcode`, `kimi`, `omniroute` ve yerel API/router uçlarını) bulur; `~/.project-brain/agents.json` içinde saklar (varsa `~/.store-automation/models.json` verisini de kayıpsız içeri aktarır).
     - Canlı abonelik ve kota kontrolü (`PB agents quota`):
       - `codex`: `codex login status` + `codex app-server --stdio` üzerinden model listesi, desteklenen eforlar (`low|medium|high`) ve canlı `account/rateLimits/read` (primary/secondary kalan kota % ve sıfırlanma zamanı).
       - `agy`: `agy models` + `agy --output-format json -p /usage` ve `/credits` üzerinden kalan kota grupları.
       - `opencode`: `opencode --pure models` üzerinden ücretsiz/yapılandırılmış sağlayıcı modelleri.
       - `claude`, `gemini`, `qwen` vb.: resmi auth/help kontrolleri ve kullanıcı/gözlem kota pencereleri.
     - **Kota Koruma Kuralları:**
       - Hiçbir abonelik havuzu `%10` rezerv sınırının (`worker_reserve = 10%`) altına düşürülmez.
       - Yürütücüyle paylaşılan bir havuzda alt ajanlar için `%20-%25` yürütücü rezervi (`director_reserve`) korunur ki yüksek modelin planlama ve review kotası asla bitmesin!
       - Görevin `Tier` ve `Risk` tabanını sağlayan **en düşük yeterli model ve en düşük yeterli efor (`low` veya `medium`)** seçilir (`PB agents select --task PB-NNN`).
   - **CLI Üzerinden Alt Ajana İş Verme (`PB delegate`):**
     - `PB delegate [root] <PB-NNN> [--cli ...] [--model ...] [--effort ...] [--mode apply|patch|probe] [--dry-run]`:
     - Görevin `READY` olduğunu doğrular, uygun CLI ajanını ve düşük/orta eforlu modeli seçer, görevi o ajan adına `start` eder, sadece görevin sözleşmesini + ilgili `current.md` kesitini + `constraints.md` + `Areas` dosyalarını içeren **kompakt, sıfır sohbet geçmişli bir görev paketi (prompt)** hazırlar, `ProcessTree` içinde CLI ajanını çalıştırır (`codex exec`, `opencode run`, `claude -p`, `gemini -p`, `agy --print`), bitince otomatik `PB check` koşar ve yürütücüye tek ekranlık özet rapor döner.

## UYGULAMA ADIMLARI
1. `.project-brain/` planını güncelle (`target.md`, `ADR-003.md`, görevler).
2. `skills/project-brain/scripts/` altında modüler, sıfır dış bağımlılıklı (Python stdlib) çalışma zamanını kur (`brain.py`, `runtime_verify.py`, `runtime_agents.py`, `migrate.py`).
3. `skills/project-brain/` belgelerini (`SKILL.md`, `SCHEMAS.md`, `REFERENCE.md`, `QUALITY.md`, `AGENTS_CLI.md`) eksiksiz ve birbiriyle %100 tutarlı şekilde güncelle.
4. `test_brain.py` içinde hem mevcut tüm regresyon testlerini (v0-v4 migration, checkpoint, recovery) hem de yeni 3.0 özelliklerini (`start`, `check`, `evidence`, `review`, `accept`, `score`, `agents scan/quota/select/merge`, `delegate`, `legacy`, UI/Backend kalite doğrulamaları) kapsayan kapsamlı test paketini çalıştır ve %100 PASS al.
5. Dağıtım manifestlerini (`plugin.json`, `.claude-plugin/`, `gemini-extension.json`, `README.md`, `CHANGELOG.md`) `3.0.0` sürümüne yükselt ve yerel ajan kurulumlarını güncelle.
```

---

## 2. İki Reponun Sentez Haritası (Neler Alındı, Neler Dışarıda Bırakıldı, Neler Yeni Eklendi)

| Alan | `project-brain` 2.1.0 | `store-otomaston` 4.2.0 + 2.4 | **Project Brain 3.0 (Yeni Sentez)** |
|---|---|---|---|
| **Kimlik & Dizin** | `.project-brain/`, `PB-NNN`, `PB-*` trailer, `config.yaml` | `.store-automation/`, `SA-NNN`, `SA-*`, `config.json` | `.project-brain/`, `PB-NNN`, `PB-*` trailer, `config.yaml` (ve `config.json` uyumu), Schema 5 |
| **Durum Makinesi (State)** | `PLANNED`, `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE` | + `REVIEW`, `WAITING_USER`, `READBACK_FIRST`, `FIX` | **Tamamı alındı:** `PLANNED`, `READY`, `IN_PROGRESS`, `REVIEW`, `BLOCKED` (`WAITING_USER` dahil), `DONE` + `READBACK_FIRST` & `FIX` kuyrukları |
| **Kanıt ve Kabul (`accept`)** | Serbest metin `## Evidence`, model kendi yazar | Araç tarafından yazılan `check`, `evidence`, `review`, `accept`; `areas_digest` + `contract` özeti; `ProcessTree` | **Tamamı alındı ve `PB` komutlarına entegre edildi** (`PB start`, `PB check`, `PB evidence`, `PB review`, `PB accept`) |
| **Zorluk Ölçümü (`score`)** | Yalnız elle yazılan `Tier: L\|M\|H` | Elle yazılan `Tier` + `HIGH_RISK_RE` uyarısı | **YENİ:** `PB score` — 0-100 zorluk puanı, otomatik `Tier` (`L/M/H`), `Effort` (`low/medium/high`), `Risk` tabanı, bölme (split) önerisi ve delege edilebilirlik analizi |
| **CLI Ajan Keşfi & Kota (`agents`)** | Yok | 4.2'de pasif `models.py`; 2.4'te `subscriptions.py` (`codex app-server`, `agy /usage`, `opencode models`) | **YENİ Birleşik Motor (`PB agents`):** Hem yerel CLI taraması (`codex`, `claude`, `gemini`, `opencode`, `agy`, `qwen`, `aider`, `omniroute`) ve canlı abonelik kotası okuma (`codex` RPC, `agy` JSON, `opencode` katalog) hem de benchmark/override tabanlı kalite seçimi + `%10` işçi / `%25` yürütücü kota rezervi! |
| **CLI Alt-Ajan Görev Yürütme (`delegate`)** | Yok (yalnız tavsiye) | 4.2'de yok; 2.4'te salt-okunur `CodexSession` | **YENİ (`PB delegate`):** Uygun CLI ajanına (`codex exec`, `opencode run`, `claude -p`, `gemini -p`, `agy --print`) düşük/orta eforla görev devretme, `ProcessTree` koruması ve otomatik `PB check` doğrulaması! |
| **Frontend (UI) & Backend Mimarisi** | Yok | `product-quality.md` (Premium bar + mağaza materyali) | **YENİ (`QUALITY.md` + Validator):** Zorunlu Design System Token Foundation, UI Triad (`[visual]`, `[interaction]`, `[accessibility]`), Clean Architecture + Sealed State Machine + Backend İdempotency/Concurrency/Migration kanıt kuralları |
| **Mağaza Yayın / Dağıtım** | Yok | `release.md`, `release-readback`, Fastlane, Play Store | **KAPSAM DIŞI (Alınmadı):** Kullanıcının talebi doğrultusunda mağaza yayını ayrı bir skill'e bırakıldı |
| **Geçmiş & Yabancı Plan Devralma** | `migrate.py` (v0 `PROJECT_BRAIN.md` ve şema ≤3) | `legacy.py` (`.project-brain`, `.taskmaster`, `memory-bank`, `.kiro/specs`, `.factory`) | **İkisi Birleştirildi:** `PB migrate` eski Brain şemalarını kayıpsız yükseltir; `PB legacy` ise `.store-automation`, `.taskmaster`, `memory-bank`, `.kiro/specs`, `.factory` gibi yabancı durum sistemlerini `.project-brain/` içine devralır! |
