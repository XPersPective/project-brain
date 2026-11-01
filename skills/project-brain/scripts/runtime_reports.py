"""Lossless private reports with bounded, deterministic director views."""
import json
import math
import statistics

import runtime_security as S


def validate(report):
    if not isinstance(report, dict) or report.get("status") not in ("completed", "partial", "blocked"):
        raise ValueError("Missing structured completed/partial/blocked report")
    if not isinstance(report.get("summary"), str) or not report["summary"].strip():
        raise ValueError("Report summary required")
    for key in ("files", "checks", "research", "blockers"):
        if not isinstance(report.get(key), list):
            raise ValueError("Report needs " + key + " array")
    if any(not isinstance(b, str) for b in report["blockers"]):
        raise ValueError("Blockers must be strings")
    if "findings" in report and (not isinstance(report["findings"], list) or any(not isinstance(f, str) for f in report["findings"])):
        raise ValueError("Findings must be a string array")
    if "verdict" in report and report["verdict"] not in ("PASS", "BLOCKED"):
        raise ValueError("Review verdict must be PASS/BLOCKED")
    for check in report["checks"]:
        if (not isinstance(check, dict) or not isinstance(check.get("command"), str)
                or check.get("outcome") not in ("passed", "failed", "not_run")):
            raise ValueError("Invalid check observation")
    for file in report["files"]:
        if not isinstance(file, dict) or not isinstance(file.get("path"), str):
            raise ValueError("Invalid file observation")
    raw = json.dumps(report, ensure_ascii=False)
    if len(raw.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Report exceeds 1 MiB")
    S.require_clean(raw, "worker report")
    return report


def compact(report, reference, limit=1024):
    validate(report)
    decision = bool(report["blockers"] or report["status"] != "completed"
                    or any(c["outcome"] == "failed" for c in report["checks"])
                    or report.get("findings") or report.get("decision_required"))
    view = {"status": report["status"], "summary": report["summary"][:300],
            "files": len(report["files"]), "checks": len(report["checks"]),
            "blockers": len(report["blockers"]), "decision_required": decision, "report": reference}
    while len(json.dumps(view, ensure_ascii=False).encode("utf-8")) > limit and view["summary"]:
        view["summary"] = view["summary"][:-20]
    if len(json.dumps(view, ensure_ascii=False).encode("utf-8")) > limit:
        raise ValueError("Reference exceeds output budget")
    return view


def usage(value):
    """Keep provider totals and subsets distinct. Missing counters stay unknown."""
    if value is None:
        return {"source": "unknown", "total": None}
    if not isinstance(value, dict) or not isinstance(value.get("source"), str):
        raise ValueError("Usage requires a provider source")
    for k, v in value.items():
        if k == "source":
            continue
        if k not in ("total", "input", "output", "reasoning", "cached") or (v is not None and
                (type(v) not in (int, float) or not math.isfinite(v) or v < 0)):
            raise ValueError("Invalid usage counter")
    return dict(value, total=value.get("total"))


def compare(records):
    """Compare like acceptance contracts; unknown or failed runs are never hidden."""
    if not isinstance(records, list) or not records or len(records) > 10000:
        raise ValueError("Expected 1..10000 measurement records")
    groups, contracts = {}, {}
    for r in records:
        if not isinstance(r, dict) or r.get("variant") not in ("baseline", "candidate"):
            raise ValueError("Measurement variant must be baseline/candidate")
        if not all(isinstance(r.get(k), str) and r[k] for k in ("case", "acceptance", "model", "environment")):
            raise ValueError("Measurement requires case/acceptance/model/environment")
        key = (r["case"], r["model"], r["environment"])
        if key in contracts and contracts[key] != r["acceptance"]:
            raise ValueError("Acceptance changed between measurements")
        contracts[key] = r["acceptance"]
        if type(r.get("accepted")) is not bool or type(r.get("seconds")) not in (int, float) or not math.isfinite(r["seconds"]) or r["seconds"] < 0:
            raise ValueError("Invalid acceptance/time measurement")
        u = usage(r.get("director_usage"))
        groups.setdefault((key, r["variant"]), []).append((u["total"], r["seconds"], r["accepted"]))
    results = []
    for key in sorted(contracts):
        pair = {v: groups.get((key, v), []) for v in ("baseline", "candidate")}
        item = {"case": key[0], "model": key[1], "environment": key[2]}
        for variant, data in pair.items():
            known = [v[0] for v in data if v[0] is not None]
            item[variant] = {"runs": len(data), "failed": sum(not v[2] for v in data),
                             "unknown_usage": len(data) - len(known),
                             "median_director_tokens": statistics.median(known) if known else None,
                             "median_seconds": statistics.median(v[1] for v in data) if data else None}
        a, b = item["baseline"], item["candidate"]
        eligible = all(x["runs"] >= 3 and not x["failed"] and not x["unknown_usage"] for x in (a, b))
        item["director_reduction_pct"] = (round(100 * (1 - b["median_director_tokens"] / a["median_director_tokens"]), 2)
                                             if eligible and a["median_director_tokens"] else None)
        item["pilot_target_met"] = bool(item["director_reduction_pct"] is not None and
                                         item["director_reduction_pct"] >= 50 and b["median_seconds"] <= a["median_seconds"])
        results.append(item)
    return {"comparisons": results, "claim": "small pilot only; no universal quality/token guarantee"}
