from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def make_obsidian_project(tmp_path: Path, *, stale_dashboard: bool = False, stale_active_state: bool = False) -> Path:
    project = tmp_path / 'renpy' / 'audit_title'
    obs_root = tmp_path / 'obsidian' / 'audit_title' / 'VN'
    (project / 'game').mkdir(parents=True)
    (project / 'game/script.rpy').write_text('label scene_056_probe:\n    return\n', encoding='utf-8')
    (obs_root / 'Automation').mkdir(parents=True)
    (obs_root / 'Scenes').mkdir(parents=True)
    write_json(project / 'docs/automation/project_contract.json', {
        'game_title': 'Audit Title',
        'game_slug': 'audit_title',
        'renpy_game_dir': (project / 'game').as_posix(),
        'manifest_path': (project / 'game/data/asset_manifest.json').as_posix(),
        'obsidian_vault': (tmp_path / 'obsidian' / 'audit_title').as_posix(),
        'obsidian_project_root': obs_root.as_posix(),
        'obsidian_scenes_glob': 'Scenes/*.md',
        'workflow_pack_root': (tmp_path / 'workflows').as_posix(),
        'workflow_index': (tmp_path / 'workflows' / 'WORKFLOW_INDEX.json').as_posix(),
    })
    write_json(project / 'game/data/asset_manifest.json', {'version': '1.0.0', 'assets': []})
    current = obs_root / 'Automation/current_state_20260610.md'
    current.write_text(
        '---\n'
        'type: automation_state\n'
        'game_slug: audit_title\n'
        f'status: {"superseded" if stale_active_state else "active"}\n'
        'source_status: true_end_route_verified_polished\n'
        '---\n\n'
        '# Current State — Active Resume 2026-06-10\n\n'
        '## Current Playable State\n\n'
        '- Playable range: `start` / Scene 001 through Scene 068 TRUE END.\n'
        '- Latest implemented route node: [[scene_056_to_068_true_end_arc]].\n'
        '- Next recommended step: optional manual click-through playtest or packaging/release refresh.\n',
        encoding='utf-8',
    )
    (obs_root / 'Automation/current_state_20260607.md').write_text(
        '---\n'
        'type: automation_state\n'
        'game_slug: audit_title\n'
        'status: superseded\n'
        'source_status: old_scene044\n'
        '---\n\n'
        '# Old State\n\n'
        '- Playable range: Scene 001–042.\n',
        encoding='utf-8',
    )
    dashboard_current = '[[current_state_20260607]]' if stale_dashboard else '[[current_state_20260610]]'
    dashboard_latest = 'scene016_report.md' if stale_dashboard else 'global_story_polish_20260610/final_report.md'
    (obs_root / 'Automation/dashboard.md').write_text(
        '---\n'
        'type: automation_dashboard\n'
        'game_slug: audit_title\n'
        'status: active\n'
        '---\n\n'
        '# Automation Dashboard\n\n'
        '## Active Resume / Completion Snapshot — 2026-06-10\n\n'
        '- Current status: `true_end_route_verified_polished`.\n'
        f'- Compact active state: {dashboard_current}.\n'
        '- Ending arc: [[scene_056_to_068_true_end_arc]].\n'
        f'- Latest QA: `{dashboard_latest}`\n'
        '- Next recommended step: manual click-through playtest or packaging/release refresh.\n',
        encoding='utf-8',
    )
    (obs_root / 'Scenes/scene_056_to_068_true_end_arc.md').write_text(
        '---\n'
        'type: scene_arc\n'
        'game_slug: audit_title\n'
        'status: implemented_verified\n'
        '---\n\n'
        '# Scene 056–068 — True End Arc\n\n'
        'TRUE END card.\n',
        encoding='utf-8',
    )
    return project


def test_obsidian_audit_passes_when_active_notes_are_consistent(tmp_path: Path):
    project = make_obsidian_project(tmp_path)
    proc = run_cli('obsidian-audit', '--project-root', str(project))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'OBSIDIAN_ACTIVE_STATE_AUDIT_PASSED' in proc.stdout
    report = project / 'docs/automation/obsidian_active_state_audit.json'
    assert report.exists()
    data = json.loads(report.read_text(encoding='utf-8'))
    assert data['status'] == 'PASS'
    assert data['active_current_state'].endswith('current_state_20260610.md')


def test_obsidian_audit_accepts_json_out_alias(tmp_path: Path):
    project = make_obsidian_project(tmp_path)
    out = project / 'docs/validation/obsidian_alias/report.json'
    proc = run_cli('obsidian-audit', '--project-root', str(project), '--json-out', str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['status'] == 'PASS'


def test_obsidian_audit_fails_on_stale_dashboard_current_state_link(tmp_path: Path):
    project = make_obsidian_project(tmp_path, stale_dashboard=True)
    proc = run_cli('obsidian-audit', '--project-root', str(project))
    assert proc.returncode == 1
    text = proc.stdout + proc.stderr
    assert 'OBSIDIAN_ACTIVE_STATE_AUDIT_FAILED' in text
    assert 'dashboard does not link active current_state' in text
    assert 'dashboard latest QA appears stale' in text


def test_obsidian_audit_fails_when_no_active_current_state_exists(tmp_path: Path):
    project = make_obsidian_project(tmp_path, stale_active_state=True)
    proc = run_cli('obsidian-audit', '--project-root', str(project))
    assert proc.returncode == 1
    text = proc.stdout + proc.stderr
    assert 'expected exactly one active automation_state note' in text


def test_obsidian_audit_updates_machine_managed_dashboard_block(tmp_path: Path):
    project = make_obsidian_project(tmp_path)
    proc = run_cli(
        'obsidian-audit', '--project-root', str(project),
        '--update-dashboard-active-block', '--latest-report', 'docs/validation/latest/final_report.md',
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    dashboard = tmp_path / 'obsidian/audit_title/VN/Automation/dashboard.md'
    text = dashboard.read_text(encoding='utf-8')
    assert '<!-- VN_AUTO_ACTIVE_STATE_START -->' in text
    assert '[[current_state_20260610]]' in text
    assert 'docs/validation/latest/final_report.md' in text


def test_obsidian_audit_fails_on_stale_scene_note_without_script_label(tmp_path: Path):
    project = make_obsidian_project(tmp_path)
    stale = tmp_path / 'obsidian/audit_title/VN/Scenes/scene_999_deleted.md'
    stale.write_text('---\ntype: scene\nstatus: active\n---\n\n# Deleted Scene\n', encoding='utf-8')
    proc = run_cli('obsidian-audit', '--project-root', str(project))
    assert proc.returncode == 1
    assert 'scene notes without matching script labels/range' in proc.stdout + proc.stderr


def test_obsidian_audit_requires_writeback_manifest_when_requested(tmp_path: Path):
    project = make_obsidian_project(tmp_path)
    missing = run_cli('obsidian-audit', '--project-root', str(project), '--require-writeback-manifest')
    assert missing.returncode == 1
    assert 'writeback_manifest missing' in missing.stdout + missing.stderr

    manifest = project / 'docs/automation/writeback_manifest.json'
    write_json(manifest, {
        'required': [
            {'category': 'dashboard', 'path': 'Automation/dashboard.md'},
            {'category': 'current_state', 'path': 'Automation/current_state_20260610.md'},
            {'category': 'scene_arc', 'path': 'Scenes/scene_056_to_068_true_end_arc.md'},
        ]
    })
    ok = run_cli('obsidian-audit', '--project-root', str(project), '--require-writeback-manifest')
    assert ok.returncode == 0, ok.stdout + ok.stderr
    data = json.loads((project / 'docs/automation/obsidian_active_state_audit.json').read_text(encoding='utf-8'))
    assert data['writeback_manifest_audit']['status'] == 'PASS'

