from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH_SCRIPT = ROOT / 'tools/run_generation_queue.py'
AUDIO_SCRIPT = ROOT / 'tools/run_audio_bgm_with_sfx_smoke.py'


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_wav(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b'\x00\x00' * 800)


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / 'project'
    write_json(project / 'docs/automation/project_contract.json', {
        'comfyui_endpoint': 'http://127.0.0.1:8000',
        'comfyui_endpoint_candidates': ['http://127.0.0.1:8000'],
        'workflow_pack_root': str(tmp_path / 'workflow_pack'),
        'comfyui_output_root': str(tmp_path / 'comfy_output'),
        'workflow_routes': {'sfx': 'audio_bgm_with_sfx'},
    })
    write_json(project / 'game/data/asset_manifest.json', {'version': '1.0.0', 'assets': []})
    write_json(project / 'docs/production/prompt_slots/sfx_door_knock_soft.json', {
        'workflow_id': 'audio_bgm_with_sfx',
        'asset_id': 'sfx_door_knock_soft',
        'author': 'agent',
        'prompt_slots': {
            'positive_prompt': 'soft door knock, realistic visual novel sound effect, short clean foley, close microphone, no music, no speech',
            'negative_prompt': 'music, speech, voice, singing, distorted',
        },
    })
    resolved = project / 'docs/production/asset_requests/scene.resolved_asset_requests.json'
    write_json(resolved, {
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
    return project


def test_generation_orchestrator_runs_generate_items_and_writes_qa_reports(tmp_path: Path):
    project = make_project(tmp_path)
    fake_runner = tmp_path / 'fake_runner.py'
    fake_runner.write_text(
        "import argparse, json, wave\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--project-root'); parser.add_argument('--asset-id'); parser.add_argument('--description'); parser.add_argument('--scene-id'); parser.add_argument('--prompt-slots'); parser.add_argument('--asset-type')\n"
        "args=parser.parse_args()\n"
        "root=Path(args.project_root)\n"
        "run_dir=root/'docs/automation/generation_runs/fake_sfx_run'\n"
        "cand=root/'docs/automation/generated_candidates/audio/fake_sfx_run/sfx_door_knock_soft.wav'\n"
        "cand.parent.mkdir(parents=True, exist_ok=True); run_dir.mkdir(parents=True, exist_ok=True)\n"
        "with wave.open(str(cand),'wb') as w:\n    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b'\\x00\\x00'*800)\n"
        "meta={'run_id':'fake_sfx_run','asset_type':'sfx','workflow_id':'audio_bgm_with_sfx','asset_id':args.asset_id,'positive_prompt':args.description,'candidate_copies':[str(cand)],'promotion_status':'not_promoted','qa_status':'pending_file_qa'}\n"
        "meta_path=run_dir/'metadata.json'; meta_path.write_text(json.dumps(meta, indent=2)+'\\n', encoding='utf-8')\n"
        "print('RUN_ID fake_sfx_run'); print('METADATA', meta_path)\n",
        encoding='utf-8',
    )
    out = project / 'docs/automation/generation_batch.json'
    proc = subprocess.run([
        sys.executable, str(ORCH_SCRIPT),
        '--project-root', str(project),
        '--resolved-glob', 'docs/production/asset_requests/*.resolved_asset_requests.json',
        '--runner', f'audio_bgm_with_sfx={sys.executable} {fake_runner}',
        '--out', str(out),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'generated 1' in proc.stdout
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['counts']['generated'] == 1
    result = data['results'][0]
    assert result['asset_id'] == 'sfx_door_knock_soft'
    assert result['metadata_path'].endswith('metadata.json')
    assert result['qa_reports'][0]['status'] == 'pass'
    assert Path(result['qa_reports'][0]['path']).exists()
    metadata = json.loads(Path(result['metadata_path']).read_text(encoding='utf-8'))
    assert metadata['qa_status'] == 'qa_pass_candidate_not_promoted'
    assert metadata['qa_reports'][0]['status'] == 'pass'
    assert metadata['qa_report'] == metadata['qa_reports'][0]['path']
    assert Path(metadata['qa_report']).exists()
    assert metadata['promotion_status'] == 'not_promoted_pending_owner_approval'


def test_generation_orchestrator_passes_scene_event_source_char_base_metadata(tmp_path: Path):
    project = make_project(tmp_path)
    char_meta = project / 'docs/automation/generation_runs/char_source/metadata.json'
    write_json(char_meta, {'run_id': 'char_source', 'seed': 123, 'scene_event_cg_seed_to_reuse': 123})
    write_json(project / 'docs/production/prompt_slots/event_test.json', {
        'workflow_id': 'scene_event_cg',
        'asset_id': 'event_test',
        'prompt_slots': {
            'character_features': ['medium_hair'],
            'outfit_detail': ['white_shirt'],
            'scene_context': ['indoors'],
        },
    })
    write_json(project / 'docs/production/asset_requests/scene.resolved_asset_requests.json', {
        'scene_id': 'scene',
        'resolved_asset_requests': [{
            'asset_id': 'event_test',
            'asset_type': 'scene_event_cg',
            'description': 'event test',
            'decision': 'generate',
            'status': 'needs_generation',
            'recommended_workflow_id': 'scene_event_cg',
            'source_char_base_metadata': str(char_meta),
            'scene_event_route_mode': 'production_character',
        }],
    })
    fake_runner = tmp_path / 'fake_event_runner.py'
    fake_runner.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--project-root'); parser.add_argument('--asset-id'); parser.add_argument('--description'); parser.add_argument('--scene-id'); parser.add_argument('--prompt-slots'); parser.add_argument('--char-base-metadata'); parser.add_argument('--route-mode')\n"
        "args=parser.parse_args()\n"
        "assert args.char_base_metadata and args.char_base_metadata.endswith('metadata.json'), args.char_base_metadata\n"
        "root=Path(args.project_root); run_dir=root/'docs/automation/generation_runs/fake_event_run'; run_dir.mkdir(parents=True, exist_ok=True)\n"
        "meta={'run_id':'fake_event_run','asset_type':'scene_event_cg','workflow_id':'scene_event_cg','asset_id':args.asset_id,'candidate_copies':[],'source_char_base_metadata':args.char_base_metadata,'promotion_status':'not_promoted','qa_status':'pending_visual_review'}\n"
        "meta_path=run_dir/'metadata.json'; meta_path.write_text(json.dumps(meta, indent=2)+'\\n', encoding='utf-8')\n"
        "print('RUN_ID fake_event_run'); print('METADATA', meta_path)\n",
        encoding='utf-8',
    )
    out = project / 'docs/automation/generation_batch.json'
    proc = subprocess.run([
        sys.executable, str(ORCH_SCRIPT),
        '--project-root', str(project),
        '--resolved-glob', 'docs/production/asset_requests/*.resolved_asset_requests.json',
        '--runner', f'scene_event_cg={sys.executable} {fake_runner}',
        '--out', str(out),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    event_result = next(r for r in data['results'] if r['asset_id'] == 'event_test')
    assert event_result['status'] == 'generated'
    assert '--char-base-metadata' in event_result['command']
    assert str(char_meta) in event_result['command']
    assert '--route-mode' in event_result['command']
    assert 'production_character' in event_result['command']


def test_generation_orchestrator_passes_char_alpha_source_metadata(tmp_path: Path):
    project = make_project(tmp_path)
    source_meta = project / 'docs/automation/generation_runs/source_char/metadata.json'
    write_json(source_meta, {'run_id': 'source_char', 'candidate_copies': ['source.png']})
    write_json(project / 'docs/production/asset_requests/scene.resolved_asset_requests.json', {
        'scene_id': 'scene',
        'resolved_asset_requests': [{
            'asset_id': 'alpha_sprite_test',
            'asset_type': 'transparent_sprite',
            'description': 'alpha sprite test',
            'decision': 'generate',
            'status': 'needs_generation',
            'recommended_workflow_id': 'char_alpha',
            'source_char_base_metadata': str(source_meta),
        }],
    })
    fake_runner = tmp_path / 'fake_alpha_runner.py'
    fake_runner.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--project-root'); parser.add_argument('--asset-id'); parser.add_argument('--description'); parser.add_argument('--scene-id'); parser.add_argument('--source-metadata')\n"
        "args=parser.parse_args()\n"
        "assert args.source_metadata and args.source_metadata.endswith('metadata.json'), args.source_metadata\n"
        "root=Path(args.project_root); run_dir=root/'docs/automation/generation_runs/fake_alpha_run'; run_dir.mkdir(parents=True, exist_ok=True)\n"
        "meta={'run_id':'fake_alpha_run','asset_type':'transparent_sprite','workflow_id':'char_alpha','asset_id':args.asset_id,'candidate_copies':[],'source_metadata':args.source_metadata,'promotion_status':'not_promoted','qa_status':'pending_visual_review'}\n"
        "meta_path=run_dir/'metadata.json'; meta_path.write_text(json.dumps(meta, indent=2)+'\\n', encoding='utf-8')\n"
        "print('RUN_ID fake_alpha_run'); print('METADATA', meta_path)\n",
        encoding='utf-8',
    )
    out = project / 'docs/automation/generation_batch.json'
    proc = subprocess.run([
        sys.executable, str(ORCH_SCRIPT),
        '--project-root', str(project),
        '--resolved-glob', 'docs/production/asset_requests/*.resolved_asset_requests.json',
        '--runner', f'char_alpha={sys.executable} {fake_runner}',
        '--out', str(out),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    alpha_result = next(r for r in data['results'] if r['asset_id'] == 'alpha_sprite_test')
    assert alpha_result['status'] == 'generated'
    assert '--source-metadata' in alpha_result['command']
    assert str(source_meta) in alpha_result['command']


def test_generation_orchestrator_passes_char_expression_prompt_slots_and_source_metadata(tmp_path: Path):
    project = make_project(tmp_path)
    source_meta = project / 'docs/automation/generation_runs/source_char/metadata.json'
    write_json(source_meta, {'run_id': 'source_char', 'candidate_copies': ['source.png']})
    slots = project / 'docs/production/prompt_slots/expr_happy_test.json'
    write_json(slots, {
        'workflow_id': 'char_expression',
        'asset_id': 'expr_happy_test',
        'prompt_slots': {
            'identity_tags': ['medium_hair'],
            'expression_positive': ['happy'],
            'expression_negative': ['sad'],
        },
    })
    write_json(project / 'docs/production/asset_requests/scene.resolved_asset_requests.json', {
        'scene_id': 'scene',
        'resolved_asset_requests': [{
            'asset_id': 'expr_happy_test',
            'asset_type': 'character_expression',
            'description': 'happy expression test',
            'decision': 'generate',
            'status': 'needs_generation',
            'recommended_workflow_id': 'char_expression',
            'source_char_base_metadata': str(source_meta),
        }],
    })
    fake_runner = tmp_path / 'fake_expression_runner.py'
    fake_runner.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--project-root'); parser.add_argument('--asset-id'); parser.add_argument('--description'); parser.add_argument('--scene-id'); parser.add_argument('--prompt-slots'); parser.add_argument('--source-metadata')\n"
        "args=parser.parse_args()\n"
        "assert args.prompt_slots and args.prompt_slots.endswith('expr_happy_test.json'), args.prompt_slots\n"
        "assert args.source_metadata and args.source_metadata.endswith('metadata.json'), args.source_metadata\n"
        "root=Path(args.project_root); run_dir=root/'docs/automation/generation_runs/fake_expression_run'; run_dir.mkdir(parents=True, exist_ok=True)\n"
        "meta={'run_id':'fake_expression_run','asset_type':'character_expression','workflow_id':'char_expression','asset_id':args.asset_id,'candidate_copies':[],'prompt_slots_path':args.prompt_slots,'source_metadata':args.source_metadata,'promotion_status':'not_promoted','qa_status':'pending_visual_review'}\n"
        "meta_path=run_dir/'metadata.json'; meta_path.write_text(json.dumps(meta, indent=2)+'\\n', encoding='utf-8')\n"
        "print('RUN_ID fake_expression_run'); print('METADATA', meta_path)\n",
        encoding='utf-8',
    )
    out = project / 'docs/automation/generation_batch.json'
    proc = subprocess.run([
        sys.executable, str(ORCH_SCRIPT),
        '--project-root', str(project),
        '--resolved-glob', 'docs/production/asset_requests/*.resolved_asset_requests.json',
        '--runner', f'char_expression={sys.executable} {fake_runner}',
        '--out', str(out),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    result = next(r for r in data['results'] if r['asset_id'] == 'expr_happy_test')
    assert result['status'] == 'generated'
    assert '--prompt-slots' in result['command']
    assert str(slots) in result['command']
    assert '--source-metadata' in result['command']
    assert str(source_meta) in result['command']


def test_audio_bgm_with_sfx_runner_prepare_only_patches_prompt_and_metadata(tmp_path: Path):
    project = tmp_path / 'project'
    workflow_pack = tmp_path / 'workflow_pack'
    output_root = tmp_path / 'output'
    input_root = tmp_path / 'input'
    write_json(project / 'docs/automation/project_contract.json', {
        'workflow_pack_root': str(workflow_pack),
        'comfyui_output_root': str(output_root),
        'comfyui_input_root': str(input_root),
        'comfyui_endpoint_candidates': ['http://127.0.0.1:65534'],
    })
    workflow = {
        '52:31': {'class_type': 'PrimitiveStringMultiline', 'inputs': {'value': 'old prompt'}},
        '52:7': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'old negative'}},
        '52:43': {'class_type': 'CustomCombo', 'inputs': {'choice': 'Music', 'index': 0}},
        '52:36': {'class_type': 'PrimitiveFloat', 'inputs': {'value': 150.0}},
        '52:35': {'class_type': 'PrimitiveBoolean', 'inputs': {'value': True}},
        '52:3': {'class_type': 'KSampler', 'inputs': {'seed': 0, 'steps': 8, 'cfg': 1.0, 'sampler_name': 'lcm', 'scheduler': 'simple'}},
        '19': {'class_type': 'SaveAudioMP3', 'inputs': {'filename_prefix': 'old_prefix'}},
    }
    write_json(workflow_pack / 'audio_bgm_with_sfx/audio_bgm_with_sfx_workflow_api.json', workflow)
    slots = project / 'docs/production/prompt_slots/sfx_door_knock_soft.json'
    write_json(slots, {
        'workflow_id': 'audio_bgm_with_sfx',
        'asset_id': 'sfx_door_knock_soft',
        'prompt_slots': {
            'positive_prompt': 'An old wooden door opens slowly with one clear metal hinge creak and a soft wooden handle click.',
        },
    })
    out = project / 'docs/automation/generation_runs/prepared.json'
    proc = subprocess.run([
        sys.executable, str(AUDIO_SCRIPT),
        '--project-root', str(project),
        '--asset-id', 'sfx_door_knock_soft',
        '--description', 'soft wooden door knock',
        '--scene-id', 'scene',
        '--prompt-slots', str(slots),
        '--prepare-only',
        '--out-metadata', str(out),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['asset_id'] == 'sfx_door_knock_soft'
    assert data['workflow_id'] == 'audio_bgm_with_sfx'
    assert data['audio_mode'] == 'One-shot'
    assert data['audio_role'] == 'audio_sfx'
    assert data['prompt_shape'] == 'short positive-only natural-language cue + one/two material or timbre colors'
    assert data['negative_prompt_strategy'] == 'blank_by_default_per_owner_qa_unless_prompt_slots_override'
    patched = json.loads(Path(data['patched_workflow_path']).read_text(encoding='utf-8'))
    assert 'old wooden door opens slowly' in patched['52:31']['inputs']['value']
    assert patched['52:7']['inputs']['text'] == ''
    assert patched['52:43']['inputs']['choice'] == 'One-shot'
    assert patched['19']['inputs']['filename_prefix'].startswith('audio_bgm_with_sfx/')
