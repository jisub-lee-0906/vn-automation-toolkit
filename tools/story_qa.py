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

MIN = {
    'canon_fit': 4,
    'character_voice': 4,
    'emotional_progression': 4,
    'player_reward': 4,
}
MAX_REPETITION = 3


def score(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def validate(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    raw_targets = plan.get('story_qa_targets')
    targets: dict[str, Any] = raw_targets if isinstance(raw_targets, dict) else {}
    for key, minimum in MIN.items():
        observed = score(targets.get(key))
        if observed is None or observed < minimum:
            issues.append(f'{key}={observed} < {minimum}')
    rep = score(targets.get('repetition_risk'))
    if rep is not None and rep > MAX_REPETITION:
        issues.append(f'repetition_risk={rep} > {MAX_REPETITION}')
    beats = plan.get('beats')
    if not isinstance(beats, list) or len(beats) < 3:
        issues.append('beats must contain at least 3 story beats')
    assets = plan.get('asset_opportunities')
    if not isinstance(assets, list) or not assets:
        issues.append('asset_opportunities must be non-empty')
    else:
        types = {str(a.get('asset_type')) for a in assets if isinstance(a, dict)}
        if 'bgm' not in types and 'sfx' not in types:
            issues.append('asset_opportunities should include audio enrichment (bgm or sfx)')
    for field in ['scene_id']:
        if not plan.get(field):
            issues.append(f'missing {field}')
    return {
        'status': 'pass' if not issues else 'fail',
        'qa_type': 'story_qa',
        'scene_id': plan.get('scene_id'),
        'issues': issues,
        'story_qa_pass': not issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate VN story plan quality gates.')
    add_project_args(parser)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    paths = build_project_paths(args.project_root, args.contract)
    plan_path = resolve_project_path(paths.project_root, args.plan, 'plan').resolve()
    require_under(plan_path, paths.project_root, 'plan')
    out = resolve_project_path(paths.project_root, args.out, 'out').resolve()
    require_under(out, paths.project_root, 'out')
    result = validate(load_json(plan_path))
    save_json(out, result)
    print('STORY_QA')
    print('status', result['status'])
    for issue in result['issues']:
        print('issue', issue)
    return 0 if result['status'] == 'pass' else 1

if __name__ == '__main__':
    raise SystemExit(main())
