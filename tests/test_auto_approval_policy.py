from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/auto_approve_candidate.py'


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / 'project'
    write_json(project / 'docs/automation/project_contract.json', {
        'project_root': str(project),
        'renpy_game_dir': str(project / 'game'),
        'manifest_path': str(project / 'game/data/asset_manifest.json'),
    })
    write_json(project / 'game/data/asset_manifest.json', {'assets': []})
    return project


def run_auto(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), '--project-root', str(project), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def base_policy(project: Path) -> Path:
    return write_json(project / 'docs/automation/auto_approval_policy.json', {
        'policy_version': '1.0',
        'default_mode': 'delegated_auto_with_gates',
        'asset_type_rules': {
            'scene_local_background_replacement': {
                'auto_approve': True,
                'allowed_scope': 'scene_local',
                'asset_types': ['background'],
                'requires_scene_local': True,
                'min_scores': {
                    'semantic_fit': 4,
                    'mobile_portrait_composition': 4,
                    'textbox_safety': 4,
                    'artifact_absence': 4,
                    'scene_purpose_fit': 4
                }
            }
        },
        'human_gate_asset_types': ['character_base', 'event_cg', 'main_ui_identity'],
        'hard_rejects': ['fake dialogue box', 'readable fake text', 'watermark'],
        'required_gates_for_auto_promotion': [
            'file_qa_pass',
            'vision_scorecard_pass',
            'renpy_lint_pass',
            'toolkit_validate_pass',
            'scene_guard_pass',
            'gameplay_capture_pass',
            'obsidian_audit_pass',
            'rollback_point_exists'
        ]
    })


def test_auto_approve_allows_scene_local_background_when_all_gates_pass(tmp_path: Path):
    project = make_project(tmp_path)
    policy = base_policy(project)
    metadata = write_json(project / 'docs/automation/generation_runs/run/metadata.json', {
        'asset_id': 'bg_room_portrait_v01',
        'asset_type': 'background',
        'scene_id': 'scene_001_opening',
        'candidate_copies': ['docs/automation/generated_candidates/run/candidate_01.png'],
    })
    file_qa = write_json(project / 'docs/validation/run/file_qa.json', {'status': 'pass'})
    scorecard = write_json(project / 'docs/validation/run/vision_scorecard.json', {
        'asset_id': 'bg_room_portrait_v01',
        'candidate_id': 'candidate_01',
        'semantic_fit': 5,
        'mobile_portrait_composition': 5,
        'textbox_safety': 5,
        'artifact_absence': 4,
        'scene_purpose_fit': 5,
        'promotion_blocker': False,
        'observed_issues': []
    })
    gates = write_json(project / 'docs/validation/run/gates.json', {
        'renpy_lint_pass': True,
        'toolkit_validate_pass': True,
        'scene_guard_pass': True,
        'gameplay_capture_pass': True,
        'obsidian_audit_pass': True,
        'rollback_point_exists': True
    })
    out = project / 'docs/validation/run/auto_approval.json'

    proc = run_auto(
        project,
        '--approval-class', 'scene_local_background_replacement',
        '--candidate-metadata', str(metadata),
        '--file-qa', str(file_qa),
        '--vision-scorecard', str(scorecard),
        '--gate-report', str(gates),
        '--policy', str(policy),
        '--out', str(out),
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    decision = json.loads(out.read_text(encoding='utf-8'))
    assert decision['decision'] == 'approve'
    assert decision['allowed_to_promote'] is True
    assert decision['allowed_to_integrate'] is True
    assert decision['approval_mode'] == 'delegated_auto'
    assert decision['allowed_scope'] == 'scene_local'


def test_auto_approve_rejects_hard_blocker_even_when_scores_pass(tmp_path: Path):
    project = make_project(tmp_path)
    policy = base_policy(project)
    metadata = write_json(project / 'docs/automation/generation_runs/run/metadata.json', {
        'asset_id': 'bg_room_portrait_v01',
        'asset_type': 'background',
        'scene_id': 'scene_001_opening',
    })
    file_qa = write_json(project / 'docs/validation/run/file_qa.json', {'status': 'pass'})
    scorecard = write_json(project / 'docs/validation/run/vision_scorecard.json', {
        'semantic_fit': 5,
        'mobile_portrait_composition': 5,
        'textbox_safety': 5,
        'artifact_absence': 5,
        'scene_purpose_fit': 5,
        'promotion_blocker': False,
        'observed_issues': ['fake dialogue box']
    })
    gates = write_json(project / 'docs/validation/run/gates.json', {
        'renpy_lint_pass': True,
        'toolkit_validate_pass': True,
        'scene_guard_pass': True,
        'gameplay_capture_pass': True,
        'obsidian_audit_pass': True,
        'rollback_point_exists': True
    })

    proc = run_auto(
        project,
        '--approval-class', 'scene_local_background_replacement',
        '--candidate-metadata', str(metadata),
        '--file-qa', str(file_qa),
        '--vision-scorecard', str(scorecard),
        '--gate-report', str(gates),
        '--policy', str(policy),
    )

    assert proc.returncode == 1
    assert 'decision reject' in proc.stdout
    assert 'fake dialogue box' in proc.stdout


def test_auto_approve_ignores_negated_hard_reject_words_in_caveats_and_verdict(tmp_path: Path):
    project = make_project(tmp_path)
    policy = base_policy(project)
    metadata = write_json(project / 'docs/automation/generation_runs/run/metadata.json', {
        'asset_id': 'bg_salon_portrait_v01',
        'asset_type': 'background',
        'scene_id': 'scene_001_opening',
    })
    file_qa = write_json(project / 'docs/validation/run/file_qa.json', {'status': 'pass'})
    scorecard = write_json(project / 'docs/validation/run/vision_scorecard.json', {
        'semantic_fit': 5,
        'mobile_portrait_composition': 5,
        'textbox_safety': 5,
        'artifact_absence': 5,
        'scene_purpose_fit': 5,
        'promotion_blocker': False,
        'observed_issues': [],
        'caveats': ['No readable fake text or watermark observed; envelopes are textless.'],
        'verdict': 'ACCEPT: no humans/fake UI/readable fake text/watermark.'
    })
    gates = write_json(project / 'docs/validation/run/gates.json', {
        'renpy_lint_pass': True,
        'toolkit_validate_pass': True,
        'scene_guard_pass': True,
        'gameplay_capture_pass': True,
        'obsidian_audit_pass': True,
        'rollback_point_exists': True
    })

    proc = run_auto(
        project,
        '--approval-class', 'scene_local_background_replacement',
        '--candidate-metadata', str(metadata),
        '--file-qa', str(file_qa),
        '--vision-scorecard', str(scorecard),
        '--gate-report', str(gates),
        '--policy', str(policy),
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'decision approve' in proc.stdout


def test_auto_approve_requires_human_for_gated_asset_type(tmp_path: Path):
    project = make_project(tmp_path)
    policy = base_policy(project)
    metadata = write_json(project / 'docs/automation/generation_runs/run/metadata.json', {
        'asset_id': 'serena_base',
        'asset_type': 'character_base',
        'scene_id': 'scene_001_opening',
    })
    file_qa = write_json(project / 'docs/validation/run/file_qa.json', {'status': 'pass'})
    scorecard = write_json(project / 'docs/validation/run/vision_scorecard.json', {
        'semantic_fit': 5,
        'mobile_portrait_composition': 5,
        'textbox_safety': 5,
        'artifact_absence': 5,
        'scene_purpose_fit': 5,
        'promotion_blocker': False,
        'observed_issues': []
    })
    gates = write_json(project / 'docs/validation/run/gates.json', {
        'renpy_lint_pass': True,
        'toolkit_validate_pass': True,
        'scene_guard_pass': True,
        'gameplay_capture_pass': True,
        'obsidian_audit_pass': True,
        'rollback_point_exists': True
    })

    proc = run_auto(
        project,
        '--approval-class', 'scene_local_background_replacement',
        '--candidate-metadata', str(metadata),
        '--file-qa', str(file_qa),
        '--vision-scorecard', str(scorecard),
        '--gate-report', str(gates),
        '--policy', str(policy),
    )

    assert proc.returncode == 1
    assert 'decision review_required' in proc.stdout
    assert 'human-gated asset_type' in proc.stdout
