#!/usr/bin/env python3
"""Run/preflight the char_expression face-expression workflow.

This runner is prompt-sensitive but fixture-safe: the agent supplies explicit
identity/expression prompt slots, the runner validates tags, stages the source
image, patches a runtime workflow copy, and records provenance metadata.
"""
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

from danbooru_taxonomy import validate_tags
from vn_product_config import build_project_paths, require_under

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
DEFAULT_SEED = 719251301
DEFAULT_DENOISE = 0.4

README_POSITIVE = (
    'masterpiece, best_quality, amazing_quality, 4k, very_aesthetic, high_resolution, '
    'ultra-detailed, absurdres, newest, 1girl, solo, cowboy_shot, standing, '
    'facing_viewer, looking_at_viewer, arms_at_sides, {identity_tags}, {expression_positive}, '
    'BREAK, depth_of_field, volumetric_lighting'
)
README_NEGATIVE = (
    'modern, recent, old, oldest, cartoon, graphic, text, painting, crayon, graphite, '
    'abstract, glitch, deformed, mutated, ugly, disfigured, lowres, bad_anatomy, '
    'cropped, very_displeasing, sketch, jpeg_artifacts, signature, watermark, username, '
    'conjoined, bad_ai-generated, (worst_quality, bad_quality:1.2), {expression_negative}'
)


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9_]+', '_', str(value).strip().lower().replace('-', '_')).strip('_')
    return slug or 'char_expression'


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def listify(value) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(',') if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


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


def load_prompt_slots(path: Path, workflow_id: str, asset_id: str) -> tuple[list[str], list[str], list[str], str, dict[str, Any]]:
    data = load_json(path)
    if data.get('workflow_id') and data.get('workflow_id') != workflow_id:
        raise RuntimeError(f'Prompt slots workflow_id mismatch: expected {workflow_id}, got {data.get("workflow_id")}')
    if data.get('asset_id') and asset_id and data.get('asset_id') != asset_id:
        raise RuntimeError(f'Prompt slots asset_id mismatch: expected {asset_id}, got {data.get("asset_id")}')
    slots = data.get('prompt_slots') or {}
    identity_tags = listify(slots.get('identity_tags') or slots.get('character_features'))
    expression_positive = listify(slots.get('expression_positive') or slots.get('emotion_positive'))
    expression_negative = listify(slots.get('expression_negative') or slots.get('emotion_negative'))
    expression_id = str(data.get('expression_id') or slots.get('expression_id') or data.get('asset_id') or asset_id)
    if not identity_tags or not expression_positive or not expression_negative:
        raise RuntimeError('UNROUTED_CHAR_EXPRESSION: agent-authored prompt_slots.identity_tags, expression_positive, and expression_negative are required')
    return identity_tags, expression_positive, expression_negative, expression_id, data


def resolve_confined_existing_file(raw: str | Path, project_root: Path, label: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    require_under(path, project_root, label)
    if not path.exists() or not path.is_file():
        raise RuntimeError(f'{label} not found: {path}')
    return path


def source_image_from_metadata(metadata_path: Path, project_root: Path) -> tuple[Path, dict[str, Any]]:
    require_under(metadata_path.resolve(), project_root, 'source-metadata')
    if not metadata_path.exists() or not metadata_path.is_file():
        raise RuntimeError(f'source metadata not found: {metadata_path}')
    metadata = load_json(metadata_path)
    for raw in metadata.get('candidate_copies') or metadata.get('output_paths') or []:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = project_root / path
        path = path.resolve()
        try:
            require_under(path, project_root, 'source image from metadata')
        except ValueError:
            continue
        if path.exists() and path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            return path, metadata
    raise RuntimeError(f'no usable candidate image found in source metadata: {metadata_path}')


def stage_source_image(source_image: Path, input_root: Path, run_id: str) -> Path:
    input_root.mkdir(parents=True, exist_ok=True)
    staged = input_root / f'{run_id}_source{source_image.suffix.lower() or ".png"}'
    shutil.copy2(source_image, staged)
    return staged.resolve()


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
        except Exception as exc:
            errors.append(f'{base}: {type(exc).__name__} {exc}')
    raise RuntimeError('No live ComfyUI endpoint found: ' + '; '.join(errors))


def submit_prompt(endpoint: str, workflow: dict) -> str:
    payload = json.dumps({'prompt': workflow, 'client_id': str(uuid.uuid4())}).encode('utf-8')
    req = urllib.request.Request(endpoint + '/prompt', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode('utf-8', errors='replace')
            data = json.loads(body)
            print('prompt_submit_status', r.status)
            print('prompt_submit_response', body)
            return data['prompt_id']
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'/prompt HTTP {exc.code}: {body}') from exc


def wait_history(endpoint: str, prompt_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            status, hist = url_json(endpoint + '/history/' + prompt_id, timeout=10)
            if status == 200 and isinstance(hist, dict) and prompt_id in hist:
                return hist[prompt_id]
        except Exception:
            pass
        time.sleep(5)
    raise TimeoutError(f'history did not complete within {timeout_s}s for {prompt_id}')


def image_paths_from_history(history: dict, output_root: Path) -> list[Path]:
    root = output_root.resolve()
    paths: list[Path] = []
    for node_out in history.get('outputs', {}).values():
        if not isinstance(node_out, dict):
            continue
        for img in node_out.get('images', []):
            filename = img.get('filename')
            subfolder = img.get('subfolder', '') or ''
            typ = img.get('type', 'output')
            if filename and typ == 'output':
                candidate = (root / subfolder / filename).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError:
                    continue
                paths.append(candidate)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--asset-id', default='char_expression')
    parser.add_argument('--scene-id', default='')
    parser.add_argument('--description', default='')
    parser.add_argument('--source-image', default=None)
    parser.add_argument('--source-metadata', default=None)
    parser.add_argument('--prompt-slots', default=None)
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--denoise', type=float, default=DEFAULT_DENOISE)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--out-metadata', default=None)
    args = parser.parse_args()

    project_paths = build_project_paths(args.project_root, None)
    project_root = project_paths.project_root
    contract = project_paths.contract
    if args.out_metadata:
        try:
            require_under(Path(args.out_metadata).expanduser().resolve(), project_root, 'out-metadata')
        except ValueError as exc:
            print(f'CHAR_EXPRESSION_REFUSED: {exc}')
            return 2

    prompt_slots_path = resolve_prompt_slots_path(project_root, Path(args.prompt_slots)) if args.prompt_slots else prompt_slots_path_for(project_root, args.asset_id, args.scene_id)
    if prompt_slots_path is None:
        raise RuntimeError('UNROUTED_CHAR_EXPRESSION: missing agent-authored prompt slots JSON under docs/production/prompt_slots')
    identity_tags, expression_positive, expression_negative, expression_id, prompt_slots_data = load_prompt_slots(prompt_slots_path, 'char_expression', args.asset_id)

    try:
        if bool(args.source_image) == bool(args.source_metadata):
            raise RuntimeError('CHAR_EXPRESSION_SOURCE_REQUIRED: pass exactly one of --source-image or --source-metadata')
        source_metadata_path: Path | None = None
        source_metadata: dict[str, Any] | None = None
        if args.source_metadata:
            source_metadata_path = resolve_confined_existing_file(args.source_metadata, project_root, 'source-metadata')
            source_image, source_metadata = source_image_from_metadata(source_metadata_path, project_root)
        else:
            source_image = resolve_confined_existing_file(args.source_image, project_root, 'source-image')
    except ValueError as exc:
        print(f'CHAR_EXPRESSION_REFUSED: {exc}')
        return 2

    if source_image.suffix.lower() not in IMAGE_EXTS:
        raise RuntimeError(f'CHAR_EXPRESSION_SOURCE_UNSUPPORTED: expected image file, got {source_image}')

    workflow_root = Path(contract['workflow_pack_root']).expanduser().resolve()
    input_root = Path(contract.get('comfyui_input_root') or contract.get('comfyui_windows_input_root') or project_root / 'docs/automation/comfyui_input').expanduser().resolve()
    output_root = Path(contract.get('comfyui_output_root') or project_root / 'docs/automation/comfyui_output').expanduser().resolve()
    workflow_path = workflow_root / 'char_expression/char_expression_workflow_api.json'
    if not workflow_path.exists():
        raise RuntimeError(f'char_expression workflow not found: {workflow_path}')

    placeholder_tags = identity_tags + expression_positive + expression_negative
    taxonomy_validation, taxonomy_meta = validate_tags(workflow_root, placeholder_tags)

    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f'char_expression_{slugify(args.asset_id)}_{timestamp}'
    filename_prefix = f'hermes_vn_char_expression/{run_id}_{slugify(expression_id)}'
    staged_source = stage_source_image(source_image, input_root, run_id)

    positive = README_POSITIVE.format(identity_tags=', '.join(identity_tags), expression_positive=', '.join(expression_positive))
    negative = README_NEGATIVE.format(expression_negative=', '.join(expression_negative))

    workflow['1']['inputs']['image'] = staged_source.name
    workflow['6']['inputs']['text'] = positive
    workflow['7']['inputs']['text'] = negative
    workflow['13']['inputs']['seed'] = args.seed
    workflow['13']['inputs']['denoise'] = args.denoise
    workflow['19']['inputs']['filename_prefix'] = filename_prefix

    run_dir = project_paths.generation_runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    patched_workflow_path = run_dir / 'char_expression_patched_workflow_api.json'
    save_json(patched_workflow_path, workflow)

    base_metadata = {
        'run_id': run_id,
        'asset_id': args.asset_id,
        'scene_id': args.scene_id,
        'description': args.description,
        'asset_type': 'character_expression',
        'workflow_id': 'char_expression',
        'expression_id': expression_id,
        'workflow_path': str(workflow_path),
        'workflow_sha256': workflow_sha,
        'patched_workflow_path': str(patched_workflow_path),
        'source_image': str(source_image),
        'source_metadata': str(source_metadata_path) if source_metadata_path else None,
        'source_run_id': source_metadata.get('run_id') if source_metadata else None,
        'staged_source_image': str(staged_source),
        'comfyui_input_root': str(input_root),
        'prompt_source': 'agent_authored_prompt_slots',
        'prompt_slots_path': str(prompt_slots_path),
        'prompt_slots': prompt_slots_data,
        'prompt_policy': 'README wrapper + agent-authored SQLite-verified expression prompt slots only',
        'taxonomy_source': taxonomy_meta['taxonomy_source'],
        'taxonomy_db_path': taxonomy_meta['taxonomy_db_path'],
        'legacy_csv_path': taxonomy_meta['legacy_csv_path'],
        'legacy_csv_used': taxonomy_meta['legacy_csv_used'],
        'taxonomy_placeholder_tags': placeholder_tags,
        'taxonomy_validation': taxonomy_validation,
        'identity_tags': identity_tags,
        'expression_positive': expression_positive,
        'expression_negative': expression_negative,
        'positive_prompt': positive,
        'negative_prompt': negative,
        'seed': args.seed,
        'denoise': args.denoise,
        'filename_prefix': filename_prefix,
        'output_paths': [],
        'candidate_copies': [],
        'qa_status': 'prepare_only' if args.prepare_only else 'pending_visual_review',
        'promotion_status': 'not_promoted',
        'prepare_only': bool(args.prepare_only),
    }

    print('RUN_ID', run_id)
    print('WORKFLOW', str(workflow_path))
    print('SOURCE_IMAGE', str(source_image))
    print('STAGED_SOURCE_IMAGE', str(staged_source))
    print('PROMPT_POLICY', base_metadata['prompt_policy'])
    print('TAXONOMY_SOURCE', taxonomy_meta['taxonomy_source'])
    print('POSITIVE', positive)
    print('NEGATIVE', negative)
    print('SEED', args.seed)
    print('DENOISE', args.denoise)

    if args.prepare_only:
        metadata_path = Path(args.out_metadata).expanduser().resolve() if args.out_metadata else run_dir / 'metadata.json'
        save_json(metadata_path, base_metadata)
        print('METADATA', str(metadata_path))
        print('PREPARE_ONLY')
        return 0

    endpoint = discover_endpoint(contract.get('comfyui_endpoint_candidates') or [contract['comfyui_endpoint']])
    print('ENDPOINT', endpoint)
    prompt_id = submit_prompt(endpoint, workflow)
    print('PROMPT_ID', prompt_id)
    history = wait_history(endpoint, prompt_id)
    history_path = run_dir / 'history.json'
    save_json(history_path, history)
    output_paths = image_paths_from_history(history, output_root)
    copied_paths: list[Path] = []
    candidate_dir = project_root / 'docs/automation/generated_candidates/characters' / run_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    for src in output_paths:
        print('OUTPUT_PATH', str(src), 'exists=', src.exists())
        if src.exists():
            dst = candidate_dir / f'candidate_{len(copied_paths) + 1:02d}{src.suffix.lower() or ".png"}'
            shutil.copy2(src, dst)
            copied_paths.append(dst)
            print('CANDIDATE_COPY', str(dst))
    metadata = {**base_metadata, 'endpoint': endpoint, 'prompt_id': prompt_id, 'history_path': str(history_path), 'output_paths': [str(p) for p in output_paths], 'candidate_copies': [str(p) for p in copied_paths], 'qa_status': 'pending_visual_review', 'prepare_only': False}
    metadata_path = run_dir / 'metadata.json'
    save_json(metadata_path, metadata)
    print('METADATA', str(metadata_path))
    if not output_paths or not all(p.exists() for p in output_paths):
        print('GENERATION_FAILED_NO_VERIFIED_OUTPUT')
        return 2
    print('GENERATION_OUTPUT_VERIFIED')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('ERROR', type(exc).__name__, exc, file=sys.stderr)
        raise
