from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_owner_review_queue import build_queue, render_markdown, save_json as save_queue_json  # noqa: E402
from promote_asset_candidate import main as promote_asset_main  # noqa: E402
from resolve_asset_requests import build_resolution, save_json as save_resolution_json  # noqa: E402
from sync_obsidian_scene_asset_requests import sync_notes  # noqa: E402
from vn_product_config import build_project_paths, require_under  # noqa: E402

SLUG_RE = re.compile(r'[^a-z0-9_]+')




def director_paths(args: argparse.Namespace):
    return build_project_paths(args.project_root, getattr(args, 'contract', None))


def director_project_root(args: argparse.Namespace) -> Path:
    return director_paths(args).project_root

def slugify(value: str) -> str:
    slug = SLUG_RE.sub('_', value.strip().lower().replace('-', '_')).strip('_')
    return slug or 'scene'


def project_title(project_root: Path) -> str:
    return project_root.name.replace('_', ' ').replace('-', ' ').title()


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding='utf-8'))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def telegram_media_cache_path(source: Path, scene_id: str, asset_id: str, index: int) -> tuple[Path, str]:
    """Copy review media to Hermes cache and return (absolute_path, tilde_MEDIA_path)."""
    cache_dir = Path('C:/Users/Desktop/AppData/Local/hermes/image_cache')
    safe_stem = slugify(f'{scene_id}_{asset_id}_{index}')
    target = cache_dir / f'{safe_stem}{source.suffix.lower()}'
    cache_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target, f'~/AppData/Local/hermes/image_cache/{target.name}'


def build_telegram_media_files(scene_id: str, asset_id: str, candidate_files: list[str]) -> list[dict[str, str]]:
    media = []
    for index, raw in enumerate(candidate_files, start=1):
        source = Path(str(raw)).resolve()
        if not source.exists() or source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
            continue
        cached_abs, media_path = telegram_media_cache_path(source, scene_id, asset_id, index)
        media.append({
            'source_file': str(source),
            'cached_file': str(cached_abs),
            'media_path': media_path,
            'photo_syntax': f'MEDIA:{media_path}',
            'document_syntax': f'[[as_document]]\nMEDIA:{media_path}',
        })
    return media


def load_contract(project_root: Path) -> dict[str, Any]:
    return load_json(project_root / 'docs/automation/project_contract.json')


def contract_vault(project_root: Path, explicit: str | None = None) -> Path:
    contract = load_contract(project_root)
    raw = contract.get('obsidian_project_root') or contract.get('obsidian_vault')
    if not raw:
        raise ValueError('missing Obsidian project root: pass --vault or run init with --obsidian-vault')
    expected = Path(raw).resolve()
    if not contract.get('obsidian_project_root') and expected.name != 'VN':
        expected = expected / 'VN'
    if explicit:
        root = Path(explicit).resolve()
        if root.name != 'VN':
            root = root / 'VN'
        if root.resolve() != expected.resolve():
            raise ValueError(f'explicit --vault must match active project obsidian_project_root: {expected}')
        return root.resolve()
    return expected.resolve()


def contract_scenes_glob(project_root: Path) -> str:
    contract = load_contract(project_root)
    return contract.get('obsidian_scenes_glob') or 'Scenes/*.md'


def queue_counts(project_root: Path) -> dict[str, int]:
    data = load_json(project_root / 'docs/production/owner_review_queue.json', default={})
    counts = data.get('counts') or {}
    return {
        'review_items': int(counts.get('review_items', 0) or 0),
        'generation_items': int(counts.get('generation_items', 0) or 0),
        'blocked_items': int(counts.get('blocked_items', 0) or 0),
    }


def recent_director_cards(project_root: Path) -> list[Path]:
    card_dir = project_root / 'docs/production/director_cards'
    if not card_dir.exists():
        return []
    return sorted(card_dir.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:5]


def status(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    contract = load_contract(project_root)
    vault_raw = contract.get('obsidian_project_root') or contract.get('obsidian_vault') or ''
    vault = Path(vault_raw) if vault_raw else None
    manifest = project_root / 'game/data/asset_manifest.json'
    queue = project_root / 'docs/production/owner_review_queue.json'
    counts = queue_counts(project_root)
    approval_pending = counts['review_items'] + counts['generation_items'] + counts['blocked_items']

    print('VN Production Console')
    print('')
    print(f'Project: {project_title(project_root)}')
    print(f'Project root: {project_root}')
    print('')
    print('Production readiness:')
    print(f"[{'OK' if contract else '!'}] Ren'Py project contract")
    print(f"[{'OK' if vault and vault.exists() else '!'}] Obsidian production vault")
    print(f"[{'OK' if manifest.exists() else '!'}] Asset manifest")
    print(f"[{'OK' if queue.exists() else '!'}] Owner review queue")
    print(f'[!] Approval pending asset items: {approval_pending}')
    print('')
    print("Today's director actions:")
    print('1. Create a new scene')
    print('2. Review approval pending assets')
    print('3. Run static verification')
    print('4. Generate or refresh playable placeholder')
    print('5. Continue to the next scene')
    cards = recent_director_cards(project_root)
    if cards:
        print('')
        print('Recent scene cards:')
        for card in cards:
            print(f'- {card.stem}: {card}')
    return 0


def parse_asset(raw: str) -> dict[str, str]:
    if '|' in raw:
        left, description = raw.split('|', 1)
    else:
        left, description = raw, ''
    if ':' not in left:
        raise ValueError(f'asset must be type:asset_id|description, got: {raw}')
    asset_type, asset_id = left.split(':', 1)
    asset_type = asset_type.strip().lower().replace('-', '_')
    asset_id = slugify(asset_id)
    if not asset_type or not asset_id:
        raise ValueError(f'asset must include type and asset_id, got: {raw}')
    return {'asset_type': asset_type, 'asset_id': asset_id, 'description': description.strip()}


def render_scene_note(scene_id: str, title: str, summary: str, goal: str, assets: list[dict[str, str]], choices: list[str]) -> str:
    lines = [
        '---',
        f'scene_id: {scene_id}',
        'status: draft',
        'ux_flow: supervised_director_console',
        '---',
        '',
        f'# Scene: {title}',
        '',
        '## Summary',
        summary.strip() or 'TBD.',
        '',
        '## Director Goal',
        goal.strip() or 'TBD.',
        '',
        '## Required Assets',
    ]
    if assets:
        for asset in assets:
            lines.append(f"- [ ] {asset['asset_type']}: {asset['asset_id']} | {asset['description']}")
    else:
        lines.append('- None')
    lines.extend(['', '## Playable Choices'])
    if choices:
        for choice in choices:
            lines.append(f'- {choice}')
    else:
        lines.append('- Continue')
    lines.extend(['', '## Beats', '1. Establish the scene mood.', '2. Let the player make one small interpretive choice.', '3. Exit to the next production beat.'])
    return '\n'.join(lines).rstrip() + '\n'


def renpy_quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def render_placeholder_rpy(scene_id: str, title: str, summary: str, goal: str, choices: list[str]) -> str:
    safe_choices = choices or ['Continue']
    lines = [
        f'# Auto-generated supervised placeholder draft for {scene_id}.',
        '# Replace placeholder dialogue only after director approval.',
        f'label {scene_id}:',
        f'    "{title}"',
        f'    "{summary}"',
        f'    "Director goal: {goal}"',
        '    menu:',
    ]
    for idx, choice in enumerate(safe_choices, start=1):
        lines.extend([
            f'        {renpy_quote(choice)}:',
            f'            "Placeholder branch {idx}: {choice}"',
        ])
    lines.append('    return')
    return '\n'.join(lines) + '\n'


def render_director_card(project_root: Path, scene_id: str, title: str, note: Path, draft: Path | None, queue_data: dict[str, Any]) -> str:
    counts = queue_data.get('counts', {})
    lines = [
        f'# Scene Director Card: {scene_id}',
        '',
        f'Project: {project_title(project_root)}',
        f'Title: {title}',
        f'Generated: {datetime.now().isoformat(timespec="seconds")}',
        '',
        '## Produced',
        f'- Obsidian scene note: `{note}`',
    ]
    if draft:
        lines.append(f'- Playable placeholder draft: `{draft}`')
    lines.extend([
        f'- Owner review queue: `{project_root / "docs/production/owner_review_queue.md"}`',
        '',
        '## Gate Status',
        f'- Asset approval needed: {counts.get("review_items", 0) + counts.get("generation_items", 0) + counts.get("blocked_items", 0)}',
        f'- Generation items: {counts.get("generation_items", 0)}',
        f'- Existing candidate review items: {counts.get("review_items", 0)}',
        f'- Blocked items: {counts.get("blocked_items", 0)}',
        '',
        '## Next director choices',
        '1. Review or generate asset candidates.',
        '2. Play the placeholder draft and request dialogue/tone changes.',
        '3. Approve a candidate for promotion.',
        '4. Run static verification.',
        '5. Continue to the next scene.',
    ])
    return '\n'.join(lines).rstrip() + '\n'


def refresh_queue(project_root: Path) -> dict[str, Any]:
    data = build_queue(project_root, 'docs/production/asset_requests/*.resolved_asset_requests.json')
    out_json = project_root / 'docs/production/owner_review_queue.json'
    out_md = project_root / 'docs/production/owner_review_queue.md'
    save_queue_json(out_json, data)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(data), encoding='utf-8')
    return data


def re_resolve_asset_requests(project_root: Path) -> None:
    for requests_path in sorted((project_root / 'docs/production/asset_requests').glob('*.asset_requests.json')):
        resolved_path = requests_path.with_name(requests_path.name.replace('.asset_requests.json', '.resolved_asset_requests.json'))
        ns = argparse.Namespace(
            project_root=str(project_root),
            asset_requests=str(requests_path),
            manifest=None,
            contract=None,
            generation_runs_root=None,
            out=str(resolved_path),
        )
        save_resolution_json(resolved_path, build_resolution(ns))


def infer_renpy_name(asset_id: str, asset_type: str) -> str:
    if asset_type == 'background' and str(asset_id).startswith('bg_'):
        return str(asset_id).replace('_', ' ')
    return f"{asset_type} {asset_id}".replace('background ', 'bg ')


def candidate_qa_report_path(candidate: dict[str, Any]) -> str:
    raw = candidate.get('qa_report')
    if raw:
        return str(raw)
    for item in candidate.get('qa_reports') or []:
        if isinstance(item, dict) and item.get('status') in (None, 'pass'):
            raw = item.get('report_path') or item.get('path') or item.get('qa_report')
            if raw:
                return str(raw)
        elif item:
            return str(item)
    return ''


def approve_command(project_root: Path, item: dict[str, Any], candidate: dict[str, Any], index: int) -> str:
    metadata = candidate.get('metadata_path', '')
    asset_id = item.get('asset_id', '')
    asset_type = item.get('asset_type', '')
    renpy_name = infer_renpy_name(str(asset_id), str(asset_type))
    qa_report = candidate_qa_report_path(candidate)
    parts = [
        'vn-auto director approve-candidate',
        f'--project-root "{project_root}"',
        f'--metadata "{metadata}"',
        f'--asset-id {asset_id}',
        f'--asset-type {asset_type}',
        f'--renpy-name "{renpy_name}"',
        f'--scene-usage {item.get("scene_id", "")}',
    ]
    if qa_report:
        parts.append(f'--qa-report "{qa_report}"')
    parts.append('--approved')
    return ' '.join(parts)


def render_asset_review_markdown(project_root: Path, queue_data: dict[str, Any]) -> str:
    lines = [
        '# Asset Review Console',
        '',
        f'Project: {project_title(project_root)}',
        f'Generated: {datetime.now().isoformat(timespec="seconds")}',
        '',
        '## Existing candidates needing director approval',
        '',
    ]
    review_items = queue_data.get('review_items', []) or []
    if not review_items:
        lines.append('- None')
    for item in review_items:
        lines.append(f"- `{item.get('scene_id')}` / `{item.get('asset_id')}` ({item.get('asset_type')})")
        lines.append(f"  - description: {item.get('description') or ''}")
        for idx, candidate in enumerate(item.get('candidate_matches', []) or [], start=1):
            lines.append(f'  - candidate {idx}')
            lines.append(f"    - metadata: `{candidate.get('metadata_path')}`")
            lines.append(f"    - qa_status: `{candidate.get('qa_status')}`")
            lines.append(f"    - score: `{candidate.get('score')}`")
            for file in candidate.get('candidate_files', []) or []:
                lines.append(f"    - file: `{file}`")
            lines.append(f"    - approve command: `{approve_command(project_root, item, candidate, idx)}`")
    lines.extend(['', '## Assets still needing generation', ''])
    generation_items = queue_data.get('generation_items', []) or []
    if not generation_items:
        lines.append('- None')
    for item in generation_items:
        lines.append(f"- `{item.get('scene_id')}` / `{item.get('asset_id')}` -> workflow `{item.get('recommended_workflow_id')}`")
    lines.extend(['', '## Blocked', ''])
    blocked = queue_data.get('blocked_items', []) or []
    if not blocked:
        lines.append('- None')
    for item in blocked:
        lines.append(f"- `{item.get('scene_id')}` / `{item.get('asset_id')}`: {item.get('decision')}")
    return '\n'.join(lines).rstrip() + '\n'


def render_dashboard_html(project_root: Path, queue_data: dict[str, Any]) -> str:
    title = project_title(project_root)
    cards: list[str] = []
    for item in queue_data.get('review_items', []) or []:
        candidate_html = []
        for idx, candidate in enumerate(item.get('candidate_matches', []) or [], start=1):
            files_html = []
            for raw in candidate.get('candidate_files', []) or []:
                escaped = html.escape(str(raw))
                suffix = Path(str(raw)).suffix.lower()
                if suffix in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                    files_html.append(f'<img src="file:///{escaped}" alt="candidate {idx}" />')
                elif suffix in {'.ogg', '.mp3', '.wav', '.flac'}:
                    files_html.append(f'<audio controls src="file:///{escaped}"></audio>')
                else:
                    files_html.append(f'<code>{escaped}</code>')
            command = html.escape(approve_command(project_root, item, candidate, idx))
            candidate_html.append(
                '<div class="candidate">'
                f'<h3>candidate {idx}</h3>'
                f'<p>QA: {html.escape(str(candidate.get("qa_status")))} / score: {html.escape(str(candidate.get("score")))}</p>'
                + ''.join(files_html)
                + f'<pre>{command}</pre>'
                '</div>'
            )
        cards.append(
            '<section class="asset-card">'
            f'<h2>{html.escape(str(item.get("asset_id")))} <small>{html.escape(str(item.get("asset_type")))}</small></h2>'
            f'<p>{html.escape(str(item.get("description") or ""))}</p>'
            + ''.join(candidate_html)
            + '</section>'
        )
    screenshots = []
    for shot in sorted((project_root / 'docs/production/screenshots').glob('*')):
        if shot.is_file():
            screenshots.append(f'<img src="file:///{html.escape(str(shot))}" alt="{html.escape(shot.name)}" />')
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)} Director Dashboard</title>
<style>body{{font-family:system-ui;background:#111;color:#eee;margin:2rem}}.asset-card,.preview{{border:1px solid #444;border-radius:12px;padding:1rem;margin:1rem 0;background:#1b1b1b}}img{{max-width:360px;max-height:240px;display:block;margin:.5rem 0}}pre{{white-space:pre-wrap;background:#050505;padding:.75rem;border-radius:8px}}</style>
</head><body>
<h1>{html.escape(title)} Director Dashboard</h1>
<p>Asset Review / approval-gated VN production console.</p>
<h2>Asset Review</h2>
{''.join(cards) if cards else '<p>No existing candidates need review.</p>'}
<section class="preview"><h2>Ren\'Py Screenshot Preview</h2>{''.join(screenshots) if screenshots else '<p>No screenshots registered yet.</p>'}</section>
</body></html>'''



def registry_path(project_root: Path) -> Path:
    return project_root / 'docs/production/telegram_approval_registry.json'


def load_registry(project_root: Path) -> dict[str, Any]:
    return load_json(registry_path(project_root), default={'items': []})


def save_registry(project_root: Path, data: dict[str, Any]) -> None:
    path = registry_path(project_root)
    data['updated_at'] = datetime.now().isoformat(timespec='seconds')
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def make_approval_token(project_root: Path, scene_id: str, asset_id: str, metadata_path: str, index: int) -> str:
    try:
        rel = Path(metadata_path).resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        rel = str(metadata_path)
    digest = hashlib.sha256(f'{scene_id}|{asset_id}|{rel}|{index}'.encode('utf-8')).hexdigest()
    return f'VN-{digest[:10].upper()}'


def build_telegram_review_items(project_root: Path, queue_data: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in queue_data.get('review_items', []) or []:
        scene_id = str(item.get('scene_id') or '')
        asset_id = str(item.get('asset_id') or '')
        asset_type = str(item.get('asset_type') or '')
        renpy_name = infer_renpy_name(asset_id, asset_type)
        for idx, candidate in enumerate(item.get('candidate_matches', []) or [], start=1):
            metadata = str(candidate.get('metadata_path') or '')
            candidate_files = candidate.get('candidate_files', []) or []
            token = make_approval_token(project_root, scene_id, asset_id, metadata, idx)
            items.append({
                'token': token,
                'status': 'pending_telegram_approval',
                'project_root': str(project_root),
                'scene_id': scene_id,
                'asset_id': asset_id,
                'asset_type': asset_type,
                'renpy_name': renpy_name,
                'metadata_path': metadata,
                'candidate_files': candidate_files,
                'telegram_media_files': build_telegram_media_files(scene_id, asset_id, candidate_files),
                'qa_status': candidate.get('qa_status'),
                'score': candidate.get('score'),
                'created_at': datetime.now().isoformat(timespec='seconds'),
                'approval_phrase': f'승인 {token}',
            })
    return items


def render_telegram_review_card(project_root: Path, items: list[dict[str, Any]]) -> str:
    lines = [
        '# Telegram Asset Approval Registry',
        '',
        f'Project: {project_title(project_root)}',
        f'Generated: {datetime.now().isoformat(timespec="seconds")}',
        '',
        '## Pending Telegram approval tokens',
        '',
    ]
    if not items:
        lines.append('- None')
    for item in items:
        lines.append(f"- token: `{item['token']}`")
        lines.append(f"  - approve phrase: `{item['approval_phrase']}`")
        lines.append(f"  - scene/asset: `{item['scene_id']}` / `{item['asset_id']}` ({item['asset_type']})")
        lines.append(f"  - metadata: `{item['metadata_path']}`")
        for file in item.get('candidate_files', []) or []:
            lines.append(f"  - source media: `MEDIA:{file}`")
        for media in item.get('telegram_media_files', []) or []:
            lines.append(f"  - telegram photo: `{media['photo_syntax']}`")
            lines.append(f"  - telegram document: `{media['document_syntax']}`")
        lines.append(f"  - CLI approve: `vn-auto director telegram-approve --project-root \"{project_root}\" --token {item['token']} --approved-text \"승인 {item['token']}\" --approved`")
    lines.extend(['', '## Safety rule', 'Only the exact tokened approval phrase for a pending item should trigger promotion. Old, unknown, or already-used tokens must be rejected.'])
    return '\n'.join(lines).rstrip() + '\n'


def telegram_review(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    re_resolve_asset_requests(project_root)
    queue_data = refresh_queue(project_root)
    items = build_telegram_review_items(project_root, queue_data)
    registry = {
        'project_root': str(project_root),
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'items': items,
    }
    save_registry(project_root, registry)
    card = project_root / 'docs/production/director_cards/telegram_asset_review.md'
    write_text(card, render_telegram_review_card(project_root, items))
    print('Telegram Approval Review Prepared')
    print(f'Project: {project_title(project_root)}')
    print('pending_tokens', len(items))
    for item in items:
        print('token', item['token'], item['asset_id'], item['metadata_path'])
        print('approval_phrase', item['approval_phrase'])
        for file in item.get('candidate_files', []) or []:
            print('MEDIA_SOURCE', file)
        for media in item.get('telegram_media_files', []) or []:
            print('MEDIA_PHOTO', media.get('photo_syntax'))
            print('MEDIA_DOCUMENT', media.get('document_syntax'))
    print('registry', registry_path(project_root))
    print('review_card', card)
    return 0


def normalized_approval(text: str) -> str:
    return ' '.join(text.strip().split())



APPROVAL_WORDS = {'승인', 'approve', 'approved'}


def promote_telegram_item(project_root: Path, registry: dict[str, Any], item: dict[str, Any], args: argparse.Namespace, approved_text: str, approval_message_id: str | None) -> int:
    metadata_path = Path(str(item.get('metadata_path') or '')).resolve()
    try:
        require_under(metadata_path, project_root, 'metadata outside project root')
    except ValueError as exc:
        print(f'TELEGRAM_APPROVE_REFUSED: {exc}')
        return 2
    approve_args = argparse.Namespace(
        project_root=str(project_root),
        approved=True,
        metadata=str(metadata_path),
        asset_id=item['asset_id'],
        asset_type=item.get('asset_type') or '',
        renpy_name=item.get('renpy_name') or infer_renpy_name(item['asset_id'], item.get('asset_type') or ''),
        character_id=getattr(args, 'character_id', '') or '',
        dest_dir=getattr(args, 'dest_dir', '') or '',
        filename=getattr(args, 'filename', '') or '',
        scene_usage=[item.get('scene_id')] if item.get('scene_id') else [],
        qa_report=getattr(args, 'qa_report', '') or '',
        force_overwrite=bool(getattr(args, 'force_overwrite', False)),
        replace_existing=bool(getattr(args, 'replace_existing', False)),
    )
    rc = approve_candidate(approve_args)
    if rc != 0:
        return rc
    item['status'] = 'owner_approved_promoted'
    item['approved_at'] = datetime.now().isoformat(timespec='seconds')
    item['approved_text'] = approved_text
    item['telegram_approval_message_id'] = approval_message_id
    save_registry(project_root, registry)
    print('Telegram Approval Consumed')
    print('token', item.get('token'))
    if approval_message_id:
        print('approval_message_id', approval_message_id)
    print('registry', registry_path(project_root))
    return 0


def telegram_approve(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    if not args.approved:
        print('TELEGRAM_APPROVE_REFUSED: missing --approved explicit owner approval flag')
        return 2
    token = args.token.strip().upper()
    registry = load_registry(project_root)
    item = next((entry for entry in registry.get('items', []) if str(entry.get('token', '')).upper() == token), None)
    if not item:
        print(f'TELEGRAM_APPROVE_REFUSED: unknown token: {token}')
        return 2
    if item.get('status') != 'pending_telegram_approval':
        print(f"TELEGRAM_APPROVE_REFUSED: token is not pending: {item.get('status')}")
        return 2
    expected = normalized_approval(str(item.get('approval_phrase') or f'승인 {token}'))
    actual = normalized_approval(args.approved_text)
    if actual != expected:
        print('TELEGRAM_APPROVE_REFUSED: approval text does not match token phrase')
        print('expected', expected)
        print('actual', actual)
        return 2
    return promote_telegram_item(project_root, registry, item, args, args.approved_text, args.message_id or None)


def telegram_bind_message(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    token = args.token.strip().upper()
    registry = load_registry(project_root)
    item = next((entry for entry in registry.get('items', []) if str(entry.get('token', '')).upper() == token), None)
    if not item:
        print(f'TELEGRAM_BIND_REFUSED: unknown token: {token}')
        return 2
    if item.get('status') != 'pending_telegram_approval':
        print(f"TELEGRAM_BIND_REFUSED: token is not pending: {item.get('status')}")
        return 2
    # Do not let two pending tokens point at the same Telegram review message.
    for entry in registry.get('items', []) or []:
        if entry is not item and entry.get('status') == 'pending_telegram_approval' and str(entry.get('telegram_review_message_id') or '') == str(args.message_id):
            print(f'TELEGRAM_BIND_REFUSED: message_id already bound to token: {entry.get("token")}')
            return 2
    item['telegram_review_message_id'] = str(args.message_id)
    item['telegram_chat_id'] = args.chat_id or None
    item['telegram_bound_at'] = datetime.now().isoformat(timespec='seconds')
    save_registry(project_root, registry)
    print('Telegram Review Message Bound')
    print('token', token)
    print('message_id', args.message_id)
    print('registry', registry_path(project_root))
    return 0


def telegram_approve_message(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    if not args.approved:
        print('TELEGRAM_APPROVE_REFUSED: missing --approved explicit owner approval flag')
        return 2
    registry = load_registry(project_root)
    matches = [
        entry for entry in registry.get('items', []) or []
        if entry.get('status') == 'pending_telegram_approval'
        and str(entry.get('telegram_review_message_id') or '') == str(args.reply_to_message_id)
    ]
    if not matches:
        print(f'TELEGRAM_APPROVE_REFUSED: no pending token bound to reply_to_message_id: {args.reply_to_message_id}')
        return 2
    if len(matches) > 1:
        print(f'TELEGRAM_APPROVE_REFUSED: multiple pending tokens bound to reply_to_message_id: {args.reply_to_message_id}')
        return 2
    item = matches[0]
    actual = normalized_approval(args.approved_text)
    expected = normalized_approval(str(item.get('approval_phrase') or f"승인 {item.get('token')}"))
    if actual != expected and actual.lower() not in APPROVAL_WORDS:
        print('TELEGRAM_APPROVE_REFUSED: approval text is neither a plain approval nor the exact token phrase')
        print('expected_plain', '승인')
        print('expected_tokened', expected)
        print('actual', actual)
        return 2
    item['telegram_reply_to_message_id'] = str(args.reply_to_message_id)
    return promote_telegram_item(project_root, registry, item, args, args.approved_text, args.approval_message_id or None)


def review_assets(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    re_resolve_asset_requests(project_root)
    queue_data = refresh_queue(project_root)
    card = project_root / 'docs/production/director_cards/asset_review.md'
    dashboard = project_root / 'docs/production/director_dashboard.html'
    write_text(card, render_asset_review_markdown(project_root, queue_data))
    write_text(dashboard, render_dashboard_html(project_root, queue_data))
    counts = queue_data.get('counts', {})
    print('Asset Review Console')
    print(f'Project: {project_title(project_root)}')
    print(f'review_items {counts.get("review_items", 0)}')
    print(f'generation_items {counts.get("generation_items", 0)}')
    for item in queue_data.get('review_items', []) or []:
        print('asset', item.get('asset_id'), item.get('asset_type'))
        for idx, candidate in enumerate(item.get('candidate_matches', []) or [], start=1):
            print('candidate', idx, candidate.get('metadata_path'))
            print('approve command', approve_command(project_root, item, candidate, idx))
    print('review_card', card)
    print('dashboard', dashboard)
    return 0


def preview(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    scene_id = slugify(args.scene_id)
    screenshot = Path(args.screenshot).resolve()
    try:
        require_under(screenshot, project_root / 'docs/production/screenshots', 'preview screenshot')
    except ValueError as exc:
        print(f'PREVIEW_REFUSED: {exc}')
        return 2
    if not screenshot.exists():
        print(f'PREVIEW_FAILED: screenshot not found: {screenshot}')
        return 1
    card = project_root / 'docs/production/director_cards' / f'{scene_id}_preview.md'
    lines = [
        f'# RenPy Preview: {scene_id}',
        '',
        f'Project: {project_title(project_root)}',
        f'Screenshot: `{screenshot}`',
        f'Note: {args.note or ""}',
        '',
        '## Next director choices',
        '1. Approve scene direction.',
        '2. Request dialogue/tone changes.',
        '3. Review asset candidates.',
        '4. Continue to the next scene.',
    ]
    write_text(card, '\n'.join(lines).rstrip() + '\n')
    # Refresh dashboard screenshot gallery without changing queue state.
    queue_data = load_json(project_root / 'docs/production/owner_review_queue.json', default={'review_items': [], 'generation_items': [], 'blocked_items': [], 'counts': {}})
    write_text(project_root / 'docs/production/director_dashboard.html', render_dashboard_html(project_root, queue_data))
    print('Preview Registered')
    print('scene', scene_id)
    print('screenshot', screenshot)
    print('preview_card', card)
    print('dashboard', project_root / 'docs/production/director_dashboard.html')
    return 0


def approve_candidate(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    if not args.approved:
        print('APPROVE_REFUSED: missing --approved explicit owner approval flag')
        return 2
    metadata_path = Path(args.metadata).resolve()
    try:
        require_under(metadata_path, project_root, 'metadata outside project root')
    except ValueError as exc:
        print(f'APPROVE_REFUSED: {exc}')
        return 2
    promote_args = [
        str(metadata_path),
        '--project-root', str(project_root),
        '--asset-id', args.asset_id,
        '--renpy-name', args.renpy_name,
        '--approved',
    ]
    if args.asset_type:
        promote_args.extend(['--asset-type', args.asset_type])
    if args.character_id:
        promote_args.extend(['--character-id', args.character_id])
    if args.dest_dir:
        promote_args.extend(['--dest-dir', args.dest_dir])
    if args.filename:
        promote_args.extend(['--filename', args.filename])
    for scene in args.scene_usage:
        promote_args.extend(['--scene-usage', scene])
    if args.qa_report:
        promote_args.extend(['--qa-report', args.qa_report])
    if args.force_overwrite:
        promote_args.append('--force-overwrite')
    if args.replace_existing:
        promote_args.append('--replace-existing')
    rc = promote_asset_main(promote_args)
    if rc != 0:
        return rc
    re_resolve_asset_requests(project_root)
    queue_data = refresh_queue(project_root)
    write_text(project_root / 'docs/production/director_dashboard.html', render_dashboard_html(project_root, queue_data))
    verify = subprocess.run(
        [sys.executable, str(TOOLS / 'verify_vn_automation_runtime.py'), '--project-root', str(project_root), '--skip-comfyui', '--skip-renpy-lint'],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    print('Candidate Approved And Promoted')
    print(f'Project: {project_title(project_root)}')
    print('verify_exit', verify.returncode)
    print(verify.stdout.rstrip())
    if verify.stderr:
        print(verify.stderr.rstrip())
    return verify.returncode


def new_scene(args: argparse.Namespace) -> int:
    project_root = director_project_root(args)
    try:
        vault = contract_vault(project_root, args.vault)
        assets = [parse_asset(raw) for raw in args.asset]
    except ValueError as exc:
        print(f'DIRECTOR_REFUSED: {exc}')
        return 2

    scene_id = slugify(args.scene_id)
    title = args.title or scene_id.replace('_', ' ').title()
    note = vault / 'Scenes' / f'{scene_id}.md'
    draft = project_root / 'game/scripts' / f'{scene_id}.rpy' if args.playable_placeholder else None
    try:
        require_under(note, vault, 'Obsidian scene note')
        if draft:
            require_under(draft, project_root / 'game', 'RenPy scene draft')
    except ValueError as exc:
        print(f'DIRECTOR_REFUSED: {exc}')
        return 2
    protected_existing = [path for path in [note, draft] if path and path.exists()]
    if protected_existing and not args.force:
        print('DIRECTOR_REFUSED: scene output already exists; use --force to overwrite derived scene files')
        for path in protected_existing:
            print('already exists', path)
        return 2
    write_text(note, render_scene_note(scene_id, title, args.summary, args.goal, assets, args.choice))

    if draft:
        write_text(draft, render_placeholder_rpy(scene_id, title, args.summary, args.goal, args.choice))

    summary_path = project_root / 'docs/automation/obsidian_scene_asset_request_batch.json'
    sync_data = sync_notes(project_root, vault, f'Scenes/{scene_id}.md', summary_path)
    queue_data = refresh_queue(project_root)
    card = project_root / 'docs/production/director_cards' / f'{scene_id}.md'
    write_text(card, render_director_card(project_root, scene_id, title, note, draft, queue_data))

    scene_count = len(sync_data.get('scenes', []))
    print('Scene Draft Ready')
    print('')
    print(f'Project: {project_title(project_root)}')
    print(f'Scene: {scene_id}')
    print('')
    print('Created:')
    print(f'[OK] Obsidian scene note: {note}')
    if draft:
        print(f"[OK] Ren'Py placeholder draft: {draft}")
    else:
        print("[ ] Ren'Py placeholder draft: skipped")
    print(f'[OK] Asset request sync scenes: {scene_count}')
    print(f'[OK] Owner review queue: {project_root / "docs/production/owner_review_queue.md"}')
    print(f'[OK] Director card: {card}')
    print('')
    print('Required assets:')
    for asset in assets:
        print(f"- {asset['asset_type']}: {asset['asset_id']} | {asset['description']}")
    print('')
    print('Review status:')
    counts = queue_data.get('counts', {})
    print(f'[!] Asset approval needed: {counts.get("review_items", 0) + counts.get("generation_items", 0) + counts.get("blocked_items", 0)}')
    print(f'[!] Generation items: {counts.get("generation_items", 0)}')
    print('')
    print('Next director choices:')
    print('1. Generate/review asset candidates')
    print('2. Play placeholder and request tone changes')
    print('3. Approve asset candidate for promotion')
    print('4. Run vn-auto verify --skip-comfyui --skip-renpy-lint')
    print('5. Continue to the next scene')
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Director-facing UX console for supervised VN production.')
    sub = parser.add_subparsers(dest='command', required=True)

    def add_project(parser_obj: argparse.ArgumentParser) -> None:
        parser_obj.add_argument('--project-root', required=True)
        parser_obj.add_argument('--contract', default=None)

    status_parser = sub.add_parser('status', help='Show project-agnostic production dashboard.')
    add_project(status_parser)
    status_parser.set_defaults(func=status)

    scene_parser = sub.add_parser('new-scene', help='Create a supervised scene note, optional placeholder draft, and approval cards.')
    add_project(scene_parser)
    scene_parser.add_argument('--vault', default=None)
    scene_parser.add_argument('--scene-id', required=True)
    scene_parser.add_argument('--title', default='')
    scene_parser.add_argument('--summary', default='')
    scene_parser.add_argument('--goal', default='')
    scene_parser.add_argument('--choice', action='append', default=[])
    scene_parser.add_argument('--asset', action='append', default=[], help='type:asset_id|description. Repeatable.')
    scene_parser.add_argument('--playable-placeholder', action='store_true')
    scene_parser.add_argument('--force', action='store_true', help='Overwrite existing scene note/placeholder draft for this scene_id.')
    scene_parser.set_defaults(func=new_scene)

    review_parser = sub.add_parser('review-assets', help='Build director asset candidate cards and static local HTML dashboard.')
    add_project(review_parser)
    review_parser.set_defaults(func=review_assets)

    preview_parser = sub.add_parser('preview', help='Register a RenPy screenshot/preview evidence card for a scene.')
    add_project(preview_parser)
    preview_parser.add_argument('--scene-id', required=True)
    preview_parser.add_argument('--screenshot', required=True)
    preview_parser.add_argument('--note', default='')
    preview_parser.set_defaults(func=preview)

    telegram_review_parser = sub.add_parser('telegram-review', help='Prepare tokened Telegram approval registry and review card.')
    add_project(telegram_review_parser)
    telegram_review_parser.set_defaults(func=telegram_review)

    telegram_approve_parser = sub.add_parser('telegram-approve', help='Consume an exact tokened Telegram approval phrase and promote the candidate.')
    add_project(telegram_approve_parser)
    telegram_approve_parser.add_argument('--token', required=True)
    telegram_approve_parser.add_argument('--approved-text', required=True)
    telegram_approve_parser.add_argument('--message-id', default='')
    telegram_approve_parser.add_argument('--qa-report', default='')
    telegram_approve_parser.add_argument('--character-id', default='')
    telegram_approve_parser.add_argument('--dest-dir', default='')
    telegram_approve_parser.add_argument('--filename', default='')
    telegram_approve_parser.add_argument('--force-overwrite', action='store_true')
    telegram_approve_parser.add_argument('--replace-existing', action='store_true')
    telegram_approve_parser.add_argument('--approved', action='store_true')
    telegram_approve_parser.set_defaults(func=telegram_approve)

    bind_parser = sub.add_parser('telegram-bind-message', help='Bind a pending token to the Telegram review message_id that displayed the candidate.')
    add_project(bind_parser)
    bind_parser.add_argument('--token', required=True)
    bind_parser.add_argument('--message-id', required=True)
    bind_parser.add_argument('--chat-id', default='')
    bind_parser.set_defaults(func=telegram_bind_message)

    approve_msg_parser = sub.add_parser('telegram-approve-message', help='Approve by reply_to_message_id, allowing plain approval text after a candidate message is bound.')
    add_project(approve_msg_parser)
    approve_msg_parser.add_argument('--reply-to-message-id', required=True)
    approve_msg_parser.add_argument('--approved-text', required=True)
    approve_msg_parser.add_argument('--approval-message-id', default='')
    approve_msg_parser.add_argument('--qa-report', default='')
    approve_msg_parser.add_argument('--character-id', default='')
    approve_msg_parser.add_argument('--dest-dir', default='')
    approve_msg_parser.add_argument('--filename', default='')
    approve_msg_parser.add_argument('--force-overwrite', action='store_true')
    approve_msg_parser.add_argument('--replace-existing', action='store_true')
    approve_msg_parser.add_argument('--approved', action='store_true')
    approve_msg_parser.set_defaults(func=telegram_approve_message)

    approve_parser = sub.add_parser('approve-candidate', help='Promote an explicitly approved candidate and refresh review queues.')
    add_project(approve_parser)
    approve_parser.add_argument('--metadata', required=True)
    approve_parser.add_argument('--asset-id', required=True)
    approve_parser.add_argument('--renpy-name', required=True)
    approve_parser.add_argument('--asset-type', default='')
    approve_parser.add_argument('--character-id', default='')
    approve_parser.add_argument('--dest-dir', default='')
    approve_parser.add_argument('--filename', default='')
    approve_parser.add_argument('--scene-usage', action='append', default=[])
    approve_parser.add_argument('--qa-report', default='')
    approve_parser.add_argument('--force-overwrite', action='store_true')
    approve_parser.add_argument('--replace-existing', action='store_true')
    approve_parser.add_argument('--approved', action='store_true')
    approve_parser.set_defaults(func=approve_candidate)
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
