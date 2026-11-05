"""One batched new-session setup screen with a 5-minute default; stdlib, Python 3.8+.

`setup ask` prints the 7-item Turkish setup screen (with ✅/⬜ options vertically under
each item), writes the pre-filled HTML widget to `.project-brain/.cache/setup-form.html`,
and records when setup was asked. When a relay director or a quota-recovery wait is
active in the background, `setup ask` shows that status and 3 Turkish action choices
instead of re-asking the 7 setup items. Explicit answers are saved with `policy --file
--confirm`. If the user selects "Kullanıcı seçimi" without details, the director asks
a single follow-up question for the missing route/model/category; without a reply in
5 minutes, `setup wait` + `setup defaults` saves and confirms the shown defaults.
A relay successor or worker inherits confirmed settings and is never asked.
"""
import copy
import json
import os
from pathlib import Path
import time

import runtime_executor_policy as E
import runtime_verify as V

TIMEOUT = 300
SLICE = 60
BUILTIN = {
    "schema": 1,
    "execution": {"source": "native"},
    "scheduling": {"mode": "parallel", "max_parallel": 32, "auto": True},
    "speed": "balanced",
    "quota_recovery": {"enabled": True, "threshold_percent": 10},
    "relay": {"enabled": True, "threshold_percent": 10, "director_category": "same"},
}


def _path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/.cache/setup.json")


def _form_path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/.cache/setup-form.html")


def defaults(B, root):
    """Saved confirmed policy when one exists, else the 7-item default choice."""
    saved = E.load(B, root)
    value = copy.deepcopy(saved) if saved and E.last_confirmed(B, root) else copy.deepcopy(BUILTIN)
    value.pop("note", None)
    value.pop("origin", None)
    # Silence in a later session must not erase an explicit CAP-only restriction.
    if saved and E.last_confirmed(B, root) and saved.get("origin") != "defaults":
        if any(value.get(role, value["execution"])["source"].startswith("cap-")
               for role in ("execution", "review")):
            value.setdefault("cap_fallback", "wait")
    value.setdefault("speed", "balanced")
    value.setdefault("relay", {"enabled": True, "threshold_percent": 10, "director_category": "same"})
    return value


def _detail(selector):
    if selector.get("categories"):
        return ", ".join(selector["categories"])
    if selector.get("models"):
        return ", ".join(m.get("routeId", m.get("host", "")) + "/" + m.get("modelId", m.get("model", ""))
                         for m in selector["models"])
    return ""


def _relay_detail(relay):
    if relay.get("candidates"):
        return ", ".join(c["route"] + ("/" + c["model"] if c.get("model") else "") for c in relay["candidates"])
    cat = relay.get("director_category", "same")
    return "" if cat == "same" else cat


def _form_state(value):
    s = value["scheduling"]
    q = value["quota_recovery"]
    relay = value.get("relay") or {"enabled": True, "threshold_percent": 10, "director_category": "same"}
    src = value["execution"]["source"]
    src_idx = {"native": 0, "native-cheap": 0, "solo": 0, "mixed": 1, "cap-catalog": 2}.get(src, 3)
    r_detail = _relay_detail(relay)
    return {
        "cap_fallback": value.get("cap_fallback", "wait"),
        1: {"i": 0 if s["mode"] == "parallel" else 1, "note": "", "pct": 10},
        2: {"i": 1 if src == "solo" else 0, "note": "", "pct": 10},
        3: {"i": src_idx, "note": _detail(value["execution"]), "pct": 10},
        4: {"i": 1 if value.get("speed") == "turbo" else 0, "note": "", "pct": 10},
        5: {"i": 0 if q["enabled"] else 1, "note": "", "pct": q["threshold_percent"]},
        6: {"i": 0 if relay.get("enabled") else 1, "note": "", "pct": relay.get("threshold_percent", 10)},
        7: {"i": 1 if r_detail else 0, "note": r_detail, "pct": 10},
    }


def write_form(B, root, value):
    template_path = Path(__file__).resolve().parents[1] / "assets" / "setup-form.html"
    if not template_path.is_file():
        return None
    html = template_path.read_text(encoding="utf-8")
    payload = json.dumps(_form_state(value), ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = html.replace("const INIT = null; // PB_INIT", "const INIT = " + payload + ";")
    out = _form_path(B, root)
    B.write_atomic(out, html)
    return str(out)


def questions(value):
    s, q = value["scheduling"], value["quota_recovery"]
    relay = value.get("relay") or {"enabled": True, "threshold_percent": 10, "director_category": "same"}
    src = value["execution"]["source"]
    parallel_label = ("Paralel" if s["mode"] != "parallel" or s.get("auto") or s["max_parallel"] == 32
                      else "Paralel (en fazla %d)" % s["max_parallel"])
    detail = _detail(value["execution"])
    src_idx = {"native": 0, "native-cheap": 0, "solo": 0, "mixed": 1, "cap-catalog": 2}.get(src, 3)
    src_opts = [
        "Yerleşik ajanlar",
        "Yerleşik ajanlar + CLI Ajan Havuzu" + (": " + detail if src_idx == 1 and detail else ""),
        "Yalnız CLI Ajan Havuzu",
        "Kullanıcı seçimi" + (": " + detail if src_idx == 3 and detail else ""),
    ]
    r_detail = _relay_detail(relay)
    r_idx = 1 if r_detail else 0
    r_opts = [
        "Aynı havuzdan eşdeğer aday",
        "Kullanıcı seçimi" + (": " + r_detail if r_detail else ""),
    ]
    return [
        ("Çalışma düzeni", [parallel_label, "Sıralı"], 0 if s["mode"] == "parallel" else 1),
        ("Ajan kullanımı", ["Çoklu ajan", "Sadece yönetici"], 1 if src == "solo" else 0),
        ("Ajan kaynağı", src_opts, src_idx),
        ("Çalışma hızı", ["Dengeli: yüksek kalite, düşük toplam maliyet",
                          "Turbo: sınırları zorlar, en hızlı bitirir"],
         1 if value.get("speed") == "turbo" else 0),
        ("Kota yenilenmesini bekleme", ["Açık, %%%d" % q["threshold_percent"], "Kapalı"],
         0 if q["enabled"] else 1),
        ("Yönetici devri", ["Açık, %%%d" % relay.get("threshold_percent", 10), "Kapalı"],
         0 if relay.get("enabled") else 1),
        ("Devralacak yönetici", r_opts, r_idx),
    ]


def render(value):
    lines = ["✅ varsayılan seçimdir; yalnız değiştirmek istediğiniz maddeleri numarasıyla yazın:"]
    for number, (title, opts, selected) in enumerate(questions(value), 1):
        lines.append("%d. %s" % (number, title))
        for idx, opt in enumerate(opts):
            mark = "✅" if idx == selected else "⬜"
            lines.append("   %s %s" % (mark, opt))
        lines.append("   Varsayılan: " + opts[selected])
    lines.append('Örnek yanıt: "3: yerleşik + havuz, yalnız medium; 4: turbo" veya "varsayılanlarla devam". '
                 "5 dakika yanıt gelmezse gösterilen varsayılanlarla devam ederim.")
    return lines


def needs_clarification(answer):
    """True when the user chose 'Kullanıcı seçimi' or a pool option without naming the pool/model."""
    if not isinstance(answer, str) or not answer.strip():
        return False
    low = answer.lower()
    if "ayrıntı sorulsun" in low:
        return True
    for part in low.split(";"):
        part = part.strip()
        if (part.startswith("3:") or part.startswith("7:")) and "kullanıcı seçimi" in part:
            _, _, tail = part.partition("kullanıcı seçimi")
            if not tail.strip(" ,:-"):
                return True
    return False


def pending(B, root):
    path = _path(B, root)
    if not path.is_file():
        return False
    try:
        record = _record(B, root)
    except ValueError as error:
        if "SETUP_STALE" in str(error):
            return False
        raise
    return record.get("mode") == "clarification" and record.get("status") != "resolved"


def clarify(B, root, answer, value=None, now=None):
    """Host translates resolved answers into policy; unresolved details stay gated."""
    if not needs_clarification(answer):
        raise ValueError("No missing user selection in answer")
    if value is None and any(part.strip() and not needs_clarification(part)
                             for part in answer.split(";")):
        raise ValueError("SETUP_RESOLVED_FILE_REQUIRED: preserve other explicit answers with --file")
    with B.checkout_lock(root):
        record = _record(B, root)
        if record.get("mode") not in ("setup", "clarification"):
            raise ValueError("Background operation owns setup; resolve it first")
        if pending(B, root):
            return {"status": "CLARIFICATION_REQUIRED", "lines": record["lines"],
                    "timeout_seconds": TIMEOUT, "next": "setup wait"}
        chosen = E._validate(value if value is not None else record["defaults"])
        # The host must retain resolved answers. Only unresolved fields use the
        # previously shown defaults; never invent a category or model identity.
        parts = answer.lower().split(";")
        missing = [n for n in (3, 7) if any(p.strip().startswith(str(n) + ":") and
                   needs_clarification(p) for p in parts)]
        if not missing:
            raise ValueError("Specify missing selection as item 3 or 7")
        for number, key in ((3, "execution"), (7, "relay")):
            if number in missing:
                chosen[key] = copy.deepcopy(record["defaults"][key])
                if number == 3 and "review" not in (value or {}):
                    chosen["review"] = copy.deepcopy(chosen[key])
        if any(chosen[role]["source"].startswith("cap-") for role in ("execution", "review")):
            chosen.setdefault("cap_fallback", "wait")
        lines = []
        if 3 in missing:
            lines.append("3. Hangi ajan kaynağı, havuz/kategori veya tam hesap/model kullanılacak?")
        if 7 in missing:
            lines.append("7. Devralacak yönetici için hangi havuz veya tam hesap/model kullanılacak?")
        lines.append("5 dakika yanıt gelmezse yalnız eksik seçimlerde gösterilen varsayılanlar uygulanır.")
        record.update(mode="clarification", asked_at=time.time() if now is None else now,
                      defaults=chosen, lines=lines)
        B.write_atomic(_path(B, root), json.dumps(record, ensure_ascii=False, indent=2))
    return {"status": "CLARIFICATION_REQUIRED", "timeout_seconds": TIMEOUT, "lines": lines,
            "next": "Resolve via policy --file --confirm; otherwise setup wait then setup defaults"}


def recover_cap(B, root, role="exec"):
    """Authorize a new native job, never resubmit or settle an uncertain CAP job."""
    with B.checkout_lock(root):
        value = E.require_confirmed(B, root)
        result = E.cap_unavailable(value, role)
        if result["action"] == "CONTINUE_NATIVE" and value[E._role(role)]["source"] != "mixed":
            chosen = copy.deepcopy(value)
            chosen[E._role(role)] = {"source": "native"}
            E.save(B, root, chosen, "Previously authorized native fallback after CAP unavailability")
            E.confirm(B, root, "Native fallback; director must relay notification before new dispatch")
        result["next"] = "Notify user; read back any uncertain CAP job before starting replacement work"
        return result


def _render_relay_active(state, line):
    d = state["director"]
    who = d["route"] + ("/" + d["model"] if d.get("model") else "")
    badge = ("🟡 Arka planda yönetici devri durduruluyor" if state["status"] == "STOPPING"
             else "🔴 Arka planda yönetici devri adayları tükendi" if state["status"] == "EXHAUSTED"
             else "🟢 Arka planda yönetici devri aktif")
    return [
        badge,
        line,
        "Son devralan: %s (nesil %d)" % (who, state["generation"]),
        "Ne yapılmasını istersiniz?",
        "   ✅ 1. Devam etsin (ben izlerim)",
        "   ⬜ 2. Durdur: işi kaydedip en geç 2 dakika içinde çekilsin",
        "   ⬜ 3. Durdur ve ben devralayım",
        "5 dakika yanıt gelmezse 1. seçenek uygulanır ve arka plandaki iş kesilmez.",
    ]


def _render_quota_waiting(recovery):
    return [
        "🟡 Arka planda kota yenilenmesini bekleyen yönetici var",
        "Durum: %s | Kayıt: %s | Yenilenme: %s" % (
            recovery["status"], recovery.get("checkpoint") or "?", recovery.get("wake_at") or "?"),
        "Ne yapılmasını istersiniz?",
        "   ✅ 1. Beklesin, kota yenilenince kendisi devam etsin",
        "   ⬜ 2. Beklemeyi iptal et, ben devralayım (önce bekleyen zamanlayıcı iptal edilir)",
        "   ⬜ 3. Tamamen durdur",
        "5 dakika yanıt gelmezse 1. seçenek uygulanır ve bekleme bozulmaz.",
    ]


def ask(B, root, now=None):
    import runtime_quota_recovery as Q
    import runtime_relay as RL
    if RL.authorized(B, root) or RL.stopping_holder(B, root):
        return {"status": "RELAY_SUCCESSOR", "lines": ["Çalışma ayarları önceki yöneticiden devralındı; yeniden soru sorulmaz."]}
    session = E._session(B, root) or E.begin_session(B, root)
    previous = None
    if _path(B, root).is_file():
        try:
            previous = _record(B, root)
        except ValueError as error:
            if "SETUP_STALE" not in str(error):
                raise
        else:
            if previous.get("mode") == "clarification" and previous.get("status") != "resolved":
                return {"status": "CLARIFICATION_REQUIRED", "lines": previous["lines"], "timeout_seconds": TIMEOUT}
    now = time.time() if now is None else now
    line = RL.boot_line(B, root)
    state = None
    try:
        state = RL.read(B, root)
    except ValueError:
        state = None
    if state and state.get("status") in ("ACTIVE", "HANDOFF_PENDING", "STOPPING", "EXHAUSTED"):
        B.write_atomic(_path(B, root), json.dumps(
            {"schema": 1, "nonce": session["nonce"], "asked_at": now, "mode": "relay_active", "defaults": defaults(B, root)}, indent=2))
        return {"status": "RELAY_ACTIVE", "timeout_seconds": TIMEOUT, "lines": _render_relay_active(state, line or "")}
    recovery = Q.status(B, root)
    if recovery.get("status") in ("PREPARED", "ARMED"):
        B.write_atomic(_path(B, root), json.dumps(
            {"schema": 1, "nonce": session["nonce"], "asked_at": now, "mode": "quota_waiting", "defaults": defaults(B, root)}, indent=2))
        return {"status": "QUOTA_WAITING", "timeout_seconds": TIMEOUT, "lines": _render_quota_waiting(recovery)}
    if previous and previous.get("mode") == "setup" and previous.get("status") != "resolved":
        return {"status": "ASKED", "timeout_seconds": TIMEOUT, "lines": render(previous["defaults"]),
                "form_path": str(_form_path(B, root))}
    value = defaults(B, root)
    form = write_form(B, root, value)
    B.write_atomic(_path(B, root), json.dumps({"schema": 1, "nonce": session["nonce"], "asked_at": now, "mode": "setup", "defaults": value}, indent=2))
    result = {"status": "ASKED", "timeout_seconds": TIMEOUT, "lines": render(value)}
    if form:
        result["form_path"] = form
    return result


def _record(B, root):
    path = _path(B, root)
    if not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("SETUP_NOT_ASKED: run `setup ask` first")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("asked_at"), (int, float)):
        raise ValueError("Malformed setup record; run `setup ask` again")
    session = E._session(B, root)
    if value.get("nonce") != (session or {}).get("nonce"):
        raise ValueError("SETUP_STALE: run setup ask in the current session")
    return value


def wait(B, root, now=None, sleep=time.sleep):
    """Sleeps at most one slice; returns the seconds left before defaults apply."""
    record = _record(B, root)
    now = time.time() if now is None else now
    left = max(0, TIMEOUT - (now - record["asked_at"]))
    if left > 0:
        sleep(min(SLICE, left))
        left = max(0, left - SLICE)
    return {"status": "TIMEOUT_REACHED" if left <= 0 else "WAITING", "seconds_left": int(left),
            "next": "setup defaults" if left <= 0 else "check for a user reply, then setup wait again"}


def apply_defaults(B, root, accepted=False, now=None):
    with B.checkout_lock(root):
        return _apply_defaults_locked(B, root, accepted, now)


def _apply_defaults_locked(B, root, accepted=False, now=None):
    record = _record(B, root)
    now = time.time() if now is None else now
    if not accepted and now - record["asked_at"] < TIMEOUT:
        raise ValueError("SETUP_WAIT: %d seconds remain before defaults apply; use --accepted only if the user said so"
                         % int(TIMEOUT - (now - record["asked_at"])))
    if record.get("mode") in ("relay_active", "quota_waiting"):
        return {"status": "CONTINUE_BACKGROUND", "mode": record["mode"],
                "note": "No reply within 5 minutes; background operation continues untouched"}
    if E.load(B, root) is not None and E.confirmed(B, root) and not pending(B, root):
        return {"status": "ALREADY_CONFIRMED", "policy": E.summary(B, root)}
    note = "User accepted the shown defaults" if accepted else "Defaults after 5-minute setup timeout (no reply)"
    chosen = copy.deepcopy(record["defaults"])
    chosen["origin"] = "user" if accepted else "defaults"
    E.save(B, root, chosen, note)
    E.confirm(B, root, note)
    record["status"] = "resolved"
    B.write_atomic(_path(B, root), json.dumps(record, ensure_ascii=False, indent=2))
    return {"status": "DEFAULTS_CONFIRMED", "note": note, "policy": E.summary(B, root)}


def add_parser(sub):
    p = sub.add_parser("setup", help="One batched new-session setup screen with a 5-minute default")
    p.add_argument("action", choices=("ask", "wait", "defaults", "clarify", "recover-cap"))
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--accepted", action="store_true")
    p.add_argument("--answer", help="Submitted form answer with unresolved user selections")
    p.add_argument("--file", help="Project-relative policy preserving the resolved answers")
    p.add_argument("--role", choices=("exec", "rev"), default="exec")


def command(B, args):
    import runtime_relay as RL
    root = Path(args.root).resolve()
    director_recovery = args.action == "recover-cap" and RL.authorized(B, root)
    if os.environ.get("CLI_AGENT_POOL_WORKER") and not director_recovery:
        if args.action == "ask":
            return {"status": "INHERITED", "lines": ["Yardımcılar çalışma ayarlarını devralır; yeniden soru sorulmaz."]}
        raise ValueError("Workers inherit settings; they never answer setup questions")
    if not B.brain_exists(root):
        raise ValueError("Initialize Brain before session setup")
    if args.action == "ask":
        return ask(B, root)
    if args.action == "wait":
        return wait(B, root)
    if args.action == "clarify":
        value = None
        if args.file:
            value, _ = E._read(V.public_path(root, args.file))
        return clarify(B, root, args.answer, value)
    if args.action == "recover-cap":
        return recover_cap(B, root, args.role)
    return apply_defaults(B, root, accepted=args.accepted)
