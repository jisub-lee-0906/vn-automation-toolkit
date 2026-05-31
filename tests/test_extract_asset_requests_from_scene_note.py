from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/extract_asset_requests_from_scene_note.py'
FIXTURE = ROOT / 'docs/automation/test_fixtures/sample_scene_note.md'


def test_extract_required_assets_from_fixture(tmp_path: Path):
    out = tmp_path / 'sample_scene.asset_requests.json'
    proc = subprocess.run([
        sys.executable, str(SCRIPT), str(FIXTURE), '--scene-id', 'sample_scene', '--out', str(out)
    ], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'count 2' in proc.stdout
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['scene_id'] == 'sample_scene'
    assert len(data['asset_requests']) == 2
    assert data['asset_requests'][0]['asset_id'] == 'bg_classroom_evening'
    assert data['asset_requests'][0]['asset_type'] == 'background'
    assert data['asset_requests'][1]['required'] is True
