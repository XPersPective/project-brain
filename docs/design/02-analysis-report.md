# 02 — Analiz Raporu (v2 promptunun skill'e uygulanması)

Kapsam: skill v1.0.0 (SKILL.md 882 satır, REFERENCE.md, SCHEMAS.md, scripts/brain.py).
"Sonra" sütunu v2.0.0 güncellemesinden sonraki durumdur.

## 1. Ölçümler

| Ölçüm | Önce (v1) | Sonra (v2) |
|---|---|---|
| M1 her oturum yüklenen | SKILL.md 28.2KB ≈ **7.6k token** | 12.1KB ≈ **3.2k token** (−%57) |
| M2 resume maliyeti | ~6–8 git komutu + tasks/ listesi + **her görev dosyası** + current/target/constraints ≈ 10–15 çağrı, 10k+ token | `PB boot` (1 çağrı, ~20 satır) + LOAD satırındaki 2–4 dosya (paralel) ≈ **2–3 çağrı** |
| M3 genesis maliyeti | serbest keşif + SCHEMAS okuma (2.7k) + elle şablon yazımı | `PB map` + ≤15 dosya + `PB init` (şablonlar hazır) |
| M4 görev başı ek yük | görev dosyası alan başına başlık, ID'yi elle bulma | `PB new` (ID + şablon), checkbox ilerleme, `PB validate` |
| REFERENCE / SCHEMAS | 20.6KB / 10.8KB | 7.7KB / 6.4KB |

## 2. Skor tablosu (0–5)

| Mercek | Önce | Sonra | Not |
|---|---|---|---|
| L1 Aktivasyon | 3 | 4 | Tetik ifadeleri (continue/resume/devam/kaldığın yerden, `.project-brain/`) eklendi |
| L2 Token ekonomisi | 2 | 4 | %57 küçülme, tekrarlar silindi, bütçeler + validator |
| L3 Zayıf-model determinizmi | 2 | 4 | Durum ve intake karar tabloları, sayısal eşikler, kesin komutlar |
| L4 Süreklilik | 2 | 5 | Boot tek ekranda plan + odak + sonraki adım + LOAD; ID asla tekrar kullanılmaz |
| L5 Niyet yakalama | 1 | 4 | Intake tablosu; kullanıcının sözü Objective'e birebir |
| L6 Durum modeli | 3 | 4 | Tespit edilemeyen durumlar kaldırıldı; v4 şema makine-okunur |
| L7 Koda devretme | 1 | 4 | Script SKILL'in merkezinde; 6 hata düzeltildi; map/init/new/changed eklendi |
| L8 Güvenlik/öncelik | 2 | 4 | Harness en üstte; `git.commit`, `run.mode` ayarları; soru politikası netleşti |
| L9 Doğrulama | 4 | 4 | Komutlar config'te; baseline `git worktree` ile (stash yasak) |
| L10 Bakım | 2 | 4 | Tekrarlar silindi; REFERENCE başlık-adresli; test script'i |

## 3. Senaryo masa testi

| Senaryo | Önce | Sonra |
|---|---|---|
| S1 Genesis | Keşif bütçesi yok, şablonlar elle | `map` → ≤15 dosya → `init` → doldur → `new` → `validate` → commit |
| S2 "devam et" | Script'ten habersiz; tüm görevleri açar; durum sırası belirsiz | `boot` → NEXT "start PB-00X" → LOAD dosyaları → döngü |
| S3 Çökme + kirli ağaç | Script INTERRUPTED/DIRTY'yi spec'ten farklı sıralar; ilk yol kırpık | Areas ile sahiplik ayrımı: içeride → INTERRUPTED + `next:`; dışarıda → DIRTY + yol listesi |
| S4 Yeni özellik | Yönlendirme yok; "durma, sıradakine geç" kuralı isteği gölgeleyebilir | Intake: `PB new` → backlog'un önüne |
| S5 Sadece soru | Yönlendirme yok; görev açma riski | Intake: Map + hedefli okuma, Brain'e yazma yok |
| S6 Hedef değişimi | §30 + REF §24 iki yerde | Intake tek satır + `PB-Target-Checkpoint` |
| S7 Araya insan commit'i | Domain grep'i hatalı, değişen dosya → domain eşlemesi yok | `boot` ADVANCED + `STALE <domain>: dosyalar`; `changed` ayrıntı |
| S8 Typo | "<2 dakika" ölçülemez | "≤1 dosya, ≤20 satır, davranış değişmez" |

## 4. Bulgular

| ID | Önem | Kanıt (v1) | Başarısızlık | Düzeltme | Durum |
|---|---|---|---|---|---|
| F1 | P0 | SKILL.md'de `brain.py` 0 kez geçiyor; README "SKILL.md'den çağrılır" diyor | Model her şeyi elle yapar: token + hata | Script SKILL'in merkezine alındı | ✅ |
| F2 | P0 | Görevler siliniyor, sonraki ID kuralı yok (SKILL §20, §35) | Git geçmişindeki ID tekrar kullanılır → trailer sorguları bozulur | `PB new`: max(dosyalar, git trailer'ları)+1; validate uyarır | ✅ |
| F3 | P0 | SKILL.md:37-55 "Never ask", oto commit, "durma" ↔ harness kuralları; §6'da harness yok | Zayıf model ya kuralı çiğner ya takılır | Öncelikte harness en üstte; `git.commit: auto/ask`, `run.mode` | ✅ |
| F4 | P0 | Boot yalnız repo durumunu sınıflıyor (SKILL §5) | Soru için görev açma, isteği bırakıp backlog'a dalma | §3 Intake tablosu | ✅ |
| F5 | P0 | Öncelik sırası script↔spec farklı; NO_GIT/checkpoint-yok → CLEAN_RESUME; BRANCH_CHANGED/HISTORY_REWRITTEN tespit edilemez (SKILL.md:152-153) | Yanlış dal; uygulanamayan talimat | Tek durum makinesi (script = spec), tespit edilemeyenler REFERENCE'a | ✅ |
| F6a | P0 | brain.py:63 `strip()` + :93 `line[3:]` | İlk kirli dosyanın yolu kırpılır | `rstrip` + `-z` porcelain | ✅ |
| F6b | P0 | brain.py:117-121 domain grep'i | `api,auth` ve `all` kaçırılır, `authz` yakalanır | Trailer'lar Python'da parse, `all` desteği | ✅ |
| F6c | P1 | brain.py:229 her `- PB-x` satırı bağımlılık | Notes'taki atıf sahte bağımlılık olur | Yalnız `Depends:` / `## Dependencies` | ✅ |
| F6d | P1 | brain.py:227 `Status: READY` parse edilmiyor (SKILL §20 bu biçimi gösteriyordu) | Geçerli görev "status yok" sayılır | v4 başlık satırları + v3 uyumu | ✅ |
| F6e | P1 | brain.py:505-511 BLOCKED bağımlılık atlanıyor (ters mantık) | READY görev açık bağımlılıkla başlar | Açık her bağımlılık uyarı | ✅ |
| F6f | P1 | brain.py:610 domain regex'i sonraki bölümleri de topluyor | Yanlış dosyalar yüklenir | `Domains:` başlık satırı | ✅ |
| F6g | P1 | boot normal durumlarda exit 1 | Zayıf model "script hata verdi" sanar | Başarılı sınıflandırma exit 0 | ✅ |
| F6h | P2 | `SKIP_DIRS` kullanılmıyor; `changed` domain çıkarımı vaat edip yapmıyor (:733) | Ölü kod, yanıltıcı çıktı | `map`'te kullanılıyor; `changed` Sources glob eşlemesi yapıyor | ✅ |
| F7 | P1 | ~%45 tekrar: §1/§45/REF34, §19/§41, §31/REF32, §43/REF31, §39/REF15, §42/REF26, §13/REF3, Golden Rules | Token israfı; çelişki riski | Tek yer kuralı; REFERENCE'tan SKILL tekrarları silindi | ✅ |
| F8 | P1 | "when useful", "materially", "<2 minutes" (SKILL.md:175) | Zayıf model karar veremez | Sayısal eşikler ve tablolar | ✅ |
| F9 | P1 | current.md şablonunda dosya haritası yok; komutlar saklanmıyor | Her oturum yeniden keşif | `## Map` + `config.commands` + boot `CMDS:` | ✅ |
| F10 | P1 | Boot sadece sayı basıyor | Plan için her görev dosyası açılır | Boot PLAN tablosu + FOCUS | ✅ |
| F11 | P1 | Görev şeması uzun, ilerleme takibi yok | Resume düzyazıya bağlı | Kompakt başlık + `- [ ]` checkbox | ✅ |
| F12 | P1 | Sıcak dosyalarda bütçe yok (§43 iddiasına rağmen) | Doğrusal büyüme | Bütçeler + validate uyarısı | ✅ |
| F13 | P1 | Genesis keşif bütçesi/iskele yok | Genesis'te token patlaması | `map` + ≤15 dosya + `init` | ✅ |
| F14 | P1 | Görev boyutu tanımsız | Zayıf model bağlam ortasında tükenir | ≤8 dosya / ≤300 satır / tek bağlam | ✅ |
| F15 | P1 | Description soyut | Tetiklenmeme | Tetik ifadeleri | ✅ |
| F16 | P1 | Bitiş raporu yok ("never report") | Kullanıcı kör kalır | ≤8 satır rapor formatı | ✅ |
| F17 | P2 | REFERENCE büyük ölçüde genel Git bilgisi | Gereksiz okuma | %63 küçüldü, başlık-adresli | ✅ |
| F18 | P2 | `~/.claude/CLAUDE.md` "SKILL.md §10"a atıf yapıyor | Numara değişince kırılır | Genesis artık §8; CLAUDE.md'de "Genesis section" yazılmalı | ⚠️ kullanıcıda |
| F19 | P2 | Test/eval yok | Gerilemeler fark edilmez | `scripts/test_brain.py` (script); model eval'i Faz 3 | ◑ |
| F20 | P2 | Domain adı normalizasyonu tanımsız | Trailer ↔ başlık uyuşmazlığı | lowercase-with-dashes kuralı | ✅ |
| F21 | P1 | "3 başarısız deneme → BLOCKED" ↔ "BLOCKED yalnız dış engel" çelişkisi (v1 §23 ↔ §20) | Model iki kural arasında kalır | BLOCKED tanımına açıkça eklendi | ✅ |

## 5. Korunan güçlü yönler

Git-native tasarım ve geçmişi çoğaltmama · "yeniden inşa maliyetine göre sakla" kuralı · current/target
ayrımı ve epistemik işaretler · bitince-sil · checkpoint trailer'ları · kirli ağaçta kullanıcı işini koruma ·
risk-orantılı doğrulama · ADR minimalizmi · tüm kenar durum kapsamı (REFERENCE'ta sıkıştırılmış olarak).

## 6. Bilinen sınırlar

- SKILL.md 12.1KB; 10KB hedefinin üstünde. Kalan içerik karar tablolarıdır; daha fazla kısaltma zayıf
  modelin determinizmini düşürür. Ölçüm Faz 3 eval'iyle yapılmalı.
- `fnmatch`'te `*` `/`'yi de geçer: `src/**/*.py` kök seviyedeki `src/a.py`'yi eşlemez. Pratikte
  `src/x/**` biçimi önerildiği için sorun değil.
- Shallow clone'da `new` gizli geçmişteki bir ID'yi yeniden verebilir (REFERENCE "Shallow"da belirtildi).
