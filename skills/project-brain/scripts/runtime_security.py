"""Project secret references, host adapter preflight and safe outputs. Stdlib only."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import runtime_core as Core

ASSIGNMENT = re.compile(
    r"""(?i)(["']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|"""
    r"""session[_-]?token|secret[_-]?key|password|passwd|client[_-]?secret|private[_-]?key|"""
    r"""database[_-]?url|dsn|cookie|pb[_-]?relay[_-]?token)["']?\s*[:=]\s*["']?)([^\s"',;}]{8,})"""
)
TOKENS = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{24,}|"
    r"AIza[0-9A-Za-z_-]{35}|xox[baprs]-[0-9A-Za-z-]{10,}|"
    r"glpat-[0-9A-Za-z_-]{20,}|npm_[A-Za-z0-9]{30,}|pypi-[A-Za-z0-9_-]{30,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
)
PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)
ALIAS = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")


def sanitize(text):
    secret_vals = sorted(
        {value for name, value in os.environ.items() if Core.SECRET_ENV.search(name) and len(value) >= 8},
        key=len,
        reverse=True,
    )
    for value in secret_vals:
        text = text.replace(value, "[REDACTED]")
    text = PEM.sub("[REDACTED PRIVATE KEY]", text)
    text = TOKENS.sub("[REDACTED TOKEN]", text)
    text = re.sub(
        r"(?i)([?&](?:x-amz-signature|x-goog-signature|signature|sig|access_token|token|api_key|password|client_secret)=)([^&\s]+)",
        lambda m: m.group(1) + "[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+:)([^/\s@]{4,})@",
        lambda m: m.group(1) + "[REDACTED]@",
        text,
    )
    text = re.sub(
        r"(?i)(authorization:\s*(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=-]{8,}",
        lambda m: m.group(1) + "[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(--relay-token(?:=|\s+))[0-9a-f]{32}\b",
        lambda m: m.group(1) + "[REDACTED]",
        text,
    )
    return ASSIGNMENT.sub(
        lambda m: m.group(1) + "[REDACTED]" if not m.group(2).startswith(("<", "${", "[REDACTED")) else m.group(0),
        text,
    )


def require_clean(text, label):
    if sanitize(text) != text:
        raise ValueError("Sensitive content refused in " + sanitize(label) + "; values are never printed")


def require_public(text, label):
    require_clean(text, label)
    if (
        re.search(r"\b[A-Za-z]:[\\/]", text)
        or re.search(r"(?<![\w:])/(?:private/)?(?:home|Users|root|tmp|var|mnt|opt|etc)/", text)
        or re.search(r"(?<![\w:])/[a-z]/(?:Users|Windows|Program Files)/", text, re.I)
        or re.search(r"(?:\\\\|(?<![\w:])//)[A-Za-z0-9_.-]+[\\/][A-Za-z0-9_$.-]+", text)
    ):
        raise ValueError(
            "Host-private absolute path refused in " + label + "; use project-relative paths or a symbolic reference"
        )


def policy_path(B, root):
    return Core.public_path(root, B.BRAIN_DIR + "/security.json")


def policy(B, root):
    data = Core.read_json(policy_path(B, root))
    if data and (
        data.get("schema") != 1
        or not ALIAS.fullmatch(str(data.get("reference", "")))
        or not isinstance(data.get("note"), str)
        or not data["note"].strip()
    ):
        raise ValueError("Invalid project secret policy; confirm a symbolic reference with `security --ref`")
    if data:
        require_public(json.dumps(data), "project secret policy")
    return data


def configure(B, root, reference, note):
    if not ALIAS.fullmatch(reference) or reference == "pending" or not note.strip():
        raise ValueError("Choose `none` or a symbolic --ref and provide the actual user decision --note")
    require_public(note, "secret policy note")
    data = {"schema": 1, "reference": reference, "note": note.strip()}
    Core.write_atomic(policy_path(B, root), json.dumps(data, ensure_ascii=False, indent=2))
    return data


def policy_guard(B, root, task):
    ref = task.get("secrets", "none")
    if ref == "none":
        return
    if not ALIAS.fullmatch(ref) or ref == "pending":
        raise ValueError("Secrets must be `none` or an approved symbolic reference")
    configured = policy(B, root)
    if configured.get("reference") != ref:
        raise ValueError("SECRET_POLICY_PENDING: confirm this project's external reference once; secret-free work may continue")


def _check_unlinked_exec(exe_str, label):
    p = Path(exe_str)
    if (
        not p.is_absolute()
        or not p.is_file()
        or p.suffix.lower() in (".cmd", ".bat", ".ps1")
        or Core.is_link(p)
        or any(Core.is_link(parent) for parent in p.parents)
    ):
        raise ValueError(label)


def binding(B, root, task):
    policy_guard(B, root, task)
    filename = os.environ.get("PB_PRIVATE_BINDING", "")
    if not filename:
        raise ValueError("SECRET_ACCESS_PENDING: PB_PRIVATE_BINDING must resolve the approved external host adapter")
    path = Path(filename)
    if not path.is_absolute() or Core.is_link(path) or any(Core.is_link(p) for p in path.parents):
        raise ValueError("Private binding must be an absolute unlinked external file")
    project = Path(root).resolve()
    if project == path.resolve() or project in path.resolve().parents:
        raise ValueError("Private binding must stay outside the repository")
    data = Core.read_json(path)
    if data.get("project") != str(project) or data.get("reference") != task["secrets"]:
        raise ValueError("Private binding does not match this project/reference")
    capabilities = data.get("capabilities", [])
    if not isinstance(capabilities, list) or any(not isinstance(v, str) for v in capabilities):
        raise ValueError("Malformed host capability contract")
    if not isinstance(data.get("commands", {}), dict):
        raise ValueError("Host command bindings must be an object")
    if not {"credential_broker", "filesystem_isolation"}.issubset(set(capabilities)):
        raise ValueError("Host adapter must explicitly provide credential_broker and filesystem_isolation")
    return data


def binding_fingerprint(B, root, task):
    data = binding(B, root, task)
    files = {}
    argvs = list(data.get("commands", {}).values()) + [data.get("scanner_argv", [])]
    for argv in argvs:
        if not isinstance(argv, list):
            raise ValueError("Host adapter argv must be a list")
        for argument in argv:
            if not isinstance(argument, str):
                raise ValueError("Host adapter argv must contain text")
            path = Path(argument)
            if path.is_absolute() and path.is_file():
                if Core.is_link(path) or any(Core.is_link(p) for p in path.parents):
                    raise ValueError("Linked adapter/scanner paths refused")
                if path.stat().st_size > 32 * 1024 * 1024:
                    raise ValueError("Adapter/scanner binary needs a bounded launcher for freshness verification")
                files[str(path)] = Core.sha256_file(path)
    return Core.fingerprint([data, files])


def command(B, root, task, cmd):
    require_clean(cmd, "Verify command")
    argv = Core.command_argv(cmd)
    credential_option = re.compile(
        r"(?i)^--?(?:api[-_]?key|access[-_]?token|token|password|client[-_]?secret|secret|authorization)(?:=|$)"
    )
    if any(credential_option.search(value) for value in argv):
        raise ValueError("Credential options are not allowed in Verify argv; use the approved broker")
    if task.get("secrets", "none") == "none":
        return argv
    data = binding(B, root, task)
    prefix = data.get("commands", {}).get(cmd)
    if not isinstance(prefix, list) or not prefix or any(not isinstance(v, str) or not v or "\x00" in v for v in prefix):
        raise ValueError("Secret-dependent Verify command lacks an approved shell-free absolute host adapter")
    _check_unlinked_exec(prefix[0], "Secret-dependent Verify command lacks an approved shell-free absolute host adapter")
    if not data.get("scanner_argv"):
        raise ValueError("Secret-dependent checks require an approved output scanner")
    require_clean(" ".join(prefix), "adapter arguments")
    if any(credential_option.search(value) for value in prefix):
        raise ValueError("Host adapter arguments must not contain credential options")
    return list(prefix) + argv


def scan_output(B, root, task, raw):
    if task.get("secrets", "none") == "none":
        return
    argv = binding(B, root, task).get("scanner_argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(v, str) or not v or "\x00" in v for v in argv):
        raise ValueError("Output scanner requires an approved shell-free absolute argv")
    _check_unlinked_exec(argv[0], "Output scanner requires an approved shell-free absolute argv")
    try:
        env = Core.clean_env()
        with Core.ProcessTree() as tree, tempfile.TemporaryFile() as payload:
            payload.write(raw)
            payload.seek(0)
            proc = tree.spawn(
                argv,
                cwd=str(root),
                env=env,
                stdin=payload,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            result = proc.wait(timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Output scanner failed; output withheld")
    if result != 0:
        raise ValueError("Output scanner rejected sensitive/unknown output; output withheld")


def scan_artifacts(B, root, files):
    """Bounded staged/export scan. Never emits matched values or copies private files."""
    checked = 0
    for name in sorted(set(files)):
        path = Core.public_path(root, name)
        if not path.is_file():
            continue
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Artifact needs an approved large/binary scanner before export: " + name)
        raw = path.read_bytes()
        if b"\x00" in raw:
            raise ValueError("Binary artifact requires visual/private-data inspection before export: " + name)
        require_clean(raw.decode("utf-8", errors="replace"), "artifact " + name)
        checked += 1
    return checked


def scan_bytes(raw, label):
    """Scan UTF-8, UTF-16, or printable ASCII runs inside binary/NUL-containing bytes."""
    if b"\x00" not in raw:
        require_clean(raw.decode("utf-8", errors="replace"), label)
        return
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            require_clean(raw.decode("utf-16", errors="replace"), label)
        except UnicodeError:
            pass
    ascii_runs = b"\n".join(re.findall(rb"[\x20-\x7e]{8,}", raw))
    if ascii_runs:
        require_clean(ascii_runs.decode("ascii", errors="replace"), label)


def scan_staged(B, root, env=None, base=None):
    """Inspect the bytes and Git modes that will be committed, not a different working-tree copy."""
    kwargs = {
        "capture_output": True,
        "timeout": 20,
        "env": Core.clean_env(env if isinstance(env, dict) else None),
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    diff_cmd = ["git", "-C", str(root), "diff", "--cached", "--raw", "-z", "--diff-filter=ACMR"]
    if base:
        diff_cmd.append(base)
    raw_diff = subprocess.run(diff_cmd, **kwargs)
    if raw_diff.returncode != 0:
        raise ValueError("Staged scan requires Git")
    tokens = [t for t in raw_diff.stdout.split(b"\x00") if t]
    files = []
    idx = 0
    while idx < len(tokens):
        meta = tokens[idx].decode("utf-8", errors="replace")
        idx += 1
        if not meta.startswith(":") or idx >= len(tokens):
            continue
        parts = meta[1:].split()
        new_mode = parts[1] if len(parts) >= 2 else ""
        status = parts[4] if len(parts) >= 5 else ""
        if status.startswith(("R", "C")):
            idx += 1  # skip old path
            if idx >= len(tokens):
                break
        name = tokens[idx].decode("utf-8", errors="replace")
        idx += 1
        if new_mode == "120000":
            raise ValueError("Staged symlink (mode 120000) refused: " + name)
        files.append(name)
    for name in files:
        Core.public_path(root, name)
        size_res = subprocess.run(["git", "-C", str(root), "cat-file", "-s", ":" + name], **kwargs)
        size = size_res.stdout.decode("utf-8", errors="replace").strip() if size_res.returncode == 0 else ""
        if not size or not size.isdigit() or int(size) > 8 * 1024 * 1024:
            raise ValueError("Staged artifact requires an approved large/binary scanner: " + name)
        try:
            result = subprocess.run(["git", "-C", str(root), "show", ":" + name], **kwargs)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Staged security scan timed out on " + name) from exc
        if result.returncode:
            raise ValueError("Cannot inspect staged artifact: " + name)
        scan_bytes(result.stdout, "staged artifact " + name)
    return len(files)
