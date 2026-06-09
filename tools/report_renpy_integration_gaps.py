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

from vn_product_config import build_project_paths, resolve_project_path  # noqa: E402

IMAGE_LINE_RE = re.compile(r'^\s*image\s+([^=]+?)\s*=\s*(.+?)\s*$')
STRING_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')
ASSET_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.ogg', '.mp3', '.wav', '.flac')


def norm_path(s: str | None) -> str:
    return (s or '').replace('\\', '/').strip()


def asset_refs_from_line(line: str) -> list[str]:
    """Return Ren'Py game-relative image/audio paths referenced by string literals."""
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return []
    if not IMAGE_LINE_RE.match(line) and not stripped.startswith(('play ', 'queue ', 'voice ')):
        return []
    refs: list[str] = []
    for a, b in STRING_RE.findall(line):
        value = norm_path(a or b)
        if '[' in value or ']' in value or '{' in value or '}' in value:
            continue
        if value.lower().endswith(ASSET_EXTS):
            refs.append(value)
    return refs


def scan_renpy_refs(project_root: Path, game_dir: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    names: dict[str, list[str]] = {}
    paths: dict[str, list[str]] = {}
    for rpy in sorted(game_dir.rglob('*.rpy')):
        text = rpy.read_text(encoding='utf-8-sig')
        rel_rpy = rpy.relative_to(project_root).as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            m = IMAGE_LINE_RE.match(line)
            if m:
                renpy_name = re.sub(r'\s+', ' ', m.group(1).strip())
                names.setdefault(renpy_name, []).append(f'{rel_rpy}:{lineno}')
            for value in asset_refs_from_line(line):
                paths.setdefault(value, []).append(f'{rel_rpy}:{lineno}')
    return names, paths


def build_report(project_root: Path, game_dir: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    names, paths = scan_renpy_refs(project_root, game_dir)
    rows = []
    counts = {'integrated': 0, 'file_only_not_declared': 0, 'missing_file': 0}
    for asset in manifest.get('assets', []):
        promoted = norm_path(asset.get('promoted_path'))
        file_path = game_dir / promoted if promoted else None
        file_exists = bool(file_path and file_path.exists())
        declared_by = names.get(asset.get('renpy_name') or '', [])
        referenced_by = paths.get(promoted, [])
        if not file_exists:
            status = 'missing_file'
        elif declared_by or referenced_by:
            status = 'integrated'
        else:
            status = 'file_only_not_declared'
        counts[status] = counts.get(status, 0) + 1
        rows.append({
            'asset_id': asset.get('asset_id'),
            'asset_type': asset.get('asset_type'),
            'renpy_name': asset.get('renpy_name'),
            'promoted_path': promoted,
            'file_exists': file_exists,
            'declared_by_renpy_name': declared_by,
            'referenced_by_path': referenced_by,
            'status': status,
        })
    return {
        'tool': 'report_renpy_integration_gaps',
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'project_root': str(project_root),
        'manifest_path': str(manifest_path),
        'counts': counts,
        'assets': rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Report whether manifest assets are integrated into RenPy image declarations.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--json-out')
    args = parser.parse_args(argv)
    paths = build_project_paths(args.project_root, args.contract)
    report = build_report(paths.project_root, paths.game_dir, paths.manifest)
    if args.json_out:
        try:
            out = resolve_project_path(paths.project_root, args.json_out, 'json-out')
        except ValueError as exc:
            print(f'GAPS_REFUSED: {exc}')
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('REPORT_RENPY_INTEGRATION_GAPS')
    for key, value in report['counts'].items():
        print(key, value)
    for item in report['assets']:
        if item['status'] != 'integrated':
            print(item['status'], item['asset_id'], item['promoted_path'])
    return 1 if report['counts'].get('missing_file') else 0


if __name__ == '__main__':
    raise SystemExit(main())
