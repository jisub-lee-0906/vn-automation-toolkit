import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/create_scene_event_cg_prompt_slots.py'


def run_cli(project: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), '--project-root', str(project), '--asset-id', 'event_auto_surprised', '--emotion', 'surprised', '--framing', 'default', *extra],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_create_scene_event_cg_prompt_slots_requires_project_specific_base_tags(tmp_path: Path):
    project = tmp_path / 'game'
    (project / 'docs/production/prompt_slots').mkdir(parents=True)

    proc = run_cli(project)

    assert proc.returncode != 0
    assert 'SCENE_EVENT_CG_CHARACTER_FEATURES_REQUIRED' in proc.stderr or 'SCENE_EVENT_CG_CHARACTER_FEATURES_REQUIRED' in proc.stdout
    assert not (project / 'docs/production/prompt_slots/event_auto_surprised.json').exists()


def test_create_scene_event_cg_prompt_slots_cli_writes_with_explicit_project_tags(tmp_path: Path):
    project = tmp_path / 'game'
    (project / 'docs/production/prompt_slots').mkdir(parents=True)

    proc = run_cli(
        project,
        '--character-features', 'blue_eyes,blonde_hair,long_hair',
        '--outfit-detail', 'red_dress,jewelry',
        '--scene-context', 'ballroom,chandelier',
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    path = project / 'docs/production/prompt_slots/event_auto_surprised.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['scene_event_route_mode'] == 'production_character_front'
    assert data['prompt_slots']['character_features'][-2:] == ['surprised', 'open_mouth']
    assert data['prompt_slots']['outfit_detail'] == ['red_dress', 'jewelry']
    assert data['prompt_slots']['scene_context'] == ['ballroom', 'chandelier', 'upper_body', 'looking_at_viewer', 'facing_viewer', 'straight_on']


def test_create_scene_event_cg_prompt_slots_allows_generic_fixture_only_with_explicit_flag(tmp_path: Path):
    project = tmp_path / 'game'
    (project / 'docs/production/prompt_slots').mkdir(parents=True)

    proc = run_cli(project, '--allow-generic-fixture-defaults')

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads((project / 'docs/production/prompt_slots/event_auto_surprised.json').read_text(encoding='utf-8'))
    assert 'school_uniform' in data['prompt_slots']['outfit_detail']
    assert data['fixture_defaults_used'] is True
