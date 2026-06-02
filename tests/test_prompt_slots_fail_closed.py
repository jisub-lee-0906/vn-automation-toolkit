from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_SCRIPT = ROOT / 'tools/run_generation_queue.py'
BG_SCRIPT = ROOT / 'tools/run_scene_background_smoke.py'


def load_tool_module(script: Path, name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def make_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / 'project'
    workflow_pack = tmp_path / 'workflow_pack'
    write_json(project / 'docs/automation/project_contract.json', {
        'workflow_pack_root': str(workflow_pack),
        'comfyui_output_root': str(tmp_path / 'comfy_out'),
        'comfyui_endpoint': 'http://127.0.0.1:9',
    })
    write_json(workflow_pack / 'scene_background/scene_background_workflow_api.json', {
        '3': {'inputs': {'text': 'old positive'}},
        '4': {'inputs': {'text': 'old negative'}},
        '5': {'inputs': {'width': 0, 'height': 0}},
        '6': {'inputs': {'seed': 0, 'steps': 0, 'cfg': 0}},
        '8': {'inputs': {'filename_prefix': 'old'}},
    })
    write_text(workflow_pack / 'danbooru_tag.csv', '\n'.join([
        'bus_interior', 'vehicle_interior', 'bus', 'chair', 'window',
        'rain', 'wet', 'reflection', 'road', 'street', 'indoors', 'dawn',
        'school', 'classroom', 'desk', 'chalkboard', 'day', 'sunlight', 'clear_sky',
        'medium_hair', 'straight_hair', 'brown_hair', 'brown_eyes', 'white_shirt', 'blue_skirt',
    ]))
    return project, workflow_pack


def test_generation_queue_fails_closed_when_prompt_sensitive_request_has_no_prompt_slots(tmp_path: Path):
    project, _ = make_project(tmp_path)
    write_json(project / 'docs/production/asset_requests/scene.resolved_asset_requests.json', {
        'scene_id': 'scene',
        'resolved_asset_requests': [{
            'asset_id': 'bg_bus_interior_dawn',
            'asset_type': 'background',
            'description': '새벽 첫차 버스 내부',
            'decision': 'generate',
            'status': 'needs_generation',
            'recommended_workflow_id': 'scene_background',
        }],
    })
    out = tmp_path / 'batch.json'

    proc = subprocess.run([
        sys.executable, str(QUEUE_SCRIPT),
        '--project-root', str(project),
        '--out', str(out),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding='utf-8'))
    result = data['results'][0]
    assert result['status'] == 'failed_missing_prompt_slots'
    assert result['reason'] == 'prompt_sensitive_workflow_requires_agent_authored_prompt_slots'


def test_scene_background_prepare_only_uses_agent_authored_prompt_slots_not_classroom_fallback(tmp_path: Path):
    project, _ = make_project(tmp_path)
    slots = project / 'docs/production/prompt_slots/bg_bus_interior_dawn.json'
    write_json(slots, {
        'workflow_id': 'scene_background',
        'asset_id': 'bg_bus_interior_dawn',
        'author': 'agent',
        'prompt_slots': {
            'background_theme': ['bus_interior', 'vehicle_interior', 'bus', 'chair', 'window', 'rain', 'wet', 'reflection', 'road', 'street'],
            'time_mood': ['indoors', 'dawn'],
        },
        'semantic_requirements': ['dawn first-bus interior', 'no people', 'no readable text'],
    })
    meta = tmp_path / 'metadata.json'

    proc = subprocess.run([
        sys.executable, str(BG_SCRIPT),
        '--project-root', str(project),
        '--asset-id', 'bg_bus_interior_dawn',
        '--description', '새벽 첫차 버스 내부',
        '--scene-id', 'scene',
        '--prompt-slots', str(slots),
        '--prepare-only',
        '--out-metadata', str(meta),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(meta.read_text(encoding='utf-8'))
    assert data['prompt_source'] == 'agent_authored_prompt_slots'
    assert 'bus_interior' in data['csv_placeholder_tags']
    assert 'classroom' not in data['csv_placeholder_tags']
    patched = json.loads(Path(data['patched_workflow_path']).read_text(encoding='utf-8'))
    assert 'bus_interior' in patched['3']['inputs']['text']
    assert 'classroom' not in patched['3']['inputs']['text']


def test_audio_generation_queue_fails_closed_without_prompt_slots(tmp_path: Path):
    project, _ = make_project(tmp_path)
    write_json(project / 'docs/production/asset_requests/scene.resolved_asset_requests.json', {
        'scene_id': 'scene',
        'resolved_asset_requests': [{
            'asset_id': 'sfx_door_knock_soft',
            'asset_type': 'sfx',
            'description': 'soft door knock',
            'decision': 'generate',
            'status': 'needs_generation',
            'recommended_workflow_id': 'audio_sfx_mmaudio',
        }],
    })
    out = tmp_path / 'batch.json'

    proc = subprocess.run([
        sys.executable, str(QUEUE_SCRIPT),
        '--project-root', str(project),
        '--out', str(out),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 1
    result = json.loads(out.read_text(encoding='utf-8'))['results'][0]
    assert result['status'] == 'failed_missing_prompt_slots'


def test_char_base_generation_queue_fails_closed_without_prompt_slots(tmp_path: Path):
    project, _ = make_project(tmp_path)
    write_json(project / 'docs/production/asset_requests/scene.resolved_asset_requests.json', {
        'scene_id': 'scene',
        'resolved_asset_requests': [{
            'asset_id': 'char_seoha_base',
            'asset_type': 'character_base',
            'description': '서하 기본 캐릭터 베이스',
            'decision': 'generate',
            'status': 'needs_generation',
            'recommended_workflow_id': 'char_base',
        }],
    })
    out = tmp_path / 'batch.json'

    proc = subprocess.run([
        sys.executable, str(QUEUE_SCRIPT),
        '--project-root', str(project),
        '--out', str(out),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 1
    result = json.loads(out.read_text(encoding='utf-8'))['results'][0]
    assert result['status'] == 'failed_missing_prompt_slots'


def test_char_base_prepare_only_requires_agent_authored_prompt_slots(tmp_path: Path):
    char_script = ROOT / 'tools/run_char_base_smoke.py'
    project, workflow_pack = make_project(tmp_path)
    write_json(workflow_pack / 'char_base/char_base_workflow_api.json', {
        '3': {'inputs': {'text': 'old positive'}},
        '4': {'inputs': {'text': 'old negative'}},
        '5': {'inputs': {'width': 0, 'height': 0}},
        '6': {'inputs': {'seed': 0, 'steps': 0, 'cfg': 0}},
        '8': {'inputs': {'filename_prefix': 'old'}},
    })
    slots = project / 'docs/production/prompt_slots/char_seoha_base.json'
    write_json(slots, {
        'workflow_id': 'char_base',
        'asset_id': 'char_seoha_base',
        'prompt_slots': {
            'character_features': ['medium_hair', 'straight_hair', 'brown_hair', 'brown_eyes'],
            'outfit_detail': ['white_shirt', 'blue_skirt'],
        },
    })
    meta = tmp_path / 'char_meta.json'

    proc = subprocess.run([
        sys.executable, str(char_script),
        '--project-root', str(project),
        '--asset-id', 'char_seoha_base',
        '--prompt-slots', str(slots),
        '--prepare-only',
        '--out-metadata', str(meta),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(meta.read_text(encoding='utf-8'))
    assert data['prompt_source'] == 'agent_authored_prompt_slots'
    assert 'school_uniform' not in data['csv_placeholder_tags']
    patched = json.loads(Path(data['patched_workflow_path']).read_text(encoding='utf-8'))
    assert 'brown_hair' in patched['3']['inputs']['text']
    assert 'school_uniform' not in patched['3']['inputs']['text']
