from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path = ROOT):
    return subprocess.run([sys.executable, '-m', 'vn_automation.cli', *args], cwd=cwd, text=True, capture_output=True)


def make_min_project(tmp_path: Path) -> Path:
    project = tmp_path / 'audit_title'
    (project / 'game').mkdir(parents=True)
    (project / 'docs/production/director_cards').mkdir(parents=True)
    (project / 'docs/production/screenshots').mkdir(parents=True)
    (project / 'docs/automation').mkdir(parents=True)
    (project / 'game/data').mkdir(parents=True)
    (project / 'game/data/asset_manifest.json').write_text(json.dumps({'version': '1.0.0', 'assets': []}), encoding='utf-8')
    (project / 'docs/automation/project_contract.json').write_text(json.dumps({'renpy_project_root': str(project), 'renpy_game_dir': str(project / 'game'), 'manifest_path': str(project / 'game/data/asset_manifest.json')}), encoding='utf-8')
    return project


def test_artifact_audit_passes_when_preview_screenshot_exists(tmp_path: Path):
    project = make_min_project(tmp_path)
    screenshot = project / 'docs/production/screenshots/opening.png'
    screenshot.write_bytes(b'fake screenshot')
    card = project / 'docs/production/director_cards/opening_preview.md'
    card.write_text(f'# Preview\n\nScreenshot: `{screenshot}`\n', encoding='utf-8')

    proc = run_cli('audit', '--project-root', str(project), '--strict')

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'VN_ARTIFACT_AUDIT' in proc.stdout
    assert 'pass: docs/production/director_cards/opening_preview.md' in proc.stdout
    assert 'AUDIT_PASSED' in proc.stdout


def test_artifact_audit_strict_fails_when_preview_screenshot_is_missing(tmp_path: Path):
    project = make_min_project(tmp_path)
    missing = project / 'docs/production/screenshots/missing.png'
    card = project / 'docs/production/director_cards/opening_preview.md'
    card.write_text(f'# Preview\n\nScreenshot: `{missing}`\n', encoding='utf-8')

    proc = run_cli('audit', '--project-root', str(project), '--strict')

    assert proc.returncode == 1
    assert 'missing_screenshot_file' in proc.stdout
    assert 'AUDIT_FAILED' in proc.stdout


def test_artifact_audit_reports_runtime_junk_without_failing_non_strict(tmp_path: Path):
    project = make_min_project(tmp_path)
    (project / 'game/cache').mkdir(parents=True)
    (project / 'log.txt').write_text('runtime log', encoding='utf-8')

    proc = run_cli('audit', '--project-root', str(project))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'Runtime junk found on disk:' in proc.stdout
    assert 'game/cache' in proc.stdout
    assert 'log.txt' in proc.stdout
    assert 'AUDIT_PASSED' in proc.stdout
