"""Fresh-session gates, bounded orientation, complete intake and architecture inputs."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
from unittest.mock import patch
import brain as B
import runtime_agents as A
import runtime_protocol as R
import runtime_session as RS
from test_routing import _project


def economy_checks():
    import migrate
    import runtime_agent_pool as AP
    import runtime_runs as runs
    assert len((Path(__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8").encode("utf-8")) <= 6500

    def capture(fn, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert fn(*args) == 0
        raw = output.getvalue()
        assert len(raw.encode("utf-8")) <= 4096, len(raw.encode("utf-8"))
        return json.loads(raw)

    def snapshot(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    with tempfile.TemporaryDirectory(prefix="pb-brief-") as directory:
        root = Path(directory) / "project"
        root.mkdir()
        with patch.object(A, "DEFAULT_REGISTRY", Path(directory) / "registry.json"):
            empty = snapshot(root)
            with patch.object(sys, "argv", ["brain.py", "brief", str(root)]):
                assert capture(B.main)["status"] == "no_brain"
            assert snapshot(root) == empty
            _project(root, legacy=False)
            task_file = B.bp(root) / "tasks/PB-001.md"
            B.set_headers(task_file, {"Status": "IN_PROGRESS"})
            for i in range(6):
                B.append_section(task_file, "Resume", "Next: " + chr(0x1f642) * 800)
            for i in range(5):
                B.append_section(task_file, "External",
                                 "- response_unknown | readback%d %s" % (i, chr(0x1f642) * 500))
            with contextlib.redirect_stdout(io.StringIO()):
                for i in range(5):
                    RS.intake(B, root, ["Directive %d" % i])
            rows = [{"run": "run%d" % i, "task": "PB-001", "state": "UNKNOWN"} for i in range(8)]
            before = snapshot(root)
            with patch.object(AP, "rpc", side_effect=AssertionError("brief called Pool")), \
                    patch.object(migrate, "startup", side_effect=AssertionError("brief migrated")), \
                    patch.object(B, "cmd_boot", side_effect=AssertionError("brief booted")), \
                    patch.object(B, "cmd_map", side_effect=AssertionError("brief scanned")), \
                    patch.object(B, "set_session_modes", side_effect=AssertionError("brief reset session")), \
                    patch.object(runs, "peek", return_value=rows):
                info = capture(RS.brief, B, root)
            assert snapshot(root) == before
            assert info["observational"] and info["gate"] == "not_evaluated"
            assert info["focus"]["id"] == "PB-001" and info["focus"]["resume_omitted"]
            assert info["intake"]["pending_total"] == 5 and info["intake"]["omitted"] == 2
            assert info["external"]["unresolved_total"] == 5 and info["external"]["omitted"] >= 2
            assert info["external"]["sample_refs"][0]["op_truncated"]
            assert info["readback_required"] and info["runs"]["total_unknown"]
            assert info["runs"]["readback_count_lower_bound"] == 8

            # Active implementation wins over an earlier ID in review. A brief
            # never evaluates history/dependencies to schedule a READY task.
            second = B.bp(root) / "tasks/PB-002.md"
            second.write_text(task_file.read_text(encoding="utf-8").replace("PB-001", "PB-002"), encoding="utf-8")
            B.set_headers(task_file, {"Status": "REVIEW"})
            with patch.object(runs, "peek", return_value=[]):
                assert capture(RS.brief, B, root)["focus"]["id"] == "PB-002"
                assert RS.focus(B, root) == "PB-002"
                B.set_headers(second, {"Status": "READY"})
                assert capture(RS.brief, B, root)["focus"]["id"] == "PB-001"
                B.set_headers(task_file, {"Status": "READY"})
                ready = capture(RS.brief, B, root)
                assert ready["focus"] is None and "READY selection not evaluated" in ready["focus_scope"]

            # Malformed state is surfaced without repairing or authorizing it.
            ledger_file = RS.ledger_path(B, root)
            ledger_file.write_text('{"schema":99}', encoding="utf-8")
            try:
                capture(RS.brief, B, root)
                raise AssertionError("malformed ledger hidden")
            except ValueError:
                pass

            # Selected request/identity is enough; default output excludes catalogs.
            B.set_session_modes(root, "pool-all", "pool-all", new=True)
            model = {"id": "small", "routeId": "local", "enabled": True, "group": "low"}
            response = {"selected": model, "alias": "pool/test", "strength": "low",
                        "request": {"group": "low", "kind": "read"},
                        "alternatives": [{"id": "candidate%d" % i} for i in range(100)]}
            for role, tier in (("discovery", "L"), ("worker", "M"), ("lead", "H"), ("reviewer", "H")):
                args = SimpleNamespace(root=str(root), agents_cmd="select", tier="", role=role,
                                       task=None, cli="", exclude="", full=False, mode=None)
                with patch.object(AP, "select", return_value=response) as selection, patch.object(AP, "remember"):
                    view = capture(AP.agents, B, args)
                assert selection.call_args.args[0] == tier
                assert "alternatives" not in view and view["alternatives_count"] == 100
                assert view["selected"]["id"] == "small"
            args.role, args.tier, args.full = "discovery", "M", True
            with patch.object(AP, "select", return_value=response) as selection, patch.object(AP, "remember"):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    AP.agents(B, args)
                assert len(json.loads(output.getvalue())["alternatives"]) == 100
                assert selection.call_args.args[0] == "M"
            args.task, args.full = "PB-001", False
            with patch.object(AP, "A_score", return_value={"effective_tier": "H"}), \
                    patch.object(AP, "select", return_value=response) as selection, patch.object(AP, "remember"):
                capture(AP.agents, B, args)
                assert selection.call_args.args[0] == "H"
            B.set_session_modes(root, "pool-low", "pool-low", new=True)
            with patch.object(AP, "A_score", return_value={"effective_tier": "H"}), \
                    patch.object(AP, "select", side_effect=AssertionError("resource cap bypassed")):
                try:
                    capture(AP.agents, B, args)
                    raise AssertionError("high discovery task silently lowered")
                except ValueError:
                    pass
    print("PASS: bounded read-only brief, unresolved-state retention, low discovery and compact/full selection")


def main():
    economy_checks()
    with tempfile.TemporaryDirectory(prefix='pb-session-') as directory:
        root = Path(directory) / 'project'
        root.mkdir()
        with patch.object(A, 'DEFAULT_REGISTRY', Path(directory) / 'registry.json'), contextlib.redirect_stdout(io.StringIO()) as output:
            _project(root, legacy=False)
            file = B.bp(root) / 'tasks/PB-001.md'
            file.write_text(file.read_text().replace('Risk: LOW', 'Purpose: discovery\nRisk: LOW'), encoding='utf-8')
            task = B.find_task(root, 'PB-001')
            R.reconcile(B, root, task, 'Read source only', independent=True)
            B.set_session_modes(root, new=True)
            try:
                B.cmd_start(root, 'PB-001')
                raise AssertionError('implementation started before session choice')
            except ValueError as exc:
                assert 'SESSION_CHOICE_REQUIRED' in str(exc)
            modes = B.set_session_modes(root, 'native', 'solo', schedule='parallel', max_parallel=3, task_mode='execute', note='User choice')
            assert modes['exec'] == 'self_mixed' and modes['max_parallel'] == 3
            assert B.get_session_modes(root)['schedule'] == 'parallel'
            B.set_session_modes(root, schedule='serial')
            assert B.get_session_modes(root)['max_parallel'] == 1
            B.set_session_modes(root, 'SOLO', 'SOLO')
            assert B.cmd_start(root, 'PB-001') == 0
            before_task = file.read_bytes()
            requirements = ['Requirement %d' % i for i in range(12)]
            first = RS.intake(B, root, requirements, 'related')
            assert first['request']['items'] == requirements and first['resume_task'] == 'PB-001'
            question = RS.intake(B, root, ['What is this function doing?'], 'question')
            assert file.read_bytes() == before_task
            RS.intake(B, root, [], resolve=question['request']['id'])
            assert file.read_bytes() == before_task and RS.focus(B, root) == 'PB-001'
            try:
                RS.intake(B, root, [], resolve=first['request']['id'])
                raise AssertionError('directive silently dropped without task mapping')
            except ValueError:
                pass
            RS.intake(B, root, [], task='PB-001', resolve=first['request']['id'])
            assert RS.ledger(B, root)['requests'][0]['items'] == requirements
            pending = RS.intake(B, root, ['A separate follow-up request'], 'new-work')
            portable = R.handoff(B, root, B.find_task(root, 'PB-001'))
            assert pending['request']['id'] in portable['intake']['pending']
            B.set_session_modes(root, task_mode='response')
            try:
                B.require_session(root, implementation=True)
                raise AssertionError('response session allowed implementation')
            except ValueError as exc:
                assert 'RESPONSE_ONLY' in str(exc)
            B.set_session_modes(root, task_mode='execute')
            # Metadata orientation neither calls Pool nor executes commands/tests.
            import runtime_agent_pool as AP
            B.set_session_modes(root, 'pool-all', 'native', task_mode='response')
            fake_model = {'id': 'model', 'routeId': 'local', 'enabled': True}
            with patch.object(AP, 'select', return_value={'selected': fake_model}) as selection:
                AP.agents(B, SimpleNamespace(root=str(root), agents_cmd='select', tier='L', role='worker', task=None, cli='', exclude=''))
                assert selection.call_args.kwargs['mode'] == 'response'
            B.set_session_modes(root, 'SOLO', 'SOLO', task_mode='execute')
            catalog = AP.compact_catalog({'policy': {'selectionMode': 'manual'}, 'connections': [], 'models': [{'id': str(i), 'group': 'low'} for i in range(50)]})
            assert len(catalog['pools'][0]['members']) == 12 and catalog['pools'][0]['omitted'] == 38
            assert 'models' not in catalog and catalog['catalog_digest']
            with patch.object(AP, 'rpc', side_effect=AssertionError('orientation must not call Pool')):
                capture = io.StringIO()
                with contextlib.redirect_stdout(capture):
                    assert RS.orient(B, root) == 0
                info = json.loads(capture.getvalue())
                assert info['focus'] == 'PB-001' and len(capture.getvalue()) < 6000
            # Architectural Current is an allowed explicit verification input.
            task = B.find_task(root, 'PB-001')
            task['inputs'] = ['.project-brain/current.md']
            R.reconcile(B, root, task, 'Include the architecture document as a verification input', independent=True)
            before = R.task_digest(B, root, task)[0]
            current = B.bp(root) / 'current.md'
            current.write_text(current.read_text()+'\nObserved new boundary.\n', encoding='utf-8')
            assert R.task_digest(B, root, task)[0] != before
            # A fresh top-level session resets resource choices; in-session boot does not.
            with patch.object(sys, 'argv', ['brain.py', 'boot', str(root), '--new-session']):
                B.main()
            assert not B.get_session_modes(root)['exec']
            assert B.find_task(root, 'PB-001')['status'] == 'IN_PROGRESS'
            assert (root / 'src/a.py').read_text() == 'pass\n'
            with patch.dict(os.environ, {'PB_SESSION_ID': 'first'}):
                B.set_session_modes(root, 'pool-low', 'pool-medium', new=True)
            with patch.dict(os.environ, {'PB_SESSION_ID': 'second'}):
                assert not B.get_session_modes(root)['exec']
    print('PASS: mandatory session choice, serial/parallel and task modes, metadata orientation, complete intake, focus and architecture updates')


if __name__ == '__main__':
    main()
