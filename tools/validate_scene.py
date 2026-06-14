
from __future__ import annotations

import argparse
import json
import re
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

SAFE_SCENE_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')
SAFE_CAPTURE_NAME_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
SAFE_LABEL_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,120}$')
MAX_CAPTURES = 12
MAX_WAIT_SECONDS = 15.0
MAX_ACTIONS_PER_CAPTURE = 100
MAX_ACTION_REPEAT = 80
ALLOWED_CAPTURE_KEYS = {'enter', 'space', 'escape', 'up', 'down', 'left', 'right'}



def find_label_line(project_root: Path, label: str, rel_file: str = 'game/script.rpy') -> tuple[str, int] | None:
    """Return a project-relative file:line for a Ren'Py label.

    Capture plans may specify either legacy ``warp: game/script.rpy:123`` or
    stable ``warp_label: scene_001_opening``. Label-based plans avoid line drift
    after script edits; this resolver keeps execution compatible with Ren'Py's
    existing --warp file:line interface.
    """
    if not SAFE_LABEL_RE.fullmatch(label):
        return None
    rel_path = Path(str(rel_file).replace('\\', '/'))
    if rel_path.is_absolute() or '..' in rel_path.parts or rel_path.suffix != '.rpy':
        return None
    target = (project_root / rel_path).resolve()
    try:
        require_under(target, project_root, 'capture label file')
    except ValueError:
        return None
    if not target.exists():
        return None
    label_re = re.compile(rf'^label\s+{re.escape(label)}\s*(?:\([^)]*\))?\s*:')
    for idx, line in enumerate(target.read_text(encoding='utf-8').splitlines(), 1):
        if label_re.match(line.strip()):
            return rel_path.as_posix(), idx
    return None


def resolve_capture_warp(cap: dict[str, Any], project_root: Path) -> str | None:
    warp = cap.get('warp')
    if isinstance(warp, str) and warp:
        return warp
    label = cap.get('warp_label')
    if not isinstance(label, str) or not label:
        return None
    rel_file = cap.get('warp_file') or 'game/script.rpy'
    if not isinstance(rel_file, str):
        return None
    resolved = find_label_line(project_root, label, rel_file)
    if not resolved:
        return None
    rel, line = resolved
    offset_raw = cap.get('warp_offset_lines', 0)
    try:
        offset = int(offset_raw)
    except Exception:
        return None
    if offset < 0 or offset > 500:
        return None
    line += offset
    return f'{rel}:{line}'



def extract_menu_choices_at_warp(project_root: Path, warp: str) -> list[str]:
    rel, line_raw = warp.rsplit(':', 1)
    target = (project_root / Path(rel.replace('\\', '/'))).resolve()
    try:
        start_line = int(line_raw)
    except Exception:
        return []
    try:
        lines = target.read_text(encoding='utf-8').splitlines()
    except Exception:
        return []
    if start_line < 1 or start_line > len(lines):
        return []
    idx = start_line - 1
    menu_idx = None
    for probe in range(max(0, idx - 8), min(len(lines), idx + 4)):
        if lines[probe].strip() == 'menu:':
            menu_idx = probe
            break
    if menu_idx is None:
        return []
    choices: list[str] = []
    choice_re = re.compile(r'^\s{8,}"(?P<choice>.+?)"\s*:')
    for raw in lines[menu_idx + 1:]:
        stripped = raw.strip()
        if stripped.startswith('label ') or (stripped and not raw.startswith(' ')):
            break
        match = choice_re.match(raw)
        if match:
            choices.append(match.group('choice'))
    return choices

def run_phase(cmd: list[str], cwd: Path, log: Path, timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ''
        stderr = exc.stderr or ''
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors='replace')
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors='replace')
        log.write_text(str(stdout) + (("\nSTDERR:\n" + str(stderr)) if stderr else '') + f"\nTIMEOUT after {timeout}s\n", encoding='utf-8')
        return {'status': 'FAIL', 'exit_code': 'TIMEOUT', 'timeout_seconds': timeout, 'log': str(log)}
    log.write_text((proc.stdout or '') + (("\nSTDERR:\n" + proc.stderr) if proc.stderr else ''), encoding='utf-8')
    return {'status': 'PASS' if proc.returncode == 0 else 'FAIL', 'exit_code': proc.returncode, 'log': str(log)}


def validate_capture_plan(plan_path: Path, scene_id: str, project_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        data = json.loads(plan_path.read_text(encoding='utf-8'))
    except Exception as exc:
        return {'status': 'FAIL', 'errors': [f'capture_plan unreadable or invalid JSON: {exc}'], 'path': str(plan_path)}
    if data.get('scene_id') != scene_id:
        errors.append(f'capture_plan scene_id mismatch: {data.get("scene_id")} != {scene_id}')
    captures = data.get('captures')
    seen_names: set[str] = set()
    if not isinstance(captures, list) or not captures:
        errors.append('capture_plan captures must be a non-empty list')
    elif len(captures) > MAX_CAPTURES:
        errors.append(f'too many captures: {len(captures)} > {MAX_CAPTURES}')
    if isinstance(captures, list):
        for idx, cap in enumerate(captures):
            if not isinstance(cap, dict):
                errors.append(f'captures[{idx}] must be object')
                continue
            name = cap.get('name')
            if not name:
                errors.append(f'captures[{idx}] missing name')
            elif not isinstance(name, str) or not SAFE_CAPTURE_NAME_RE.match(name) or name in {'.', '..'}:
                errors.append(f'captures[{idx}] unsafe capture name: {name}')
            elif name.upper().rstrip(' .') in {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'LPT1', 'LPT2', 'LPT3'}:
                errors.append(f'captures[{idx}] reserved Windows capture name: {name}')
            elif name in seen_names:
                errors.append(f'captures[{idx}] duplicate capture name: {name}')
            else:
                seen_names.add(name)
            wait_raw = cap.get('wait_seconds', 3.0)
            try:
                wait = float(wait_raw)
            except Exception:
                errors.append(f'captures[{idx}] wait_seconds must be numeric')
            else:
                if not (0 <= wait <= MAX_WAIT_SECONDS):
                    errors.append(f'captures[{idx}] wait_seconds must be between 0 and {MAX_WAIT_SECONDS}')
            actions = cap.get('pre_capture_actions', [])
            if actions is None:
                actions = []
            if not isinstance(actions, list):
                errors.append(f'captures[{idx}] pre_capture_actions must be a list')
                actions = []
            elif len(actions) > MAX_ACTIONS_PER_CAPTURE:
                errors.append(f'captures[{idx}] too many pre_capture_actions: {len(actions)} > {MAX_ACTIONS_PER_CAPTURE}')
            for action_idx, action in enumerate(actions):
                if not isinstance(action, dict):
                    errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] must be object')
                    continue
                action_type = action.get('type')
                if action_type not in {'wait', 'key', 'click'}:
                    errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] invalid type: {action_type}')
                    continue
                repeat_raw = action.get('repeat', 1)
                try:
                    repeat = int(repeat_raw)
                except Exception:
                    errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] repeat must be integer')
                    repeat = 1
                if not (1 <= repeat <= MAX_ACTION_REPEAT):
                    errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] repeat must be between 1 and {MAX_ACTION_REPEAT}')
                for field in ['seconds', 'interval_seconds', 'post_wait_seconds']:
                    if field in action:
                        try:
                            value = float(action[field])
                        except Exception:
                            errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] {field} must be numeric')
                            continue
                        if not (0 <= value <= MAX_WAIT_SECONDS):
                            errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] {field} must be between 0 and {MAX_WAIT_SECONDS}')
                if action_type == 'key':
                    key = action.get('key')
                    if key not in ALLOWED_CAPTURE_KEYS:
                        errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] key must be one of {sorted(ALLOWED_CAPTURE_KEYS)}')
                elif action_type == 'click':
                    for field in ['x', 'y']:
                        try:
                            value = float(action.get(field))
                        except Exception:
                            errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] click {field} must be numeric')
                            continue
                        if not (0.0 <= value <= 1.0):
                            errors.append(f'captures[{idx}].pre_capture_actions[{action_idx}] click {field} must be normalized 0..1')
            warp = resolve_capture_warp(cap, project_root)
            if not warp or not isinstance(warp, str) or ':' not in warp:
                errors.append(f'captures[{idx}] missing warp file:line or resolvable warp_label')
            else:
                rel, line = warp.rsplit(':', 1)
                if not line.isdigit() or int(line) <= 0:
                    errors.append(f'captures[{idx}] warp line must be positive integer: {line}')
                rel_norm = rel.replace('\\', '/')
                rel_path = Path(rel_norm)
                if rel_path.is_absolute() or '..' in rel_path.parts:
                    errors.append(f'captures[{idx}] warp path must be project-relative without traversal: {rel}')
                    continue
                if rel_path.suffix != '.rpy':
                    errors.append(f'captures[{idx}] warp target must be .rpy: {rel}')
                target = (project_root / rel_path).resolve()
                try:
                    require_under(target, project_root, 'capture warp')
                except ValueError as exc:
                    errors.append(str(exc))
                if not target.exists():
                    errors.append(f'captures[{idx}] warp file missing: {rel}')
                elif line.isdigit():
                    try:
                        total_lines = len(target.read_text(encoding='utf-8').splitlines())
                    except Exception:
                        total_lines = 0
                    if total_lines and int(line) > total_lines:
                        errors.append(f'captures[{idx}] warp line outside file: {line} > {total_lines}')
                    expected_choices = cap.get('expect_menu_choices')
                    if expected_choices is not None:
                        if not isinstance(expected_choices, list) or not all(isinstance(item, str) and item for item in expected_choices):
                            errors.append(f'captures[{idx}] expect_menu_choices must be a non-empty list of strings')
                        else:
                            actual_choices = extract_menu_choices_at_warp(project_root, warp)
                            if actual_choices != expected_choices:
                                errors.append(f'captures[{idx}] menu choices mismatch: expected {expected_choices!r}, got {actual_choices!r}')
    return {'status': 'PASS' if not errors else 'FAIL', 'errors': errors, 'path': str(plan_path)}

def cleanup_runtime_junk(project_root: Path) -> dict[str, Any]:
    removed = []
    for pattern in ['game/**/*.rpyc', 'game/cache/*.rpyb', 'traceback.txt', 'errors.txt', 'log.txt']:
        for p in project_root.glob(pattern):
            if p.is_file():
                p.unlink()
                removed.append(str(p))
    return {'status': 'PASS', 'removed_count': len(removed), 'removed': removed[:20]}


def write_report(out_dir: Path, manifest: dict[str, Any]) -> None:
    lines = [
        f"# Scene Validation Report — {manifest['scene_id']}",
        '',
        f"- checked_at: `{manifest['checked_at']}`",
        f"- project_root: `{manifest['project_root']}`",
        f"- static_only: `{manifest['static_only']}`",
        '',
        '## Gates',
    ]
    for name, gate in manifest['gates'].items():
        lines.append(f"- {name}: `{gate.get('status')}`")
        if gate.get('errors'):
            for err in gate['errors']:
                lines.append(f"  - {err}")
        if gate.get('log'):
            lines.append(f"  - log: `{gate['log']}`")
        if gate.get('image_quality_status'):
            lines.append(f"  - image_quality: `{gate['image_quality_status']}`")
            for item in gate.get('image_quality', [])[:12]:
                lines.append(
                    f"  - capture `{item.get('name')}`: `{item.get('status')}` "
                    f"({item.get('reason')}, mean={item.get('mean_luma')}, stdev={item.get('stdev_luma')})"
                )
    out_dir.joinpath('report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generic title-agnostic scene validation harness.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--capture-plan', required=True)
    parser.add_argument('--out-dir', default='')
    parser.add_argument('--static-only', action='store_true', help='Skip RenPy runtime/capture execution; validate static gates and capture plan only.')
    parser.add_argument('--runtime-timeout', type=int, default=120, help='Timeout seconds for RenPy lint/capture phases.')
    args = parser.parse_args(argv)
    if not SAFE_SCENE_ID_RE.match(args.scene_id):
        print(f'VALIDATE_SCENE_REFUSED: unsafe scene_id: {args.scene_id}')
        return 2

    paths = build_project_paths(args.project_root, args.contract)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (paths.project_root / 'docs/validation' / args.scene_id).resolve()
    try:
        require_under(out_dir, paths.project_root, 'validation output directory')
    except ValueError as exc:
        print('VALIDATE_SCENE_REFUSED:', exc)
        return 2
    plan_path = Path(args.capture_plan).resolve()
    try:
        require_under(plan_path, paths.project_root, 'capture plan')
    except ValueError as exc:
        print('VALIDATE_SCENE_REFUSED:', exc)
        return 2
    if not plan_path.exists():
        print(f'VALIDATE_SCENE_REFUSED: capture plan not found: {plan_path}')
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    gates: dict[str, Any] = {}
    gates['capture_plan'] = validate_capture_plan(plan_path, args.scene_id, paths.project_root)
    gates['asset_ref'] = run_phase([sys.executable, str(TOOLS / 'check_renpy_asset_refs.py'), '--project-root', str(paths.project_root)], paths.project_root, out_dir / 'asset_ref.log', timeout=args.runtime_timeout)
    if args.static_only:
        gates['runtime'] = {'status': 'SKIP', 'reason': 'static-only'}
    else:
        renpy = paths.contract.get('renpy_sdk_exe')
        if renpy:
            gates['renpy_lint'] = run_phase([renpy, str(paths.project_root), 'lint'], paths.project_root, out_dir / 'renpy_lint.log', timeout=args.runtime_timeout)
            capture_out_dir = out_dir / 'gameplay_screenshots'
            # Remove stale per-capture manifests before launching. If the new runtime
            # capture fails before writing a final manifest, old PASS data must not
            # leak into the current validation report.
            for stale_name in ['capture_manifest.json', 'capture_quality_failed.json']:
                stale = capture_out_dir / stale_name
                if stale.exists():
                    stale.unlink()
            gates['runtime_capture'] = run_phase([sys.executable, str(TOOLS / 'capture_scene_contact_sheet.py'), '--project-root', str(paths.project_root), '--scene-id', args.scene_id, '--capture-plan', str(plan_path), '--out-dir', str(capture_out_dir), '--runtime-timeout', str(args.runtime_timeout)], paths.project_root, out_dir / 'runtime_capture.log', timeout=args.runtime_timeout + 10)
            capture_manifest = capture_out_dir / 'capture_manifest.json'
            capture_quality_failed = capture_out_dir / 'capture_quality_failed.json'
            if capture_manifest.exists():
                try:
                    capture_data = json.loads(capture_manifest.read_text(encoding='utf-8'))
                    gates['runtime_capture']['image_quality_status'] = capture_data.get('image_quality_status')
                    gates['runtime_capture']['image_quality'] = capture_data.get('image_quality', [])
                    if capture_data.get('image_quality_status') == 'FAIL':
                        gates['runtime_capture']['status'] = 'FAIL'
                except Exception as exc:
                    gates['runtime_capture']['image_quality_status'] = 'UNKNOWN'
                    gates['runtime_capture']['image_quality_error'] = str(exc)
            elif capture_quality_failed.exists():
                try:
                    failed_data = json.loads(capture_quality_failed.read_text(encoding='utf-8'))
                    gates['runtime_capture']['image_quality_status'] = 'FAIL'
                    gates['runtime_capture']['image_quality'] = failed_data
                    gates['runtime_capture']['status'] = 'FAIL'
                except Exception as exc:
                    gates['runtime_capture']['image_quality_status'] = 'UNKNOWN'
                    gates['runtime_capture']['image_quality_error'] = str(exc)
        else:
            gates['renpy_lint'] = {'status': 'SKIP', 'reason': 'renpy_sdk_exe not configured'}
            gates['runtime_capture'] = {'status': 'SKIP', 'reason': 'renpy_sdk_exe not configured'}
    gates['cleanup'] = cleanup_runtime_junk(paths.project_root)

    manifest = {
        'tool': 'validate_scene',
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'project_root': str(paths.project_root),
        'scene_id': args.scene_id,
        'static_only': args.static_only,
        'capture_plan': str(plan_path),
        'gates': gates,
    }
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_report(out_dir, manifest)
    failed = [name for name, gate in gates.items() if gate.get('status') == 'FAIL']
    if failed:
        print('VALIDATE_SCENE_FAILED')
        for name in failed:
            print('-', name)
        print('manifest', out_dir / 'manifest.json')
        return 1
    print('VALIDATE_SCENE_PASSED')
    print('manifest', out_dir / 'manifest.json')
    print('report', out_dir / 'report.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
