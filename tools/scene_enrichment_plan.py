#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import add_project_args, build_project_paths, load_json, resolve_project_path, require_under, save_json

DEFAULT_POLICY = {
    'default_generation_mode': 'proactive_variety',
    'minimum_candidate_counts': {
        'background': 3,
        'bgm': 2,
        'sfx': 3,
        'prop_cg': 3,
        'event_cg': 2,
        'char_expression': 2,
    },
    'promotion_policy': 'approval_gated',
    'reuse_policy': {
        'reuse_allowed_for': ['same_game_identity_anchor', 'same_location_continuity', 'approved_ui_identity'],
        'reuse_discouraged_for': ['branch_background', 'clue_prop', 'event_cg', 'scene_bgm', 'scene_sfx'],
    },
}


def build_enrichment(story: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    raw_counts = policy.get('minimum_candidate_counts')
    counts: dict[str, Any] = raw_counts if isinstance(raw_counts, dict) else DEFAULT_POLICY['minimum_candidate_counts']
    batches = []
    for item in story.get('asset_opportunities', []):
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get('asset_type') or '')
        if not asset_type:
            continue
        count = int(item.get('count_hint') or counts.get(asset_type, 1))
        batches.append({
            'asset_type': asset_type,
            'role': item.get('role', ''),
            'count': count,
            'promotion': item.get('promotion', 'approval_gated'),
            'generation_status': 'planned_not_generated',
        })
    return {
        'scene_id': story.get('scene_id'),
        'generation_mode': policy.get('default_generation_mode', 'proactive_variety'),
        'promotion_policy': policy.get('promotion_policy', 'approval_gated'),
        'reuse_policy': policy.get('reuse_policy', DEFAULT_POLICY['reuse_policy']),
        'candidate_batches': batches,
        'status': 'ready_for_candidate_generation' if batches else 'no_asset_opportunities',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Convert a story plan into a proactive VN asset enrichment/candidate-generation plan.')
    add_project_args(parser)
    parser.add_argument('--story-plan', required=True)
    parser.add_argument('--policy', default='docs/automation/asset_generation_policy.json')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    paths = build_project_paths(args.project_root, args.contract)
    story_path = resolve_project_path(paths.project_root, args.story_plan, 'story plan').resolve()
    require_under(story_path, paths.project_root, 'story plan')
    policy_path = resolve_project_path(paths.project_root, args.policy, 'policy').resolve()
    policy = load_json(policy_path) if policy_path.exists() else DEFAULT_POLICY
    out = resolve_project_path(paths.project_root, args.out, 'out').resolve()
    require_under(out, paths.project_root, 'out')
    plan = build_enrichment(load_json(story_path), policy)
    save_json(out, plan)
    print('SCENE_ENRICHMENT_PLAN')
    print('scene_id', plan.get('scene_id'))
    print('candidate_batches', len(plan['candidate_batches']))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
