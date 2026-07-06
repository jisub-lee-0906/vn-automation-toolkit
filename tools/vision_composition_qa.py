#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import add_project_args, build_project_paths, load_json, require_under, resolve_project_path, save_json

DEFAULT_THRESHOLDS = {
    'character_positioning': 4,
    'character_scale': 4,
    'textbox_safety': 5,
    'background_character_harmony': 4,
    'visual_focus': 4,
    'scene_mood_fit': 4,
    'continuity_with_adjacent_captures': 4,
}
ALLOWED_DECISIONS = {'pass'}
ALLOWED_UNCERTAINTY = {'low'}


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def score_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_scorecard(scorecard: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    captures_out: list[dict[str, Any]] = []
    thresholds = dict(DEFAULT_THRESHOLDS)
    if isinstance(scorecard.get('thresholds'), dict):
        thresholds.update(scorecard['thresholds'])

    top_uncertainty = str(scorecard.get('uncertainty', '')).lower()
    if top_uncertainty not in ALLOWED_UNCERTAINTY:
        issues.append(f'uncertainty_not_low:{top_uncertainty or "missing"}')

    decision = str(scorecard.get('decision', '')).lower()
    if decision not in ALLOWED_DECISIONS:
        issues.append(f'decision_not_pass:{decision or "missing"}')

    top_blockers = [str(x) for x in listify(scorecard.get('blockers')) if str(x).strip()]
    for blocker in top_blockers:
        issues.append(f'top_level_blocker:{blocker}')

    captures = listify(scorecard.get('captures'))
    if not captures:
        issues.append('no_captures_in_scorecard')

    for idx, raw_capture in enumerate(captures):
        capture = raw_capture if isinstance(raw_capture, dict) else {}
        name = str(capture.get('name') or f'capture_{idx + 1}')
        capture_issues: list[str] = []
        raw_scores = capture.get('scores')
        scores: dict[str, Any] = raw_scores if isinstance(raw_scores, dict) else {}
        for key, minimum_raw in thresholds.items():
            observed = score_float(scores.get(key))
            minimum = score_float(minimum_raw)
            if minimum is None:
                continue
            if observed is None or observed < minimum:
                capture_issues.append(f'{name}:{key}={observed} < {minimum:g}')
        capture_uncertainty = str(capture.get('uncertainty', scorecard.get('uncertainty', ''))).lower()
        if capture_uncertainty not in ALLOWED_UNCERTAINTY:
            capture_issues.append(f'{name}:uncertainty_not_low:{capture_uncertainty or "missing"}')
        blockers = [str(x) for x in listify(capture.get('blockers')) if str(x).strip()]
        for blocker in blockers:
            capture_issues.append(f'{name}:blocker:{blocker}')
        rationale = str(capture.get('rationale') or '').strip()
        if not rationale:
            capture_issues.append(f'{name}:missing_rationale')
        captures_out.append({
            'name': name,
            'status': 'pass' if not capture_issues else 'fail',
            'scores': scores,
            'uncertainty': capture_uncertainty,
            'blockers': blockers,
            'caveats': [str(x) for x in listify(capture.get('caveats')) if str(x).strip()],
            'rationale': rationale,
            'issues': capture_issues,
        })
        issues.extend(capture_issues)

    status = 'pass' if not issues else 'fail'
    return {
        'status': status,
        'vision_composition_scorecard_pass': status == 'pass',
        'qa_type': 'vision_composition',
        'scene_id': scorecard.get('scene_id'),
        'asset_ids': [str(x) for x in listify(scorecard.get('asset_ids'))],
        'thresholds': thresholds,
        'decision': scorecard.get('decision'),
        'uncertainty': scorecard.get('uncertainty'),
        'captures': captures_out,
        'issues': issues,
        'policy_note': 'Delegated auto-approval requires low uncertainty, no blockers, passing composition scores, and human-readable rationale per capture.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate structured vision composition scorecards for VN auto-approval.')
    add_project_args(parser)
    parser.add_argument('--scorecard', required=True, help='Vision composition scorecard JSON under project root.')
    parser.add_argument('--out', required=True, help='Output QA JSON under project root.')
    args = parser.parse_args()

    paths = build_project_paths(args.project_root, args.contract)
    project_root = paths.project_root
    scorecard_path = resolve_project_path(project_root, args.scorecard, 'scorecard').resolve()
    require_under(scorecard_path, project_root, 'scorecard')
    scorecard = load_json(scorecard_path)
    result = validate_scorecard(scorecard)
    out = resolve_project_path(project_root, args.out, 'out').resolve()
    require_under(out, project_root, 'out')
    save_json(out, result)

    print('VISION_COMPOSITION_QA')
    print('status', result['status'])
    print('captures', len(result['captures']))
    for issue in result['issues']:
        print('issue', issue)
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
