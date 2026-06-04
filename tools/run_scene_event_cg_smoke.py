#!/usr/bin/env python3
"""Run one README-guided scene_event_cg ComfyUI smoke generation.

Prompt discipline:
- Keep scene_event_cg README positive wrapper exactly.
- Fill only the two README brace placeholders with situation-appropriate taxonomy-verified tags.
- Do not rewrite the workflow negative prompt.
- Use the selected char_base seed for downstream consistency.
- Do not modify canonical workflow JSON; write a patched runtime copy under docs/automation/generation_runs/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from danbooru_taxonomy import validate_tags

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
    args = parser.parse_args()

    project_root = Path(args.project_root)
    contract_path = project_root / 'docs/automation/project_contract.json'
    runs_root = project_root / 'docs/automation/generation_runs'
    prompt_slots_path = resolve_prompt_slots_path(project_root, Path(args.prompt_slots)) if args.prompt_slots else prompt_slots_path_for(project_root, args.asset_id, args.scene_id)
    if prompt_slots_path is None:
        raise RuntimeError('UNROUTED_SCENE_EVENT_CG: missing agent-authored prompt slots JSON under docs/production/prompt_slots')
    character_feature_tags, outfit_detail_tags, scene_context_tags, prompt_slots_data = load_prompt_slots(prompt_slots_path, 'scene_event_cg', args.asset_id)
    contract = load_json(contract_path)
    workflow_root = Path(contract["workflow_pack_root"])
    output_root = Path(contract["comfyui_output_root"])
    workflow_path = workflow_root / "scene_event_cg/scene_event_cg_workflow_api.json"
    if not args.char_base_metadata:
        raise RuntimeError('SCENE_EVENT_CG_SOURCE_REQUIRED: pass --char-base-metadata for the approved/current source character base metadata; stale hardcoded run fallbacks are forbidden')
    char_meta_path = Path(args.char_base_metadata)
    char_meta = load_json(char_meta_path)

    seed = args.seed if args.seed is not None else int(char_meta.get("scene_event_cg_seed_to_reuse") or char_meta["seed"])

    placeholder_tags = character_feature_tags + outfit_detail_tags + scene_context_tags
    taxonomy_validation, taxonomy_meta = validate_tags(workflow_root, placeholder_tags)

    endpoint = discover_endpoint(contract.get("comfyui_endpoint_candidates") or [contract["comfyui_endpoint"]])
    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()

    positive = README_POSITIVE.format(
        character_features=", ".join(character_feature_tags),
        outfit_detail=", ".join(outfit_detail_tags),
        scene_context=", ".join(scene_context_tags),
    )
    original_negative = workflow["10"]["inputs"]["text"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"scene_event_cg_{slugify(args.asset_id or args.scene_id or 'readme_positive_only')}_{timestamp}"
    filename_prefix = f"hermes_vn_scene_event_cg_smoke/{run_id}_seed{seed}"

    workflow["100"]["inputs"]["lora_name"] = LORA_NAME
    workflow["100"]["inputs"]["strength_model"] = LORA_STRENGTH_MODEL
    workflow["100"]["inputs"]["strength_clip"] = LORA_STRENGTH_CLIP
    workflow["9"]["inputs"]["text"] = positive
    # Intentionally do not patch workflow["10"] negative prompt.
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
    print("ENDPOINT", endpoint)
    print("WORKFLOW", str(workflow_path))
    print("CHAR_BASE_METADATA", str(char_meta_path))
    print("PATCHED_WORKFLOW", str(patched_workflow_path))
    print("PROMPT_POLICY", "README positive exact; fill only brace placeholders with agent-authored SQLite-verified prompt slots; leave workflow negative unchanged" if taxonomy_meta['taxonomy_source'] == 'db' else "README positive exact; fill only brace placeholders with agent-authored legacy taxonomy-verified prompt slots; leave workflow negative unchanged")
    print("PROMPT_SLOTS", str(prompt_slots_path))
    print("TAXONOMY_SOURCE", taxonomy_meta['taxonomy_source'])
    print("TAXONOMY_PLACEHOLDER_TAGS", ", ".join(placeholder_tags))
    print("POSITIVE", positive)
    print("NEGATIVE_UNCHANGED", original_negative)
    print("SEED", seed)

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
        "prompt_policy": "README positive exact; fill only brace placeholders with agent-authored SQLite-verified prompt slots; leave workflow negative unchanged" if taxonomy_meta['taxonomy_source'] == 'db' else "README positive exact; fill only brace placeholders with agent-authored legacy taxonomy-verified prompt slots; leave workflow negative unchanged",
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
        "negative_prompt": original_negative,
        "negative_prompt_policy": "unchanged_from_canonical_workflow",
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
