# 03 — Yol Haritası

Sıralama: etki / efor. Her maddenin bir kabul kontrolü var.

## Faz 1 — Doğruluk ve süreklilik (P0) — ✅ tamamlandı (v2.0.0)

| Madde | Kabul kontrolü |
|---|---|
| Script'i SKILL'in merkezine al (boot, new, changed, validate, map, init) | `grep brain.py SKILL.md` → komut listesi; boot her oturumun ilk adımı |
| Tek durum makinesi (script = spec), tespit edilemeyen durumları kaldır | SKILL §2 tablosu = `cmd_boot` durumları |
| ID'ler asla tekrar kullanılmaz | `test_brain.py`: tüm görev dosyaları silindikten sonra `new` → PB-002 |
| Harness/kullanıcı önceliği, `git.commit`, `run.mode` | SKILL §1; boot `MODE:` satırı |
| Intake yönlendirme tablosu | SKILL §3, 7 mesaj tipi |
| Script hataları (porcelain, checkpoint eşleme, deps, status, ters mantık, exit kodu) | `python scripts/test_brain.py` → OK |

## Faz 2 — Token ve zayıf-model verimi (P1) — ✅ tamamlandı (v2.0.0)

| Madde | Kabul kontrolü |
|---|---|
| SKILL.md'yi yeniden yaz, tekrarları sil | 28.2KB → 12.1KB |
| Şema v4: kompakt görev başlığı, checkbox, `## Map`, `Sources:`, `commands:` | `init`/`new` şablonları; v3 hâlâ parse ediliyor |
| Boot tek ekran: PLAN, FOCUS, next, LOAD, CMDS, NEXT | Demo çıktısı ~15 satır |
| `changed`: domain başına checkpoint + Sources glob eşlemesi | test: harici commit → `STALE billing`, auth temiz |
| Bütçeler + yer tutucu kontrolü | `validate` WARN satırları |
| REFERENCE/SCHEMAS sıkıştırma, başlık-adresli REFERENCE | 20.6KB → 7.7KB, 10.8KB → 6.4KB |
| Description tetikleri, bitiş raporu, görev boyutu | SKILL frontmatter, §4, §5 |

## Faz 3 — Ölçüm ve otomasyon (öneri, yapılmadı)

| Madde | Neden | Kabul kontrolü |
|---|---|---|
| S1–S8 senaryolarıyla Haiku eval'i (`skill-creator` eval akışı) | "Zayıf model bile yapabilir" iddiasını ölçmek | Her senaryoda doğru ilk aksiyon; M2 ≤3 çağrı |
| SessionStart hook: `brain.py boot` çıktısını otomatik bağlama ekle | Model boot'u unutsa bile durum hazır; 1 çağrı daha az | `.project-brain/` olan repoda oturum açılışında STATE görünür |
| `brain.py commit --task PB-004 --verify domain --checkpoint auth` | Trailer biçim hatalarını sıfırlamak | Üretilen mesaj `git interpret-trailers --parse` ile okunuyor |
| `brain.py done PB-004`: dosyayı sil + validate + commit mesajı öner | Döngünün 8. adımını tek komuta indirmek | Test: görev silinir, boot "done +1" |
| SKILL.md'yi 10KB altına indirme denemesi | M1'i daha da düşürmek | Eval skorları düşmeden |
| `~/.claude/CLAUDE.md` içindeki "SKILL.md §10" → "SKILL.md Genesis section" | Numara kırılganlığı (F18) | Kullanıcı düzenler |

## Faz 4 — İsteğe bağlı genişlemeler (ihtiyaç doğarsa)

- Domain modunda `boot` LOAD'a yalnız ilgili target/<d>.md'yi ekleme (şu an planlama sırasında target tümüyle yüklenir).
- `map` çıktısını `.cache/map.txt`'ye yazıp değişmediyse tekrar üretmeme (büyük monorepolar için).
- Çoklu ajan için branch-başına görev sahipliği raporu (şimdilik REFERENCE "Worktrees" yeterli).
