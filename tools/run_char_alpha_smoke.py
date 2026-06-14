#!/usr/bin/env python3
"""Run/preflight the char_alpha transparent sprite workflow.

This workflow has no creative prompt. It stages an already QA-reviewed source
character image into the active ComfyUI input root, patches LoadImage and
SaveImage on a runtime workflow copy, and records provenance metadata.
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

from vn_product_config import build_project_paths, require_under

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9_]+', '_', str(value).strip().lower().replace('-', '_')).strip('_')
    return slug or 'char_alpha'


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


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
    candidates = metadata.get('candidate_copies') or metadata.get('output_paths') or []
    for raw in candidates:
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
    suffix = source_image.suffix.lower() or '.png'
    staged = input_root / f'{run_id}_source{suffix}'
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
    parser.add_argument('--asset-id', default='char_alpha')
    parser.add_argument('--scene-id', default='')
    parser.add_argument('--description', default='')
    parser.add_argument('--source-image', default=None, help='Project-confined source image to alpha-cut.')
    parser.add_argument('--source-metadata', default=None, help='Project-confined metadata containing candidate_copies/output_paths.')
    parser.add_argument('--prepare-only', action='store_true', help='Patch workflow and write metadata without submitting to ComfyUI.')
    parser.add_argument('--out-metadata', default=None)
    args = parser.parse_args()

    project_paths = build_project_paths(args.project_root, None)
    project_root = project_paths.project_root
    contract = project_paths.contract

    if args.out_metadata:
        try:
            require_under(Path(args.out_metadata).expanduser().resolve(), project_root, 'out-metadata')
        except ValueError as exc:
            print(f'CHAR_ALPHA_REFUSED: {exc}')
            return 2

    try:
        if bool(args.source_image) == bool(args.source_metadata):
            raise RuntimeError('CHAR_ALPHA_SOURCE_REQUIRED: pass exactly one of --source-image or --source-metadata')
        source_metadata_path: Path | None = None
        source_metadata: dict[str, Any] | None = None
        if args.source_metadata:
            source_metadata_path = resolve_confined_existing_file(args.source_metadata, project_root, 'source-metadata')
            source_image, source_metadata = source_image_from_metadata(source_metadata_path, project_root)
        else:
            source_image = resolve_confined_existing_file(args.source_image, project_root, 'source-image')
    except ValueError as exc:
        print(f'CHAR_ALPHA_REFUSED: {exc}')
        return 2

    if source_image.suffix.lower() not in IMAGE_EXTS:
        raise RuntimeError(f'CHAR_ALPHA_SOURCE_UNSUPPORTED: expected image file, got {source_image}')

    workflow_root = Path(contract['workflow_pack_root']).expanduser().resolve()
    output_root = Path(contract.get('comfyui_output_root') or project_root / 'docs/automation/comfyui_output').expanduser().resolve()
    input_root = Path(contract.get('comfyui_input_root') or contract.get('comfyui_windows_input_root') or project_root / 'docs/automation/comfyui_input').expanduser().resolve()
    workflow_path = workflow_root / 'char_alpha/char_alpha_workflow_api.json'
    if not workflow_path.exists():
        raise RuntimeError(f'char_alpha workflow not found: {workflow_path}')

    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    asset_slug = slugify(args.asset_id)
    run_id = f'char_alpha_{asset_slug}_{timestamp}'
    filename_prefix = f'hermes_vn_char_alpha/{run_id}'
    staged_source = stage_source_image(source_image, input_root, run_id)

    workflow['1']['inputs']['image'] = staged_source.name
    workflow['3']['inputs']['filename_prefix'] = filename_prefix

    runs_root = project_paths.generation_runs_root
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    patched_workflow_path = run_dir / 'char_alpha_patched_workflow_api.json'
    save_json(patched_workflow_path, workflow)

    base_metadata = {
        'run_id': run_id,
        'asset_id': args.asset_id,
        'scene_id': args.scene_id,
        'description': args.description,
        'asset_type': 'transparent_sprite',
        'workflow_id': 'char_alpha',
        'workflow_path': str(workflow_path),
        'workflow_sha256': workflow_sha,
        'patched_workflow_path': str(patched_workflow_path),
        'source_image': str(source_image),
        'source_metadata': str(source_metadata_path) if source_metadata_path else None,
        'source_run_id': source_metadata.get('run_id') if source_metadata else None,
        'staged_source_image': str(staged_source),
        'comfyui_input_root': str(input_root),
        'filename_prefix': filename_prefix,
        'prompt_policy': 'no_prompt_or_minimal; source-image alpha cutout only',
        'output_paths': [],
        'candidate_copies': [],
        'qa_status': 'prepare_only' if args.prepare_only else 'pending_visual_review',
        'promotion_status': 'not_promoted',
        'prepare_only': bool(args.prepare_only),
    }

    print('RUN_ID', run_id)
    print('WORKFLOW', str(workflow_path))
    print('SOURCE_IMAGE', str(source_image))
    if source_metadata_path:
        print('SOURCE_METADATA', str(source_metadata_path))
    print('STAGED_SOURCE_IMAGE', str(staged_source))
    print('PATCHED_WORKFLOW', str(patched_workflow_path))
    print('PROMPT_POLICY', base_metadata['prompt_policy'])

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

    metadata = {
        **base_metadata,
        'endpoint': endpoint,
        'prompt_id': prompt_id,
        'history_path': str(history_path),
        'output_paths': [str(p) for p in output_paths],
        'candidate_copies': [str(p) for p in copied_paths],
        'qa_status': 'pending_visual_review',
        'prepare_only': False,
    }
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
