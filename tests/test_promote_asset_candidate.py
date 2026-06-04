from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/promote_asset_candidate.py'
METADATA = ROOT / 'docs/automation/generation_runs/scene_event_cg_readme_positive_only_20260530_072325/metadata.json'


def make_promote_project(tmp_path: Path, *, with_qa: bool = False, qa_status: str = 'pass') -> tuple[Path, Path, Path | None]:
    project = tmp_path / 'project'
    (project / 'game/data').mkdir(parents=True, exist_ok=True)
    (project / 'game/data/asset_manifest.json').write_text(json.dumps({'assets': []}), encoding='utf-8')
    candidate = project / 'docs/automation/generated_candidates/candidate.png'
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b'candidate')
    metadata = project / 'docs/automation/generation_runs/test/metadata.json'
    metadata.parent.mkdir(parents=True, exist_ok=True)
    qa = None
    payload = {
        'asset_type': 'background',
        'candidate_copies': [str(candidate)],
        'qa_status': 'qa_pass_candidate_not_promoted',
    }
    if with_qa:
        qa = project / 'docs/automation/qa_reports/candidate_qa.json'
        qa.parent.mkdir(parents=True, exist_ok=True)
        qa.write_text(json.dumps({'status': qa_status}), encoding='utf-8')
    metadata.write_text(json.dumps(payload), encoding='utf-8')
    return project, metadata, qa


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


def test_promote_refuses_missing_qa_report_even_when_approved(tmp_path: Path):
    project, metadata, _qa = make_promote_project(tmp_path)
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPT), str(metadata),
            '--project-root', str(project),
            '--asset-id', 'test_refuse_missing_qa',
            '--renpy-name', 'test_refuse_missing_qa',
            '--approved',
        ],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert proc.returncode == 2
    assert 'missing --qa-report passing QA evidence' in proc.stdout


def test_promote_refuses_failing_qa_report(tmp_path: Path):
    project, metadata, qa = make_promote_project(tmp_path, with_qa=True, qa_status='fail')
    assert qa is not None
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPT), str(metadata),
            '--project-root', str(project),
            '--asset-id', 'test_refuse_bad_qa',
            '--renpy-name', 'test_refuse_bad_qa',
            '--approved',
            '--qa-report', str(qa),
        ],
        cwd=ROOT, text=True, capture_output=True,
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
