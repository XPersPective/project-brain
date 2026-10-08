# Target Architecture
Status: CONFIRMED

## Goal
"Bu projeyi oku, tamam mı? Bu projedeki yapı doğru mu? Mimarı doğru mu? Yani bu skill doğru mu? Bir kontrol etsene. Doğru yazılmış mı? Mimarisi doğru mu? Amacına, hedefine uygun çalışıyor mu? Çalışır mı? Bir eleştir. Kendine bir program, kapsamlı bir analiz yap, tamam mı? Ve sorun varsa düzelt." (user, 2026-10-08)

## Target State
### Protocol
- Preserve the Git-native vendor-neutral design; make scope and recovery instructions executable.
- Record findings, fixes, evidence and limits in a Turkish audit report.
### Runtime
- Checkpoint and dependency decisions do not silently assert unverified state.
- Configuration and migration preserve user data; reproduced defects have runnable stdlib checks.

## Non-Goals
- No new framework, service, dependency, publication or live installation changes.
- No unmeasured claim that all smaller models obey this protocol.

## Open Decisions
- None blocking this explicitly requested audit and corrective work.

## Success Conditions
- `python skills/project-brain/scripts/test_brain.py` passes with regression scenarios.
- `python skills/project-brain/scripts/brain.py validate` has no warnings or failures here.
- Audit report links claims to code/tests and separates guarantees from agent-dependent behavior.
