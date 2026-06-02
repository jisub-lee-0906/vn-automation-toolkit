from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

RUNTIME_JUNK_NAMES = {
    '.pytest_cache',
    '__pycache__',
    'cache',
    'saves',
}
RUNTIME_JUNK_SUFFIXES = {'.rpyc', '.rpymc', '.pyc'}
RUNTIME_JUNK_FILES = {
    'log.txt',
    'errors.txt',
    'files.txt',
    'image_cache.txt',
    'save_dump.txt',
    'traceback.txt',
    'dialogue.tab',
    'dialogue.txt',
    'strings.json',
}

SCREENSHOT_RE = re.compile(r'^Screenshot:\s*`([^`]+)`\s*$', re.MULTILINE)


def relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def classify(path: str) -> str:
    p = path.replace('\\', '/').lstrip('./')
    name = Path(p).name
    parts = set(Path(p).parts)
    suffix = Path(p).suffix.lower()

    if name in RUNTIME_JUNK_FILES or suffix in RUNTIME_JUNK_SUFFIXES:
        return 'runtime_junk'
    if parts & RUNTIME_JUNK_NAMES:
        return 'runtime_junk'
    if p.startswith('docs/automation/generation_runs/') or p.startswith('docs/automation/generated_candidates/'):
        return 'generated_staging'
    if p.startswith('docs/automation/qa_reports/'):
        return 'qa_reports'
    if p.startswith('docs/production/screenshots/'):
        return 'production_screenshots'
    if p.startswith('docs/production/director_cards/') or p == 'docs/production/director_dashboard.html':
        return 'director_evidence'
    if p.startswith('docs/production/promotions/'):
        return 'promotion_records'
    if p.startswith('game/images/') or p.startswith('game/audio/') or p == 'game/data/asset_manifest.json':
        return 'approved_game_assets'
    if p.startswith('tools/') or p.startswith('tests/') or p.startswith('vn_automation/') or p == 'pyproject.toml':
        return 'automation_code'
    if p.startswith('docs/automation/') and (p.endswith('.md') or p.endswith('.json')):
        return 'automation_docs'
    if p.startswith('docs/production/asset_requests/') or p in {'docs/production/owner_review_queue.json', 'docs/production/owner_review_queue.md'}:
        return 'production_sidecars'
    return 'other'


def git_status(project_root: Path) -> list[dict[str, str]]:
    try:
        proc = subprocess.run(
            ['git', 'status', '--porcelain=v1', '-z'],
            cwd=project_root,
            text=False,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []
    raw = proc.stdout.split(b'\0')
    entries: list[dict[str, str]] = []
    i = 0
    while i < len(raw):
        item = raw[i]
        i += 1
        if not item:
            continue
        text = item.decode('utf-8', errors='replace')
        status = text[:2]
        path = text[3:]
        if status.startswith('R') or status.startswith('C'):
            if i < len(raw) and raw[i]:
                old_path = raw[i].decode('utf-8', errors='replace')
                i += 1
                path = f'{old_path} -> {path}'
        entries.append({'status': status, 'path': path, 'category': classify(path)})
    return entries


def scan_runtime_junk(project_root: Path) -> list[str]:
    findings: list[str] = []
    candidates = [
        project_root / 'log.txt',
        project_root / 'errors.txt',
        project_root / 'traceback.txt',
        project_root / '.pytest_cache',
        project_root / 'game/cache',
        project_root / 'game/saves',
    ]
    for path in candidates:
        if path.exists():
            findings.append(relpath(path, project_root))
    for suffix in RUNTIME_JUNK_SUFFIXES:
        for path in (project_root / 'game').rglob(f'*{suffix}') if (project_root / 'game').exists() else []:
            findings.append(relpath(path, project_root))
    return sorted(set(findings))


def check_preview_cards(project_root: Path) -> list[dict[str, Any]]:
    card_dir = project_root / 'docs/production/director_cards'
    if not card_dir.exists():
        return []
    checks: list[dict[str, Any]] = []
    for card in sorted(card_dir.glob('*_preview.md')):
        text = card.read_text(encoding='utf-8')
        match = SCREENSHOT_RE.search(text)
        if not match:
            checks.append({'card': relpath(card, project_root), 'status': 'missing_screenshot_field', 'screenshot': None})
            continue
        raw = match.group(1)
        screenshot = Path(raw)
        if not screenshot.is_absolute():
            screenshot = (project_root / screenshot).resolve()
        checks.append({
            'card': relpath(card, project_root),
            'status': 'pass' if screenshot.exists() else 'missing_screenshot_file',
            'screenshot': str(screenshot),
        })
    return checks


def summarize_status(entries: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        key = entry['category']
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_audit(project_root: Path) -> dict[str, Any]:
    entries = git_status(project_root)
    preview_checks = check_preview_cards(project_root)
    runtime_findings = scan_runtime_junk(project_root)
    visible_runtime_entries = [entry for entry in entries if entry['category'] == 'runtime_junk']
    missing_previews = [item for item in preview_checks if item['status'] != 'pass']
    return {
        'tool': 'audit_vn_artifacts',
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'project_root': str(project_root),
        'git_status_available': bool(entries),
        'git_status_counts': summarize_status(entries),
        'git_status_entries': entries,
        'runtime_junk_findings': runtime_findings,
        'visible_runtime_junk_git_entries': visible_runtime_entries,
        'preview_checks': preview_checks,
        'missing_preview_evidence': missing_previews,
        'recommended_policy': {
            'commit': [
                'automation_code',
                'automation_docs',
                'production_sidecars',
                'promotion_records',
                'approved_game_assets',
                'director_evidence needed for review',
            ],
            'treat_as_artifacts_or_prune': [
                'generated_staging rejected or superseded candidates',
                'large generation_runs unless needed for reproducibility',
                'temporary screenshots not referenced by preview cards',
            ],
            'never_commit': ['runtime_junk'],
        },
    }


def render_text(audit: dict[str, Any]) -> str:
    lines = [
        'VN_ARTIFACT_AUDIT',
        f"project_root {audit['project_root']}",
        f"git_status_available {str(audit['git_status_available']).lower()}",
        '',
        'Git status categories:',
    ]
    counts = audit['git_status_counts']
    if counts:
        for key, value in counts.items():
            lines.append(f'- {key}: {value}')
    else:
        lines.append('- none')
    lines.extend(['', 'Runtime junk found on disk:'])
    if audit['runtime_junk_findings']:
        for item in audit['runtime_junk_findings'][:20]:
            lines.append(f'- {item}')
        if len(audit['runtime_junk_findings']) > 20:
            lines.append(f"- ... plus {len(audit['runtime_junk_findings']) - 20} more")
    else:
        lines.append('- none')
    lines.extend(['', 'Preview evidence checks:'])
    if audit['preview_checks']:
        for item in audit['preview_checks']:
            lines.append(f"- {item['status']}: {item['card']} -> {item.get('screenshot')}")
    else:
        lines.append('- no *_preview.md cards found')
    lines.extend(['', 'Policy summary:', '- Commit approved game assets, production sidecars, promotion records, director cards/previews, automation code/docs.', '- Keep runtime junk out of git.', '- Treat generated candidates/runs as review artifacts; keep only reproducibility-critical runs or move superseded candidates out of the repo.'])
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Audit VN automation artifacts, preview evidence, and git-status categories.')
    parser.add_argument('--project-root', default='.', help='RenPy/VN project root')
    parser.add_argument('--json-out', help='Optional JSON report path')
    parser.add_argument('--strict', action='store_true', help='Fail if preview evidence is missing or runtime junk appears in git status')
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    audit = build_audit(project_root)
    if args.json_out:
        out = Path(args.json_out)
        if not out.is_absolute():
            out = project_root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(render_text(audit), end='')
    if args.strict and (audit['missing_preview_evidence'] or audit['visible_runtime_junk_git_entries']):
        print('AUDIT_FAILED')
        return 1
    print('AUDIT_PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
