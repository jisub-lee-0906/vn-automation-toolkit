from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, require_under  # noqa: E402

DEST_BY_TYPE = {
    'background': 'images/backgrounds',
    'scene_background': 'images/backgrounds',
    'event_cg': 'images/cgs',
    'scene_event_cg': 'images/cgs',
    'prop_cg': 'images/props',
    'scene_prop_cg': 'images/props',
    'character_base': 'images/characters/{character_id}/source',
    'character_expression': 'images/characters/{character_id}/expressions',
    'transparent_sprite': 'images/characters/{character_id}/sprites',
    'char_alpha': 'images/characters/{character_id}/sprites',
    'bgm': 'audio/bgm',
    'sfx': 'audio/sfx',
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def ensure_under(child: Path, parent: Path) -> None:
    child_r = child.resolve()
    parent_r = parent.resolve()
    if parent_r != child_r and parent_r not in child_r.parents:
        raise ValueError(f'Unsafe path outside {parent}: {child}')


def first_existing_candidate(metadata: dict) -> Path:
    for key in ['candidate_copies', 'output_paths']:
        for raw in metadata.get(key, []) or []:
            p = Path(raw)
            if p.exists() and p.is_file():
                return p
    raise FileNotFoundError('No existing candidate file found in metadata candidate_copies/output_paths')


def discover_pass_qa_report(metadata: dict, metadata_path: Path) -> Path | None:
    """Return a saved passing QA report recorded in metadata, if present.

    Promotion still needs concrete QA evidence. Director/Telegram approval flows may
    pass the path explicitly, but generated queue metadata can also carry the saved
    report path. A bare `qa_status=qa_pass_candidate_not_promoted` is not enough.
    """
    candidates: list[str] = []
    for key in ['qa_report', 'qa_report_path']:
        raw = metadata.get(key)
        if raw:
            candidates.append(str(raw))
    for item in metadata.get('qa_reports') or []:
        if isinstance(item, dict):
            raw = item.get('report_path') or item.get('path') or item.get('qa_report')
            if item.get('status') not in (None, 'pass'):
                continue
            if raw:
                candidates.append(str(raw))
        elif item:
            candidates.append(str(item))
    for raw in candidates:
        path = Path(raw)
        if not path.is_absolute():
            path = metadata_path.parent / path
        if path.exists():
            try:
                report = load_json(path)
            except Exception:
                continue
            if report.get('status') == 'pass':
                return path
    return None


def default_dest_dir(game_dir: Path, asset_type: str, character_id: str | None) -> Path:
    template = DEST_BY_TYPE.get(asset_type) or DEST_BY_TYPE.get(asset_type.replace('scene_', ''), 'images/generated/promoted')
    if '{character_id}' in template:
        if not character_id:
            raise ValueError(f'asset_type {asset_type} requires --character-id')
        template = template.format(character_id=character_id)
    return game_dir / template


def upsert_manifest(manifest_path: Path, entry: dict, *, replace_existing: bool = False) -> str:
    manifest = load_json(manifest_path)
    assets = manifest.setdefault('assets', [])
    for i, item in enumerate(assets):
        if item.get('asset_id') == entry['asset_id']:
            if not replace_existing:
                raise ValueError(f"manifest asset_id already exists: {entry['asset_id']} (use --replace-existing to update it)")
            assets[i] = entry
            save_json(manifest_path, manifest)
            return 'updated'
    assets.append(entry)
    save_json(manifest_path, manifest)
    return 'added'


def mark_metadata_promoted(metadata_path: Path, metadata: dict, entry: dict, log_path: Path) -> None:
    """Keep source generation sidecar fresh after promotion.

    The manifest is the playable source of truth, but resolver/owner-review flows
    also read generation-run metadata. If the metadata stays
    `not_promoted_pending_owner_approval`, later audits can show stale review
    work even though the asset is already promoted.
    """
    now = entry['metadata']['promoted_at']
    metadata['qa_status'] = 'owner_approved_promoted'
    metadata['promotion_status'] = 'owner_approved_promoted'
    promotions = metadata.setdefault('promotions', [])
    promotion_record = {
        'promoted_at': now,
        'asset_id': entry['asset_id'],
        'renpy_name': entry['renpy_name'],
        'promoted_path': entry['promoted_path'],
        'promotion_log': str(log_path),
    }
    if promotion_record not in promotions:
        promotions.append(promotion_record)
    save_json(metadata_path, metadata)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Promote an approved generated candidate into RenPy game assets and update manifest.')
    parser.add_argument('metadata', help='Path to generation run metadata.json')
    parser.add_argument('--asset-id', required=True)
    parser.add_argument('--renpy-name', required=True)
    parser.add_argument('--asset-type', help='Defaults to metadata asset_type')
    parser.add_argument('--character-id', help='Required for character destination templates')
    parser.add_argument('--dest-dir', help='Game-relative destination directory override, e.g. images/cgs')
    parser.add_argument('--filename', help='Promoted filename override; defaults to source filename')
    parser.add_argument('--scene-usage', action='append', default=[])
    parser.add_argument('--approved', action='store_true', help='Required explicit human/owner approval gate')
    parser.add_argument('--qa-report', help='Required qa_asset_file.py JSON report; refused unless status is pass')
    parser.add_argument('--project-root', default=None, help='RenPy/VN project root; defaults to repo root or VN_AUTOMATION_PROJECT_ROOT')
    parser.add_argument('--contract', help='Optional project_contract.json path')
    parser.add_argument('--force-overwrite', action='store_true', help='Allow overwriting an existing promoted destination file.')
    parser.add_argument('--replace-existing', action='store_true', help='Allow replacing an existing manifest entry with the same asset_id.')
    args = parser.parse_args(argv)

    paths = build_project_paths(args.project_root, args.contract)
    game_dir = paths.game_dir
    manifest_path = paths.manifest

    if not args.approved:
        print('PROMOTE_REFUSED: missing --approved explicit approval flag')
        return 2

    metadata_path = Path(args.metadata)
    if not metadata_path.exists():
        print(f'PROMOTE_FAILED: metadata not found: {metadata_path}')
        return 1
    metadata = load_json(metadata_path)
    asset_type = args.asset_type or metadata.get('asset_type') or metadata.get('workflow_id') or 'image'
    src = first_existing_candidate(metadata)

    if args.dest_dir:
        dest_dir = game_dir / args.dest_dir
    else:
        dest_dir = default_dest_dir(game_dir, asset_type, args.character_id)
    require_under(dest_dir, game_dir, 'destination directory')
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = args.filename or src.name
    dest = dest_dir / filename
    require_under(dest, game_dir, 'destination file')
    if dest.exists() and not args.force_overwrite:
        print(f'PROMOTE_REFUSED: destination already exists: {dest} (use --force-overwrite to replace it)')
        return 2

    manifest = load_json(manifest_path)
    for item in manifest.get('assets', []) or []:
        if item.get('asset_id') == args.asset_id and not args.replace_existing:
            print(f'PROMOTE_REFUSED: manifest asset_id already exists: {args.asset_id} (use --replace-existing to update it)')
            return 2

    qa_report_path = Path(args.qa_report) if args.qa_report else discover_pass_qa_report(metadata, metadata_path)
    if not qa_report_path:
        print('PROMOTE_REFUSED: missing --qa-report passing QA evidence')
        return 2
    if not qa_report_path.exists():
        print(f'PROMOTE_REFUSED: QA report not found: {qa_report_path}')
        return 2
    qa_report = load_json(qa_report_path)
    if qa_report.get('status') != 'pass':
        print('PROMOTE_REFUSED: QA report status is not pass')
        print('qa_report', qa_report_path)
        print('qa_status', qa_report.get('status'))
        return 2

    shutil.copy2(src, dest)

    promoted_rel = dest.relative_to(game_dir).as_posix()
    generated_path = src.as_posix()
    now = datetime.now().isoformat(timespec='seconds')
    entry = {
        'asset_id': args.asset_id,
        'asset_type': asset_type,
        'workflow_id': metadata.get('workflow_id', 'unknown'),
        'generated_path': generated_path,
        'promoted_path': promoted_rel,
        'qa_status': 'owner_approved_promoted',
        'renpy_name': args.renpy_name,
        'scene_usage': args.scene_usage,
        'metadata': {
            'promoted_at': now,
            'source_metadata': str(metadata_path),
            'source_run_id': metadata.get('run_id'),
            'source_prompt_id': metadata.get('prompt_id'),
            'seed': metadata.get('seed'),
            'approval': 'explicit_cli_approved_flag',
            'qa_report': str(qa_report_path) if qa_report_path else None,
        },
    }
    action = upsert_manifest(manifest_path, entry, replace_existing=args.replace_existing)

    paths.promotions_root.mkdir(parents=True, exist_ok=True)
    log = paths.promotions_root / f'{now.replace(":", "")}_{args.asset_id}.json'
    save_json(log, {'action': action, 'manifest_entry': entry, 'source_file': str(src), 'destination_file': str(dest)})
    mark_metadata_promoted(metadata_path, metadata, entry, log)

    print('PROMOTE_ASSET_CANDIDATE')
    print('action', action)
    print('source', src)
    print('destination', dest)
    print('manifest_path', manifest_path)
    print('promotion_log', log)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
