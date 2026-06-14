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

from PIL import Image

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from danbooru_taxonomy import validate_tags

DEFAULT_PROJECT_ROOT = Path.cwd()
WIDTH = 1024
HEIGHT = 576
STEPS = 30
CFG = 3.6
SEED = 260604913

QUALITY_WRAPPER = 'masterpiece, best quality, amazing quality, very aesthetic, absurdres, highres, newest'
NEGATIVE = (
    'worst quality, low quality, bad quality, lowres, jpeg artifacts, blurry, bad anatomy, bad hands, '
    'missing fingers, extra fingers, extra digits, fewer digits, cropped, very displeasing, artist name, '
    'signature, watermark, text, fake_text, text_focus, english_text, korean_text, logo, label, caption, '
    'speech_bubble, dialogue_options, 1girl, 1boy, people, portrait, glowing_eye, animal, cat, scenery, '
    'indoors, outdoors, city, building, window_(computing), dialogue_box, icon_(computing), emblem, crest, '
    'magic_circle, runes, glyph, circle, red_circle, heart, halo, lens_flare, spotlight, gem, jewel, crystal, '
    'cross, medallion, box, paper, book, empty_picture_frame, picture_frame, photo_frame, painting, painting_(object)'
)

PROMPT_SHAPES = {
    'minimal_red_gold_border': [
        'black_background', 'no_humans', 'border', 'red_border', 'gold_border',
    ],
    'corner_alert_backdrop': [
        'game_cg', 'visual_novel', 'border', 'outside_border', 'red_border', 'black_border',
        'gold_border', 'corner', 'red_theme', 'black_theme', 'dark_background',
        'black_background', 'no_humans',
    ],
}


def slugify(value: str) -> str:
    value = re.sub(r'[^A-Za-z0-9_.-]+', '_', value.strip())
    return value.strip('_') or 'ui_alert'


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def require_under(path: Path, root: Path, code: str) -> Path:
    resolved = path.resolve()
    root = root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f'{code}: {resolved} not under {root}') from exc
    return resolved


def resolve_project_paths(project_root: Path | str, contract: str = '') -> dict[str, Path]:
    project = Path(project_root).expanduser().resolve()
    contract_path = (Path(contract).expanduser().resolve() if contract else project / 'docs/automation/project_contract.json')
    if contract:
        require_under(contract_path, project, 'UI_SYSTEM_ALERT_CONTRACT_MUST_BE_UNDER_PROJECT_ROOT')
    run_root = require_under(project / 'docs/automation/generation_runs', project, 'UI_SYSTEM_ALERT_RUN_ROOT_MUST_BE_UNDER_PROJECT_ROOT')
    candidate_root = require_under(project / 'docs/automation/generated_candidates/ui', project, 'UI_SYSTEM_ALERT_CANDIDATE_ROOT_MUST_BE_UNDER_PROJECT_ROOT')
    return {'project_root': project, 'contract_path': contract_path, 'run_root': run_root, 'candidate_root': candidate_root}


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
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'/prompt HTTP {e.code}: {body}') from e


def wait_history(endpoint: str, prompt_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            status, hist = url_json(endpoint + '/history/' + prompt_id, timeout=10)
            if status == 200 and isinstance(hist, dict) and prompt_id in hist:
                return hist[prompt_id]
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f'Timed out waiting for prompt_id={prompt_id}')


def output_paths_from_history(history: dict, output_root: Path) -> list[Path]:
    paths = []
    for node_out in history.get('outputs', {}).values():
        if not isinstance(node_out, dict):
            continue
        for img in node_out.get('images', []):
            if img.get('type') == 'output' and img.get('filename'):
                paths.append((output_root / (img.get('subfolder') or '') / img['filename']).resolve())
    return paths


def build_positive(prompt_shape: str) -> tuple[str, list[str]]:
    if prompt_shape not in PROMPT_SHAPES:
        raise RuntimeError(f'UI_SYSTEM_ALERT_UNSUPPORTED_PROMPT_SHAPE: {prompt_shape}')
    tags = PROMPT_SHAPES[prompt_shape]
    return QUALITY_WRAPPER + ', ' + ', '.join(tags), tags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', default=str(DEFAULT_PROJECT_ROOT))
    parser.add_argument('--asset-id', default='ui_system_alert_frame_smoke')
    parser.add_argument('--description', default='ui system alert frame candidate')
    parser.add_argument('--scene-id', default='ui_system_alert_frame_smoke')
    parser.add_argument('--prompt-shape', default='corner_alert_backdrop', choices=sorted(PROMPT_SHAPES))
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--contract', default='')
    args = parser.parse_args()

    paths = resolve_project_paths(args.project_root, args.contract)
    project_root = paths['project_root']
    contract_path = paths['contract_path']
    contract = load_json(contract_path)
    workflow_root = Path(contract['workflow_pack_root'])
    output_root = Path(contract['comfyui_output_root'])
    workflow_path = workflow_root / 'ui_system_alert_frame/ui_system_alert_frame_workflow_api.json'

    positive, validated_tags = build_positive(args.prompt_shape)
    taxonomy_validation, taxonomy_meta = validate_tags(workflow_root, validated_tags)

    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    request_slug = slugify(args.asset_id)
    run_id = f'ui_system_alert_frame_{request_slug}_{timestamp}'
    filename_prefix = f'hermes_vn_ui_system_alert_frame/{run_id}'

    workflow['3']['inputs']['text'] = positive
    workflow['4']['inputs']['text'] = NEGATIVE
    workflow['5']['inputs']['width'] = WIDTH
    workflow['5']['inputs']['height'] = HEIGHT
    workflow['6']['inputs']['seed'] = args.seed
    workflow['6']['inputs']['steps'] = STEPS
    workflow['6']['inputs']['cfg'] = CFG
    workflow['8']['inputs']['filename_prefix'] = filename_prefix

    runs_root = paths['run_root']
    candidates_root = paths['candidate_root']
    run_dir = runs_root / run_id
    candidate_dir = candidates_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    patched_workflow_path = run_dir / 'ui_system_alert_frame_patched_workflow_api.json'
    patched_workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding='utf-8')

    print('RUN_ID', run_id)
    print('WORKFLOW', workflow_path)
    print('PATCHED_WORKFLOW', patched_workflow_path)
    print('PROMPT_SHAPE', args.prompt_shape)
    print('TAXONOMY_SOURCE', taxonomy_meta['taxonomy_source'])
    print('TAXONOMY_PLACEHOLDER_TAGS', ', '.join(validated_tags))
    print('POSITIVE', positive)
    print('NEGATIVE', NEGATIVE)
    print('SEED', args.seed)

    endpoint_candidates = contract.get('comfyui_endpoint_candidates') or [contract.get('comfyui_endpoint')]
    endpoint_candidates = [str(value) for value in endpoint_candidates if value]
    endpoint = discover_endpoint(endpoint_candidates)
    print('ENDPOINT', endpoint)
    prompt_id = submit_prompt(endpoint, workflow)
    print('PROMPT_ID', prompt_id)
    history = wait_history(endpoint, prompt_id)
    history_path = run_dir / 'history.json'
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')

    copied = []
    for i, out_path in enumerate(output_paths_from_history(history, output_root), 1):
        print('OUTPUT_PATH', out_path, 'exists=', out_path.exists())
        if out_path.exists():
            dst = candidate_dir / f'candidate_{i:02d}{out_path.suffix.lower() or ".png"}'
            shutil.copy2(out_path, dst)
            print('CANDIDATE_COPY', dst)
            with Image.open(dst) as im:
                copied.append({'path': str(dst), 'size': list(im.size), 'format': im.format})
    if not copied:
        raise RuntimeError('GENERATION_OUTPUT_MISSING: /history contained no copied image outputs')

    metadata = {
        'run_id': run_id,
        'workflow_id': 'ui_system_alert_frame',
        'asset_id': args.asset_id,
        'prompt_shape': args.prompt_shape,
        'prompt_id': prompt_id,
        'seed': args.seed,
        'width': WIDTH,
        'height': HEIGHT,
        'steps': STEPS,
        'cfg': CFG,
        'positive': positive,
        'negative': NEGATIVE,
        'workflow_path': str(workflow_path),
        'workflow_sha256': workflow_sha,
        'taxonomy_source': taxonomy_meta['taxonomy_source'],
        'taxonomy_validation': taxonomy_validation,
        'outputs': copied,
        'promotion_allowed': False,
        'status': 'generated_candidate_not_promoted',
    }
    metadata_path = run_dir / 'metadata.json'
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print('METADATA', metadata_path)
    print('GENERATION_OUTPUT_VERIFIED')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as e:
        print('ERROR', type(e).__name__, str(e), file=sys.stderr)
        raise
