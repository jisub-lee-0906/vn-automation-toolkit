#!/usr/bin/env python3
"""Run one README-guided char_base ComfyUI smoke generation.

Prompt discipline:
- Keep positive/negative wrapper from char_base/README.md.
- Fill only README placeholders with minimal tags verified in the workflow-pack Danbooru taxonomy oracle.
- Do not modify canonical workflow JSON; write a patched runtime copy under docs/automation/generation_runs/.
- Record the char_base seed for future scene_event_cg reuse.
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

README_POSITIVE = (
    "masterpiece, best_quality, amazing_quality, 4k, very_aesthetic, high_resolution, "
    "ultra-detailed, absurdres, newest, 1girl, solo, cowboy_shot, "
    "standing, facing_viewer, looking_at_viewer, expressionless, closed_mouth, "
    "arms_at_sides, {body_shape_segment}{character_features}, {outfit_detail}, grey_background"
)

README_NEGATIVE = (
    "modern, recent, old, oldest, cartoon, graphic, text, painting, crayon, graphite, "
    "abstract, glitch, deformed, mutated, ugly, disfigured, long_body, lowres, "
    "bad_anatomy, bad_hands, missing_fingers, extra_digits, fewer_digits, cropped, "
    "close-up, very_displeasing, sketch, jpeg_artifacts, signature, watermark, username, "
    "conjoined, bad_ai-generated, (worst_quality, bad_quality:1.2), shadow, depth_of_field"
)

DEFAULT_SEED = 260529200
WIDTH = 1152
HEIGHT = 1536
STEPS = 28
CFG = 5.0


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9_]+', '_', value.strip().lower().replace('-', '_')).strip('_')
    return slug or 'char_base'


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


def load_prompt_slots(path: Path, workflow_id: str, asset_id: str) -> tuple[list[str], list[str], list[str], list[str], dict]:
    data = load_json(path)
    if data.get('workflow_id') and data.get('workflow_id') != workflow_id:
        raise RuntimeError(f'Prompt slots workflow_id mismatch: expected {workflow_id}, got {data.get("workflow_id")}')
    if data.get('asset_id') and asset_id and data.get('asset_id') != asset_id:
        raise RuntimeError(f'Prompt slots asset_id mismatch: expected {asset_id}, got {data.get("asset_id")}')
    slots = data.get('prompt_slots') or {}
    character_features = listify(slots.get('character_features'))
    outfit_detail = listify(slots.get('outfit_detail'))
    body_shape = listify(slots.get('body_shape'))
    negative_tags = listify(slots.get('negative_tags'))
    if not character_features or not outfit_detail:
        raise RuntimeError('UNROUTED_CHAR_BASE: agent-authored prompt_slots.character_features and prompt_slots.outfit_detail are required')
    return character_features, outfit_detail, body_shape, negative_tags, data


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))



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
    parser.add_argument('--asset-id', default='char_base')
    parser.add_argument('--scene-id', default='')
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument('--prompt-slots', help='Agent-authored char_base prompt slots JSON under docs/production/prompt_slots.')
    parser.add_argument('--prepare-only', action='store_true', help='Patch workflow and write metadata without submitting to ComfyUI.')
    parser.add_argument('--out-metadata', help='Metadata path for prepare-only/tests. Defaults to run_dir/metadata.json.')
    args = parser.parse_args()
    project_paths = build_project_paths(args.project_root, None)
    project_root = project_paths.project_root
    if args.out_metadata:
        try:
            require_under(Path(args.out_metadata).expanduser().resolve(), project_root, 'out-metadata')
        except ValueError as exc:
            print(f'CHAR_BASE_REFUSED: {exc}')
            return 2
    contract_path = project_root / 'docs/automation/project_contract.json'
    runs_root = project_root / 'docs/automation/generation_runs'
    seed = args.seed
    prompt_slots_path = resolve_prompt_slots_path(project_root, Path(args.prompt_slots)) if args.prompt_slots else prompt_slots_path_for(project_root, args.asset_id, args.scene_id)
    if prompt_slots_path is None:
        raise RuntimeError('UNROUTED_CHAR_BASE: missing agent-authored prompt slots JSON under docs/production/prompt_slots')
    character_feature_tags, outfit_detail_tags, body_shape_tags, negative_tags, prompt_slots_data = load_prompt_slots(prompt_slots_path, 'char_base', args.asset_id)

    contract = load_json(contract_path)
    workflow_root = Path(contract["workflow_pack_root"])
    output_root = Path(contract["comfyui_output_root"])
    workflow_path = workflow_root / "char_base/char_base_workflow_api.json"

    placeholder_tags = character_feature_tags + outfit_detail_tags + body_shape_tags + negative_tags
    taxonomy_validation, taxonomy_meta = validate_tags(workflow_root, placeholder_tags)

    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()

    body_shape_segment = (", ".join(body_shape_tags) + ", ") if body_shape_tags else ""
    positive = README_POSITIVE.format(
        body_shape_segment=body_shape_segment,
        character_features=", ".join(character_feature_tags),
        outfit_detail=", ".join(outfit_detail_tags),
    )
    negative = README_NEGATIVE + ((", " + ", ".join(negative_tags)) if negative_tags else "")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    asset_slug = slugify(args.asset_id)
    run_id = f"char_base_{asset_slug}_{timestamp}"
    filename_prefix = f"hermes_vn_char_base/{run_id}_seed{seed}"

    workflow["3"]["inputs"]["text"] = positive
    workflow["4"]["inputs"]["text"] = negative
    workflow["5"]["inputs"]["width"] = WIDTH
    workflow["5"]["inputs"]["height"] = HEIGHT
    workflow["6"]["inputs"]["seed"] = seed
    workflow["6"]["inputs"]["steps"] = STEPS
    workflow["6"]["inputs"]["cfg"] = CFG
    workflow["8"]["inputs"]["filename_prefix"] = filename_prefix

    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    patched_workflow_path = run_dir / "char_base_patched_workflow_api.json"
    patched_workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")

    print("RUN_ID", run_id)
    print("WORKFLOW", str(workflow_path))

    print("PROMPT_POLICY", "README wrapper + agent-authored SQLite-verified prompt slots only" if taxonomy_meta['taxonomy_source'] == 'db' else "README wrapper + agent-authored legacy taxonomy-verified prompt slots only")
    print("PROMPT_SLOTS", str(prompt_slots_path))
    print("TAXONOMY_SOURCE", taxonomy_meta['taxonomy_source'])
    print("TAXONOMY_PLACEHOLDER_TAGS", ", ".join(placeholder_tags))
    print("POSITIVE", positive)
    print("NEGATIVE", negative)
    print("SEED", seed)
    print("SCENE_EVENT_CG_SEED_TO_REUSE", seed)

    if args.prepare_only:
        metadata = {
            "run_id": run_id,
            "asset_id": args.asset_id,
            "scene_id": args.scene_id,
            "asset_type": "character_base",
            "workflow_id": "char_base",
            "workflow_path": str(workflow_path),
            "workflow_sha256": workflow_sha,
            "patched_workflow_path": str(patched_workflow_path),
            "endpoint": None,
            "prompt_policy": "README wrapper + agent-authored SQLite-verified prompt slots only" if taxonomy_meta['taxonomy_source'] == 'db' else "README wrapper + agent-authored legacy taxonomy-verified prompt slots only",
            "prompt_source": "agent_authored_prompt_slots",
            "prompt_slots_path": str(prompt_slots_path),
            "prompt_slots": prompt_slots_data.get('prompt_slots', {}),
            "taxonomy_source": taxonomy_meta['taxonomy_source'],
            "taxonomy_db_path": taxonomy_meta['taxonomy_db_path'],
            "legacy_csv_path": taxonomy_meta['legacy_csv_path'],
            "legacy_csv_used": taxonomy_meta['legacy_csv_used'],
            "taxonomy_placeholder_tags": placeholder_tags,
            "taxonomy_validation": taxonomy_validation,
            "csv_placeholder_tags": placeholder_tags,
            "character_features": character_feature_tags,
            "body_shape": body_shape_tags,
            "outfit_detail": outfit_detail_tags,
            "negative_tags": negative_tags,
            "positive_prompt": positive,
            "negative_prompt": negative,
            "seed": seed,
            "scene_event_cg_seed_to_reuse": seed,
            "width": WIDTH,
            "height": HEIGHT,
            "steps": STEPS,
            "cfg": CFG,
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
    candidate_dir = project_root / "docs/automation/generated_candidates/characters" / run_id
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
        "asset_type": "character_base",
        "workflow_id": "char_base",
        "workflow_path": str(workflow_path),
        "workflow_sha256": workflow_sha,
        "patched_workflow_path": str(patched_workflow_path),
        "endpoint": endpoint,
        "prompt_id": prompt_id,
        "prompt_policy": "README wrapper + agent-authored SQLite-verified prompt slots only" if taxonomy_meta['taxonomy_source'] == 'db' else "README wrapper + agent-authored legacy taxonomy-verified prompt slots only",
        "prompt_source": "agent_authored_prompt_slots",
        "prompt_slots_path": str(prompt_slots_path),
        "prompt_slots": prompt_slots_data.get('prompt_slots', {}),
        "taxonomy_source": taxonomy_meta['taxonomy_source'],
        "taxonomy_db_path": taxonomy_meta['taxonomy_db_path'],
        "legacy_csv_path": taxonomy_meta['legacy_csv_path'],
        "legacy_csv_used": taxonomy_meta['legacy_csv_used'],
        "taxonomy_placeholder_tags": placeholder_tags,
        "taxonomy_validation": taxonomy_validation,
        "csv_placeholder_tags": placeholder_tags,
        "character_features": character_feature_tags,
        "body_shape": body_shape_tags,
        "outfit_detail": outfit_detail_tags,
        "negative_tags": negative_tags,
        "positive_prompt": positive,
        "negative_prompt": negative,
        "seed": seed,
        "scene_event_cg_seed_to_reuse": seed,
        "width": WIDTH,
        "height": HEIGHT,
        "steps": STEPS,
        "cfg": CFG,
        "output_paths": [str(p) for p in output_paths],
        "candidate_copies": [str(p) for p in copied_paths],
        "qa_status": "pending_visual_review",
        "promotion_status": "not_promoted",
    }
    metadata_path = Path(args.out_metadata) if args.out_metadata else run_dir / "metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
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
