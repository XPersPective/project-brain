"""Private, worktree-shared durable run ledger. No model calls or automatic replay."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

import runtime_agents as A
import runtime_security as S
import runtime_verify as V

SCHEMA = 1
ACTIVE = ("PREPARED", "SUBMITTING", "RUNNING", "CANCEL_REQUESTED", "UNKNOWN")
TRANSITIONS = {
    "PREPARED": ("SUBMITTING", "CANCELLED"),
    "SUBMITTING": ("RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"),
    "RUNNING": ("SUCCEEDED", "FAILED", "CANCEL_REQUESTED", "CANCELLED", "UNKNOWN"),
    "CANCEL_REQUESTED": ("SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"),
    "UNKNOWN": ("RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "CANCEL_REQUESTED"),
    "SUCCEEDED": (), "FAILED": (), "CANCELLED": (),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(B, root):
    root = Path(root).resolve()
    common = B.git(root, "rev-parse", "--git-common-dir")
    if not common:
        raise ValueError("Orchestration requires a Git repository")
    path = Path(common)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    return path


def private(path):
    path = Path(path).absolute()
    if any(V.is_link(p) for p in [path] + list(path.parents)):
        raise ValueError("Linked orchestration state refused")
    return path


def directory(B, root, create=True):
    common = canonical(B, root)
    key = hashlib.sha256(os.path.normcase(str(common)).encode("utf-8")).hexdigest()[:24]
    path = private(A.registry_path().parent / "orchestration" / key)
    project = Path(root).resolve()
    if project == path or project in path.parents:
        raise ValueError("Orchestration ledger must be outside the repository")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def peek(B, root):
    """Boot readback is read-only: no database, migration or directory creation."""
    if not (A.registry_path().parent / "orchestration").exists():
        return []
    if not B.git(root, "rev-parse", "--git-common-dir"):
        return []
    path = private(directory(B, root, create=False) / "runs.sqlite3")
    if not path.is_file():
        return []
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
            raise ValueError("Unsupported orchestration schema; preserve and upgrade")
        return [dict(zip(("run", "task", "kind", "state", "verification", "integration"), row))
                for row in db.execute("SELECT id,task,kind,state,verification,integration FROM runs WHERE state IN "
                                      "('PREPARED','SUBMITTING','RUNNING','CANCEL_REQUESTED','UNKNOWN') OR "
                                      "(state='SUCCEEDED' AND integration!='REJECTED' AND (verification!='PASS' OR integration='PENDING')) "
                                      "ORDER BY created LIMIT 8")]
    finally:
        db.close()


def implementation_strength(B, root, tid, actor):
    """Read immutable execution selection for this candidate or integrated task."""
    if not (A.registry_path().parent / "orchestration").exists() or not B.git(root, "rev-parse", "--git-common-dir"):
        return None
    path = directory(B, root, create=False) / "runs.sqlite3"
    if not path.exists():
        return None
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        for rid, spec, integration in db.execute("SELECT id,spec,integration FROM runs WHERE task=? AND kind='EXECUTE' AND state='SUCCEEDED' ORDER BY created DESC", (tid,)):
            if not Path(root).name.startswith(rid + "-") and integration != "MERGED":
                continue
            for data, in db.execute("SELECT data FROM events WHERE run=? ORDER BY seq", (rid,)):
                value = json.loads(data)
                if value.get("actor") == actor:
                    return {"L": "low", "M": "medium", "H": "high"}[value["tier"]]
        return None
    finally:
        db.close()


class Ledger:
    def __init__(self, path):
        self.path = private(path)
        for suffix in ("-journal", "-wal", "-shm"):
            private(str(self.path) + suffix)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA synchronous=FULL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA):
            self.db.close()
            raise ValueError("Unsupported orchestration schema; preserve database")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, task TEXT NOT NULL, kind TEXT NOT NULL,
          state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
          spec TEXT NOT NULL, backend_id TEXT, report TEXT,
          verification TEXT NOT NULL DEFAULT 'PENDING', integration TEXT NOT NULL,
          output TEXT, created TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT NOT NULL REFERENCES runs(id),
          event TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests (run TEXT PRIMARY KEY REFERENCES runs(id), payload TEXT NOT NULL);
        """)
        self.db.execute("PRAGMA user_version=1")

    def close(self):
        self.db.close()

    def backup(self, destination):
        destination = private(destination)
        if destination.exists():
            raise ValueError("Backup destination already exists; never overwrite")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(destination), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        # SQLite backup includes a consistent snapshot even while another process
        # owns a transaction; never copy a live database file with shutil.
        target = sqlite3.connect(str(destination))
        try:
            self.db.backup(target)
        finally:
            target.close()
        return destination

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def event(self, rid, event, data):
        self.db.execute("INSERT INTO events(run,event,data,created) VALUES(?,?,?,?)",
                        (rid, event, json.dumps(data, ensure_ascii=False), now()))

    def get(self, rid):
        row = self.db.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise ValueError("Unknown run")
        value = dict(row)
        value["spec"] = json.loads(value["spec"])
        value["report"] = json.loads(value["report"]) if value["report"] else None
        return value

    def all(self):
        return [self.get(r[0]) for r in self.db.execute("SELECT id FROM runs ORDER BY created,id")]

    def select(self, where, params=()):
        return [self.get(r[0]) for r in self.db.execute("SELECT id FROM runs WHERE " + where + " ORDER BY created,id", params)]

    def configure(self, schedule, cap):
        if schedule not in ("serial", "parallel") or type(cap) is not int or not 1 <= cap <= 32:
            raise ValueError("Invalid schedule/capacity")
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO settings VALUES('policy',?)",
                            (json.dumps({"schedule": schedule, "cap": 1 if schedule == "serial" else cap}),))

    def origin(self, root):
        with self.transaction():
            self.db.execute("INSERT OR IGNORE INTO settings VALUES('origin',?)", (str(Path(root).resolve()),))
            return Path(self.db.execute("SELECT value FROM settings WHERE key='origin'").fetchone()[0])

    def policy(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='policy'").fetchone()
        return json.loads(row[0]) if row else {"schedule": "serial", "cap": 1}

    def prepare(self, spec):
        required = ("task", "kind", "backend", "areas", "resources", "contract", "source", "base", "workspace")
        if any(k not in spec for k in required) or spec["kind"] not in ("EXECUTE", "REVIEW"):
            raise ValueError("Invalid immutable run specification")
        if spec["backend"] not in ("pool", "native"):
            raise ValueError("Only pool/native worker runs are supported")
        if any(not isinstance(spec[k], list) or any(not isinstance(v, str) for v in spec[k]) for k in ("areas", "resources")):
            raise ValueError("Areas/resources must be lists of strings")
        S.require_clean(json.dumps(spec, ensure_ascii=False), "run specification")
        rid = "run-" + uuid.uuid4().hex
        spec = dict(spec, idempotencyKey="pb-" + rid)
        with self.transaction():
            held = self.select("state IN ('PREPARED','SUBMITTING','RUNNING','CANCEL_REQUESTED','UNKNOWN') OR "
                               "(kind='EXECUTE' AND state='SUCCEEDED' AND integration NOT IN ('MERGED','REJECTED'))")
            # Completed writes reserve their scope until integrated; process capacity
            # counts only active jobs. UNKNOWN always reserves both.
            if sum(r["state"] in ACTIVE for r in held) >= self.policy()["cap"]:
                raise ValueError("CAPACITY: active jobs must drain before dispatch")
            for r in held:
                if spec["kind"] == "EXECUTE" and r["kind"] == "EXECUTE":
                    if r["task"] == spec["task"] or conflict(spec["areas"], r["spec"]["areas"]):
                        raise ValueError("OWNERSHIP: conflicting writer " + r["id"])
                if set(spec["resources"]) & set(r["spec"]["resources"]):
                    raise ValueError("RESOURCE: already reserved")
            stamp = now()
            self.db.execute("INSERT INTO runs(id,task,kind,state,spec,integration,created,updated) VALUES(?,?,?,'PREPARED',?,?,?,?)",
                            (rid, spec["task"], spec["kind"], json.dumps(spec, ensure_ascii=False),
                             "PENDING" if spec["kind"] == "EXECUTE" else "NOT_APPLICABLE", stamp, stamp))
            self.event(rid, "PREPARED", {})
        return self.get(rid)

    def transition(self, rid, state, version, backend_id=None, report=None, observation=None):
        from runtime_reports import validate
        if report is not None:
            validate(report)
        with self.transaction():
            r = self.get(rid)
            if r["version"] != version:
                raise ValueError("STALE_RUN: reread before mutation")
            if state != r["state"] and state not in TRANSITIONS[r["state"]]:
                raise ValueError("Invalid process transition")
            if r["state"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                if state == r["state"] and (report is None or report == r["report"]):
                    return r
                raise ValueError("Terminal run observations are immutable")
            if state == "SUCCEEDED" and report is None and r["report"] is None:
                raise ValueError("Successful run needs a structured report")
            if backend_id and r["backend_id"] and backend_id != r["backend_id"]:
                raise ValueError("Backend identity is immutable")
            self.db.execute("UPDATE runs SET state=?,version=version+1,backend_id=?,report=?,updated=? WHERE id=?",
                            (state, backend_id or r["backend_id"], json.dumps(report, ensure_ascii=False) if report is not None else
                             json.dumps(r["report"], ensure_ascii=False) if r["report"] is not None else None, now(), rid))
            self.event(rid, state, dict(observation or {}, previous=r["state"]))
        return self.get(rid)

    def annotate(self, rid, event, **values):
        allowed = {"verification", "integration", "output"}
        if not values or set(values) - allowed:
            raise ValueError("Invalid annotation")
        if ("verification" in values and values["verification"] not in ("PENDING", "PASS", "FAIL", "STALE") or
                "integration" in values and values["integration"] not in ("NOT_APPLICABLE", "PENDING", "MERGED", "REJECTED")):
            raise ValueError("Invalid verification/integration state")
        with self.transaction():
            self.get(rid)
            for key, value in values.items():
                self.db.execute("UPDATE runs SET " + key + "=?,version=version+1,updated=? WHERE id=?", (value, now(), rid))
            self.event(rid, event, values)

    def events(self, after=0, limit=20):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid event cursor/page size")
        return [dict(r) for r in self.db.execute("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (after, limit))]


def conflict(left, right):
    """Conservative glob-prefix overlap, including not-yet-created files."""
    if not left or not right:
        return True
    def prefix(value):
        value = value.replace("\\", "/")
        value = value[2:] if value.startswith("./") else value
        return re.split(r"[*?\[]", value.lower(), maxsplit=1)[0].rstrip("/")
    for a in left:
        for b in right:
            x, y = prefix(a), prefix(b)
            if not x or not y or x == y or x.startswith(y + "/") or y.startswith(x + "/"):
                return True
            if (any(c in a for c in "*?[") and y.startswith(x) or
                    any(c in b for c in "*?[") and x.startswith(y)):
                return True
    return False


def ready(tasks, completed, held):
    """Pure ready-set projection; no virtual future completion authorizes work."""
    ids = {t["id"] for t in tasks} | set(completed)
    byid = {t["id"]: t for t in tasks}
    visiting, seen = set(), set()
    def visit(tid):
        if tid in visiting:
            raise ValueError("Dependency cycle: " + tid)
        if tid in seen or tid not in byid:
            return
        visiting.add(tid)
        for dep in byid[tid].get("deps", []):
            if dep not in ids:
                raise ValueError("Unknown dependency: " + dep)
            visit(dep)
        visiting.remove(tid)
        seen.add(tid)
    for tid in byid:
        visit(tid)
    return [t["id"] for t in sorted(tasks, key=lambda t: (t.get("priority", "P2"), t["id"]))
            if t["status"] == "READY" and t["id"] not in held and all(d in completed for d in t.get("deps", []))]
