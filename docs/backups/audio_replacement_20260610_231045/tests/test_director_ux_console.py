from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_IDS = [
    'char_base',
    'char_expression',
    'char_alpha',
    'scene_background',
    'scene_prop_cg',
    'scene_event_cg',
    'audio_bgm_ace',
    'audio_sfx_mmaudio',
]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def make_workflow_pack(tmp_path: Path) -> Path:
    pack = tmp_path / 'workflow_pack'
    pack.mkdir()
    workflows = []
    for workflow_id in WORKFLOW_IDS:
        api_name = f'{workflow_id}.json'
        readme_name = f'{workflow_id}.md'
        (pack / api_name).write_text(
            json.dumps({'1': {'class_type': 'TestNode', 'inputs': {'text': 'placeholder'}}}),
            encoding='utf-8',
        )
        (pack / readme_name).write_text(f'# {workflow_id}\n', encoding='utf-8')
        workflows.append({
            'id': workflow_id,
            'api': api_name,
            'readme': readme_name,
            'editable_fields': ['1.inputs.text'],
        })
    (pack / 'WORKFLOW_INDEX.json').write_text(json.dumps({'workflows': workflows}), encoding='utf-8')
    return pack


def bootstrap_moonlit_library(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / 'moonlit_library'
    vault = tmp_path / 'Moonlit Library Vault'
    workflow_pack = make_workflow_pack(tmp_path)
    renpy = tmp_path / 'renpy.exe'
    renpy.write_text('stub', encoding='utf-8')
    init = run_cli(
        'init',
        '--project-root', str(project),
        '--workflow-pack-root', str(workflow_pack),
        '--obsidian-vault', str(vault),
        '--obsidian-project-root', str(vault / 'VN'),
        '--renpy-sdk-exe', str(renpy),
    )
    assert init.returncode == 0, init.stdout + init.stderr
    return project, vault


def test_director_status_presents_project_agnostic_dashboard(tmp_path: Path):
    project, _vault = bootstrap_moonlit_library(tmp_path)

    proc = run_cli('director', 'status', '--project-root', str(project))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'VN Production Console' in proc.stdout
    assert 'moonlit_library' in proc.stdout
    assert '[✓] Ren\'Py project contract' in proc.stdout
    assert '[✓] Obsidian production vault' in proc.stdout
    assert 'Today\'s director actions' in proc.stdout
    assert '1. Create a new scene' in proc.stdout
    assert str(project) in proc.stdout


def test_director_new_scene_creates_supervised_playable_draft_and_review_cards(tmp_path: Path):
    project, vault = bootstrap_moonlit_library(tmp_path)

    proc = run_cli(
        'director', 'new-scene',
        '--project-root', str(project),
        '--scene-id', 'opening_night_library',
        '--title', 'Opening Night Library',
        '--summary', 'The protagonist wakes after closing time while rain taps on the library windows.',
        '--goal', 'Make the player wonder whether the quiet librarian can be trusted.',
        '--choice', 'Who are you?',
        '--choice', 'Why do you know my name?',
        '--asset', 'background:bg_library_rainy_night|rainy night library interior, no characters',
        '--asset', 'character_base:char_librarian_base|memory-lost librarian, calm, black hair, faint smile',
        '--asset', 'character_expression:char_librarian_uneasy|same librarian looking uneasy',
        '--asset', 'sfx:sfx_rain_window|soft rain tapping on windows',
        '--playable-placeholder',
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'Scene Draft Ready' in proc.stdout
    assert 'Moonlit Library' in proc.stdout
    assert 'opening_night_library' in proc.stdout
    assert '[✓] Obsidian scene note' in proc.stdout
    assert '[✓] Ren\'Py placeholder draft' in proc.stdout
    assert '[✓] Owner review queue' in proc.stdout
    assert 'Next director choices' in proc.stdout

    note = vault / 'VN/Scenes/opening_night_library.md'
    assert note.exists()
    note_text = note.read_text(encoding='utf-8')
    assert '## Required Assets' in note_text
    assert '- [ ] background: bg_library_rainy_night | rainy night library interior, no characters' in note_text
    assert '- [ ] character_base: char_librarian_base | memory-lost librarian, calm, black hair, faint smile' in note_text

    draft = project / 'game/scripts/opening_night_library.rpy'
    assert draft.exists()
    draft_text = draft.read_text(encoding='utf-8')
    assert 'label opening_night_library:' in draft_text
    assert 'menu:' in draft_text
    assert '"Who are you?"' in draft_text

    resolved = project / 'docs/production/asset_requests/opening_night_library.resolved_asset_requests.json'
    assert resolved.exists()
    resolved_data = json.loads(resolved.read_text(encoding='utf-8'))
    assert resolved_data['counts']['generate'] == 4

    queue = project / 'docs/production/owner_review_queue.json'
    queue_data = json.loads(queue.read_text(encoding='utf-8'))
    assert queue_data['counts']['generation_items'] == 4

    card = project / 'docs/production/director_cards/opening_night_library.md'
    assert card.exists()
    card_text = card.read_text(encoding='utf-8')
    assert '# Scene Director Card: opening_night_library' in card_text
    assert 'Playable placeholder draft' in card_text
    assert 'Asset approval needed' in card_text

    status = run_cli('director', 'status', '--project-root', str(project))
    assert status.returncode == 0, status.stdout + status.stderr
    assert '[!] Approval pending asset items: 4' in status.stdout
    assert 'opening_night_library' in status.stdout

    validate = run_cli('validate', '--project-root', str(project))
    assert validate.returncode == 0, validate.stdout + validate.stderr
    verify = run_cli('verify', '--project-root', str(project), '--skip-comfyui', '--skip-renpy-lint')
    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert 'VERIFY_PASSED' in verify.stdout
