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

from vn_product_config import build_project_paths, require_under, save_json  # noqa: E402

FRONTMATTER_RE = re.compile(r'^---\s*\n(?P<body>.*?)\n---\s*\n', re.S)
FRONTMATTER_FIELD_RE = re.compile(r'^(?P<key>[A-Za-z0-9_ -]+)\s*:\s*(?P<value>.*?)\s*$', re.M)
WIKILINK_RE = re.compile(r'\[\[(?P<target>[^\]|#]+)')
STALE_LATEST_QA_RE = re.compile(r'narrative_density_0_2|scene0?1[0-9]|scene0?2[0-9]|scene0?3[0-9]|scene0?4[0-9]|scene0?5[0-5]', re.I)
STALE_NEXT_RE = re.compile(r'Next recommended scene:\s*\[\[scene_0(0[1-9]|[1-4][0-9]|5[0-5])', re.I)
DASHBOARD_BLOCK_START = '<!-- VN_AUTO_ACTIVE_STATE_START -->'
DASHBOARD_BLOCK_END = '<!-- VN_AUTO_ACTIVE_STATE_END -->'
LABEL_RE = re.compile(r'^label\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:')


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig')


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for item in FRONTMATTER_FIELD_RE.finditer(match.group('body')):
        fields[item.group('key').strip()] = item.group('value').strip().strip('"\'')
    return fields


def note_stem_from_link(link: str) -> str:
    return link.strip().split('|', 1)[0].split('#', 1)[0].strip()


def collect_notes(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*.md') if p.is_file())


def find_active_current_states(notes: list[Path]) -> list[Path]:
    active = []
    for note in notes:
        text = read_text(note)
        fm = parse_frontmatter(text)
        if fm.get('type') == 'automation_state' and fm.get('status') == 'active':
            active.append(note)
    return active


def relative_or_str(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)



def extract_script_labels(project_root: Path) -> set[str]:
    labels: set[str] = set()
    game_dir = project_root / 'game'
    if not game_dir.exists():
        return labels
    for script in sorted(game_dir.rglob('*.rpy')):
        for line in read_text(script).splitlines():
            match = LABEL_RE.match(line.strip())
            if match:
                labels.add(match.group(1))
    return labels


def scene_note_covers_label(note_stem: str, label: str) -> bool:
    if note_stem == label or note_stem.startswith(label + '_'):
        return True
    note_num = re.match(r'scene_(\d{3})', note_stem)
    label_num = re.match(r'scene_(\d{3})', label)
    if note_num and label_num and note_num.group(1) == label_num.group(1):
        return True
    m = re.match(r'scene_(\d{3})_to_(\d{3})', note_stem)
    lm = re.match(r'scene_(\d{3})', label)
    if m and lm:
        num = int(lm.group(1))
        return int(m.group(1)) <= num <= int(m.group(2))
    return False


def audit_scene_label_notes(project_root: Path, obsidian_root: Path) -> dict[str, Any]:
    all_labels = extract_script_labels(project_root)
    script_scene_labels = {label for label in all_labels if label.startswith('scene_')}
    scene_dir = obsidian_root / 'Scenes'
    notes = sorted(scene_dir.glob('*.md')) if scene_dir.exists() else []
    note_stems = {p.stem for p in notes}
    note_meta = {p.stem: parse_frontmatter(read_text(p)) for p in notes}

    def note_has_live_renpy_label(stem: str) -> bool:
        renpy_label = note_meta.get(stem, {}).get('renpy_label')
        return bool(renpy_label and renpy_label in all_labels)

    stale_notes = sorted(
        stem for stem in note_stems
        if stem.startswith('scene_')
        and not note_has_live_renpy_label(stem)
        and not any(scene_note_covers_label(stem, label) for label in script_scene_labels)
    )
    labels_without_notes = sorted(label for label in script_scene_labels if not any(scene_note_covers_label(stem, label) for stem in note_stems))
    return {
        'script_label_count': len(all_labels),
        'script_scene_label_count': len(script_scene_labels),
        'scene_note_count': len(note_stems),
        'stale_scene_notes': stale_notes[:50],
        'labels_without_notes': labels_without_notes[:50],
        'labels_without_notes_count': len(labels_without_notes),
    }


def build_dashboard_active_block(active_state: Path, source_status: str, latest_report: str | None = None) -> str:
    latest_line = f'- Latest QA: `{latest_report}`' if latest_report else '- Latest QA: see active current_state / latest validation reports.'
    return '\n'.join([
        DASHBOARD_BLOCK_START,
        '## Active Resume / Machine Snapshot',
        '',
        f'- Current status: `{source_status or "active"}`.',
        f'- Compact active state: [[{active_state.stem}]].',
        latest_line,
        '- Next recommended step: run `obsidian-audit` after any baseline-changing work before final signoff.',
        DASHBOARD_BLOCK_END,
        '',
    ])


def update_dashboard_active_block(dashboard: Path, active_state: Path, source_status: str, latest_report: str | None = None) -> bool:
    text = read_text(dashboard) if dashboard.exists() else '# Automation Dashboard\n\n'
    block = build_dashboard_active_block(active_state, source_status, latest_report)
    if DASHBOARD_BLOCK_START in text and DASHBOARD_BLOCK_END in text:
        pattern = re.compile(re.escape(DASHBOARD_BLOCK_START) + r'.*?' + re.escape(DASHBOARD_BLOCK_END) + r'\n?', re.S)
        new_text = pattern.sub(block, text, count=1)
    else:
        lines = text.splitlines()
        insert_at = 0
        if lines and lines[0].startswith('---'):
            for i in range(1, len(lines)):
                if lines[i].startswith('---'):
                    insert_at = i + 1
                    break
        elif lines and lines[0].startswith('#'):
            insert_at = 1
        new_lines = lines[:insert_at] + [''] + block.rstrip('\n').splitlines() + [''] + lines[insert_at:]
        new_text = '\n'.join(new_lines).rstrip() + '\n'
    changed = new_text != text
    if changed:
        dashboard.parent.mkdir(parents=True, exist_ok=True)
        dashboard.write_text(new_text, encoding='utf-8')
    return changed


def validate_writeback_manifest(manifest_path: Path, obsidian_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not manifest_path.exists():
        return {'status': 'FAIL', 'errors': [f'writeback_manifest missing: {manifest_path}']}
    try:
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as exc:
        return {'status': 'FAIL', 'errors': [f'writeback_manifest invalid JSON: {exc}']}
    required = data.get('required') or []
    if not isinstance(required, list) or not required:
        errors.append('writeback_manifest.required must be a non-empty list')
        required = []
    for idx, item in enumerate(required):
        if not isinstance(item, dict):
            errors.append(f'required[{idx}] must be object')
            continue
        category = item.get('category')
        path_raw = item.get('path')
        if not category or not path_raw:
            errors.append(f'required[{idx}] missing category/path')
            continue
        path = Path(str(path_raw)).expanduser()
        if not path.is_absolute():
            path = obsidian_root / path
        path = path.resolve()
        try:
            require_under(path, obsidian_root, f'writeback {category}')
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.exists():
            errors.append(f'writeback {category} path missing: {path}')
    return {'status': 'PASS' if not errors else 'FAIL', 'errors': errors, 'required_count': len(required)}



READABLE_INDEX_REQUIREMENTS = {
    'reader_entrypoint': 'Automation/reader_entrypoint.md',
    'timeline': 'Timeline/common_act2_true_end_timeline.md',
    'seed_payoff': 'Canon/true_end_seed_payoff_map.md',
    'emotional_arc': 'Continuity/emotional_arc_serena_lucian_true_end.md',
}


def validate_readable_indexes(obsidian_root: Path, active_state: Path | None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    active_stem = active_state.stem if active_state else None
    required_links = ['scene_056_to_068_true_end_arc']
    if active_stem:
        required_links.append(active_stem)
    for key, rel in READABLE_INDEX_REQUIREMENTS.items():
        path = obsidian_root / rel
        if not path.exists():
            errors.append(f'readable index missing: {rel}')
            continue
        text = read_text(path)
        fm = parse_frontmatter(text)
        if fm.get('type') != 'readable_index':
            warnings.append(f'readable index {rel} frontmatter type is not readable_index')
        if fm.get('status') != 'active':
            warnings.append(f'readable index {rel} is not marked active')
        for target in required_links:
            if target not in text:
                errors.append(f'readable index {rel} does not link/reference {target}')
    return {
        'status': 'PASS' if not errors else 'FAIL',
        'errors': errors,
        'warnings': warnings,
        'required': READABLE_INDEX_REQUIREMENTS,
    }


def audit_obsidian(project_root: Path, obsidian_root: Path, *, writeback_manifest: Path | None = None, require_writeback_manifest: bool = False, require_readable_indexes: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    obsidian_root = obsidian_root.resolve()
    if not obsidian_root.exists():
        return {
            'status': 'FAIL',
            'errors': [f'obsidian_project_root missing: {obsidian_root}'],
            'warnings': [],
            'obsidian_project_root': str(obsidian_root),
        }
    notes = collect_notes(obsidian_root)
    dashboard = obsidian_root / 'Automation' / 'dashboard.md'
    active_states = find_active_current_states(notes)
    active_state = active_states[0] if len(active_states) == 1 else None

    if len(active_states) != 1:
        errors.append(f'expected exactly one active automation_state note, found {len(active_states)}')

    dashboard_text = ''
    if not dashboard.exists():
        errors.append('missing Automation/dashboard.md')
    else:
        dashboard_text = read_text(dashboard)
        dashboard_fm = parse_frontmatter(dashboard_text)
        if dashboard_fm.get('type') != 'automation_dashboard':
            warnings.append('dashboard frontmatter type is not automation_dashboard')

    if active_state and dashboard_text:
        active_stem = active_state.stem
        if f'[[{active_stem}]]' not in dashboard_text:
            errors.append(f'dashboard does not link active current_state [[{active_stem}]]')
        active_text = read_text(active_state)
        active_fm = parse_frontmatter(active_text)
        source_status = active_fm.get('source_status') or ''
        if source_status and source_status not in dashboard_text:
            warnings.append(f'dashboard does not mention active source_status {source_status}')
        for required in ['Latest implemented route node', 'Current Playable State']:
            if required not in active_text:
                warnings.append(f'active current_state missing section/field: {required}')

    if dashboard_text:
        if 'Current state: [[current_state_20260607]]' in dashboard_text or 'Compact active state: [[current_state_20260607]]' in dashboard_text:
            errors.append('dashboard points to superseded current_state_20260607')
        latest_lines = [line for line in dashboard_text.splitlines() if 'Latest QA' in line or 'Latest screenshot QA' in line]
        for line in latest_lines:
            if STALE_LATEST_QA_RE.search(line) and 'global_story_polish' not in line and 'true_end' not in line:
                errors.append(f'dashboard latest QA appears stale: {line.strip()}')
        for m in STALE_NEXT_RE.finditer(dashboard_text):
            errors.append(f'dashboard active next recommended scene appears stale: {m.group(0)}')

    superseded_active = []
    for note in notes:
        text = read_text(note)
        fm = parse_frontmatter(text)
        if fm.get('status') == 'active' and 'Superseded:' in text:
            superseded_active.append(note)
    if superseded_active:
        errors.append('notes marked active but text says superseded: ' + ', '.join(relative_or_str(p, obsidian_root) for p in superseded_active))

    scene055 = obsidian_root / 'Scenes' / 'scene_055_source_trace_or_enemy_method_reversal.md'
    if scene055.exists():
        t = read_text(scene055)
        stale_hooks = [
            'act2_editor_desk_pressure_window',
            'act2_authority_blank_pressure_window',
            'act2_sponsor_claim_source_pressure_window',
        ]
        found = [hook for hook in stale_hooks if hook in t]
        if found:
            errors.append('scene055 contains stale next-hook names: ' + ', '.join(found))

    scene_label_audit = audit_scene_label_notes(project_root, obsidian_root)
    if scene_label_audit['stale_scene_notes']:
        errors.append('scene notes without matching script labels/range: ' + ', '.join(scene_label_audit['stale_scene_notes'][:10]))
    if scene_label_audit['labels_without_notes_count']:
        warnings.append(f"script scene labels without Obsidian note coverage: {scene_label_audit['labels_without_notes_count']}")

    readable_index_audit = None
    if require_readable_indexes:
        readable_index_audit = validate_readable_indexes(obsidian_root, active_state)
        if readable_index_audit['status'] != 'PASS':
            errors.extend(readable_index_audit['errors'])
        warnings.extend(readable_index_audit.get('warnings', []))

    writeback_audit = None
    if writeback_manifest or require_writeback_manifest:
        manifest_path = writeback_manifest or (project_root / 'docs/automation/writeback_manifest.json')
        writeback_audit = validate_writeback_manifest(manifest_path, obsidian_root)
        if writeback_audit['status'] != 'PASS':
            errors.extend(writeback_audit['errors'])

    result = {
        'tool': 'obsidian_active_state_audit',
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'project_root': str(project_root),
        'obsidian_project_root': str(obsidian_root),
        'status': 'PASS' if not errors else 'FAIL',
        'errors': errors,
        'warnings': warnings,
        'note_count': len(notes),
        'active_current_state': str(active_state) if active_state else None,
        'dashboard': str(dashboard) if dashboard.exists() else None,
        'scene_label_audit': scene_label_audit,
        'writeback_manifest_audit': writeback_audit,
        'readable_index_audit': readable_index_audit,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Audit Obsidian active-state semantic consistency for a VN title.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--out', '--json-out', dest='out', default='docs/automation/obsidian_active_state_audit.json', help='Project-confined JSON report path. --json-out is kept as a compatibility alias used by other report commands.')
    parser.add_argument('--update-dashboard-active-block', action='store_true', help='Insert/update a machine-managed active-state block in Automation/dashboard.md.')
    parser.add_argument('--latest-report', default=None, help='Optional latest QA/report path to write into the dashboard active block.')
    parser.add_argument('--writeback-manifest', default=None, help='Optional writeback manifest JSON to validate.')
    parser.add_argument('--require-writeback-manifest', action='store_true', help='Require docs/automation/writeback_manifest.json or --writeback-manifest to pass.')
    parser.add_argument('--require-readable-indexes', action='store_true', help='Require reader-facing Obsidian timeline/seed/emotional-arc index notes to exist and link current state.')
    args = parser.parse_args(argv)

    paths = build_project_paths(args.project_root, args.contract)
    raw_root = paths.contract.get('obsidian_project_root') or paths.contract.get('obsidian_vault')
    if not raw_root:
        print('OBSIDIAN_ACTIVE_STATE_AUDIT_FAILED')
        print('- obsidian_project_root missing in project_contract.json')
        return 1
    obsidian_root = Path(raw_root).expanduser().resolve()
    vault_raw = paths.contract.get('obsidian_vault')
    if vault_raw:
        try:
            require_under(obsidian_root, Path(str(vault_raw)).expanduser().resolve(), 'obsidian_project_root')
        except ValueError as exc:
            print('OBSIDIAN_ACTIVE_STATE_AUDIT_FAILED')
            print('-', exc)
            return 2

    wb_path = Path(args.writeback_manifest).expanduser().resolve() if args.writeback_manifest else None
    result = audit_obsidian(paths.project_root, obsidian_root, writeback_manifest=wb_path, require_writeback_manifest=args.require_writeback_manifest, require_readable_indexes=args.require_readable_indexes)
    if args.update_dashboard_active_block and result.get('active_current_state'):
        active_path = Path(str(result['active_current_state']))
        active_fm = parse_frontmatter(read_text(active_path))
        dashboard_path = obsidian_root / 'Automation' / 'dashboard.md'
        changed = update_dashboard_active_block(dashboard_path, active_path, active_fm.get('source_status') or active_fm.get('status') or 'active', args.latest_report)
        result['dashboard_active_block_updated'] = changed
        # Re-audit after writing the block so the saved report reflects final state.
        result = audit_obsidian(paths.project_root, obsidian_root, writeback_manifest=wb_path, require_writeback_manifest=args.require_writeback_manifest, require_readable_indexes=args.require_readable_indexes)
        result['dashboard_active_block_updated'] = changed
    out_path = Path(args.out).expanduser()
    if not out_path.is_absolute():
        out_path = paths.project_root / out_path
    out_path = out_path.resolve()
    try:
        require_under(out_path, paths.project_root, 'obsidian audit output')
    except ValueError as exc:
        print('OBSIDIAN_ACTIVE_STATE_AUDIT_REFUSED:', exc)
        return 2
    save_json(out_path, result)

    if result['status'] == 'PASS':
        print('OBSIDIAN_ACTIVE_STATE_AUDIT_PASSED')
    else:
        print('OBSIDIAN_ACTIVE_STATE_AUDIT_FAILED')
    print('active_current_state', result.get('active_current_state'))
    print('dashboard', result.get('dashboard'))
    for err in result['errors']:
        print('-', err)
    for warn in result['warnings']:
        print('WARN', warn)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
