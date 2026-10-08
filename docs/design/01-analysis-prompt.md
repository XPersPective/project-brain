# 01 — Skill Analiz Promptu (v1 → denetim → v2)

Bu dosya, `project-brain` gibi "agent skill"lerini analiz etmek için yazılan promptun evrimidir.
Prompt metni modele verileceği için İngilizcedir; açıklamalar Türkçedir.

## v1 (ilk taslak)

> You are a skill auditor. Evaluate SKILL.md, its references and scripts for clarity, completeness,
> token efficiency and safety. List strengths, weaknesses and recommendations.

## v1 denetimi — neden yetersiz

| Eksik | Sonucu |
|---|---|
| Ölçülebilir hedef yok | "İyi" tanımsız; her öneri eşit ağırlıkta görünür |
| Zayıf model simülasyonu yok | Güçlü modelin kolayca tolere ettiği muğlaklıklar görünmez kalır |
| Token ölçümü yok | "Kısa olmalı" gibi genel tavsiyeler üretir |
| Kanıt (dosya:satır) zorunluluğu yok | Doğrulanamaz, uydurma bulgu riski |
| Senaryo yürütmesi yok | Akış hataları (yanlış sıra, eksik dal) yakalanmaz |
| Önem/öncelik yok | Yol haritasına dönüşmez |
| Doküman ↔ script tutarlılık kontrolü yok | Script'in hiç çağrılmaması gibi en büyük hata kaçar |
| Host harness çatışma kontrolü yok | "Never ask / auto-commit" ile Claude Code kuralları çatışması kaçar |
| "Koda devretme" merceği yok | Modelin mekanik işi elle yapması (token + hata) fark edilmez |
| Zamanla büyüme merceği yok | Sıcak dosyaların şişmesi fark edilmez |
| Fren yok | "Her şeyi yeniden yaz" eğilimi; çalışan mimari gereksiz yere atılabilir |

## v2 (nihai prompt)

```text
ROLE
You audit an agent skill (SKILL.md + reference files + scripts). The skill's purpose: let a coding
agent keep persistent project state (current architecture, approved target, open tasks) and resume
work across sessions.

NORTH STAR (score everything against it)
A zero-context, Haiku-class model:
  - on resume: takes the correct next step within ≤3 tool calls and ≤4k tokens of reading;
  - on genesis: maps the repo once, never re-scans it in later sessions;
  - routes any user message (question / trivial edit / continue / new work / goal change / rule)
    to the right action without guessing.

INPUT
Read every file of the skill completely. Run or statically trace every script.

MEASURE
  M1 tokens loaded every session (SKILL.md + description)      chars / 3.7
  M2 resume cost: tool calls + tokens read until the first productive edit
  M3 genesis cost: calls + tokens until the first checkpoint commit
  M4 per-task overhead: Brain reads/writes per task beyond the code itself

LENSES (score each 0–5, with one-line justification)
  L1  Activation: does the description trigger on the right phrases/situations, and not on others?
  L2  Token economy: size, % duplicated content across files, progressive disclosure, growth over time.
  L3  Weak-model determinism: vague words ("when useful", "materially"), judgment calls without a
      default, cross-reference jumps, decision tables vs prose, exact commands, defaults for every branch.
  L4  Continuity: one source for "next action"; no re-scans; stable IDs; handoff fidelity.
  L5  Intent capture: user message → action routing; verbatim intent recorded; goal changes; questions.
  L6  State model: completeness of the state machine; invariants; is every listed state detectable?
      Are file formats machine-parseable?
  L7  Code offload: which mechanical steps does the model do by hand that a script could do?
      Does the doc call the script? Do doc and script agree? Script bugs? Cross-platform?
  L8  Safety & precedence: destructive operations; conflicts with the host harness rules
      (commit/push/ask policies); runaway autonomy.
  L9  Verification: gates, stored commands, baseline failures, evidence.
  L10 Maintainability: duplication between files, fragile numbering, external references to the skill.

SCENARIOS (walk through each as the weak model; count calls/tokens; mark every guess)
  S1 genesis on a half-built repo   S2 next day, user says "continue"
  S3 crash mid-task, dirty tree     S4 user asks for a new feature
  S5 user only asks a question      S6 user changes the goal
  S7 a human committed in between   S8 one-line typo fix

FINDINGS FORMAT
  ID | lens | severity | evidence (file:line) | failure scenario | fix | cost
  severity: P0 breaks correctness or continuity; P1 large token or weak-model cost; P2 polish.

RULES
  - No generic advice. Every finding cites evidence and a concrete failure scenario.
  - Prefer deletion and code offload over adding prose.
  - Keep the architecture (Git-native, current/target/tasks, delete-on-complete, trailers) unless a
    finding proves it wrong; list explicitly what to keep.
  - Separate "missing" from "could be better".

OUTPUT
  1. Measurements M1–M4.  2. Scorecard L1–L10 (now → achievable).  3. Scenario table.
  4. Findings sorted by severity.  5. Strengths to keep.  6. Roadmap: phases ordered by
  impact/effort, each item with an acceptance check.
```
