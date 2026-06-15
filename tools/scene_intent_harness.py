from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, require_under  # noqa: E402

SAFE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,96}$')
LABEL_RE = re.compile(r'^\s*label\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:')
MENU_RE = re.compile(r'^\s*menu\s*:')
CHOICE_RE = re.compile(r'^\s*"([^"]+)"\s*:')


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def project_rel(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def resolve_under(project_root: Path, raw: str, label: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = project_root / p
    p = p.resolve()
    require_under(p, project_root, label)
    return p


def read_script(project_root: Path, rel: str = 'game/script.rpy') -> tuple[Path, list[str]]:
    script = resolve_under(project_root, rel, 'script')
    if not script.exists():
        raise FileNotFoundError(script)
    return script, script.read_text(encoding='utf-8').splitlines()


def label_span(lines: list[str], label: str) -> tuple[int, int]:
    labels: list[tuple[str, int]] = []
    for idx, line in enumerate(lines, 1):
        if m := LABEL_RE.match(line):
            labels.append((m.group(1), idx))
    for pos, (found, start) in enumerate(labels):
        if found == label:
            end = labels[pos + 1][1] - 1 if pos + 1 < len(labels) else len(lines)
            return start, end
    raise ValueError(f'label not found: {label}')


def extract_first_menu_choices(lines: list[str], label: str) -> tuple[list[str], int]:
    start, end = label_span(lines, label)
    slice_lines = lines[start - 1:end]
    in_menu = False
    menu_indent = 0
    menu_line = start
    choices: list[str] = []
    for rel_idx, raw in enumerate(slice_lines, start=0):
        stripped = raw.lstrip(' ')
        indent = len(raw) - len(stripped)
        if MENU_RE.match(raw):
            in_menu = True
            menu_indent = indent
            menu_line = start + rel_idx
            continue
        if in_menu:
            if raw.strip() and indent <= menu_indent:
                break
            if m := CHOICE_RE.match(raw):
                choices.append(m.group(1))
    return choices, max(0, menu_line - start)


def obsidian_project_root(contract: dict[str, Any]) -> Path | None:
    raw = contract.get('obsidian_project_root') or contract.get('obsidian_vault')
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    if root.name != 'VN':
        root = root / 'VN'
    return root.resolve()


def require_under_root(child: Path, parent: Path, label: str) -> None:
    child_r = child.resolve()
    parent_r = parent.resolve()
    if child_r != parent_r and parent_r not in child_r.parents:
        raise ValueError(f'Unsafe {label} outside {parent}: {child}')


def scene_note_path(contract: dict[str, Any], scene_id: str) -> Path:
    root = obsidian_project_root(contract)
    if root is None:
        raise ValueError('missing obsidian_project_root in project contract')
    path = (root / 'Scenes' / f'{scene_id}.md').resolve()
    require_under_root(path, root, 'scene note')
    return path


def render_scene_note_intent_block(intent: dict[str, Any]) -> str:
    prepared = intent.get('prepared_run') or {}
    lines = [
        '<!-- vn-auto:scene-intent:start -->',
        '## Automation Intent',
        '',
        f"- latest_intent: `{intent['intent_id']}`",
        f"- status: `{intent['status']}`",
        f"- intent_json: `{intent['intent_json']}`",
        f"- intent_md: `{intent['intent_md']}`",
        f"- before_script: `{prepared.get('before_script') or ''}`",
        f"- capture_plan: `{prepared.get('capture_plan') or ''}`",
        f"- asset_policy: `{intent['asset_policy']}`",
        f"- permanent_asset_changes: `{intent['permanent_asset_changes']}`",
        '',
        '### Objective',
        intent.get('objective') or 'none recorded',
        '',
        '### Owner Text',
        intent.get('owner_text') or 'none recorded',
        '',
        '<!-- vn-auto:scene-intent:end -->',
    ]
    return '\n'.join(lines) + '\n'


def upsert_scene_note_intent_block(note_path: Path, block: str) -> None:
    start = '<!-- vn-auto:scene-intent:start -->'
    end = '<!-- vn-auto:scene-intent:end -->'
    if not note_path.exists():
        raise FileNotFoundError(note_path)
    text = note_path.read_text(encoding='utf-8')
    if start in text and end in text:
        pattern = re.compile(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', re.DOTALL)
        text = pattern.sub(block, text, count=1)
    else:
        if text and not text.endswith('\n'):
            text += '\n'
        text += '\n' + block
    note_path.write_text(text, encoding='utf-8')


def render_markdown(intent: dict[str, Any]) -> str:
    lines = [
        f"# Scene Intent — {intent['scene_id']}",
        '',
        f"- intent_id: `{intent['intent_id']}`",
        f"- status: `{intent['status']}`",
        f"- created_at: `{intent['created_at']}`",
        f"- asset_policy: `{intent['asset_policy']}`",
        f"- permanent_asset_changes: `{intent['permanent_asset_changes']}`",
        '',
        '## Owner Text',
        intent.get('owner_text') or 'none recorded',
        '',
        '## Objective',
        intent.get('objective') or 'none recorded',
        '',
        '## Requested Choices',
    ]
    choices = intent.get('choices') or []
    if choices:
        lines.extend(f'- {choice}' for choice in choices)
    else:
        lines.append('- none recorded')
    lines.extend([
        '',
        '## Prepared Run',
        f"- before_script: `{intent['prepared_run']['before_script']}`",
        f"- capture_plan: `{intent['prepared_run'].get('capture_plan') or ''}`",
        '',
        '## Next Command',
        '```bash',
        intent['next_polish_scene_command'],
        '```',
    ])
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Normalize an owner/director scene response into a project-confined scene intent packet and prepared polish-scene run directory.')
    parser.add_argument('--project-root')
    parser.add_argument('--contract')
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--intent-id', default='')
    parser.add_argument('--owner-text', default='')
    parser.add_argument('--objective', default='')
    parser.add_argument('--choice', action='append', default=[])
    parser.add_argument('--risk', action='append', default=[])
    parser.add_argument('--next-step', action='append', default=[])
    parser.add_argument('--start-label', default='')
    parser.add_argument('--script', default='game/script.rpy')
    parser.add_argument('--make-capture-plan', action='store_true')
    parser.add_argument('--update-scene-note', action='store_true', help='Upsert a bounded Automation Intent block into the title-scoped Obsidian scene note.')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)

    try:
        if not SAFE_ID_RE.fullmatch(args.scene_id):
            raise ValueError(f'unsafe scene_id: {args.scene_id}')
        intent_id = args.intent_id or f'{args.scene_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        if not SAFE_ID_RE.fullmatch(intent_id):
            raise ValueError(f'unsafe intent_id: {intent_id}')
        if not args.owner_text.strip() and not args.objective.strip() and not args.choice:
            raise ValueError('owner text, objective, or at least one choice is required')
        paths = build_project_paths(args.project_root, args.contract)
        script_path, script_lines = read_script(paths.project_root, args.script)
        start_label = args.start_label or args.scene_id
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]{0,120}$', start_label):
            raise ValueError(f'unsafe start_label: {start_label}')
        # Require the label to exist before writing state so downstream polish-scene can run deterministically.
        label_span(script_lines, start_label)
    except Exception as exc:
        print(f'SCENE_INTENT_REFUSED: {exc}')
        return 2

    intent_dir = paths.docs_automation / 'scene_intents' / args.scene_id
    intent_path = intent_dir / f'{intent_id}.json'
    intent_md = intent_dir / f'{intent_id}.md'
    run_dir = paths.project_root / 'docs' / 'validation' / intent_id
    before_script = run_dir / 'script_before.rpy'
    capture_plan_path = run_dir / 'capture_plan.json'
    for target in [intent_path, intent_md, before_script, capture_plan_path if args.make_capture_plan else None]:
        if target and target.exists() and not args.force:
            print(f'SCENE_INTENT_REFUSED: target exists, pass --force to overwrite: {target}')
            return 2

    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(script_path, before_script)

    existing_choices, menu_offset = extract_first_menu_choices(script_lines, start_label)
    capture_rel = None
    if args.make_capture_plan:
        capture_plan = {
            'scene_id': args.scene_id,
            'captures': [
                {
                    'name': f'{args.scene_id}_entry',
                    'warp_label': start_label,
                    'warp_offset_lines': menu_offset,
                    'wait_seconds': 0.5,
                    'expect_menu_choices': existing_choices,
                }
            ],
        }
        save_json(capture_plan_path, capture_plan)
        capture_rel = project_rel(capture_plan_path, paths.project_root)

    polish_parts = [
        'python -m vn_automation.cli polish-scene',
        f'  --project-root {paths.project_root.as_posix()}',
        f'  --scene-id {args.scene_id}',
        f'  --patch-id {intent_id}',
        f'  --before {project_rel(before_script, paths.project_root)}',
        f'  --start-label {start_label}',
        '  --changed-file game/script.rpy',
    ]
    if capture_rel:
        polish_parts.append(f'  --capture-plan {capture_rel}')
    next_command = ' \\\n'.join(polish_parts)

    intent = {
        'schema_version': 1,
        'scene_id': args.scene_id,
        'intent_id': intent_id,
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'status': 'pending_implementation',
        'owner_text': args.owner_text.strip(),
        'objective': args.objective.strip(),
        'choices': [item.strip() for item in args.choice if item.strip()],
        'risks': [item.strip() for item in args.risk if item.strip()],
        'next_steps': [item.strip() for item in args.next_step if item.strip()],
        'asset_policy': 'scene_local_preview_only',
        'permanent_asset_changes': False,
        'start_label': start_label,
        'script': project_rel(script_path, paths.project_root),
        'existing_menu_choices_at_capture': existing_choices,
        'prepared_run': {
            'run_dir': project_rel(run_dir, paths.project_root),
            'before_script': project_rel(before_script, paths.project_root),
            'capture_plan': capture_rel,
        },
        'intent_json': project_rel(intent_path, paths.project_root),
        'intent_md': project_rel(intent_md, paths.project_root),
        'next_polish_scene_command': next_command,
    }
    save_json(intent_path, intent)
    write_text(intent_md, render_markdown(intent))
    updated_scene_note: Path | None = None
    if args.update_scene_note:
        try:
            updated_scene_note = scene_note_path(paths.contract, args.scene_id)
            upsert_scene_note_intent_block(updated_scene_note, render_scene_note_intent_block(intent))
        except Exception as exc:
            print(f'SCENE_INTENT_REFUSED: {exc}')
            return 2

    print('SCENE_INTENT_READY')
    print('scene_id', args.scene_id)
    print('intent_id', intent_id)
    print('intent', intent_path)
    print('intent_md', intent_md)
    print('before_script', before_script)
    if capture_rel:
        print('capture_plan', capture_plan_path)
    if updated_scene_note:
        print('scene_note', updated_scene_note)
    print('next_polish_scene_command')
    print(next_command)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
