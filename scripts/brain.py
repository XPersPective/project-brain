#!/usr/bin/env python3
"""project-brain helper. Stdlib only.

  python brain.py boot      <root>                Session classification
  python brain.py validate  <root>                Structural validation
  python brain.py context   <root>                Minimal context file list
  python brain.py checkpoint <root> [--domain D]  Find last checkpoint
  python brain.py changed   <root> [--domain D]   Files changed since checkpoint

boot       Observe repo state, classify session, print NEXT action.
validate   Check Brain file integrity, task graph, cross-references.
context    Print the minimal set of Brain files to load for the active task.
checkpoint Find the latest checkpoint commit for a domain or all.
changed    Show files changed since the last checkpoint.

Exit: 0 OK, 1 WARN (non-fatal issues), 2 FAIL (blocking issues),
      3 NO_BRAIN, 4 BRAIN_INVALID.
"""

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

BRAIN_DIR = ".project-brain"
CONFIG_FILE = "config.yaml"
CURRENT_FILE = "current.md"
TARGET_FILE = "target.md"
CONSTRAINTS_FILE = "constraints.md"
TASKS_DIR = "tasks"
DECISIONS_DIR = "decisions"
CACHE_DIR = ".cache"

TASK_ID_RE = re.compile(r"^PB-(\d+)$")
TASK_FILE_RE = re.compile(r"^PB-(\d+)\.md$")
STATUS_VALUES = {"PLANNED", "READY", "IN_PROGRESS", "BLOCKED"}
RISK_VALUES = {"LOW", "MEDIUM", "HIGH"}
ADR_FILE_RE = re.compile(r"^ADR-(\d+)\.md$")
ADR_STATUS_VALUES = {"Proposed", "Accepted", "Superseded", "Rejected"}

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".turbo", ".cache", ".idea", ".gradle",
    "bin", "obj", ".dart_tool", ".pub-cache",
}


# ── Git helpers ──────────────────────────────────────────────────────────

def git(root, *args, timeout=30):
    """Run a git command and return stdout on success, None on failure."""
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_available(root):
    """Check if root is inside a git working tree."""
    return git(root, "rev-parse", "--is-inside-work-tree") == "true"


def git_head(root):
    """Return short HEAD SHA or None."""
    return git(root, "rev-parse", "--short", "HEAD")


def git_branch(root):
    """Return current branch name or 'HEAD' if detached."""
    ref = git(root, "symbolic-ref", "--short", "HEAD")
    return ref if ref else "HEAD (detached)"


def git_status_porcelain(root):
    """Return list of (status, path) tuples from git status."""
    out = git(root, "status", "--porcelain", "-uall")
    if out is None:
        return None
    result = []
    for line in out.splitlines():
        if len(line) >= 4:
            status = line[:2].strip()
            path = line[3:]
            result.append((status, path))
    return result


def git_is_merging(root):
    """Check for active merge/rebase/cherry-pick/revert."""
    git_dir = Path(root) / ".git"
    if not git_dir.is_dir():
        # Check for worktree or bare repo
        actual = git(root, "rev-parse", "--git-dir")
        if actual:
            git_dir = Path(actual)
    for marker in ["MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"]:
        if (git_dir / marker).exists():
            return marker.replace("_HEAD", "").lower()
    if (git_dir / "rebase-merge").is_dir() or (git_dir / "rebase-apply").is_dir():
        return "rebase"
    return None


def git_find_checkpoint(root, domain=None, limit=20):
    """Find the latest commit with a PB-Current-Checkpoint trailer."""
    if domain:
        pattern = f"PB-Current-Checkpoint: {domain}"
    else:
        pattern = "PB-Current-Checkpoint:"
    # Search in commit body/trailers
    out = git(root, "log", f"-{limit}", "--format=%H %s", f"--grep={pattern}")
    if out:
        lines = out.splitlines()
        if lines:
            parts = lines[0].split(" ", 1)
            return parts[0] if parts else None
    # Fallback: find latest commit touching current architecture files
    brain_path = Path(root) / BRAIN_DIR
    if (brain_path / CURRENT_FILE).exists():
        out = git(root, "log", "-1", "--format=%H", "--",
                  f"{BRAIN_DIR}/{CURRENT_FILE}")
        if out:
            return out.splitlines()[0]
    if (brain_path / "current").is_dir():
        if domain:
            out = git(root, "log", "-1", "--format=%H", "--",
                      f"{BRAIN_DIR}/current/{domain}.md")
        else:
            out = git(root, "log", "-1", "--format=%H", "--",
                      f"{BRAIN_DIR}/current/")
        if out:
            return out.splitlines()[0]
    return None


def git_changed_since(root, since_sha):
    """Return list of changed files since a commit SHA."""
    out = git(root, "diff", "--name-only", f"{since_sha}..HEAD")
    if out:
        return [f for f in out.splitlines() if f.strip()]
    return []


# ── Brain file helpers ───────────────────────────────────────────────────

def brain_path(root):
    """Return Path to .project-brain directory."""
    return Path(root) / BRAIN_DIR


def brain_exists(root):
    """Check if .project-brain directory exists with minimum files."""
    bp = brain_path(root)
    return bp.is_dir() and (
        (bp / CONFIG_FILE).exists() or
        (bp / CURRENT_FILE).exists() or
        (bp / "current").is_dir()
    )


def read_file_safe(path):
    """Read a file safely, return content or None."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def parse_yaml_simple(text):
    """Minimal YAML parser for config.yaml (flat key-value, no nested)."""
    result = {}
    current_section = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Section header (no value after colon, or only whitespace)
        if ":" in stripped and not stripped.split(":", 1)[1].strip():
            current_section = stripped.rstrip(":").strip()
            result[current_section] = {}
            continue
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip()
            # Remove comments
            if " #" in val:
                val = val[:val.index(" #")].strip()
            if current_section and isinstance(result.get(current_section), dict):
                result[current_section][key] = val
            else:
                result[key] = val
    return result


def list_tasks(root):
    """List all task files and parse basic info."""
    tasks_path = brain_path(root) / TASKS_DIR
    if not tasks_path.is_dir():
        return []
    tasks = []
    for f in sorted(tasks_path.iterdir()):
        if not TASK_FILE_RE.match(f.name):
            continue
        content = read_file_safe(f)
        if content is None:
            continue
        task_id = f"PB-{TASK_FILE_RE.match(f.name).group(1)}"
        status = None
        deps = []
        objective = None
        has_acceptance = False
        has_verification = False
        has_resume = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in STATUS_VALUES:
                status = stripped
            elif stripped.startswith("- PB-"):
                dep_match = re.match(r"^- (PB-\d+)", stripped)
                if dep_match:
                    deps.append(dep_match.group(1))
            elif stripped.startswith("## Objective") or stripped.startswith("## Status"):
                pass  # section headers
            elif not objective and stripped and not stripped.startswith("#") and not stripped.startswith("-"):
                if status and not objective:
                    objective = stripped[:80]
            if "## Acceptance Criteria" in stripped:
                has_acceptance = True
            if "## Verification" in stripped:
                has_verification = True
            if "## Resume" in stripped:
                has_resume = True
        tasks.append({
            "id": task_id,
            "file": f.name,
            "status": status,
            "deps": deps,
            "objective": objective,
            "has_acceptance": has_acceptance,
            "has_verification": has_verification,
            "has_resume": has_resume,
        })
    return tasks


def list_adrs(root):
    """List all ADR files."""
    adrs_path = brain_path(root) / DECISIONS_DIR
    if not adrs_path.is_dir():
        return []
    adrs = []
    for f in sorted(adrs_path.iterdir()):
        if ADR_FILE_RE.match(f.name):
            adrs.append(f"ADR-{ADR_FILE_RE.match(f.name).group(1)}")
    return adrs


# ── Commands ─────────────────────────────────────────────────────────────

def cmd_boot(root):
    """Classify session state and print recommended next action."""
    root = Path(root).resolve()
    problems = []
    info = []

    # Check Brain existence
    if not brain_exists(root):
        print("GENESIS")
        print("  .project-brain/ directory does not exist")
        print("NEXT: Create Project Brain (SKILL.md §10 Genesis)")
        return 3

    bp = brain_path(root)

    # Check for minimum valid structure
    has_config = (bp / CONFIG_FILE).exists()
    has_current = (bp / CURRENT_FILE).exists() or (bp / "current").is_dir()
    has_target = (bp / TARGET_FILE).exists() or (bp / "target").is_dir()

    if not has_config and not has_current:
        print("BRAIN_INVALID")
        print("  Missing both config.yaml and current architecture")
        print("NEXT: Read REFERENCE.md §22 (Corrupt Brain)")
        return 4

    # Check Git
    has_git = git_available(root)

    if not has_git:
        info.append("NO_GIT: operating in degraded mode (no checkpoint guarantees)")
        print("CLEAN_RESUME (degraded: no Git)")
        for i in info:
            print(f"  {i}")
        tasks = list_tasks(root)
        in_progress = [t for t in tasks if t["status"] == "IN_PROGRESS"]
        ready = [t for t in tasks if t["status"] == "READY"]
        if in_progress:
            print(f"NEXT: Resume {in_progress[0]['id']} (IN_PROGRESS)")
        elif ready:
            print(f"NEXT: Start {ready[0]['id']} (first READY task)")
        else:
            print("NEXT: Create tasks or run final reconciliation (SKILL.md §31)")
        return 0

    # Git state checks
    head = git_head(root)
    branch = git_branch(root)
    info.append(f"Branch: {branch}")
    info.append(f"HEAD: {head}")

    # Check for conflict operations
    conflict_op = git_is_merging(root)
    if conflict_op:
        print("CONFLICTED")
        print(f"  Active {conflict_op} operation detected")
        for i in info:
            print(f"  {i}")
        print("NEXT: Read REFERENCE.md §9 (Merge/Rebase conflicts)")
        return 1

    # Check working tree
    status = git_status_porcelain(root)
    is_dirty = bool(status)

    # Check for IN_PROGRESS tasks
    tasks = list_tasks(root)
    in_progress = [t for t in tasks if t["status"] == "IN_PROGRESS"]

    # Find last checkpoint
    checkpoint = git_find_checkpoint(root)

    # Classify
    if in_progress and is_dirty:
        classification = "INTERRUPTED"
        detail = f"Task {in_progress[0]['id']} is IN_PROGRESS with dirty working tree"
        next_action = f"Read SKILL.md §19 (Interrupted Work), verify state, resume {in_progress[0]['id']}"
    elif is_dirty:
        classification = "DIRTY_RESUME"
        detail = f"{len(status)} uncommitted changes"
        next_action = "Read SKILL.md §18 (Dirty Resume), classify ownership"
    elif in_progress:
        classification = "INTERRUPTED"
        detail = f"Task {in_progress[0]['id']} is IN_PROGRESS (clean tree)"
        next_action = f"Verify state, resume {in_progress[0]['id']}"
    elif checkpoint:
        # Check if HEAD advanced past checkpoint
        changed = git_changed_since(root, checkpoint)
        if changed:
            brain_changes = [f for f in changed if f.startswith(BRAIN_DIR + "/")]
            other_changes = [f for f in changed if not f.startswith(BRAIN_DIR + "/")]
            if other_changes:
                classification = "HEAD_ADVANCED"
                detail = f"{len(other_changes)} files changed since last checkpoint"
                next_action = "Read SKILL.md §17 (HEAD Advanced), reconcile"
            else:
                classification = "CLEAN_RESUME"
                detail = "HEAD at checkpoint (only Brain files changed)"
                ready = [t for t in tasks if t["status"] == "READY"]
                if ready:
                    next_action = f"Start {ready[0]['id']} (first READY task)"
                else:
                    next_action = "Create tasks or run final reconciliation"
        else:
            classification = "CLEAN_RESUME"
            detail = "HEAD at last checkpoint"
            ready = [t for t in tasks if t["status"] == "READY"]
            if ready:
                next_action = f"Start {ready[0]['id']} (first READY task)"
            else:
                blocked = [t for t in tasks if t["status"] == "BLOCKED"]
                if blocked:
                    next_action = f"All tasks BLOCKED ({len(blocked)}). Review blockers."
                elif tasks:
                    next_action = "All tasks complete. Run final reconciliation (SKILL.md §31)"
                else:
                    next_action = "No tasks. Create tasks or verify completion."
    else:
        # No checkpoint found
        classification = "CLEAN_RESUME"
        detail = "No checkpoint trailer found (legacy or fresh Brain)"
        next_action = "Establish checkpoint at next commit"

    print(classification)
    print(f"  {detail}")
    for i in info:
        print(f"  {i}")

    # Task summary
    by_status = {}
    for t in tasks:
        by_status.setdefault(t["status"] or "UNKNOWN", []).append(t["id"])
    if by_status:
        parts = []
        for s in ["IN_PROGRESS", "READY", "PLANNED", "BLOCKED", "UNKNOWN"]:
            if s in by_status:
                parts.append(f"{s}: {len(by_status[s])}")
        print(f"  Tasks: {', '.join(parts)}")

    print(f"NEXT: {next_action}")
    return 0 if classification == "CLEAN_RESUME" else 1


def cmd_validate(root):
    """Validate Brain file integrity, task graph, cross-references."""
    root = Path(root).resolve()

    if not brain_exists(root):
        print("NO_BRAIN: .project-brain/ does not exist")
        return 3

    bp = brain_path(root)
    problems = []
    warnings = []

    # ── Config validation ────────────────────────────────────────────
    config_path = bp / CONFIG_FILE
    config = {}
    if config_path.exists():
        content = read_file_safe(config_path)
        if content:
            config = parse_yaml_simple(content)
        else:
            problems.append("FAIL config: cannot read config.yaml")
    else:
        warnings.append("WARN config: config.yaml missing (using defaults)")

    # Check architecture mode consistency
    arch_mode = config.get("architecture", {}).get("mode", "single")
    if arch_mode == "domains":
        if not (bp / "current").is_dir():
            problems.append("FAIL config: mode=domains but current/ directory missing")
    elif arch_mode == "single":
        if (bp / "current").is_dir() and not (bp / CURRENT_FILE).exists():
            warnings.append("WARN config: mode=single but current/ directory exists (update config?)")

    # ── Current architecture validation ──────────────────────────────
    if (bp / CURRENT_FILE).exists():
        content = read_file_safe(bp / CURRENT_FILE)
        if not content or len(content.strip()) < 20:
            warnings.append("WARN current: current.md appears empty")
    elif (bp / "current").is_dir():
        domain_files = list((bp / "current").glob("*.md"))
        if not domain_files:
            warnings.append("WARN current: current/ directory is empty")
    else:
        problems.append("FAIL current: no current architecture found")

    # ── Target validation ────────────────────────────────────────────
    if not (bp / TARGET_FILE).exists() and not (bp / "target").is_dir():
        warnings.append("WARN target: no target architecture found")

    # ── Task validation ──────────────────────────────────────────────
    tasks = list_tasks(root)
    task_ids = {t["id"] for t in tasks}
    in_progress_count = 0

    for t in tasks:
        tid = t["id"]

        # Status check
        if t["status"] is None:
            problems.append(f"FAIL task {tid}: missing or invalid status")
        elif t["status"] not in STATUS_VALUES:
            problems.append(f"FAIL task {tid}: unknown status '{t['status']}'")

        if t["status"] == "IN_PROGRESS":
            in_progress_count += 1

        # Required fields
        if not t["has_acceptance"]:
            warnings.append(f"WARN task {tid}: missing Acceptance Criteria section")
        if not t["has_verification"]:
            warnings.append(f"WARN task {tid}: missing Verification section")

        # Dependency validation
        for dep in t["deps"]:
            if dep not in task_ids:
                # Check if dep might be in Git history (completed task)
                dep_in_git = False
                if git_available(root):
                    out = git(root, "log", "--grep", f"PB-Task: {dep}",
                              "--format=%H", "-1")
                    if out:
                        dep_in_git = True
                if not dep_in_git:
                    warnings.append(f"WARN task {tid}: dependency {dep} not found "
                                    f"(may be completed and in Git history)")

        # READY with unresolved deps
        if t["status"] == "READY" and t["deps"]:
            active_deps = [d for d in t["deps"] if d in task_ids]
            for dep_id in active_deps:
                dep_task = next((x for x in tasks if x["id"] == dep_id), None)
                if dep_task and dep_task["status"] not in (None,):
                    if dep_task["status"] != "BLOCKED":
                        # Dep still exists and isn't completed
                        warnings.append(
                            f"WARN task {tid}: READY but dependency {dep_id} "
                            f"is still {dep_task['status']}"
                        )

    # Multiple IN_PROGRESS
    if in_progress_count > 1:
        ip_ids = [t["id"] for t in tasks if t["status"] == "IN_PROGRESS"]
        problems.append(f"FAIL task: {in_progress_count} tasks IN_PROGRESS "
                        f"({', '.join(ip_ids)}). Only one allowed.")

    # Dependency cycle detection
    adj = {t["id"]: t["deps"] for t in tasks}
    visited, path_set = set(), set()

    def has_cycle(node):
        if node in path_set:
            return True
        if node in visited:
            return False
        visited.add(node)
        path_set.add(node)
        for dep in adj.get(node, []):
            if dep in adj and has_cycle(dep):
                return True
        path_set.discard(node)
        return False

    for tid in adj:
        if has_cycle(tid):
            problems.append(f"FAIL task: dependency cycle detected involving {tid}")
            break

    # Duplicate IDs (shouldn't happen with file naming but check)
    seen_ids = set()
    for t in tasks:
        if t["id"] in seen_ids:
            problems.append(f"FAIL task: duplicate ID {t['id']}")
        seen_ids.add(t["id"])

    # ── ADR validation ───────────────────────────────────────────────
    adrs = list_adrs(root)
    # Check for ADRs referenced in tasks
    for t in tasks:
        content = read_file_safe(bp / TASKS_DIR / t["file"])
        if content:
            for adr_ref in re.findall(r"ADR-(\d+)", content):
                adr_id = f"ADR-{adr_ref}"
                if adr_id not in adrs:
                    warnings.append(f"WARN task {t['id']}: references {adr_id} "
                                    f"which does not exist")

    # ── Cache check ──────────────────────────────────────────────────
    cache_path = bp / CACHE_DIR
    if cache_path.is_dir() and git_available(root):
        tracked = git(root, "ls-files", str(cache_path.relative_to(root)))
        if tracked and tracked.strip():
            warnings.append("WARN cache: .cache/ contains tracked files "
                            "(should be in .gitignore)")

    # ── Output ───────────────────────────────────────────────────────
    all_issues = problems + warnings
    if all_issues:
        for issue in all_issues:
            print(issue)
    else:
        print("OK")

    # Summary
    print(f"\nSummary: {len(tasks)} tasks, {len(adrs)} ADRs, "
          f"{len(problems)} errors, {len(warnings)} warnings")

    return 2 if problems else (1 if warnings else 0)


def cmd_context(root):
    """Print the minimal set of Brain files needed for the current session."""
    root = Path(root).resolve()

    if not brain_exists(root):
        print("NO_BRAIN")
        return 3

    bp = brain_path(root)
    files = []

    # Always load config
    if (bp / CONFIG_FILE).exists():
        files.append(f"{BRAIN_DIR}/{CONFIG_FILE}")

    # Find active task
    tasks = list_tasks(root)
    in_progress = [t for t in tasks if t["status"] == "IN_PROGRESS"]
    active = in_progress[0] if in_progress else None

    if active:
        files.append(f"{BRAIN_DIR}/{TASKS_DIR}/{active['file']}")

        # Load relevant current architecture
        task_content = read_file_safe(bp / TASKS_DIR / active["file"])
        if task_content:
            # Extract affected domains from Architecture Impact section
            domains = re.findall(r"^\s*-\s+(\w+)\s*$",
                                 task_content.split("## Architecture Impact")[-1]
                                 if "## Architecture Impact" in task_content else "",
                                 re.MULTILINE)
            if domains and (bp / "current").is_dir():
                for d in domains:
                    df = bp / "current" / f"{d}.md"
                    if df.exists():
                        files.append(f"{BRAIN_DIR}/current/{d}.md")
                    target_df = bp / "target" / f"{d}.md"
                    if target_df.exists():
                        files.append(f"{BRAIN_DIR}/target/{d}.md")
            else:
                if (bp / CURRENT_FILE).exists():
                    files.append(f"{BRAIN_DIR}/{CURRENT_FILE}")
                if (bp / TARGET_FILE).exists():
                    files.append(f"{BRAIN_DIR}/{TARGET_FILE}")
    else:
        # No active task: load current and target for task selection
        if (bp / CURRENT_FILE).exists():
            files.append(f"{BRAIN_DIR}/{CURRENT_FILE}")
        if (bp / TARGET_FILE).exists():
            files.append(f"{BRAIN_DIR}/{TARGET_FILE}")

    # Always include constraints
    if (bp / CONSTRAINTS_FILE).exists():
        files.append(f"{BRAIN_DIR}/{CONSTRAINTS_FILE}")

    # Print
    print("CONTEXT FILES:")
    for f in files:
        print(f"  {f}")

    if active:
        print(f"\nACTIVE: {active['id']} ({active['status']})")
        if active.get("objective"):
            print(f"  {active['objective']}")
    else:
        ready = [t for t in tasks if t["status"] == "READY"]
        if ready:
            print(f"\nNEXT READY: {ready[0]['id']}")
        elif tasks:
            print(f"\nNO READY TASKS ({len(tasks)} total)")
        else:
            print("\nNO TASKS")

    return 0


def cmd_checkpoint(root, domain=None):
    """Find and display the latest checkpoint."""
    root = Path(root).resolve()

    if not git_available(root):
        print("NO_GIT: cannot find checkpoints without Git")
        return 1

    if domain:
        sha = git_find_checkpoint(root, domain)
        if sha:
            short = git(root, "rev-parse", "--short", sha) or sha[:8]
            subject = git(root, "log", "-1", "--format=%s", sha) or ""
            print(f"CHECKPOINT ({domain}): {short} {subject}")
        else:
            print(f"NO_CHECKPOINT: no checkpoint found for domain '{domain}'")
            return 1
    else:
        sha = git_find_checkpoint(root)
        if sha:
            short = git(root, "rev-parse", "--short", sha) or sha[:8]
            subject = git(root, "log", "-1", "--format=%s", sha) or ""
            print(f"CHECKPOINT: {short} {subject}")
        else:
            print("NO_CHECKPOINT: no checkpoint found in recent history")
            # Try fallback
            bp = brain_path(root)
            if (bp / CURRENT_FILE).exists():
                out = git(root, "log", "-1", "--format=%h %s", "--",
                          f"{BRAIN_DIR}/{CURRENT_FILE}")
                if out:
                    print(f"FALLBACK (last current.md edit): {out}")
            return 1

    return 0


def cmd_changed(root, domain=None):
    """Show files changed since the last checkpoint."""
    root = Path(root).resolve()

    if not git_available(root):
        print("NO_GIT: cannot determine changes without Git")
        return 1

    sha = git_find_checkpoint(root, domain)
    if not sha:
        print("NO_CHECKPOINT: cannot determine changed files")
        return 1

    changed = git_changed_since(root, sha)
    if not changed:
        print("NO_CHANGES since last checkpoint")
        return 0

    brain_changes = [f for f in changed if f.startswith(BRAIN_DIR + "/")]
    source_changes = [f for f in changed if not f.startswith(BRAIN_DIR + "/")]

    if source_changes:
        print(f"SOURCE CHANGES ({len(source_changes)}):")
        for f in source_changes[:30]:
            print(f"  {f}")
        if len(source_changes) > 30:
            print(f"  ... and {len(source_changes) - 30} more")

    if brain_changes:
        print(f"BRAIN CHANGES ({len(brain_changes)}):")
        for f in brain_changes:
            print(f"  {f}")

    # Suggest affected domains
    if domain:
        print(f"\nDOMAIN: {domain} may need reconciliation")
    else:
        # Try to infer affected domains from source mapping
        print(f"\nTOTAL: {len(changed)} files changed since checkpoint")
        print("NEXT: Reconcile affected architecture domains (SKILL.md §14)")

    return 0


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(
        description="Project Brain helper — Git-native project cognition",
        epilog="See SKILL.md for the full protocol."
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    # boot
    p = sub.add_parser("boot", help="Classify session state")
    p.add_argument("root", help="Repository root directory")

    # validate
    p = sub.add_parser("validate", help="Validate Brain integrity")
    p.add_argument("root", help="Repository root directory")

    # context
    p = sub.add_parser("context", help="Show minimal context files")
    p.add_argument("root", help="Repository root directory")

    # checkpoint
    p = sub.add_parser("checkpoint", help="Find latest checkpoint")
    p.add_argument("root", help="Repository root directory")
    p.add_argument("--domain", "-d", help="Specific domain to check")

    # changed
    p = sub.add_parser("changed", help="Show files changed since checkpoint")
    p.add_argument("root", help="Repository root directory")
    p.add_argument("--domain", "-d", help="Specific domain to check")

    args = ap.parse_args()
    root = Path(args.root).resolve()

    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1

    if args.cmd == "boot":
        return cmd_boot(root)
    elif args.cmd == "validate":
        return cmd_validate(root)
    elif args.cmd == "context":
        return cmd_context(root)
    elif args.cmd == "checkpoint":
        return cmd_checkpoint(root, getattr(args, "domain", None))
    elif args.cmd == "changed":
        return cmd_changed(root, getattr(args, "domain", None))
    else:
        print(f"Unknown command: {args.cmd}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
