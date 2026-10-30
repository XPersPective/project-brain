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


def main():
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
