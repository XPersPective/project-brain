"""Project secret references, host adapter preflight and safe outputs. Stdlib only."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import runtime_verify as V

ASSIGNMENT = re.compile(
    r'''(?i)(["']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|client[_-]?secret|private[_-]?key)["']?\s*[:=]\s*["']?)([^\s"',;}]{8,})''')
TOKENS = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{24,})\b")
PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)
ALIAS = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")


def sanitize(text):
    for name, value in os.environ.items():
        if V.SECRET_ENV.search(name) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    text = PEM.sub("[REDACTED PRIVATE KEY]", text)
    text = TOKENS.sub("[REDACTED TOKEN]", text)
    text = re.sub(r"(?i)([?&](?:x-amz-signature|x-goog-signature|signature|sig|access_token|token)=)([^&\s]+)", lambda m: m.group(1) + "[REDACTED]", text)
    text = re.sub(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~-]{8,}", lambda m: m.group(1) + "[REDACTED]", text)
    return ASSIGNMENT.sub(lambda m: m.group(1) + "[REDACTED]" if not m.group(2).startswith(("<", "${", "[REDACTED")) else m.group(0), text)


def require_clean(text, label):
    if sanitize(text) != text:
        raise ValueError("Sensitive content refused in " + sanitize(label) + "; values are never printed")


def require_public(text, label):
    require_clean(text, label)
    if re.search(r"\b[A-Za-z]:[\\/]", text) or re.search(r"(?<![\w:])/(?:home|Users|root|tmp|var|mnt|opt|etc)/", text):
        raise ValueError("Host-private absolute path refused in " + label + "; use project-relative paths or a symbolic reference")


def policy_path(B, root):
    return V.public_path(root, B.BRAIN_DIR + "/security.json")


def policy(B, root):
    import runtime_protocol as P
    data = P.read_json(policy_path(B, root))
    if data and (data.get("schema") != 1 or not ALIAS.fullmatch(str(data.get("reference", "")))
                 or not isinstance(data.get("note"), str) or not data["note"].strip()):
        raise ValueError("Invalid project secret policy; confirm a symbolic reference with `security --ref`")
    if data:
        require_public(json.dumps(data), "project secret policy")
    return data


def configure(B, root, reference, note):
    if not ALIAS.fullmatch(reference) or reference == "pending" or not note.strip():
        raise ValueError("Choose `none` or a symbolic --ref and provide the actual user decision --note")
    require_public(note, "secret policy note")
    data = {"schema": 1, "reference": reference, "note": note.strip()}
    B.write_atomic(policy_path(B, root), json.dumps(data, ensure_ascii=False, indent=2))
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


def binding(B, root, task):
    policy_guard(B, root, task)
    filename = os.environ.get("PB_PRIVATE_BINDING", "")
    if not filename:
        raise ValueError("SECRET_ACCESS_PENDING: PB_PRIVATE_BINDING must resolve the approved external host adapter")
    path = Path(filename)
    if not path.is_absolute() or V.is_link(path) or any(V.is_link(p) for p in path.parents):
        raise ValueError("Private binding must be an absolute unlinked external file")
    project = Path(root).resolve()
    if project == path.resolve() or project in path.resolve().parents:
        raise ValueError("Private binding must stay outside the repository")
    import runtime_protocol as P
    data = P.read_json(path)
    if data.get("project") != str(project) or data.get("reference") != task["secrets"]:
        raise ValueError("Private binding does not match this project/reference")
    capabilities = data.get("capabilities", [])
    if not isinstance(capabilities, list) or any(not isinstance(v, str) for v in capabilities):
        raise ValueError("Malformed host capability contract")
    if not isinstance(data.get("commands", {}), dict):
        raise ValueError("Host command bindings must be an object")
    if not {"credential_broker", "filesystem_isolation"}.issubset(set(capabilities)):
        raise ValueError("Host adapter must explicitly provide credential_broker and filesystem_isolation")
    # These capabilities are an explicit trust contract with the approved host,
    # not a claim that a JSON boolean installs an OS security boundary.
    return data


def binding_fingerprint(B, root, task):
    import runtime_protocol as P
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
                if V.is_link(path) or any(V.is_link(p) for p in path.parents):
                    raise ValueError("Linked adapter/scanner paths refused")
                if path.stat().st_size > 32 * 1024 * 1024:
                    raise ValueError("Adapter/scanner binary needs a bounded launcher for freshness verification")
                files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return P.fingerprint([data, files])


def command(B, root, task, cmd):
    require_clean(cmd, "Verify command")
    argv = V.command_argv(cmd)
    credential_option = re.compile(r"(?i)^--?(?:api[-_]?key|access[-_]?token|token|password|client[-_]?secret|secret|authorization)(?:=|$)")
    if any(credential_option.search(value) for value in argv):
        raise ValueError("Credential options are not allowed in Verify argv; use the approved broker")
    if task.get("secrets", "none") == "none":
        return argv
    data = binding(B, root, task)
    prefix = data.get("commands", {}).get(cmd)
    if (not isinstance(prefix, list) or not prefix or any(not isinstance(v, str) or not v or "\x00" in v for v in prefix)
            or not Path(prefix[0]).is_absolute() or not Path(prefix[0]).is_file()
            or Path(prefix[0]).suffix.lower() in (".cmd", ".bat", ".ps1")):
        raise ValueError("Secret-dependent Verify command lacks an approved shell-free absolute host adapter")
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
    if (not isinstance(argv, list) or not argv or any(not isinstance(v, str) or not v or "\x00" in v for v in argv)
            or not Path(argv[0]).is_absolute() or Path(argv[0]).suffix.lower() in (".cmd", ".bat", ".ps1")):
        raise ValueError("Output scanner requires an approved shell-free absolute argv")
    try:
        env = {k: v for k, v in os.environ.items() if not V.SECRET_ENV.search(k)}
        with V.ProcessTree() as tree, __import__("tempfile").TemporaryFile() as payload:
            payload.write(raw)
            payload.seek(0)
            proc = tree.spawn(argv, cwd=str(root), env=env, stdin=payload,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = proc.wait(timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Output scanner failed; output withheld")
    if result != 0:
        raise ValueError("Output scanner rejected sensitive/unknown output; output withheld")


def scan_artifacts(B, root, files):
    """Bounded staged/export scan. Never emits matched values or copies private files."""
    checked = 0
    for name in sorted(set(files)):
        path = V.public_path(root, name)
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


def scan_staged(B, root):
    """Inspect the bytes that will be committed, not a different working-tree copy."""
    files = B.git_paths(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if files is None:
        raise ValueError("Staged scan requires Git")
    for name in files:
        V.public_path(root, name)  # Reject linked/private paths without reading them.
        size = B.git(root, "cat-file", "-s", ":" + name)
        if not size or not size.isdigit() or int(size) > 8 * 1024 * 1024:
            raise ValueError("Staged artifact requires an approved large/binary scanner: " + name)
        result = subprocess.run(["git", "-C", str(root), "show", ":" + name],
                                capture_output=True, timeout=20)
        if result.returncode:
            raise ValueError("Cannot inspect staged artifact: " + name)
        if b"\x00" in result.stdout:
            # Rendered screenshots/recordings already require typed visual evidence;
            # this text scan cannot assert that their pixels contain no private data.
            continue
        require_clean(result.stdout.decode("utf-8", errors="replace"), "staged artifact " + name)
    return len(files)
