from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/resolve_asset_requests.py'


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run_resolver(project: Path, requests: Path, out: Path):
    return subprocess.run([
        sys.executable,
        str(SCRIPT),
        str(requests),
        '--project-root',
        str(project),
        '--out',
        str(out),
    ], cwd=ROOT, text=True, capture_output=True)


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / 'project'
    game = project / 'game'
    bg = game / 'images/backgrounds/classroom_morning.png'
    bg.parent.mkdir(parents=True, exist_ok=True)
    bg.write_bytes(b'png-ish')

    write_json(project / 'docs/automation/project_contract.json', {
        'workflow_routes': {
            'background': 'scene_background',
            'event_cg': 'scene_event_cg',
            'sfx': 'audio_sfx_mmaudio',
        }
    })
    write_json(project / 'game/data/asset_manifest.json', {
        'version': '1.0.0',
        'assets': [{
            'asset_id': 'bg_classroom_morning',
            'asset_type': 'background',
            'workflow_id': 'scene_background',
            'promoted_path': 'images/backgrounds/classroom_morning.png',
            'renpy_name': 'bg classroom_morning',
            'qa_status': 'owner_approved_promoted',
        }],
    })
    return project


def test_resolver_reuses_manifest_candidate_or_recommends_generation(tmp_path: Path):
    project = make_project(tmp_path)

    candidate = project / 'docs/automation/generated_candidates/event_cg/run_event/pause.png'
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b'candidate')
    write_json(project / 'docs/automation/generation_runs/run_event/metadata.json', {
        'run_id': 'run_event',
        'asset_type': 'scene_event_cg',
        'workflow_id': 'scene_event_cg',
        'positive_prompt': 'Seoha hesitates before the first choice pause in classroom',
        'candidate_copies': [str(candidate)],
        'qa_status': 'qa_warn_pass_candidate_not_promoted',
        'promotion_status': 'not_promoted_pending_owner_approval',
        'seed': 123,
    })

    # Weak type-compatible candidates should not block fresh generation for unrelated requests.
    weak_sfx = project / 'docs/automation/generated_candidates/sfx/run_sfx/door.flac'
    weak_sfx.parent.mkdir(parents=True, exist_ok=True)
    weak_sfx.write_bytes(b'audio')
    write_json(project / 'docs/automation/generation_runs/run_sfx/metadata.json', {
        'run_id': 'run_sfx',
        'asset_type': 'sfx',
        'workflow_id': 'audio_sfx_mmaudio',
        'positive_prompt': 'soft door knock in classroom',
        'candidate_copies': [str(weak_sfx)],
        'qa_status': 'qa_pass_candidate_not_promoted',
        'promotion_status': 'not_promoted_pending_owner_approval',
    })

    # A same-type candidate with a different explicit asset_id must not appear under this request.
    wrong_bg = project / 'docs/automation/generated_candidates/backgrounds/run_bg_variant/cafe.png'
    wrong_bg.parent.mkdir(parents=True, exist_ok=True)
    wrong_bg.write_bytes(b'candidate')
    write_json(project / 'docs/automation/generation_runs/run_bg_variant/metadata.json', {
        'run_id': 'run_bg_variant',
        'asset_id': 'bg_classroom_morning_v2',
        'asset_type': 'background',
        'workflow_id': 'scene_background',
        'positive_prompt': 'classroom morning variant with overlapping tokens',
        'candidate_copies': [str(wrong_bg)],
        'qa_status': 'qa_pass_candidate_not_promoted',
        'promotion_status': 'not_promoted_pending_owner_approval',
    })

    requests = project / 'docs/production/asset_requests/sample.asset_requests.json'
    write_json(requests, {
        'scene_id': 'sample',
        'asset_requests': [
            {'asset_id': 'bg_classroom_morning', 'asset_type': 'background', 'description': 'existing classroom'},
            {'asset_id': 'event_cg_seoha_choice_pause', 'asset_type': 'event_cg', 'description': 'Seoha hesitates before the first choice'},
            {'asset_id': 'sfx_paper_slide_soft', 'asset_type': 'sfx', 'description': 'soft paper sliding across a classroom desk'},
        ],
    })
    out = tmp_path / 'resolved.json'
    proc = run_resolver(project, requests, out)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'reuse_manifest 1' in proc.stdout
    assert 'review_existing_candidate 1' in proc.stdout
    assert 'generate 1' in proc.stdout

    data = json.loads(out.read_text(encoding='utf-8'))
    decisions = {item['asset_id']: item for item in data['resolved_asset_requests']}
    assert decisions['bg_classroom_morning']['decision'] == 'reuse_manifest'
    assert decisions['bg_classroom_morning']['status'] == 'resolved'
    assert decisions['event_cg_seoha_choice_pause']['decision'] == 'review_existing_candidate'
    assert decisions['event_cg_seoha_choice_pause']['candidate_matches'][0]['run_id'] == 'run_event'
    assert decisions['sfx_paper_slide_soft']['decision'] == 'generate'
    assert decisions['sfx_paper_slide_soft']['recommended_workflow_id'] == 'audio_sfx_mmaudio'


def test_resolver_blocks_manifest_hit_with_missing_file(tmp_path: Path):
    project = make_project(tmp_path)
    manifest_path = project / 'game/data/asset_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['assets'][0]['promoted_path'] = 'images/backgrounds/missing.png'
    write_json(manifest_path, manifest)

    requests = tmp_path / 'requests.json'
    write_json(requests, {
        'scene_id': 'sample',
        'asset_requests': [{'asset_id': 'bg_classroom_morning', 'asset_type': 'background'}],
    })
    out = tmp_path / 'resolved.json'
    proc = run_resolver(project, requests, out)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    item = data['resolved_asset_requests'][0]
    assert item['decision'] == 'blocked_manifest_missing_file'
    assert item['status'] == 'blocked'
    assert item['manifest_matches'][0]['file_exists'] is False
