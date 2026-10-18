# Local coding agent and model inventory

Updated 2026-10-18 from local CLI metadata only. No model inference, quota RPC, credential contents, or paid API call was used. Access, billing, and quota remain separate facts.

## Current safe worker candidates

- **OpenCode built-in free catalog:** `opencode --pure models opencode --verbose` reports 10 models under provider `opencode`; inspected entries report input/output cost `0`. Examples: `opencode/big-pickle`, `opencode/deepseek-v4.1-flash-free`, and `opencode/glm-5.3-flash-free`. This is model metadata, not a guarantee of ongoing availability, service limits, account entitlement, or quality. `opencode auth list` reports three configured credential providers—Qwen Pay-to-Play (API), OpenAI (OAuth), and OpenRouter (API)—without needing to read credential files. Do not select their paid/API routes without explicit billing authorization. A cheap worker command supported by current help is `opencode run --pure -m opencode/big-pickle --variant low --dir <root> "<bounded task prompt>"`; `run` takes message arguments and exposes no stdin input option. `--pure` disables external plugins.
- **MiniMax Code:** `mcode provider list` reports `minimax_oauth` active via managed login and `minimax_api` enabled with no key. The subscription/usage terms and remaining quota are not exposed by this metadata, so do not infer either. `mcode exec --input - --cwd <root> --prompt-mode coding --permission off --timeout 2m --max-steps 20 "<bounded task prompt>"` is the supported non-TUI, stdin-capable invocation; omit `--model` to use its configured default. User explicitly permits MiniMax workers, subject to the account route's actual terms.
- **Native subagents:** available through the current Codex task's collaboration tools; user explicitly permits them.

## Other observed tools and exclusions

Codex 0.163.0-alpha.10.2, OpenCode 1.18.35, Claude Code 2.1.299, Gemini CLI 0.63.0, Antigravity `agy` 1.4.0, Qwen Code 0.21.3, MCode 0.6.8, Kimi 2.1.1, OmniRoute, Hermes, and LM Studio CLI are installed. Aider/Kilo aliases and Ollama were not found; LM Studio's daemon was not running. `kimi provider list` reports a managed Kimi OAuth provider with four models and default `kimi-code/k3-256k`; price/quota not verified. Qwen's and Hermes's configured access and price were not inspected. OmniRoute help loaded environment files, so its route inventory was skipped; no environment values were read.

- **Codex and Claude CLI jobs:** excluded for this session because the user reports their external quotas are exhausted. Cached quota snapshots are stale and do not override this instruction.
- **Antigravity:** exclude all `agy` model jobs because the Argon alias is unclear, as directed by the user.
- **OpenCode paid/API providers:** catalog/auth metadata shows configured providers, but no API routes are authorized. Use only an explicitly zero-cost OpenCode catalog model for the approved cheap-worker pool.
- **Gemini, Qwen, Kimi, OmniRoute, Hermes, and local LM Studio:** installation or provider metadata alone does not establish a permitted, available, or free worker route. Do not dispatch without separate confirmation of route and cost.

## Probe boundary

Read Project Brain discovery guidance and ran `python skills/project-brain/scripts/brain.py boot`; inspected bounded CLI help/provider/model metadata for OpenCode, MCode, Kimi, Qwen, Hermes, and OmniRoute. OpenCode verbose output included cost fields; only zero-cost entries from its own provider are candidates. MCode's managed OAuth source is active, but entitlement remains unknown. No registry, runtime, tests, configuration, or credentials were changed or read. No external model job was run.
