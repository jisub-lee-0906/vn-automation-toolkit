from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/qa_asset_file.py'


def run_qa(*args: str):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def test_missing_file_fails(tmp_path: Path):
    report = tmp_path / 'missing.json'
    proc = run_qa(str(tmp_path / 'missing.png'), '--asset-type', 'event_cg', '--json-out', str(report))
    assert proc.returncode == 1
    assert 'status fail' in proc.stdout
    data = json.loads(report.read_text(encoding='utf-8'))
    assert data['status'] == 'fail'
    assert any('file_missing' in e for e in data['errors'])


def test_empty_file_fails(tmp_path: Path):
    empty = tmp_path / 'empty.png'
    empty.write_bytes(b'')
    proc = run_qa(str(empty), '--asset-type', 'event_cg')
    assert proc.returncode == 1
    assert 'file_empty' in proc.stdout


def test_valid_png_reports_dimensions_and_alpha(tmp_path: Path):
    # 1x1 RGBA PNG, base64-decoded bytes kept inline to avoid Pillow dependency.
    png = tmp_path / 'pixel_rgba.png'
    png.write_bytes(bytes.fromhex(
        '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
        '0000000a49444154789c6360000000020001e221bc330000000049454e44ae426082'
    ))
    report = tmp_path / 'qa.json'
    proc = run_qa(str(png), '--asset-type', 'event_cg', '--json-out', str(report))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(report.read_text(encoding='utf-8'))
    assert data['status'] == 'pass'
    assert data['width'] == 1
    assert data['height'] == 1
    assert data['has_alpha'] is True
