from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def write_workflow_pack(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    workflows = []
    for workflow_id in [
        'char_base',
        'char_expression',
        'char_alpha',
        'scene_background',
        'scene_prop_cg',
        'scene_event_cg',
        'audio_bgm_with_sfx',
    ]:
        (root / f'{workflow_id}.md').write_text(f'# {workflow_id}\n', encoding='utf-8')
        (root / f'{workflow_id}.json').write_text('{}\n', encoding='utf-8')
        workflows.append({
            'id': workflow_id,
            'readme': f'{workflow_id}.md',
            'api': f'{workflow_id}.json',
            'editable_fields': ['prompt'],
        })
    (root / 'WORKFLOW_INDEX.json').write_text(json.dumps({'workflows': workflows}), encoding='utf-8')


def bootstrap_project(tmp_path: Path) -> Path:
    workflow = tmp_path / 'workflow_pack'
    write_workflow_pack(workflow)
    renpy_root = tmp_path / 'renpy-project'
    proc = run_cli(
        'new-title',
        '--title', 'Harness VN',
        '--slug', 'harness_vn',
        '--renpy-projects-root', str(renpy_root),
        '--obsidian-vault', str(tmp_path / 'obsidian-vn'),
        '--workflow-pack-root', str(workflow),
        '--skip-renpy-lint',
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return renpy_root / 'harness_vn'


def test_polish_scene_runs_guard_state_and_validation_without_assets(tmp_path: Path) -> None:
    project = bootstrap_project(tmp_path)
    run_dir = project / 'docs/validation/scene001_polish_harness'
    run_dir.mkdir(parents=True)
    before = run_dir / 'script_before.rpy'
    shutil.copy2(project / 'game/script.rpy', before)

    proc = run_cli(
        'polish-scene',
        '--project-root', str(project),
        '--scene-id', 'scene_001_opening',
        '--patch-id', 'scene001_polish_harness',
        '--before', 'docs/validation/scene001_polish_harness/script_before.rpy',
        '--start-label', 'scene_001_opening',
        '--require-menu-choice', '첫 장면의 방향을 정한다',
        '--changed-file', 'game/script.rpy',
        '--skip-renpy-lint',
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'POLISH_SCENE_COMPLETE' in proc.stdout
    assert (run_dir / 'scene_patch_guard.json').exists()
    assert (run_dir / 'scene_polish_qa_report.md').exists()
    assert (run_dir / 'scene_polish_qa_report.json').exists()
    state = json.loads((project / 'docs/automation/scene_remaster/current_state.json').read_text(encoding='utf-8'))
    assert state['scene_id'] == 'scene_001_opening'
    assert state['latest_patch_id'] == 'scene001_polish_harness'
    assert state['asset_policy'] == 'scene_local_preview_only'
    assert state['permanent_asset_changes'] is False
    assert state['latest_guard_report'] == 'docs/validation/scene001_polish_harness/scene_patch_guard.json'
    assert state['latest_qa_report'] == 'docs/validation/scene001_polish_harness/scene_polish_qa_report.md'
    pool = json.loads((project / state['scene_pool']).read_text(encoding='utf-8'))
    assert pool['global_replacement_allowed'] is False
    assert pool['promotion_requires_owner_approval'] is True


def test_polish_scene_fails_closed_when_required_choice_missing(tmp_path: Path) -> None:
    project = bootstrap_project(tmp_path)
    run_dir = project / 'docs/validation/scene001_missing_choice'
    run_dir.mkdir(parents=True)
    shutil.copy2(project / 'game/script.rpy', run_dir / 'script_before.rpy')

    proc = run_cli(
        'polish-scene',
        '--project-root', str(project),
        '--scene-id', 'scene_001_opening',
        '--patch-id', 'scene001_missing_choice',
        '--before', 'docs/validation/scene001_missing_choice/script_before.rpy',
        '--start-label', 'scene_001_opening',
        '--require-menu-choice', '존재하지 않는 선택지',
        '--skip-renpy-lint',
    )

    assert proc.returncode == 1
    assert 'POLISH_SCENE_FAILED scene-guard' in proc.stdout + proc.stderr
    assert not (run_dir / 'scene_polish_qa_report.md').exists()
