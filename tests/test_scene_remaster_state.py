from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import scene_remaster_state  # noqa: E402


def write_contract(root: Path) -> None:
    (root / 'docs/automation').mkdir(parents=True)
    (root / 'game').mkdir()
    (root / 'docs/automation/project_contract.json').write_text(json.dumps({
        'project_root': str(root),
        'renpy_project_root': str(root),
        'renpy_game_dir': str(root / 'game'),
    }), encoding='utf-8')


def test_scene_remaster_state_writes_state_patch_and_pool(tmp_path: Path) -> None:
    write_contract(tmp_path)
    qa = tmp_path / 'docs/validation/scene001/report.md'
    qa.parent.mkdir(parents=True)
    qa.write_text('# QA\n', encoding='utf-8')
    candidate = tmp_path / 'docs/automation/audio_regen_20260613/recommended_review_audio/sfx_red_system_alert_v2.mp3'
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b'audio')

    rc = scene_remaster_state.main([
        '--project-root', str(tmp_path),
        '--scene-id', 'scene_001_red_system_contract',
        '--patch-id', 'scene001_patch1',
        '--status', 'owner_review_pending',
        '--asset-policy', 'scene_local_preview_only',
        '--changed-file', 'game/script.rpy',
        '--qa-report', str(qa),
        '--known-blocker', 'menu capture needs proof',
        '--next-step', 'contract feedback polish',
        '--candidate', f'sfx_red_system_alert_v2|audio|{candidate}|Scene 001 alert preview only',
    ])
    assert rc == 0
    base = tmp_path / 'docs/automation/scene_remaster'
    state = json.loads((base / 'states/scene_001_red_system_contract.json').read_text(encoding='utf-8'))
    assert state['latest_patch_id'] == 'scene001_patch1'
    assert state['permanent_asset_changes'] is False
    assert state['latest_qa_report'] == 'docs/validation/scene001/report.md'
    assert state['candidate_count'] == 1
    patch = json.loads((base / 'patches/scene001_patch1.json').read_text(encoding='utf-8'))
    assert patch['asset_policy'] == 'scene_local_preview_only'
    pool = json.loads((base / 'scene_pools/scene_001_red_system_contract.json').read_text(encoding='utf-8'))
    assert pool['global_replacement_allowed'] is False
    assert pool['promotion_requires_owner_approval'] is True
    assert pool['candidates'][0]['promotion_allowed'] is False


def test_scene_remaster_state_refuses_unapproved_permanent_asset_change(tmp_path: Path) -> None:
    write_contract(tmp_path)
    rc = scene_remaster_state.main([
        '--project-root', str(tmp_path),
        '--scene-id', 'scene_001_red_system_contract',
        '--patch-id', 'scene001_patch1',
        '--status', 'owner_review_pending',
        '--asset-policy', 'scene_local_preview_only',
        '--permanent-asset-changes',
    ])
    assert rc == 2


def test_scene_remaster_state_check_existing_passes_without_writing(tmp_path: Path) -> None:
    write_contract(tmp_path)
    base = tmp_path / 'docs/automation/scene_remaster'
    qa = tmp_path / 'docs/validation/scene001/report.md'
    guard = tmp_path / 'docs/validation/scene001/guard.json'
    sheet = tmp_path / 'docs/validation/scene001/contact_sheet.png'
    candidate = tmp_path / 'docs/automation/audio_regen_20260613/recommended_review_audio/sfx_red_system_alert_v2.mp3'
    for path in [qa, guard, sheet, candidate]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'ok')
    pool = base / 'scene_pools/scene_001_red_system_contract.json'
    patch = base / 'patches/scene001_patch1.json'
    pool.parent.mkdir(parents=True)
    patch.parent.mkdir(parents=True)
    pool.write_text(json.dumps({
        'schema_version': 1,
        'scene_id': 'scene_001_red_system_contract',
        'policy': 'scene_local_preview_only',
        'global_replacement_allowed': False,
        'promotion_requires_owner_approval': True,
        'candidates': [{
            'candidate_id': 'sfx_red_system_alert_v2',
            'asset_type': 'audio',
            'path': 'docs/automation/audio_regen_20260613/recommended_review_audio/sfx_red_system_alert_v2.mp3',
            'purpose': 'preview only',
            'status': 'preview_reference_only',
            'approved': False,
            'promotion_allowed': False,
        }],
    }), encoding='utf-8')
    patch.write_text(json.dumps({
        'schema_version': 1,
        'patch_id': 'scene001_patch1',
        'scene_id': 'scene_001_red_system_contract',
        'status': 'owner_review_pending',
        'approval_status': 'pending',
        'asset_policy': 'scene_local_preview_only',
        'permanent_asset_changes': False,
        'qa_report': 'docs/validation/scene001/report.md',
        'guard_report': 'docs/validation/scene001/guard.json',
        'capture_sheets': ['docs/validation/scene001/contact_sheet.png'],
        'scene_pool': 'docs/automation/scene_remaster/scene_pools/scene_001_red_system_contract.json',
    }), encoding='utf-8')
    current = base / 'current_state.json'
    current.write_text(json.dumps({
        'schema_version': 1,
        'scene_id': 'scene_001_red_system_contract',
        'status': 'owner_review_pending',
        'latest_patch_id': 'scene001_patch1',
        'approval_status': 'pending',
        'asset_policy': 'scene_local_preview_only',
        'permanent_asset_changes': False,
        'latest_qa_report': 'docs/validation/scene001/report.md',
        'latest_guard_report': 'docs/validation/scene001/guard.json',
        'capture_sheets': ['docs/validation/scene001/contact_sheet.png'],
        'patch_manifest': 'docs/automation/scene_remaster/patches/scene001_patch1.json',
        'scene_pool': 'docs/automation/scene_remaster/scene_pools/scene_001_red_system_contract.json',
        'candidate_count': 1,
    }), encoding='utf-8')
    before = current.read_text(encoding='utf-8')

    rc = scene_remaster_state.main([
        '--project-root', str(tmp_path),
        '--scene-id', 'scene_001_red_system_contract',
        '--check-existing',
    ])

    assert rc == 0
    assert current.read_text(encoding='utf-8') == before


def test_scene_remaster_state_check_existing_fails_unsafe_pool(tmp_path: Path) -> None:
    write_contract(tmp_path)
    base = tmp_path / 'docs/automation/scene_remaster'
    qa = tmp_path / 'docs/validation/scene001/report.md'
    guard = tmp_path / 'docs/validation/scene001/guard.json'
    qa.parent.mkdir(parents=True, exist_ok=True)
    qa.write_text('# QA\n', encoding='utf-8')
    guard.write_text('{}\n', encoding='utf-8')
    pool = base / 'scene_pools/scene_001_red_system_contract.json'
    patch = base / 'patches/scene001_patch1.json'
    pool.parent.mkdir(parents=True)
    patch.parent.mkdir(parents=True)
    pool.write_text(json.dumps({
        'scene_id': 'scene_001_red_system_contract',
        'policy': 'scene_local_preview_only',
        'global_replacement_allowed': True,
        'promotion_requires_owner_approval': True,
        'candidates': [],
    }), encoding='utf-8')
    patch.write_text(json.dumps({
        'scene_id': 'scene_001_red_system_contract',
        'asset_policy': 'scene_local_preview_only',
        'permanent_asset_changes': False,
        'qa_report': 'docs/validation/scene001/report.md',
        'guard_report': 'docs/validation/scene001/guard.json',
    }), encoding='utf-8')
    (base / 'current_state.json').write_text(json.dumps({
        'scene_id': 'scene_001_red_system_contract',
        'asset_policy': 'scene_local_preview_only',
        'permanent_asset_changes': False,
        'latest_qa_report': 'docs/validation/scene001/report.md',
        'latest_guard_report': 'docs/validation/scene001/guard.json',
        'patch_manifest': 'docs/automation/scene_remaster/patches/scene001_patch1.json',
        'scene_pool': 'docs/automation/scene_remaster/scene_pools/scene_001_red_system_contract.json',
    }), encoding='utf-8')

    rc = scene_remaster_state.main([
        '--project-root', str(tmp_path),
        '--scene-id', 'scene_001_red_system_contract',
        '--check-existing',
    ])

    assert rc == 1
