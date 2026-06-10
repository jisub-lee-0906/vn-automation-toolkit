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

from asset_lifecycle import apply_lifecycle  # noqa: E402
from vn_product_config import build_project_paths, resolve_project_path  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def normalize_manifest(manifest_path: Path, *, write: bool = False) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    assets = manifest.get('assets') or []
    updated = 0
    rows = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        before = asset.get('lifecycle_stage')
        changed = apply_lifecycle(asset)
        after = asset.get('lifecycle_stage')
        if changed:
            updated += 1
        rows.append({'asset_id': asset.get('asset_id'), 'before': before, 'after': after, 'changed': changed})
    if write and updated:
        save_json(manifest_path, manifest)
    return {
        'tool': 'normalize_asset_lifecycle',
        'manifest_path': str(manifest_path),
        'asset_count': len(assets),
        'updated': updated,
        'dry_run': not write,
        'assets': rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Normalize manifest assets to the canonical VN asset lifecycle_stage vocabulary.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--write', action='store_true', help='Write normalized lifecycle_stage fields back to the manifest.')
    parser.add_argument('--json-out')
    args = parser.parse_args(argv)
    paths = build_project_paths(args.project_root, args.contract)
    result = normalize_manifest(paths.manifest, write=args.write)
    if args.json_out:
        try:
            out = resolve_project_path(paths.project_root, args.json_out, 'json-out')
        except ValueError as exc:
            print(f'NORMALIZE_LIFECYCLE_REFUSED: {exc}')
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        save_json(out, result)
    print('NORMALIZE_ASSET_LIFECYCLE')
    print('manifest_path', result['manifest_path'])
    print('asset_count', result['asset_count'])
    print('updated', result['updated'])
    print('dry_run', str(result['dry_run']).lower())
    for row in result['assets']:
        if row['changed']:
            print('normalized', row['asset_id'], row['before'], '->', row['after'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
