from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'


def make_min_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / 'generic_title'
    game = project / 'game'
    (game / 'images/backgrounds').mkdir(parents=True)
    (game / 'audio/sfx').mkdir(parents=True)
    (game / 'data').mkdir(parents=True)
    (project / 'docs/automation/templates').mkdir(parents=True)
    (project / 'docs/automation/schemas').mkdir(parents=True)
    (project / 'docs/production/promotions').mkdir(parents=True)
    (game / 'images/backgrounds/bg_room.png').write_bytes(b'not a real png but existence is enough for static ref checks')
    (game / 'script.rpy').write_text(
        'image bg room = "images/backgrounds/bg_room.png"\n'
        'label start:\n'
        '    scene bg room\n'
        '    return\n',
        encoding='utf-8',
    )
    manifest = {
        'version': '1.0.0',
        'assets': [{
            'asset_id': 'bg_room',
            'asset_type': 'background',
            'workflow_id': 'unknown_existing_or_scene_background',
            'generated_path': 'images/backgrounds/bg_room.png',
            'promoted_path': 'images/backgrounds/bg_room.png',
            'qa_status': 'integrated_existing_needs_owner_review',
            'renpy_name': 'bg room',
            'scene_usage': ['test'],
            'metadata': {},
        }],
    }
    (game / 'data/asset_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    workflow_root = tmp_path / 'workflow_pack'
    workflow_root.mkdir()
    (workflow_root / 'WORKFLOW_INDEX.json').write_text(json.dumps({'workflows': []}), encoding='utf-8')
    contract = {
        'renpy_project_root': str(project),
        'renpy_game_dir': str(game),
        'manifest_path': str(game / 'data/asset_manifest.json'),
        'workflow_pack_root': str(workflow_root),
        'workflow_index': str(workflow_root / 'WORKFLOW_INDEX.json'),
        'renpy_sdk_exe': str(tmp_path / 'renpy.exe'),
        'obsidian_vault': str(tmp_path / 'vault'),
    }
    (project / 'docs/automation/project_contract.json').write_text(json.dumps(contract), encoding='utf-8')
    return project, game


def test_config_resolves_arbitrary_project_root(tmp_path: Path):
    sys.path.insert(0, str(TOOLS))
    from vn_product_config import build_project_paths

    project, game = make_min_project(tmp_path)
    paths = build_project_paths(project)
    assert paths.project_root == project.resolve()
    assert paths.game_dir == game.resolve()
    assert paths.manifest == (game / 'data/asset_manifest.json').resolve()
    assert paths.promotions_root == (project / 'docs/production/promotions').resolve()


def test_asset_ref_checker_accepts_generic_project_root(tmp_path: Path):
    project, _ = make_min_project(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(TOOLS / 'check_renpy_asset_refs.py'), '--project-root', str(project)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'ALL_RENPY_ASSET_REFS_EXIST' in proc.stdout


def test_integration_gap_report_accepts_generic_project_root(tmp_path: Path):
    project, _ = make_min_project(tmp_path)
    report_path = project / 'docs/automation/gap.json'
    proc = subprocess.run(
        [sys.executable, str(TOOLS / 'report_renpy_integration_gaps.py'), '--project-root', str(project), '--json-out', str(report_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert report['counts']['integrated'] == 1
    assert report['counts']['missing_file'] == 0
    assert str(project.resolve()) == report['project_root']
