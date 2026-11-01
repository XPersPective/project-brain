#!/usr/bin/env python3
"""Reproducible release from the Git index, plus an extracted CLI smoke check."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile


def run(root, *argv):
    result = subprocess.run(list(argv), cwd=str(root), capture_output=True, timeout=120)
    if result.returncode:
        raise ValueError("Release command failed: " + result.stderr.decode("utf-8", "replace")[:500])
    return result.stdout


def main():
    root = Path(__file__).resolve().parents[1]
    names = sorted(run(root, "git", "ls-files", "-z").decode("utf-8").split("\0"))
    entries = {}
    for name in filter(None, names):
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or name.startswith("dist/"):
            raise ValueError("Invalid tracked release path")
        if re.search(r"(^|/)(\.env(?:\.|$)|auth\.json$|credentials?(/|$)|secrets?(/|$))|\.(pem|p12|pfx|keystore)$", name, re.I):
            raise ValueError("Private path cannot be packaged")
        entries[name] = run(root, "git", "show", ":" + name)
    version = json.loads(entries["plugin.json"].decode("utf-8"))["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid release version")
    for name in (".claude-plugin/plugin.json",):
        if json.loads(entries[name].decode("utf-8"))["version"] != version:
            raise ValueError("Manifest versions differ")
    required = ("skills/project-brain/scripts/brain.py", "skills/project-brain/ORCHESTRATION.md",
                "skills/project-brain/WORKFLOW.md", "skills/project-brain/scripts/runtime_runs.py")
    if any(name not in entries for name in required):
        raise ValueError("Stage all required source files before packaging")
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
        run(extracted, sys.executable, "-B", "skills/project-brain/scripts/brain.py", "runs", "--help")
        data = staging.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        output.write_bytes(data)
        output.with_suffix(".sha256").write_text(checksum + "  " + output.name + "\n", encoding="utf-8")
    print(json.dumps({"version": version, "files": len(entries), "sha256": checksum,
                      "package": str(output), "smoke": "extracted version and runs help passed"}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print("FAIL " + str(error), file=sys.stderr)
        sys.exit(2)
