"""Actual isolated Squad task handshake; no model, game or ASTER write.

Models and HTTP/input serving are deliberately not started. This verifies the
real task DB, membership, send/receive and reported identity, not live agent QA.
"""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.desktop_broker import DesktopBroker
from core.natural_desktop import NaturalDesktopTask
from core.squad_adapter import SquadAdapter
from core.multi_agent_service import MultiAgentService
from tests.test_desktop_broker import FakeBackend


def main():
    destination = ROOT / 'labs' / ('warband-squad-' + time.strftime('%Y%m%d-%H%M%S'))
    destination.mkdir(parents=True)
    project = Path('C:/WarbandIsland')
    before = (project / '.squad').exists()
    idle = MultiAgentService._task_squad_status(SquadAdapter(project))
    assert idle['ready'] and not idle['initialized'] and idle['database'] == '', idle
    broker = DesktopBroker(FakeBackend())
    desktop = SimpleNamespace(broker=broker, windows=lambda: [])
    task = NaturalDesktopTask(desktop, lambda *args: None, factories={}, evidence_root=destination,
        warband_factory=lambda _: SimpleNamespace(context=lambda: {}, shutdown=lambda: None))
    try:
        # The bridge itself uses the real installed Squad CLI. Only model/input
        # execution is omitted so this narrow test needs no screen permission.
        with patch.object(task, '_launch_provider'), patch.object(task, '_serve'), \
             patch.object(task, '_watch', side_effect=lambda: task.stopped.wait(60)):
            state = task.start('Codex logları incele. Gemini bağımsız kontrol et.',
                {'id': 'aster-warband', 'path': str(project), 'workflow': 'warband'}, 'squad-test',
                {'codex': {'model': 'gpt-6-luna', 'effort': 'low'},
                 'antigravity': {'model': 'gemini-3.8-flash-low', 'effort': 'low'}})
        info = state['squad']
        assert info['connected'] and info['mode'] == 'task-isolated', info
        assert Path(info['database']).is_file()
        assert destination in Path(info['database']).parents
        left, right = task.agent_ids['codex'], task.agent_ids['antigravity']
        task.squad.send(left, right, 'Quartz isolated bridge probe', task_id=state['job']['task_id'])
        replies = task.squad.receive(right)
        assert any(row.get('task_id') == state['job']['task_id'] and
                   'Quartz isolated bridge probe' in str(row) for row in replies), replies
        assert (project / '.squad').exists() == before
        report = {'status': 'VERIFIED', 'scope': 'real CLI/task DB/membership/send/receive, no models or GUI',
                  'idle': idle, 'squad': info, 'task_id': state['job']['task_id'], 'root_squad_unchanged': True}
        (destination / 'acceptance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        task.stop(); broker.close()


if __name__ == '__main__':
    main()
