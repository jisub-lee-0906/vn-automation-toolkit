from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths  # noqa: E402

IMAGE_LINE_RE = re.compile(r'^\s*image\s+([^=]+?)\s*=\s*(.+?)\s*$')
STRING_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')
ASSET_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.ogg', '.mp3', '.wav', '.flac')


def asset_refs_from_line(line: str) -> list[str]:
    """Return Ren'Py game-relative asset paths referenced by string literals on a line."""
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return []
    if not IMAGE_LINE_RE.match(line) and not stripped.startswith(('play ', 'queue ', 'voice ')):
        return []
    refs: list[str] = []
    for a, b in STRING_RE.findall(line):
        value = (a or b).replace('\\', '/')
        if '[' in value or ']' in value or '{' in value or '}' in value:
            continue
        if value.lower().endswith(ASSET_EXTS):
            refs.append(value)
    return refs


def check_refs(project_root: Path, game_dir: Path) -> tuple[int, int, list[str]]:
    missing: list[str] = []
    checked = 0
    skipped_alias_or_generated = 0
    for path in sorted(game_dir.rglob('*.rpy')):
        text = path.read_text(encoding='utf-8-sig')
        for lineno, line in enumerate(text.splitlines(), 1):
            asset_strings = asset_refs_from_line(line)
            if not asset_strings:
                if IMAGE_LINE_RE.match(line):
                    skipped_alias_or_generated += 1
                continue
            for s in asset_strings:
                checked += 1
                rel = s.replace('\\', '/')
                target = game_dir / rel
                if not target.exists():
                    missing.append(f'{path.relative_to(project_root)}:{lineno} missing {rel}')
    return checked, skipped_alias_or_generated, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Check literal RenPy image/audio refs under game/ exist.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    args = parser.parse_args(argv)
    paths = build_project_paths(args.project_root, args.contract)
    checked, skipped, missing = check_refs(paths.project_root, paths.game_dir)
    print('CHECK_RENPY_ASSET_REFS')
    print('project_root', paths.project_root)
    print('checked_asset_refs', checked)
    print('skipped_alias_or_generated_refs', skipped)
    if missing:
        print('MISSING_REFS')
        for item in missing:
            print('-', item)
        return 1
    print('ALL_RENPY_ASSET_REFS_EXIST')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
