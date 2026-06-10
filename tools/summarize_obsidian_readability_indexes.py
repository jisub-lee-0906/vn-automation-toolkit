from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from audit_obsidian_active_state import collect_notes, find_active_current_states, parse_frontmatter, read_text  # noqa: E402
from vn_product_config import build_project_paths, require_under, save_json  # noqa: E402


READABLE_INDEXES = {
    'reader_entrypoint': 'Automation/reader_entrypoint.md',
    'timeline': 'Timeline/common_act2_true_end_timeline.md',
    'seed_payoff': 'Canon/true_end_seed_payoff_map.md',
    'emotional_arc': 'Continuity/emotional_arc_serena_lucian_true_end.md',
}


def wiki(path: str) -> str:
    return f'[[{Path(path).stem}]]'


def first_existing(root: Path, rels: list[str]) -> Path | None:
    for rel in rels:
        p = root / rel
        if p.exists():
            return p
    return None


def compact_text(text: str, *, limit: int = 150) -> str:
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'\[\[[^\]]+\]\]', lambda m: m.group(0), text)
    text = ' '.join(line.strip('- |').strip() for line in text.splitlines() if line.strip())
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ''
    # Prefer the first sentence/phrase when available; avoid mid-word truncation.
    sentence = re.split(r'(?<=[.!?。])\s+', text, maxsplit=1)[0]
    if 30 <= len(sentence) <= limit:
        return sentence
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:')
    return cut + '…'


def extract_scene_rows(obsidian_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in sorted((obsidian_root / 'Scenes').glob('scene_*.md')):
        stem = p.stem
        match = re.match(r'scene_(\d{3})(?:_to_(\d{3}))?', stem)
        if not match:
            continue
        text = read_text(p)
        title = next((line.lstrip('# ').strip() for line in text.splitlines() if line.startswith('#')), stem)
        purpose = ''
        pm = re.search(r'## Purpose\s*\n+(.*?)(?:\n## |\Z)', text, re.S)
        if pm:
            purpose = compact_text(pm.group(1), limit=155)
        rows.append({
            'num': int(match.group(1)),
            'to': int(match.group(2)) if match.group(2) else None,
            'stem': stem,
            'title': title,
            'purpose': purpose,
        })
    return rows


def block_for_scene(num: int) -> str:
    if num <= 2:
        return 'Opening death-sentence contract'
    if num <= 4:
        return 'First investigation / source tracing'
    if num <= 12:
        return 'First public trap and survival contract closure'
    if num <= 23:
        return 'Act 2 route pressure escalation'
    if num <= 42:
        return 'Public confrontation / private cost / record duel'
    if num <= 55:
        return 'Source-handler chase and method reversal'
    if num <= 68:
        return 'TRUE END record reversal'
    return 'Probe / non-canon automation support'


def build_timeline(obsidian_root: Path, game_slug: str, active_state: Path, ending_arc: Path | None) -> str:
    rows = extract_scene_rows(obsidian_root)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row['num'] == 999:
            continue
        groups.setdefault(block_for_scene(row['num']), []).append(row)
    lines = [
        '---',
        'type: readable_index',
        f'game_slug: {game_slug}',
        'index_kind: timeline',
        'status: active',
        f'generated_at: {datetime.now().isoformat(timespec="seconds")}',
        '---',
        '',
        '# Common Act 2 TRUE END Timeline',
        '',
        f'Source state: [[{active_state.stem}]].',
        f'Ending arc: [[{ending_arc.stem if ending_arc else "scene_056_to_068_true_end_arc"}]].',
        '',
        'This is a reader-facing compression of the implemented route. It is not a replacement for detailed scene notes; it is the first-pass map for humans and RAG retrieval.',
        '',
    ]
    for idx, (name, items) in enumerate(groups.items(), 1):
        start = items[0]['num']; end = items[-1]['to'] or items[-1]['num']
        lines += [f'## Block {idx} — {name}', '', f'Scenes: `{start:03d}`–`{end:03d}`', '']
        for item in items[:8]:
            target = item['stem']
            purpose = item['purpose'] or item['title']
            lines.append(f'- [[{target}]] — {purpose}')
        if len(items) > 8:
            lines.append(f'- … {len(items) - 8} additional scene notes in this block.')
        lines.append('')
    lines += [
        '## Current Reading Order',
        '',
        f'1. [[{active_state.stem}]]',
        f'2. [[{ending_arc.stem if ending_arc else "scene_056_to_068_true_end_arc"}]]',
        '3. [[true_end_seed_payoff_map]]',
        '4. [[emotional_arc_serena_lucian_true_end]]',
        '',
    ]
    return '\n'.join(lines)


def build_seed_payoff(obsidian_root: Path, game_slug: str, active_state: Path, ending_arc: Path | None) -> str:
    tracker = first_existing(obsidian_root, ['Canon/route_seed_tracker.md'])
    tracker_text = read_text(tracker) if tracker else ''
    seed_names = []
    for name in ['Contract Blade', 'Red Author', 'Villainess Crown', 'Lifespan Condition', 'Black Scribe']:
        if name in tracker_text or name in ['Lifespan Condition', 'Black Scribe']:
            seed_names.append(name)
    all_routes_arc_exists = (obsidian_root / 'Scenes/scene_069_to_073_all_routes_completion.md').exists()
    if all_routes_arc_exists:
        payoff = {
            'Contract Blade': ('Scene 001–012 contract pressure', 'Scene 070', 'completed: Lucian remains questioner / contract blade, not savior', 'closed as route ending; future polish may deepen romance, not replace endpoint'),
            'Red Author': ('system witness / record-law pressure', 'Scene 071', 'completed: red system demoted from fate to edit history', 'closed as route ending; system-origin expansion remains optional lore'),
            'Villainess Crown': ('public fear / reputation weaponization', 'Scene 072', 'completed: villainess reputation becomes protective political power', 'closed as route ending; politics route may expand consequences'),
            'Lifespan Condition': ('opening death sentence / 시한부 condition', 'Scene 063 / 067 / 073', 'reframed and preserved as evidence rather than erased', 'open survival pressure remains sequel/polish material'),
            'Black Scribe': ('source trace / upper-room method', 'Scene 059–065 / 073', 'exposed and absorbed into all-routes-complete evidence chain', 'upper-room conspiracy can expand only after current route set'),
        }
    else:
        payoff = {
            'Contract Blade': ('Scene 001–012 contract pressure', 'Scene 058 / 064 / 068', 'partially paid off as Lucian becomes questioner / record partner', 'future trust/romance route expansion'),
            'Red Author': ('system witness / record-law pressure', 'Scene 063–066', 'paid off through badend-title reversal', 'system origin expansion'),
            'Villainess Crown': ('public fear / reputation weaponization', 'Scene 061–065', 'paid off as 악녀 기록 becomes evidence', 'political power route expansion'),
            'Lifespan Condition': ('opening death sentence / 시한부 condition', 'Scene 063 / 067', 'reframed, not erased', 'open survival sequel pressure'),
            'Black Scribe': ('source trace / upper-room method', 'Scene 059–065', 'exposed as method and record actor', 'upper-room conspiracy expansion'),
        }
    lines = [
        '---', 'type: readable_index', f'game_slug: {game_slug}', 'index_kind: seed_payoff', 'status: active', f'generated_at: {datetime.now().isoformat(timespec="seconds")}', '---', '',
        '# TRUE END Seed Payoff Map', '',
        f'Source state: [[{active_state.stem}]].',
        f'Ending arc: [[{ending_arc.stem if ending_arc else "scene_056_to_068_true_end_arc"}]].',
        'Tracker source: [[route_seed_tracker]].', '',
        '| Seed | Planted / tracked in | Paid off in TRUE END | Current status | Future route potential |',
        '| --- | --- | --- | --- | --- |',
    ]
    for name in seed_names:
        planted, paid, status, future = payoff[name]
        lines.append(f'| {name} | {planted} | {paid} | {status} | {future} |')
    lines += ['', '## Notes', '', '- This map is generated as a readable index from current state, ending arc, and route seed notes.', '- Treat nuanced literary wording as reviewable; link/coverage/currentness are mechanically audited.', '']
    return '\n'.join(lines)


def section_excerpt(path: Path | None, heading: str) -> str:
    if not path or not path.exists():
        return ''
    text = read_text(path)
    m = re.search(rf'## {re.escape(heading)}\s*\n+(.*?)(?:\n## |\Z)', text, re.S)
    if not m:
        return ''
    return '\n'.join(line for line in m.group(1).splitlines() if line.strip())[:900]


def build_emotional_arc(obsidian_root: Path, game_slug: str, active_state: Path, ending_arc: Path | None) -> str:
    serena = first_existing(obsidian_root, ['Characters/serena.md'])
    lucian = first_existing(obsidian_root, ['Characters/lucian.md'])
    lines = [
        '---', 'type: readable_index', f'game_slug: {game_slug}', 'index_kind: emotional_arc', 'status: active', f'generated_at: {datetime.now().isoformat(timespec="seconds")}', '---', '',
        '# Emotional Arc — Serena / Lucian TRUE END', '',
        f'Source state: [[{active_state.stem}]].',
        f'Ending arc: [[{ending_arc.stem if ending_arc else "scene_056_to_068_true_end_arc"}]].',
        'Character sources: [[serena]], [[lucian]].', '',
        '## Arc Compression', '',
        '| Phase | Scenes | Serena | Lucian | Relationship function |',
        '| --- | --- | --- | --- | --- |',
        '| Threat contract | 001–002 | Condemned villainess reading the death record as evidence. | Executor / watcher. | Survival bargain under distrust. |',
        '| Investigation pressure | 003–012 | Uses 악녀 reputation as leverage. | Treats her claims as dangerous but usable evidence. | Witnessing begins before trust. |',
        '| Public record war | 013–055 | Stops asking to be believed; forces records to answer. | Shifts from surveillance to formal questioning. | Tactical partnership with emotional cost. |',
        '| TRUE END reversal | 056–068 | Turns badend title / 시한부 condition into evidence and next-scene authorship. | Record partner, not savior. | Agency preserved: he asks beside her, not for her. |',
        '',
        '## Current Serena Note Excerpt', '',
        section_excerpt(serena, 'Current Emotional State') or '- See [[serena]].', '',
        '## Current Lucian Note Excerpt', '',
        section_excerpt(lucian, 'Current Emotional State') or '- See [[lucian]].', '',
        '## Practical Writing Rule', '',
        '- Do not write Lucian as the rescuer who solves Serena’s ending for her.',
        '- Do write Serena as the person who weaponizes records, reputation, and the false ending title into proof.',
        '- Relationship polish should preserve the “questioner / record partner” endpoint.', '',
    ]
    return '\n'.join(lines)


def build_reader_entrypoint(obsidian_root: Path, game_slug: str, active_state: Path, ending_arc: Path | None) -> str:
    lines = [
        '---', 'type: readable_index', f'game_slug: {game_slug}', 'index_kind: reader_entrypoint', 'status: active', f'generated_at: {datetime.now().isoformat(timespec="seconds")}', '---', '',
        f'# Reader Entrypoint — {game_slug}', '',
        'Use this page when opening the vault cold. It separates current story flow from production logs.', '',
        '## Current Production State', '',
        f'1. [[{active_state.stem}]]',
        f'2. [[{ending_arc.stem if ending_arc else "scene_056_to_068_true_end_arc"}]]',
        '3. [[dashboard]]', '',
        '## Story / Readability Maps', '',
        '1. [[common_act2_true_end_timeline]]',
        '2. [[true_end_seed_payoff_map]]',
        '3. [[emotional_arc_serena_lucian_true_end]]', '',
        '## Canon / Character Sources', '',
        '1. [[gameplay_direction]]',
        '2. [[epic_narrative_bible]]',
        '3. [[route_seed_tracker]]',
        '4. [[serena]]',
        '5. [[lucian]]', '',
        '## Implementation Proof', '',
        '- Latest validation reports are linked from [[current_state_20260610]] and [[dashboard]].',
        '- Machine audit: `docs/automation/obsidian_active_state_audit.json` in the Ren\'Py project.', '',
    ]
    return '\n'.join(lines)


def generate_indexes(project_root: Path, obsidian_root: Path, *, write: bool) -> dict[str, Any]:
    notes = collect_notes(obsidian_root)
    active_states = find_active_current_states(notes)
    if len(active_states) != 1:
        raise SystemExit(f'expected exactly one active automation_state note, found {len(active_states)}')
    active_state = active_states[0]
    ending_arc = first_existing(obsidian_root, ['Scenes/scene_056_to_068_true_end_arc.md'])
    game_slug = parse_frontmatter(read_text(active_state)).get('game_slug') or project_root.name
    payloads = {
        'Automation/reader_entrypoint.md': build_reader_entrypoint(obsidian_root, game_slug, active_state, ending_arc),
        'Timeline/common_act2_true_end_timeline.md': build_timeline(obsidian_root, game_slug, active_state, ending_arc),
        'Canon/true_end_seed_payoff_map.md': build_seed_payoff(obsidian_root, game_slug, active_state, ending_arc),
        'Continuity/emotional_arc_serena_lucian_true_end.md': build_emotional_arc(obsidian_root, game_slug, active_state, ending_arc),
    }
    written: list[str] = []
    for rel, text in payloads.items():
        path = (obsidian_root / rel).resolve()
        require_under(path, obsidian_root, 'readable index output')
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            written.append(rel)
    return {'status': 'PASS', 'generated': list(payloads), 'written': written, 'active_current_state': str(active_state), 'ending_arc': str(ending_arc) if ending_arc else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generate reader-facing Obsidian readability indexes for a VN title.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--write', action='store_true', help='Write generated markdown notes. Without this, only reports planned outputs.')
    parser.add_argument('--out', default='docs/automation/obsidian_readability_indexes.json')
    args = parser.parse_args(argv)
    paths = build_project_paths(args.project_root, args.contract)
    raw_root = paths.contract.get('obsidian_project_root') or paths.contract.get('obsidian_vault')
    if not raw_root:
        print('OBSIDIAN_SUMMARIZE_FAILED')
        print('- obsidian_project_root missing in project_contract.json')
        return 1
    obsidian_root = Path(raw_root).expanduser().resolve()
    vault_raw = paths.contract.get('obsidian_vault')
    if vault_raw:
        require_under(obsidian_root, Path(str(vault_raw)).expanduser().resolve(), 'obsidian_project_root')
    try:
        result = generate_indexes(paths.project_root, obsidian_root, write=args.write)
    except Exception as exc:
        print('OBSIDIAN_SUMMARIZE_FAILED')
        print('-', exc)
        return 1
    out_path = Path(args.out).expanduser()
    if not out_path.is_absolute():
        out_path = paths.project_root / out_path
    out_path = out_path.resolve()
    require_under(out_path, paths.project_root, 'obsidian summarize output')
    save_json(out_path, result)
    print('OBSIDIAN_SUMMARIZE_COMPLETED')
    for rel in result['generated']:
        print(('wrote' if rel in result['written'] else 'planned'), rel)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
