#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import add_project_args, build_project_paths, load_json, require_under, resolve_project_path, save_json


PASS_DECISION = 'approve'
REVIEW_DECISION = 'review_required'
REJECT_DECISION = 'reject'


def as_bool(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() in {'true', 'yes', 'pass', 'ok'})


def listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return [str(value)]


def load_project_json(project_root: Path, raw: str, label: str) -> tuple[Path, dict[str, Any]]:
    path = resolve_project_path(project_root, raw, label).resolve()
    require_under(path, project_root, label)
    return path, load_json(path)


def lower_texts(values: list[str]) -> list[str]:
    return [v.lower() for v in values]


def observed_issue_texts(scorecard: dict[str, Any]) -> list[str]:
    """Return only fields that assert actual blocking issues.

    Do not scan caveats/verdict/recommendation prose for hard-reject words:
    those fields often contain negated QA statements such as "no watermark" or
    "no readable fake text", which are evidence of acceptance rather than
    blockers. Blocking terms must be recorded in observed_issues/issues/blockers
    or by promotion_blocker=true.
    """
    texts: list[str] = []
    for key in ['observed_issues', 'issues', 'blockers']:
        texts.extend(listify(scorecard.get(key)))
    value = scorecard.get('qa_blocker_notes')
    if isinstance(value, str):
        texts.append(value)
    return texts


def find_hard_rejects(policy: dict[str, Any], scorecard: dict[str, Any]) -> list[str]:
    hard = lower_texts(listify(policy.get('hard_rejects')))
    observed = lower_texts(observed_issue_texts(scorecard))
    matched: list[str] = []
    for reject in hard:
        if any(reject in text for text in observed):
            matched.append(reject)
    return matched


def gate_passes(required_gate: str, file_qa: dict[str, Any], gate_report: dict[str, Any]) -> bool:
    if required_gate == 'file_qa_pass':
        return file_qa.get('status') == 'pass'
    if required_gate == 'vision_scorecard_pass':
        return True  # scorecard thresholds and blockers are checked separately.
    return as_bool(gate_report.get(required_gate))


def score_value(scorecard: dict[str, Any], key: str) -> float | None:
    value = scorecard.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def decide(
    *,
    approval_class: str,
    policy: dict[str, Any],
    metadata: dict[str, Any],
    file_qa: dict[str, Any],
    scorecard: dict[str, Any],
    gate_report: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    asset_type = str(metadata.get('asset_type') or '')
    asset_id = str(metadata.get('asset_id') or scorecard.get('asset_id') or '')

    if asset_type in set(listify(policy.get('human_gate_asset_types'))):
        reasons.append(f'human-gated asset_type: {asset_type}')
        return {
            'decision': REVIEW_DECISION,
            'approval_mode': 'human_required',
            'allowed_to_promote': False,
            'allowed_to_integrate': False,
            'asset_id': asset_id,
            'asset_type': asset_type,
            'reasons': reasons,
        }

    hard_rejects = find_hard_rejects(policy, scorecard)
    if scorecard.get('promotion_blocker') is True:
        hard_rejects.append('promotion_blocker true')
    if hard_rejects:
        reasons.extend(f'hard reject matched: {item}' for item in hard_rejects)
        return {
            'decision': REJECT_DECISION,
            'approval_mode': 'blocked',
            'allowed_to_promote': False,
            'allowed_to_integrate': False,
            'asset_id': asset_id,
            'asset_type': asset_type,
            'reasons': reasons,
        }

    rules = policy.get('asset_type_rules') or {}
    rule = rules.get(approval_class)
    if not isinstance(rule, dict):
        reasons.append(f'unknown approval_class: {approval_class}')
        return {
            'decision': REVIEW_DECISION,
            'approval_mode': 'human_required',
            'allowed_to_promote': False,
            'allowed_to_integrate': False,
            'asset_id': asset_id,
            'asset_type': asset_type,
            'reasons': reasons,
        }

    if rule.get('auto_approve') is not True:
        reasons.append(f'approval_class not auto-approved: {approval_class}')
        return {
            'decision': REVIEW_DECISION,
            'approval_mode': 'human_required',
            'allowed_to_promote': False,
            'allowed_to_integrate': False,
            'asset_id': asset_id,
            'asset_type': asset_type,
            'reasons': reasons,
        }

    allowed_asset_types = set(listify(rule.get('asset_types')))
    if allowed_asset_types and asset_type not in allowed_asset_types:
        reasons.append(f'asset_type {asset_type} not allowed for {approval_class}')
        return {
            'decision': REVIEW_DECISION,
            'approval_mode': 'human_required',
            'allowed_to_promote': False,
            'allowed_to_integrate': False,
            'asset_id': asset_id,
            'asset_type': asset_type,
            'reasons': reasons,
        }

    required_gates = listify(policy.get('required_gates_for_auto_promotion'))
    missing_gates = [gate for gate in required_gates if not gate_passes(gate, file_qa, gate_report)]
    if missing_gates:
        reasons.extend(f'required gate failed: {gate}' for gate in missing_gates)
        return {
            'decision': REVIEW_DECISION,
            'approval_mode': 'gate_incomplete',
            'allowed_to_promote': False,
            'allowed_to_integrate': False,
            'asset_id': asset_id,
            'asset_type': asset_type,
            'reasons': reasons,
        }

    min_scores = rule.get('min_scores') or {}
    low_scores = []
    for key, minimum in min_scores.items():
        observed = score_value(scorecard, key)
        try:
            required = float(minimum)
        except (TypeError, ValueError):
            continue
        if observed is None or observed < required:
            low_scores.append(f'{key}={observed} < {required:g}')
    if low_scores:
        reasons.extend(f'score below threshold: {item}' for item in low_scores)
        return {
            'decision': REVIEW_DECISION,
            'approval_mode': 'score_below_threshold',
            'allowed_to_promote': False,
            'allowed_to_integrate': False,
            'asset_id': asset_id,
            'asset_type': asset_type,
            'reasons': reasons,
        }

    return {
        'decision': PASS_DECISION,
        'approval_mode': 'delegated_auto',
        'allowed_scope': rule.get('allowed_scope', 'scene_local'),
        'allowed_to_promote': True,
        'allowed_to_integrate': True,
        'asset_id': asset_id,
        'asset_type': asset_type,
        'approval_class': approval_class,
        'reasons': ['all required gates and score thresholds passed'],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Evaluate whether a generated VN asset candidate may be auto-approved under a project policy.')
    add_project_args(parser)
    parser.add_argument('--approval-class', required=True, help='Policy class, e.g. scene_local_background_replacement.')
    parser.add_argument('--candidate-metadata', required=True, help='Generation run metadata.json under the project root.')
    parser.add_argument('--file-qa', required=True, help='qa_asset_file JSON report.')
    parser.add_argument('--vision-scorecard', required=True, help='Structured vision scorecard JSON.')
    parser.add_argument('--gate-report', required=True, help='JSON object containing boolean integration gates.')
    parser.add_argument('--policy', help='auto_approval_policy.json. Defaults to docs/automation/auto_approval_policy.json.')
    parser.add_argument('--out', help='Optional output JSON path under project root.')
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    paths = build_project_paths(args.project_root, args.contract)
    project_root = paths.project_root
    policy_path = resolve_project_path(project_root, args.policy or 'docs/automation/auto_approval_policy.json', 'policy')
    require_under(policy_path, project_root, 'policy')
    policy = load_json(policy_path)
    metadata_path, metadata = load_project_json(project_root, args.candidate_metadata, 'candidate-metadata')
    file_qa_path, file_qa = load_project_json(project_root, args.file_qa, 'file-qa')
    scorecard_path, scorecard = load_project_json(project_root, args.vision_scorecard, 'vision-scorecard')
    gate_report_path, gate_report = load_project_json(project_root, args.gate_report, 'gate-report')

    result = decide(
        approval_class=args.approval_class,
        policy=policy,
        metadata=metadata,
        file_qa=file_qa,
        scorecard=scorecard,
        gate_report=gate_report,
    )
    result.update({
        'policy_path': str(policy_path),
        'candidate_metadata_path': str(metadata_path),
        'file_qa_path': str(file_qa_path),
        'vision_scorecard_path': str(scorecard_path),
        'gate_report_path': str(gate_report_path),
    })
    if args.out:
        out = resolve_project_path(project_root, args.out, 'out')
        require_under(out, project_root, 'out')
        save_json(out, result)
    print('AUTO_APPROVE_CANDIDATE')
    print('decision', result['decision'])
    print('approval_mode', result['approval_mode'])
    for reason in result.get('reasons', []):
        print('reason', reason)
    return 0 if result['decision'] == PASS_DECISION else 1


if __name__ == '__main__':
    raise SystemExit(main())
