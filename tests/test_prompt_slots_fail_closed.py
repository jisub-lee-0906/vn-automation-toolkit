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


def make_project(tmp_path: Path, *, sqlite_only: bool = False) -> tuple[Path, Path]:
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
    tags = [
        'bus_interior', 'vehicle_interior', 'bus', 'chair', 'window',
        'rain', 'wet', 'reflection', 'road', 'street', 'indoors', 'dawn', 'train_interior',
        'school', 'classroom', 'desk', 'chalkboard', 'day', 'sunlight', 'clear_sky',
        'medium_hair', 'straight_hair', 'brown_hair', 'brown_eyes', 'white_shirt', 'blue_skirt',
    ]
    if sqlite_only:
        import sqlite3
        db = workflow_pack / 'danbooru-taxonomy.release.sqlite'
        db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db) as conn:
            conn.execute('CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT, normalized_name TEXT, display_name TEXT, category_name TEXT, post_count INTEGER, is_deprecated INTEGER)')
            conn.execute('CREATE TABLE tag_aliases (alias_normalized_name TEXT, target_tag_id INTEGER, status TEXT)')
            for i, tag in enumerate(tags, start=1):
                conn.execute('INSERT INTO tags VALUES (?, ?, ?, ?, ?, ?, 0)', (i, tag, tag, tag.replace('_', ' '), 'general', 1000 - i))
    else:
        write_text(workflow_pack / 'danbooru_tag.csv', '\n'.join(tags))
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
    out = project / 'docs/automation/batch.json'

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
            'negative_tags': ['train_interior'],
            'semantic_prompt': 'empty dawn city bus interior, rain-wet windows',
            'style_prompt': 'quiet blue-hour commute atmosphere',
        },
        'visual_brief': 'Dawn first-bus interior, empty and rain-wet through the windows.',
        'tag_rationale': {'bus_interior': 'primary class anchor'},
        'negative_rationale': {'train_interior': 'avoid subway/train interior confusion'},
        'semantic_requirements': ['dawn first-bus interior', 'no people', 'no readable text'],
    })
    meta = project / 'docs/automation/generation_runs/metadata.json'

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
    assert 'train_interior' in data['csv_negative_tags']
    assert data['prompt_context_notes']['visual_brief'] == 'Dawn first-bus interior, empty and rain-wet through the windows.'
    assert data['prompt_context_notes']['tag_rationale']['bus_interior'] == 'primary class anchor'
    assert data['prompt_context_notes']['negative_rationale']['train_interior'] == 'avoid subway/train interior confusion'
    assert data['semantic_prompt_segment'] == 'empty dawn city bus interior, rain-wet windows, quiet blue-hour commute atmosphere'
    assert 'classroom' not in data['csv_placeholder_tags']
    patched = json.loads(Path(data['patched_workflow_path']).read_text(encoding='utf-8'))
    assert 'bus_interior' in patched['3']['inputs']['text']
    assert 'empty dawn city bus interior' in patched['3']['inputs']['text']
    assert 'train_interior' in patched['4']['inputs']['text']
    assert 'classroom' not in patched['3']['inputs']['text']


def test_scene_background_prepare_only_uses_sqlite_taxonomy_when_root_csv_removed(tmp_path: Path):
    project, workflow_pack = make_project(tmp_path, sqlite_only=True)
    assert not (workflow_pack / 'danbooru_tag.csv').exists()
    slots = project / 'docs/production/prompt_slots/bg_bus_interior_dawn.json'
    write_json(slots, {
        'workflow_id': 'scene_background',
        'asset_id': 'bg_bus_interior_dawn',
        'prompt_slots': {
            'background_theme': ['bus_interior', 'vehicle_interior', 'bus'],
            'time_mood': ['indoors', 'dawn'],
            'negative_tags': ['train_interior'],
        },
    })
    meta = project / 'docs/automation/generation_runs/metadata_sqlite.json'

    proc = subprocess.run([
        sys.executable, str(BG_SCRIPT),
        '--project-root', str(project),
        '--asset-id', 'bg_bus_interior_dawn',
        '--prompt-slots', str(slots),
        '--prepare-only',
        '--out-metadata', str(meta),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(meta.read_text(encoding='utf-8'))
    assert data['prompt_policy'] == 'README wrapper + agent-authored SQLite-verified prompt slots'
    assert data['taxonomy_db_path'].endswith('danbooru-taxonomy.release.sqlite')
    assert data['taxonomy_placeholder_tags'] == ['bus_interior', 'vehicle_interior', 'bus', 'indoors', 'dawn']
    assert data['taxonomy_negative_tags'] == ['train_interior']
    assert all(item['source'] == 'db' for item in data['taxonomy_validation'].values())


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
            'recommended_workflow_id': 'audio_bgm_with_sfx',
        }],
    })
    out = project / 'docs/automation/batch.json'

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
    out = project / 'docs/automation/batch.json'

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
    meta = project / 'docs/automation/generation_runs/char_meta.json'

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


def test_char_base_prepare_only_uses_sqlite_taxonomy_when_root_csv_removed(tmp_path: Path):
    char_script = ROOT / 'tools/run_char_base_smoke.py'
    project, workflow_pack = make_project(tmp_path, sqlite_only=True)
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
    meta = project / 'docs/automation/generation_runs/char_meta_sqlite.json'

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
    assert data['prompt_policy'] == 'README wrapper + agent-authored SQLite-verified prompt slots only'
    assert data['taxonomy_placeholder_tags'] == ['medium_hair', 'straight_hair', 'brown_hair', 'brown_eyes', 'white_shirt', 'blue_skirt']
    assert data['taxonomy_db_path'].endswith('danbooru-taxonomy.release.sqlite')


def test_scene_event_cg_refuses_missing_source_char_base_metadata(tmp_path: Path):
    event_script = ROOT / 'tools/run_scene_event_cg_smoke.py'
    project, workflow_pack = make_project(tmp_path, sqlite_only=True)
    write_json(workflow_pack / 'scene_event_cg/scene_event_cg_workflow_api.json', {
        '9': {'inputs': {'text': 'old positive'}},
        '10': {'inputs': {'text': 'old negative'}},
        '11': {'inputs': {'width': 0, 'height': 0}},
        '12': {'inputs': {'seed': 0, 'steps': 0, 'cfg': 0, 'denoise': 0}},
        '14': {'inputs': {'filename_prefix': 'old'}},
        '100': {'inputs': {'lora_name': '', 'strength_model': 0, 'strength_clip': 0}},
    })
    slots = project / 'docs/production/prompt_slots/event_test.json'
    write_json(slots, {
        'workflow_id': 'scene_event_cg',
        'asset_id': 'event_test',
        'prompt_slots': {
            'character_features': ['medium_hair', 'brown_hair'],
            'outfit_detail': ['white_shirt', 'blue_skirt'],
            'scene_context': ['indoors', 'dawn'],
        },
    })

    proc = subprocess.run([
        sys.executable, str(event_script),
        '--project-root', str(project),
        '--asset-id', 'event_test',
        '--prompt-slots', str(slots),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 1
    assert 'SCENE_EVENT_CG_SOURCE_REQUIRED' in proc.stdout + proc.stderr
