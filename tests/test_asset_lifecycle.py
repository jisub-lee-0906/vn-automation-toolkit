from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMOTE_SCRIPT = ROOT / 'tools/promote_asset_candidate.py'
NORMALIZE_SCRIPT = ROOT / 'tools/normalize_asset_lifecycle.py'


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / 'portable_title'
    game = project / 'game'
    workflow = tmp_path / 'workflow_pack'
    workflow.mkdir(parents=True, exist_ok=True)
    write_json(workflow / 'WORKFLOW_INDEX.json', {'workflows': []})
    obs_root = tmp_path / 'obsidian' / 'portable_title' / 'VN'
    (obs_root / 'Scenes').mkdir(parents=True, exist_ok=True)
    write_json(project / 'docs/automation/project_contract.json', {
        'game_title': 'Portable Title',
        'game_slug': 'portable_title',
        'obsidian_vault': (tmp_path / 'obsidian').as_posix(),
        'obsidian_project_root': obs_root.as_posix(),
        'obsidian_scenes_glob': 'Scenes/*.md',
        'renpy_project_root': project.as_posix(),
        'renpy_game_dir': game.as_posix(),
        'renpy_sdk_exe': '',
        'workflow_pack_root': workflow.as_posix(),
        'workflow_index': (workflow / 'WORKFLOW_INDEX.json').as_posix(),
        'manifest_path': (game / 'data/asset_manifest.json').as_posix(),
    })
    write_json(game / 'data/asset_manifest.json', {'version': '1.0.0', 'assets': []})
    return project


def test_promote_writes_canonical_lifecycle_stage_to_manifest_and_metadata(tmp_path: Path):
    project = make_project(tmp_path)
    candidate = project / 'docs/automation/generated_candidates/bg_test/candidate.png'
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b'fake image')
    metadata = project / 'docs/automation/generation_runs/bg_test/metadata.json'
    write_json(metadata, {
        'run_id': 'bg_test',
        'asset_id': 'bg_test',
        'asset_type': 'background',
        'workflow_id': 'scene_background',
        'candidate_copies': [candidate.as_posix()],
        'qa_status': 'qa_pass_candidate_not_promoted',
        'promotion_status': 'not_promoted_pending_owner_approval',
    })
    qa = project / 'docs/automation/qa_reports/bg_test_file_qa.json'
    write_json(qa, {'status': 'pass', 'path': candidate.as_posix()})

    proc = subprocess.run([
        sys.executable, str(PROMOTE_SCRIPT), str(metadata),
        '--project-root', str(project),
        '--asset-id', 'bg_test',
        '--renpy-name', 'bg test',
        '--approved',
        '--qa-report', str(qa),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = json.loads((project / 'game/data/asset_manifest.json').read_text(encoding='utf-8'))
    entry = manifest['assets'][0]
    assert entry['lifecycle_stage'] == 'promoted_integrated_pending_verification'
    assert entry['metadata']['lifecycle_stage'] == 'promoted_integrated_pending_verification'
    saved_metadata = json.loads(metadata.read_text(encoding='utf-8'))
    assert saved_metadata['lifecycle_stage'] == 'promoted_integrated_pending_verification'


def test_normalize_asset_lifecycle_backfills_legacy_manifest_statuses(tmp_path: Path):
    project = make_project(tmp_path)
    promoted = project / 'game/images/backgrounds/bg_done.png'
    promoted.parent.mkdir(parents=True, exist_ok=True)
    promoted.write_bytes(b'img')
    write_json(project / 'game/data/asset_manifest.json', {
        'version': '1.0.0',
        'assets': [{
            'asset_id': 'bg_done',
            'asset_type': 'background',
            'workflow_id': 'scene_background',
            'generated_path': 'docs/automation/generated_candidates/bg_done.png',
            'promoted_path': 'images/backgrounds/bg_done.png',
            'qa_status': 'approved_promoted_scene_integrated_verified',
            'renpy_name': 'bg done',
            'scene_usage': ['scene_start'],
            'metadata': {},
        }],
    })

    proc = subprocess.run([
        sys.executable, str(NORMALIZE_SCRIPT), '--project-root', str(project), '--write'
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'updated 1' in proc.stdout
    manifest = json.loads((project / 'game/data/asset_manifest.json').read_text(encoding='utf-8'))
    entry = manifest['assets'][0]
    assert entry['lifecycle_stage'] == 'promoted_integrated_verified'
    assert entry['metadata']['legacy_qa_status'] == 'approved_promoted_scene_integrated_verified'


def test_validate_rejects_unknown_lifecycle_stage(tmp_path: Path):
    project = make_project(tmp_path)
    promoted = project / 'game/images/backgrounds/bg_bad.png'
    promoted.parent.mkdir(parents=True, exist_ok=True)
    promoted.write_bytes(b'img')
    write_json(project / 'game/data/asset_manifest.json', {
        'version': '1.0.0',
        'assets': [{
            'asset_id': 'bg_bad',
            'asset_type': 'background',
            'workflow_id': 'scene_background',
            'generated_path': 'docs/automation/generated_candidates/bg_bad.png',
            'promoted_path': 'images/backgrounds/bg_bad.png',
            'qa_status': 'owner_approved_promoted',
            'renpy_name': 'bg bad',
            'scene_usage': [],
            'metadata': {},
            'lifecycle_stage': 'almost_done_but_not_canonical',
        }],
    })
    # Add minimum docs so this test isolates manifest lifecycle validation.
    for rel in [
        'docs/automation/vn_automation_design.md',
        'docs/automation/templates/Scene_Note_Template.md',
        'docs/automation/templates/Character_Note_Template.md',
        'docs/automation/templates/Asset_Request_Template.md',
        'docs/automation/qa_checklist.md',
        'docs/automation/schemas/asset_manifest.schema.json',
        'docs/automation/schemas/character_asset.schema.json',
    ]:
        p = project / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('## 1. 목표\n## 2. 고정 경로\n## 3. 역할 분담\n## 4. 데이터 흐름\n## 7. Workflow routing\n## 11. QA gates\n## 13. 첫 투입 milestone\n## 14. 금지 사항\n', encoding='utf-8')

    proc = subprocess.run([
        sys.executable, '-m', 'vn_automation.cli', 'validate', '--project-root', str(project), '--skip-obsidian'
    ], cwd=ROOT, text=True, capture_output=True, env={**__import__('os').environ, 'PYTHONPATH': str(ROOT)})

    assert proc.returncode == 1
    assert 'unknown lifecycle_stage' in proc.stdout + proc.stderr
