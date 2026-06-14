from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, require_under  # noqa: E402

SAFE_LABEL_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,120}$')
LABEL_RE = re.compile(r'^\s*label\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:')
JUMP_RE = re.compile(r'^\s*jump\s+([A-Za-z_][A-Za-z0-9_]*)\b')
CALL_RE = re.compile(r'^\s*call\s+([A-Za-z_][A-Za-z0-9_]*)\b')
MENU_RE = re.compile(r'^\s*menu\s*:')
CHOICE_RE = re.compile(r'^\s*"([^"]+)"\s*:')
VAR_ASSIGN_RE = re.compile(r'^\s*\$\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:[+\-*/]?=)')
DEFAULT_RE = re.compile(r'^\s*default\s+([A-Za-z_][A-Za-z0-9_]*)\s*=')
SCREEN_CALL_RE = re.compile(r'^\s*(?:show|hide)\s+screen\s+([A-Za-z_][A-Za-z0-9_]*)\b')
SCENE_SHOW_RE = re.compile(r'^\s*(?:scene|show)\s+([A-Za-z_][A-Za-z0-9_ ]*)\b')
AUDIO_RE = re.compile(r'^\s*play\s+(music|sound|audio)\s+"([^"]+)"')


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding='utf-8').splitlines()


def label_line_map(lines: list[str]) -> dict[str, int]:
    labels: dict[str, int] = {}
    for idx, line in enumerate(lines, 1):
        m = LABEL_RE.match(line)
        if m:
            labels[m.group(1)] = idx
    return labels


def slice_by_labels(lines: list[str], start_label: str, end_label: str | None) -> tuple[int, int, list[str]]:
    labels = label_line_map(lines)
    if start_label not in labels:
        raise ValueError(f'start label not found: {start_label}')
    start = labels[start_label]
    if end_label:
        if end_label not in labels:
            raise ValueError(f'end label not found: {end_label}')
        end = labels[end_label] - 1
        if end < start:
            raise ValueError(f'end label occurs before start label: {end_label}')
    else:
        later = sorted(line for label, line in labels.items() if line > start)
        end = later[0] - 1 if later else len(lines)
    return start, end, lines[start - 1:end]


def dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def inspect_scene(lines: list[str]) -> dict[str, Any]:
    labels: list[str] = []
    jumps: list[str] = []
    calls: list[str] = []
    menus: list[dict[str, Any]] = []
    vars_set: list[str] = []
    defaults: list[str] = []
    screen_calls: list[str] = []
    image_refs: list[str] = []
    audio_refs: list[str] = []
    current_menu: dict[str, Any] | None = None
    current_menu_indent: int | None = None

    for idx, line in enumerate(lines, 1):
        stripped = line.lstrip(' ')
        indent = len(line) - len(stripped)
        if current_menu is not None and current_menu_indent is not None and line.strip() and indent <= current_menu_indent and not MENU_RE.match(line):
            current_menu = None
            current_menu_indent = None

        if m := LABEL_RE.match(line):
            labels.append(m.group(1))
        if m := JUMP_RE.match(line):
            jumps.append(m.group(1))
        if m := CALL_RE.match(line):
            calls.append(m.group(1))
        if MENU_RE.match(line):
            current_menu = {'relative_line': idx, 'choices': []}
            current_menu_indent = indent
            menus.append(current_menu)
        elif current_menu is not None and (m := CHOICE_RE.match(line)):
            current_menu['choices'].append(m.group(1))
        if m := VAR_ASSIGN_RE.match(line):
            vars_set.append(m.group(1))
        if m := DEFAULT_RE.match(line):
            defaults.append(m.group(1))
        if m := SCREEN_CALL_RE.match(line):
            screen_calls.append(m.group(1))
        if m := SCENE_SHOW_RE.match(line):
            token = ' '.join(m.group(1).split())
            if token and token not in {'screen'}:
                image_refs.append(token)
        if m := AUDIO_RE.match(line):
            audio_refs.append(m.group(2))

    return {
        'line_count': len(lines),
        'labels': dedupe(labels),
        'jumps': dedupe(jumps),
        'calls': dedupe(calls),
        'menus': menus,
        'menu_count': len(menus),
        'vars_set': dedupe(vars_set),
        'defaults': dedupe(defaults),
        'screen_calls': dedupe(screen_calls),
        'image_refs': dedupe(image_refs),
        'audio_refs': dedupe(audio_refs),
    }


def removed(before: list[str], after: list[str]) -> list[str]:
    return [item for item in before if item not in set(after)]


def added(before: list[str], after: list[str]) -> list[str]:
    return [item for item in after if item not in set(before)]


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = ['labels', 'jumps', 'calls', 'vars_set', 'defaults', 'screen_calls', 'image_refs', 'audio_refs']
    diff: dict[str, Any] = {
        'line_count_delta': after['line_count'] - before['line_count'],
        'menu_count_delta': after['menu_count'] - before['menu_count'],
        'menus_before': before['menus'],
        'menus_after': after['menus'],
    }
    for key in keys:
        diff[f'removed_{key}'] = removed(before[key], after[key])
        diff[f'added_{key}'] = added(before[key], after[key])
    return diff


def parse_requirements(values: list[str]) -> list[str]:
    out = []
    for raw in values:
        for part in raw.split(','):
            part = part.strip()
            if part:
                out.append(part)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Deterministic RenPy scene patch guard: compare before/after scene slices and enforce required labels/jumps/vars.')
    parser.add_argument('--project-root')
    parser.add_argument('--contract')
    parser.add_argument('--before', required=True, help='Before script path. May be project-relative or absolute under project root.')
    parser.add_argument('--after', default='game/script.rpy', help='After script path. Defaults to game/script.rpy.')
    parser.add_argument('--start-label', required=True)
    parser.add_argument('--end-label')
    parser.add_argument('--out', default='')
    parser.add_argument('--require-var', action='append', default=[])
    parser.add_argument('--require-jump', action='append', default=[])
    parser.add_argument('--require-label', action='append', default=[])
    parser.add_argument('--require-menu-choice', action='append', default=[])
    parser.add_argument('--fail-on-removed-jump', action='store_true')
    parser.add_argument('--fail-on-removed-label', action='store_true')
    args = parser.parse_args(argv)

    if not SAFE_LABEL_RE.fullmatch(args.start_label) or (args.end_label and not SAFE_LABEL_RE.fullmatch(args.end_label)):
        print('SCENE_PATCH_GUARD_REFUSED: unsafe label')
        return 2

    paths = build_project_paths(args.project_root, args.contract)

    def resolve(raw: str, label: str) -> Path:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = paths.project_root / p
        p = p.resolve()
        require_under(p, paths.project_root, label)
        if not p.exists():
            raise FileNotFoundError(p)
        return p

    try:
        before_path = resolve(args.before, 'before script')
        after_path = resolve(args.after, 'after script')
    except Exception as exc:
        print(f'SCENE_PATCH_GUARD_REFUSED: {exc}')
        return 2

    try:
        b_start, b_end, before_slice = slice_by_labels(read_lines(before_path), args.start_label, args.end_label)
        a_start, a_end, after_slice = slice_by_labels(read_lines(after_path), args.start_label, args.end_label)
    except Exception as exc:
        print(f'SCENE_PATCH_GUARD_FAILED: {exc}')
        return 1

    before_info = inspect_scene(before_slice)
    after_info = inspect_scene(after_slice)
    diff = compare(before_info, after_info)

    errors: list[str] = []
    required_vars = parse_requirements(args.require_var)
    required_jumps = parse_requirements(args.require_jump)
    required_labels = parse_requirements(args.require_label)
    required_choices = parse_requirements(args.require_menu_choice)
    after_choices = [choice for menu in after_info['menus'] for choice in menu.get('choices', [])]

    for var in required_vars:
        if var not in after_info['vars_set'] and var not in after_info['defaults']:
            errors.append(f'required variable not assigned/defaulted in after slice: {var}')
    for jump in required_jumps:
        if jump not in after_info['jumps']:
            errors.append(f'required jump missing in after slice: {jump}')
    for label in required_labels:
        if label not in after_info['labels']:
            errors.append(f'required label missing in after slice: {label}')
    for choice in required_choices:
        if choice not in after_choices:
            errors.append(f'required menu choice missing in after slice: {choice}')
    if args.fail_on_removed_jump and diff['removed_jumps']:
        errors.append(f'jumps removed: {diff["removed_jumps"]}')
    if args.fail_on_removed_label and diff['removed_labels']:
        errors.append(f'labels removed: {diff["removed_labels"]}')

    manifest = {
        'tool': 'scene_patch_guard',
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'project_root': str(paths.project_root),
        'before': str(before_path),
        'after': str(after_path),
        'start_label': args.start_label,
        'end_label': args.end_label,
        'before_range': {'start_line': b_start, 'end_line': b_end},
        'after_range': {'start_line': a_start, 'end_line': a_end},
        'requirements': {
            'vars': required_vars,
            'jumps': required_jumps,
            'labels': required_labels,
            'menu_choices': required_choices,
        },
        'before': before_info,
        'after': after_info,
        'diff': diff,
        'status': 'PASS' if not errors else 'FAIL',
        'errors': errors,
    }

    out = Path(args.out).expanduser() if args.out else paths.docs_automation / 'scene_patch_guard' / f'{args.start_label}_guard.json'
    if not out.is_absolute():
        out = paths.project_root / out
    out = out.resolve()
    try:
        require_under(out, paths.project_root, 'guard output')
    except ValueError as exc:
        print(f'SCENE_PATCH_GUARD_REFUSED: {exc}')
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if errors:
        print('SCENE_PATCH_GUARD_FAILED')
        for error in errors:
            print('-', error)
        print('manifest', out)
        return 1
    print('SCENE_PATCH_GUARD_PASSED')
    print('manifest', out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
