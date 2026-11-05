"""Automatic on-use conversion, observational exceptions and continuity."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import brain as B
import migrate as M
from test_brain import BRAIN, V0_FILE, V3_TASK, git, run, write
from test_routing import _project


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def main():
    for command in ('orient', 'boot'):
        for unborn in (False, True):
            with tempfile.TemporaryDirectory(prefix='pb-startup-') as directory:
                root = Path(directory)
                if unborn:
                    git(root, 'init', '-q')
                original = V0_FILE.replace('\n', '\r\n').encode('utf-8')
                (root / 'PROJECT_BRAIN.md').write_bytes(original)
                write(root, 'user.txt', 'Uncommitted user work\n')
                before = snapshot(root)
                for read in ('orient', 'boot'):
                    assert run(root, read, '--read-only')[0] == 0
                    assert snapshot(root) == before
                code, output = run(root, command)
                assert code == 0, output
                if command == 'orient':
                    data = json.loads(output)
                    assert data['focus'] == 'PB-003' and 'auto-migrated' in data['maintenance'][0]
                assert B.parse_config(root)['skill_version'] == B.VERSION
                assert (B.bp(root) / 'migration-backup/PROJECT_BRAIN.md').read_bytes() == original
                assert (root / 'PROJECT_BRAIN.md').read_bytes() == original
                assert (root / 'user.txt').read_text(encoding='utf-8') == 'Uncommitted user work\n'
                active = B.find_task(root, 'PB-003')
                assert active['status'] == 'IN_PROGRESS' and 'conflict policy undecided' in active['text']
                assert 'Depends: PB-002' in active['text'] and B.target_status(root) == 'DRAFT'
                assert (root / '.git').exists() == unborn
                after = snapshot(root)
                code, output = run(root, command)
                assert code == 0 and snapshot(root) == after, output

    with tempfile.TemporaryDirectory(prefix='pb-startup-dir-') as directory:
        root = Path(directory)
        write(root, '.project-brain/config.yaml', 'schema_version: 3\ncustom:\n  keep: yes\n')
        write(root, '.project-brain/current.md', '# Current\n')
        write(root, '.project-brain/target.md', '# Target\n## Objective\nUser goal\n')
        write(root, '.project-brain/tasks/PB-004.md', V3_TASK)
        raw = snapshot(root)
        assert run(root, 'orient')[0] == 0
        assert B.parse_config(root)['custom']['keep'] == 'yes'
        assert B.parse_config(root)['schema_version'] == str(B.SCHEMA)
        assert (B.bp(root) / 'migration-backup/tasks/PB-004.md').read_bytes() == raw[str(Path('.project-brain/tasks/PB-004.md'))]
        assert 'waiting on a design note' in B.find_task(root, 'PB-004')['text']

    # Actual processes share the first migration's writer lock.
    with tempfile.TemporaryDirectory(prefix='pb-startup-race-') as directory:
        root = Path(directory)
        write(root, 'PROJECT_BRAIN.md', V0_FILE)
        workers = [subprocess.Popen([sys.executable, '-B', str(BRAIN), 'orient', str(root)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for worker in workers:
            output, error = worker.communicate(timeout=45)
            assert worker.returncode == 0, (output, error)
            assert json.loads(output)['focus'] == 'PB-003'
        assert (B.bp(root) / 'migration-backup/PROJECT_BRAIN.md').read_text(encoding='utf-8') == V0_FILE

    # A failed automatic conversion remains retryable from the raw backup.
    with tempfile.TemporaryDirectory(prefix='pb-startup-retry-') as directory:
        root = Path(directory)
        write(root, '.project-brain/config.yaml', 'schema_version: 3\n')
        write(root, '.project-brain/current.md', '# Current\n')
        write(root, '.project-brain/tasks/PB-004.md', V3_TASK)
        replace = B.os.replace
        def fail_task(source, destination):
            if Path(destination).name == 'PB-004.md':
                raise OSError('injected startup interruption')
            return replace(source, destination)
        with patch.object(B.os, 'replace', side_effect=fail_task), contextlib.redirect_stdout(io.StringIO()):
            try:
                with B.startup_lock(root):
                    M.startup(root)
                raise AssertionError('failure injection not reached')
            except OSError as exc:
                assert 'injected' in str(exc)
        assert B.parse_config(root)['schema_version'] == '3'
        assert run(root, 'orient')[0] == 0
        assert 'waiting on a design note' in B.find_task(root, 'PB-004')['text']
        assert (B.bp(root) / 'migration-backup/tasks/PB-004.md').read_text(encoding='utf-8') == V3_TASK

    # A new-session boot upgrades the previous release without changing saved
    # executor restrictions, unresolved requests, active work or unrelated files.
    with tempfile.TemporaryDirectory(prefix='pb-startup-310-') as directory:
        root = Path(directory)
        with contextlib.redirect_stdout(io.StringIO()):
            _project(root, legacy=False)
        config = B.bp(root) / 'config.yaml'
        config.write_text(config.read_text(encoding='utf-8').replace(B.VERSION, '3.10.0'), encoding='utf-8')
        policy = {'schema': 1, 'execution': {'source': 'cap-pinned', 'models': [{'routeId': 'user-route', 'modelId': 'user-model'}]},
                  'scheduling': {'mode': 'serial', 'max_parallel': 1},
                  'quota_recovery': {'enabled': False, 'threshold_percent': 10}}
        write(root, '.project-brain/executor-policy.json', json.dumps(policy))
        write(root, '.project-brain/requests.json', '{"schema":1,"requests":[]}')
        write(root, 'user-work.txt', 'Keep this local work\n')
        task = B.bp(root) / 'tasks/PB-001.md'
        task.write_text(task.read_text(encoding='utf-8').replace('Status: READY', 'Status: IN_PROGRESS') +
                        '\n## Resume\nKeep pending user changes.\n\n## External\nStatus: response_unknown\n', encoding='utf-8')
        protected = [B.bp(root) / 'executor-policy.json', B.bp(root) / 'requests.json', root / 'user-work.txt']
        before = {p: p.read_bytes() for p in protected}
        raw_task = task.read_bytes()
        code, output = run(root, 'boot', '--new-session')
        assert code == 0, output
        assert B.parse_config(root)['skill_version'] == B.VERSION
        assert all(p.read_bytes() == raw for p, raw in before.items())
        assert 'Keep pending user changes.' in task.read_text(encoding='utf-8')
        assert 'response_unknown' in task.read_text(encoding='utf-8')
        assert (B.bp(root) / 'migration-backup/tasks/PB-001.md').read_bytes() == raw_task
        stable = snapshot(root)
        assert run(root, 'orient')[0] == 0 and snapshot(root) == stable

    with tempfile.TemporaryDirectory(prefix='pb-startup-modern-') as directory:
        root = Path(directory)
        with contextlib.redirect_stdout(io.StringIO()):
            _project(root, legacy=False)
        config = B.bp(root) / 'config.yaml'
        config.write_text(config.read_text(encoding='utf-8').replace(B.VERSION, '3.7.0'), encoding='utf-8')
        task = B.bp(root) / 'tasks/PB-001.md'
        task.write_text(task.read_text(encoding='utf-8').replace('Status: READY', 'Status: IN_PROGRESS') +
                        '\n## Resume\nKeep the pending edit.\n\n## External\nStatus: response_unknown\nReceipt: user-owned\n', encoding='utf-8')
        original = task.read_bytes()
        assert run(root, 'orient')[0] == 0
        assert 'Keep the pending edit.' in task.read_text(encoding='utf-8') and 'Receipt: user-owned' in task.read_text(encoding='utf-8')
        assert (B.bp(root) / 'migration-backup/tasks/PB-001.md').read_bytes() == original
        # A future project must be rejected before resetting session policy.
        for field, value in (('skill_version', '99.0.0'), ('schema_version', '99')):
            old = B.VERSION if field == 'skill_version' else str(B.SCHEMA)
            config.write_text(config.read_text(encoding='utf-8').replace(old, value), encoding='utf-8')
            before = snapshot(root)
            for command in (('boot', '--new-session'), ('orient',)):
                assert run(root, *command)[0] == 2
                assert snapshot(root) == before
            config.write_text(config.read_text(encoding='utf-8').replace('99.0.0', B.VERSION).replace('schema_version: 99', 'schema_version: 4'), encoding='utf-8')
        # Merge/rebase defers conversion and session reset.
        config.write_text(config.read_text(encoding='utf-8').replace(B.VERSION, '3.7.0'), encoding='utf-8')
        before = snapshot(root)
        with patch.object(B, 'merge_op', return_value='rebase'), contextlib.redirect_stdout(io.StringIO()):
            with B.startup_lock(root):
                assert M.startup(root) == []
                B.cmd_boot(root, new_session=True)
        assert snapshot(root) == before

    for malformed in ('# My unrelated notes\n', ''):
        with tempfile.TemporaryDirectory(prefix='pb-startup-unknown-') as directory:
            root = Path(directory)
            write(root, 'PROJECT_BRAIN.md', malformed)
            before = snapshot(root)
            for command in ('orient', 'boot'):
                assert run(root, command)[0] == 2
                assert snapshot(root) == before and not B.bp(root).exists()
    with tempfile.TemporaryDirectory(prefix='pb-startup-empty-') as directory:
        root = Path(directory)
        assert run(root, 'orient')[0] == 0 and run(root, 'boot')[0] == 0
        assert not B.bp(root).exists() and not (root / '.git').exists()
    print('PASS: automatic startup upgrade without Git/HEAD, raw backups, continuity, idempotency, read-only/merge/future/unknown guards')


if __name__ == '__main__':
    main()
