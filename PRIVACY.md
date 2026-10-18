# Privacy Policy — Project Brain

Last updated: 2026-10-18

Project Brain is an open-source skill (instructions plus local Python scripts) for coding agents.

- **No hosted service.** Project Brain has no server, analytics or telemetry of its own.
- **Local state.** Scripts read repository files and Git metadata, write `.project-brain/`,
  instruction pointers, local verification/worker logs, and the machine registry
  `~/.project-brain/agents.json` (CLI paths, model configuration, account/quota metadata)
  and adjacent project-scoped session records (user selections, approval note, job states).
  It does not intentionally read credential contents. Local task/log content may be sensitive;
  inspect it before sharing or committing it.
- **Commands and providers.** `check` runs the configured Verify commands. `agents scan/quota`
  can invoke installed CLI tools to query account metadata; those tools may contact their
  providers. `delegate` sends task/project context to the selected coding CLI, whose
  provider, tools and network permissions apply. Process containment terminates descendants;
  it is not a filesystem or network sandbox. No automatic paid API fallback is authorized.
- **Your agent.** The coding agent that loads the skill (Claude, Codex, Gemini or another) is governed by
  that provider's own privacy policy. Project Brain instructs agents never to store secrets or
  credentials in its files.
- **Children.** Project Brain is a developer tool and is not directed at children.

Questions: open an issue at https://github.com/XPersPective/project-brain/issues.
