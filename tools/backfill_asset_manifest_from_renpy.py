from __future__ import annotations

import json
import re
import shutil
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths  # noqa: E402

GAME = ROOT / 'game'
MANIFEST = GAME / 'data/asset_manifest.json'
BACKUP_DIR = ROOT / 'docs/automation/backups'

IMAGE_LINE_RE = re.compile(r'^\s*image\s+([^=]+?)\s*=\s*(.+?)\s*$')
STRING_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')


def normalize_renpy_name(raw: str) -> str:
    return re.sub(r'\s+', ' ', raw.strip())


def infer_asset_type(rel: str, renpy_name: str) -> str:
    rel_l = rel.lower()
    name_l = renpy_name.lower()
    if '/background' in rel_l or name_l.startswith('bg '):
        return 'background'
    if '/event_cg/' in rel_l or 'event_cg' in name_l or '/cgs/' in rel_l:
        return 'event_cg'
    if '/props/' in rel_l or 'prop' in name_l:
        return 'prop_cg'
    if '/seoha/' in rel_l or 'heroine' in name_l or '/characters/' in rel_l:
        return 'character_sprite'
    return 'image'


def infer_workflow(asset_type: str) -> str:
    return {
        'background': 'unknown_existing_or_scene_background',
        'event_cg': 'unknown_existing_or_scene_event_cg',
        'prop_cg': 'unknown_existing_or_scene_prop_cg',
        'character_sprite': 'unknown_existing_or_manual_sprite',
        'image': 'unknown_existing',
    }.get(asset_type, 'unknown_existing')


def asset_id_from(renpy_name: str) -> str:
    s = renpy_name.lower().strip()
    s = s.replace(' ', '_')
    s = re.sub(r'[^a-z0-9_]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'unnamed_asset'


def extract_image_refs(project_root: Path = ROOT, game_dir: Path = GAME) -> list[dict]:
    refs: list[dict] = []
    for path in sorted(game_dir.rglob('*.rpy')):
        text = path.read_text(encoding='utf-8-sig')
        for lineno, line in enumerate(text.splitlines(), 1):
            m = IMAGE_LINE_RE.match(line)
            if not m:
                continue
            renpy_name = normalize_renpy_name(m.group(1))
            expr = m.group(2)
            strings = [a or b for a, b in STRING_RE.findall(expr)]
            for s in strings:
                if not s.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.ogg', '.mp3', '.wav')):
                    continue
                rel = s.replace('\\', '/')
                abs_path = game_dir / rel
                if abs_path.exists():
                    refs.append({
                        'renpy_name': renpy_name,
                        'relative_path': rel,
                        'source_file': str(path.relative_to(project_root)).replace('\\', '/'),
                        'source_line': lineno,
                    })
    return refs


def main() -> int:
    parser = argparse.ArgumentParser(description='Backfill existing RenPy image declarations into the asset manifest.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    args = parser.parse_args()
    paths = build_project_paths(args.project_root, args.contract)
    manifest_path = paths.manifest
    backup_dir = paths.docs_automation / 'backups'
    if not manifest_path.exists():
        raise SystemExit(f'Missing manifest: {manifest_path}')
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'asset_manifest_before_backfill_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    shutil.copy2(manifest_path, backup)

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assets = manifest.setdefault('assets', [])
    by_id = {a.get('asset_id'): a for a in assets}
    by_path_name = {(a.get('promoted_path'), a.get('renpy_name')) for a in assets}

    added = []
    for ref in extract_image_refs(paths.project_root, paths.game_dir):
        rel = ref['relative_path']
        renpy_name = ref['renpy_name']
        key = (rel, renpy_name)
        if key in by_path_name:
            continue
        base_id = asset_id_from(renpy_name)
        asset_id = base_id
        i = 2
        while asset_id in by_id:
            asset_id = f'{base_id}_{i}'
            i += 1
        asset_type = infer_asset_type(rel, renpy_name)
        entry = {
            'asset_id': asset_id,
            'asset_type': asset_type,
            'workflow_id': infer_workflow(asset_type),
            'generated_path': rel,
            'promoted_path': rel,
            'qa_status': 'integrated_existing_needs_owner_review',
            'renpy_name': renpy_name,
            'scene_usage': ['first5_control_observer_slice'] if ref['source_file'].endswith('first5_control_observer.rpy') else [],
            'metadata': {
                'backfilled_from': ref['source_file'],
                'backfilled_line': ref['source_line'],
                'backfilled_at': datetime.now().isoformat(timespec='seconds'),
                'note': 'Existing RenPy image declaration backfilled into manifest; generated/provenance path unknown.',
            },
        }
        assets.append(entry)
        by_id[asset_id] = entry
        by_path_name.add(key)
        added.append(asset_id)

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('BACKFILL_ASSET_MANIFEST_FROM_RENPY')
    print('backup', backup)
    print('added_count', len(added))
    for a in added:
        print('added', a)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
