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
    obs = tmp_path / 'obsidian' / 'VN'
    write_json(project / 'docs/automation/project_contract.json', {
        'project_root': str(project),
        'renpy_game_dir': str(project / 'game'),
        'manifest_path': str(project / 'game/data/asset_manifest.json'),
        'obsidian_project_root': str(obs),
        'obsidian_scenes_glob': 'Scenes/*.md',
    })
    write_json(project / 'game/data/asset_manifest.json', {'assets': []})
    (project / 'game').mkdir(parents=True, exist_ok=True)
    (project / 'game/script.rpy').write_text('label scene_003_first_clue_field:\n    narrator "첫 단서"\n    return\n', encoding='utf-8')
    (obs / 'Scenes').mkdir(parents=True, exist_ok=True)
    (obs / 'Scenes/scene_003_first_clue_field.md').write_text('# Scene 003\nfirst investigation, record fracture, Serena and Lucian tension\n', encoding='utf-8')
    return project


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, '-m', 'vn_automation.cli', *args], cwd=ROOT, text=True, capture_output=True)


def test_scene_story_plan_generates_structured_story_and_asset_opportunities(tmp_path: Path):
    project = make_project(tmp_path)
    out = project / 'docs/automation/story_plans/scene_003_first_clue_field.json'
    proc = run_cli('scene-story-plan', '--project-root', str(project), '--scene-id', 'scene_003_first_clue_field', '--out', str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['scene_id'] == 'scene_003_first_clue_field'
    assert data['story_qa_targets']['canon_fit'] >= 4
    assert any(item['asset_type'] == 'bgm' for item in data['asset_opportunities'])
    assert any(item['asset_type'] == 'event_cg' and item['promotion'] == 'human_gated' for item in data['asset_opportunities'])


def test_story_qa_fails_missing_emotional_arc_and_asset_opportunities(tmp_path: Path):
    project = make_project(tmp_path)
    bad = write_json(project / 'docs/automation/story_plans/bad.json', {
        'scene_id': 'scene_bad',
        'beats': [{'beat_id': 'b1', 'summary': 'info dump only'}],
        'asset_opportunities': [],
        'story_qa_targets': {'canon_fit': 5, 'character_voice': 5, 'emotional_progression': 2, 'player_reward': 2, 'repetition_risk': 5},
    })
    out = project / 'docs/validation/story_qa_bad.json'
    proc = run_cli('story-qa', '--project-root', str(project), '--plan', str(bad), '--out', str(out))
    assert proc.returncode == 1
    result = json.loads(out.read_text(encoding='utf-8'))
    assert result['status'] == 'fail'
    assert any('emotional_progression' in issue for issue in result['issues'])
    assert any('asset_opportunities' in issue for issue in result['issues'])


def test_scene_enrichment_plan_uses_story_plan_and_policy(tmp_path: Path):
    project = make_project(tmp_path)
    policy = write_json(project / 'docs/automation/asset_generation_policy.json', {
        'default_generation_mode': 'proactive_variety',
        'minimum_candidate_counts': {'background': 3, 'bgm': 2, 'sfx': 3, 'prop_cg': 3, 'event_cg': 2, 'char_expression': 2},
        'promotion_policy': 'approval_gated',
    })
    story = write_json(project / 'docs/automation/story_plans/scene.json', {
        'scene_id': 'scene_003_first_clue_field',
        'asset_opportunities': [
            {'asset_type': 'bgm', 'role': 'quiet investigation loop', 'promotion': 'delegated_auto_possible'},
            {'asset_type': 'event_cg', 'role': 'clue reveal', 'promotion': 'human_gated'},
        ],
        'story_qa_targets': {'canon_fit': 5, 'character_voice': 5, 'emotional_progression': 4, 'player_reward': 4, 'repetition_risk': 2},
    })
    out = project / 'docs/automation/scene_enrichment/scene_003_first_clue_field.json'
    proc = run_cli('scene-enrichment-plan', '--project-root', str(project), '--story-plan', str(story), '--policy', str(policy), '--out', str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['generation_mode'] == 'proactive_variety'
    event = next(item for item in data['candidate_batches'] if item['asset_type'] == 'event_cg')
    assert event['count'] == 2
    assert event['promotion'] == 'human_gated'
