#!/usr/bin/env python3
"""Refresh Hermes-local VN automation current_state.md and dashboard.md.

This keeps the conversational operating anchors synchronized with live project
state instead of relying on stale hand-written status blocks.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def run_resume_check(project_root: Path, skip_endpoint: bool) -> dict[str, Any]:
    script = Path(__file__).with_name('vn_hermes_resume_check.py')
    cmd = [sys.executable, str(script), '--project-root', str(project_root)]
    if skip_endpoint:
        cmd.append('--skip-endpoint')
    result = subprocess.run(cmd, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def latest_asset_index(resume: dict[str, Any]) -> dict[str, Any]:
    paths = resume.get('latest_reports', {}).get('asset_request_indexes') or []
    if not paths:
        return {}
    return load_json(Path(paths[0]))


def render_current_state(resume: dict[str, Any], asset_index: dict[str, Any]) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    contract = resume.get('contract', {})
    batches = resume.get('recent_batches') or []
    latest_batch = batches[0] if batches else {}
    return f"""# VN Automation Current State — Hermes Local Operating Anchor

Last refreshed: {now}

## Purpose

This file is the first anchor Hermes should read when continuing VN automation in a local conversational session.

## Operating mode

```text
Hermes-local conversational automation
User role: creative director / approval authority
Hermes role: production orchestrator / automation runner / validator
Promotion rule: explicit owner approval required
```

## Active project

```text
Title: {contract.get('title')}
Slug: {contract.get('slug')}
Project root: {resume.get('project', {}).get('root')}
ComfyUI endpoint: {contract.get('comfyui_endpoint')} ({contract.get('comfyui_endpoint_status')})
Input root exists: {contract.get('comfyui_input_root_exists')}
Output root exists: {contract.get('comfyui_output_root_exists')}
```

## Automation status

```text
Automation infrastructure: verified
Current title play-feel: requires human review
Asset promotion: approval-gated
Hermes resume anchors: current_state={resume.get('anchors', {}).get('current_state_exists')}, dashboard={resume.get('anchors', {}).get('dashboard_exists')}
Recent scene_event batch: {latest_batch.get('asset_id_prefix') or 'none'}
Recent batch promotion status: {latest_batch.get('promotion_status') or 'none'}
```

## Scene-note asset extraction

```text
Latest index: {(resume.get('latest_reports', {}).get('asset_request_indexes') or ['none'])[0]}
Scenes scanned: {asset_index.get('scene_count', 0)}
Explicit asset requests: {asset_index.get('total_asset_requests', 0)}
Candidate suggestions: {asset_index.get('total_candidate_suggestions', 0)}
Review-only inferred suggestions: {asset_index.get('total_review_only_inferred_suggestions', 0)}
Unresolved required asset mentions: {asset_index.get('total_unresolved_required_asset_mentions', 0)}
Policy: explicit Required Assets become requests; inline asset ids and inferred needs are review-only suggestions.
```

## Scene event CG policy snapshot

```text
single-character defaults: neutral/happy/serious/surprised/sad + default/front/cutin/cowboy
multi-character support: request/policy schema available, review-gated, not identity-lock guaranteed
reference conditioning: preflight request schema only; no unsafe default execution
```

## Resume protocol

```text
1. Read this file.
2. Read project_contract.json.
3. Run vn_hermes_resume_check.py if live state is needed.
4. Inspect asset_request_index.json and recent batches before generating.
5. Use chat MEDIA previews as review UI.
6. Require explicit approval before promotion.
7. Verify asset refs and Ren'Py lint after integration.
```
"""


def render_dashboard(resume: dict[str, Any], asset_index: dict[str, Any]) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    contract = resume.get('contract', {})
    batches = resume.get('recent_batches') or []
    latest_batch = batches[0] if batches else {}
    return f"""# VN automation dashboard

Last refreshed: {now}

## Overall status

```text
Automation infrastructure: verified
Current title play-feel: requires human review
Asset promotion: approval-gated
Operating mode: Hermes-local conversational automation
Active title: {contract.get('title')}
Slug: {contract.get('slug')}
```

## Live project state

```text
Project exists: {resume.get('project', {}).get('exists')}
Game dir exists: {resume.get('project', {}).get('game_dir_exists')}
ComfyUI endpoint: {contract.get('comfyui_endpoint')} ({contract.get('comfyui_endpoint_status')})
Input root exists: {contract.get('comfyui_input_root_exists')}
Output root exists: {contract.get('comfyui_output_root_exists')}
```

## Asset request index

```text
Scenes scanned: {asset_index.get('scene_count', 0)}
Explicit asset requests: {asset_index.get('total_asset_requests', 0)}
Candidate suggestions: {asset_index.get('total_candidate_suggestions', 0)}
Review-only inferred suggestions: {asset_index.get('total_review_only_inferred_suggestions', 0)}
Unresolved required asset mentions: {asset_index.get('total_unresolved_required_asset_mentions', 0)}
Latest index: {(resume.get('latest_reports', {}).get('asset_request_indexes') or ['none'])[0]}
```

## Recent batch

```text
Asset prefix: {latest_batch.get('asset_id_prefix') or 'none'}
Items: {latest_batch.get('items') or 0}
Prepare only: {latest_batch.get('prepare_only')}
Promotion status: {latest_batch.get('promotion_status') or 'none'}
Emotion/framing: {latest_batch.get('emotion') or 'n/a'} / {latest_batch.get('framing') or 'n/a'}
```

## Safety gates

```text
Good/looks nice = feedback only
승인/반영/프로덕션 적용 = promotion intent
Multi-character event CG = review-gated
Reference conditioning = preflight only unless validated workflow + explicit approval
```

## Next optional improvements

```text
1. Use multi-character schema for review-only two-character CG probes.
2. Add validated reference-conditioning workflow only if identity drift blocks production.
3. Expand scene-note inference cautiously, keeping suggestions review-only.
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description='Refresh Hermes-local VN automation dashboard/current_state anchors.')
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--skip-endpoint', action='store_true')
    args = parser.parse_args()
    project_root = Path(args.project_root)
    automation = project_root / 'docs/automation'
    resume = run_resume_check(project_root, args.skip_endpoint)
    asset_index = latest_asset_index(resume)
    current_state = automation / 'current_state.md'
    dashboard = automation / 'dashboard.md'
    current_state.write_text(render_current_state(resume, asset_index), encoding='utf-8')
    dashboard.write_text(render_dashboard(resume, asset_index), encoding='utf-8')
    print(json.dumps({'current_state': str(current_state), 'dashboard': str(dashboard)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
