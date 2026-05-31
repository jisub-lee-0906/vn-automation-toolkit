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

from extract_asset_requests_from_scene_note import build_output  # noqa: E402
from resolve_asset_requests import build_resolution, save_json  # noqa: E402

FRONTMATTER_RE = re.compile(r'^---\s*\n(?P<body>.*?)\n---\s*\n', re.S)
SCENE_ID_RE = re.compile(r'^scene_id\s*:\s*(?P<scene_id>.+?)\s*$', re.M)
SLUG_RE = re.compile(r'[^a-z0-9_]+')


def slugify(value: str) -> str:
    slug = SLUG_RE.sub('_', value.strip().lower().replace('-', '_')).strip('_')
    return slug or 'scene'


def scene_id_from_note(note: Path) -> str:
    text = note.read_text(encoding='utf-8-sig')
    fm = FRONTMATTER_RE.match(text)
    if fm:
        m = SCENE_ID_RE.search(fm.group('body'))
        if m:
            return slugify(m.group('scene_id').strip().strip('"\''))
    return slugify(note.stem)


def default_vault_from_contract(project_root: Path) -> Path | None:
    contract = project_root / 'docs/automation/project_contract.json'
    if not contract.exists():
        return None
    data = json.loads(contract.read_text(encoding='utf-8'))
    raw = data.get('obsidian_vault')
    return Path(raw) if raw else None


def resolve_args(project_root: Path, asset_requests: Path, out: Path) -> argparse.Namespace:
    return argparse.Namespace(
        project_root=str(project_root),
        asset_requests=str(asset_requests),
        manifest=None,
        contract=None,
        generation_runs_root=None,
        out=str(out),
    )


def sync_notes(project_root: Path, vault: Path, notes_glob: str, out_summary: Path) -> dict[str, Any]:
    asset_requests_dir = project_root / 'docs/production/asset_requests'
    scenes = []
    skipped = []
    for note in sorted(vault.glob(notes_glob)):
        if not note.is_file():
            continue
        scene_id = scene_id_from_note(note)
        extracted = build_output(note, scene_id)
        if not extracted.get('asset_requests'):
            skipped.append({'note': str(note), 'reason': 'no_required_assets', 'scene_id': scene_id})
            continue

        requests_path = asset_requests_dir / f'{scene_id}.asset_requests.json'
        resolved_path = asset_requests_dir / f'{scene_id}.resolved_asset_requests.json'
        save_json(requests_path, extracted)
        resolution = build_resolution(resolve_args(project_root, requests_path, resolved_path))
        save_json(resolved_path, resolution)
        scenes.append({
            'scene_id': scene_id,
            'source_note': str(note),
            'asset_requests_path': str(requests_path),
            'resolved_asset_requests_path': str(resolved_path),
            'counts': resolution.get('counts', {}),
            'asset_count': len(extracted.get('asset_requests', [])),
        })

    counts = {
        'processed': len(scenes),
        'skipped': len(skipped),
    }
    data = {
        'tool': 'sync_obsidian_scene_asset_requests',
        'synced_at': datetime.now().isoformat(timespec='seconds'),
        'project_root': str(project_root),
        'vault': str(vault),
        'notes_glob': notes_glob,
        'counts': counts,
        'scenes': scenes,
        'skipped': skipped,
    }
    save_json(out_summary, data)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Extract and resolve Required Assets from Obsidian scene notes.')
    parser.add_argument('--project-root', default=str(ROOT))
    parser.add_argument('--vault', help='Obsidian vault root. Defaults to project_contract.json obsidian_vault.')
    parser.add_argument('--notes-glob', default='VN/Scenes/*.md')
    parser.add_argument('--out-summary', default=None)
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    out_summary = Path(args.out_summary) if args.out_summary else project_root / 'docs/automation/obsidian_scene_asset_request_batch.json'
    vault = Path(args.vault) if args.vault else default_vault_from_contract(project_root)
    if vault is None:
        print('SYNC_FAILED: missing --vault and no obsidian_vault in project_contract.json')
        return 1
    if not vault.exists():
        print(f'SYNC_FAILED: missing vault: {vault}')
        return 1

    try:
        data = sync_notes(project_root, vault, args.notes_glob, out_summary)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f'SYNC_FAILED: {exc}')
        return 1

    print('SYNC_OBSIDIAN_SCENE_ASSET_REQUESTS')
    print('processed', data['counts']['processed'])
    print('skipped', data['counts']['skipped'])
    for scene in data['scenes']:
        print('scene', scene['scene_id'], scene['counts'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
