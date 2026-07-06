import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / 'tools/run_generation_queue.py'
EXTRACTOR = ROOT / 'tools/extract_scene_asset_requests.py'


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extractor_workflow_ids_are_supported_by_generation_queue_defaults():
    queue = load_module(QUEUE, 'run_generation_queue')
    extractor = load_module(EXTRACTOR, 'extract_scene_asset_requests')
    produced = {extractor.workflow_for_kind(kind) for kind in ['background', 'event_cg', 'prop', 'ui', 'bgm', 'sfx', 'char_base', 'char_alpha', 'char_expression']}
    unsupported = produced - set(queue.DEFAULT_RUNNERS)
    assert unsupported == set()


def test_ui_system_alert_runner_accepts_generation_queue_common_args():
    # Queue always passes --project-root/--asset-id/--description/--scene-id.
    # The runner must accept these even when the queue invokes it.
    text = (ROOT / 'tools/run_ui_system_alert_frame_smoke.py').read_text(encoding='utf-8')
    assert "parser.add_argument('--description'" in text
    assert "parser.add_argument('--scene-id'" in text


def test_generation_queue_requires_ui_system_alert_prompt_shape(tmp_path: Path):
    queue = load_module(QUEUE, 'run_generation_queue')
    project = tmp_path / 'game'
    project.mkdir()
    item = {
        'workflow_id': 'ui_system_alert_frame',
        'asset_id': 'ui_alert',
        'scene_id': 'scene_a',
        'description': 'red alert',
    }
    result = queue.run_one(project, item, 'python -c "print(123)"')
    assert result['status'] == 'failed_missing_prompt_shape'


def test_generation_queue_passes_ui_system_alert_prompt_shape(tmp_path: Path):
    queue = load_module(QUEUE, 'run_generation_queue')
    project = tmp_path / 'game'
    (project / 'docs/automation/generation_runs').mkdir(parents=True)
    item = {
        'workflow_id': 'ui_system_alert_frame',
        'asset_id': 'ui_alert',
        'scene_id': 'scene_a',
        'description': 'red alert',
        'recommended_prompt_shape': 'corner_alert_backdrop',
    }
    result = queue.run_one(project, item, 'python -c "print(123)"')
    assert result['status'] == 'failed_missing_metadata'
    assert '--prompt-shape' in result['command']
    assert 'corner_alert_backdrop' in result['command']
