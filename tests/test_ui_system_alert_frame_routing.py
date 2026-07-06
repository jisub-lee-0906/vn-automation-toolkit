from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/run_ui_system_alert_frame_smoke.py'


def load_runner():
    spec = importlib.util.spec_from_file_location('run_ui_system_alert_frame_smoke', SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ui_alert_corner_backdrop_prompt_shape():
    runner = load_runner()
    positive, tags = runner.build_positive('corner_alert_backdrop')
    assert positive.startswith('masterpiece, best quality')
    assert 'border, outside_border, red_border' in positive
    assert 'corner' in tags
    assert 'no_humans' in tags


def test_ui_alert_minimal_prompt_shape_is_small():
    runner = load_runner()
    positive, tags = runner.build_positive('minimal_red_gold_border')
    assert tags == ['black_background', 'no_humans', 'border', 'red_border', 'gold_border']
    assert 'visual_novel' not in tags
    assert 'corner' not in tags


def test_ui_alert_resolve_paths_confines_project_outputs(tmp_path: Path):
    runner = load_runner()
    project = tmp_path / 'game'
    project.mkdir()
    paths = runner.resolve_project_paths(project, '')
    assert paths['project_root'] == project.resolve()
    assert str(paths['run_root']).startswith(str(project.resolve()))
    assert str(paths['candidate_root']).startswith(str(project.resolve()))


def test_ui_alert_resolve_paths_rejects_outside_contract(tmp_path: Path):
    runner = load_runner()
    project = tmp_path / 'game'
    project.mkdir()
    outside = tmp_path / 'outside_contract.json'
    outside.write_text('{}', encoding='utf-8')
    try:
        runner.resolve_project_paths(project, str(outside))
    except RuntimeError as exc:
        assert 'UI_SYSTEM_ALERT_CONTRACT_MUST_BE_UNDER_PROJECT_ROOT' in str(exc)
    else:
        raise AssertionError('expected outside contract to be rejected')
