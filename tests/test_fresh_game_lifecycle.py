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


def test_fresh_game_can_be_bootstrapped_synced_queued_and_static_verified(tmp_path: Path):
    project = tmp_path / 'brand_new_title'
    vault = tmp_path / 'obsidian_vault'
    workflow_pack = make_workflow_pack(tmp_path)
    renpy = tmp_path / 'renpy.exe'
    renpy.write_text('stub', encoding='utf-8')

    init = run_cli(
        'init',
        '--project-root', str(project),
        '--workflow-pack-root', str(workflow_pack),
        '--obsidian-vault', str(vault),
        '--renpy-sdk-exe', str(renpy),
    )
    assert init.returncode == 0, init.stdout + init.stderr

    scene_note = vault / 'VN/Scenes/opening.md'
    scene_note.parent.mkdir(parents=True, exist_ok=True)
    scene_note.write_text(
        '---\nscene_id: opening_scene\nstatus: draft\n---\n\n'
        '# Opening\n\n'
        '## Required Assets\n'
        '- [ ] background: bg_opening_room | quiet opening room, no characters\n'
        '- [ ] sfx: sfx_door_soft | short soft door sound\n',
        encoding='utf-8',
    )

    sync = run_cli('sync', '--project-root', str(project), '--vault', str(vault), '--notes-glob', 'VN/Scenes/*.md')
    assert sync.returncode == 0, sync.stdout + sync.stderr
    assert 'processed 1' in sync.stdout

    default_sync = run_cli('sync', '--project-root', str(project))
    assert default_sync.returncode == 0, default_sync.stdout + default_sync.stderr
    assert 'processed 1' in default_sync.stdout

    legacy_explicit_vault_sync = run_cli('sync', '--project-root', str(project), '--vault', str(vault))
    assert legacy_explicit_vault_sync.returncode == 0, legacy_explicit_vault_sync.stdout + legacy_explicit_vault_sync.stderr
    assert 'processed 1' in legacy_explicit_vault_sync.stdout
    assert (project / 'docs/automation/obsidian_scene_asset_request_batch.json').exists()
    resolved = project / 'docs/production/asset_requests/opening_scene.resolved_asset_requests.json'
    assert resolved.exists()
    resolved_data = json.loads(resolved.read_text(encoding='utf-8'))
    assert resolved_data['counts']['generate'] == 2

    queue = run_cli('queue', '--project-root', str(project))
    assert queue.returncode == 0, queue.stdout + queue.stderr
    assert 'generation_items 2' in queue.stdout
    assert (project / 'docs/production/owner_review_queue.md').exists()
    queue_data = json.loads((project / 'docs/production/owner_review_queue.json').read_text(encoding='utf-8'))
    assert queue_data['counts']['generation_items'] == 2

    validate = run_cli('validate', '--project-root', str(project))
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert 'VALIDATION PASSED' in validate.stdout

    verify = run_cli('verify', '--project-root', str(project), '--skip-comfyui', '--skip-renpy-lint')
    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert 'VERIFY_PASSED' in verify.stdout


def test_sync_rejects_notes_glob_that_escapes_title_root(tmp_path: Path):
    project = tmp_path / 'brand_new_title'
    vault = tmp_path / 'obsidian_vault'
    workflow_pack = make_workflow_pack(tmp_path)
    renpy = tmp_path / 'renpy.exe'
    renpy.write_text('stub', encoding='utf-8')

    init = run_cli(
        'init',
        '--project-root', str(project),
        '--workflow-pack-root', str(workflow_pack),
        '--obsidian-vault', str(vault),
        '--renpy-sdk-exe', str(renpy),
    )
    assert init.returncode == 0, init.stdout + init.stderr

    sync = run_cli('sync', '--project-root', str(project), '--notes-glob', '../other_game/VN/Scenes/*.md')
    assert sync.returncode != 0
    assert 'parent traversal' in sync.stdout

    absolute_sync = run_cli('sync', '--project-root', str(project), '--notes-glob', str(vault / 'VN/Scenes/*.md'))
    assert absolute_sync.returncode != 0
    assert 'must be relative' in absolute_sync.stdout


def test_init_without_obsidian_vault_does_not_scaffold_in_cwd(tmp_path: Path):
    project = tmp_path / 'no_vault_title'
    workflow_pack = make_workflow_pack(tmp_path)
    init = run_cli(
        'init',
        '--project-root', str(project),
        '--workflow-pack-root', str(workflow_pack),
    )
    assert init.returncode == 0, init.stdout + init.stderr
    contract = json.loads((project / 'docs/automation/project_contract.json').read_text(encoding='utf-8'))
    assert contract['obsidian_vault'] == ''
    assert contract['obsidian_project_root'] == ''
    assert contract['obsidian_scenes_glob'] == ''
    assert not (ROOT / '00_Index.md').exists()
    assert not (ROOT / 'Automation').exists()
    assert not (ROOT / 'Templates').exists()
