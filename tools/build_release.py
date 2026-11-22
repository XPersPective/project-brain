#!/usr/bin/env python3
"""Reproducible release from the Git index, plus version/AST/cycle/CLI checks."""
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

SKILL_ENTRY_BUDGET = 4500


def run(root, *argv):
    result = subprocess.run(list(argv), cwd=str(root), capture_output=True, timeout=120)
    if result.returncode:
        raise ValueError("Release command failed: " + result.stderr.decode("utf-8", "replace")[:500])
    return result.stdout


def check_runtime_invariants(entries):
    # Parse EVERY tracked Python file under Python 3.8 grammar (runtime, tests, and tools).
    all_py = {name: content.decode("utf-8") for name, content in entries.items() if name.endswith(".py")}
    for name, src in sorted(all_py.items()):
        try:
            ast.parse(src, filename=name, feature_version=(3, 8))
        except SyntaxError as exc:
            raise ValueError(f"Python 3.8 syntax error in {name}: {exc}")

    scripts = {
        PurePosixPath(name).stem: src
        for name, src in all_py.items()
        if name.startswith("skills/project-brain/scripts/")
        and not PurePosixPath(name).name.startswith("test_")
    }
    graph = {}
    for mod, src in sorted(scripts.items()):
        tree = ast.parse(src, filename=mod + ".py", feature_version=(3, 8))
        top_nodes = set(tree.body)
        deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in scripts:
                        if node not in top_nodes:
                            raise ValueError(f"Non-top-level internal import in {mod}.py: {alias.name}")
                        deps.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module in scripts:
                if node not in top_nodes:
                    raise ValueError(f"Non-top-level internal import in {mod}.py: {node.module}")
                deps.add(node.module)
        graph[mod] = deps
    if graph.get("runtime_core"):
        raise ValueError(f"runtime_core.py must have zero internal imports: {sorted(graph['runtime_core'])}")
    visiting, visited = set(), set()

    def dfs(node, trail):
        visiting.add(node)
        for nxt in graph.get(node, ()):
            if nxt in visiting:
                raise ValueError("Circular runtime import: " + " -> ".join(trail + [nxt]))
            if nxt not in visited:
                dfs(nxt, trail + [nxt])
        visiting.remove(node)
        visited.add(node)

    for mod in sorted(graph):
        if mod not in visited:
            dfs(mod, [mod])


def check_versions(entries, version):
    for manifest in ("plugin.json", ".claude-plugin/plugin.json"):
        if manifest not in entries:
            raise ValueError(f"Missing manifest {manifest}")
        data = json.loads(entries[manifest].decode("utf-8"))
        if data.get("version") != version:
            raise ValueError(f"Manifest version differs in {manifest}")
        if manifest == "plugin.json":
            desc = data.get("extensions", {}).get("com.openai", {}).get("interface", {}).get("longDescription", "")
            if f"Project Brain {version}" not in desc:
                raise ValueError(f"plugin.json longDescription missing Project Brain {version}")
    checks = {
        "skills/project-brain/SKILL.md": (f"version: {version}", f"# Project Brain {version}"),
        "skills/project-brain/SCHEMAS.md": (f'skill_version: "{version}"',),
        "skills/project-brain/POOL.md": (f"(Project Brain {version})",),
        "README.md": (f"Current release: **{version}**",),
        "docs/PROJECT-OVERVIEW.md": (f"# Project Brain {version}",),
        "docs/VERIFICATION.md": (f"Project Brain {version}",),
        "site/index.html": (f"<span data-version>v{version}</span>",),
        "CHANGELOG.md": (f"## {version} ",),
    }
    for path, needles in checks.items():
        if path not in entries:
            raise ValueError(f"Missing release file {path}")
        text = entries[path].decode("utf-8")
        for needle in needles:
            if needle not in text:
                raise ValueError(f"Version mismatch in {path}: expected {needle!r}")
    skill_bytes = len(entries["skills/project-brain/SKILL.md"].replace(b"\r\n", b"\n"))
    if skill_bytes > SKILL_ENTRY_BUDGET:
        raise ValueError(f"SKILL.md exceeds byte budget: {skill_bytes} > {SKILL_ENTRY_BUDGET}")


def main():
    root = Path(__file__).resolve().parents[1]
    names = sorted(run(root, "git", "ls-files", "-z").decode("utf-8").split("\0"))
    entries = {}
    for name in filter(None, names):
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or name.startswith("dist/"):
            raise ValueError("Invalid tracked release path")
        if re.search(
            r"(^|/)(?:\.env(?:\.[^/]+)?|auth\.json|credentials?|secrets?|"
            r"service-account[^/]*|key\.properties|id_rsa|id_ed25519)(/|$)|"
            r"\.(?:jks|keystore|p8|p12|pfx|pem)$",
            name,
            re.I,
        ):
            raise ValueError("Private path cannot be packaged")
        entries[name] = run(root, "git", "show", ":" + name)
    if "plugin.json" not in entries:
        raise ValueError("Stage plugin.json before packaging")
    version = json.loads(entries["plugin.json"].decode("utf-8"))["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid release version")
    for manifest in ("plugin.json", ".claude-plugin/plugin.json", ".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json"):
        if manifest in entries:
            json.loads(entries[manifest].decode("utf-8"))
    required = (
        "plugin.json",
        ".claude-plugin/plugin.json",
        "skills/project-brain/SKILL.md",
        "skills/project-brain/WORKFLOW.md",
        "skills/project-brain/SCHEMAS.md",
        "skills/project-brain/PROTOCOL.md",
        "skills/project-brain/QUALITY.md",
        "skills/project-brain/REFERENCE.md",
        "skills/project-brain/POOL.md",
        "skills/project-brain/ORCHESTRATION.md",
        "skills/project-brain/RECOVERY.md",
        "skills/project-brain/RELAY.md",
        "skills/project-brain/references/director-contract.md",
        "skills/project-brain/scripts/brain.py",
        "skills/project-brain/scripts/migrate.py",
        "skills/project-brain/scripts/runtime_core.py",
        "skills/project-brain/scripts/runtime_scoring.py",
        "skills/project-brain/scripts/runtime_security.py",
        "skills/project-brain/scripts/runtime_actors.py",
        "skills/project-brain/scripts/runtime_executor_policy.py",
        "skills/project-brain/scripts/runtime_protocol.py",
        "skills/project-brain/scripts/runtime_verify.py",
        "skills/project-brain/scripts/runtime_context.py",
        "skills/project-brain/scripts/runtime_reports.py",
        "skills/project-brain/scripts/runtime_runs.py",
        "skills/project-brain/scripts/runtime_adopt.py",
        "skills/project-brain/scripts/runtime_agent_pool.py",
        "skills/project-brain/scripts/runtime_orchestration.py",
        "skills/project-brain/scripts/runtime_quota_recovery.py",
        "skills/project-brain/scripts/runtime_relay.py",
        "skills/project-brain/scripts/runtime_control.py",
        "skills/project-brain/scripts/runtime_session.py",
        "skills/project-brain/scripts/runtime_setup.py",
    )
    if any(name not in entries for name in required):
        missing_req = [name for name in required if name not in entries]
        raise ValueError("Stage all required source files before packaging: " + ", ".join(missing_req))
    check_versions(entries, version)
    check_runtime_invariants(entries)
    directory = root / "dist"
    if directory.is_symlink() or directory.resolve() != root / "dist":
        raise ValueError("Release directory must stay in the repository")
    directory.mkdir(exist_ok=True)
    output = directory / ("project-brain-" + version + ".zip")
    with tempfile.TemporaryDirectory(prefix="pb-package-") as temporary:
        staging = Path(temporary) / output.name
        with zipfile.ZipFile(str(staging), "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, content in entries.items():
                info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
        extracted = Path(temporary) / "extracted"
        with zipfile.ZipFile(str(staging)) as archive:
            if archive.testzip() is not None:
                raise ValueError("Package CRC failed")
            archive.extractall(str(extracted))
        observed = run(extracted, sys.executable, "-B", "skills/project-brain/scripts/brain.py", "--version").decode("utf-8").strip()
        if observed != "project-brain " + version + " (schema 4)":
            raise ValueError("Extracted runtime version differs")
        for subcmd in ("boot", "board", "watch", "validate", "runs", "setup", "policy", "quota", "relay"):
            run(extracted, sys.executable, "-B", "skills/project-brain/scripts/brain.py", subcmd, "--help")
        data = staging.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        tmp_zip = directory / (output.name + ".tmp")
        tmp_sha = directory / (output.with_suffix(".sha256").name + ".tmp")
        tmp_zip.write_bytes(data)
        tmp_zip.replace(output)
        tmp_sha.write_text(checksum + "  " + output.name + "\n", encoding="utf-8")
        tmp_sha.replace(output.with_suffix(".sha256"))
    print(json.dumps({"version": version, "files": len(entries), "sha256": checksum,
                      "package": str(output), "smoke": "extracted version, AST, cycles, budget and CLI help passed"}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print("FAIL " + str(error), file=sys.stderr)
        sys.exit(2)
