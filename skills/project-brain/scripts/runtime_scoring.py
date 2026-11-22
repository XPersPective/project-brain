"""Deterministic task complexity scoring and UI/backend surface classification.

Python 3.8+, standard library only. Imports only runtime_core.
"""

import json
import re

import runtime_core as Core

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


def task_surface(task):
    """Classify whether a task touches UI/Frontend, Backend/Data/Runtime, or Architecture."""
    domains_str = " ".join(task.get("domains", []))
    areas_str = " ".join(task.get("areas", []))
    body_str = f"{task.get('title', '')}\n{task.get('objective', '')}\n" + "\n".join(task.get("steps", []))
    ui = bool(
        UI_DOMAIN_RE.search(domains_str)
        or UI_AREA_RE.search(areas_str)
        or re.search(r"\[(visual|interaction|accessibility)\]", task.get("text", ""), re.I)
    )
    backend = bool(
        BACKEND_DOMAIN_RE.search(domains_str)
        or BACKEND_AREA_RE.search(areas_str)
        or re.search(r"\[(security|integration|architecture)\]", task.get("text", ""), re.I)
    )
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

    risk_floor = "LOW"
    if surf["ui"] or surf["backend"] or len(areas) > 2 or len(domains) > 1:
        risk_floor = "MEDIUM"
    if surf["arch"] or len(domains) >= 3 or len(areas) >= 6:
        risk_floor = "HIGH"
    eff_risk = B.RISK_VALUES[max(B.RISK_VALUES.index(risk_decl), B.RISK_VALUES.index(risk_floor))]

    pts_areas = min(20, len(areas) * 4)
    pts_domains = min(15, max(0, len(domains) - 1) * 6 + (4 if domains else 0))
    pts_steps = min(16, len(steps) * 3)
    pts_acc = min(14, len(acc) * 2)
    pts_deps = min(10, len(deps) * 4)
    pts_risk = {"LOW": 0, "MEDIUM": 10, "HIGH": 22}[eff_risk]
    pts_arch = 14 if surf["arch"] else 0
    pts_uif = 10 if surf["ui_foundation"] else 0

    raw_score = min(100, pts_areas + pts_domains + pts_steps + pts_acc + pts_deps + pts_risk + pts_arch + pts_uif)

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

    raw_kinds = {item.get("raw_kind") for item in acc if item.get("raw_kind")}
    missing_ui_triad = []
    if surf["ui"]:
        for req_k in ("visual", "interaction", "accessibility"):
            if req_k not in raw_kinds:
                missing_ui_triad.append(req_k)

    executable = bool(task.get("has_steps") and task.get("checkboxes") and task.get("verify_cmd") and not task.get("vague"))
    must_split = raw_score > 78 or task.get("spec_lines", task.get("lines", 0)) > B.BUDGETS["task"] or len(steps) > 10
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


def effective_risk(B, task):
    """Risk never drops below deterministic surface/scope floors."""
    declared = task.get("risk") if task.get("risk") in B.RISK_VALUES else "MEDIUM"
    floor = score_task(B, None, task)["effective_risk"]
    return B.RISK_VALUES[max(B.RISK_VALUES.index(declared), B.RISK_VALUES.index(floor))]


def apply_score_headers(B, task, info):
    """Update Tier and Risk headers in-place in the task file."""
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
        Core.write_atomic(task["file"], "\n".join(lines) + "\n")
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
        del_str = "DELEGATABLE (worker)" if r["delegatable"] else ("SPLIT_FIRST" if r["must_split"] else "LEAD_ONLY")
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
