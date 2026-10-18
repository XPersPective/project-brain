"""Agent complexity scoring, system CLI agent discovery, live subscription quota tracking,
cost-aware model routing, CLI worker delegation, and foreign planning adoption. Stdlib only."""

from datetime import datetime, timezone
import json
import hashlib
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import runtime_verify as V

DEFAULT_REGISTRY = Path.home() / ".project-brain" / "agents.json"
STORE_AUTOMATION_MODELS = Path.home() / ".store-automation" / "models.json"
ROLES = ("lead", "worker", "reviewer", "discovery")
EFFORTS = ("low", "medium", "high", "xhigh", "default")

# Minimum quality score required by (tier, risk)
QUALITY_FLOOR = {
    ("L", "LOW"): 35, ("L", "MEDIUM"): 38, ("L", "HIGH"): 45,
    ("M", "LOW"): 46, ("M", "MEDIUM"): 48, ("M", "HIGH"): 54,
    ("H", "LOW"): 56, ("H", "MEDIUM"): 58, ("H", "HIGH"): 60,
}

WORKER_RESERVE_PCT = 10.0    # Never dispatch workers when pool remaining_pct <= 10%
DIRECTOR_RESERVE_PCT = 25.0  # Reserve last 25% of primary pool for Tier H / reviewer / lead if secondary pools exist

UI_DOMAIN_RE = re.compile(
    r"\b(ui|ux|frontend|web|mobile|screen|view|widget|component|page|theme|design|style|css|layout|flutter|react|vue|svelte)\b",
    re.I,
)
UI_AREA_RE = re.compile(
    r"(\.(tsx|jsx|vue|svelte|css|scss|html)(?:\*|\s|$)|(?:^|[ /])(ui|views|screens|pages|components|widgets|theme|styles|presentation)/)",
    re.I,
)
BACKEND_DOMAIN_RE = re.compile(
    r"\b(backend|api|server|db|database|storage|auth|service|worker|queue|domain|data|repository|migration|protocol|runtime|cli)\b",
    re.I,
)
BACKEND_AREA_RE = re.compile(
    r"((?:^|[ /])(api|server|backend|db|migrations|services|repositories|controllers|handlers|domain|data|runtime|scripts)/|\.(sql|prisma|proto|graphql)(?:\*|\s|$))",
    re.I,
)
ARCH_KEYWORD_RE = re.compile(
    r"\b(auth|authentication|authorization|migration|schema|payment|billing|crypto|encryption|security|"
    r"state[- ]machine|concurrency|lock|transaction|oauth|jwt|permission|digest|contract|protocol)\b",
    re.I,
)
UI_FOUNDATION_RE = re.compile(
    r"\b(design[- ]system|token|tokens|theme|typography|color[- ]scheme|navigation|shell|layout[- ]system|breakpoint)\b",
    re.I,
)

# Built-in baseline benchmarks so routing works out of the box even before external benchmark import
BUILTIN_BENCHMARKS = {
    "claude-opus-4-6": {"quality": 65.0, "coding": 64.0},
    "claude-sonnet-4-6": {"quality": 58.0, "coding": 57.0},
    "claude-haiku-4-5": {"quality": 44.0, "coding": 43.0},
    "gpt-5.4": {"quality": 62.0, "coding": 61.0},
    "gpt-5.3-codex": {"quality": 59.0, "coding": 60.0},
    "gpt-5.2-codex": {"quality": 56.0, "coding": 57.0},
    "gpt-5.2": {"quality": 55.0, "coding": 54.0},
    "gpt-5.1-codex-max": {"quality": 55.0, "coding": 56.0},
    "gpt-5.1-codex-mini": {"quality": 43.0, "coding": 45.0},
    "gpt-5-nano": {"quality": 38.0, "coding": 39.0},
    "gemini-3.1-pro": {"quality": 61.0, "coding": 60.0},
    "gemini-2.5-pro": {"quality": 56.0, "coding": 55.0},
    "gemini-2.5-flash": {"quality": 45.0, "coding": 44.0},
    "qwen3-coder-plus": {"quality": 50.0, "coding": 52.0},
    "minimax-m2.5-free": {"quality": 46.0, "coding": 47.0},
    "big-pickle": {"quality": 42.0, "coding": 43.0},
}

CLI_SPECS = (
    ("codex", ("codex",), "OpenAI Codex CLI"),
    ("opencode", ("opencode",), "OpenCode multi-provider CLI"),
    ("claude", ("claude",), "Anthropic Claude Code CLI"),
    ("gemini", ("gemini",), "Google Gemini CLI"),
    ("agy", ("agy", "antigravity"), "Google Antigravity CLI"),
    ("qwen", ("qwen",), "Qwen Code CLI"),
    ("aider", ("aider",), "Aider AI pair programmer CLI"),
    ("kilocode", ("kilocode", "kilo"), "Kilo Code CLI"),
    ("mcode", ("mcode",), "MCode CLI"),
    ("kimi", ("kimi",), "Moonshot Kimi CLI"),
    ("omniroute", ("omniroute",), "OmniRoute router CLI"),
    ("hermes", ("hermes",), "Hermes CLI"),
    ("lmstudio", ("lmstudio", "lms"), "LM Studio CLI"),
    ("ollama", ("ollama",), "Ollama CLI"),
)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_key(value):
    s = re.sub(r"[^a-z0-9.+-]+", "-", str(value or "").strip().lower()).strip("-")
    for prefix in ("openai-", "anthropic-", "google-", "opencode-", "alibaba-", "moonshot-"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def registry_path(path=None):
    if path:
        return Path(path)
    env = os.environ.get("PB_AGENTS_REGISTRY")
    return Path(env) if env else DEFAULT_REGISTRY


def canonical_identity(alias, path=None):
    """Resolve aliases to model identity so alternate CLI routes cannot self-review."""
    models = load(path).get("models", {})
    spec = models.get(alias)
    value = spec.get("model_id", alias) if isinstance(spec, dict) else alias
    return norm_key(str(value).replace(":", "/").rsplit("/", 1)[-1])


# ── Task Complexity Scoring & Quality Classification ──────────────────────

def task_surface(task):
    """Classify whether a task touches UI/Frontend, Backend/Data/Runtime, or Architecture."""
    domains_str = " ".join(task.get("domains", []))
    areas_str = " ".join(task.get("areas", []))
    body_str = f"{task.get('title', '')}\n{task.get('objective', '')}\n" + "\n".join(task.get("steps", []))
    ui = bool(UI_DOMAIN_RE.search(domains_str) or UI_AREA_RE.search(areas_str) or
              re.search(r"\[(visual|interaction|accessibility)\]", task.get("text", ""), re.I))
    backend = bool(BACKEND_DOMAIN_RE.search(domains_str) or BACKEND_AREA_RE.search(areas_str) or
                   re.search(r"\[(security|integration|architecture)\]", task.get("text", ""), re.I))
    arch = bool(ARCH_KEYWORD_RE.search(body_str) or ARCH_KEYWORD_RE.search(domains_str))
    ui_foundation = bool(UI_FOUNDATION_RE.search(body_str))
    return {"ui": ui, "backend": backend, "arch": arch, "ui_foundation": ui_foundation}


def score_task(B, root, task):
    """Deterministic 0-100 complexity scorer + tier/effort/risk/delegation recommender."""
    surf = task_surface(task)
    areas = task.get("areas", [])
    domains = task.get("domains", [])
    steps = task.get("steps", [])
    acc = task.get("acceptance", [])
    deps = task.get("deps", [])
    risk_decl = task.get("risk", "MEDIUM") if task.get("risk") in B.RISK_VALUES else "MEDIUM"

    # Risk floor escalation based on surface
    risk_floor = "LOW"
    if surf["ui"] or surf["backend"] or len(areas) > 2 or len(domains) > 1:
        risk_floor = "MEDIUM"
    if surf["arch"] or len(domains) >= 3 or len(areas) >= 6:
        risk_floor = "HIGH"
    eff_risk = B.RISK_VALUES[max(B.RISK_VALUES.index(risk_decl), B.RISK_VALUES.index(risk_floor))]

    # Score components (0..100)
    pts_areas = min(20, len(areas) * 4)
    pts_domains = min(15, max(0, len(domains) - 1) * 6 + (4 if domains else 0))
    pts_steps = min(16, len(steps) * 3)
    pts_acc = min(14, len(acc) * 2)
    pts_deps = min(10, len(deps) * 4)
    pts_risk = {"LOW": 0, "MEDIUM": 10, "HIGH": 22}[eff_risk]
    pts_arch = 14 if surf["arch"] else 0
    pts_uif = 10 if surf["ui_foundation"] else 0

    raw_score = min(100, pts_areas + pts_domains + pts_steps + pts_acc + pts_deps + pts_risk + pts_arch + pts_uif)

    # Computed Tier
    if raw_score >= 65 or (eff_risk == "HIGH" and (surf["arch"] or surf["ui_foundation"] or len(domains) >= 3)):
        computed_tier = "H"
    elif raw_score <= 32 and eff_risk == "LOW" and not surf["arch"] and not surf["ui_foundation"]:
        computed_tier = "L"
    elif raw_score <= 28 and eff_risk != "HIGH" and not surf["arch"]:
        computed_tier = "L"
    else:
        computed_tier = "M"

    decl_tier = task.get("tier") if task.get("tier") in B.TIER_VALUES else computed_tier
    eff_tier = B.TIER_VALUES[max(B.TIER_VALUES.index(decl_tier), B.TIER_VALUES.index(computed_tier))]

    if eff_tier == "L":
        effort = "low"
    elif eff_tier == "M":
        effort = "high" if eff_risk == "HIGH" else "medium"
    else:
        effort = "high"

    # Check UI Triad and Backend Quality completeness
    raw_kinds = {item.get("raw_kind") for item in acc if item.get("raw_kind")}
    missing_ui_triad = []
    if surf["ui"]:
        for req_k in ("visual", "interaction", "accessibility"):
            if req_k not in raw_kinds:
                missing_ui_triad.append(req_k)

    executable = bool(task.get("has_steps") and task.get("checkboxes") and task.get("verify_cmd") and not task.get("vague"))
    must_split = raw_score > 78 or task.get("lines", 0) > B.BUDGETS["task"] or len(steps) > 10
    delegatable = bool(
        eff_tier in ("L", "M")
        and executable
        and not must_split
        and task.get("status") in ("READY", "IN_PROGRESS")
    )

    reasons = []
    if pts_areas:
        reasons.append(f"areas={len(areas)} (+{pts_areas})")
    if pts_domains:
        reasons.append(f"domains={len(domains)} (+{pts_domains})")
    if pts_steps:
        reasons.append(f"steps={len(steps)} (+{pts_steps})")
    if pts_acc:
        reasons.append(f"acceptance={len(acc)} (+{pts_acc})")
    if pts_risk:
        reasons.append(f"risk={eff_risk} (+{pts_risk})")
    if pts_arch:
        reasons.append(f"arch-keywords (+{pts_arch})")
    if pts_uif:
        reasons.append(f"ui-foundation (+{pts_uif})")

    return {
        "id": task["id"],
        "title": task["title"],
        "status": task["status"],
        "score": raw_score,
        "declared_tier": task.get("tier") or "?",
        "computed_tier": computed_tier,
        "effective_tier": eff_tier,
        "declared_risk": task.get("risk") or "?",
        "risk_floor": risk_floor,
        "effective_risk": eff_risk,
        "recommended_effort": effort,
        "recommended_role": "lead" if eff_tier == "H" else "worker",
        "surface": surf,
        "missing_ui_triad": missing_ui_triad,
        "executable": executable,
        "must_split": must_split,
        "delegatable": delegatable,
        "reasons": reasons,
    }


def apply_score_headers(B, task, info):
    """Update Tier and Risk headers in-place in the task file to match effective_tier and effective_risk."""
    text = B.read(task["file"]) or ""
    lines = text.splitlines()
    changed = False
    for i, line in enumerate(lines):
        if line.startswith("## "):
            break
        if re.match(r"^\**tier\**:", line, re.I):
            new_line = f"Tier: {info['effective_tier']}"
            if line != new_line:
                lines[i] = new_line
                changed = True
        elif re.match(r"^\**risk\**:", line, re.I):
            new_line = f"Risk: {info['effective_risk']}"
            if line != new_line:
                lines[i] = new_line
                changed = True
    if changed:
        B.write_atomic(task["file"], "\n".join(lines) + "\n")
    return changed


def cmd_score(B, root, tid=None, write=False, as_json=False):
    if not B.brain_exists(root):
        print("NO_BRAIN")
        return 3
    tasks = [B.find_task(root, tid)] if tid else [
        t for t in B.list_tasks(root) if t["status"] != "DONE" or not t["has_evidence"]
    ]
    if tid and not tasks[0]:
        print(f"FAIL {tid}: task not found")
        return 2
    results = []
    for t in tasks:
        info = score_task(B, root, t)
        if write:
            info["updated"] = apply_score_headers(B, t, info)
        results.append(info)
    if as_json:
        print(json.dumps(results[0] if tid else results, indent=2, ensure_ascii=False))
        return 0
    for r in results:
        surf_tags = [k for k, v in r["surface"].items() if v] or ["general"]
        del_str = "DELEGATABLE (worker CLI)" if r["delegatable"] else ("SPLIT_FIRST" if r["must_split"] else "LEAD_ONLY")
        print(
            f"SCORE {r['id']}: {r['score']}/100 | tier {r['declared_tier']}->{r['effective_tier']} | "
            f"risk {r['declared_risk']}->{r['effective_risk']} | effort {r['recommended_effort']} | "
            f"role {r['recommended_role']} | {del_str}"
        )
        print(f"  surface: {', '.join(surf_tags)} | breakdown: {', '.join(r['reasons']) or 'minimal'}")
        if r["missing_ui_triad"]:
            print(f"  ! UI task missing Acceptance tags: {', '.join('[' + k + ']' for k in r['missing_ui_triad'])}")
        if r.get("updated"):
            print(f"  updated {r['id']} headers -> Tier: {r['effective_tier']}, Risk: {r['effective_risk']}")
    return 0


# ── System CLI Discovery & Live Quota Probing ─────────────────────────────

def _extra_search_dirs():
    dirs = []
    home = Path.home()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        localapp = os.environ.get("LOCALAPPDATA")
        if appdata:
            dirs.append(Path(appdata) / "npm")
        if localapp:
            dirs.extend([
                Path(localapp) / "agy" / "bin",
                Path(localapp) / "qwen-code" / "bin",
                Path(localapp) / "Programs" / "claude",
                Path(localapp) / "Programs" / "opencode",
            ])
    dirs.extend([home / ".local" / "bin", home / ".npm-global" / "bin", home / "bin"])
    return [str(d) for d in dirs if d.is_dir()]


def which_cli(names):
    """Find executable path on PATH or common user install locations. Prefer .exe/.cmd over .ps1 on Windows."""
    path_env = os.environ.get("PATH", "")
    extra = os.pathsep.join(_extra_search_dirs())
    full_path = f"{path_env}{os.pathsep}{extra}" if extra else path_env
    for name in names:
        if os.name == "nt":
            for ext in (".exe", ".cmd", ".bat", ""):
                found = shutil.which(name + ext, path=full_path)
                if found and not found.lower().endswith(".ps1"):
                    return str(Path(found).resolve())
        found = shutil.which(name, path=full_path)
        if found:
            return str(Path(found).resolve())
    return None


def _run_probe(argv, timeout=8, stdin_text=None):
    """Run a quick local CLI probe without shell expansion where possible."""
    try:
        cmd = list(argv)
        if os.name == "nt" and cmd[0].lower().endswith((".cmd", ".bat")):
            cmd = ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(cmd)]
        r = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL if stdin_text is None else None,
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)


def probe_codex_quota(exe_path, timeout=8):
    """Query `codex app-server --stdio` JSON-RPC `account/rateLimits/read` for live 5h & weekly quota."""
    cmd = [exe_path, "app-server", "--stdio"]
    if os.name == "nt" and exe_path.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(cmd)]
    init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "project-brain", "title": "Project Brain", "version": "3.0.0"}}}) + "\n"
    read_limits = json.dumps({"jsonrpc": "2.0", "method": "initialized"}) + "\n" + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": {}}) + "\n"
    output = ""
    try:
        with V.ProcessTree() as tree:
            proc = tree.spawn(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            received = queue.Queue()

            def read_lines():
                try:
                    for line in proc.stdout:
                        received.put(line)
                finally:
                    received.put(None)

            reader = threading.Thread(target=read_lines, daemon=True)
            reader.start()
            try:
                proc.stdin.write(init)
                proc.stdin.flush()
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        line = received.get(timeout=max(0.001, deadline - time.monotonic()))
                    except queue.Empty:
                        break
                    if line is None:
                        break
                    output += line
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if message.get("id") == 1 and "result" in message:
                        proc.stdin.write(read_limits)
                        proc.stdin.flush()
                    if message.get("id") == 2:
                        break
            finally:
                tree.close()
                reader.join(timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("id") == 2 and "result" in msg:
            rl = msg["result"].get("rateLimits") or {}
            primary = rl.get("primary") or {}
            secondary = rl.get("secondary") or {}
            p_used = primary.get("usedPercent")
            s_used = secondary.get("usedPercent")
            if any(x is not None and (type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 100)
                   for x in (p_used, s_used)):
                return None
            used_vals = [float(x) for x in (p_used, s_used) if isinstance(x, (int, float))]
            if not used_vals:
                return None
            bottleneck_used = max(used_vals)
            rem_pct = round(max(0.0, 100.0 - bottleneck_used), 1)
            resets_ts = secondary.get("resetsAt") or primary.get("resetsAt")
            resets_iso = (
                datetime.fromtimestamp(int(resets_ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                if isinstance(resets_ts, (int, float))
                else ""
            )
            return {
                "plan_type": rl.get("planType") or "subscription",
                "primary_5h_remaining_pct": round(max(0.0, 100.0 - float(p_used)), 1) if isinstance(p_used, (int, float)) else None,
                "weekly_7d_remaining_pct": round(max(0.0, 100.0 - float(s_used)), 1) if isinstance(s_used, (int, float)) else None,
                "remaining_pct": rem_pct,
                "resets_at": resets_iso,
                "updated_at": now_iso(),
            }
    return None


def probe_opencode_models(exe_path, timeout=8):
    rc, out, _ = _run_probe([exe_path, "--pure", "models"], timeout=timeout)
    if rc != 0 or not out:
        return []
    models = []
    for line in out.splitlines():
        s = line.strip()
        if "/" in s and not s.startswith(("{", "[", "#")) and " " not in s:
            models.append(s)
    return models


def probe_claude_status(exe_path, timeout=6):
    rc, out, _ = _run_probe([exe_path, "auth", "status"], timeout=timeout)
    text = out or ""
    if text.startswith("{"):
        try:
            data = json.loads(text)
            return {
                "authenticated": bool(data.get("loggedIn")),
                "auth_method": data.get("authMethod", ""),
                "subscription_type": data.get("subscriptionType", ""),
            }
        except ValueError:
            pass
    return {"authenticated": rc == 0 and "true" in text.lower()}


def _read_safe(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def probe_codex_info(exe_path):
    home = Path.home() / ".codex"
    cfg_text = _read_safe(home / "config.toml")
    default_model = ""
    default_effort = "medium"
    if cfg_text:
        m = re.search(r'^\s*model\s*=\s*"([^"]+)"', cfg_text, re.M)
        if m:
            default_model = m.group(1)
        e = re.search(r'^\s*model_reasoning_effort\s*=\s*"([^"]+)"', cfg_text, re.M)
        if e:
            default_effort = e.group(1)
    models = []
    cache_file = home / "models_cache.json"
    if cache_file.exists():
        try:
            cdata = json.loads(cache_file.read_text(encoding="utf-8", errors="replace"))
            for item in cdata.get("models", []):
                if isinstance(item, dict) and item.get("slug"):
                    models.append(item["slug"])
        except ValueError:
            pass
    if not models and default_model:
        models = [default_model]
    rc, out, err = _run_probe([exe_path, "login", "status"], timeout=5)
    status = (out + err).lower()
    logged_in = rc == 0 and "logged in" in status and "chatgpt" in status
    return {
        "authenticated": logged_in,
        "default_model": default_model,
        "default_effort": default_effort,
        "models": models,
    }


def _default_registry():
    """Create initial registry, seeding benchmarks from ~/.store-automation/models.json if available."""
    reg = {
        "schema_version": 1,
        "updated_at": now_iso(),
        "benchmarks": {
            "source": "builtin-heuristic",
            "updated_at": now_iso(),
            "models": dict(BUILTIN_BENCHMARKS),
        },
        "pools": {},
        "models": {},
        "cli_agents": {},
    }
    if STORE_AUTOMATION_MODELS.exists():
        try:
            sa = json.loads(STORE_AUTOMATION_MODELS.read_text(encoding="utf-8", errors="replace"))
            sa_bm = ((sa.get("benchmarks") or {}).get("models") or {})
            for k, v in sa_bm.items():
                if isinstance(v, dict) and "quality" in v:
                    reg["benchmarks"]["models"][norm_key(k)] = {
                        "quality": v.get("quality"),
                        "coding": v.get("coding"),
                    }
        except ValueError:
            pass
    return reg


def load(path=None):
    p = registry_path(path)
    if not p.exists():
        return _default_registry()
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except ValueError as exc:
        raise ValueError(f"{p}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{p}: root must be an object")
    data.setdefault("schema_version", 1)
    data.setdefault("benchmarks", {"source": "builtin", "updated_at": "", "models": dict(BUILTIN_BENCHMARKS)})
    bm_models = data["benchmarks"].setdefault("models", {})
    for k, v in BUILTIN_BENCHMARKS.items():
        bm_models.setdefault(k, dict(v))
    data.setdefault("pools", {})
    data.setdefault("models", {})
    data.setdefault("cli_agents", {})
    return data


def save(data, path=None):
    p = registry_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p


def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def scan_agents(path=None, probe_quota=True, persist=True):
    """Scan local machine for installed CLI agents, populate pools/models, and optionally read live quotas."""
    data = load(path)
    discovered = {}
    for cli_id, binaries, desc in CLI_SPECS:
        exe = which_cli(binaries)
        if not exe:
            continue
        rc, ver_out, ver_err = _run_probe([exe, "--version"], timeout=3)
        raw_ver = ver_out if rc == 0 and ver_out else (ver_out or ver_err)
        if "timed out" in raw_ver.lower():
            ver_line = "installed"
        else:
            ver_line = next((l.strip() for l in raw_ver.splitlines() if l.strip()), "installed")
        entry = {
            "id": cli_id,
            "binary": exe,
            "description": desc,
            "version": ver_line[:80],
            "available": True,
            "authenticated": False,
            "discovered_at": now_iso(),
        }
        if cli_id == "codex":
            cinfo = probe_codex_info(exe)
            entry.update(cinfo)
            pool = data["pools"].setdefault("codex", {"remaining_pct": None, "reserve_pct": WORKER_RESERVE_PCT})
            if probe_quota:
                q = probe_codex_quota(exe)
                if q:
                    pool.update(q)
                    entry["quota"] = q
            for m_id in entry["models"]:
                data["models"].setdefault(f"codex/{m_id}", {
                    "cli": "codex",
                    "model_id": m_id,
                    "pool": "codex",
                    "benchmark_key": norm_key(m_id),
                    "cost_weight": 1.0,
                    "tiers": [],
                    "roles": [],
                    "efforts": ["low", "medium", "high", "xhigh"],
                    # Cached model names and login state do not establish model entitlement.
                    "available": False,
                })
        elif cli_id == "opencode":
            oc_models = probe_opencode_models(exe)
            entry["models"] = oc_models
            data["pools"].setdefault("opencode-catalog", {"remaining_pct": None, "reserve_pct": 10.0, "plan_type": "unknown"})
            for om in oc_models:
                data["models"].setdefault(f"opencode:{om}", {
                    "cli": "opencode", "model_id": om, "pool": "opencode-catalog",
                    "roles": [], "tiers": [], "efforts": ["default"], "available": False,
                })
        elif cli_id == "claude":
            cstat = probe_claude_status(exe)
            cstat["authenticated"] = bool(cstat.get("authenticated") and cstat.get("subscription_type") and cstat.get("auth_method") != "api_key")
            entry.update(cstat)
            data["pools"].setdefault("claude", {
                "remaining_pct": None,
                "reserve_pct": WORKER_RESERVE_PCT,
                "plan_type": cstat.get("subscription_type") or "subscription",
            })
        elif cli_id == "gemini":
            entry["authenticated"] = False  # Local credential files do not prove usable subscription access.
            data["pools"].setdefault("gemini", {"remaining_pct": None, "reserve_pct": WORKER_RESERVE_PCT})
        elif cli_id == "qwen":
            entry["authenticated"] = False
            data["pools"].setdefault("qwen", {"remaining_pct": None, "reserve_pct": WORKER_RESERVE_PCT})
        elif cli_id == "agy":
            data["pools"].setdefault("agy", {"remaining_pct": None, "reserve_pct": DIRECTOR_RESERVE_PCT})
        if cli_id in ("mcode", "kimi", "hermes") and not any(
                isinstance(spec, dict) and spec.get("cli") == cli_id for spec in data["models"].values()):
            data["pools"].setdefault(cli_id, {"remaining_pct": None, "reserve_pct": WORKER_RESERVE_PCT})
            data["models"].setdefault(f"{cli_id}/default", {
                "cli": cli_id, "model_id": "default", "pool": cli_id,
                "roles": [], "tiers": [], "efforts": ["default"], "available": False,
            })
        discovered[cli_id] = entry
    for cli_id, entry in discovered.items():
        existing = (data.get("cli_agents") or {}).get(cli_id)
        if existing and isinstance(existing, dict):
            # Preserve explicitly configured adapter and other local CLI metadata.
            entry = {**existing, **entry}
            for key in ("binary", "worker_argv"):
                if existing.get(key) is not None:
                    entry[key] = existing[key]
            discovered[cli_id] = entry
    data["cli_agents"] = {**(data.get("cli_agents") or {}), **discovered}
    if persist:
        save(data, path)
    return data


def refresh_quota(path=None):
    """Refresh live subscription rate limits for discovered CLI agents."""
    data = load(path)
    agents = data.get("cli_agents", {})
    if not agents:
        return scan_agents(path, probe_quota=True)
    codex_info = agents.get("codex")
    if codex_info and codex_info.get("binary"):
        q = probe_codex_quota(codex_info["binary"])
        if q:
            data["pools"].setdefault("codex", {}).update(q)
            codex_info["quota"] = q
    claude_info = agents.get("claude")
    if claude_info and claude_info.get("binary"):
        cs = probe_claude_status(claude_info["binary"])
        claude_info.update(cs)
    save(data, path)
    return data


# ── Model Benchmark & Quota-Aware Selection ───────────────────────────────

def _benchmark_for(data, alias, spec):
    models = (data.get("benchmarks") or {}).get("models") or {}
    for candidate in (spec.get("benchmark_key"), spec.get("model_id"), alias, norm_key(spec.get("model_id", "")), norm_key(alias)):
        if candidate and candidate in models and isinstance(models[candidate], dict):
            return models[candidate]
    return {}


def _quality(bm):
    vals = [bm[k] for k in ("coding", "quality", "intelligence")
            if type(bm.get(k)) in (int, float)]
    return round(sum(vals) / len(vals), 2) if vals else None


def _pool_status(data, spec, role, tier):
    pool_name = spec.get("pool")
    pool = (data.get("pools") or {}).get(pool_name or "") or {}
    rem = pool.get("remaining_pct")
    raw_reserve = pool.get("reserve_pct", WORKER_RESERVE_PCT)
    if type(raw_reserve) not in (int, float):
        return False, None, "invalid quota reserve"
    reserve = float(raw_reserve)
    if not math.isfinite(reserve) or not 0 <= reserve <= 100:
        return False, None, "invalid quota reserve"
    if rem is not None and (type(rem) not in (int, float) or not math.isfinite(rem) or not 0 <= rem <= 100):
        return False, None, "invalid remaining quota"
    if isinstance(rem, (int, float)):
        if rem <= max(reserve, WORKER_RESERVE_PCT):
            return False, rem, f"pool {pool_name} at {rem}% <= reserve {max(reserve, WORKER_RESERVE_PCT)}%"
        if role == "worker" and tier in ("L", "M") and rem <= DIRECTOR_RESERVE_PCT:
            return False, rem, f"pool {pool_name} at {rem}% <= director reserve {DIRECTOR_RESERVE_PCT}%"
        return True, rem, "ok"
    return True, None, "unmetered"


def _effort_for(spec, tier, risk):
    supported = [e.lower() for e in (spec.get("efforts") or EFFORTS)]
    if tier == "L":
        wanted = ("low", "medium", "high")
    elif tier == "M":
        wanted = ("high", "medium", "low") if risk == "HIGH" else ("medium", "low", "high")
    else:
        wanted = ("high", "xhigh", "medium")
    for e in wanted:
        if e in supported:
            return e
    return supported[0] if supported else "medium"


def candidates(data, role="worker", tier="M", risk="MEDIUM", exclude="", cli_filter=""):
    ex = {x.strip() for x in (exclude or "").split(",") if x.strip()}
    floor = QUALITY_FLOOR.get((tier, risk), 48)
    primary_rows, fallback_rows = [], []

    for alias, spec in sorted((data.get("models") or {}).items()):
        if not isinstance(spec, dict) or alias in ex:
            continue
        if not spec.get("available", True):
            continue
        if cli_filter and spec.get("cli") != cli_filter:
            continue
        roles = [r.lower() for r in (spec.get("roles") or ROLES)]
        tiers = [t.upper() for t in (spec.get("tiers") or ("L", "M", "H"))]
        if role not in roles or tier not in tiers:
            continue
        p_ok, rem_pct, pool_reason = _pool_status(data, spec, role, tier)
        if not p_ok and not spec.get("user_approved"):
            continue
        if not p_ok and spec.get("user_approved") and ("invalid" in pool_reason or pool_reason.startswith("pool ")):
            continue
        bm = _benchmark_for(data, alias, spec)
        q = _quality(bm)
        effective_q = q if q is not None else (float(spec["quality"]) if type(spec.get("quality")) in (int, float) else None)
        if effective_q is not None and not math.isfinite(effective_q):
            if spec.get("user_approved"):
                effective_q = None
            else:
                continue
        if effective_q is None and not spec.get("user_approved"):
            continue
        if effective_q is not None and effective_q < floor and not spec.get("user_approved"):
            continue
        try:
            cost = float(spec.get("cost_weight", 1.0))
        except (TypeError, ValueError):
            cost = 1.0
        if not math.isfinite(cost):
            cost = 1.0
        quality_sort = effective_q if effective_q is not None else 0.0
        if tier in ("L", "M") and role == "worker":
            sort_key = (cost, -(rem_pct if rem_pct is not None else 50.0), -quality_sort, alias)
        else:
            sort_key = (-quality_sort, cost, -(rem_pct if rem_pct is not None else 50.0), alias)
        row = {
            "alias": alias,
            "cli": spec.get("cli", ""),
            "model_id": spec.get("model_id") or alias,
            "effort": _effort_for(spec, tier, risk),
            "quality": effective_q,
            "cost_weight": cost,
            "pool": spec.get("pool", ""),
            "remaining_pct": rem_pct,
        }
        if p_ok == "director_reserve":
            fallback_rows.append((sort_key, row))
        else:
            primary_rows.append((sort_key, row))

    primary_rows.sort(key=lambda item: item[0])
    fallback_rows.sort(key=lambda item: item[0])
    return [r for _, r in primary_rows] + [r for _, r in fallback_rows]


def gate(B, task, alias, action, path=None, root=None):
    """Validate that `alias` is permitted for `action` (start/review/accept) on `task`."""
    p = registry_path(path)
    if not alias or not p.exists():
        return
    data = load(p)
    selected = None
    if root is not None:
        import runtime_pool as P
        session = P.load_session(root, p)
        if session and session.get("status") == "APPROVED":
            data, session = P.approved_data(B, root, data, p)
            selected = session["selection"].get("models", {}).get(alias)
            if selected is None:
                raise ValueError(f"{alias}: not selected in the approved model pool")
    models = data.get("models") or {}
    if not models:
        return
    spec = models.get(alias)
    if not isinstance(spec, dict):
        #Only enforce strict registry membership when explicitly registered or whenPB_STRICT_AGENTS=1
        for k, v in models.items():
            if isinstance(v, dict) and (v.get("model_id") == alias or k.endswith("/" + alias)):
                alias, spec = k, v
                break
    if not isinstance(spec, dict):
        if os.environ.get("PB_STRICT_AGENTS") == "1" or path is not None:
            raise ValueError(f"{alias}: not in model registry ({p}); run `agents list` or `agents scan`")
        return
    if not spec.get("available", True):
        raise ValueError(f"{alias}: marked unavailable in model registry")
    roles = [r.lower() for r in (spec.get("roles") or ROLES)]
    if selected:
        needed_roles = ({"lead"} if action == "start" and score_task(B, None, task)["effective_tier"] == "H"
                        else {"worker", "lead"} if action == "start"
                        else {"reviewer", "lead"} if action == "review"
                        else {"worker", "lead", "reviewer"})
        if not (set(selected["roles"]) & needed_roles):
            raise ValueError(f"{alias}: role is outside the approved pool selection for {action}")
    scored = score_task(B, None, task) if task else None
    tier = scored["effective_tier"] if scored else "M"
    tier = tier if tier in B.TIER_VALUES else "M"
    risk = V.effective_risk(B, task) if task else "MEDIUM"
    if action == "start":
        needed = {"lead"} if tier == "H" else {"worker", "lead"}
        if not (set(roles) & needed):
            raise ValueError(f"{alias}: role not allowed to start tier {tier} task (roles: {', '.join(roles)})")
        tiers = [t.upper() for t in (spec.get("tiers") or B.TIER_VALUES)]
        if tier not in tiers and "lead" not in roles:
            raise ValueError(f"{alias}: tier {tier} not allowed (tiers: {', '.join(tiers)})")
        p_ok, _, reason = _pool_status(data, spec, "worker" if tier != "H" else "lead", tier)
        if not p_ok and (not spec.get("user_approved") or "invalid" in reason):
            raise ValueError(f"{alias}: {reason}")
        quality = _quality(_benchmark_for(data, alias, spec))
        if quality is None:
            quality = spec.get("quality")
        if not spec.get("user_approved") and (not isinstance(quality, (int, float)) or not math.isfinite(quality) or quality < QUALITY_FLOOR[(tier, risk)]):
            raise ValueError(f"{alias}: quality below tier={tier} risk={risk} floor")
    elif action == "review":
        if "reviewer" not in roles and "lead" not in roles:
            raise ValueError(f"{alias}: not permitted to review (roles: {', '.join(roles)})")
        supported = [t for t in (spec.get("tiers") or B.TIER_VALUES) if t in B.TIER_VALUES]
        if not supported or max(B.TIER_VALUES.index(t) for t in supported) < B.TIER_VALUES.index(tier):
            raise ValueError(f"{alias}: reviewer does not support tier {tier}")
        quality = _quality(_benchmark_for(data, alias, spec))
        if quality is None:
            quality = spec.get("quality")
        if not spec.get("user_approved") and (not isinstance(quality, (int, float)) or not math.isfinite(quality) or quality < QUALITY_FLOOR[(tier, risk)]):
            raise ValueError(f"{alias}: reviewer quality below tier={tier} risk={risk} floor")
        if task:
            impl = V.implementers(B, task)
            if canonical_identity(alias, p) in {canonical_identity(i, p) for i in impl}:
                raise ValueError(f"{alias}: implemented {task['id']}; reviewer must be a different agent/model")
            bm_rev = quality
            for imp in impl:
                imp_spec = next((v for k, v in models.items() if canonical_identity(k, p) == canonical_identity(imp, p)), None)
                if isinstance(imp_spec, dict):
                    bm_imp = _quality(_benchmark_for(data, imp, imp_spec))
                    if bm_imp is None:
                        bm_imp = imp_spec.get("quality")
                    if not spec.get("user_approved") and bm_rev is not None and bm_imp is not None and bm_rev < bm_imp:
                        raise ValueError(f"reviewer {alias} (quality {bm_rev}) is weaker than implementer {imp} (quality {bm_imp})")


# ── Sub-Agent CLI Delegation (`PB delegate`) ──────────────────────────────

def build_worker_prompt(B, root, task, score_info):
    """Build a compact, zero-history execution prompt for a delegated CLI worker."""
    rel_task = Path(os.path.relpath(task["file"], root)).as_posix()
    surf = score_info["surface"]
    rules = [
        f"You are executing Project Brain task `{task['id']}: {task['title']}` in `{Path(root).as_posix()}`.",
        "Read repository agent instructions, `.project-brain/constraints.md`, matching domain slices in `.project-brain/current.md`, and task-linked ADRs before editing.",
        f"1. Read `{rel_task}` first. Follow its `Objective`, `Steps`, `Acceptance`, and `Verify` sections strictly.",
        f"2. Restrict all file edits to `Areas`: {', '.join(f'`{a}`' for a in task['areas']) or '(see task file)'}.",
        "3. Do NOT modify unrelated tasks, do NOT rewrite git history, and do NOT hand-edit `## Evidence` or `## Review`.",
    ]
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
    rules.append("6. Run every command in `## Verify` and fix any failures before finishing.")
    return "\n".join(rules)


def _worker_command(cli_name, binary, root, model_id, effort, prompt, cli_config=None, prompt_file=""):
    """Construct the exact non-interactive CLI command + optional stdin payload."""
    root_str = str(Path(root).resolve())
    if cli_name == "mcode" and effort != "default" and re.search(r"(?:^|[-_])m3(?:$|[.-])", model_id, re.I):
        raise ValueError("MiniMax-M3 does not support a worker effort setting")
    if cli_name in ("opencode", "agy") and prompt_file:
        prompt = f"Read the task instructions from {prompt_file} and execute them."
    template = (cli_config or {}).get("generic_worker_argv", (cli_config or {}).get("worker_argv"))
    if template is not None:
        prompt_stdin = cli_config.get("prompt_stdin")
        if prompt_stdin is not None and type(prompt_stdin) is not bool:
            raise ValueError(f"invalid prompt_stdin adapter setting for {cli_name}")
        if not isinstance(template, list) or not template or any(not isinstance(item, str) for item in template):
            raise ValueError(f"invalid worker_argv adapter for {cli_name}")
        allowed = {"binary", "root", "model", "effort", "prompt", "prompt_file"}
        values = {"binary": binary, "root": root_str, "model": model_id,
                  "effort": effort, "prompt": prompt, "prompt_file": prompt_file}
        argv = []
        for raw in template:
            names = re.findall(r"\{([^{}]+)\}", raw)
            if any(name not in allowed for name in names):
                raise ValueError(f"unknown worker_argv placeholder for {cli_name}")
            value = raw
            for name in names:
                value = value.replace("{" + name + "}", str(values[name]))
            if "{" in value or "}" in value:
                raise ValueError(f"invalid worker_argv placeholder for {cli_name}")
            argv.append(value)
        if not argv[0]:
            raise ValueError(f"worker_argv binary is empty for {cli_name}")
        return argv, prompt if prompt_stdin is True else None
    if cli_name == "codex":
        argv = [binary, "exec"]
        if model_id != "default":
            argv += ["-m", model_id]
        if effort != "default":
            argv += ["-c", f"model_reasoning_effort='{effort}'"]
        argv += ["--cd", root_str, "--sandbox", "workspace-write",
                 "-c", "approval_policy='never'", "-"]
        return argv, prompt
    if cli_name == "opencode":
        argv = [binary, "run", "--pure"]
        if model_id != "default":
            argv += ["-m", model_id]
        if effort != "default":
            argv += ["--variant", effort]
        return argv + ["--dir", root_str, prompt], None
    if cli_name == "claude":
        argv = [binary, "-p"]
        if model_id != "default":
            argv += ["--model", model_id]
        if effort != "default":
            argv += ["--effort", effort]
        return argv + ["--permission-mode", "acceptEdits"], prompt
    if cli_name == "gemini":
        argv = [binary, "-p", "Execute the task provided on stdin."]
        if model_id != "default":
            argv += ["-m", model_id]
        return argv + ["--approval-mode", "auto_edit"], prompt
    if cli_name == "agy":
        argv = [binary]
        if model_id != "default":
            argv += ["--model", model_id]
        if effort != "default":
            argv += ["--effort", effort]
        return argv + ["--mode", "auto", "--print", prompt], None
    if cli_name == "qwen":
        argv = [binary, "-p", "Execute the task provided on stdin."]
        if model_id != "default":
            argv += ["-m", model_id]
        return argv, prompt
    if cli_name == "mcode":
        argv = [binary, "exec", "--input", "-", "--cwd", root_str,
                "--prompt-mode", "coding", "--permission", "full", "--mode", "lightweight"]
        if model_id != "default":
            argv += ["--model", model_id]
        if effort != "default":
            if model_id == "default":
                raise ValueError("MCode default model effort support is unknown; select effort=default")
            argv += ["--effort", effort]
        return argv, prompt
    raise ValueError(f"unsupported worker CLI: {cli_name}")


def _check_batch_args(argv):
    if argv and Path(argv[0]).suffix.lower() in (".cmd", ".bat") and any(V.BATCH_META.search(arg) for arg in argv):
        raise ValueError("Unsafe Windows batch arguments; use a native executable or a CLI accepting the prompt on stdin")


def delegate_task(B, root, tid, cli_filter="", model_override="", effort_override="",
                  dry_run=False, force=False, timeout=900, reg_path=None):
    # ponytail: one worker per checkout; use isolated worktrees for parallel implementation.
    with B.checkout_lock(root, timeout=0.1, name="delegate.lock"):
        return _delegate_task(B, root, tid, cli_filter, model_override, effort_override,
                              dry_run, force, timeout, reg_path)


def _delegate_task(B, root, tid, cli_filter="", model_override="", effort_override="",
                   dry_run=False, force=False, timeout=900, reg_path=None):
    """Select an eligible low/medium-cost CLI worker, run the task in ProcessTree, and run `PB check`."""
    if not B.brain_exists(root):
        print("NO_BRAIN")
        return 3
    task = B.find_task(root, tid)
    if not task:
        print(f"FAIL {tid}: task not found")
        return 2
    sinfo = score_task(B, root, task)
    if task["status"] not in ("READY", "IN_PROGRESS"):
        print(f"FAIL {task['id']}: delegation requires READY or IN_PROGRESS status")
        return 2
    if sinfo["effective_tier"] == "H" and not force:
        print(
            f"FAIL {task['id']}: computed Tier is H (score {sinfo['score']}/100, risk {sinfo['effective_risk']}). "
            "High-complexity architecture tasks belong to the lead model; split into L/M tasks or pass --force."
        )
        return 2
    if B.task_errors(task) or sinfo["must_split"]:
        print(f"FAIL {task['id']}: task is not an executable spec (missing Steps, Acceptance checkboxes, or Verify command)")
        return 2

    data = load(reg_path)
    dispatch_config = data
    approved_session = None
    if dry_run:
        import runtime_pool as P
        pool_session = P.load_session(root, reg_path)
        if pool_session and pool_session.get("status") == "APPROVED":
            data, approved_session = P.approved_data(B, root, data, reg_path)
        elif not data.get("cli_agents") and not data.get("models"):
            data = scan_agents(reg_path, probe_quota=False, persist=False)
    else:
        import runtime_pool as P
        try:
            data, approved_session = P.approved_data(B, root, data, reg_path)
        except ValueError as exc:
            print(f"FAIL {task['id']}: {exc}; approve a model pool before dispatch")
            return 2

    eligible = candidates(data, role="worker", tier=sinfo["effective_tier"], risk=sinfo["effective_risk"], cli_filter=cli_filter)

    chosen = None
    if model_override:
        chosen = next((c for c in eligible if c["alias"] == model_override or c["model_id"] == model_override), None)
        if chosen is None:
            print(f"FAIL {task['id']}: requested model is not an eligible registered worker")
            return 2
    else:
        cands = eligible
        if not cands:
            print(f"FAIL {task['id']}: no eligible CLI worker model found for tier={sinfo['effective_tier']} risk={sinfo['effective_risk']} (check `agents list` / `agents scan`)")
            return 2
        chosen = cands[0]
    if effort_override:
        supported = data["models"][chosen["alias"]].get("efforts") or EFFORTS
        if effort_override not in supported:
            raise ValueError(f"Unsupported effort {effort_override} for {chosen['alias']}")
        chosen["effort"] = effort_override

    if task.get("owner") and task["owner"] != chosen["alias"]:
        print(f"FAIL {task['id']}: owned by {task['owner']}; explicit takeover required before delegation")
        return 2

    cli_name = chosen["cli"]
    cli_entry = (data.get("cli_agents") or {}).get(cli_name) or {}
    binary = cli_entry.get("binary") or which_cli((cli_name,))
    if cli_name != "host" and not binary and not dry_run:
        print(f"FAIL {task['id']}: CLI binary for `{cli_name}` not found on system")
        return 2
    binary = binary or cli_name

    prompt = build_worker_prompt(B, root, task, sinfo)
    if cli_name == "host":
        if dry_run:
            print(f"DELEGATE_PLAN {task['id']}: native host handoff preview")
            if not approved_session:
                print("PREVIEW ONLY: model pool approval required before dispatch")
            return 0
        import runtime_pool as P
        job_id = P.reserve(B, root, dispatch_config, chosen["alias"], chosen["effort"], reg_path,
                           expected_session_id=approved_session["session_id"])
        try:
            rc = B.cmd_start(root, task["id"], agent=chosen["alias"], agents_path=reg_path)
        except ValueError as exc:
            P.finish(B, root, job_id, exit_code=2, registry=reg_path)
            print(f"FAIL {task['id']}: {exc}")
            return 2
        if rc != 0:
            P.finish(B, root, job_id, exit_code=rc, registry=reg_path)
            return rc
        action = {"alias": chosen["alias"], "model_id": chosen["model_id"],
                  "effort": chosen["effort"], "task_id": task["id"],
                  "prompt": prompt[:20000], "job_id": job_id,
                  "session_id": approved_session["session_id"],
                  "root": str(Path(root).resolve()),
                  "registry": str(registry_path(reg_path).resolve()),
                  "environment": {"PB_SESSION_ID": approved_session["session_id"]}}
        print("HOST_ACTION_PENDING " + json.dumps(action, ensure_ascii=False))
        return 0

    if chosen["model_id"] == "default" and not (cli_entry.get("generic_worker_argv") or cli_entry.get("worker_argv")):
        print(f"FAIL {task['id']}: default provider route is unverified; select an explicit model ID or configure an adapter")
        return 2

    prompt_file = ""
    if os.name == "nt" and cli_name in ("opencode", "agy") and Path(binary).suffix.lower() in (".cmd", ".bat"):
        prompt_file = f".project-brain/.cache/runs/{task['id']}-worker-prompt.txt"
    argv, stdin_text = _worker_command(cli_name, binary, root, chosen["model_id"], chosen["effort"], prompt,
                                       cli_entry, prompt_file)
    _check_batch_args(argv)

    if dry_run:
        rem = f"{chosen['remaining_pct']}%" if chosen.get("remaining_pct") is not None else "unmetered"
        print(
            f"DELEGATE_PLAN {task['id']}: cli={cli_name} model={chosen['model_id']} effort={chosen['effort']} "
            f"tier={sinfo['effective_tier']} score={sinfo['score']}/100 pool_remaining={rem}"
        )
        if not approved_session:
            print("PREVIEW ONLY: model pool approval required before dispatch")
        print(f"  cmd: {subprocess.list2cmdline(argv)}")
        return 0

    if prompt_file:
        prompt_path = V.public_path(root, prompt_file)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        B.write_atomic(prompt_path, prompt)
    import runtime_pool as P
    try:
        job_id = P.reserve(B, root, dispatch_config, chosen["alias"], chosen["effort"], reg_path,
                           expected_session_id=approved_session["session_id"])
    except ValueError as exc:
        print(f"FAIL {task['id']}: {exc}")
        return 2
    try:
        rc = B.cmd_start(root, task["id"], agent=chosen["alias"], agents_path=reg_path)
    except ValueError as exc:
        P.finish(B, root, job_id, exit_code=2, registry=reg_path)
        print(f"FAIL {task['id']}: {exc}")
        return 2
    if rc != 0:
        P.finish(B, root, job_id, exit_code=rc, registry=reg_path)
        return rc

    rdir = V.public_path(root, ".project-brain/.cache/runs")
    rdir.mkdir(parents=True, exist_ok=True)
    log_path = V.public_path(root, f".project-brain/.cache/runs/{task['id']}-delegate.log")
    log_rel = f".project-brain/.cache/runs/{log_path.name}"
    run_cmd = list(argv)
    if os.name == "nt" and run_cmd[0].lower().endswith((".cmd", ".bat")):
        run_cmd = ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(run_cmd)]

    t0 = time.monotonic()
    with open(log_path, "w", encoding="utf-8", newline="\n") as logf, tempfile.TemporaryFile(mode="w+", encoding="utf-8") as payload:
        if stdin_text is not None:
            payload.write(stdin_text)
            payload.seek(0)
        logf.write(f"# DELEGATE {task['id']} -> {chosen['alias']} (effort={chosen['effort']}) @ {now_iso()}\n")
        logf.write(f"# CMD: {subprocess.list2cmdline(argv)}\n\n")
        logf.flush()
        with V.ProcessTree() as tree:
            try:
                child_env = {k: v for k, v in os.environ.items() if not V.SECRET_ENV.search(k)}
                if approved_session:
                    child_env["PB_SESSION_ID"] = approved_session["session_id"]
                proc = tree.spawn(
                    run_cmd,
                    cwd=str(root),
                    env=child_env,
                    stdin=payload if stdin_text is not None else subprocess.DEVNULL,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                proc.wait(timeout=timeout)
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                P.finish(B, root, job_id, exit_code=None, registry=reg_path)
                logf.write(f"\nTIMEOUT after {timeout}s\n")
                print(f"FAIL {task['id']}: worker `{chosen['alias']}` timed out after {timeout}s (log: {log_rel})")
                return 2
            except Exception:
                P.finish(B, root, job_id, exit_code=None, registry=reg_path)
                raise

    P.finish(B, root, job_id, exit_code=rc, registry=reg_path)

    elapsed = time.monotonic() - t0
    print(f"WORKER_DONE {task['id']}: {chosen['alias']} (effort={chosen['effort']}) exit={rc} in {elapsed:.1f}s (log: {log_rel})")
    if rc != 0:
        return 2
    with B.checkout_lock(root):
        chk_rc, chk_lines = V.check(B, root, task["id"], timeout=timeout, actor=chosen["alias"])
    for l in chk_lines:
        print(l)
    return chk_rc


# ── CLI Command Entrypoint (`PB agents ...`) ──────────────────────────────

def run_agents(B, args):
    p = registry_path(getattr(args, "registry", None))
    sub = args.agents_cmd
    if sub in ("session", "approve", "revoke", "settle"):
        import runtime_pool as P
        root = Path(args.root).resolve()
        inherited_session_id = os.environ.get("PB_SESSION_ID")
        inherited_session = P.load_session(root, p) if inherited_session_id else None
        if inherited_session_id and (not inherited_session or inherited_session.get("session_id") != inherited_session_id):
            raise ValueError("worker session does not match the current project pool")
        if inherited_session_id and sub in ("approve", "revoke", "settle"):
            raise ValueError("delegated workers cannot change or settle the inherited model pool session")
        if sub == "session":
            if inherited_session_id:
                if getattr(args, "new", False) or getattr(args, "refresh", False):
                    raise ValueError("delegated workers cannot rotate or refresh the inherited model pool session")
                session = inherited_session
            else:
                session = P.propose(B, root, p, new=getattr(args, "new", False),
                                    refresh=getattr(args, "refresh", False))
        elif sub == "approve":
            selection_path = Path(args.file)
            selection = json.loads(selection_path.read_text(encoding="utf-8"))
            session = P.approve(B, root, selection, args.session_id, p,
                                confirmed=getattr(args, "user_confirmed", False), note=args.note)
        elif sub == "revoke":
            session = P.revoke(B, root, p)
        else:
            session = P.settle(B, root, args.job_id, args.state, args.note, p)
        if getattr(args, "json", False):
            print(json.dumps(session, indent=2, ensure_ascii=False))
        else:
            for line in P.summary(B, root, p):
                print(line)
        return 0
    if sub == "scan":
        data = scan_agents(p, probe_quota=not getattr(args, "no_quota", False))
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0
        agents = data.get("cli_agents") or {}
        print(f"DISCOVERED {len(agents)} CLI agents (saved to {p}):")
        for cid, info in sorted(agents.items()):
            q = info.get("quota") or (data.get("pools") or {}).get(cid) or {}
            rem = q.get("remaining_pct")
            rem_str = f"quota={rem}%" if isinstance(rem, (int, float)) else "quota=unknown"
            auth_str = "auth=ok" if info.get("authenticated") else "auth=missing"
            print(f"  {cid:<10} {auth_str:<12} {rem_str:<16} {info.get('version', '')[:45]} ({info.get('binary')})")
        return 0

    if sub == "quota":
        data = refresh_quota(p)
        if getattr(args, "json", False):
            print(json.dumps(data.get("pools", {}), indent=2, ensure_ascii=False))
            return 0
        for pname, pinfo in sorted((data.get("pools") or {}).items()):
            rem = pinfo.get("remaining_pct", "?")
            p5 = pinfo.get("primary_5h_remaining_pct")
            w7 = pinfo.get("weekly_7d_remaining_pct")
            detail = f" (5h={p5}%, 7d={w7}%)" if p5 is not None or w7 is not None else ""
            resets = f" resets={pinfo.get('resets_at')}" if pinfo.get("resets_at") else ""
            print(f"POOL {pname:<14} remaining={rem}%{detail}{resets}")
        return 0

    if sub == "merge":
        src = Path(args.file)
        if not src.exists():
            print(f"FAIL {src}: file not found")
            return 2
        patch = json.loads(src.read_text(encoding="utf-8", errors="replace"))
        data = deep_merge(load(p), patch)
        save(data, p)
        print(f"MERGED {p} ({len(data.get('models', {}))} models, {len(data.get('pools', {}))} pools)")
        return 0

    data = load(p)
    if sub == "list":
        models = data.get("models") or {}
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0
        if not models:
            print(f"EMPTY {p}: run `agents scan` or `agents merge <file.json>`")
            return 1
        for alias, spec in sorted(models.items()):
            if not isinstance(spec, dict):
                continue
            bm = _benchmark_for(data, alias, spec)
            q = _quality(bm)
            p_ok, rem_pct, _ = _pool_status(data, spec, "worker", "M")
            avail = "ready" if spec.get("available", True) and p_ok else "exhausted/off"
            roles = ",".join(spec.get("roles") or ROLES)
            tiers = ",".join(spec.get("tiers") or B.TIER_VALUES)
            rem = f"{rem_pct}%" if rem_pct is not None else "-"
            q_txt = f"{q:.1f}" if q is not None else "?"
            print(
                f"{alias:<28} {avail:<13} cli={spec.get('cli', '-'):<9} roles={roles:<20} "
                f"tiers={tiers:<6} quality={q_txt:<5} cost={spec.get('cost_weight', 1.0):<4} pool={rem}"
            )
        return 0

    if sub == "select":
        role = args.role
        tier = (args.tier or "").upper()
        risk = (args.risk or "").upper()
        if getattr(args, "task", None):
            task = B.find_task(Path(args.root).resolve(), args.task)
            if not task:
                print(f"FAIL {args.task}: task not found")
                return 2
            sinfo = score_task(B, Path(args.root).resolve(), task)
            tier = tier or sinfo["effective_tier"]
            risk = risk or sinfo["effective_risk"]
        tier = tier if tier in B.TIER_VALUES else ("H" if role == "lead" else "M")
        risk = risk if risk in B.RISK_VALUES else "MEDIUM"
        import runtime_pool as P
        pool_session = P.load_session(Path(args.root).resolve(), p)
        approved = bool(pool_session and pool_session.get("status") == "APPROVED")
        if approved:
            data, pool_session = P.approved_data(B, Path(args.root).resolve(), data, p)
        cands = candidates(data, role=role, tier=tier, risk=risk, exclude=getattr(args, "exclude", ""), cli_filter=getattr(args, "cli", ""))
        if not cands:
            print(f"NONE role={role} tier={tier} risk={risk}")
            return 2
        best = cands[0]
        if getattr(args, "json", False):
            print(json.dumps({"selected": best, "fallbacks": cands[1:4],
                              "approval_required": not approved}, indent=2, ensure_ascii=False))
            return 0
        q_txt = f"{best['quality']:.1f}" if best["quality"] is not None else "?"
        rem_txt = f"{best['remaining_pct']}%" if best["remaining_pct"] is not None else "unmetered"
        print(
            f"SELECT {best['alias']} cli={best['cli']} model={best['model_id']} effort={best['effort']} "
            f"role={role} tier={tier} risk={risk} quality={q_txt} cost={best['cost_weight']} pool={rem_txt}"
        )
        if not approved:
            print("PREVIEW ONLY: model pool approval required before dispatch")
        if len(cands) > 1:
            print("FALLBACK " + ", ".join(f"{c['alias']}({c['effort']})" for c in cands[1:4]))
        return 0
    return 2


# ── Foreign Planning State Adoption (`PB legacy`) ─────────────────────────

FOREIGN_SYSTEMS = (
    ("project-brain-v0", ("PROJECT_BRAIN.md",)),
    ("store-automation", (".store-automation",)),
    ("taskmaster", (".taskmaster/tasks/tasks.json", ".taskmaster")),
    ("Spec Kit", (".specify", "specs")),
    ("BMAD", ("_bmad", "_bmad-output", ".bmad-core")),
    ("OpenSpec", ("openspec",)),
    ("GSD", (".planning",)),
    ("Kiro", (".kiro/specs", ".kiro/steering")),
    ("Memory Bank", ("memory-bank", ".cursor/memory-bank")),
    ("Factory", (".factory", "missions")),
    ("Flat file", ("TODO.md", "TASKS.md", "PLAN.md", "ROADMAP.md")),
)

STORE_RELEASE_SKIP_RE = re.compile(
    r"\b(play[- ]store|google[- ]play|app[- ]store|appstore|fastlane|store[- ]listing|testflight|"
    r"publish(?:ing|ed)?|publication|distribution|deploy(?:ment|ing)?|release|yayın\w*|yayımla\w*|dağıtım\w*)\b",
    re.I,
)


def detect_foreign(root):
    root = Path(root)
    hits = []
    for name, markers in FOREIGN_SYSTEMS:
        found = [m for m in markers if (root / m).exists()]
        if found:
            hits.append((name, found))
    return hits


def _extract_foreign_tasks(root):
    """Extract candidate tasks from .store-automation, .taskmaster, or markdown checklists."""
    root = Path(root)
    extracted = []
    sa_tasks = root / ".store-automation" / "tasks"
    if sa_tasks.is_dir():
        for f in sorted(sa_tasks.glob("SA-*.md")):
            text = _read_safe(V.public_path(root, f.relative_to(root).as_posix())) or ""
            title_m = re.search(r"^#\s+(?:SA-\d+\s*[—–-]\s*)?(.+)$", text, re.M)
            title = title_m.group(1).strip() if title_m else f.stem
            if STORE_RELEASE_SKIP_RE.search(title) or STORE_RELEASE_SKIP_RE.search(text):
                continue
            if re.search(r"^Status:\s*(DONE|COMPLETE(?:D)?|CANCELLED|CANCELED)\b", text, re.I | re.M):
                continue
            extracted.append({"source": f.relative_to(root).as_posix(), "title": title, "text": text})
    tm_json = root / ".taskmaster" / "tasks" / "tasks.json"
    if tm_json.exists():
        try:
            tdata = json.loads(_read_safe(V.public_path(root, tm_json.relative_to(root).as_posix())) or "{}")
            items = tdata.get("tasks", []) if isinstance(tdata, dict) else []
            if isinstance(tdata, dict) and not items:
                items = [item for tag in tdata.values() if isinstance(tag, dict) for item in tag.get("tasks", [])]
            for item in items or []:
                if isinstance(item, dict) and item.get("title") and item.get("status", "").lower() not in ("done", "completed", "cancelled", "canceled"):
                    text = json.dumps(item, ensure_ascii=False, indent=2)
                    if STORE_RELEASE_SKIP_RE.search(text):
                        continue
                    extracted.append({
                        "source": ".taskmaster/tasks/tasks.json",
                        "title": item["title"],
                        "objective": item.get("description") or item["title"],
                        "text": text,
                    })
        except ValueError:
            pass
    for flat in ("TODO.md", "TASKS.md", "PLAN.md", "ROADMAP.md"):
        fp = root / flat
        if fp.exists():
            for line in (_read_safe(V.public_path(root, flat)) or "").splitlines():
                m = re.match(r"^\s*-\s*\[\s*\]\s+(.+)$", line)
                if m and not STORE_RELEASE_SKIP_RE.search(m.group(1)):
                    extracted.append({"source": flat, "title": m.group(1).strip(), "text": line})
    return extracted


def cmd_legacy(B, root, apply=False):
    root = Path(root)
    hits = detect_foreign(root)
    if not hits:
        print("NONE: no foreign planning systems detected")
        return 0
    for name, paths in hits:
        print(f"FOREIGN {name}: {', '.join(paths)}")
    candidates_list = _extract_foreign_tasks(root)
    print(f"CANDIDATES: {len(candidates_list)} open tasks (store publishing/distribution tasks filtered out)")
    for c in candidates_list[:15]:
        print(f"  - [{c['source']}] {c['title'][:70]}")
    if not apply:
        print("NEXT: Run `legacy --apply` to initialize `.project-brain/` and import non-publishing tasks as PLANNED.")
        return 0
    if any(name == "project-brain-v0" for name, _ in hits):
        import migrate
        return migrate.run(root, apply=True)
    if not B.brain_exists(root):
        B.cmd_init(root)
    created = 0
    for c in candidates_list:
        title = " ".join(str(c["title"]).split())
        raw = c.get("text") or c.get("objective") or title
        source_id = hashlib.sha256((c["source"] + "\0" + raw).encode("utf-8")).hexdigest()[:16]
        source_rel = f".project-brain/migration-backup/imported/{source_id}-source.md"
        # ponytail: conservative publication keywords can skip mixed tasks; manually split them before importing.
        source = V.public_path(root, source_rel)
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            B.write_atomic(source, raw)
        tasks = B.list_tasks(root)
        if any(source_rel in t["objective"] for t in tasks):
            continue
        # Recover only an untouched scaffold left by a crash, never an existing user's spec.
        partial = [t for t in tasks if t["title"] == title and t["status"] == "PLANNED"
                   and t["text"].strip() == B.TASK_TMPL.format(id=t["id"], title=title, status="PLANNED",
                        risk="MEDIUM", priority="P2", tier="M", deps="-").strip()]
        if partial:
            task = partial[0]
        else:
            before = {t["id"] for t in tasks}
            rc = B.cmd_new(root, title, depends="", risk="MEDIUM", priority="P2", tier="M")
            if rc:
                return rc
            task = next(t for t in B.list_tasks(root) if t["id"] not in before)
            created += 1
        body = B.read(task["file"])
        objective = f"Imported from `{c['source']}`. Read the preserved original at `{source_rel}` before refining this task."
        B.write_atomic(task["file"], body.replace("<what and why, in the user's words>", objective, 1))
    print(f"ADOPTED: created {created} PLANNED tasks in .project-brain/tasks/")
    return 0
