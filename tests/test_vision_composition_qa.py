from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/vision_composition_qa.py'


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


def run_qa(project: Path, scorecard: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), '--project-root', str(project), '--scorecard', str(scorecard), '--out', str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def base_scorecard() -> dict:
    return {
        'scene_id': 'scene_003_field_backgrounds',
        'asset_ids': ['bg_records_room_portrait_v01', 'bg_west_corridor_portrait_v01'],
        'qa_type': 'vision_composition',
        'uncertainty': 'low',
        'decision': 'pass',
        'blockers': [],
        'captures': [
            {
                'name': 'records_room_entry',
                'screenshot': 'docs/validation/run/records.png',
                'scores': {
                    'character_positioning': 5,
                    'character_scale': 5,
                    'textbox_safety': 5,
                    'background_character_harmony': 4,
                    'visual_focus': 4,
                    'scene_mood_fit': 5,
                    'continuity_with_adjacent_captures': 4,
                },
                'blockers': [],
                'caveats': ['background is dark but faces/textbox remain readable'],
                'uncertainty': 'low',
                'rationale': 'Serena and Lucian are balanced; scene identity remains visible.',
            }
        ],
        'thresholds': {
            'character_positioning': 4,
            'character_scale': 4,
            'textbox_safety': 5,
            'background_character_harmony': 4,
            'visual_focus': 4,
            'scene_mood_fit': 4,
            'continuity_with_adjacent_captures': 4,
        },
    }


def test_vision_composition_qa_passes_low_uncertainty_scorecard(tmp_path: Path):
    project = make_project(tmp_path)
    scorecard = write_json(project / 'docs/validation/run/vision_composition_scorecard.json', base_scorecard())
    out = project / 'docs/validation/run/vision_composition_qa.json'

    proc = run_qa(project, scorecard, out)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'VISION_COMPOSITION_QA' in proc.stdout
    assert 'status pass' in proc.stdout
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'pass'
    assert data['vision_composition_scorecard_pass'] is True


def test_vision_composition_qa_fails_low_required_score(tmp_path: Path):
    project = make_project(tmp_path)
    card = base_scorecard()
    card['captures'][0]['scores']['background_character_harmony'] = 3
    scorecard = write_json(project / 'docs/validation/run/vision_composition_scorecard.json', card)
    out = project / 'docs/validation/run/vision_composition_qa.json'

    proc = run_qa(project, scorecard, out)

    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'fail'
    assert any('background_character_harmony' in issue for issue in data['issues'])


def test_vision_composition_qa_fails_medium_uncertainty_for_auto_approval(tmp_path: Path):
    project = make_project(tmp_path)
    card = base_scorecard()
    card['uncertainty'] = 'medium'
    card['captures'][0]['uncertainty'] = 'medium'
    scorecard = write_json(project / 'docs/validation/run/vision_composition_scorecard.json', card)
    out = project / 'docs/validation/run/vision_composition_qa.json'

    proc = run_qa(project, scorecard, out)

    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['vision_composition_scorecard_pass'] is False
    assert any('uncertainty' in issue for issue in data['issues'])


def test_vision_composition_qa_fails_blockers_even_with_good_scores(tmp_path: Path):
    project = make_project(tmp_path)
    card = base_scorecard()
    card['captures'][0]['blockers'] = ['Lucian face blends into dark wall']
    scorecard = write_json(project / 'docs/validation/run/vision_composition_scorecard.json', card)
    out = project / 'docs/validation/run/vision_composition_qa.json'

    proc = run_qa(project, scorecard, out)

    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'fail'
    assert any('blocker' in issue for issue in data['issues'])
