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


def test_vn_auto_cli_help_lists_product_commands():
    proc = run_cli('--help')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'vn-auto' in proc.stdout
    for command in ['init', 'check', 'gaps', 'validate', 'sync', 'resolve', 'queue', 'generate', 'promote', 'verify', 'scene-guard', 'scene-state', 'stack-doctor', 'obsidian-audit', 'obsidian-summarize', 'roadmap']:
        assert command in proc.stdout


def test_vn_auto_cli_init_dispatches_bootstrap(tmp_path: Path):
    project = tmp_path / 'cli_title'
    proc = run_cli('init', '--project-root', str(project))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'INIT_VN_AUTOMATION_PROJECT' in proc.stdout
    assert (project / 'docs/automation/project_contract.json').exists()
    assert (project / 'game/data/asset_manifest.json').exists()


def test_vn_auto_cli_check_and_gaps_accept_generic_project(tmp_path: Path):
    project = tmp_path / 'cli_title'
    init = run_cli('init', '--project-root', str(project))
    assert init.returncode == 0, init.stdout + init.stderr

    image_path = project / 'game/images/backgrounds/bg_cli_room.png'
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b'static existence check')
    (project / 'game/script.rpy').write_text(
        'image bg cli_room = "images/backgrounds/bg_cli_room.png"\n'
        'label start:\n'
        '    scene bg cli_room\n'
        '    return\n',
        encoding='utf-8',
    )
    manifest_path = project / 'game/data/asset_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['assets'].append({
        'asset_id': 'bg_cli_room',
        'asset_type': 'background',
        'workflow_id': 'unknown_existing_or_scene_background',
        'generated_path': 'images/backgrounds/bg_cli_room.png',
        'promoted_path': 'images/backgrounds/bg_cli_room.png',
        'qa_status': 'integrated_existing_needs_owner_review',
        'renpy_name': 'bg cli_room',
        'scene_usage': ['cli_test'],
        'metadata': {},
    })
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    check = run_cli('check', '--project-root', str(project))
    assert check.returncode == 0, check.stdout + check.stderr
    assert 'ALL_RENPY_ASSET_REFS_EXIST' in check.stdout

    gap_path = project / 'docs/automation/gap.json'
    gaps = run_cli('gaps', '--project-root', str(project), '--json-out', str(gap_path))
    assert gaps.returncode == 0, gaps.stdout + gaps.stderr
    gap_report = json.loads(gap_path.read_text(encoding='utf-8'))
    assert gap_report['counts']['integrated'] == 1
