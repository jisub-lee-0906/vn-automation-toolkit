#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import add_project_args, build_project_paths, load_json, resolve_project_path, require_under, save_json

WORKFLOW_BY_TYPE = {
    'background': 'scene_background',
    'bgm': 'audio_bgm_with_sfx',
    'sfx': 'audio_bgm_with_sfx',
    'prop_cg': 'scene_prop_cg',
    'event_cg': 'scene_event_cg',
    'char_expression': 'char_expression',
}

SOURCE_METADATA_REQUIRED = {'event_cg', 'char_expression'}


def slugify(value: object) -> str:
    slug = re.sub(r'[^a-z0-9_]+', '_', str(value or '').strip().lower().replace('-', '_')).strip('_')
    return slug or 'asset'


def prompt_slot_path(project_root: Path, scene_id: str, asset_id: str) -> Path:
    return project_root / 'docs/production/prompt_slots' / f'{slugify(scene_id)}__{slugify(asset_id)}.json'


def prompt_slots_for(asset_type: str, asset_id: str, scene_id: str, role: str, variant_index: int) -> dict[str, Any]:
    visual_brief = f'{scene_id}: {role}; candidate variant {variant_index}; generated from story enrichment plan.'
    if asset_type == 'background':
        variants = [
            (['scenery', 'no_humans', 'indoors', 'bookshelf', 'window'], ['night', 'candle']),
            (['scenery', 'no_humans', 'hallway', 'window', 'indoors'], ['night']),
            (['scenery', 'no_humans', 'indoors', 'table', 'candle'], ['night']),
        ]
        theme, mood = variants[(variant_index - 1) % len(variants)]
        return {
            'asset_id': asset_id,
            'scene_id': scene_id,
            'workflow_id': 'scene_background',
            'prompt_slots': {
                'background_theme': theme,
                'time_mood': mood,
                'negative_tags': ['1girl', '1boy', 'text_focus', 'watermark', 'dialogue_box', 'caption', 'subtitled', 'speech_bubble', 'comic'],
                'semantic_prompt': f'gothic mansion library background, {role}, empty room, no UI, no subtitles',
                'style_prompt': 'portrait crop, empty lower floor',
            },
            'visual_brief': visual_brief,
            'tag_rationale': 'Use only SQLite-validated broad Danbooru tags; semantic_prompt carries scene-specific mansion/investigation intent.',
        }
    if asset_type == 'prop_cg':
        return {
            'asset_id': asset_id,
            'scene_id': scene_id,
            'workflow_id': 'scene_prop_cg',
            'prompt_slots': {
                'item_form': ['paper', 'letter'],
                'material_detail': ['paper'],
                'placement_background': ['table', 'candle'],
                'negative_tags': ['1girl', '1boy', 'text', 'watermark', 'duplicate'],
                'semantic_prompt': f'single clue document prop cut-in for VN, {role}, no readable fake text',
                'style_prompt': 'still life object focus, gothic investigation mood',
                'extra_negative_prompt': 'readable letters, fake text, logo, signature, duplicate papers',
            },
            'visual_brief': visual_brief,
            'tag_rationale': 'Use paper/letter/table/candle because document-like specific tag was missing in local taxonomy.',
        }
    if asset_type == 'bgm':
        return {
            'asset_id': asset_id,
            'scene_id': scene_id,
            'workflow_id': 'audio_bgm_with_sfx',
            'audio_role': 'audio_bgm',
            'prompt_slots': {
                'positive_prompt': f'instrumental visual novel background music, quiet gothic investigation tension, soft piano, low strings and sparse clock-like pulse, low density, {role}, no vocals, no singing, no lyrics, dialogue friendly, loopable',
                'negative_prompt': '',
                'prompt_shape': 'instrumentation + musical form/rhythm + mood + short role',
            },
            'visual_brief': visual_brief,
        }
    if asset_type == 'sfx':
        return {
            'asset_id': asset_id,
            'scene_id': scene_id,
            'workflow_id': 'audio_bgm_with_sfx',
            'audio_role': 'audio_sfx',
            'prompt_slots': {
                'positive_prompt': f'short visual novel sound effect, {role}, crisp paper friction and soft candlelit room resonance, one-shot, no music, no voice',
                'negative_prompt': '',
                'prompt_shape': 'short positive-only natural-language cue + one/two material or timbre colors',
            },
            'visual_brief': visual_brief,
        }
    if asset_type == 'char_expression':
        return {
            'asset_id': asset_id,
            'scene_id': scene_id,
            'workflow_id': 'char_expression',
            'prompt_slots': {
                'identity_tags': ['1girl', 'solo', 'looking_at_viewer'],
                'expression_positive': ['serious', 'frown'],
                'expression_negative': ['smile', 'open_mouth'],
            },
            'visual_brief': visual_brief,
        }
    return {'asset_id': asset_id, 'scene_id': scene_id, 'workflow_id': WORKFLOW_BY_TYPE.get(asset_type, asset_type), 'prompt_slots': {}, 'visual_brief': visual_brief}


def build_queue(project_root: Path, enrichment: dict[str, Any]) -> tuple[dict[str, Any], list[Path]]:
    scene_id = str(enrichment.get('scene_id') or 'scene')
    items: list[dict[str, Any]] = []
    written_slots: list[Path] = []
    type_counters: dict[str, int] = {}
    for batch in enrichment.get('candidate_batches', []) or []:
        if not isinstance(batch, dict):
            continue
        asset_type = str(batch.get('asset_type') or '').strip()
        if not asset_type:
            continue
        count = int(batch.get('count') or 1)
        role = str(batch.get('role') or asset_type)
        workflow = WORKFLOW_BY_TYPE.get(asset_type, asset_type)
        for _ in range(max(1, count)):
            type_counters[asset_type] = type_counters.get(asset_type, 0) + 1
            idx = type_counters[asset_type]
            asset_id = f'{slugify(scene_id)}_{slugify(asset_type)}_{idx:02d}'
            slot_path = prompt_slot_path(project_root, scene_id, asset_id)
            slots = prompt_slots_for(asset_type, asset_id, scene_id, role, idx)
            if asset_type in {'background', 'bgm', 'sfx', 'prop_cg', 'char_expression'}:
                save_json(slot_path, slots)
                written_slots.append(slot_path)
            decision = 'hold_for_source_metadata' if asset_type in SOURCE_METADATA_REQUIRED else 'generate'
            item = {
                'asset_id': asset_id,
                'asset_type': asset_type,
                'description': role,
                'decision': decision,
                'recommended_workflow_id': workflow,
                'promotion': batch.get('promotion', 'approval_gated'),
                'enrichment_source': 'scene_enrichment_plan',
            }
            if slot_path.exists():
                item['prompt_slots_path'] = str(slot_path)
            if asset_type in {'bgm', 'sfx'}:
                item['recommended_audio_role'] = 'audio_bgm' if asset_type == 'bgm' else 'audio_sfx'
                item['recommended_audio_mode'] = 'Music' if asset_type == 'bgm' else 'One-shot'
                item['recommended_audio_duration'] = 24.0 if asset_type == 'bgm' else 2.5
            items.append(item)
    queue = {
        'scene_id': scene_id,
        'source': 'enrichment-queue',
        'resolved_asset_requests': items,
        'counts': {
            'total': len(items),
            'generate': sum(1 for item in items if item['decision'] == 'generate'),
            'hold_for_source_metadata': sum(1 for item in items if item['decision'] == 'hold_for_source_metadata'),
        },
    }
    return queue, written_slots


def main() -> int:
    parser = argparse.ArgumentParser(description='Create resolved generation queue and prompt slots from a scene enrichment plan.')
    add_project_args(parser)
    parser.add_argument('--enrichment-plan', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        paths = build_project_paths(args.project_root, args.contract)
        project_root = paths.project_root
        enrichment_path = resolve_project_path(project_root, args.enrichment_plan, 'enrichment plan').resolve()
        require_under(enrichment_path, project_root, 'enrichment plan')
        out = resolve_project_path(project_root, args.out, 'out').resolve()
        require_under(out, project_root, 'out')
        queue, slots = build_queue(project_root, load_json(enrichment_path))
        save_json(out, queue)
    except ValueError as exc:
        print(f'ENRICHMENT_QUEUE_REFUSED: {exc}')
        return 2
    except Exception as exc:
        print(f'ENRICHMENT_QUEUE_FAILED: {type(exc).__name__}: {exc}')
        return 1
    print('ENRICHMENT_QUEUE')
    print('resolved_asset_requests', queue['counts']['total'])
    print('generate', queue['counts']['generate'])
    print('hold_for_source_metadata', queue['counts']['hold_for_source_metadata'])
    print('prompt_slots', len(slots))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
