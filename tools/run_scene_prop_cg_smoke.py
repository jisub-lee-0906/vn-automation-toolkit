#!/usr/bin/env python3
"""Run one README-guided scene_prop_cg ComfyUI smoke generation.

Prompt discipline:
- Keep positive/negative wrapper from scene_prop_cg/README.md.
- Fill only README placeholders with minimal tags verified in the workflow-pack Danbooru taxonomy oracle.
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

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from danbooru_taxonomy import validate_tags

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs/automation/project_contract.json"
RUNS_ROOT = PROJECT_ROOT / "docs/automation/generation_runs"

README_POSITIVE = (
    "masterpiece, best_quality, amazing_quality, 4k, very_aesthetic, high_resolution, "
    "ultra-detailed, absurdres, newest, no_humans, still_life, object_focus, "
    "{item_form}, {material_detail}, {placement_background}, BREAK, depth_of_field"
)
README_NEGATIVE = (
    "1girl, 1boy, cropped, out_of_frame, duplicate, close-up, modern, recent, old, oldest, "
    "cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, "
    "ugly, lowres, bad_anatomy, sketch, jpeg_artifacts, signature, watermark, username, "
    "bad_ai-generated, (worst_quality, bad_quality:1.2), fake_text, logo, label, screenshot, "
    "dialogue_box, caption"
)

SEED = 260530101
WIDTH = 1024
HEIGHT = 576
STEPS = 30
CFG = 5.2

PROMPT_CONTEXT_KEYS = [
    "visual_brief",
    "semantic_prompt",
    "style_prompt",
    "extra_negative_prompt",
    "tag_rationale",
    "negative_rationale",
    "semantic_failure_notes",
    "reroll_or_prompt_change_reason",
]


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9_]+', '_', value.strip().lower().replace('-', '_')).strip('_')
    return slug or 'prop'


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
    item_form = listify(slots.get('item_form'))
    material = listify(slots.get('material_detail'))
    placement = listify(slots.get('placement_background'))
    if not item_form or not material or not placement:
        raise RuntimeError('UNROUTED_SCENE_PROP_CG: agent-authored prompt_slots.item_form/material_detail/placement_background are required')
    return item_form, material, placement, data


def prompt_context_notes(prompt_slots_data: dict) -> dict:
    raw_slots = prompt_slots_data.get("prompt_slots")
    slots = raw_slots if isinstance(raw_slots, dict) else {}
    notes = {}
    for key in PROMPT_CONTEXT_KEYS:
        if key in prompt_slots_data:
            notes[key] = prompt_slots_data[key]
        elif key in slots:
            notes[key] = slots[key]
    return notes


def semantic_prompt_segment(prompt_slots_data: dict) -> str:
    """Return short semantic/style guidance for the live prop prompt.

    Unit 7 owner QA showed that generic tags like `letter, envelope,
    blank_page` can produce a generic envelope when the intended prop is a red
    magical contract. Keep taxonomy validation for the object/material/placement
    tags, but allow concise semantic/style text to carry story identity.
    """
    raw_slots = prompt_slots_data.get("prompt_slots")
    slots = raw_slots if isinstance(raw_slots, dict) else {}
    parts: list[str] = []
    for key in ("semantic_prompt", "style_prompt"):
        value = slots.get(key, prompt_slots_data.get(key))
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        elif isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
    segment = ", ".join(parts).strip()
    if len(segment) > 240:
        raise RuntimeError("SCENE_PROP_CG_SEMANTIC_PROMPT_TOO_LONG: keep semantic/style prompt under 240 characters")
    return segment


def extra_negative_prompt_segment(prompt_slots_data: dict) -> str:
    raw_slots = prompt_slots_data.get("prompt_slots")
    slots = raw_slots if isinstance(raw_slots, dict) else {}
    value = slots.get("extra_negative_prompt", prompt_slots_data.get("extra_negative_prompt"))
    if isinstance(value, str):
        segment = value.strip()
    elif isinstance(value, list):
        segment = ", ".join(str(item).strip() for item in value if str(item).strip())
    else:
        segment = ""
    if len(segment) > 240:
        raise RuntimeError("SCENE_PROP_CG_EXTRA_NEGATIVE_TOO_LONG: keep extra negative prompt under 240 characters")
    return segment


def prompt_shape(prompt_slots_data: dict) -> str:
    raw_slots = prompt_slots_data.get("prompt_slots")
    slots = raw_slots if isinstance(raw_slots, dict) else {}
    value = slots.get("prompt_shape", prompt_slots_data.get("prompt_shape", "quality_first_wrapper"))
    shape = str(value).strip() if value is not None else "quality_first_wrapper"
    allowed = {"quality_first_wrapper", "object_first_compact", "screen_device_black_screen_safe"}
    if shape not in allowed:
        raise RuntimeError(f"SCENE_PROP_CG_UNSUPPORTED_PROMPT_SHAPE: {shape}")
    return shape


def build_positive_prompt(
    item_form_tags: list[str],
    material_detail_tags: list[str],
    placement_background_tags: list[str],
    prompt_slots_data: dict,
    semantic_segment: str,
) -> tuple[str, str]:
    """Build the live positive prompt.

    Default keeps the README quality-first wrapper. Verified prompt research added
    class-specific opt-ins for novaAnimeXL_ilV190:
    - object_first_compact: better for simple physical props like keys/rings/vials.
    - screen_device_black_screen_safe: verified by Unit 7M smartphone repeat and
      Unit 7L tablet candidate; allows hardware marks but suppresses UI/text/logo.
    """
    shape = prompt_shape(prompt_slots_data)
    tags = item_form_tags + material_detail_tags + placement_background_tags
    tag_segment = ", ".join(tags)
    if shape == "quality_first_wrapper":
        positive = README_POSITIVE.format(
            item_form=", ".join(item_form_tags),
            material_detail=", ".join(material_detail_tags),
            placement_background=", ".join(placement_background_tags),
        )
        if semantic_segment:
            positive = positive + ", BREAK, " + semantic_segment
        return positive, shape

    quality_tail = "depth_of_field, masterpiece, best_quality, very_aesthetic, high_resolution"
    if shape == "object_first_compact":
        head = semantic_segment or tag_segment
        positive = f"{head}, {tag_segment}, still_life, object_focus, no_humans, {quality_tail}"
        return positive, shape

    # screen_device_black_screen_safe
    head = semantic_segment or "small plain smartphone on wooden tabletop, featureless empty black glass front, display powered off, completely blank dark reflective glass surface, single smartphone only"
    positive = (
        f"{head}, {tag_segment}, still_life, object_focus, no_humans, tabletop fills background, "
        f"no logo, no icons, no app UI, no text, no corner marks, no colored marks, "
        f"no monitor, no large display, simple modern item cut-in, {quality_tail}"
    )
    return positive, shape


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
    parser.add_argument('--asset-id', default='')
    parser.add_argument('--description', default='')
    parser.add_argument('--scene-id', default='')
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument('--prompt-slots', help='Agent-authored prompt slots JSON. Required for production scene_prop_cg generation.')
    args = parser.parse_args()
    seed = args.seed
    project_root = Path(args.project_root)
    contract_path = project_root / 'docs/automation/project_contract.json'
    runs_root = project_root / 'docs/automation/generation_runs'
    prompt_slots_path = resolve_prompt_slots_path(project_root, Path(args.prompt_slots)) if args.prompt_slots else prompt_slots_path_for(project_root, args.asset_id, args.scene_id)
    if prompt_slots_path is None:
        raise RuntimeError('UNROUTED_SCENE_PROP_CG: missing agent-authored prompt slots JSON under docs/production/prompt_slots')
    item_form_tags, material_detail_tags, placement_background_tags, prompt_slots_data = load_prompt_slots(prompt_slots_path, 'scene_prop_cg', args.asset_id)

    contract = load_json(contract_path)
    workflow_root = Path(contract["workflow_pack_root"])
    output_root = Path(contract["comfyui_output_root"])
    workflow_path = workflow_root / "scene_prop_cg/scene_prop_cg_workflow_api.json"

    placeholder_tags = item_form_tags + material_detail_tags + placement_background_tags
    taxonomy_validation, taxonomy_meta = validate_tags(workflow_root, placeholder_tags)

    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()

    semantic_segment = semantic_prompt_segment(prompt_slots_data)
    positive, prompt_shape_used = build_positive_prompt(
        item_form_tags,
        material_detail_tags,
        placement_background_tags,
        prompt_slots_data,
        semantic_segment,
    )
    negative = README_NEGATIVE
    extra_negative_segment = extra_negative_prompt_segment(prompt_slots_data)
    if extra_negative_segment:
        negative = negative + ", " + extra_negative_segment

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    request_slug = slugify(args.asset_id or args.scene_id or 'prop')
    run_id = f"scene_prop_cg_{request_slug}_{timestamp}"
    filename_prefix = f"hermes_vn_prop_cg_smoke/{run_id}_readme_csv_minimal"

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
    patched_workflow_path = run_dir / "scene_prop_cg_patched_workflow_api.json"
    patched_workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")

    print("RUN_ID", run_id)
    print("WORKFLOW", str(workflow_path))
    print("PATCHED_WORKFLOW", str(patched_workflow_path))
    print("PROMPT_POLICY", "README wrapper + agent-authored SQLite-verified prompt slots" if taxonomy_meta['taxonomy_source'] == 'db' else "README wrapper + agent-authored legacy taxonomy-verified prompt slots")
    print("PROMPT_SHAPE", prompt_shape_used)
    print("PROMPT_SLOTS", str(prompt_slots_path))
    print("TAXONOMY_SOURCE", taxonomy_meta['taxonomy_source'])
    print("TAXONOMY_PLACEHOLDER_TAGS", ", ".join(placeholder_tags))
    print("POSITIVE", positive)
    print("NEGATIVE", negative)
    print("SEED", seed)

    endpoint = discover_endpoint(contract.get("comfyui_endpoint_candidates") or [contract["comfyui_endpoint"]])
    print("ENDPOINT", endpoint)
    prompt_id = submit_prompt(endpoint, workflow)
    print("PROMPT_ID", prompt_id)
    history = wait_history(endpoint, prompt_id)
    history_path = run_dir / "history.json"
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    output_paths = image_paths_from_history(history, output_root)
    copied_paths = []
    candidate_dir = project_root / "docs/automation/generated_candidates/props" / run_id
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
        "asset_type": "prop_cg",
        "workflow_id": "scene_prop_cg",
        "workflow_path": str(workflow_path),
        "workflow_sha256": workflow_sha,
        "patched_workflow_path": str(patched_workflow_path),
        "endpoint": endpoint,
        "prompt_id": prompt_id,
        "prompt_source": "agent_authored_prompt_slots",
        "prompt_slots_path": str(prompt_slots_path),
        "prompt_slots": prompt_slots_data,
        "prompt_context_notes": prompt_context_notes(prompt_slots_data),
        "semantic_prompt_segment": semantic_segment,
        "prompt_shape": prompt_shape_used,
        "extra_negative_prompt_segment": extra_negative_segment,
        "prompt_policy": "README wrapper + agent-authored SQLite-verified prompt slots" if taxonomy_meta['taxonomy_source'] == 'db' else "README wrapper + agent-authored legacy taxonomy-verified prompt slots",
        "taxonomy_source": taxonomy_meta['taxonomy_source'],
        "taxonomy_db_path": taxonomy_meta['taxonomy_db_path'],
        "legacy_csv_path": taxonomy_meta['legacy_csv_path'],
        "legacy_csv_used": taxonomy_meta['legacy_csv_used'],
        "taxonomy_placeholder_tags": placeholder_tags,
        "taxonomy_validation": taxonomy_validation,
        "csv_placeholder_tags": placeholder_tags,
        "positive_prompt": positive,
        "negative_prompt": negative,
        "seed": seed,
        "width": WIDTH,
        "height": HEIGHT,
        "steps": STEPS,
        "cfg": CFG,
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
