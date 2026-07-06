from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, '-m', 'vn_automation.cli', *args], cwd=ROOT, text=True, capture_output=True)


def test_enrichment_queue_writes_resolved_requests_and_prompt_slots(tmp_path: Path):
    project = make_project(tmp_path)
    enrichment = write_json(project / 'docs/automation/scene_enrichment/scene.json', {
        'scene_id': 'scene_003_first_clue_field',
        'candidate_batches': [
            {'asset_type': 'background', 'role': 'records room branch identity', 'count': 2, 'promotion': 'delegated_auto_possible'},
            {'asset_type': 'bgm', 'role': 'quiet investigation loop', 'count': 1, 'promotion': 'delegated_auto_possible'},
            {'asset_type': 'sfx', 'role': 'paper clue reveal', 'count': 1, 'promotion': 'delegated_auto_possible'},
            {'asset_type': 'prop_cg', 'role': 'missing roster line clue', 'count': 1, 'promotion': 'human_review_required'},
            {'asset_type': 'event_cg', 'role': 'Serena points at clue', 'count': 1, 'promotion': 'human_gated'},
        ],
    })
    out = project / 'docs/production/asset_requests/scene_003_first_clue_field.enrichment.resolved_asset_requests.json'
    proc = run_cli('enrichment-queue', '--project-root', str(project), '--enrichment-plan', str(enrichment), '--out', str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    items = data['resolved_asset_requests']
    assert len(items) == 6
    bg = next(item for item in items if item['asset_type'] == 'background')
    assert bg['decision'] == 'generate'
    assert bg['recommended_workflow_id'] == 'scene_background'
    assert Path(bg['prompt_slots_path']).exists()
    bg_slots = json.loads(Path(bg['prompt_slots_path']).read_text(encoding='utf-8'))
    assert bg_slots['workflow_id'] == 'scene_background'
    assert bg_slots['prompt_slots']['background_theme']
    assert 'visual_novel' not in bg_slots['prompt_slots']['background_theme']
    assert 'dialogue_box' in bg_slots['prompt_slots']['negative_tags']
    assert 'text_focus' in bg_slots['prompt_slots']['negative_tags']
    audio = next(item for item in items if item['asset_type'] == 'bgm')
    audio_slots = json.loads(Path(audio['prompt_slots_path']).read_text(encoding='utf-8'))
    assert 'instrumental visual novel background music' in audio_slots['prompt_slots']['positive_prompt']
    event = next(item for item in items if item['asset_type'] == 'event_cg')
    assert event['decision'] == 'hold_for_source_metadata'
    assert event['recommended_workflow_id'] == 'scene_event_cg'


def test_enrichment_queue_refuses_outside_out_path(tmp_path: Path):
    project = make_project(tmp_path)
    enrichment = write_json(project / 'docs/automation/scene_enrichment/scene.json', {'scene_id': 's', 'candidate_batches': []})
    proc = run_cli('enrichment-queue', '--project-root', str(project), '--enrichment-plan', str(enrichment), '--out', str(tmp_path / 'outside.json'))
    assert proc.returncode == 2
