from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
ITEM_RE = re.compile(r'^\s*-\s+(.*)$')
CHECKBOX_RE = re.compile(r'^\[(?P<mark>[ xX])\]\s*(?P<body>.*)$')
KV_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_ -]*)\s*:\s*(.*?)\s*$')
INLINE_ASSET_RE = re.compile(r'^\s*(?P<asset_type>[A-Za-z_][A-Za-z0-9_ -]*)\s*:\s*(?P<rest>.*?)\s*$')


def parse_bool(value: str) -> Any:
    low = value.strip().lower()
    if low in {'true', 'yes', 'y', '1'}:
        return True
    if low in {'false', 'no', 'n', '0'}:
        return False
    return value.strip()


def normalize_key(key: str) -> str:
    return key.strip().lower().replace(' ', '_').replace('-', '_')


def required_assets_section(text: str) -> list[str]:
    lines = text.splitlines()
    start = None
    level = None
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and m.group(2).strip().lower() == 'required assets':
            start = i + 1
            level = len(m.group(1))
            break
    if start is None:
        return []
    out = []
    for line in lines[start:]:
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) <= level:
            break
        out.append(line)
    return out


def parse_inline_asset(rest: str) -> dict[str, Any] | None:
    """Parse Obsidian checklist shorthand: ``- [ ] type: asset_id | description``."""
    checkbox = CHECKBOX_RE.match(rest)
    required = True
    if checkbox:
        rest = checkbox.group('body').strip()
    inline = INLINE_ASSET_RE.match(rest)
    if not inline:
        return None
    asset_type = normalize_key(inline.group('asset_type'))
    value = inline.group('rest').strip()
    if not value:
        return None
    parts = [part.strip() for part in value.split('|', 1)]
    asset_id = parts[0]
    description = parts[1] if len(parts) > 1 else ''
    if not asset_id:
        return None
    return {
        'asset_type': asset_type,
        'asset_id': asset_id,
        'description': description,
        'required': required,
    }


def parse_required_assets(text: str) -> list[dict[str, Any]]:
    lines = required_assets_section(text)
    assets: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        item = ITEM_RE.match(line)
        if item:
            if current:
                assets.append(current)
            rest = item.group(1).strip()
            inline = parse_inline_asset(rest)
            if inline:
                current = inline
                continue
            current = {}
            if rest:
                m = KV_RE.match(rest)
                if m:
                    current[normalize_key(m.group(1))] = parse_bool(m.group(2))
                else:
                    current['description'] = rest
            continue
        if current is not None:
            m = KV_RE.match(line)
            if m:
                current[normalize_key(m.group(1))] = parse_bool(m.group(2))
    if current:
        assets.append(current)

    normalized = []
    for item in assets:
        asset_id = item.get('id') or item.get('asset_id')
        asset_type = item.get('type') or item.get('asset_type')
        if not asset_id or not asset_type:
            continue
        normalized.append({
            'asset_id': asset_id,
            'asset_type': asset_type,
            'description': item.get('description', ''),
            'required': bool(item.get('required', True)),
            'status': 'needs_manifest_lookup',
            'raw': item,
        })
    return normalized


def build_output(note: Path, scene_id: str) -> dict[str, Any]:
    text = note.read_text(encoding='utf-8-sig')
    return {
        'tool': 'extract_asset_requests_from_scene_note',
        'extracted_at': datetime.now().isoformat(timespec='seconds'),
        'scene_id': scene_id,
        'source_note': str(note),
        'asset_requests': parse_required_assets(text),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Extract explicit Required Assets from a scene note markdown file.')
    parser.add_argument('scene_note')
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)

    note = Path(args.scene_note)
    if not note.exists():
        print(f'EXTRACT_FAILED: missing scene note: {note}')
        return 1
    data = build_output(note, args.scene_id)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('EXTRACT_ASSET_REQUESTS')
    print('scene_id', args.scene_id)
    print('count', len(data['asset_requests']))
    for item in data['asset_requests']:
        print('asset', item.get('asset_id'), item.get('asset_type'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
