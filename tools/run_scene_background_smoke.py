#!/usr/bin/env python3
"""Run one README-guided scene_background ComfyUI smoke generation.

Prompt discipline:
- Keep the positive/negative wrapper from scene_background/README.md.
- Fill only the README placeholders with minimal tags verified in the workflow-pack Danbooru taxonomy oracle.
- Do not modify the canonical workflow JSON; write a patched runtime copy under docs/automation/generation_runs/.
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs/automation/project_contract.json"
RUNS_ROOT = PROJECT_ROOT / "docs/automation/generation_runs"

README_POSITIVE = (
    "masterpiece, best_quality, amazing_quality, 4k, very_aesthetic, high_resolution, "
    "ultra-detailed, absurdres, newest, scenery, no_humans, wide_shot, landscape, "
    "{background_theme}, {time_mood}, BREAK, depth_of_field, volumetric_lighting"
)
README_NEGATIVE = (
    "1girl, 1boy, crowd, people, silhouette, monster, animal, modern, recent, old, oldest, "
    "cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, ugly, "
    "lowres, cropped, very_displeasing, sketch, jpeg_artifacts, signature, watermark, username, "
    "bad_ai-generated, simple_background, (worst_quality, bad_quality:1.2)"
)

PROMPT_CONTEXT_KEYS = [
    "visual_brief",
    "tag_rationale",
    "negative_rationale",
    "semantic_failure_notes",
    "reroll_or_prompt_change_reason",
]

SEED = 260529001
WIDTH = 1024
HEIGHT = 576
STEPS = 24
CFG = 5.5


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9_]+', '_', value.strip().lower().replace('-', '_')).strip('_')
    return slug or 'background'


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


def load_prompt_slots(path: Path, workflow_id: str, asset_id: str) -> tuple[list[str], list[str], list[str], dict]:
    data = load_json(path)
    if data.get('workflow_id') and data.get('workflow_id') != workflow_id:
        raise RuntimeError(f'Prompt slots workflow_id mismatch: expected {workflow_id}, got {data.get("workflow_id")}')
    if data.get('asset_id') and asset_id and data.get('asset_id') != asset_id:
        raise RuntimeError(f'Prompt slots asset_id mismatch: expected {asset_id}, got {data.get("asset_id")}')
    slots = data.get('prompt_slots') or {}
    theme = listify(slots.get('background_theme'))
    mood = listify(slots.get('time_mood'))
    negative_tags = listify(slots.get('negative_tags'))
    if not theme or not mood:
        raise RuntimeError('UNROUTED_SCENE_BACKGROUND: agent-authored prompt_slots.background_theme and prompt_slots.time_mood are required')
    return theme, mood, negative_tags, data


def prompt_context_notes(prompt_slots_data: dict) -> dict:
    """Return agent-authored prompt context notes without affecting generation.

    These fields are intentionally metadata-only. They preserve why the agent
    chose the tags, negatives, or reroll/prompt-change direction, while keeping
    the runner from inventing creative routing from descriptions.
    """
    raw_slots = prompt_slots_data.get("prompt_slots")
    slots = raw_slots if isinstance(raw_slots, dict) else {}
    notes = {}
    for key in PROMPT_CONTEXT_KEYS:
        if key in prompt_slots_data:
            notes[key] = prompt_slots_data[key]
        elif key in slots:
            notes[key] = slots[key]
    return notes


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))



def url_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")
        return r.status, json.loads(body) if body else None


def discover_endpoint(candidates: list[str]) -> str:
    errors = []
    for base in candidates:
        try:
            status, _ = url_json(base.rstrip("/") + "/system_stats", timeout=3)
            if status == 200:
                return base.rstrip("/")
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


def image_paths_from_history(history: dict, output_roots: list[Path]) -> list[Path]:
    roots = [root.resolve() for root in output_roots]
    paths = []
    for node_out in history.get("outputs", {}).values():
        for img in node_out.get("images", []) if isinstance(node_out, dict) else []:
            filename = img.get("filename")
            subfolder = img.get("subfolder", "") or ""
            typ = img.get("type", "output")
            if filename and typ == "output":
                for root in roots:
                    candidate = (root / subfolder / filename).resolve()
                    try:
                        candidate.relative_to(root)
                    except ValueError:
                        continue
                    if candidate.exists():
                        paths.append(candidate)
                        break
                else:
                    # Keep the contract-root path for diagnostics even if a live
                    # ComfyUI package wrote elsewhere; callers verify existence.
                    paths.append((roots[0] / subfolder / filename).resolve())
    return paths


def candidate_output_roots(contract: dict) -> list[Path]:
    roots = [Path(contract["comfyui_output_root"])]
    # Windows ComfyUI desktop/package installs can ignore a desired output root
    # and write under the package cwd. Keep this fallback so future sessions do
    # not lose successful history outputs just because the contract root differs.
    packaged = Path("C:/Users/Desktop/AppData/Local/Programs/ComfyUI/resources/ComfyUI/output")
    if packaged not in roots:
        roots.append(packaged)
    return roots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', default=str(PROJECT_ROOT))
    parser.add_argument('--asset-id', default='')
    parser.add_argument('--description', default='')
    parser.add_argument('--scene-id', default='')
    parser.add_argument('--seed', type=int, default=SEED, help='Sampler seed; override for rerolls while preserving prompt contract.')
    parser.add_argument('--prompt-slots', help='Agent-authored prompt slots JSON. Required for production scene_background generation.')
    parser.add_argument('--prepare-only', action='store_true', help='Patch workflow and write metadata without submitting to ComfyUI.')
    parser.add_argument('--out-metadata', help='Metadata path for prepare-only/tests. Defaults to run_dir/metadata.json.')
    args = parser.parse_args()
    project_root = Path(args.project_root)
    contract_path = project_root / 'docs/automation/project_contract.json'
    runs_root = project_root / 'docs/automation/generation_runs'
    prompt_slots_path = resolve_prompt_slots_path(project_root, Path(args.prompt_slots)) if args.prompt_slots else prompt_slots_path_for(project_root, args.asset_id, args.scene_id)
    if prompt_slots_path is None:
        raise RuntimeError('UNROUTED_SCENE_BACKGROUND: missing agent-authored prompt slots JSON under docs/production/prompt_slots')
    background_theme_tags, time_mood_tags, negative_slot_tags, prompt_slots_data = load_prompt_slots(prompt_slots_path, 'scene_background', args.asset_id)

    contract = load_json(contract_path)
    workflow_root = Path(contract["workflow_pack_root"])
    output_roots = candidate_output_roots(contract)
    workflow_path = workflow_root / "scene_background/scene_background_workflow_api.json"

    placeholder_tags = background_theme_tags + time_mood_tags
    tags_to_validate = placeholder_tags + negative_slot_tags
    taxonomy_validation, taxonomy_meta = validate_tags(workflow_root, tags_to_validate)

    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()

    positive = README_POSITIVE.format(
        background_theme=", ".join(background_theme_tags),
        time_mood=", ".join(time_mood_tags),
    )
    negative = README_NEGATIVE
    if negative_slot_tags:
        negative = negative + ', ' + ', '.join(negative_slot_tags)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    request_slug = slugify(args.asset_id or args.scene_id or 'background')
    run_id = f"scene_background_{request_slug}_{timestamp}"
    filename_prefix = f"hermes_vn_background_smoke/{run_id}_readme_csv_minimal"

    workflow["3"]["inputs"]["text"] = positive
    workflow["4"]["inputs"]["text"] = negative
    workflow["5"]["inputs"]["width"] = WIDTH
    workflow["5"]["inputs"]["height"] = HEIGHT
    workflow["6"]["inputs"]["seed"] = args.seed
    workflow["6"]["inputs"]["steps"] = STEPS
    workflow["6"]["inputs"]["cfg"] = CFG
    workflow["8"]["inputs"]["filename_prefix"] = filename_prefix

    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    patched_workflow_path = run_dir / "scene_background_patched_workflow_api.json"
    patched_workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")

    print("RUN_ID", run_id)
    print("WORKFLOW", str(workflow_path))
    print("PATCHED_WORKFLOW", str(patched_workflow_path))
    print("PROMPT_POLICY", "README wrapper + agent-authored SQLite-verified prompt slots" if taxonomy_meta['taxonomy_source'] == 'db' else "README wrapper + agent-authored legacy taxonomy-verified prompt slots")
    print("PROMPT_SLOTS", str(prompt_slots_path))
    print("TAXONOMY_SOURCE", taxonomy_meta['taxonomy_source'])
    print("TAXONOMY_PLACEHOLDER_TAGS", ", ".join(placeholder_tags))
    print("POSITIVE", positive)
    print("NEGATIVE", negative)
    print("SEED", args.seed)

    metadata = {
        "run_id": run_id,
        "asset_id": args.asset_id,
        "scene_id": args.scene_id,
        "description": args.description,
        "asset_type": "background",
        "workflow_id": "scene_background",
        "workflow_path": str(workflow_path),
        "workflow_sha256": workflow_sha,
        "patched_workflow_path": str(patched_workflow_path),
        "prompt_source": "agent_authored_prompt_slots",
        "prompt_slots_path": str(prompt_slots_path),
        "prompt_slots": prompt_slots_data,
        "prompt_context_notes": prompt_context_notes(prompt_slots_data),
        "prompt_policy": "README wrapper + agent-authored SQLite-verified prompt slots" if taxonomy_meta['taxonomy_source'] == 'db' else "README wrapper + agent-authored legacy taxonomy-verified prompt slots",
        "taxonomy_source": taxonomy_meta['taxonomy_source'],
        "taxonomy_db_path": taxonomy_meta['taxonomy_db_path'],
        "legacy_csv_path": taxonomy_meta['legacy_csv_path'],
        "legacy_csv_used": taxonomy_meta['legacy_csv_used'],
        "taxonomy_placeholder_tags": placeholder_tags,
        "taxonomy_negative_tags": negative_slot_tags,
        "taxonomy_validation": taxonomy_validation,
        "csv_placeholder_tags": placeholder_tags,
        "csv_negative_tags": negative_slot_tags,
        "positive_prompt": positive,
        "negative_prompt": negative,
        "seed": args.seed,
        "width": WIDTH,
        "height": HEIGHT,
        "steps": STEPS,
        "cfg": CFG,
        "output_paths": [],
        "candidate_copies": [],
        "qa_status": "pending_generation",
        "promotion_status": "not_promoted",
    }
    metadata_path = Path(args.out_metadata) if args.out_metadata else run_dir / "metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    if args.prepare_only:
        metadata["prepare_only"] = True
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print("METADATA", str(metadata_path))
        print("PREPARE_ONLY")
        return 0

    endpoint = discover_endpoint(contract.get("comfyui_endpoint_candidates") or [contract["comfyui_endpoint"]])
    metadata["endpoint"] = endpoint
    print("ENDPOINT", endpoint)
    prompt_id = submit_prompt(endpoint, workflow)
    print("PROMPT_ID", prompt_id)
    history = wait_history(endpoint, prompt_id)
    history_path = run_dir / "history.json"
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    output_paths = image_paths_from_history(history, output_roots)
    copied_paths = []
    candidate_dir = project_root / "docs/automation/generated_candidates/backgrounds" / run_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    for p in output_paths:
        print("OUTPUT_PATH", str(p), "exists=", p.exists())
        if p.exists():
            dst = candidate_dir / f"candidate_{len(copied_paths) + 1:02d}{p.suffix.lower() or '.png'}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            copied_paths.append(dst)
            print("CANDIDATE_COPY", str(dst))

    metadata["prompt_id"] = prompt_id
    metadata["output_paths"] = [str(p) for p in output_paths]
    metadata["candidate_copies"] = [str(p) for p in copied_paths]
    metadata["qa_status"] = "pending_visual_review"
    metadata["promotion_status"] = "not_promoted_pending_owner_approval"
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
