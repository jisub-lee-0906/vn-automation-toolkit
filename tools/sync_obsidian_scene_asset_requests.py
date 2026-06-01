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


def default_obsidian_from_contract(project_root: Path) -> tuple[Path | None, str | None]:
    contract = project_root / 'docs/automation/project_contract.json'
    if not contract.exists():
        return None, None
    data = json.loads(contract.read_text(encoding='utf-8'))
    root_raw = data.get('obsidian_project_root') or data.get('obsidian_vault')
    if not root_raw:
        return None, data.get('obsidian_scenes_glob')
    notes_glob = data.get('obsidian_scenes_glob') or ('Scenes/*.md' if data.get('obsidian_project_root') else 'VN/Scenes/*.md')
    return Path(root_raw), notes_glob


def resolve_args(project_root: Path, asset_requests: Path, out: Path) -> argparse.Namespace:
    return argparse.Namespace(
        project_root=str(project_root),
        asset_requests=str(asset_requests),
        manifest=None,
        contract=None,
        generation_runs_root=None,
        out=str(out),
    )


def validate_notes_glob(notes_glob: str) -> None:
    pattern_path = Path(notes_glob)
    normalized_parts = notes_glob.replace('\\', '/').split('/')
    if pattern_path.is_absolute() or notes_glob.startswith(('/', '\\')) or ':' in normalized_parts[0]:
        raise ValueError(f'notes_glob must be relative to the Obsidian project root: {notes_glob}')
    if any(part == '..' for part in normalized_parts):
        raise ValueError(f'notes_glob must not contain parent traversal: {notes_glob}')


def ensure_under(child: Path, parent: Path) -> None:
    child_r = child.resolve()
    parent_r = parent.resolve()
    if child_r != parent_r and parent_r not in child_r.parents:
        raise ValueError(f'note escaped Obsidian project root: {child}')


def sync_notes(project_root: Path, vault: Path, notes_glob: str, out_summary: Path) -> dict[str, Any]:
    validate_notes_glob(notes_glob)
    vault = vault.resolve()
    asset_requests_dir = project_root / 'docs/production/asset_requests'
    scenes = []
    skipped = []
    for note in sorted(vault.glob(notes_glob)):
        ensure_under(note, vault)
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
    parser.add_argument('--notes-glob', default=None, help='Glob relative to --vault/obsidian_project_root. Defaults to project_contract obsidian_scenes_glob or VN/Scenes/*.md.')
    parser.add_argument('--out-summary', default=None)
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    out_summary = Path(args.out_summary) if args.out_summary else project_root / 'docs/automation/obsidian_scene_asset_request_batch.json'
    default_root, default_glob = default_obsidian_from_contract(project_root)
    vault = Path(args.vault) if args.vault else default_root
    if args.vault and args.notes_glob is None and default_root is not None:
        explicit_root = Path(args.vault).resolve()
        default_root_resolved = default_root.resolve()
        # Backward compatibility: --vault historically meant the Obsidian vault root.
        # New contracts store obsidian_project_root as <vault>/VN, so normalize an
        # explicitly supplied legacy vault root to the contract's title project root.
        if explicit_root != default_root_resolved and (explicit_root / 'VN').resolve() == default_root_resolved:
            vault = default_root
    notes_glob = args.notes_glob or default_glob or 'VN/Scenes/*.md'
    if vault is None:
        print('SYNC_FAILED: missing --vault and no obsidian_project_root/obsidian_vault in project_contract.json')
        return 1
    if not vault.exists():
        print(f'SYNC_FAILED: missing vault: {vault}')
        return 1

    try:
        data = sync_notes(project_root, vault, notes_glob, out_summary)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
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
