# 04 — Sert Eleştiri (v2.0, saha verisiyle)

Yöntem: bu makinedeki **14 gerçek repo** (v1 ile kurulmuş Brain'ler) üzerinde `boot`/`validate` salt-okunur
çalıştırıldı, commit trailer disiplini ölçüldü, SKILL.md baştan taze gözle okundu. Puanlar değil, veriler.

## 1. Saha verisi: v1 gerçekte nasıl kullanılmış

| Gözlem | Ölçü | Örnek |
|---|---|---|
| Status satırı not defteri gibi kullanılmış | 24 görev | kamubul: `PLANNED. KULLANICI AÇIKÇA İSTEDİ: ...` |
| Status hiç yok, üçüncü bir format uydurulmuş | 16 görev | n-ai-science-lab: `Objective:` satır içi |
| Birden çok IN_PROGRESS (kural: tek) | 2/14 repo | halen-quit-smoking: 4 görev |
| Bitmiş görev dosyası tutulmuş (kural: sil) | 1 repo | rocketgame: `DONE (2026-09-29) — commit … Kanıt: …` |
| Acceptance yok / Verify yok | 34 / 29 görev | — |
| current.md bütçe aşımı | 4/14 repo | n-alphesis-lab: 463 satır (her yüklemede ~6–8k token) |
| Commit'lerde checkpoint trailer oranı | %27–%100 | halen 8/30, doctorfilter 11/30, store-publish 28/61 |
| Trailer adı ↔ mimari başlığı uyumsuz | yaygın | chatimus: `wallet` ↔ `Cüzdan & Ledger` |
| Eski protokol kalıntısı | 2 yer | kamubul `PROJECT_BRAIN.md`; `~/.gemini/GEMINI.md` var olmayan bir yola işaret ediyordu |
| Yüklü skill ≠ repo | 10 ajan | skills-manager kopyası v1'de kalmıştı; güncellemeler hiçbir ajanda aktif değildi |

**Ana ders:** Modeller kuralı okuyor ama uygulamıyor. Yazılı kural ≠ uyum. Uyumu artıran iki şey var:
kuralı koda taşımak (script hesaplar, model hesaplamaz) ve ihlali her oturumda görünür kılmak (boot `!` satırları).

Kanıt yeri yokluğu da dikkat çekiyor: modeller bitmiş görevi silmek yerine kanıtı görev dosyasına yazıp
tutmuş. Kanıtın meşru yeri tanımlanmamıştı. Artık commit gövdesindeki `Evidence:` satırı bu yer.

## 2. Bu oturumda v2'de bulunup düzeltilen kendi hatalarım

| # | Hata | Sahadaki etkisi | Düzeltme |
|---|---|---|---|
| 1 | Her `PB-Task` trailer'ı "bitti" sayılıyordu | 40 yanlış "ID geçmişte kullanılmış" uyarısı, şişik done sayıları | done = geçmiş − açık görevler |
| 2 | Format hatası boot'u INVALID'e düşürüyordu | 14 reponun 5'inde ajan dururdu | Toleranslı okuma; INVALID yalnız Current yoksa |
| 3 | Domain-başına checkpoint eşlemesi | chatimus'ta checkpoint = HEAD iken 8 sahte STALE | Tek taban |
| 4 | Taban = son checkpoint | Trailer'sız kendi commit'leri dış commit sayıldı (2 sahte ADVANCED) | Taban = mesajında `PB-` geçen son commit |
| 5 | INTERRUPTED'da yeni kullanıcı isteği yok sayılıyordu | "Son kullanıcı talimatı önce" kuralıyla çelişki | Önce Resume yaz, sonra Intake |
| 6 | Heredoc `\b`'yi backspace'e çevirdi | Hiçbir status okunmazdı | Testler yakaladı |

**Ders:** Sentetik test seti geçiyordu, ama gerçek veri 4 tasarım hatası gösterdi. Sentetik test tek başına yetersiz.

## 3. Hâlâ açık zayıflıklar

| Önem | Zayıflık | Neden önemli | Öneri |
|---|---|---|---|
| P0 | **Ana iddia ölçülmedi.** "Zayıf model bile yapar" için hiçbir küçük model koşusu yok | Bütün skorlar masa başı tahmin | 2–3 gerçek repoda S2/S3/S5 senaryolarıyla Haiku eval'i |
| P1 | Uyum zorlanmıyor; `validate` isteğe bağlı | Saha: 34 görevde Acceptance yok | `brain.py done PB-x`: dosyayı sil + validate + kanıtlı commit mesajı; opsiyonel commit-msg hook |
| P1 | 14 repo v3 formatında, otomatik geçiş yok | Satır aralığı ve checkbox tasarrufu mevcut projelere hiç ulaşmıyor | `brain.py migrate --dry-run` |
| P1 | SKILL.md yeniden büyüyor: 12.1 → 13.7KB (~3.7k token) | Her düzeltme metin ekliyor; 10KB hedefinin %37 üstünde | Eval sonrası, ölçüme dayalı kısaltma |
| P1 | `run.mode: continuous` varsayılan | store-publish-matic'te 22 açık görev var; tek istekten sonra saatlerce backlog işlenebilir | Varsayılanı kullanıcı seçmeli; `request` daha ucuz |
| P1 | Claude Code `AGENTS.md` okumuyor | Global CLAUDE.md olmayan başka bir makinede proje bloğu Claude'a ulaşmaz | Kabul edilmiş ödünleşim (ajan başına dosya oluşturmamak için) |
| P2 | Bayatlık tabanı "mesajında PB- geçen son commit" | İnsan "revert PB-12" atarsa öncesindeki dış değişiklikler gizlenir | Bilinçli ödünleşim, kodda `ponytail:` notuyla |
| P2 | Markdown regex ile okunuyor | Yeni varyantlar sessizce yanlış okunabilir (ör. `Durum: HAZIR` tanınmaz) | Toleranslı okuma + `validate` uyarıları; gerekirse TR eşanlamlıları |
| P2 | config.yaml basit alt-küme ile okunuyor | Liste/çok satırlı değerler sessizce kaybolur | Şablona sadık kalındıkça sorun yok |
| P2 | Global yönlendirmeler makineye özgü mutlak yol içeriyor | skills-manager yolu değişirse 7 dosya birden kırılır | Yol değişirse `pointer.py` ile yeniden yaz |
| P2 | Kimi, ZCode, Cursor'a global talimat yazılmadı | Konum bilinmiyor ya da ayar arayüzde | Proje `AGENTS.md`'si Cursor'ı kapsıyor |
| P2 | **Skill'in kendi reposu Git değil** | Git-native bir skill'in kaynağı sürüm kontrolünde değil; v1'in tek yedeği `review/v1-original/` | `git init` + ilk commit |

## 4. Öncelik sırası

1. `git init` (5 dk; geri dönüş imkânı).
2. Haiku eval: 2–3 gerçek repoda salt-okunur S2/S3/S5 (iddiayı ölç).
3. `brain.py done` (sahada en çok ihlal edilen adımı tek komuta indir).
4. `brain.py migrate --dry-run` (14 repoyu v4'e taşı; kazanç oraya ulaşsın).
5. `run.mode` varsayılanını kullanıcı belirlesin.
