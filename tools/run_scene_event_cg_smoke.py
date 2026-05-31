#!/usr/bin/env python3
"""Run one README-guided scene_event_cg ComfyUI smoke generation.

Prompt discipline:
- Keep scene_event_cg README positive wrapper exactly.
- Fill only the two README brace placeholders with situation-appropriate CSV-verified tags.
- Do not rewrite the workflow negative prompt.
- Use the selected char_base seed for downstream consistency.
- Do not modify canonical workflow JSON; write a patched runtime copy under docs/automation/generation_runs/.
"""
from __future__ import annotations

import argparse
import csv
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs/automation/project_contract.json"
RUNS_ROOT = PROJECT_ROOT / "docs/automation/generation_runs"
DEFAULT_CHAR_BASE_METADATA = RUNS_ROOT / "char_base_smoke_20260530_063002/metadata.json"

# Exact positive shape from scene_event_cg/README.md line 36; only the brace placeholders are filled.
README_POSITIVE = (
    "masterpiece, best_quality, amazing_quality, 4k, very_aesthetic, high_resolution, "
    "ultra-detailed, absurdres, newest, 1girl, solo, {character_features}, "
    "{outfit_detail}, auditorium, indoors, spotlight, depth_of_field"
)

# Situation-appropriate placeholder values, all verified against danbooru_tag.csv.
# Placeholder 1: {캐릭터 특징(연령대, 헤어스타일, 눈매, 머리색, 눈색)}
CHARACTER_FEATURE_TAGS = [
    "mature_female",
    "medium_hair",
    "straight_hair",
    "blunt_bangs",
    "downturned_eyes",
    "brown_hair",
    "brown_eyes",
]
# Placeholder 2: {의상 디테일(의상 이름, 색상_의상종류)}
OUTFIT_DETAIL_TAGS = [
    "school_uniform",
    "white_shirt",
    "brown_cardigan",
    "blue_skirt",
    "brown_pantyhose",
]

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
    parser.add_argument("--char-base-metadata", default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    project_root = Path(args.project_root)
    contract_path = project_root / 'docs/automation/project_contract.json'
    runs_root = project_root / 'docs/automation/generation_runs'
    default_char_base_metadata = runs_root / "char_base_smoke_20260530_063002/metadata.json"
    contract = load_json(contract_path)
    workflow_root = Path(contract["workflow_pack_root"])
    output_root = Path(contract["comfyui_output_root"])
    workflow_path = workflow_root / "scene_event_cg/scene_event_cg_workflow_api.json"
    csv_path = workflow_root / "danbooru_tag.csv"
    char_meta_path = Path(args.char_base_metadata) if args.char_base_metadata else default_char_base_metadata
    char_meta = load_json(char_meta_path)

    seed = args.seed if args.seed is not None else int(char_meta.get("scene_event_cg_seed_to_reuse") or char_meta["seed"])

    placeholder_tags = CHARACTER_FEATURE_TAGS + OUTFIT_DETAIL_TAGS
    tags = collect_csv_tags(csv_path)
    missing = [t for t in placeholder_tags if t not in tags]
    if missing:
        raise RuntimeError(f"CSV tag validation failed for README placeholder tags: {missing}")

    endpoint = discover_endpoint(contract.get("comfyui_endpoint_candidates") or [contract["comfyui_endpoint"]])
    workflow = load_json(workflow_path)
    workflow_sha = hashlib.sha256(workflow_path.read_bytes()).hexdigest()

    positive = README_POSITIVE.format(
        character_features=", ".join(CHARACTER_FEATURE_TAGS),
        outfit_detail=", ".join(OUTFIT_DETAIL_TAGS),
    )
    original_negative = workflow["10"]["inputs"]["text"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"scene_event_cg_readme_positive_only_{timestamp}"
    filename_prefix = f"hermes_vn_scene_event_cg_smoke/{run_id}_school_uniform_seed{seed}"

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
    print("PROMPT_POLICY", "README positive exact; fill only brace placeholders with CSV-verified tags; leave workflow negative unchanged")
    print("CSV_PLACEHOLDER_TAGS", ", ".join(placeholder_tags))
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
        "asset_type": "scene_event_cg",
        "workflow_id": "scene_event_cg",
        "workflow_path": str(workflow_path),
        "workflow_sha256": workflow_sha,
        "patched_workflow_path": str(patched_workflow_path),
        "source_char_base_metadata": str(char_meta_path),
        "source_char_base_run_id": char_meta.get("run_id"),
        "endpoint": endpoint,
        "prompt_id": prompt_id,
        "prompt_policy": "README positive exact; fill only brace placeholders with CSV-verified tags; leave workflow negative unchanged",
        "csv_placeholder_tags": placeholder_tags,
        "character_features_placeholder": CHARACTER_FEATURE_TAGS,
        "outfit_detail_placeholder": OUTFIT_DETAIL_TAGS,
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
