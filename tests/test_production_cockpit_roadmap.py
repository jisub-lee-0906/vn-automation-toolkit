from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import validate_production_cockpit_roadmap  # noqa: E402


def write_contract(root: Path) -> None:
    (root / 'docs/automation').mkdir(parents=True)
    (root / 'game').mkdir()
    (root / 'docs/automation/project_contract.json').write_text(json.dumps({
        'project_root': str(root),
        'renpy_project_root': str(root),
        'renpy_game_dir': str(root / 'game'),
    }), encoding='utf-8')


def valid_roadmap(root: Path, obsidian_note: Path) -> dict:
    state = root / 'docs/automation/scene_remaster/current_state.json'
    evidence = root / 'docs/validation/scene001/report.md'
    for path in [state, evidence]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}\n' if path.suffix == '.json' else '# report\n', encoding='utf-8')
    obsidian_note.parent.mkdir(parents=True, exist_ok=True)
    obsidian_note.write_text('# Scene\n', encoding='utf-8')
    return {
        'schema_version': 1,
        'game_slug': 'portable_title',
        'target_level': 'level_3_human_supervised_vertical_polish_cockpit',
        'goal': 'Human-supervised scene-by-scene vertical polish cockpit.',
        'non_goals': [
            'No auto_promote of candidates.',
            'No global_replacement of assets.',
            'No unapproved_production_replacement in game/images or game/audio.',
        ],
        'principles': ['scene-local', 'approval-gated', 'evidence-backed'],
        'current_focus': {
            'scene_id': 'scene_001_red_system_contract',
            'state_file': 'docs/automation/scene_remaster/current_state.json',
            'obsidian_scene_note': str(obsidian_note),
        },
        'workstreams': [{
            'id': 'state_and_evidence_spine',
            'name': 'State and evidence spine',
            'status': 'active',
            'objective': 'Keep current_state, patch manifests, and QA reports linked.',
            'tasks': ['Validate state links'],
            'verification': ['vn-auto scene-state --check-existing'],
            'evidence': ['docs/validation/scene001/report.md'],
            'outputs': ['docs/automation/scene_remaster/current_state.json'],
        }],
    }


def test_production_cockpit_roadmap_passes_valid_project(tmp_path: Path) -> None:
    write_contract(tmp_path)
    roadmap = tmp_path / 'docs/automation/production_cockpit_roadmap.json'
    data = valid_roadmap(tmp_path, tmp_path / 'obsidian/VN/Scenes/scene_001.md')
    roadmap.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    rc = validate_production_cockpit_roadmap.main(['--project-root', str(tmp_path), '--roadmap', str(roadmap)])
    assert rc == 0


def test_production_cockpit_roadmap_requires_explicit_non_goals(tmp_path: Path) -> None:
    write_contract(tmp_path)
    roadmap = tmp_path / 'docs/automation/production_cockpit_roadmap.json'
    data = valid_roadmap(tmp_path, tmp_path / 'obsidian/VN/Scenes/scene_001.md')
    data['non_goals'] = ['too vague']
    roadmap.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    rc = validate_production_cockpit_roadmap.main(['--project-root', str(tmp_path), '--roadmap', str(roadmap)])
    assert rc == 1


def test_production_cockpit_roadmap_refuses_outside_project_roadmap(tmp_path: Path) -> None:
    write_contract(tmp_path / 'project')
    outside = tmp_path / 'outside.json'
    outside.write_text('{}', encoding='utf-8')
    rc = validate_production_cockpit_roadmap.main(['--project-root', str(tmp_path / 'project'), '--roadmap', str(outside)])
    assert rc == 2
