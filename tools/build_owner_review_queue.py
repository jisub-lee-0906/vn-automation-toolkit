from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, resolve_project_path, require_under, validate_project_glob  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def iter_resolved(project_root: Path, pattern: str) -> list[Path]:
    validate_project_glob(pattern, 'resolved_glob')
    paths = []
    for path in sorted(project_root.glob(pattern)):
        require_under(path.resolve(), project_root, 'resolved asset request')
        paths.append(path)
    return paths


ARCHIVED_STATUSES = {'archived', 'archived_smoke', 'closed', 'superseded', 'done_no_queue'}


def is_archived(value: Any) -> bool:
    return str(value or '').strip().lower() in ARCHIVED_STATUSES


def collect_items(paths: list[Path]) -> dict[str, Any]:
    review_items = []
    generation_items = []
    blocked_items = []
    archived_items = []
    for path in paths:
        data = load_json(path)
        scene_id = data.get('scene_id') or path.stem.replace('.resolved_asset_requests', '')
        file_archived = is_archived(data.get('queue_status') or data.get('status'))
        for item in data.get('resolved_asset_requests', []) or []:
            row = {
                'scene_id': scene_id,
                'source_resolved_path': str(path),
                'asset_id': item.get('asset_id'),
                'asset_type': item.get('asset_type'),
                'decision': item.get('decision'),
                'status': item.get('status'),
                'queue_status': item.get('queue_status') or data.get('queue_status'),
                'recommended_workflow_id': item.get('recommended_workflow_id'),
                'candidate_matches': item.get('candidate_matches', []),
                'manifest_matches': item.get('manifest_matches', []),
                'description': item.get('description', ''),
            }
            if file_archived or is_archived(item.get('queue_status')) or is_archived(item.get('status')) or is_archived(item.get('decision')):
                archived_items.append(row)
                continue
            if item.get('decision') == 'review_existing_candidate':
                review_items.append(row)
            elif item.get('decision') == 'generate':
                generation_items.append(row)
            elif item.get('status') == 'blocked' or str(item.get('decision', '')).startswith('blocked'):
                blocked_items.append(row)
    return {
        'review_items': review_items,
        'generation_items': generation_items,
        'blocked_items': blocked_items,
        'archived_items': archived_items,
    }


def bullet_candidates(item: dict[str, Any]) -> list[str]:
    lines = []
    for idx, candidate in enumerate(item.get('candidate_matches', []) or [], start=1):
        candidate_id = f"{item['asset_id']}::candidate{idx}"
        lines.append(f"  - candidate_id: `{candidate_id}`")
        lines.append(f"    - run_id: `{candidate.get('run_id')}`")
        lines.append(f"    - qa_status: `{candidate.get('qa_status')}`")
        lines.append(f"    - score: `{candidate.get('score')}`")
        for file in candidate.get('candidate_files', []) or []:
            lines.append(f"    - file: `{file}`")
    return lines


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        '# VN Owner Review Queue',
        '',
        f"Generated: `{data['generated_at']}`",
        '',
        '## How to use',
        '',
        '- For review items, inspect the candidate file(s), then write the selected `approve_candidate_id` into your approval note or ask Hermes to promote it with explicit approval.',
        '- For generation items, confirm the prompt/route before running the ComfyUI workflow.',
        '- Blocked items must be fixed before generation or promotion.',
        '',
        '## Review Existing Candidates',
        '',
    ]
    if not data['review_items']:
        lines.append('- None')
    for item in data['review_items']:
        lines.extend([
            f"- [ ] `{item['scene_id']}` / `{item['asset_id']}` ({item.get('asset_type')})",
            f"  - decision: `{item.get('decision')}`",
            f"  - recommended_workflow_id: `{item.get('recommended_workflow_id')}`",
            '  - approve_candidate_id: ``',
            '  - reject_reason: ``',
        ])
        lines.extend(bullet_candidates(item))
    lines.extend(['', '## Needs Generation', ''])
    if not data['generation_items']:
        lines.append('- None')
    for item in data['generation_items']:
        lines.extend([
            f"- [ ] `{item['scene_id']}` / `{item['asset_id']}` ({item.get('asset_type')})",
            f"  - recommended_workflow_id: `{item.get('recommended_workflow_id')}`",
            f"  - description: {item.get('description') or ''}",
        ])
    lines.extend(['', '## Blocked', ''])
    if not data['blocked_items']:
        lines.append('- None')
    for item in data['blocked_items']:
        lines.extend([
            f"- [ ] `{item['scene_id']}` / `{item['asset_id']}` ({item.get('asset_type')})",
            f"  - decision: `{item.get('decision')}`",
            f"  - status: `{item.get('status')}`",
        ])
    return '\n'.join(lines).rstrip() + '\n'


def build_queue(project_root: Path, resolved_glob: str) -> dict[str, Any]:
    paths = iter_resolved(project_root, resolved_glob)
    grouped = collect_items(paths)
    counts = {
        'review_items': len(grouped['review_items']),
        'generation_items': len(grouped['generation_items']),
        'blocked_items': len(grouped['blocked_items']),
    }
    return {
        'tool': 'build_owner_review_queue',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'project_root': str(project_root),
        'resolved_glob': resolved_glob,
        'source_files': [str(p) for p in paths],
        'counts': counts,
        **grouped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build an owner review queue from resolved scene asset requests.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--resolved-glob', default='docs/production/asset_requests/*.resolved_asset_requests.json')
    parser.add_argument('--out-md', default=None)
    parser.add_argument('--out-json', default=None)
    args = parser.parse_args(argv)

    paths = build_project_paths(args.project_root, args.contract)
    project_root = paths.project_root
    try:
        out_md = resolve_project_path(project_root, args.out_md, 'out-md') if args.out_md else (project_root / 'docs/production/owner_review_queue.md').resolve()
        out_json = resolve_project_path(project_root, args.out_json, 'out-json') if args.out_json else (project_root / 'docs/production/owner_review_queue.json').resolve()
    except ValueError as exc:
        print(f'QUEUE_REFUSED: {exc}')
        return 2
    try:
        data = build_queue(project_root, args.resolved_glob)
    except ValueError as exc:
        print(f'QUEUE_REFUSED: {exc}')
        return 2
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f'QUEUE_FAILED: {exc}')
        return 1

    save_json(out_json, data)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(data), encoding='utf-8')
    print('BUILD_OWNER_REVIEW_QUEUE')
    print('review_items', data['counts']['review_items'])
    print('generation_items', data['counts']['generation_items'])
    print('blocked_items', data['counts']['blocked_items'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
