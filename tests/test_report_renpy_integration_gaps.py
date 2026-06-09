from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/report_renpy_integration_gaps.py'


def test_report_contains_integrated_and_file_only_assets(tmp_path: Path):
    project = tmp_path / 'integration_gap_project'
    game = project / 'game'
    (game / 'images/backgrounds').mkdir(parents=True)
    (game / 'images/cgs').mkdir(parents=True)
    (game / 'data').mkdir(parents=True)
    (game / 'script.rpy').write_text(
        'image bg classroom_morning = "images/backgrounds/bg_classroom_morning.png"\n'
        'label start:\n    return\n',
        encoding='utf-8',
    )
    (game / 'images/backgrounds/bg_classroom_morning.png').write_bytes(b'fake png')
    (game / 'images/cgs/event_cg_seoha_auditorium_seed260529200_candidate01.png').write_bytes(b'fake png')
    manifest = {
        'version': '1.0.0',
        'assets': [
            {
                'asset_id': 'bg_classroom_morning',
                'asset_type': 'background',
                'renpy_name': 'bg classroom_morning',
                'promoted_path': 'images/backgrounds/bg_classroom_morning.png',
            },
            {
                'asset_id': 'event_cg_seoha_auditorium_seed260529200_candidate01',
                'asset_type': 'event_cg',
                'renpy_name': 'event cg seoha auditorium',
                'promoted_path': 'images/cgs/event_cg_seoha_auditorium_seed260529200_candidate01.png',
            },
        ],
    }
    (game / 'data/asset_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (project / 'docs/automation').mkdir(parents=True, exist_ok=True)
    (project / 'docs/automation/project_contract.json').write_text(json.dumps({'renpy_project_root': str(project), 'renpy_game_dir': str(game), 'manifest_path': str(game / 'data/asset_manifest.json')}), encoding='utf-8')

    out = project / 'docs/automation/report.json'
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), '--project-root', str(project), '--json-out', str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    by_id = {item['asset_id']: item for item in data['assets']}
    assert by_id['bg_classroom_morning']['status'] == 'integrated'
    assert by_id['event_cg_seoha_auditorium_seed260529200_candidate01']['status'] == 'file_only_not_declared'
    assert by_id['event_cg_seoha_auditorium_seed260529200_candidate01']['file_exists'] is True
