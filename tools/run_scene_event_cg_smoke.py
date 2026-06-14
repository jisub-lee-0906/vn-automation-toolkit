#!/usr/bin/env python3
"""Run one README-guided scene_event_cg ComfyUI smoke generation.

Prompt discipline:
- Keep scene_event_cg README positive wrapper exactly.
- Fill only the two README brace placeholders with situation-appropriate taxonomy-verified tags.
- Do not modify canonical workflow JSON; route modes may patch the runtime negative copy only.
- Use the selected char_base seed for downstream consistency.
- Do not modify canonical workflow JSON; write a patched runtime copy under docs/automation/generation_runs/.
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

from danbooru_taxonomy import validate_tags
from vn_product_config import build_project_paths, require_under

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs/automation/project_contract.json"
RUNS_ROOT = PROJECT_ROOT / "docs/automation/generation_runs"


def slugify(value: str) -> str:
    slug = ''.join(ch.lower() if ch.isalnum() else '_' for ch in value).strip('_')
    while '__' in slug:
        slug = slug.replace('__', '_')
    return slug or 'event_cg'


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


def listify(value) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(',') if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def normalize_prompt_token(value: str) -> str:
    token = str(value or '').strip().lower().replace('-', '_').replace(' ', '_')
    return re.sub(r'_+', '_', token).strip('_')


def negative_prompt_tokens(negative_prompt: str) -> set[str]:
    tokens = set()
    for raw in str(negative_prompt or '').split(','):
        token = normalize_prompt_token(raw)
        token = token.strip('()')
        if ':' in token:
            token = token.split(':', 1)[0]
        if token:
            tokens.add(token)
    return tokens


def assert_no_positive_negative_conflicts(placeholder_tags: list[str], negative_prompt: str) -> None:
    negative = negative_prompt_tokens(negative_prompt)
    conflicts = [tag for tag in placeholder_tags if normalize_prompt_token(tag) in negative]
    if conflicts:
        raise RuntimeError(
            'SCENE_EVENT_CG_PROMPT_CONFLICT: positive placeholder tags also appear in canonical negative prompt: '
            + ', '.join(conflicts)
        )


def assert_no_prompt_text_conflicts(positive_prompt: str, negative_prompt: str, *, context: str = 'prompt') -> None:
    positive = negative_prompt_tokens(positive_prompt)
    negative = negative_prompt_tokens(negative_prompt)
    conflicts = sorted(positive & negative)
    if conflicts:
        raise RuntimeError(
            f'SCENE_EVENT_CG_PROMPT_CONFLICT ({context}): positive prompt tokens also appear in negative prompt: '
            + ', '.join(conflicts)
        )


SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS = {
    'conservative': set(),
    'production_character': {'upper_body', 'looking_at_viewer'},
    'production_character_front': {'upper_body', 'looking_at_viewer', 'facing_viewer'},
    'production_character_cowboy': {'cowboy_shot', 'looking_at_viewer'},
    'cut_in': {'portrait', 'close-up', 'headshot', 'solo_focus'},
}


def remove_negative_prompt_tokens(negative_prompt: str, tokens_to_remove: set[str]) -> str:
    normalized = {normalize_prompt_token(token) for token in tokens_to_remove}
    kept = []
    for raw in str(negative_prompt or '').split(','):
        token = normalize_prompt_token(raw).strip('()')
        if ':' in token:
            token = token.split(':', 1)[0]
        if token and token in normalized:
            continue
        if raw.strip():
            kept.append(raw.strip())
    return ', '.join(kept)


def apply_scene_event_route_policy(scene_context_tags: list[str], negative_prompt: str, *, route_mode: str = 'conservative') -> str:
    if route_mode not in SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS:
        raise RuntimeError(
            'SCENE_EVENT_CG_UNKNOWN_ROUTE_MODE: '
            + route_mode
            + '; expected one of '
            + ', '.join(sorted(SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS))
        )
    allowed = {normalize_prompt_token(tag) for tag in SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS[route_mode]}
    requested = {normalize_prompt_token(tag) for tag in scene_context_tags}
    removable = allowed & requested
    return remove_negative_prompt_tokens(negative_prompt, removable)


def resolve_scene_event_route_mode(cli_route_mode: str | None, prompt_slots_data: dict) -> str:
    route_mode = cli_route_mode or prompt_slots_data.get('scene_event_route_mode') or 'conservative'
    if route_mode not in SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS:
        raise RuntimeError(
            'SCENE_EVENT_CG_UNKNOWN_ROUTE_MODE: '
            + str(route_mode)
            + '; expected one of '
            + ', '.join(sorted(SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS))
        )
    return route_mode


# Exact quality/subject wrapper from scene_event_cg/README.md, with creative scene context supplied by agent-authored slots.
README_POSITIVE = (
    "masterpiece, best_quality, amazing_quality, 4k, very_aesthetic, high_resolution, "
    "ultra-detailed, absurdres, newest, 1girl, solo, {character_features}, "
    "{outfit_detail}, {scene_context}, depth_of_field"
)

WIDTH = 1024
HEIGHT = 576
STEPS = 30
CFG = 5.2
DENOISE = 1.0
LORA_NAME = "hinaMaybeBetterPoseXL_v5-NoobAI.safetensors"
LORA_STRENGTH_MODEL = 0.65
LORA_STRENGTH_CLIP = 0.65


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_prompt_slots_executable(prompt_slots_data: dict, *, allow_review_gated_execution: bool = False) -> None:
    reasons = []
    if prompt_slots_data.get('executable') is False:
        reasons.append('executable=false')
    reference_conditioning = prompt_slots_data.get('reference_conditioning') or {}
    if isinstance(reference_conditioning, dict):
        reference_conditioning_status = str(reference_conditioning.get('status') or '').strip().lower()
        if reference_conditioning_status in {'preflight_required_not_executable_by_default'}:
            reasons.append('reference_conditioning.status=' + reference_conditioning_status)
        if reference_conditioning.get('approval_required') is True:
            reasons.append('reference_conditioning.approval_required')
        if reference_conditioning.get('preflight_required_not_executable_by_default') is True:
            reasons.append('reference_conditioning.preflight_required_not_executable_by_default')

    if reasons and not allow_review_gated_execution:
        raise RuntimeError(
            'SCENE_EVENT_CG_REVIEW_GATED_NOT_EXECUTABLE: '
            + str(prompt_slots_data.get('asset_id') or 'unknown_asset')
            + '; review_gate='
            + str(prompt_slots_data.get('review_gate') or 'unspecified')
            + '; reasons='
            + ','.join(reasons)
            + '; pass --allow-review-gated-execution only after explicit owner approval and validated reference workflow/preflight'
        )


def load_prompt_slots(path: Path, workflow_id: str, asset_id: str) -> tuple[list[str], list[str], list[str], dict]:
    data = load_json(path)
    if data.get('workflow_id') and data.get('workflow_id') != workflow_id:
        raise RuntimeError(f'Prompt slots workflow_id mismatch: expected {workflow_id}, got {data.get("workflow_id")}')
    if data.get('asset_id') and asset_id and data.get('asset_id') != asset_id:
        raise RuntimeError(f'Prompt slots asset_id mismatch: expected {asset_id}, got {data.get("asset_id")}')
    slots = data.get('prompt_slots') or {}
    character_features = listify(slots.get('character_features'))
    outfit_detail = listify(slots.get('outfit_detail'))
    scene_context = listify(slots.get('scene_context'))
    if not character_features or not outfit_detail or not scene_context:
        raise RuntimeError('UNROUTED_SCENE_EVENT_CG: agent-authored prompt_slots.character_features, prompt_slots.outfit_detail, and prompt_slots.scene_context are required')
    return character_features, outfit_detail, scene_context, data


def url_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")
        return r.status, json.loads(body) if body else None


def discover_endpoint(candidates: list[str]) -> str:
    errors = []
    for base in candidates:
        base = base.rstrip("/")
        try:
            status, _ = url_json(base + "/system_stats", timeout=3)
            if status == 200:
                return base
            errors.append(f"{base}: status {status}")
        except Exception as e:
            errors.append(f"{base}: {type(e).__name__} {e}")
    raise RuntimeError("No live ComfyUI endpoint found: " + "; ".join(errors))


def submit_prompt(endpoint: str, workflow: dict) -> str:
    payload = json.dumps({"prompt": workflow, "client_id": str(uuid.uuid4())}).encode("utf-8")
    req = urllib.request.Request(
        endpoint + "/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            print("prompt_submit_status", r.status)
            print("prompt_submit_response", body)
            return data["prompt_id"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"/prompt HTTP {e.code}: {body}") from e


def wait_history(endpoint: str, prompt_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    last_queue_print = 0.0
    while time.time() < deadline:
        try:
            status, hist = url_json(endpoint + "/history/" + prompt_id, timeout=10)
            if status == 200 and isinstance(hist, dict) and prompt_id in hist:
                return hist[prompt_id]
        except Exception:
            pass
        if time.time() - last_queue_print > 20:
            try:
                _, q = url_json(endpoint + "/queue", timeout=5)
                print("queue_snapshot", json.dumps(q, ensure_ascii=False)[:500])
            except Exception as e:
                print("queue_snapshot_error", type(e).__name__, e)
            last_queue_print = time.time()
        time.sleep(5)
    raise TimeoutError(f"history did not complete within {timeout_s}s for {prompt_id}")


def image_paths_from_history(history: dict, output_root: Path) -> list[Path]:
    root = output_root.resolve()
    paths = []
    for node_out in history.get("outputs", {}).values():
        if not isinstance(node_out, dict):
            continue
        for img in node_out.get("images", []):
            filename = img.get("filename")
            subfolder = img.get("subfolder", "") or ""
            typ = img.get("type", "output")
            if filename and typ == "output":
                candidate = (root / subfolder / filename).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError:
                    continue
                paths.append(candidate)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', default=str(PROJECT_ROOT))
    parser.add_argument('--asset-id', default='')
    parser.add_argument('--description', default='')
    parser.add_argument('--scene-id', default='')
    parser.add_argument('--prompt-slots', help='Agent-authored prompt slots JSON. Required for production scene_event_cg generation.')
    parser.add_argument("--char-base-metadata", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument('--prepare-only', action='store_true', help='Patch workflow and write metadata without submitting to ComfyUI.')
    parser.add_argument('--allow-review-gated-execution', action='store_true', help='Allow prompt slots with executable=false. Use only after explicit owner approval and validated reference/preflight workflow.')
    parser.add_argument(
        '--route-mode',
        choices=sorted(SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS),
        default=None,
        help='scene_event_cg route policy. Defaults to prompt_slots.scene_event_route_mode, then conservative.',
    )
    parser.add_argument('--out-metadata', help='Metadata path for prepare-only/tests. Defaults to run_dir/metadata.json.')
    args = parser.parse_args()

    project_paths = build_project_paths(args.project_root, None)
    project_root = project_paths.project_root
    if args.out_metadata:
        try:
            require_under(Path(args.out_metadata).expanduser().resolve(), project_root, 'out-metadata')
        except ValueError as exc:
            print(f'SCENE_EVENT_CG_REFUSED: {exc}')
            return 2
    if args.char_base_metadata:
        try:
            require_under(Path(args.char_base_metadata).expanduser().resolve(), project_root, 'char-base-metadata')
        except ValueError as exc:
            print(f'SCENE_EVENT_CG_REFUSED: {exc}')
            return 2
    contract_path = project_root / 'docs/automation/project_contract.json'
    runs_root = project_root / 'docs/automation/generation_runs'
    prompt_slots_path = resolve_prompt_slots_path(project_root, Path(args.prompt_slots)) if args.prompt_slots else prompt_slots_path_for(project_root, args.asset_id, args.scene_id)
    if prompt_slots_path is None:
        raise RuntimeError('UNROUTED_SCENE_EVENT_CG: missing agent-authored prompt slots JSON under docs/production/prompt_slots')
    character_feature_tags, outfit_detail_tags, scene_context_tags, prompt_slots_data = load_prompt_slots(prompt_slots_path, 'scene_event_cg', args.asset_id)
    assert_prompt_slots_executable(prompt_slots_data, allow_review_gated_execution=args.allow_review_gated_execution)
    route_mode = resolve_scene_event_route_mode(args.route_mode, prompt_slots_data)
    contract = load_json(contract_path)

    workflow_root = Path(contract["workflow_pack_root"])
    output_root = Path(contract["comfyui_output_root"])
    workflow_path = workflow_root / "scene_event_cg/scene_event_cg_workflow_api.json"
    if not args.char_base_metadata:
        raise RuntimeError('SCENE_EVENT_CG_SOURCE_REQUIRED: pass --char-base-metadata for the approved/current source character base metadata; stale hardcoded run fallbacks are forbidden')
    char_meta_path = Path(args.char_base_metadata).expanduser().resolve()
    char_meta = load_json(char_meta_path)

    seed = args.seed if args.seed is not None else int(char_meta.get("scene_event_cg_seed_to_reuse") or char_meta["seed"])

    placeholder_tags = character_feature_tags + outfit_detail_tags + scene_context_tags
    taxonomy_validation, taxonomy_meta = validate_tags(workflow_root, placeholder_tags)

    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()

    positive = README_POSITIVE.format(
        character_features=", ".join(character_feature_tags),
        outfit_detail=", ".join(outfit_detail_tags),
        scene_context=", ".join(scene_context_tags),
    )
    original_negative = workflow["10"]["inputs"]["text"]
    negative = apply_scene_event_route_policy(scene_context_tags, original_negative, route_mode=route_mode)
    assert_no_positive_negative_conflicts(placeholder_tags, negative)
    assert_no_prompt_text_conflicts(positive, negative, context=f'scene_event_cg:{route_mode}')

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"scene_event_cg_{slugify(args.asset_id or args.scene_id or 'readme_positive_only')}_{timestamp}"
    filename_prefix = f"hermes_vn_scene_event_cg_smoke/{run_id}_seed{seed}"

    workflow["100"]["inputs"]["lora_name"] = LORA_NAME
    workflow["100"]["inputs"]["strength_model"] = LORA_STRENGTH_MODEL
    workflow["100"]["inputs"]["strength_clip"] = LORA_STRENGTH_CLIP
    workflow["9"]["inputs"]["text"] = positive
    workflow["10"]["inputs"]["text"] = negative
    workflow["11"]["inputs"]["width"] = WIDTH
    workflow["11"]["inputs"]["height"] = HEIGHT
    workflow["12"]["inputs"]["seed"] = seed
    workflow["12"]["inputs"]["steps"] = STEPS
    workflow["12"]["inputs"]["cfg"] = CFG
    workflow["12"]["inputs"]["denoise"] = DENOISE
    workflow["14"]["inputs"]["filename_prefix"] = filename_prefix

    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    patched_workflow_path = run_dir / "scene_event_cg_patched_workflow_api.json"
    patched_workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")

    print("RUN_ID", run_id)
    print("WORKFLOW", str(workflow_path))
    print("CHAR_BASE_METADATA", str(char_meta_path))
    print("PATCHED_WORKFLOW", str(patched_workflow_path))
    print("PROMPT_POLICY", "README positive exact; fill placeholders with agent-authored SQLite-verified prompt slots; apply route-mode negative policy to runtime copy" if taxonomy_meta['taxonomy_source'] == 'db' else "README positive exact; fill placeholders with agent-authored legacy taxonomy-verified prompt slots; apply route-mode negative policy to runtime copy")
    print("PROMPT_SLOTS", str(prompt_slots_path))
    print("TAXONOMY_SOURCE", taxonomy_meta['taxonomy_source'])
    print("TAXONOMY_PLACEHOLDER_TAGS", ", ".join(placeholder_tags))
    print("POSITIVE", positive)
    print("ROUTE_MODE", route_mode)
    print("NEGATIVE_ORIGINAL", original_negative)
    print("NEGATIVE_EFFECTIVE", negative)
    print("SEED", seed)

    if args.prepare_only:
        metadata = {
            "run_id": run_id,
            "asset_id": args.asset_id,
            "scene_id": args.scene_id,
            "description": args.description,
            "asset_type": "scene_event_cg",
            "workflow_id": "scene_event_cg",
            "workflow_path": str(workflow_path),
            "workflow_sha256": workflow_sha,
            "patched_workflow_path": str(patched_workflow_path),
            "source_char_base_metadata": str(char_meta_path),
            "source_char_base_run_id": char_meta.get("run_id"),
            "endpoint": None,
            "prompt_id": None,
            "prompt_source": "agent_authored_prompt_slots",
            "prompt_slots_path": str(prompt_slots_path),
            "prompt_slots": prompt_slots_data,
            "prompt_policy": "README positive exact; fill placeholders with agent-authored SQLite-verified prompt slots; apply route-mode negative policy to runtime copy" if taxonomy_meta['taxonomy_source'] == 'db' else "README positive exact; fill placeholders with agent-authored legacy taxonomy-verified prompt slots; apply route-mode negative policy to runtime copy",
            "taxonomy_source": taxonomy_meta['taxonomy_source'],
            "taxonomy_db_path": taxonomy_meta['taxonomy_db_path'],
            "legacy_csv_path": taxonomy_meta['legacy_csv_path'],
            "legacy_csv_used": taxonomy_meta['legacy_csv_used'],
            "taxonomy_placeholder_tags": placeholder_tags,
            "taxonomy_validation": taxonomy_validation,
            "csv_placeholder_tags": placeholder_tags,
            "character_features_placeholder": character_feature_tags,
            "outfit_detail_placeholder": outfit_detail_tags,
            "scene_context_placeholder": scene_context_tags,
            "positive_prompt": positive,
            "negative_prompt": negative,
            "original_negative_prompt": original_negative,
            "negative_prompt_policy": "route_policy_runtime_copy",
            "route_mode": route_mode,
            "route_allowed_negative_removals": sorted(SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS[route_mode]),
            "seed": seed,
            "same_seed_as_char_base": seed == int(char_meta.get("seed")),
            "width": WIDTH,
            "height": HEIGHT,
            "steps": STEPS,
            "cfg": CFG,
            "denoise": DENOISE,
            "lora_name": LORA_NAME,
            "lora_strength_model": LORA_STRENGTH_MODEL,
            "lora_strength_clip": LORA_STRENGTH_CLIP,
            "output_paths": [],
            "candidate_copies": [],
            "qa_status": "prepare_only",
            "promotion_status": "not_promoted",
            "prepare_only": True,
        }
        metadata_path = Path(args.out_metadata) if args.out_metadata else run_dir / "metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print("METADATA", str(metadata_path))
        print("PREPARE_ONLY")
        return 0

    endpoint = discover_endpoint(contract.get("comfyui_endpoint_candidates") or [contract["comfyui_endpoint"]])
    print("ENDPOINT", endpoint)
    prompt_id = submit_prompt(endpoint, workflow)
    print("PROMPT_ID", prompt_id)
    history = wait_history(endpoint, prompt_id)
    history_path = run_dir / "history.json"
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    output_paths = image_paths_from_history(history, output_root)
    copied_paths = []
    candidate_dir = project_root / "docs/automation/generated_candidates/event_cg" / run_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    for p in output_paths:
        print("OUTPUT_PATH", str(p), "exists=", p.exists())
        if p.exists():
            dst = candidate_dir / f"candidate_{len(copied_paths) + 1:02d}{p.suffix.lower() or '.png'}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            copied_paths.append(dst)
            print("CANDIDATE_COPY", str(dst))

    metadata = {
        "run_id": run_id,
        "asset_id": args.asset_id,
        "scene_id": args.scene_id,
        "description": args.description,
        "asset_type": "scene_event_cg",
        "workflow_id": "scene_event_cg",
        "workflow_path": str(workflow_path),
        "workflow_sha256": workflow_sha,
        "patched_workflow_path": str(patched_workflow_path),
        "source_char_base_metadata": str(char_meta_path),
        "source_char_base_run_id": char_meta.get("run_id"),
        "endpoint": endpoint,
        "prompt_id": prompt_id,
        "prompt_source": "agent_authored_prompt_slots",
        "prompt_slots_path": str(prompt_slots_path),
        "prompt_slots": prompt_slots_data,
        "prompt_policy": "README positive exact; fill placeholders with agent-authored SQLite-verified prompt slots; apply route-mode negative policy to runtime copy" if taxonomy_meta['taxonomy_source'] == 'db' else "README positive exact; fill placeholders with agent-authored legacy taxonomy-verified prompt slots; apply route-mode negative policy to runtime copy",
        "taxonomy_source": taxonomy_meta['taxonomy_source'],
        "taxonomy_db_path": taxonomy_meta['taxonomy_db_path'],
        "legacy_csv_path": taxonomy_meta['legacy_csv_path'],
        "legacy_csv_used": taxonomy_meta['legacy_csv_used'],
        "taxonomy_placeholder_tags": placeholder_tags,
        "taxonomy_validation": taxonomy_validation,
        "csv_placeholder_tags": placeholder_tags,
        "character_features_placeholder": character_feature_tags,
        "outfit_detail_placeholder": outfit_detail_tags,
        "scene_context_placeholder": scene_context_tags,
        "positive_prompt": positive,
        "negative_prompt": negative,
        "original_negative_prompt": original_negative,
        "negative_prompt_policy": "route_policy_runtime_copy",
        "route_mode": route_mode,
        "route_allowed_negative_removals": sorted(SCENE_EVENT_ROUTE_ALLOWED_NEGATIVE_REMOVALS[route_mode]),
        "seed": seed,
        "same_seed_as_char_base": seed == int(char_meta.get("seed")),
        "width": WIDTH,
        "height": HEIGHT,
        "steps": STEPS,
        "cfg": CFG,
        "denoise": DENOISE,
        "lora_name": LORA_NAME,
        "lora_strength_model": LORA_STRENGTH_MODEL,
        "lora_strength_clip": LORA_STRENGTH_CLIP,
        "output_paths": [str(p) for p in output_paths],
        "candidate_copies": [str(p) for p in copied_paths],
        "qa_status": "pending_visual_review",
        "promotion_status": "not_promoted",
    }
    metadata_path = run_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("METADATA", str(metadata_path))

    if not output_paths or not all(p.exists() for p in output_paths):
        print("GENERATION_FAILED_NO_VERIFIED_OUTPUT")
        return 2
    print("GENERATION_OUTPUT_VERIFIED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("ERROR", type(e).__name__, e, file=sys.stderr)
        raise
