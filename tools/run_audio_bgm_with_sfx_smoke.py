#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from vn_product_config import build_project_paths, require_under

PROJECT_ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_ID = 'audio_bgm_with_sfx'
MODE_INDEX = {'Music': 0, 'Instrument': 1, 'SFX': 2, 'One-shot': 3}
AUDIO_ROLE_CONTRACTS = {
    'bgm': {
        'audio_role': 'audio_bgm',
        'default_mode': 'Music',
        'default_duration': 24.0,
        'negative_prompt_default': '',
        'prompt_shape': 'instrumentation + musical form/rhythm + mood + short role',
        'role_contract_path': 'audio_bgm_with_sfx/roles/audio_bgm.md',
    },
    'sfx': {
        'audio_role': 'audio_sfx',
        'default_mode': 'One-shot',
        'default_duration': 2.5,
        'negative_prompt_default': '',
        'prompt_shape': 'short positive-only natural-language cue + one/two material or timbre colors',
        'role_contract_path': 'audio_bgm_with_sfx/roles/audio_sfx.md',
    },
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9_]+', '_', value.strip().lower().replace('-', '_')).strip('_')
    return slug or 'audio'


def normalize_asset_type(value: str | None) -> str:
    key = (value or '').strip().lower().replace('-', '_')
    if key in {'bgm', 'music', 'audio_bgm', 'audio_bgm_with_sfx'}:
        return 'bgm'
    if key in {'sfx', 'sound_effect', 'sound_effects', 'one_shot', 'oneshot'}:
        return 'sfx'
    return key or 'audio'


def role_contract(asset_type: str) -> dict[str, Any]:
    return AUDIO_ROLE_CONTRACTS.get(asset_type, AUDIO_ROLE_CONTRACTS['sfx'])


def default_mode(asset_type: str) -> str:
    return str(role_contract(asset_type)['default_mode'])


def default_duration(asset_type: str) -> float:
    return float(role_contract(asset_type)['default_duration'])


def resolve_prompt_slots_path(project_root: Path, path: Path) -> Path:
    root = (project_root / 'docs/production/prompt_slots').resolve()
    resolved = (path if path.is_absolute() else project_root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f'Prompt slots path must be under {root}: {resolved}') from exc
    if not resolved.exists() or not resolved.is_file():
        raise RuntimeError(f'Prompt slots file not found: {resolved}')
    return resolved


def prompt_slots_path_for(project_root: Path, asset_id: str, scene_id: str) -> Path | None:
    root = (project_root / 'docs/production/prompt_slots').resolve()
    candidates = []
    if scene_id and asset_id:
        candidates.append(root / f'{slugify(scene_id)}__{slugify(asset_id)}.json')
    if asset_id:
        candidates.append(root / f'{slugify(asset_id)}.json')
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def load_audio_prompt_slots(path: Path, asset_id: str, asset_type: str) -> dict[str, Any]:
    data = load_json(path)
    workflow_id = data.get('workflow_id')
    if workflow_id and workflow_id != WORKFLOW_ID:
        raise RuntimeError(f'Prompt slots workflow_id mismatch: expected {WORKFLOW_ID}, got {workflow_id}')
    if data.get('asset_id') and asset_id and data.get('asset_id') != asset_id:
        raise RuntimeError(f'Prompt slots asset_id mismatch: expected {asset_id}, got {data.get("asset_id")}')
    slots = data.get('prompt_slots') or {}
    prompt = str(slots.get('positive_prompt') or slots.get('audio_prompt') or slots.get('bgm_prompt') or slots.get('sfx_prompt') or '').strip()
    if not prompt:
        raise RuntimeError('UNROUTED_AUDIO: agent-authored prompt_slots.positive_prompt is required')
    expected_role = str(role_contract(asset_type)['audio_role'])
    declared_role = str(data.get('audio_role') or data.get('role') or slots.get('audio_role') or slots.get('role') or '').strip()
    if declared_role and declared_role != expected_role:
        raise RuntimeError(f'Prompt slots audio_role mismatch: expected {expected_role}, got {declared_role}')
    prompt_shape = str(slots.get('prompt_shape') or data.get('prompt_shape') or role_contract(asset_type)['prompt_shape'])
    return {
        'data': data,
        'slots': slots,
        'positive_prompt': prompt,
        'negative_prompt': str(slots.get('negative_prompt') or '').strip(),
        'audio_role': expected_role,
        'prompt_shape': prompt_shape,
    }


def url_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = r.read().decode('utf-8', errors='replace')
        return r.status, json.loads(body) if body else None


def discover_endpoint(candidates: list[str]) -> str:
    errors = []
    for base in candidates:
        base = base.rstrip('/')
        try:
            status, _ = url_json(base + '/system_stats', timeout=3)
            if status == 200:
                return base
            errors.append(f'{base}: status {status}')
        except Exception as e:
            errors.append(f'{base}: {type(e).__name__} {e}')
    raise RuntimeError('No live ComfyUI endpoint found: ' + '; '.join(errors))


def submit_prompt(endpoint: str, workflow: dict[str, Any]) -> str:
    payload = json.dumps({'prompt': workflow, 'client_id': str(uuid.uuid4())}).encode('utf-8')
    req = urllib.request.Request(endpoint + '/prompt', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode('utf-8', errors='replace')
            data = json.loads(body)
            print('prompt_submit_status', r.status)
            print('prompt_submit_response', body)
            return data['prompt_id']
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'/prompt HTTP {e.code}: {body}') from e


def wait_history(endpoint: str, prompt_id: str, timeout_s: int = 900) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_queue_print = 0.0
    while time.time() < deadline:
        try:
            status, hist = url_json(endpoint + '/history/' + prompt_id, timeout=10)
            if status == 200 and isinstance(hist, dict) and prompt_id in hist:
                item = hist[prompt_id]
                if item.get('outputs'):
                    return item
        except Exception:
            pass
        if time.time() - last_queue_print > 20:
            try:
                _, q = url_json(endpoint + '/queue', timeout=5)
                print('queue_snapshot', json.dumps(q, ensure_ascii=False)[:500])
            except Exception as e:
                print('queue_snapshot_error', type(e).__name__, e)
            last_queue_print = time.time()
        time.sleep(5)
    raise TimeoutError(f'history did not complete within {timeout_s}s for {prompt_id}')


def audio_paths_from_history(history: dict[str, Any], output_root: Path) -> list[Path]:
    root = output_root.resolve()
    paths: list[Path] = []
    for node_out in history.get('outputs', {}).values():
        if not isinstance(node_out, dict):
            continue
        for key in ('audios', 'audio'):
            entries = node_out.get(key, [])
            if isinstance(entries, dict):
                entries = [entries]
            for item in entries or []:
                if not isinstance(item, dict):
                    continue
                filename = item.get('filename')
                subfolder = str(item.get('subfolder', '') or '').replace('\\', '/')
                typ = item.get('type', 'output')
                if filename and typ == 'output':
                    candidate = (root / subfolder / filename).resolve()
                    try:
                        candidate.relative_to(root)
                    except ValueError:
                        continue
                    paths.append(candidate)
    return paths


def choose_asset_type(asset_id: str, description: str, explicit: str | None) -> str:
    if explicit:
        return normalize_asset_type(explicit)
    text = f'{asset_id} {description}'.lower()
    if 'bgm' in text or 'music' in text or 'loop' in text:
        return 'bgm'
    return 'sfx'


def prepare_workflow(
    project_root: Path,
    asset_id: str,
    description: str,
    scene_id: str,
    seed: int,
    asset_type: str,
    prompt_slots_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json(project_root / 'docs/automation/project_contract.json')
    workflow_root = Path(contract['workflow_pack_root'])
    output_root = Path(contract.get('comfyui_output_root', ''))
    workflow_path = workflow_root / 'audio_bgm_with_sfx/audio_bgm_with_sfx_workflow_api.json'
    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()
    resolved_prompt_slots = prompt_slots_path or prompt_slots_path_for(project_root, asset_id, scene_id)
    if resolved_prompt_slots is None:
        raise RuntimeError('UNROUTED_AUDIO: missing agent-authored prompt slots JSON under docs/production/prompt_slots')
    prompt_slot_values = load_audio_prompt_slots(resolved_prompt_slots, asset_id, asset_type)
    slots = prompt_slot_values['slots']
    contract_info = role_contract(asset_type)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    asset_slug = slugify(asset_id)
    run_id = f'audio_bgm_with_sfx_{asset_slug}_{timestamp}'
    run_dir = project_root / 'docs/automation/generation_runs' / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    mode = str(slots.get('mode') or slots.get('audio_mode') or default_mode(asset_type))
    if mode not in MODE_INDEX:
        raise RuntimeError(f'Unsupported audio_bgm_with_sfx mode: {mode}; expected one of {sorted(MODE_INDEX)}')
    duration = float(slots.get('duration') or slots.get('seconds') or default_duration(asset_type))
    duration = max(0.5, min(duration, 180.0))
    use_text_generate = bool(slots.get('use_text_generate', False))
    steps = int(slots.get('steps') or 8)
    cfg = float(slots.get('cfg') or 1.0)
    sampler_name = str(slots.get('sampler_name') or 'lcm')
    scheduler = str(slots.get('scheduler') or 'simple')
    filename_prefix = f'audio_bgm_with_sfx/{run_id}_{asset_slug}'

    workflow['52:31']['inputs']['value'] = prompt_slot_values['positive_prompt']
    workflow['52:7']['inputs']['text'] = prompt_slot_values['negative_prompt'] or str(contract_info['negative_prompt_default'])
    workflow['52:43']['inputs']['choice'] = mode
    workflow['52:43']['inputs']['index'] = MODE_INDEX[mode]
    workflow['52:36']['inputs']['value'] = duration
    workflow['52:35']['inputs']['value'] = use_text_generate
    workflow['52:3']['inputs']['seed'] = seed
    workflow['52:3']['inputs']['steps'] = steps
    workflow['52:3']['inputs']['cfg'] = cfg
    workflow['52:3']['inputs']['sampler_name'] = sampler_name
    workflow['52:3']['inputs']['scheduler'] = scheduler
    workflow['19']['inputs']['filename_prefix'] = filename_prefix

    patched_workflow_path = run_dir / 'audio_bgm_with_sfx_patched_workflow_api.json'
    save_json(patched_workflow_path, workflow)
    metadata = {
        'run_id': run_id,
        'asset_id': asset_id,
        'scene_id': scene_id,
        'asset_type': asset_type,
        'audio_role': prompt_slot_values['audio_role'],
        'prompt_shape': prompt_slot_values['prompt_shape'],
        'role_contract_path': str(workflow_root / contract_info['role_contract_path']),
        'negative_prompt_strategy': 'blank_by_default_per_owner_qa_unless_prompt_slots_override',
        'workflow_id': WORKFLOW_ID,
        'workflow_path': str(workflow_path),
        'workflow_sha256': workflow_sha,
        'patched_workflow_path': str(patched_workflow_path),
        'output_root': str(output_root),
        'prompt_source': 'agent_authored_prompt_slots',
        'prompt_slots_path': str(resolved_prompt_slots),
        'prompt_slots': prompt_slot_values['data'].get('prompt_slots', {}),
        'positive_prompt': workflow['52:31']['inputs']['value'],
        'negative_prompt': workflow['52:7']['inputs']['text'],
        'audio_mode': mode,
        'duration': duration,
        'use_text_generate': use_text_generate,
        'seed': seed,
        'steps': steps,
        'cfg': cfg,
        'sampler_name': sampler_name,
        'scheduler': scheduler,
        'qa_status': 'pending_file_qa',
        'promotion_status': 'not_promoted_pending_owner_approval',
        'candidate_copies': [],
        'output_paths': [],
        'postprocess_required': ['ffprobe', 'silencedetect', 'loudness_check', 'trim_tail', 'normalize_or_loop_edit', 'convert_to_ogg_before_promotion'],
    }
    return workflow, metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run one Stable Audio 3 BGM/SFX generation for a resolved VN asset request.')
    parser.add_argument('--project-root', default=str(PROJECT_ROOT))
    parser.add_argument('--asset-id', default='sfx_notification_soft')
    parser.add_argument('--description', default='soft fantasy notification sound')
    parser.add_argument('--scene-id', default='scene')
    parser.add_argument('--asset-type', choices=['bgm', 'sfx'], help='Override inferred asset type.')
    parser.add_argument('--seed', type=int, default=260610801)
    parser.add_argument('--prompt-slots', help='Agent-authored audio prompt slots JSON under docs/production/prompt_slots.')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--out-metadata')
    args = parser.parse_args(argv)

    project_paths = build_project_paths(args.project_root, None)
    project_root = project_paths.project_root
    if args.out_metadata:
        try:
            require_under(Path(args.out_metadata).expanduser().resolve(), project_root, 'out-metadata')
        except ValueError as exc:
            print(f'AUDIO_REFUSED: {exc}')
            return 2
    raw_slots = Path(args.prompt_slots) if args.prompt_slots else None
    prompt_slots_path = resolve_prompt_slots_path(project_root, raw_slots) if raw_slots else None
    asset_type = choose_asset_type(args.asset_id, args.description, args.asset_type)
    workflow, metadata = prepare_workflow(project_root, args.asset_id, args.description, args.scene_id, args.seed, asset_type, prompt_slots_path)
    run_dir = Path(metadata['patched_workflow_path']).parent
    metadata_path = Path(args.out_metadata) if args.out_metadata else run_dir / 'metadata.json'

    print('RUN_ID', metadata['run_id'])
    print('PATCHED_WORKFLOW', metadata['patched_workflow_path'])
    print('AUDIO_MODE', metadata['audio_mode'])
    print('AUDIO_ROLE', metadata['audio_role'])
    print('PROMPT_SHAPE', metadata['prompt_shape'])
    print('PROMPT', metadata['positive_prompt'])
    print('SEED', metadata['seed'])

    if args.prepare_only:
        metadata['prepare_only'] = True
        save_json(metadata_path, metadata)
        print('METADATA', metadata_path)
        print('PREPARE_ONLY')
        return 0

    contract = load_json(project_root / 'docs/automation/project_contract.json')
    endpoint = discover_endpoint(contract.get('comfyui_endpoint_candidates') or [contract['comfyui_endpoint']])
    output_root = Path(contract['comfyui_output_root'])
    metadata['endpoint'] = endpoint
    print('ENDPOINT', endpoint)

    prompt_id = submit_prompt(endpoint, workflow)
    print('PROMPT_ID', prompt_id)
    metadata['prompt_id'] = prompt_id
    history = wait_history(endpoint, prompt_id)
    history_path = run_dir / 'history.json'
    save_json(history_path, history)
    metadata['history_path'] = str(history_path)

    output_paths = audio_paths_from_history(history, output_root)
    candidate_dir = project_root / 'docs/automation/generated_candidates/audio' / metadata['run_id']
    candidate_dir.mkdir(parents=True, exist_ok=True)
    copied_paths = []
    for p in output_paths:
        print('OUTPUT_PATH', p, 'exists=', p.exists())
        if p.exists():
            dst = candidate_dir / f"candidate_{len(copied_paths) + 1:02d}{p.suffix.lower() or p.suffix or '.bin'}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            copied_paths.append(dst)
            print('CANDIDATE_COPY', dst)

    metadata['output_paths'] = [str(p) for p in output_paths]
    metadata['candidate_copies'] = [str(p) for p in copied_paths]
    save_json(metadata_path, metadata)
    print('METADATA', metadata_path)
    if not copied_paths:
        print('GENERATION_FAILED_NO_VERIFIED_OUTPUT')
        return 2
    print('GENERATION_OUTPUT_VERIFIED')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as e:
        print('ERROR', type(e).__name__, e, file=sys.stderr)
        raise
