from __future__ import annotations

import json
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


def test_new_title_refuses_non_ascii_title_without_slug(tmp_path: Path) -> None:
    workflow = tmp_path / 'workflow_pack'
    write_workflow_pack(workflow)

    proc = run_cli(
        'new-title',
        '--title', '시한부 악녀',
        '--renpy-projects-root', str(tmp_path / 'renpy-project'),
        '--obsidian-vault', str(tmp_path / 'obsidian-vn'),
        '--workflow-pack-root', str(workflow),
    )

    assert proc.returncode == 2
    assert 'GAME_SLUG_REQUIRED' in proc.stdout + proc.stderr
    assert not (tmp_path / 'renpy-project').exists()


def test_new_title_dry_run_plans_no_writes(tmp_path: Path) -> None:
    workflow = tmp_path / 'workflow_pack'
    write_workflow_pack(workflow)

    proc = run_cli(
        'new-title',
        '--title', 'Moonlit Contract',
        '--slug', 'moonlit_contract',
        '--renpy-projects-root', str(tmp_path / 'renpy-project'),
        '--obsidian-vault', str(tmp_path / 'obsidian-vn'),
        '--workflow-pack-root', str(workflow),
        '--dry-run',
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'NEW_TITLE_PLAN' in proc.stdout
    assert 'dry_run True' in proc.stdout
    assert not (tmp_path / 'renpy-project' / 'moonlit_contract').exists()
    assert not (tmp_path / 'obsidian-vn' / 'moonlit_contract').exists()


def test_new_title_bootstraps_valid_title_scoped_project_without_lint(tmp_path: Path) -> None:
    workflow = tmp_path / 'workflow_pack'
    write_workflow_pack(workflow)
    renpy_root = tmp_path / 'renpy-project'
    obsidian_vault = tmp_path / 'obsidian-vn'

    proc = run_cli(
        'new-title',
        '--title', 'Moonlit Contract',
        '--slug', 'moonlit_contract',
        '--renpy-projects-root', str(renpy_root),
        '--obsidian-vault', str(obsidian_vault),
        '--workflow-pack-root', str(workflow),
        '--skip-renpy-lint',
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'NEW_TITLE_BOOTSTRAP_COMPLETE' in proc.stdout
    project = renpy_root / 'moonlit_contract'
    obs_root = obsidian_vault / 'moonlit_contract' / 'VN'
    assert (project / 'game/script.rpy').exists()
    assert (project / 'game/options.rpy').exists()
    assert (project / 'game/gui.rpy').exists()
    assert (project / 'docs/automation/project_contract.json').exists()
    assert (project / 'docs/automation/production_cockpit_roadmap.json').exists()
    assert (project / 'docs/automation/scene_remaster/current_state.json').exists()
    assert (obs_root / 'Automation/dashboard.md').exists()
    assert (obs_root / 'Automation/current_state_0001_bootstrap.md').exists()
    assert (obs_root / 'Scenes/scene_001_opening.md').exists()
    contract = json.loads((project / 'docs/automation/project_contract.json').read_text(encoding='utf-8'))
    assert contract['game_title'] == 'Moonlit Contract'
    assert contract['game_slug'] == 'moonlit_contract'
    assert contract['renpy_project_root'] == project.resolve().as_posix()
    assert contract['obsidian_project_root'] == obs_root.resolve().as_posix()

    validate = run_cli('validate', '--project-root', str(project))
    assert validate.returncode == 0, validate.stdout + validate.stderr
    roadmap = run_cli('roadmap', '--project-root', str(project))
    assert roadmap.returncode == 0, roadmap.stdout + roadmap.stderr
    scene_state = run_cli('scene-state', '--project-root', str(project), '--scene-id', 'scene_001_opening', '--check-existing')
    assert scene_state.returncode == 0, scene_state.stdout + scene_state.stderr
    obsidian = run_cli('obsidian-audit', '--project-root', str(project))
    assert obsidian.returncode == 0, obsidian.stdout + obsidian.stderr


def test_new_title_refuses_existing_project_without_force(tmp_path: Path) -> None:
    workflow = tmp_path / 'workflow_pack'
    write_workflow_pack(workflow)
    project = tmp_path / 'renpy-project' / 'moonlit_contract'
    (project / 'game').mkdir(parents=True)

    proc = run_cli(
        'new-title',
        '--title', 'Moonlit Contract',
        '--slug', 'moonlit_contract',
        '--renpy-projects-root', str(tmp_path / 'renpy-project'),
        '--obsidian-vault', str(tmp_path / 'obsidian-vn'),
        '--workflow-pack-root', str(workflow),
        '--skip-renpy-lint',
    )

    assert proc.returncode == 2
    assert 'NEW_TITLE_REFUSED' in proc.stdout + proc.stderr
