#!/usr/bin/env python3
"""Hermes-local VN project resume check.

This script emits a compact JSON summary that Hermes can read at the start of a
new/compacted conversation before continuing VN automation work.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def endpoint_status(url: str, timeout: float = 2.0) -> str:
    if not url:
        return 'not_configured'
    probe = url.rstrip('/') + '/system_stats'
    try:
        with urllib.request.urlopen(probe, timeout=timeout) as response:
            return f'http_{response.status}'
    except Exception as exc:
        return f'{type(exc).__name__}: {str(exc)[:120]}'


def recent_json_files(path: Path, pattern: str, limit: int = 5) -> list[Path]:
    if not path.exists():
        return []
    return sorted(path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def summarize_batch(path: Path) -> dict[str, Any]:
    data = load_json(path)
    return {
        'file': str(path),
        'asset_id_prefix': data.get('asset_id_prefix'),
        'items': len(data.get('items') or []),
        'prepare_only': data.get('prepare_only'),
        'promotion_status': data.get('promotion_status'),
        'emotion': data.get('emotion'),
        'framing': data.get('framing'),
    }


def collect_promotion_status_counts(project_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    runs = project_root / 'docs/automation/generation_runs'
    if not runs.exists():
        return counts
    for meta_path in runs.glob('*/metadata.json'):
        meta = load_json(meta_path)
        status = meta.get('promotion_status')
        if status:
            counts[status] = counts.get(status, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description='Emit Hermes-local VN resume status JSON.')
    parser.add_argument('--project-root', required=True, help='RenPy project root')
    parser.add_argument('--skip-endpoint', action='store_true', help='Skip live ComfyUI endpoint probe')
    args = parser.parse_args()

    project_root = Path(args.project_root)
    automation = project_root / 'docs/automation'
    contract_path = automation / 'project_contract.json'
    current_state = automation / 'current_state.md'
    dashboard = automation / 'dashboard.md'
    contract = load_json(contract_path)

    endpoint = contract.get('comfyui_endpoint') or ''
    input_root = Path(contract.get('comfyui_input_root') or '') if contract.get('comfyui_input_root') else None
    output_root = Path(contract.get('comfyui_output_root') or '') if contract.get('comfyui_output_root') else None

    batches = [summarize_batch(path) for path in recent_json_files(automation / 'batches', '*_scene_event_cg_batch.json', 5)]

    latest_audit = recent_json_files(project_root / 'docs/validation/workflow_pack_unit_qa_20260610', 'final_vn_automation*_audit_*.md', 3)
    latest_playbooks = recent_json_files(project_root / 'docs/validation/workflow_pack_unit_qa_20260610', '*playbook*.md', 3)
    latest_asset_indexes = recent_json_files(automation / 'asset_requests', '**/asset_request_index.json', 3)

    summary = {
        'project': {
            'root': str(project_root),
            'exists': project_root.exists(),
            'game_dir_exists': (project_root / 'game').exists(),
        },
        'anchors': {
            'current_state': str(current_state),
            'current_state_exists': current_state.exists(),
            'dashboard': str(dashboard),
            'dashboard_exists': dashboard.exists(),
        },
        'contract': {
            'path': str(contract_path),
            'exists': contract_path.exists(),
            'title': contract.get('title') or contract.get('game_title'),
            'slug': contract.get('slug') or contract.get('game_slug'),
            'comfyui_endpoint': endpoint,
            'comfyui_endpoint_status': 'skipped' if args.skip_endpoint else endpoint_status(endpoint),
            'comfyui_input_root': str(input_root) if input_root else None,
            'comfyui_input_root_exists': input_root.exists() if input_root else False,
            'comfyui_output_root': str(output_root) if output_root else None,
            'comfyui_output_root_exists': output_root.exists() if output_root else False,
        },
        'recent_batches': batches,
        'promotion_status_counts': collect_promotion_status_counts(project_root),
        'latest_reports': {
            'final_audits': [str(p) for p in latest_audit],
            'playbooks': [str(p) for p in latest_playbooks],
            'asset_request_indexes': [str(p) for p in latest_asset_indexes],
        },
        'recommended_resume_steps': [
            'Read docs/automation/current_state.md first.',
            'Read docs/automation/project_contract.json and trust its endpoint/root paths.',
            'Inspect recent_batches before generating new event CG candidates.',
            'Use current chat MEDIA previews as the review UI.',
            'Require explicit approval before promotion.',
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
