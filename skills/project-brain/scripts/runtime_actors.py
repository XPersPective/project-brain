"""Slim actor identity registry, worker prompt builder, and backend gate dispatcher.

External CLI agents are managed exclusively by CLI Agent Pool (CAP); Solo and
Native host workers stay independent of CAP. This module holds only observed
actor records (native/<hash>, pool/<hash>) for reviewer independence and
provenance checks, with OS-locked atomic updates. Python 3.8+, stdlib only.
"""

import json
import os
from pathlib import Path
import re

import runtime_core as Core
import runtime_security as S

DEFAULT_REGISTRY = Path.home() / Core.BRAIN_DIR / "agents.json"
ROLES = ("lead", "worker", "reviewer", "discovery")
EFFORTS = ("low", "medium", "high", "xhigh", "default")

# Backend gate handlers registered by higher-layer modules (strictly acyclic).
_GATES = {}


def register_gate(kind, handler):
    """Register a backend gate handler ('native' or 'pool') without circular imports."""
    _GATES[kind] = handler


def norm_key(value):
    return Core.norm_key(value)


def registry_path(path=None):
    if path:
        return Path(path)
    env = os.environ.get("PB_AGENTS_REGISTRY")
    return Path(env) if env else DEFAULT_REGISTRY


def _default_registry():
    return {
        "schema_version": 1,
        "updated_at": Core.now_iso(),
        "models": {},
    }


def _validate_registry(data):
    if not isinstance(data, dict):
        raise ValueError("actor registry root must be an object")
    version = data.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise ValueError("unsupported actor registry schema_version")
    models = data.get("models")
    if models is not None:
        if not isinstance(models, dict):
            raise ValueError("actor registry models must be an object")
        for row in models.values():
            if not isinstance(row, dict):
                raise ValueError("actor registry entries must be objects")
            for field in ("cli", "model_id", "pool_route"):
                if row.get(field) is not None and not isinstance(row[field], str):
                    raise ValueError(f"actor registry {field} must be text")
            for field in ("roles", "tiers", "efforts"):
                value = row.get(field)
                if value is not None and (not isinstance(value, list) or any(not isinstance(x, str) for x in value)):
                    raise ValueError(f"actor registry {field} must be a text array")


def load(path=None):
    p = registry_path(path)
    if not p.exists():
        return _default_registry()
    try:
        data = Core.read_json(p, max_bytes=4 * 1024 * 1024, strict_constants=True)
    except ValueError as exc:
        raise ValueError(f"{p}: invalid JSON: {exc}") from exc
    _validate_registry(data)
    data.setdefault("schema_version", 1)
    data.setdefault("models", {})
    return data


def _lock_path(path=None):
    reg = registry_path(path).absolute()
    return Core.safe_private_path(reg.parent / ".registry.lock", stop_at=reg.parent)


def save(data, path=None):
    _validate_registry(data)
    p = registry_path(path)
    data["updated_at"] = Core.now_iso()
    Core.write_atomic(p, json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
    return p


def register_model(alias, record, path=None):
    """Merge one observed model under a registry-wide OS lock across projects."""
    p = registry_path(path)
    with Core.file_lock(_lock_path(p)):
        data = load(p)
        data["models"][alias] = record
        save(data, p)
    return alias


def register_models(records, path=None):
    """Batch-merge observed models under one registry lock."""
    if not records:
        return
    p = registry_path(path)
    with Core.file_lock(_lock_path(p)):
        data = load(p)
        data["models"].update(records)
        save(data, p)


def canonical_identity(alias, path=None):
    """Resolve actor aliases to canonical model identity for self-review checks."""
    p = registry_path(path)
    models = load(p).get("models", {}) if p.exists() else {}
    spec = models.get(alias)
    value = spec.get("model_id", alias) if isinstance(spec, dict) else alias
    return norm_key(str(value).replace(":", "/").rsplit("/", 1)[-1])


def implementers(B, task):
    found = []
    if task.get("owner"):
        found.append(task["owner"])
    for rec in B.start_records(task):
        if rec["owner"] not in found:
            found.append(rec["owner"])
    return found


def gate(B, task, alias, action, path=None, root=None):
    """Validate that `alias` is permitted for `action` (start/review/accept) on `task`."""
    p = registry_path(path)
    if (
        action == "review"
        and task
        and not p.exists()
        and any(re.fullmatch(r"pool/[0-9a-f]{24}", i) for i in implementers(B, task))
    ):
        raise ValueError("Pool implementation review requires its registry; a missing registry cannot bypass strength checks")
    if not alias or not p.exists():
        return None
    data = load(p)
    models = data.get("models", {})
    spec = models.get(alias)
    if isinstance(spec, dict) and spec.get("native_orchestration"):
        if root is None:
            raise ValueError("Native orchestration actors require project-bound receipts")
        handler = _GATES.get("native")
        if handler is None:
            raise ValueError("Native orchestration gate handler not initialized")
        return handler(B, root, task, alias, action)
    if action == "review" and task:
        impls = implementers(B, task)
        backend_flags = [
            bool(models.get(i, {}).get("pool_route")) or bool(re.fullmatch(r"pool/[0-9a-f]{24}", i))
            for i in impls
        ]
        reviewer_pool = isinstance(spec, dict) and bool(spec.get("pool_route"))
        if backend_flags and (any(backend_flags) and not reviewer_pool or reviewer_pool and not all(backend_flags)):
            raise ValueError("mixed-backend review has no comparable strength; use a reviewer from the implementation backend")
    if isinstance(spec, dict) and spec.get("pool_route"):
        handler = _GATES.get("pool")
        if handler is None:
            raise ValueError("CAP gate handler not initialized")
        return handler(B, task, spec, alias, action, root)
    if action == "review" and task:
        if isinstance(spec, dict) and spec.get("roles") and "reviewer" not in spec["roles"]:
            raise ValueError(f"{alias}: excluded by reviewer policy (roles={spec['roles']})")
        impls = implementers(B, task)
        if canonical_identity(alias, p) in {canonical_identity(i, p) for i in impls}:
            raise ValueError(f"{alias}: implemented {task['id']}; reviewer must be a different agent/model")
    return None


def build_worker_prompt(B, root, task, score_info):
    """Build a compact, zero-history execution prompt for a delegated CAP worker."""
    rel_task = Path(os.path.relpath(task["file"], root)).as_posix()
    surf = score_info["surface"]
    cur_file = B.bp(root) / "current.md"
    _, rng = (
        B.current_slices(cur_file, task.get("domains", []))
        if cur_file.exists() and hasattr(B, "current_slices")
        else (None, None)
    )
    slice_hint = f" (lines {rng})" if rng else " (only matching domain sections)"
    proven = B.proven_criteria_ids(root, task) if hasattr(B, "proven_criteria_ids") else []
    rules = [
        f"You are executing Project Brain task `{task['id']}: {task['title']}` in `{Path(root).as_posix()}`.",
        f"Read repository agent instructions, `.project-brain/constraints.md`, matching domain slices in `.project-brain/current.md`{slice_hint}, and task-linked ADRs before editing.",
        f"1. Read `{rel_task}` first. Follow its `Objective`, `Steps`, `Acceptance`, and `Verify` sections strictly.",
        f"2. Restrict all file edits to `Areas`: {', '.join(f'`{a}`' for a in task['areas']) or '(see task file)'}.",
        "3. Do NOT modify unrelated tasks, do NOT rewrite git history, and do NOT hand-edit `## Evidence` or `## Review`.",
        "Use the user's existing human Git identity. Never add AI/model/provider/bot author, Co-authored-by, generated-by or contributor/PR credit; leave commits pending if human identity is missing.",
    ]
    if proven:
        rules.append(
            f"   - Reusable typed evidence on current digest: {', '.join(sorted(proven))}. "
            "Do not repeat already-proven checks unless source, dependencies or environment change."
        )
    if surf["ui"]:
        rules.append(
            "4. UI QUALITY RUBRIC: Reuse the existing design foundation and verify applicable loading, empty, error/retry, "
            "and populated states, keyboard/focus accessibility, platform-appropriate touch targets, and responsive layout."
        )
    if surf["backend"]:
        rules.append(
            "5. BACKEND & STATE RUBRIC: Preserve the project's architecture boundaries and explicit state transitions, "
            "validate external inputs at the boundary, and enforce idempotency/error contracts."
        )
    rules.append(
        "6. Run the task's `Verify` commands directly and return exact command/exit observations (do NOT load external planning skills or invoke `brain.py`; the director records receipts). Never invent a PASS."
    )
    rules.append("7. Keep context to the named files; no full-repository dumps or nested delegation. Stop after one failed repair with the exact failure and remaining work. Return changed files, check results and unresolved risks in at most 12 lines; intention-only output is not completion.")
    prompt = "\n".join(rules)
    S.require_clean(prompt, "worker prompt")
    return prompt
