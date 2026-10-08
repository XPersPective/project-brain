# Target Architecture
Status: CONFIRMED

## Goal
"Bütün kontrolleri ve iyileştirmeleri yap, inisiyatif al, mükemmel hale getir. Amacına, hedefine uygun mükemmel hale getir. Kontrollerini yap, ondan sonra GitHub'a push et ve daha sonra da Cloud'a ve Codex, işte Cloud Codex mi, yani nereye yayınlanması gerekiyorsa bu skill'i yayınlansın kamuya açık bir şekilde. Ayrıca bu bilgisayarda bütün ajanlar için yükle. Skill Manager vardı galiba. Bütün ajanlar kullanabilsin bunu. Güncel versiyona yükselt. Bütün ajanların kullanabileceği hale getir." (user, 2026-10-08)

## Target State
### Protocol
- Preserve the Git-native vendor-neutral design; make scope and recovery instructions executable.
- Record findings, fixes, evidence and limits in a Turkish audit report.
### Runtime
- Checkpoint and dependency decisions do not silently assert unverified state.
- Configuration and migration preserve user data; reproduced defects have runnable stdlib checks.

### Distribution
- Publish the verified release to the existing public GitHub repository and supported plugin marketplaces.
- Update the Skill Manager library and all managed agent targets; verify their file contents.
- Submit official directory listings where authenticated account access permits; distinguish submission from approval.

## Non-Goals
- No new application framework/service or unrelated agent configuration changes.
- No unmeasured claim that all smaller models obey this protocol.

## Open Decisions
- None blocking this explicitly requested audit and corrective work.

## Success Conditions
- `python skills/project-brain/scripts/test_brain.py` passes with regression scenarios.
- `python skills/project-brain/scripts/brain.py validate` has no warnings or failures here.
- Audit report links claims to code/tests and separates guarantees from agent-dependent behavior.
- Remote release/tag matches verified local source; installable archives are available.
- Managed agent targets resolve to the released skill version; provider review/access limits are explicit.
