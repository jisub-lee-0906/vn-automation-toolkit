from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import scene_patch_guard  # noqa: E402


def write_contract(root: Path) -> None:
    (root / 'docs/automation').mkdir(parents=True)
    (root / 'game').mkdir()
    (root / 'docs/automation/project_contract.json').write_text(json.dumps({
        'project_root': str(root),
        'renpy_project_root': str(root),
        'renpy_game_dir': str(root / 'game'),
    }), encoding='utf-8')


def test_scene_patch_guard_passes_required_invariants(tmp_path: Path) -> None:
    write_contract(tmp_path)
    before = tmp_path / 'docs/backup_before.rpy'
    before.parent.mkdir(parents=True, exist_ok=True)
    before.write_text('''label start:\n    $ clue = True\n    menu:\n        "Old choice":\n            jump next_scene\n\nlabel next_scene:\n    pass\n''', encoding='utf-8')
    after = tmp_path / 'game/script.rpy'
    after.write_text('''label start:\n    $ clue = True\n    $ new_state = True\n    menu:\n        "New choice":\n            jump next_scene\n\nlabel next_scene:\n    pass\n''', encoding='utf-8')
    out = tmp_path / 'docs/automation/guard.json'
    rc = scene_patch_guard.main([
        '--project-root', str(tmp_path),
        '--before', str(before),
        '--after', 'game/script.rpy',
        '--start-label', 'start',
        '--end-label', 'next_scene',
        '--require-var', 'clue',
        '--require-jump', 'next_scene',
        '--require-menu-choice', 'New choice',
        '--out', str(out),
    ])
    assert rc == 0
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'PASS'
    assert data['diff']['removed_vars_set'] == []
    assert data['diff']['added_vars_set'] == ['new_state']


def test_scene_patch_guard_fails_missing_required_var(tmp_path: Path) -> None:
    write_contract(tmp_path)
    before = tmp_path / 'before.rpy'
    before.write_text('label start:\n    $ clue = True\n    jump next_scene\nlabel next_scene:\n    pass\n', encoding='utf-8')
    after = tmp_path / 'game/script.rpy'
    after.write_text('label start:\n    jump next_scene\nlabel next_scene:\n    pass\n', encoding='utf-8')
    out = tmp_path / 'docs/automation/guard.json'
    rc = scene_patch_guard.main([
        '--project-root', str(tmp_path),
        '--before', str(before),
        '--after', 'game/script.rpy',
        '--start-label', 'start',
        '--end-label', 'next_scene',
        '--require-var', 'clue',
        '--out', str(out),
    ])
    assert rc == 1
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'FAIL'
    assert 'required variable not assigned/defaulted in after slice: clue' in data['errors']
