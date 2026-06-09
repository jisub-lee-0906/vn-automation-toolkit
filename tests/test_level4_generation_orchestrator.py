from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH_SCRIPT = ROOT / 'tools/run_generation_queue.py'
SFX_SCRIPT = ROOT / 'tools/run_audio_sfx_mmaudio_smoke.py'


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
        'workflow_routes': {'sfx': 'audio_sfx_mmaudio'},
    })
    write_json(project / 'game/data/asset_manifest.json', {'version': '1.0.0', 'assets': []})
    write_json(project / 'docs/production/prompt_slots/sfx_door_knock_soft.json', {
        'workflow_id': 'audio_sfx_mmaudio',
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
            'recommended_workflow_id': 'audio_sfx_mmaudio',
        }],
    })
    return project


def test_generation_orchestrator_runs_generate_items_and_writes_qa_reports(tmp_path: Path):
    project = make_project(tmp_path)
    fake_runner = tmp_path / 'fake_runner.py'
    fake_runner.write_text(
        "import argparse, json, wave\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--project-root'); parser.add_argument('--asset-id'); parser.add_argument('--description'); parser.add_argument('--scene-id'); parser.add_argument('--prompt-slots')\n"
        "args=parser.parse_args()\n"
        "root=Path(args.project_root)\n"
        "run_dir=root/'docs/automation/generation_runs/fake_sfx_run'\n"
        "cand=root/'docs/automation/generated_candidates/audio/fake_sfx_run/sfx_door_knock_soft.wav'\n"
        "cand.parent.mkdir(parents=True, exist_ok=True); run_dir.mkdir(parents=True, exist_ok=True)\n"
        "with wave.open(str(cand),'wb') as w:\n    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b'\\x00\\x00'*800)\n"
        "meta={'run_id':'fake_sfx_run','asset_type':'sfx','workflow_id':'audio_sfx_mmaudio','asset_id':args.asset_id,'positive_prompt':args.description,'candidate_copies':[str(cand)],'promotion_status':'not_promoted','qa_status':'pending_file_qa'}\n"
        "meta_path=run_dir/'metadata.json'; meta_path.write_text(json.dumps(meta, indent=2)+'\\n', encoding='utf-8')\n"
        "print('RUN_ID fake_sfx_run'); print('METADATA', meta_path)\n",
        encoding='utf-8',
    )
    out = project / 'docs/automation/generation_batch.json'
    proc = subprocess.run([
        sys.executable, str(ORCH_SCRIPT),
        '--project-root', str(project),
        '--resolved-glob', 'docs/production/asset_requests/*.resolved_asset_requests.json',
        '--runner', f'audio_sfx_mmaudio={sys.executable} {fake_runner}',
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
        }],
    })
    fake_runner = tmp_path / 'fake_event_runner.py'
    fake_runner.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--project-root'); parser.add_argument('--asset-id'); parser.add_argument('--description'); parser.add_argument('--scene-id'); parser.add_argument('--prompt-slots'); parser.add_argument('--char-base-metadata')\n"
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


def test_audio_sfx_runner_prepare_only_patches_prompt_and_metadata(tmp_path: Path):
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
        '1': {'class_type': 'VHS_LoadVideo', 'inputs': {'video': 'placeholder.mp4'}},
        '2': {'class_type': 'MMAudioModelLoader', 'inputs': {'mmaudio_model': 'model.safetensors', 'base_precision': 'fp16'}},
        '3': {'class_type': 'MMAudioFeatureUtilsLoader', 'inputs': {'vae_model': 'vae.safetensors', 'synchformer_model': 'sync.safetensors', 'clip_model': 'clip.safetensors'}},
        '4': {'class_type': 'MMAudioSampler', 'inputs': {'duration': 8.0, 'steps': 25, 'cfg': 4.5, 'seed': 202, 'prompt': 'old', 'negative_prompt': 'bad'}},
        '5': {'class_type': 'SaveAudio', 'inputs': {'filename_prefix': 'old_prefix'}},
    }
    write_json(workflow_pack / 'audio_sfx_mmaudio/audio_sfx_mmaudio_workflow_api.json', workflow)
    slots = project / 'docs/production/prompt_slots/sfx_door_knock_soft.json'
    write_json(slots, {
        'workflow_id': 'audio_sfx_mmaudio',
        'asset_id': 'sfx_door_knock_soft',
        'prompt_slots': {
            'positive_prompt': 'soft wooden door knock, realistic visual novel sound effect, short clean foley, close microphone, no music, no speech',
            'negative_prompt': 'music, speech, voice, singing, distorted',
        },
    })
    out = tmp_path / 'prepared.json'
    proc = subprocess.run([
        sys.executable, str(SFX_SCRIPT),
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
    assert data['workflow_id'] == 'audio_sfx_mmaudio'
    patched = json.loads(Path(data['patched_workflow_path']).read_text(encoding='utf-8'))
    assert 'soft wooden door knock' in patched['4']['inputs']['prompt']
    assert patched['5']['inputs']['filename_prefix'].startswith('audio_sfx_mmaudio/')
