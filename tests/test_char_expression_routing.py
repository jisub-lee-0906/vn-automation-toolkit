from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/run_char_expression_smoke.py'


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def make_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / 'expression_project'
    workflow_pack = tmp_path / 'workflow_pack'
    comfy_input = tmp_path / 'ComfyUI' / 'input'
    comfy_output = tmp_path / 'ComfyUI' / 'output'
    comfy_input.mkdir(parents=True)
    comfy_output.mkdir(parents=True)
    write_json(project / 'docs/automation/project_contract.json', {
        'version': '1.0.0',
        'renpy_project_root': project.as_posix(),
        'renpy_game_dir': (project / 'game').as_posix(),
        'workflow_pack_root': workflow_pack.as_posix(),
        'workflow_index': (workflow_pack / 'WORKFLOW_INDEX.json').as_posix(),
        'comfyui_input_root': comfy_input.as_posix(),
        'comfyui_output_root': comfy_output.as_posix(),
        'comfyui_endpoint': 'http://127.0.0.1:65535',
        'comfyui_endpoint_candidates': ['http://127.0.0.1:65535'],
    })
    write_json(workflow_pack / 'WORKFLOW_INDEX.json', {'workflows': []})
    write_json(workflow_pack / 'char_expression/char_expression_workflow_api.json', {
        '1': {'class_type': 'LoadImage', 'inputs': {'image': 'TEMPLATE_character_anchor_source.png'}},
        '5': {'class_type': 'AILab_MaskEnhancer', 'inputs': {'mask_blur': 3, 'mask_offset': 0}},
        '6': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'old positive'}},
        '7': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'old negative'}},
        '13': {'class_type': 'KSampler', 'inputs': {'seed': 0, 'denoise': 0.4}},
        '19': {'class_type': 'SaveImage', 'inputs': {'filename_prefix': 'old_prefix'}},
        '1000': {'class_type': 'UltralyticsDetectorProvider', 'inputs': {'model_name': 'bbox/face_yolov9c.pt'}},
        '1002': {'class_type': 'BboxDetectorSEGS', 'inputs': {'threshold': 0.35, 'crop_factor': 2.0}},
        '1003': {'class_type': 'SAMDetectorCombined', 'inputs': {'detection_hint': 'center-1', 'threshold': 0.93}},
    })
    db = workflow_pack / 'danbooru-taxonomy.release.sqlite'
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT, normalized_name TEXT, display_name TEXT, category_name TEXT, post_count INTEGER, is_deprecated INTEGER)')
        conn.execute('CREATE TABLE tag_aliases (alias_normalized_name TEXT, target_tag_id INTEGER, status TEXT)')
        tags = ['medium_hair', 'straight_hair', 'brown_hair', 'brown_eyes', 'happy', 'smile', 'open_mouth', 'sad', 'angry', 'crying', 'tears', 'expressionless']
        for i, tag in enumerate(tags, start=1):
            conn.execute('INSERT INTO tags VALUES (?, ?, ?, ?, ?, ?, 0)', (i, tag, tag, tag.replace('_', ' '), 'general', 1000 - i))
    source = project / 'docs/automation/generated_candidates/characters/source_fixture.png'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'fake-png-fixture')
    return project, workflow_pack, source


def write_slots(project: Path) -> Path:
    slots = project / 'docs/production/prompt_slots/expr_happy_fixture.json'
    write_json(slots, {
        'workflow_id': 'char_expression',
        'asset_id': 'expr_happy_fixture',
        'expression_id': 'happy',
        'prompt_slots': {
            'identity_tags': ['medium_hair', 'straight_hair', 'brown_hair', 'brown_eyes'],
            'expression_positive': ['happy', 'smile', 'open_mouth'],
            'expression_negative': ['sad', 'angry', 'crying', 'tears', 'expressionless'],
        },
    })
    return slots


def test_char_expression_prepare_only_patches_source_prompts_and_metadata(tmp_path: Path):
    project, _, source = make_project(tmp_path)
    slots = write_slots(project)
    out_meta = project / 'docs/automation/generation_runs/expression_prepare/metadata.json'

    proc = subprocess.run([
        sys.executable, str(SCRIPT),
        '--project-root', str(project),
        '--asset-id', 'expr_happy_fixture',
        '--source-image', str(source),
        '--prompt-slots', str(slots),
        '--seed', '4242',
        '--prepare-only',
        '--out-metadata', str(out_meta),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out_meta.read_text(encoding='utf-8'))
    assert data['workflow_id'] == 'char_expression'
    assert data['asset_type'] == 'character_expression'
    assert data['source_image'] == str(source.resolve())
    assert data['expression_id'] == 'happy'
    assert data['taxonomy_source'] == 'db'
    assert data['seed'] == 4242
    assert data['prepare_only'] is True
    staged = Path(data['staged_source_image'])
    assert staged.exists()
    patched = json.loads(Path(data['patched_workflow_path']).read_text(encoding='utf-8'))
    assert patched['1']['inputs']['image'] == staged.name
    assert 'happy' in patched['6']['inputs']['text']
    assert 'brown_hair' in patched['6']['inputs']['text']
    assert 'sad' in patched['7']['inputs']['text']
    assert patched['13']['inputs']['seed'] == 4242
    assert patched['19']['inputs']['filename_prefix'].startswith('hermes_vn_char_expression/')


def test_char_expression_requires_agent_authored_prompt_slots(tmp_path: Path):
    project, _, source = make_project(tmp_path)
    proc = subprocess.run([
        sys.executable, str(SCRIPT),
        '--project-root', str(project),
        '--asset-id', 'expr_missing_slots',
        '--source-image', str(source),
        '--prepare-only',
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 1
    assert 'UNROUTED_CHAR_EXPRESSION' in proc.stdout + proc.stderr
