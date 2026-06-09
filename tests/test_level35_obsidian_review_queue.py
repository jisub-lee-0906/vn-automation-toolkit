from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT_SCRIPT = ROOT / 'tools/extract_asset_requests_from_scene_note.py'
SYNC_SCRIPT = ROOT / 'tools/sync_obsidian_scene_asset_requests.py'
QUEUE_SCRIPT = ROOT / 'tools/build_owner_review_queue.py'


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def test_extract_supports_obsidian_checkbox_required_assets(tmp_path: Path):
    note = tmp_path / 'scene.md'
    note.write_text(
        '# Seoha Choice Pause\n\n'
        '## Required Assets\n\n'
        '- [ ] background: bg_classroom_evening | Evening classroom after club activities\n'
        '- [x] event_cg: event_cg_seoha_choice_pause | Seoha hesitates before the first choice\n'
        '- [ ] sfx: sfx_door_knock_soft\n',
        encoding='utf-8',
    )
    out = tmp_path / 'requests.json'
    proc = subprocess.run([
        sys.executable, str(EXTRACT_SCRIPT), str(note), '--scene-id', 'seoha_choice_pause', '--out', str(out)
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    assert [item['asset_id'] for item in data['asset_requests']] == [
        'bg_classroom_evening',
        'event_cg_seoha_choice_pause',
        'sfx_door_knock_soft',
    ]
    assert data['asset_requests'][0]['asset_type'] == 'background'
    assert data['asset_requests'][0]['description'] == 'Evening classroom after club activities'
    assert data['asset_requests'][1]['asset_type'] == 'event_cg'
    assert data['asset_requests'][1]['required'] is True
    assert data['asset_requests'][2]['asset_type'] == 'sfx'


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / 'project'
    bg = project / 'game/images/backgrounds/classroom_evening.png'
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
            'asset_id': 'bg_classroom_evening',
            'asset_type': 'background',
            'workflow_id': 'scene_background',
            'promoted_path': 'images/backgrounds/classroom_evening.png',
            'renpy_name': 'bg classroom_evening',
            'qa_status': 'owner_approved_promoted',
        }],
    })
    candidate = project / 'docs/automation/generated_candidates/event/run/pause.png'
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b'candidate')
    write_json(project / 'docs/automation/generation_runs/run_event/metadata.json', {
        'run_id': 'run_event',
        'asset_type': 'scene_event_cg',
        'workflow_id': 'scene_event_cg',
        'positive_prompt': 'Seoha hesitates before the first choice pause',
        'candidate_copies': [str(candidate)],
        'qa_status': 'qa_warn_pass_candidate_not_promoted',
        'promotion_status': 'not_promoted_pending_owner_approval',
        'seed': 123,
    })
    return project


def test_sync_obsidian_scene_notes_extracts_and_resolves_batch(tmp_path: Path):
    project = make_project(tmp_path)
    vault = tmp_path / 'Obsidian Vault'
    scenes = vault / 'VN/Scenes'
    scenes.mkdir(parents=True)
    (scenes / 'seoha_choice_pause.md').write_text(
        '---\nscene_id: seoha_choice_pause\n---\n'
        '# Seoha Choice Pause\n\n'
        '## Required Assets\n\n'
        '- [ ] background: bg_classroom_evening | Evening classroom after club activities\n'
        '- [ ] event_cg: event_cg_seoha_choice_pause | Seoha hesitates before the first choice\n'
        '- [ ] sfx: sfx_door_knock_soft | soft knock\n',
        encoding='utf-8',
    )
    (scenes / 'empty.md').write_text('# Empty\n\nNo required assets.\n', encoding='utf-8')

    summary = project / 'docs/automation/batch.json'
    proc = subprocess.run([
        sys.executable, str(SYNC_SCRIPT),
        '--project-root', str(project),
        '--vault', str(vault),
        '--notes-glob', 'VN/Scenes/*.md',
        '--out-summary', str(summary),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'processed 1' in proc.stdout
    data = json.loads(summary.read_text(encoding='utf-8'))
    assert data['counts']['processed'] == 1
    assert data['scenes'][0]['scene_id'] == 'seoha_choice_pause'
    resolved = Path(data['scenes'][0]['resolved_asset_requests_path'])
    decisions = {item['asset_id']: item['decision'] for item in json.loads(resolved.read_text(encoding='utf-8'))['resolved_asset_requests']}
    assert decisions == {
        'bg_classroom_evening': 'reuse_manifest',
        'event_cg_seoha_choice_pause': 'review_existing_candidate',
        'sfx_door_knock_soft': 'generate',
    }


def test_build_owner_review_queue_from_resolved_requests(tmp_path: Path):
    project = make_project(tmp_path)
    resolved = project / 'docs/production/asset_requests/seoha_choice_pause.resolved_asset_requests.json'
    write_json(resolved, {
        'scene_id': 'seoha_choice_pause',
        'resolved_asset_requests': [
            {'asset_id': 'bg_classroom_evening', 'asset_type': 'background', 'decision': 'reuse_manifest', 'status': 'resolved'},
            {
                'asset_id': 'event_cg_seoha_choice_pause',
                'asset_type': 'event_cg',
                'decision': 'review_existing_candidate',
                'status': 'needs_owner_review',
                'recommended_workflow_id': 'scene_event_cg',
                'candidate_matches': [{
                    'run_id': 'run_event',
                    'candidate_files': [str(project / 'docs/automation/generated_candidates/event/run/pause.png')],
                    'qa_status': 'qa_warn_pass_candidate_not_promoted',
                    'score': 3,
                }],
            },
            {
                'asset_id': 'sfx_door_knock_soft',
                'asset_type': 'sfx',
                'decision': 'generate',
                'status': 'needs_generation',
                'recommended_workflow_id': 'audio_sfx_mmaudio',
            },
        ],
    })
    out_md = project / 'docs/production/owner_review_queue.md'
    out_json = project / 'docs/production/owner_review_queue.json'
    proc = subprocess.run([
        sys.executable, str(QUEUE_SCRIPT),
        '--project-root', str(project),
        '--resolved-glob', 'docs/production/asset_requests/*.resolved_asset_requests.json',
        '--out-md', str(out_md),
        '--out-json', str(out_json),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'review_items 1' in proc.stdout
    assert 'generation_items 1' in proc.stdout
    text = out_md.read_text(encoding='utf-8')
    assert 'event_cg_seoha_choice_pause' in text
    assert 'approve_candidate_id' in text
    assert 'sfx_door_knock_soft' in text
    data = json.loads(out_json.read_text(encoding='utf-8'))
    assert data['counts'] == {'review_items': 1, 'generation_items': 1, 'blocked_items': 0}
