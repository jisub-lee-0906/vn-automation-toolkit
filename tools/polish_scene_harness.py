from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, require_under  # noqa: E402

SAFE_ID_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')


def safe_id(value: str, label: str) -> str:
    if not value or any(ch not in SAFE_ID_CHARS for ch in value) or len(value) > 96:
        raise ValueError(f'{label} must contain only ASCII letters, digits, underscore, and dash: {value!r}')
    return value


def project_rel(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def resolve_under_project(project_root: Path, raw: str, label: str, *, must_exist: bool = True) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = project_root / p
    p = p.resolve()
    require_under(p, project_root, label)
    if must_exist and not p.exists():
        raise FileNotFoundError(f'{label} not found: {p}')
    return p


def run_tool(name: str, args: list[str]) -> dict[str, Any]:
    proc = subprocess.run([sys.executable, '-m', 'vn_automation.cli', name, *args], cwd=ROOT, text=True, capture_output=True)
    return {
        'name': name,
        'argv': args,
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
    }


def run_renpy_lint(sdk: str, project_root: Path, timeout: int) -> dict[str, Any]:
    if not sdk:
        return {'name': 'renpy-lint', 'returncode': 0, 'skipped': 'no_sdk_configured', 'stdout': '', 'stderr': ''}
    sdk_path = Path(sdk).expanduser()
    if not sdk_path.exists():
        return {'name': 'renpy-lint', 'returncode': 0, 'skipped': 'sdk_missing', 'stdout': '', 'stderr': ''}
    proc = subprocess.run([str(sdk_path), str(project_root), 'lint'], text=True, capture_output=True, timeout=timeout)
    return {'name': 'renpy-lint', 'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        f"# Scene Polish QA Report — {report['scene_id']}",
        '',
        f"- patch_id: `{report['patch_id']}`",
        f"- status: `{report['status']}`",
        f"- created_at: `{report['created_at']}`",
        f"- asset_policy: `{report['asset_policy']}`",
        f"- permanent_asset_changes: `{report['permanent_asset_changes']}`",
        f"- before: `{report['before']}`",
        f"- after: `{report['after']}`",
        '',
        '## Gate Results',
    ]
    for gate in report['gates']:
        skipped = gate.get('skipped')
        suffix = f" skipped={skipped}" if skipped else ''
        lines.append(f"- {gate['name']}: returncode `{gate['returncode']}`{suffix}")
    lines.extend(['', '## Changed Files'])
    for item in report['changed_files'] or []:
        lines.append(f'- `{item}`')
    lines.extend(['', '## Next Steps'])
    for item in report.get('next_steps') or []:
        lines.append(f'- {item}')
    if not report.get('next_steps'):
        lines.append('- none recorded')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def first_failure(gates: list[dict[str, Any]]) -> dict[str, Any] | None:
    for gate in gates:
        if int(gate.get('returncode', 0)) != 0:
            return gate
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run the safe post-patch Scene vertical-polish harness: guard, validators, lint, state writeback, and report.')
    parser.add_argument('--project-root')
    parser.add_argument('--contract')
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--patch-id', default='')
    parser.add_argument('--before', required=True, help='Project-relative or absolute before-script snapshot under the project root.')
    parser.add_argument('--after', default='game/script.rpy')
    parser.add_argument('--start-label', required=True)
    parser.add_argument('--end-label', default='')
    parser.add_argument('--changed-file', action='append', default=[])
    parser.add_argument('--require-var', action='append', default=[])
    parser.add_argument('--require-jump', action='append', default=[])
    parser.add_argument('--require-label', action='append', default=[])
    parser.add_argument('--require-menu-choice', action='append', default=[])
    parser.add_argument('--fail-on-removed-jump', action='store_true')
    parser.add_argument('--fail-on-removed-label', action='store_true')
    parser.add_argument('--skip-renpy-lint', action='store_true')
    parser.add_argument('--lint-timeout', type=int, default=120)
    parser.add_argument('--next-step', action='append', default=[])
    args = parser.parse_args(argv)

    try:
        scene_id = safe_id(args.scene_id, 'scene_id')
        patch_id = safe_id(args.patch_id or f'{scene_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}', 'patch_id')
        paths = build_project_paths(args.project_root, args.contract)
        before = resolve_under_project(paths.project_root, args.before, 'before')
        after = resolve_under_project(paths.project_root, args.after, 'after')
    except Exception as exc:
        print(f'POLISH_SCENE_REFUSED: {exc}')
        return 2

    run_dir = paths.project_root / 'docs' / 'validation' / patch_id
    guard_path = run_dir / 'scene_patch_guard.json'
    qa_md = run_dir / 'scene_polish_qa_report.md'
    qa_json = run_dir / 'scene_polish_qa_report.json'

    guard_args = [
        '--project-root', str(paths.project_root),
        '--before', project_rel(before, paths.project_root),
        '--after', project_rel(after, paths.project_root),
        '--start-label', args.start_label,
        '--out', project_rel(guard_path, paths.project_root),
    ]
    if args.end_label:
        guard_args.extend(['--end-label', args.end_label])
    for option, values in [
        ('--require-var', args.require_var),
        ('--require-jump', args.require_jump),
        ('--require-label', args.require_label),
        ('--require-menu-choice', args.require_menu_choice),
    ]:
        for value in values:
            guard_args.extend([option, value])
    if args.fail_on_removed_jump:
        guard_args.append('--fail-on-removed-jump')
    if args.fail_on_removed_label:
        guard_args.append('--fail-on-removed-label')

    gates: list[dict[str, Any]] = [run_tool('scene-guard', guard_args)]
    failure = first_failure(gates)
    if failure:
        print(f"POLISH_SCENE_FAILED {failure['name']}")
        print(failure.get('stdout', ''))
        print(failure.get('stderr', ''), file=sys.stderr)
        return int(failure['returncode'])

    gates.append(run_tool('validate', ['--project-root', str(paths.project_root)]))
    gates.append(run_tool('obsidian-audit', ['--project-root', str(paths.project_root)]))
    if args.skip_renpy_lint:
        gates.append({'name': 'renpy-lint', 'returncode': 0, 'skipped': 'skip_renpy_lint', 'stdout': '', 'stderr': ''})
    else:
        gates.append(run_renpy_lint(paths.contract.get('renpy_sdk_exe', ''), paths.project_root, args.lint_timeout))

    failure = first_failure(gates)
    if failure:
        print(f"POLISH_SCENE_FAILED {failure['name']}")
        print(failure.get('stdout', ''))
        print(failure.get('stderr', ''), file=sys.stderr)
        return int(failure['returncode'])

    changed_files = args.changed_file or [project_rel(after, paths.project_root)]
    report = {
        'schema_version': 1,
        'scene_id': scene_id,
        'patch_id': patch_id,
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'status': 'owner_review_pending',
        'asset_policy': 'scene_local_preview_only',
        'permanent_asset_changes': False,
        'before': project_rel(before, paths.project_root),
        'after': project_rel(after, paths.project_root),
        'changed_files': changed_files,
        'guard_report': project_rel(guard_path, paths.project_root),
        'gates': gates,
        'next_steps': args.next_step,
    }
    write_json(qa_json, report)
    write_markdown_report(qa_md, report)

    state_args = [
        '--project-root', str(paths.project_root),
        '--scene-id', scene_id,
        '--patch-id', patch_id,
        '--status', 'owner_review_pending',
        '--approval-status', 'pending',
        '--asset-policy', 'scene_local_preview_only',
        '--qa-report', project_rel(qa_md, paths.project_root),
        '--guard-report', project_rel(guard_path, paths.project_root),
    ]
    for changed in changed_files:
        state_args.extend(['--changed-file', changed])
    for step in args.next_step:
        state_args.extend(['--next-step', step])
    state_gate = run_tool('scene-state', state_args)
    gates.append(state_gate)
    if state_gate['returncode'] != 0:
        print('POLISH_SCENE_FAILED scene-state')
        print(state_gate.get('stdout', ''))
        print(state_gate.get('stderr', ''), file=sys.stderr)
        return int(state_gate['returncode'])

    check_gate = run_tool('scene-state', ['--project-root', str(paths.project_root), '--scene-id', scene_id, '--check-existing'])
    gates.append(check_gate)
    if check_gate['returncode'] != 0:
        print('POLISH_SCENE_FAILED scene-state-check')
        print(check_gate.get('stdout', ''))
        print(check_gate.get('stderr', ''), file=sys.stderr)
        return int(check_gate['returncode'])

    # Re-write the JSON report with the final state gates included.
    report['gates'] = gates
    write_json(qa_json, report)

    print('POLISH_SCENE_COMPLETE')
    print('scene_id', scene_id)
    print('patch_id', patch_id)
    print('qa_report', qa_md)
    print('guard_report', guard_path)
    for gate in gates:
        print('gate', gate['name'], gate['returncode'], gate.get('skipped', ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
