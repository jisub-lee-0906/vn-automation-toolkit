from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'


def run_tool(script: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOLS / script), *args],
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
    )


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def make_min_project(tmp_path: Path, name: str = 'portable_title') -> Path:
    project = tmp_path / name
    game = project / 'game'
    game.mkdir(parents=True)
    (project / 'docs/automation').mkdir(parents=True)
    (game / 'script.rpy').write_text('label start:\n    return\n', encoding='utf-8')
    (game / 'data').mkdir(parents=True)
    manifest = {'version': '1.0.0', 'assets': []}
    (game / 'data/asset_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    workflow = tmp_path / 'workflow_pack'
    workflow.mkdir(exist_ok=True)
    (workflow / 'WORKFLOW_INDEX.json').write_text('{"workflows": []}', encoding='utf-8')
    contract = {
        'version': '1.0.0',
        'game_slug': name,
        'game_title': name.replace('_', ' ').title(),
        'renpy_project_root': project.as_posix(),
        'renpy_game_dir': game.as_posix(),
        'renpy_sdk_exe': '',
        'manifest_path': (game / 'data/asset_manifest.json').as_posix(),
        'workflow_pack_root': workflow.as_posix(),
        'workflow_index': (workflow / 'WORKFLOW_INDEX.json').as_posix(),
        'obsidian_vault': (tmp_path / 'obsidian').as_posix(),
        'obsidian_project_root': (tmp_path / 'obsidian' / name / 'VN').as_posix(),
        'obsidian_scenes_glob': 'Scenes/*.md',
    }
    (project / 'docs/automation/project_contract.json').write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding='utf-8')
    return project


def test_project_tools_fail_closed_without_active_project(tmp_path: Path):
    isolated = tmp_path / 'no_project_here'
    isolated.mkdir()
    proc = run_tool('check_renpy_asset_refs.py', cwd=isolated)
    assert proc.returncode == 2
    assert 'PROJECT_SELECTION_REQUIRED' in proc.stderr or 'PROJECT_SELECTION_REQUIRED' in proc.stdout


def test_project_tools_use_cwd_project_contract_when_no_arg(tmp_path: Path):
    project = make_min_project(tmp_path)
    proc = run_tool('check_renpy_asset_refs.py', cwd=project)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'project_root' in proc.stdout
    assert str(project.resolve()) in proc.stdout


def test_init_defaults_obsidian_project_root_to_game_slug_namespace(tmp_path: Path):
    project = tmp_path / 'new_title'
    vault = tmp_path / 'obsidian_vault'
    proc = run_tool('init_vn_automation_project.py', '--project-root', str(project), '--obsidian-vault', str(vault), '--game-slug', 'new_title')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    contract = json.loads((project / 'docs/automation/project_contract.json').read_text(encoding='utf-8'))
    assert contract['obsidian_project_root'] == (vault / 'new_title' / 'VN').resolve().as_posix()
    assert (vault / 'new_title' / 'VN' / '00_Index.md').exists()


def test_preflight_reports_cross_game_contract_readiness(tmp_path: Path):
    project = make_min_project(tmp_path)
    proc = run_cli('preflight', '--project-root', str(project), '--skip-comfyui')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'VN_AUTO_PREFLIGHT' in proc.stdout
    assert 'contract PASS' in proc.stdout
    assert 'obsidian_scope PASS' in proc.stdout
    assert 'manifest PASS' in proc.stdout
    assert 'workflow_pack PASS' in proc.stdout


def test_validate_scene_static_phase_uses_capture_plan_and_writes_report(tmp_path: Path):
    project = make_min_project(tmp_path)
    plan = project / 'docs/automation/capture_plans/scene_start.json'
    plan.parent.mkdir(parents=True)
    plan.write_text(json.dumps({
        'scene_id': 'scene_start',
        'captures': [
            {'name': 'start', 'warp': 'game/script.rpy:1', 'expect': ['label start']}
        ],
    }), encoding='utf-8')
    out = project / 'docs/validation/scene_validate'
    proc = run_cli('validate-scene', '--project-root', str(project), '--scene-id', 'scene_start', '--capture-plan', str(plan), '--static-only', '--out-dir', str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'VALIDATE_SCENE_PASSED' in proc.stdout
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['scene_id'] == 'scene_start'
    assert manifest['gates']['capture_plan']['status'] == 'PASS'
    assert (out / 'report.md').exists()



def test_vn_auto_cli_uses_caller_cwd_project_contract(tmp_path: Path):
    project = make_min_project(tmp_path)
    proc = subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', 'check'],
        cwd=project,
        text=True,
        capture_output=True,
        env={**__import__('os').environ, 'PYTHONPATH': str(ROOT)},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert str(project.resolve()) in proc.stdout


def test_validate_scene_rejects_output_dir_outside_project(tmp_path: Path):
    project = make_min_project(tmp_path)
    plan = project / 'docs/automation/capture_plans/scene_start.json'
    plan.parent.mkdir(parents=True)
    plan.write_text(json.dumps({'scene_id': 'scene_start', 'captures': [{'name': 'start', 'warp': 'game/script.rpy:1'}]}), encoding='utf-8')
    outside = tmp_path / 'outside_validation'
    proc = run_cli('validate-scene', '--project-root', str(project), '--scene-id', 'scene_start', '--capture-plan', str(plan), '--static-only', '--out-dir', str(outside))
    assert proc.returncode == 2
    assert 'VALIDATE_SCENE_REFUSED' in proc.stdout
    assert not outside.exists()


def test_validate_scene_rejects_unsafe_scene_id(tmp_path: Path):
    project = make_min_project(tmp_path)
    plan = project / 'docs/automation/capture_plans/scene_start.json'
    plan.parent.mkdir(parents=True)
    plan.write_text(json.dumps({'scene_id': '../escape', 'captures': [{'name': 'start', 'warp': 'game/script.rpy:1'}]}), encoding='utf-8')
    proc = run_cli('validate-scene', '--project-root', str(project), '--scene-id', '../escape', '--capture-plan', str(plan), '--static-only')
    assert proc.returncode == 2
    assert 'unsafe scene_id' in proc.stdout


def test_preflight_rejects_obsidian_root_outside_configured_vault(tmp_path: Path):
    project = make_min_project(tmp_path)
    contract_path = project / 'docs/automation/project_contract.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    contract['obsidian_project_root'] = (tmp_path / 'other_vault' / contract['game_slug'] / 'VN').as_posix()
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    proc = run_cli('preflight', '--project-root', str(project), '--skip-comfyui')
    assert proc.returncode == 1
    assert 'obsidian_project_root must be under obsidian_vault' in proc.stdout



def test_preflight_accepts_dedicated_game_vault_root(tmp_path: Path):
    project = make_min_project(tmp_path)
    contract_path = project / 'docs/automation/project_contract.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    dedicated_vault = tmp_path / contract['game_slug']
    contract['obsidian_vault'] = dedicated_vault.as_posix()
    contract['obsidian_project_root'] = (dedicated_vault / 'VN').as_posix()
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    proc = run_cli('preflight', '--project-root', str(project), '--skip-comfyui')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'obsidian_scope PASS' in proc.stdout



def test_preflight_rejects_renpy_game_dir_outside_project_root(tmp_path: Path):
    project = make_min_project(tmp_path)
    outside_game = tmp_path / 'other_title' / 'game'
    outside_game.mkdir(parents=True)
    contract_path = project / 'docs/automation/project_contract.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    contract['renpy_game_dir'] = outside_game.as_posix()
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    proc = run_cli('preflight', '--project-root', str(project), '--skip-comfyui')
    assert proc.returncode == 2
    assert 'renpy_game_dir' in proc.stdout + proc.stderr



def test_capture_scene_dry_run_uses_generic_capture_plan(tmp_path: Path):
    project = make_min_project(tmp_path)
    plan = project / 'docs/automation/capture_plans/scene_start.json'
    plan.parent.mkdir(parents=True)
    plan.write_text(json.dumps({'scene_id': 'scene_start', 'captures': [{'name': 'start', 'warp': 'game/script.rpy:1'}]}), encoding='utf-8')
    proc = run_cli('capture-scene', '--project-root', str(project), '--scene-id', 'scene_start', '--capture-plan', str(plan), '--dry-run')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'CAPTURE_SCENE_CONTACT_SHEET' in proc.stdout
    assert 'dry_run true' in proc.stdout
    assert 'capture start game/script.rpy:1' in proc.stdout



def mutate_contract(project: Path, **updates) -> dict:
    contract_path = project / 'docs/automation/project_contract.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    contract.update({k: (v.as_posix() if isinstance(v, Path) else v) for k, v in updates.items()})
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding='utf-8')
    return contract


def write_plan(project: Path, scene_id: str = 'scene_start', captures=None) -> Path:
    plan = project / f'docs/automation/capture_plans/{scene_id}.json'
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(json.dumps({
        'scene_id': scene_id,
        'captures': captures if captures is not None else [{'name': 'start', 'warp': 'game/script.rpy:1'}],
    }), encoding='utf-8')
    return plan


def test_cli_project_commands_fail_closed_without_active_project(tmp_path: Path):
    isolated = tmp_path / 'no_project'
    isolated.mkdir()
    for command in ['sync', 'queue', 'generate']:
        proc = subprocess.run(
            [sys.executable, '-m', 'vn_automation.cli', command],
            cwd=isolated,
            text=True,
            capture_output=True,
            env={**__import__('os').environ, 'PYTHONPATH': str(ROOT), 'VN_AUTOMATION_PROJECT_ROOT': ''},
        )
        assert proc.returncode == 2, command + proc.stdout + proc.stderr
        assert 'PROJECT_SELECTION_REQUIRED' in proc.stdout + proc.stderr


def test_env_project_root_conflict_with_cwd_project_is_refused(tmp_path: Path):
    project_a = make_min_project(tmp_path, 'game_a')
    project_b = make_min_project(tmp_path, 'game_b')
    proc = subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', 'check'],
        cwd=project_b,
        text=True,
        capture_output=True,
        env={**__import__('os').environ, 'PYTHONPATH': str(ROOT), 'VN_AUTOMATION_PROJECT_ROOT': str(project_a)},
    )
    assert proc.returncode == 2
    assert 'PROJECT_SELECTION_CONFLICT' in proc.stdout + proc.stderr


def test_preflight_rejects_contract_file_outside_project_root(tmp_path: Path):
    project = make_min_project(tmp_path)
    external = tmp_path / 'external_contract.json'
    external.write_text((project / 'docs/automation/project_contract.json').read_text(encoding='utf-8'), encoding='utf-8')
    proc = run_cli('preflight', '--project-root', str(project), '--contract', str(external), '--skip-comfyui')
    assert proc.returncode == 2
    assert 'contract outside' in proc.stdout + proc.stderr


def test_preflight_rejects_cross_game_contract_roots_and_sidecars(tmp_path: Path):
    project = make_min_project(tmp_path)
    other = tmp_path / 'other_game'
    other.mkdir()
    mutate_contract(
        project,
        renpy_project_root=other,
        generation_runs_root=tmp_path / 'runs_outside',
        generated_candidates_root=tmp_path / 'candidates_outside',
        promotion_log_root=tmp_path / 'promotions_outside',
    )
    proc = run_cli('preflight', '--project-root', str(project), '--skip-comfyui')
    assert proc.returncode == 2
    text = proc.stdout + proc.stderr
    assert 'renpy_project_root must match selected project_root' in text


def test_preflight_rejects_workflow_index_outside_workflow_pack(tmp_path: Path):
    project = make_min_project(tmp_path)
    external_index = tmp_path / 'external_index.json'
    external_index.write_text('{"workflows": []}', encoding='utf-8')
    mutate_contract(project, workflow_index=external_index)
    proc = run_cli('preflight', '--project-root', str(project), '--skip-comfyui')
    assert proc.returncode == 1
    assert 'workflow_index must be under workflow_pack_root' in proc.stdout + proc.stderr


def test_capture_plan_rejects_unsafe_capture_name_and_wait(tmp_path: Path):
    project = make_min_project(tmp_path)
    plan = write_plan(project, captures=[
        {'name': '../../escape', 'warp': 'game/script.rpy:1'},
        {'name': 'slow', 'warp': 'game/script.rpy:1', 'wait_seconds': 999},
    ])
    proc = run_cli('validate-scene', '--project-root', str(project), '--scene-id', 'scene_start', '--capture-plan', str(plan), '--static-only')
    assert proc.returncode == 1
    report_path = project / 'docs/validation/scene_start/report.md'
    text = proc.stdout + (report_path.read_text(encoding='utf-8') if report_path.exists() else proc.stderr)
    assert 'unsafe capture name' in text
    assert 'wait_seconds' in text


def test_capture_plan_rejects_malformed_warp_and_too_many_captures(tmp_path: Path):
    project = make_min_project(tmp_path)
    captures = [{'name': f'cap_{i}', 'warp': 'game/script.rpy:notaline'} for i in range(13)]
    plan = write_plan(project, captures=captures)
    proc = run_cli('validate-scene', '--project-root', str(project), '--scene-id', 'scene_start', '--capture-plan', str(plan), '--static-only')
    assert proc.returncode == 1
    report_path = project / 'docs/validation/scene_start/report.md'
    report = report_path.read_text(encoding='utf-8') if report_path.exists() else proc.stdout + proc.stderr
    assert 'too many captures' in report
    assert 'warp line must be positive integer' in report


def test_capture_scene_refuses_runtime_when_dependencies_missing_even_with_fake_renpy(tmp_path: Path):
    project = make_min_project(tmp_path)
    fake = tmp_path / 'renpy_fake.py'
    fake.write_text('import time\ntime.sleep(60)\n', encoding='utf-8')
    mutate_contract(project, renpy_sdk_exe=sys.executable)
    plan = write_plan(project)
    proc = run_cli('capture-scene', '--project-root', str(project), '--scene-id', 'scene_start', '--capture-plan', str(plan), '--runtime-timeout', '1')
    assert proc.returncode in (1, 2)
    assert 'CAPTURE_SCENE_' in proc.stdout + proc.stderr
    assert 'Traceback' not in proc.stdout + proc.stderr


def test_validate_scene_runtime_failure_is_structured_without_traceback(tmp_path: Path):
    project = make_min_project(tmp_path)
    mutate_contract(project, renpy_sdk_exe=sys.executable)
    plan = write_plan(project)
    proc = run_cli('validate-scene', '--project-root', str(project), '--scene-id', 'scene_start', '--capture-plan', str(plan), '--runtime-timeout', '1')
    assert proc.returncode == 1
    text = proc.stdout + proc.stderr
    assert 'VALIDATE_SCENE_FAILED' in text
    assert 'Traceback' not in text
    report = (project / 'docs/validation/scene_start/report.md').read_text(encoding='utf-8')
    assert 'runtime_capture' in report


def test_run_phase_timeout_is_structured(tmp_path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('validate_scene_under_test', TOOLS / 'validate_scene.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    log = tmp_path / 'phase.log'
    result = module.run_phase([sys.executable, '-c', 'import time; time.sleep(5)'], tmp_path, log, timeout=1)
    assert result['status'] == 'FAIL'
    assert result['exit_code'] == 'TIMEOUT'
    assert 'TIMEOUT after 1s' in log.read_text(encoding='utf-8')



def test_project_commands_reject_sidecar_outputs_outside_project(tmp_path: Path):
    project = make_min_project(tmp_path)
    outside = tmp_path / 'outside.json'
    for args in [
        ['sync', '--project-root', str(project), '--vault', str(tmp_path / 'obsidian'), '--out-summary', str(outside)],
        ['queue', '--project-root', str(project), '--out-json', str(outside)],
        ['queue', '--project-root', str(project), '--out-md', str(tmp_path / 'outside.md')],
        ['generate', '--project-root', str(project), '--out', str(outside), '--limit', '0'],
    ]:
        proc = run_cli(*args)
        assert proc.returncode == 2, ' '.join(args) + proc.stdout + proc.stderr
        assert 'outside' in proc.stdout + proc.stderr or 'Unsafe' in proc.stdout + proc.stderr


def test_queue_and_generate_reject_resolved_glob_parent_traversal(tmp_path: Path):
    project = make_min_project(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'evil.resolved_asset_requests.json').write_text(json.dumps({
        'scene_id': 'evil',
        'resolved_asset_requests': [{'asset_id': 'evil_asset', 'decision': 'generate'}],
    }), encoding='utf-8')
    for command in ['queue', 'generate']:
        proc = run_cli(command, '--project-root', str(project), '--resolved-glob', '../outside/*.json', '--limit', '0') if command == 'generate' else run_cli(command, '--project-root', str(project), '--resolved-glob', '../outside/*.json')
        assert proc.returncode == 2, command + proc.stdout + proc.stderr
        assert 'resolved_glob' in proc.stdout + proc.stderr


def test_generate_with_active_project_default_out_is_project_scoped(tmp_path: Path):
    project = make_min_project(tmp_path)
    proc = run_cli('generate', '--project-root', str(project), '--limit', '0')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (project / 'docs/automation/generation_queue_batch.json').exists()


def test_build_project_paths_requires_existing_valid_contract(tmp_path: Path):
    project = tmp_path / 'not_initialized'
    project.mkdir()
    proc = run_cli('check', '--project-root', str(project))
    assert proc.returncode == 2
    assert 'PROJECT_CONTRACT_INVALID' in proc.stdout + proc.stderr
    bad = make_min_project(tmp_path, 'bad_contract')
    (bad / 'docs/automation/project_contract.json').write_text('{bad json', encoding='utf-8')
    proc = run_cli('check', '--project-root', str(bad))
    assert proc.returncode == 2
    assert 'PROJECT_CONTRACT_INVALID' in proc.stdout + proc.stderr



def test_resolve_rejects_output_outside_project(tmp_path: Path):
    project = make_min_project(tmp_path)
    req = project / 'docs/production/asset_requests/scene.asset_requests.json'
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text(json.dumps({'scene_id': 'scene', 'asset_requests': []}), encoding='utf-8')
    proc = run_cli('resolve', str(req), '--project-root', str(project), '--out', str(tmp_path / 'outside_resolved.json'))
    assert proc.returncode == 2
    assert 'RESOLVE_REFUSED' in proc.stdout + proc.stderr



def test_resolve_rejects_external_manifest_and_generation_runs_root(tmp_path: Path):
    project = make_min_project(tmp_path)
    req = project / 'docs/production/asset_requests/scene.asset_requests.json'
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text(json.dumps({'scene_id': 'scene', 'asset_requests': []}), encoding='utf-8')
    out = project / 'docs/production/asset_requests/resolved.json'
    external_manifest = tmp_path / 'outside_manifest.json'
    external_manifest.write_text(json.dumps({'assets': []}), encoding='utf-8')
    external_runs = tmp_path / 'outside_runs'
    external_runs.mkdir()
    for extra in [('--manifest', str(external_manifest)), ('--generation-runs-root', str(external_runs))]:
        proc = run_cli('resolve', str(req), '--project-root', str(project), extra[0], extra[1], '--out', str(out))
        assert proc.returncode == 2
        assert 'RESOLVE_REFUSED' in proc.stdout + proc.stderr


def test_gaps_rejects_json_outside_project(tmp_path: Path):
    project = make_min_project(tmp_path)
    proc = run_cli('gaps', '--project-root', str(project), '--json-out', str(tmp_path / 'outside_gap_report.json'))
    assert proc.returncode == 2
    assert 'GAPS_REFUSED' in proc.stdout + proc.stderr



def test_audit_rejects_json_outside_project(tmp_path: Path):
    project = make_min_project(tmp_path)
    proc = run_cli('audit', '--project-root', str(project), '--json-out', str(tmp_path / 'outside_audit.json'))
    assert proc.returncode == 2
    assert 'AUDIT_REFUSED' in proc.stdout + proc.stderr


def test_init_rejects_renpy_game_dir_outside_project(tmp_path: Path):
    project = tmp_path / 'new_game'
    external_game = tmp_path / 'other_game' / 'game'
    proc = run_cli('init', '--project-root', str(project), '--renpy-game-dir', str(external_game))
    assert proc.returncode == 2
    assert 'INIT_REFUSED' in proc.stdout + proc.stderr


def test_promote_rejects_external_metadata_candidate_and_qa(tmp_path: Path):
    project = make_min_project(tmp_path)
    # direct promote metadata outside project
    external_meta = tmp_path / 'outside_run' / 'metadata.json'
    external_candidate = tmp_path / 'outside_candidate.png'
    external_qa = tmp_path / 'outside_qa.json'
    external_meta.parent.mkdir(parents=True)
    external_candidate.write_bytes(b'candidate')
    external_qa.write_text(json.dumps({'status': 'pass'}), encoding='utf-8')
    external_meta.write_text(json.dumps({'asset_type': 'background', 'candidate_copies': [str(external_candidate)]}), encoding='utf-8')
    proc = run_cli('promote', str(external_meta), '--project-root', str(project), '--asset-id', 'bg_external', '--renpy-name', 'bg external', '--approved', '--qa-report', str(external_qa))
    assert proc.returncode == 2
    assert 'PROMOTE_REFUSED' in proc.stdout + proc.stderr

    # metadata inside project but candidate/qa outside project should also be refused.
    internal_meta = project / 'docs/automation/generation_runs/run/metadata.json'
    internal_meta.parent.mkdir(parents=True)
    internal_meta.write_text(json.dumps({'asset_type': 'background', 'candidate_copies': [str(external_candidate)]}), encoding='utf-8')
    proc = run_cli('promote', str(internal_meta), '--project-root', str(project), '--asset-id', 'bg_external', '--renpy-name', 'bg external', '--approved', '--qa-report', str(external_qa))
    assert proc.returncode == 2
    assert 'PROMOTE_REFUSED' in proc.stdout + proc.stderr
