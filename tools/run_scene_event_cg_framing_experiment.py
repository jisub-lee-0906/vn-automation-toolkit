#!/usr/bin/env python3
"""Unit 10I experimental scene_event_cg framing runner.

This is intentionally separate from the canonical runner. It allows selected
framing tags by removing only those exact tokens from the runtime negative
prompt copy. Canonical workflow files remain unchanged.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from run_scene_event_cg_smoke import (
    CFG,
    DENOISE,
    HEIGHT,
    LORA_NAME,
    LORA_STRENGTH_CLIP,
    LORA_STRENGTH_MODEL,
    README_POSITIVE,
    STEPS,
    WIDTH,
    discover_endpoint,
    image_paths_from_history,
    load_json,
    submit_prompt,
    wait_history,
)
from danbooru_taxonomy import validate_tags

PROJECT = Path('E:/workspace/renpy-project/sihanbu_villainess_badend')
CONTRACT = load_json(PROJECT / 'docs/automation/project_contract.json')
WORKFLOW_ROOT = Path(CONTRACT['workflow_pack_root'])
OUTPUT_ROOT = Path(CONTRACT['comfyui_output_root'])
WORKFLOW_PATH = WORKFLOW_ROOT / 'scene_event_cg/scene_event_cg_workflow_api.json'
CHAR_META_PATH = PROJECT / 'docs/automation/generation_runs/char_base_char_unit9a_neutral_schoolgirl_base_smoke_20260611_190248/metadata.json'
CHAR_META = load_json(CHAR_META_PATH)
SEED = 260529202

BASE_CHARACTER = ['brown_eyes', 'tareme', 'blunt_bangs', 'brown_hair', 'medium_hair', 'straight_hair']
BASE_OUTFIT = ['red_bow', 'brown_cardigan', 'white_shirt', 'blue_skirt', 'brown_pantyhose', 'school_uniform']
BASE_SCENE = ['auditorium', 'spotlight']

VARIANTS = [
    ('i1_upper_body', ['upper_body', 'looking_at_viewer']),
    ('i2_cowboy_shot', ['cowboy_shot', 'looking_at_viewer']),
    ('i3_portrait', ['portrait', 'solo_focus']),
    ('i4_close_up', ['close-up', 'solo_focus']),
    ('i5_upper_body_face', ['upper_body', 'facing_viewer', 'looking_at_viewer']),
]


def remove_negative_tokens(negative: str, allowed: list[str]) -> str:
    allowed_norm = {a.strip().lower() for a in allowed}
    parts = [p.strip() for p in negative.split(',')]
    kept = [p for p in parts if p.strip().lower() not in allowed_norm]
    return ', '.join(kept)


def main() -> int:
    endpoint = discover_endpoint(CONTRACT.get('comfyui_endpoint_candidates') or [CONTRACT['comfyui_endpoint']])
    print('ENDPOINT', endpoint)
    summary = []
    for variant_id, framing_tags in VARIANTS:
        placeholder_tags = BASE_CHARACTER + BASE_OUTFIT + BASE_SCENE + framing_tags
        validation, meta = validate_tags(WORKFLOW_ROOT, placeholder_tags)
        workflow = load_json(WORKFLOW_PATH)
        positive = README_POSITIVE.format(
            character_features=', '.join(BASE_CHARACTER),
            outfit_detail=', '.join(BASE_OUTFIT),
            scene_context=', '.join(BASE_SCENE + framing_tags),
        )
        original_negative = workflow['10']['inputs']['text']
        negative = remove_negative_tokens(original_negative, framing_tags)
        run_id = f'scene_event_cg_unit10i_{variant_id}_seed{SEED}'
        filename_prefix = f'hermes_vn_scene_event_cg_smoke/{run_id}'
        run_dir = PROJECT / 'docs/automation/generation_runs' / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        workflow['100']['inputs']['lora_name'] = LORA_NAME
        workflow['100']['inputs']['strength_model'] = LORA_STRENGTH_MODEL
        workflow['100']['inputs']['strength_clip'] = LORA_STRENGTH_CLIP
        workflow['9']['inputs']['text'] = positive
        workflow['10']['inputs']['text'] = negative
        workflow['11']['inputs']['width'] = WIDTH
        workflow['11']['inputs']['height'] = HEIGHT
        workflow['12']['inputs']['seed'] = SEED
        workflow['12']['inputs']['steps'] = STEPS
        workflow['12']['inputs']['cfg'] = CFG
        workflow['12']['inputs']['denoise'] = DENOISE
        workflow['14']['inputs']['filename_prefix'] = filename_prefix
        patched_path = run_dir / 'scene_event_cg_unit10i_patched_workflow_api.json'
        patched_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding='utf-8')
        print('===== RUN', variant_id, '=====', flush=True)
        print('RUN_ID', run_id)
        print('FRAMING_TAGS', ', '.join(framing_tags))
        print('POSITIVE', positive)
        print('NEGATIVE_REMOVED', ', '.join(framing_tags))
        prompt_id = submit_prompt(endpoint, workflow)
        print('PROMPT_ID', prompt_id)
        history = wait_history(endpoint, prompt_id)
        history_path = run_dir / 'history.json'
        history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
        output_paths = image_paths_from_history(history, OUTPUT_ROOT)
        candidate_dir = PROJECT / 'docs/automation/generated_candidates/event_cg' / run_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        for p in output_paths:
            print('OUTPUT_PATH', p, 'exists=', p.exists())
            if p.exists():
                dst = candidate_dir / f'candidate_{len(copied)+1:02d}{p.suffix.lower() or ".png"}'
                shutil.copy2(p, dst)
                copied.append(dst)
                print('CANDIDATE_COPY', dst)
        metadata = {
            'run_id': run_id,
            'unit': 'Unit 10I',
            'workflow_id': 'scene_event_cg',
            'experiment': 'face_proximity_framing_same_seed',
            'variant_id': variant_id,
            'framing_tags': framing_tags,
            'allowed_negative_tokens_removed': framing_tags,
            'source_char_base_metadata': str(CHAR_META_PATH),
            'source_char_base_run_id': CHAR_META.get('run_id'),
            'seed': SEED,
            'same_seed_as_char_base': SEED == int(CHAR_META.get('seed')),
            'positive_prompt': positive,
            'negative_prompt': negative,
            'original_negative_prompt': original_negative,
            'patched_workflow_path': str(patched_path),
            'endpoint': endpoint,
            'prompt_id': prompt_id,
            'history_path': str(history_path),
            'taxonomy_validation': validation,
            'taxonomy_source': meta['taxonomy_source'],
            'output_paths': [str(p) for p in output_paths],
            'candidate_copies': [str(p) for p in copied],
            'qa_status': 'pending_visual_review',
            'promotion_status': 'not_promoted',
            'canonical_workflow_modified': False,
        }
        metadata_path = run_dir / 'metadata.json'
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print('METADATA', metadata_path)
        if not output_paths or not all(p.exists() for p in output_paths):
            print('GENERATION_FAILED_NO_VERIFIED_OUTPUT')
            return 2
        summary.append({'variant_id': variant_id, 'run_id': run_id, 'candidate': str(copied[0]) if copied else None})
    summary_path = PROJECT / 'docs/validation/workflow_pack_unit_qa_20260610/unit10i_scene_event_cg_framing_experiment/unit10i_run_summary.json'
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SUMMARY', summary_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
