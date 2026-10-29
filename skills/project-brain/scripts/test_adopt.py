"""Focused adoption safety checks; run with python test_adopt.py."""

import json
import os
from pathlib import Path
import tempfile
import zipfile
from unittest import mock

import runtime_adopt as A


class Brain:
    @staticmethod
    def brain_exists(root):
        return (Path(root) / ".project-brain").is_dir()

    @staticmethod
    def write_atomic(path, content):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        if not content.endswith("\n"):
            content += "\n"
        with tmp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(str(tmp), str(path))


def raises(call, fragment=None):
    try:
        call()
    except ValueError as exc:
        if fragment:
            assert fragment in str(exc), (fragment, str(exc))
        return
    raise AssertionError("expected ValueError")


def setup(root):
    (root / ".project-brain").mkdir()
    (root / ".planning" / "tasks").mkdir(parents=True)
    (root / ".planning" / "tasks" / "task.md").write_text("goal: preserve me\n", encoding="utf-8")
    (root / ".planning" / "plan.md").write_text("plan\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("Keep this line.\n", encoding="utf-8")
    (root / "target.md").write_text("adopted intent\n", encoding="utf-8")


def map_all(data, target="target.md"):
    for source in data["sources"]:
        source["targets"] = [{"path": target}]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir()
        setup(root)
        trace = A.prepare(Brain, root)
        assert trace["state"] == "PREPARED" and len(trace["sources"]) == 2
        raises(lambda: A.cleanup(Brain, root), "verified")
        raises(lambda: A.verify(Brain, root, "reviewed"), "every source")
        assert (root / ".planning" / "plan.md").exists()
        trace = A.status(Brain, root)
        map_all(trace)
        A._save(Brain, root, trace)
        verified = A.verify(Brain, root, "Reviewed every source and destination.")
        assert verified["state"] == "VERIFIED"
        cleaned = A.cleanup(Brain, root)
        assert cleaned["state"] == "CLEANED"
        assert not (root / ".planning").exists()
        assert (root / "target.md").read_text(encoding="utf-8") == "adopted intent\n"
        assert (root / "AGENTS.md").read_text(encoding="utf-8") == "Keep this line.\n"
        archive = Path(cleaned["archive"]["path"])
        with zipfile.ZipFile(archive) as zf:
            assert set(zf.namelist()) == {
                "sources/.planning/plan.md",
                "sources/.planning/tasks/task.md",
            }
            assert zf.read("sources/.planning/tasks/task.md").decode().replace("\r\n", "\n") == "goal: preserve me\n"
        assert A.cleanup(Brain, root)["state"] == "CLEANED"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        trace = A.prepare(Brain, root)
        map_all(trace); A._save(Brain, root, trace)
        A.verify(Brain, root, "reviewed")
        (root / "target.md").write_text("drift\n", encoding="utf-8")
        raises(lambda: A.cleanup(Brain, root), "destination changed")
        assert (root / ".planning" / "plan.md").exists()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        # A selected foreign folder containing application code is never cleaned.
        (root / ".planning" / "tasks" / "code.py").write_text("print(1)\n", encoding="utf-8")
        raises(lambda: A.prepare(Brain, root), "unsupported non-tracking")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        for ext in ("html", "css", "png"):
            (root / ".planning" / "tasks" / ("app." + ext)).write_text("app payload", encoding="utf-8")
        raises(lambda: A.prepare(Brain, root), "unsupported non-tracking")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        source = root / "AGENTS.md"
        pointer = "Before work, load the instructions in .planning/.\n"
        security = "Always protect credentials and never disable authorization checks.\n"
        source.write_text(pointer + security, encoding="utf-8")
        trace = A.prepare(Brain, root)
        map_all(trace)
        trace["instruction_removals"] = [{"path": "AGENTS.md", "text": pointer + security, "reason": "old pointer"}]
        A._save(Brain, root, trace)
        raises(lambda: A.verify(Brain, root, "reviewed"), "recognized tracking pointer")
        trace["instruction_removals"] = [{"path": "AGENTS.md", "text": pointer, "reason": "old pointer"}]
        A._save(Brain, root, trace)
        A._save(Brain, root, trace)
        A.verify(Brain, root, "reviewed exact pointer")
        assert A.cleanup(Brain, root)["state"] == "CLEANED"
        assert source.read_text(encoding="utf-8") == security

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        (root / "custom").mkdir()
        (root / "custom" / "notes.txt").write_text("custom tracker\n", encoding="utf-8")
        trace = A.prepare(Brain, root, ["custom"])
        assert trace["roots"] == ["custom"]
        raises(lambda: A.prepare(Brain, root), "pending work")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        raises(lambda: A.prepare(Brain, root, [".git/config"]), "infrastructure")
        raises(lambda: A.prepare(Brain, root, ["../escape"]), "escaping")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        foreign = root / ".planning" / "tasks" / "task.md"
        foreign.write_text("- send | response_unknown\n", encoding="utf-8")
        trace = A.prepare(Brain, root)
        for item in trace["sources"]:
            item["drop_reason"] = "not needed"
        A._save(Brain, root, trace)
        raises(lambda: A.verify(Brain, root, "reviewed"), "cannot be dropped")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        (root / ".project-brain" / "tasks").mkdir()
        dest = root / ".project-brain" / "tasks" / "PB-001.md"
        dest.write_text("Imported task.\n", encoding="utf-8")
        trace = A.prepare(Brain, root)
        for item in trace["sources"]:
            item["targets"] = [{"path": ".project-brain/tasks/PB-001.md"}]
        A._save(Brain, root, trace)
        assert A.verify(Brain, root, "reviewed mapping to Brain task")["state"] == "VERIFIED"
        assert A.cleanup(Brain, root)["state"] == "CLEANED"
        assert dest.exists()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        trace = A.prepare(Brain, root)
        map_all(trace); A._save(Brain, root, trace)
        A.verify(Brain, root, "reviewed")
        original_zip = A.zipfile.ZipFile
        with mock.patch.object(A.zipfile, "ZipFile", side_effect=OSError("simulated archive failure")):
            try:
                A.cleanup(Brain, root)
            except OSError:
                pass
            else:
                raise AssertionError("archive failure was not injected")
        assert (root / ".planning" / "plan.md").exists()
        assert A.status(Brain, root)["state"] == "VERIFIED"
        assert A.zipfile.ZipFile is original_zip

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        trace = A.prepare(Brain, root)
        map_all(trace); A._save(Brain, root, trace)
        A.verify(Brain, root, "reviewed")
        original_unlink = Path.unlink
        failed = [False]

        def unlink_then_interrupt(path, *args, **kwargs):
            original_unlink(path, *args, **kwargs)
            if not failed[0] and Path(path).name == "plan.md":
                failed[0] = True
                raise OSError("simulated interruption")

        with mock.patch.object(Path, "unlink", unlink_then_interrupt):
            try:
                A.cleanup(Brain, root)
            except OSError:
                pass
            else:
                raise AssertionError("cleanup interruption was not injected")
        state = A.status(Brain, root)
        archive_path = state["archive"]["path"]
        assert state["state"] == "CLEANING" and failed[0]
        retried = A.cleanup(Brain, root)
        assert retried["state"] == "CLEANED"
        assert retried["archive"]["path"] == archive_path

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir(); setup(root)
        pointer = "Before work, load .planning/ instructions.\n"
        rule = "Protect credentials.\n"
        agents = root / "AGENTS.md"
        agents.write_text(pointer + rule, encoding="utf-8")
        (root / ".gitignore").write_text(".planning/\nkeep.txt\n", encoding="utf-8")
        trace = A.prepare(Brain, root)
        map_all(trace)
        trace["instruction_removals"] = [{"path": "AGENTS.md", "text": pointer, "reason": "obsolete pointer"}]
        A._save(Brain, root, trace)
        A.verify(Brain, root, "reviewed pointer and ignore entry")
        original = A._remove_ignore_lines
        failed = [False]

        def fail_after_instruction_removal(B, project, state):
            if not failed[0]:
                failed[0] = True
                raise OSError("simulated interruption after instruction write")
            original(B, project, state)

        with mock.patch.object(A, "_remove_ignore_lines", fail_after_instruction_removal):
            try:
                A.cleanup(Brain, root)
            except OSError:
                pass
            else:
                raise AssertionError("instruction cleanup interruption was not injected")
        assert agents.read_text(encoding="utf-8") == rule
        assert A.cleanup(Brain, root)["state"] == "CLEANED"
        assert (root / ".gitignore").read_text(encoding="utf-8") == "keep.txt\n"

    print("PASS: adoption safety, verification, archive, cleanup and retry scenarios")


if __name__ == "__main__":
    main()
