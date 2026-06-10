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


def make_readability_project(tmp_path: Path) -> Path:
    project = tmp_path / 'renpy' / 'readable_title'
    obs = tmp_path / 'obsidian' / 'readable_title' / 'VN'
    (project / 'game').mkdir(parents=True)
    (project / 'game/script.rpy').write_text(
        'label start:\n    jump scene_001_opening\n\n'
        'label scene_001_opening:\n    jump scene_002_contract\n\n'
        'label scene_002_contract:\n    jump scene_056_true_end_probe\n\n'
        'label scene_056_true_end_probe:\n    return\n',
        encoding='utf-8',
    )
    write_json(project / 'docs/automation/project_contract.json', {
        'game_title': 'Readable Title',
        'game_slug': 'readable_title',
        'renpy_game_dir': (project / 'game').as_posix(),
        'manifest_path': (project / 'game/data/asset_manifest.json').as_posix(),
        'obsidian_vault': (tmp_path / 'obsidian' / 'readable_title').as_posix(),
        'obsidian_project_root': obs.as_posix(),
        'obsidian_scenes_glob': 'Scenes/*.md',
        'workflow_pack_root': (tmp_path / 'workflows').as_posix(),
        'workflow_index': (tmp_path / 'workflows' / 'WORKFLOW_INDEX.json').as_posix(),
    })
    write_json(project / 'game/data/asset_manifest.json', {'version': '1.0.0', 'assets': []})
    for d in ['Automation', 'Scenes', 'Characters', 'Canon']:
        (obs / d).mkdir(parents=True, exist_ok=True)
    (obs / 'Automation/current_state_20260610.md').write_text(
        '---\ntype: automation_state\ngame_slug: readable_title\nstatus: active\nsource_status: true_end_route_verified_polished\n---\n\n'
        '# Current State — Active Resume 2026-06-10\n\n'
        '## Current Playable State\n\n'
        '- Playable range: `start` / Scene 001 through Scene 068 TRUE END.\n'
        '- Latest implemented route node: [[scene_056_to_068_true_end_arc]].\n\n'
        '## Current Narrative Position\n\nsource trace → final record choice → TRUE END card\n\n'
        '## Character State at Current End\n\n### Serena\n- Writes her own next scene.\n\n### Lucian\n- Record partner, not savior.\n',
        encoding='utf-8',
    )
    (obs / 'Automation/dashboard.md').write_text(
        '---\ntype: automation_dashboard\ngame_slug: readable_title\nstatus: active\n---\n\n'
        '# Dashboard\n\n- Current status: `true_end_route_verified_polished`.\n'
        '- Compact active state: [[current_state_20260610]].\n'
        '- Ending arc: [[scene_056_to_068_true_end_arc]].\n'
        '- Latest QA: `global_story_polish_20260610/final_report.md`\n',
        encoding='utf-8',
    )
    (obs / 'Scenes/scene_001_opening.md').write_text(
        '---\ntype: scene\ngame_slug: readable_title\nscene_id: scene_001_opening\nstatus: implemented_verified\nrenpy_label: scene_001_opening\n---\n\n'
        '# Scene 001 — Opening\n\n## Purpose\nEstablish the death sentence and hostile record.\n\n## Beats\n1. Possession.\n2. Record pressure.\n',
        encoding='utf-8',
    )
    (obs / 'Scenes/scene_002_contract.md').write_text(
        '---\ntype: scene\ngame_slug: readable_title\nscene_id: scene_002_contract\nstatus: implemented_verified\nrenpy_label: scene_002_contract\n---\n\n'
        '# Scene 002 — Contract\n\n## Purpose\nTurn execution threat into a survival contract.\n\n## Beats\n1. Lucian watches.\n2. Serena bargains.\n',
        encoding='utf-8',
    )
    (obs / 'Scenes/scene_056_to_068_true_end_arc.md').write_text(
        '---\ntype: scene_arc\ngame_slug: readable_title\nstatus: implemented_verified\n---\n\n'
        '# Scene 056–068 — True End Arc\n\n## Purpose\nComplete the route.\n\n## Key Beats\n\n| Scene | Beat |\n| --- | --- |\n| 056 | Source pressure |\n| 068 | TRUE END card |\n',
        encoding='utf-8',
    )
    (obs / 'Characters/serena.md').write_text(
        '---\ntype: character\ngame_slug: readable_title\ncharacter_id: serena\nstatus: active\n---\n\n'
        '# Serena\n\n## Current Emotional State\n- Turns the bad ending record into evidence.\n',
        encoding='utf-8',
    )
    (obs / 'Characters/lucian.md').write_text(
        '---\ntype: character\ngame_slug: readable_title\ncharacter_id: lucian\nstatus: active\n---\n\n'
        '# Lucian\n\n## Current Emotional State\n- Becomes a questioner / record partner.\n',
        encoding='utf-8',
    )
    (obs / 'Canon/route_seed_tracker.md').write_text(
        '---\ntype: canon\ngame_slug: readable_title\nstatus: active\n---\n\n'
        '# Route Seed Tracker\n\n## Contract Blade Seeds\nLucian threat/contract seeds.\n\n## Red Author Seeds\nSystem and record manipulation seeds.\n\n## Villainess Crown Seeds\nReputation as weapon seeds.\n',
        encoding='utf-8',
    )
    (obs / 'Canon/epic_narrative_bible.md').write_text(
        '---\ntype: canon\ngame_slug: readable_title\nstatus: active\n---\n\n# Bible\n\n## Current Implemented Baseline — 2026-06-10\nScene 001–068 common Act 2 TRUE END route.\n',
        encoding='utf-8',
    )
    return project


def test_obsidian_summarize_writes_readable_index_notes(tmp_path: Path):
    project = make_readability_project(tmp_path)
    proc = run_cli('obsidian-summarize', '--project-root', str(project), '--write')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'OBSIDIAN_SUMMARIZE_COMPLETED' in proc.stdout
    obs = tmp_path / 'obsidian/readable_title/VN'
    expected = [
        obs / 'Automation/reader_entrypoint.md',
        obs / 'Timeline/common_act2_true_end_timeline.md',
        obs / 'Canon/true_end_seed_payoff_map.md',
        obs / 'Continuity/emotional_arc_serena_lucian_true_end.md',
    ]
    for path in expected:
        assert path.exists(), path
        text = path.read_text(encoding='utf-8')
        assert 'current_state_20260610' in text
        assert 'scene_056_to_068_true_end_arc' in text
    assert 'Contract Blade' in (obs / 'Canon/true_end_seed_payoff_map.md').read_text(encoding='utf-8')
    assert 'Serena' in (obs / 'Continuity/emotional_arc_serena_lucian_true_end.md').read_text(encoding='utf-8')


def test_obsidian_audit_requires_readable_indexes(tmp_path: Path):
    project = make_readability_project(tmp_path)
    fail = run_cli('obsidian-audit', '--project-root', str(project), '--require-readable-indexes')
    assert fail.returncode == 1
    assert 'readable index missing' in fail.stdout + fail.stderr

    ok_sum = run_cli('obsidian-summarize', '--project-root', str(project), '--write')
    assert ok_sum.returncode == 0, ok_sum.stdout + ok_sum.stderr
    ok = run_cli('obsidian-audit', '--project-root', str(project), '--require-readable-indexes')
    assert ok.returncode == 0, ok.stdout + ok.stderr
    data = json.loads((project / 'docs/automation/obsidian_active_state_audit.json').read_text(encoding='utf-8'))
    assert data['readable_index_audit']['status'] == 'PASS'
