from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, require_under  # noqa: E402

REQUIRED_TOP_LEVEL = {
    'schema_version',
    'game_slug',
    'target_level',
    'goal',
    'non_goals',
    'principles',
    'workstreams',
    'current_focus',
}
REQUIRED_WORKSTREAM_KEYS = {'id', 'name', 'status', 'objective', 'tasks', 'verification'}
ALLOWED_STATUSES = {'done', 'active', 'next', 'later', 'blocked'}
FORBIDDEN_NON_GOAL_FRAGMENTS = ['auto_promote', 'global_replacement', 'unapproved_production_replacement']


def _safe_project_rel(project_root: Path, value: str, label: str, *, must_exist: bool = False) -> list[str]:
    errors: list[str] = []
    try:
        p = Path(value)
        if not p.is_absolute():
            p = project_root / p
        p = p.resolve()
        require_under(p, project_root, label)
        if must_exist and not p.exists():
            errors.append(f'missing {label}: {value}')
    except Exception as exc:
        errors.append(f'invalid {label}: {exc}')
    return errors


def validate_roadmap(data: dict[str, Any], project_root: Path) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_TOP_LEVEL - set(data)
    if missing:
        errors.append(f'roadmap missing keys: {sorted(missing)}')
    if data.get('target_level') != 'level_3_human_supervised_vertical_polish_cockpit':
        errors.append(f'unsupported target_level: {data.get("target_level")}')
    if not isinstance(data.get('non_goals'), list) or not data.get('non_goals'):
        errors.append('non_goals must be a non-empty list')
    else:
        joined = ' '.join(str(item) for item in data['non_goals']).lower()
        for fragment in FORBIDDEN_NON_GOAL_FRAGMENTS:
            if fragment not in joined:
                errors.append(f'non_goals must explicitly forbid {fragment}')
    workstreams = data.get('workstreams')
    if not isinstance(workstreams, list) or not workstreams:
        errors.append('workstreams must be a non-empty list')
    else:
        seen: set[str] = set()
        for idx, item in enumerate(workstreams):
            if not isinstance(item, dict):
                errors.append(f'workstreams[{idx}] must be object')
                continue
            missing_item = REQUIRED_WORKSTREAM_KEYS - set(item)
            if missing_item:
                errors.append(f'workstreams[{idx}] missing keys: {sorted(missing_item)}')
            wid = item.get('id')
            if not isinstance(wid, str) or not wid:
                errors.append(f'workstreams[{idx}] id must be non-empty string')
            elif wid in seen:
                errors.append(f'duplicate workstream id: {wid}')
            else:
                seen.add(wid)
            status = item.get('status')
            if status not in ALLOWED_STATUSES:
                errors.append(f'workstreams[{idx}] invalid status: {status}')
            if not isinstance(item.get('tasks'), list) or not item.get('tasks'):
                errors.append(f'workstreams[{idx}] tasks must be a non-empty list')
            if not isinstance(item.get('verification'), list) or not item.get('verification'):
                errors.append(f'workstreams[{idx}] verification must be a non-empty list')
            for key in ['evidence', 'outputs']:
                values = item.get(key) or []
                if not isinstance(values, list):
                    errors.append(f'workstreams[{idx}] {key} must be a list when present')
                    continue
                for j, value in enumerate(values):
                    if not isinstance(value, str):
                        errors.append(f'workstreams[{idx}].{key}[{j}] must be string')
                        continue
                    errors.extend(_safe_project_rel(project_root, value, f'workstreams[{idx}].{key}[{j}]', must_exist=(key == 'evidence')))
    current_focus = data.get('current_focus')
    if not isinstance(current_focus, dict):
        errors.append('current_focus must be object')
    else:
        scene_id = current_focus.get('scene_id')
        if not isinstance(scene_id, str) or not scene_id:
            errors.append('current_focus.scene_id must be a non-empty string')
        for key in ['state_file', 'obsidian_scene_note']:
            value = current_focus.get(key)
            if not isinstance(value, str):
                errors.append(f'current_focus.{key} must be string')
            else:
                # obsidian path may be outside project; state_file must be under project.
                if key == 'state_file':
                    errors.extend(_safe_project_rel(project_root, value, f'current_focus.{key}', must_exist=True))
                elif not Path(value).expanduser().exists():
                    errors.append(f'missing current_focus.{key}: {value}')
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate a human-supervised VN production cockpit roadmap.')
    parser.add_argument('--project-root')
    parser.add_argument('--contract')
    parser.add_argument('--roadmap', default='docs/automation/production_cockpit_roadmap.json')
    args = parser.parse_args(argv)
    paths = build_project_paths(args.project_root, args.contract)
    roadmap = Path(args.roadmap)
    if not roadmap.is_absolute():
        roadmap = paths.project_root / roadmap
    roadmap = roadmap.resolve()
    try:
        require_under(roadmap, paths.project_root, 'roadmap')
    except Exception as exc:
        print(f'PRODUCTION_COCKPIT_ROADMAP_REFUSED: {exc}')
        return 2
    if not roadmap.exists():
        print(f'PRODUCTION_COCKPIT_ROADMAP_FAILED: missing roadmap {roadmap}')
        return 1
    try:
        data = json.loads(roadmap.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f'PRODUCTION_COCKPIT_ROADMAP_FAILED: invalid json: {exc}')
        return 1
    errors = validate_roadmap(data, paths.project_root)
    if errors:
        print('PRODUCTION_COCKPIT_ROADMAP_FAILED')
        for error in errors:
            print('-', error)
        return 1
    print('PRODUCTION_COCKPIT_ROADMAP_PASSED')
    print('roadmap', roadmap)
    print('target_level', data.get('target_level'))
    print('workstreams', len(data.get('workstreams') or []))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
