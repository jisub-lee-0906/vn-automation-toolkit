#!/usr/bin/env python3
"""Run one README-guided scene_prop_cg ComfyUI smoke generation.

Prompt discipline:
- Keep positive/negative wrapper from scene_prop_cg/README.md.
- Fill only README placeholders with minimal tags verified in danbooru_tag.csv.
- Do not modify canonical workflow JSON; write a patched runtime copy under docs/automation/generation_runs/.
"""
from __future__ import annotations

import argparse
import csv
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

# Minimal placeholder tags chosen directly from scene_prop_cg/README.md and verified against danbooru_tag.csv.
ITEM_FORM_TAGS = ["key"]
MATERIAL_DETAIL_TAGS = ["scratches"]
PLACEMENT_BACKGROUND_TAGS = ["wooden_table"]
SEED = 260529102
WIDTH = 1024
HEIGHT = 576
STEPS = 30
CFG = 5.2


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9_]+', '_', value.strip().lower().replace('-', '_')).strip('_')
    return slug or 'prop'


def choose_prop_tags(asset_id: str, description: str) -> tuple[list[str], list[str], list[str]]:
    text = f'{asset_id} {description}'.lower()
    wants_neutral_note = any(word in text for word in ['neutral', 'plain', 'no heart', 'no seal', 'no wax'])
    if any(word in text for word in ['paper', 'note', 'letter']):
        if wants_neutral_note:
            # For neutral folded-note requests, keep an envelope/folded cue to
            # avoid pseudo-writing on open paper, but suppress seals/hearts via
            # the negative prompt below.
            return ['envelope', 'paper'], ['folded'], ['wooden_table']
        # Use an envelope-shaped cue for folded-note requests. Plain paper/note
        # tends to generate lined sheets with pseudo-writing, which violates the
        # VN no-readable-text prop gate.
        return ['envelope', 'paper'], ['folded'], ['wooden_table']
    return ITEM_FORM_TAGS, MATERIAL_DETAIL_TAGS, PLACEMENT_BACKGROUND_TAGS


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def collect_csv_tags(csv_path: Path) -> set[str]:
    tags: set[str] = set()
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.reader(f):
            for cell in row[:2]:
                s = cell.strip()
                if s:
                    tags.add(s)
    return tags


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
    paths = []
    for node_out in history.get("outputs", {}).values():
        if not isinstance(node_out, dict):
            continue
        for img in node_out.get("images", []):
            filename = img.get("filename")
            subfolder = img.get("subfolder", "") or ""
            typ = img.get("type", "output")
            if filename and typ == "output":
                paths.append(output_root / subfolder / filename)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', default=str(PROJECT_ROOT))
    parser.add_argument('--asset-id', default='')
    parser.add_argument('--description', default='')
    parser.add_argument('--scene-id', default='')
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    seed = args.seed
    project_root = Path(args.project_root)
    contract_path = project_root / 'docs/automation/project_contract.json'
    runs_root = project_root / 'docs/automation/generation_runs'
    item_form_tags, material_detail_tags, placement_background_tags = choose_prop_tags(args.asset_id, args.description)

    contract = load_json(contract_path)
    workflow_root = Path(contract["workflow_pack_root"])
    output_root = Path(contract["comfyui_output_root"])
    workflow_path = workflow_root / "scene_prop_cg/scene_prop_cg_workflow_api.json"
    csv_path = workflow_root / "danbooru_tag.csv"

    tags = collect_csv_tags(csv_path)
    placeholder_tags = item_form_tags + material_detail_tags + placement_background_tags
    missing = [t for t in placeholder_tags if t not in tags]
    if missing:
        raise RuntimeError(f"CSV tag validation failed for placeholder tags: {missing}")

    endpoint = discover_endpoint(contract.get("comfyui_endpoint_candidates") or [contract["comfyui_endpoint"]])
    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()

    request_text = f'{args.asset_id} {args.description}'.lower()
    positive = README_POSITIVE.format(
        item_form=", ".join(item_form_tags),
        material_detail=", ".join(material_detail_tags),
        placement_background=", ".join(placement_background_tags),
    )
    negative = README_NEGATIVE
    if any(word in request_text for word in ['single envelope', 'one envelope', 'envelope one', 'single_envelope']):
        positive += ', solo, (single closed envelope:1.45), (only one envelope:1.35), centered composition'
        negative += ', two envelopes, multiple envelopes, extra envelope, duplicate envelope, pair, twin, stack'
    if any(word in request_text for word in ['no heart', 'no seal', 'no wax', 'neutral', 'plain']):
        negative += ', heart, heart-shaped, heart_symbol, wax_seal, seal, red_seal, envelope_seal, romantic'

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
    print("ENDPOINT", endpoint)
    print("WORKFLOW", str(workflow_path))
    print("PATCHED_WORKFLOW", str(patched_workflow_path))
    print("PROMPT_POLICY", "README wrapper + minimal CSV-verified placeholder tags only")
    print("CSV_PLACEHOLDER_TAGS", ", ".join(placeholder_tags))
    print("POSITIVE", positive)
    print("NEGATIVE", negative)
    print("SEED", seed)

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
        "prompt_policy": "README wrapper + minimal CSV-verified placeholder tags only",
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
