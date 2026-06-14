#!/usr/bin/env python3
"""Extract machine-readable VN asset requests from an Obsidian scene note.

This is intentionally conservative: it only turns explicit `## Required Assets`
checklist lines into executable asset request JSON. Asset IDs mentioned elsewhere
are recorded as suggestions, not auto-queued.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TYPE_TO_WORKFLOW = {
    'background': 'scene_background',
    'bg': 'scene_background',
    'event_cg': 'scene_event_cg',
    'cg': 'scene_event_cg',
    'prop': 'scene_prop_cg',
    'ui': 'ui_system_alert_frame',
    'system_ui': 'ui_system_alert_frame',
    'bgm': 'audio_bgm_with_sfx',
    'music': 'audio_bgm_with_sfx',
    'sfx': 'audio_bgm_with_sfx',
    'audio_sfx': 'audio_bgm_with_sfx',
    'char_base': 'char_base',
    'char_alpha': 'char_alpha',
    'char_expression': 'char_expression',
}

REQUIRED_LINE_RE = re.compile(r'^\s*-\s*\[(?P<mark>[ xX])\]\s*(?P<kind>[A-Za-z0-9_ -]+)\s*:\s*(?P<rest>.+?)\s*$')
BACKTICK_ID_RE = re.compile(r'`(?P<asset_id>(?:event_cg|bg|background|prop|ui|sfx|bgm|char)_[A-Za-z0-9_\-]+)`')

INFERENCE_RULES = [
    {
        'workflow_id': 'scene_event_cg',
        'asset_type': 'event_cg',
        'keywords': ['confronts', 'confrontation', '대치', '마주', 'public trap', '함정'],
        'reason': 'scene language suggests a visual event beat',
    },
    {
        'workflow_id': 'ui_system_alert_frame',
        'asset_type': 'ui',
        'keywords': ['system alert', 'red system', '알림', '시스템'],
        'reason': 'scene language mentions system alert UI',
    },
    {
        'workflow_id': 'audio_bgm_with_sfx',
        'asset_type': 'sfx',
        'keywords': ['crack', 'glass', 'door slam', 'footstep', '깨지는', '유리', '군화'],
        'reason': 'scene language suggests a short sound effect',
    },
    {
        'workflow_id': 'audio_bgm_with_sfx',
        'asset_type': 'bgm',
        'keywords': ['waltz', 'low strings', 'piano', 'music', 'bgm', '왈츠', '현악', '피아노'],
        'reason': 'scene language suggests background music',
    },
]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith('---'):
        return {}, text
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}, text
    raw = parts[1]
    body = parts[2]
    meta: dict[str, Any] = {}
    for line in raw.splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        key = key.strip()
        value = value.strip()
        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1].strip()
            meta[key] = [v.strip().strip('"\'') for v in inner.split(',') if v.strip()]
        else:
            meta[key] = value.strip('"\'')
    return meta, body


def slug_kind(kind: str) -> str:
    return kind.strip().lower().replace(' ', '_').replace('-', '_')


def workflow_for_kind(kind: str) -> str | None:
    normalized = slug_kind(kind)
    return TYPE_TO_WORKFLOW.get(normalized)


def extract_section(body: str, heading: str) -> str:
    pattern = re.compile(rf'^##\s+{re.escape(heading)}\s*$', re.MULTILINE | re.IGNORECASE)
    match = pattern.search(body)
    if not match:
        return ''
    start = match.end()
    next_heading = re.search(r'^##\s+', body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    return body[start:end]


def parse_required_assets(section: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requests: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for line_no, line in enumerate(section.splitlines(), start=1):
        match = REQUIRED_LINE_RE.match(line)
        if not match:
            continue
        kind = slug_kind(match.group('kind'))
        rest = match.group('rest').strip()
        if '|' in rest:
            asset_id, description = [part.strip() for part in rest.split('|', 1)]
        else:
            parts = rest.split(None, 1)
            asset_id = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ''
        status = 'already_satisfied_or_approved' if match.group('mark').lower() == 'x' else 'requested'
        workflow_id = workflow_for_kind(kind)
        if workflow_id is None:
            unresolved.append({
                'asset_type': kind,
                'workflow_id': None,
                'asset_id': asset_id.strip('`'),
                'description': description,
                'status': 'unresolved_required_asset_kind_not_executable',
                'source_line': line.strip(),
                'section_line_index': line_no,
            })
            continue
        requests.append({
            'asset_type': kind,
            'workflow_id': workflow_id,
            'asset_id': asset_id.strip('`'),
            'description': description,
            'status': status,
            'source_line': line.strip(),
            'section_line_index': line_no,
        })
    return requests, unresolved


def extract_suggestions(body: str, request_ids: set[str]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in BACKTICK_ID_RE.finditer(body):
        asset_id = match.group('asset_id')
        if asset_id in seen:
            continue
        seen.add(asset_id)
        suggestion = {
            'asset_id': asset_id,
            'already_in_required_assets': asset_id in request_ids,
            'context': body[max(0, match.start()-80): match.end()+80].replace('\n', ' ').strip(),
        }
        suggestions.append(suggestion)
    return suggestions


def extract_review_only_inferred_suggestions(body: str, scene_id: str, existing_workflows: set[str]) -> list[dict[str, Any]]:
    text = body.lower()
    suggestions: list[dict[str, Any]] = []
    for rule in INFERENCE_RULES:
        workflow_id = rule['workflow_id']
        if workflow_id in existing_workflows:
            continue
        matched = [keyword for keyword in rule['keywords'] if keyword.lower() in text]
        if not matched:
            continue
        suggestions.append({
            'asset_type': rule['asset_type'],
            'workflow_id': workflow_id,
            'asset_id_hint': f"{scene_id}_{rule['asset_type']}_candidate",
            'status': 'review_only_inferred_not_requested',
            'matched_keywords': matched,
            'reason': rule['reason'],
            'safety_note': 'Inference is a suggestion only; user/Hermes must promote it to an explicit request before generation.',
        })
    return suggestions


def extract_scene_asset_requests(scene_note: Path) -> dict[str, Any]:
    text = scene_note.read_text(encoding='utf-8')
    meta, body = parse_frontmatter(text)
    required_section = extract_section(body, 'Required Assets')
    requests, unresolved = parse_required_assets(required_section)
    request_ids = {item['asset_id'] for item in requests}
    suggestions = extract_suggestions(body, request_ids)
    scene_id = meta.get('scene_id') or scene_note.stem
    existing_workflows = {item['workflow_id'] for item in requests}
    inferred = extract_review_only_inferred_suggestions(body, scene_id, existing_workflows)
    return {
        'schema_version': 1,
        'source_scene_note': str(scene_note),
        'game_slug': meta.get('game_slug'),
        'scene_id': scene_id,
        'renpy_label': meta.get('renpy_label'),
        'characters': meta.get('characters') or [],
        'locations': meta.get('locations') or [],
        'scene_status': meta.get('status'),
        'extraction_policy': 'explicit_required_assets_only; backtick ids outside required assets are suggestions only',
        'asset_requests': requests,
        'unresolved_required_asset_mentions': unresolved,
        'candidate_suggestions': suggestions,
        'review_only_inferred_suggestions': inferred,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Extract asset requests from an Obsidian VN scene note.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--scene-note', help='Single Obsidian scene note to extract')
    group.add_argument('--scenes-root', help='Directory of Obsidian scene notes to extract')
    parser.add_argument('--output', required=True, help='Output JSON file for single mode, or output directory for scenes-root mode')
    args = parser.parse_args()
    output = Path(args.output)

    if args.scene_note:
        scene_note = Path(args.scene_note)
        data = extract_scene_asset_requests(scene_note)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(output), 'asset_request_count': len(data['asset_requests']), 'suggestion_count': len(data['candidate_suggestions'])}, ensure_ascii=False))
        return 0

    scenes_root = Path(args.scenes_root)
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    total_requests = 0
    total_suggestions = 0
    total_inferred = 0
    total_unresolved = 0
    for scene_note in sorted(scenes_root.glob('*.md')):
        data = extract_scene_asset_requests(scene_note)
        out_file = output / f"{data['scene_id']}_asset_requests.json"
        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        request_count = len(data['asset_requests'])
        suggestion_count = len(data['candidate_suggestions'])
        inferred_count = len(data.get('review_only_inferred_suggestions') or [])
        unresolved_count = len(data.get('unresolved_required_asset_mentions') or [])
        total_requests += request_count
        total_suggestions += suggestion_count
        total_inferred += inferred_count
        total_unresolved += unresolved_count
        entries.append({
            'scene_id': data['scene_id'],
            'source_scene_note': data['source_scene_note'],
            'output': str(out_file),
            'asset_request_count': request_count,
            'suggestion_count': suggestion_count,
            'review_only_inferred_suggestion_count': inferred_count,
            'unresolved_required_asset_count': unresolved_count,
            'scene_status': data.get('scene_status'),
        })
    index = {
        'schema_version': 1,
        'scenes_root': str(scenes_root),
        'output_dir': str(output),
        'scene_count': len(entries),
        'total_asset_requests': total_requests,
        'total_candidate_suggestions': total_suggestions,
        'total_review_only_inferred_suggestions': total_inferred,
        'total_unresolved_required_asset_mentions': total_unresolved,
        'scenes': entries,
    }
    index_path = output / 'asset_request_index.json'
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output_dir': str(output), 'index': str(index_path), 'scene_count': len(entries), 'total_asset_requests': total_requests, 'total_candidate_suggestions': total_suggestions, 'total_review_only_inferred_suggestions': total_inferred, 'total_unresolved_required_asset_mentions': total_unresolved}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
