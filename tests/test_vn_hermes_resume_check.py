import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/vn_hermes_resume_check.py'


def test_vn_hermes_resume_check_reports_project_anchor(tmp_path: Path):
    project = tmp_path / 'game_project'
    (project / 'game').mkdir(parents=True)
    (project / 'docs/automation/batches').mkdir(parents=True)
    (project / 'docs/automation/asset_requests/from_obsidian_scenes').mkdir(parents=True)
    (project / 'docs/automation/generation_runs/run_a').mkdir(parents=True)
    (project / 'docs/automation/current_state.md').write_text('# state\n', encoding='utf-8')
    (project / 'docs/automation/dashboard.md').write_text('# dash\n', encoding='utf-8')
    (project / 'docs/automation/project_contract.json').write_text(json.dumps({
        'game_title': 'Test VN',
        'game_slug': 'test_vn',
        'comfyui_endpoint': 'http://127.0.0.1:65530',
        'comfyui_input_root': str(tmp_path / 'input'),
        'comfyui_output_root': str(tmp_path / 'output'),
    }), encoding='utf-8')
    (tmp_path / 'input').mkdir()
    (tmp_path / 'output').mkdir()
    (project / 'docs/automation/batches/sample_scene_event_cg_batch.json').write_text(json.dumps({
        'asset_id_prefix': 'sample',
        'items': [],
        'promotion_status': 'not_promoted_pending_owner_approval',
    }), encoding='utf-8')
    (project / 'docs/automation/asset_requests/from_obsidian_scenes/asset_request_index.json').write_text(json.dumps({
        'scene_count': 1,
        'total_asset_requests': 1,
    }), encoding='utf-8')
    (project / 'docs/automation/generation_runs/run_a/metadata.json').write_text(json.dumps({
        'run_id': 'run_a',
        'promotion_status': 'not_promoted_pending_owner_approval',
    }), encoding='utf-8')

    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--project-root', str(project), '--skip-endpoint'],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data['project']['exists'] is True
    assert data['anchors']['current_state_exists'] is True
    assert data['anchors']['dashboard_exists'] is True
    assert data['contract']['comfyui_endpoint'] == 'http://127.0.0.1:65530'
    assert data['contract']['title'] == 'Test VN'
    assert data['contract']['slug'] == 'test_vn'
    assert data['recent_batches'][0]['file'].endswith('sample_scene_event_cg_batch.json')
    assert data['latest_reports']['asset_request_indexes'][0].endswith('asset_request_index.json')
    assert data['promotion_status_counts']['not_promoted_pending_owner_approval'] == 1
    assert data['recommended_resume_steps'][0].startswith('Read docs/automation/current_state.md')
