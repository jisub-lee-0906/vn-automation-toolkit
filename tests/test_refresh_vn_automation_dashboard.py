import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/refresh_vn_automation_dashboard.py'


def test_refresh_vn_automation_dashboard_writes_current_state_and_dashboard(tmp_path: Path):
    project = tmp_path / 'project'
    automation = project / 'docs/automation'
    (project / 'game').mkdir(parents=True)
    (automation / 'batches').mkdir(parents=True)
    (automation / 'asset_requests/from_obsidian_scenes').mkdir(parents=True)
    (project / 'docs/validation').mkdir(parents=True)
    (automation / 'project_contract.json').write_text(json.dumps({
        'game_title': 'Test VN',
        'game_slug': 'test_vn',
        'comfyui_endpoint': 'http://127.0.0.1:65530',
        'comfyui_input_root': str(tmp_path / 'input'),
        'comfyui_output_root': str(tmp_path / 'output'),
    }), encoding='utf-8')
    (tmp_path / 'input').mkdir()
    (tmp_path / 'output').mkdir()
    (automation / 'asset_requests/from_obsidian_scenes/asset_request_index.json').write_text(json.dumps({
        'scene_count': 2,
        'total_asset_requests': 3,
        'total_candidate_suggestions': 4,
        'total_review_only_inferred_suggestions': 5,
        'total_unresolved_required_asset_mentions': 1,
    }), encoding='utf-8')
    (automation / 'batches/sample_scene_event_cg_batch.json').write_text(json.dumps({
        'asset_id_prefix': 'sample',
        'items': [1, 2],
        'prepare_only': True,
        'promotion_status': 'not_promoted_pending_owner_approval',
        'emotion': 'sad',
        'framing': 'default',
    }), encoding='utf-8')
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--project-root', str(project), '--skip-endpoint'],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    stdout = json.loads(result.stdout)
    current_state = automation / 'current_state.md'
    dashboard = automation / 'dashboard.md'
    assert stdout['current_state'] == str(current_state)
    assert stdout['dashboard'] == str(dashboard)
    current_text = current_state.read_text(encoding='utf-8')
    dash_text = dashboard.read_text(encoding='utf-8')
    assert 'Automation infrastructure: verified' in current_text
    assert 'Explicit asset requests: 3' in current_text
    assert 'Unresolved required asset mentions: 1' in current_text
    assert 'VN automation dashboard' in dash_text
    assert 'Candidate suggestions: 4' in dash_text
    assert 'Unresolved required asset mentions: 1' in dash_text
