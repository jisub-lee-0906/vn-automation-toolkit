
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
MAX_CAPTURES = 12
MAX_WAIT_SECONDS = 15.0


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
            warp = cap.get('warp')
            if not warp or not isinstance(warp, str) or ':' not in warp:
                errors.append(f'captures[{idx}] missing warp file:line')
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
            gates['runtime_capture'] = run_phase([sys.executable, str(TOOLS / 'capture_scene_contact_sheet.py'), '--project-root', str(paths.project_root), '--scene-id', args.scene_id, '--capture-plan', str(plan_path), '--out-dir', str(out_dir / 'gameplay_screenshots'), '--runtime-timeout', str(args.runtime_timeout)], paths.project_root, out_dir / 'runtime_capture.log', timeout=args.runtime_timeout + 10)
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
