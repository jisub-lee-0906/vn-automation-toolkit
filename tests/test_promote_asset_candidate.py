from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/promote_asset_candidate.py'
METADATA = ROOT / 'docs/automation/generation_runs/scene_event_cg_readme_positive_only_20260530_072325/metadata.json'


def run_promote(*args: str):
    return subprocess.run([sys.executable, str(SCRIPT), str(METADATA), *args], cwd=ROOT, text=True, capture_output=True)


def load_promote_module():
    spec = importlib.util.spec_from_file_location('promote_asset_candidate_under_test', SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_promote_refuses_missing_approved_even_with_required_args():
    proc = run_promote('--asset-id', 'test_refuse_no_approval', '--renpy-name', 'test_refuse_no_approval')
    assert proc.returncode == 2
    assert 'missing --approved explicit approval flag' in proc.stdout


def test_promote_refuses_failing_qa_report(tmp_path: Path):
    qa = tmp_path / 'qa_fail.json'
    qa.write_text(json.dumps({'status': 'fail', 'errors': ['file_empty']}), encoding='utf-8')
    proc = run_promote(
        '--asset-id', 'test_refuse_bad_qa',
        '--renpy-name', 'test_refuse_bad_qa',
        '--approved',
        '--qa-report', str(qa),
    )
    assert proc.returncode == 2
    assert 'QA report status is not pass' in proc.stdout


def test_mark_metadata_promoted_updates_source_sidecar(tmp_path: Path):
    module = load_promote_module()
    metadata_path = tmp_path / 'metadata.json'
    metadata = {
        'qa_status': 'qa_pass_candidate_not_promoted',
        'promotion_status': 'not_promoted_pending_owner_approval',
    }
    metadata_path.write_text(json.dumps(metadata), encoding='utf-8')
    entry = {
        'asset_id': 'bg_test',
        'renpy_name': 'bg test',
        'promoted_path': 'images/backgrounds/bg_test.png',
        'metadata': {'promoted_at': '2026-05-31T08:00:00'},
    }
    log_path = tmp_path / 'promotion.json'

    module.mark_metadata_promoted(metadata_path, metadata, entry, log_path)

    saved = json.loads(metadata_path.read_text(encoding='utf-8'))
    assert saved['qa_status'] == 'owner_approved_promoted'
    assert saved['promotion_status'] == 'owner_approved_promoted'
    assert saved['promotions'] == [{
        'promoted_at': '2026-05-31T08:00:00',
        'asset_id': 'bg_test',
        'renpy_name': 'bg test',
        'promoted_path': 'images/backgrounds/bg_test.png',
        'promotion_log': str(log_path),
    }]
