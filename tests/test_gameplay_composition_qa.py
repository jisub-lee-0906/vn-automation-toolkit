from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/gameplay_composition_qa.py'


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


def run_qa(project: Path, plan: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), '--project-root', str(project), '--plan', str(plan), '--out', str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def make_screen(path: Path, *, left_box=(90, 210, 265, 650), right_box=(265, 205, 430, 650), textbox_top=680) -> Path:
    img = Image.new('RGB', (480, 860), (28, 18, 24))
    draw = ImageDraw.Draw(img)
    # background accents
    draw.rectangle((0, 0, 480, textbox_top), fill=(45, 20, 22))
    draw.rectangle((40, 40, 440, textbox_top - 20), outline=(100, 30, 30), width=4)
    # left/right stylized sprites
    if left_box[2] > left_box[0] and left_box[3] > left_box[1]:
        draw.rectangle(left_box, fill=(205, 45, 55))
        draw.rectangle((left_box[0] + 35, left_box[1] - 35, left_box[2] - 35, left_box[1] + 35), fill=(235, 95, 95))
    if right_box[2] > right_box[0] and right_box[3] > right_box[1]:
        draw.rectangle(right_box, fill=(35, 60, 95))
        draw.rectangle((right_box[0] + 35, right_box[1] - 35, right_box[2] - 35, right_box[1] + 35), fill=(45, 60, 80))
    # textbox
    draw.rectangle((0, textbox_top, 480, 860), fill=(5, 3, 8))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def test_gameplay_composition_qa_passes_balanced_two_sprite_scene(tmp_path: Path):
    project = make_project(tmp_path)
    screenshot = make_screen(project / 'docs/validation/run/screen.png')
    plan = write_json(project / 'docs/validation/run/composition_plan.json', {
        'scene_id': 'scene_test',
        'captures': [{
            'name': 'entry',
            'screenshot': str(screenshot),
            'textbox_region': {'x1': 0, 'y1': 0.79, 'x2': 1, 'y2': 1},
            'characters': [
                {'name': 'left_actor', 'expected_region': {'x1': 0.05, 'y1': 0.15, 'x2': 0.58, 'y2': 0.82}, 'dominant_color': [205, 45, 55]},
                {'name': 'right_actor', 'expected_region': {'x1': 0.42, 'y1': 0.15, 'x2': 0.95, 'y2': 0.82}, 'dominant_color': [35, 60, 95]},
            ],
            'min_character_area_ratio': 0.06,
            'max_character_area_ratio': 0.28,
            'max_textbox_overlap_ratio': 0.08,
            'max_inter_character_overlap_ratio': 0.10,
        }]
    })
    out = project / 'docs/validation/run/composition_qa.json'

    proc = run_qa(project, plan, out)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'GAMEPLAY_COMPOSITION_QA' in proc.stdout
    assert 'status pass' in proc.stdout
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'pass'
    assert data['captures'][0]['status'] == 'pass'


def test_gameplay_composition_qa_fails_character_intruding_into_textbox(tmp_path: Path):
    project = make_project(tmp_path)
    screenshot = make_screen(project / 'docs/validation/run/screen.png', left_box=(90, 210, 265, 650))
    # Simulate a visible sprite/UI intrusion drawn over the textbox.
    img = Image.open(screenshot).convert('RGB')
    draw = ImageDraw.Draw(img)
    draw.rectangle((90, 690, 265, 795), fill=(205, 45, 55))
    img.save(screenshot)
    plan = write_json(project / 'docs/validation/run/composition_plan.json', {
        'scene_id': 'scene_test',
        'captures': [{
            'name': 'entry',
            'screenshot': str(screenshot),
            'textbox_region': {'x1': 0, 'y1': 0.79, 'x2': 1, 'y2': 1},
            'characters': [
                {'name': 'left_actor', 'expected_region': {'x1': 0.05, 'y1': 0.15, 'x2': 0.58, 'y2': 0.95}, 'dominant_color': [205, 45, 55]},
                {'name': 'right_actor', 'expected_region': {'x1': 0.42, 'y1': 0.15, 'x2': 0.95, 'y2': 0.82}, 'dominant_color': [35, 60, 95]},
            ],
            'min_character_area_ratio': 0.06,
            'max_character_area_ratio': 0.35,
            'max_textbox_overlap_ratio': 0.08,
        }]
    })
    out = project / 'docs/validation/run/composition_qa.json'

    proc = run_qa(project, plan, out)

    assert proc.returncode == 1
    assert 'status fail' in proc.stdout
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'fail'
    issues = '\n'.join(data['captures'][0]['issues'])
    assert 'textbox_overlap' in issues


def test_gameplay_composition_qa_fails_unexpected_image_size(tmp_path: Path):
    project = make_project(tmp_path)
    screenshot = make_screen(project / 'docs/validation/run/screen.png')
    plan = write_json(project / 'docs/validation/run/composition_plan.json', {
        'scene_id': 'scene_test',
        'captures': [{
            'name': 'wrong_crop_size',
            'screenshot': str(screenshot),
            'expected_size': [430, 764],
            'textbox_region': {'x1': 0, 'y1': 0.79, 'x2': 1, 'y2': 1},
            'characters': [],
        }]
    })
    out = project / 'docs/validation/run/composition_qa.json'

    proc = run_qa(project, plan, out)

    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding='utf-8'))
    issues = '\n'.join(data['captures'][0]['issues'])
    assert 'unexpected_image_size' in issues



def test_gameplay_composition_qa_fails_when_required_characters_are_not_declared(tmp_path: Path):
    project = make_project(tmp_path)
    screenshot = make_screen(project / 'docs/validation/run/screen.png')
    plan = write_json(project / 'docs/validation/run/composition_plan.json', {
        'scene_id': 'scene_test',
        'captures': [{
            'name': 'dialogue_should_have_two_sprites',
            'screenshot': str(screenshot),
            'textbox_region': {'x1': 0, 'y1': 0.79, 'x2': 1, 'y2': 1},
            'min_characters': 2,
            'characters': [],
            'background_sample_region': {'x1': 0.05, 'y1': 0.08, 'x2': 0.95, 'y2': 0.70},
        }]
    })
    out = project / 'docs/validation/run/composition_qa.json'

    proc = run_qa(project, plan, out)

    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'fail'
    issues = '\n'.join(data['captures'][0]['issues'])
    assert 'min_characters' in issues



def test_gameplay_composition_qa_fails_missing_expected_character_color(tmp_path: Path):
    project = make_project(tmp_path)
    screenshot = make_screen(project / 'docs/validation/run/screen.png', right_box=(0, 0, 0, 0))
    plan = write_json(project / 'docs/validation/run/composition_plan.json', {
        'scene_id': 'scene_test',
        'captures': [{
            'name': 'entry',
            'screenshot': str(screenshot),
            'textbox_region': {'x1': 0, 'y1': 0.79, 'x2': 1, 'y2': 1},
            'characters': [
                {'name': 'right_actor', 'expected_region': {'x1': 0.42, 'y1': 0.15, 'x2': 0.95, 'y2': 0.82}, 'dominant_color': [35, 60, 95]},
            ],
            'min_character_area_ratio': 0.06,
            'max_character_area_ratio': 0.28,
            'max_textbox_overlap_ratio': 0.08,
        }]
    })
    out = project / 'docs/validation/run/composition_qa.json'

    proc = run_qa(project, plan, out)

    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'fail'
    issues = '\n'.join(data['captures'][0]['issues'])
    assert 'missing_or_too_small' in issues
