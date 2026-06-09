from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env={**__import__('os').environ, 'PYTHONPATH': str(ROOT)},
    )


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def make_project(tmp_path: Path, name: str = 'assurance_title') -> Path:
    project = tmp_path / name
    game = project / 'game'
    game.mkdir(parents=True)
    (game / 'script.rpy').write_text('label start:\n    return\n', encoding='utf-8')
    write_json(game / 'data/asset_manifest.json', {'version': '1.0.0', 'assets': []})
    workflow = tmp_path / f'{name}_workflow_pack'
    workflow.mkdir()
    write_json(workflow / 'WORKFLOW_INDEX.json', {'workflows': []})
    vault = tmp_path / 'obsidian' / name
    obsidian_root = vault / 'VN'
    (obsidian_root / 'Scenes').mkdir(parents=True)
    write_json(project / 'docs/automation/project_contract.json', {
        'version': '1.0.0',
        'game_slug': name,
        'game_title': name.replace('_', ' ').title(),
        'renpy_project_root': project.as_posix(),
        'renpy_game_dir': game.as_posix(),
        'manifest_path': (game / 'data/asset_manifest.json').as_posix(),
        'generation_runs_root': (project / 'docs/automation/generation_runs').as_posix(),
        'generated_candidates_root': (project / 'docs/automation/generated_candidates').as_posix(),
        'promotion_log_root': (project / 'docs/production/promotions').as_posix(),
        'workflow_pack_root': workflow.as_posix(),
        'workflow_index': (workflow / 'WORKFLOW_INDEX.json').as_posix(),
        'obsidian_vault': vault.as_posix(),
        'obsidian_project_root': obsidian_root.as_posix(),
        'obsidian_scenes_glob': 'Scenes/*.md',
        'renpy_sdk_exe': '',
    })
    return project


def make_candidate(project: Path, *, asset_id: str = 'bg_test') -> tuple[Path, Path, Path]:
    candidate = project / 'docs/automation/generation_runs/run_001/candidate.png'
    metadata = candidate.parent / 'metadata.json'
    qa = candidate.parent / 'qa_pass.json'
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b'fake-png')
    write_json(metadata, {
        'run_id': 'run_001',
        'asset_id': asset_id,
        'asset_type': 'background',
        'workflow_id': 'scene_background',
        'candidate_copies': [candidate.as_posix()],
    })
    write_json(qa, {'status': 'pass', 'path': candidate.as_posix()})
    return metadata, candidate, qa


def test_director_status_requires_valid_project_contract(tmp_path: Path):
    project = make_project(tmp_path)
    contract_path = project / 'docs/automation/project_contract.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    contract['manifest_path'] = (tmp_path / 'outside_manifest.json').as_posix()
    contract_path.write_text(json.dumps(contract), encoding='utf-8')

    proc = run_cli('director', 'status', '--project-root', str(project))
    assert proc.returncode == 2
    assert 'PROJECT_CONTRACT_INVALID' in proc.stdout + proc.stderr or 'DIRECTOR_REFUSED' in proc.stdout + proc.stderr


def test_director_new_scene_rejects_cross_title_explicit_vault(tmp_path: Path):
    project_a = make_project(tmp_path, 'title_a')
    project_b = make_project(tmp_path, 'title_b')
    contract_b = json.loads((project_b / 'docs/automation/project_contract.json').read_text(encoding='utf-8'))
    other_vault = Path(contract_b['obsidian_project_root'])

    proc = run_cli('director', 'new-scene', '--project-root', str(project_a), '--vault', str(other_vault), '--scene-id', 'scene_escape')
    assert proc.returncode == 2
    assert 'DIRECTOR_REFUSED' in proc.stdout + proc.stderr
    assert not (other_vault / 'Scenes/scene_escape.md').exists()


def test_director_preview_rejects_external_screenshot(tmp_path: Path):
    project = make_project(tmp_path)
    outside = tmp_path / 'outside_preview.png'
    outside.write_bytes(b'image')
    proc = run_cli('director', 'preview', '--project-root', str(project), '--scene-id', 'scene_start', '--screenshot', str(outside))
    assert proc.returncode == 2
    assert 'PREVIEW_REFUSED' in proc.stdout + proc.stderr


def test_promote_rejects_unsafe_identity_and_filename_values(tmp_path: Path):
    project = make_project(tmp_path)
    metadata, _, qa = make_candidate(project)
    cases = [
        ('--asset-id', '../bad_asset'),
        ('--asset-id', 'bad/name'),
        ('--renpy-name', 'bg bad\nimage'),
        ('--filename', '../escape.png'),
        ('--filename', 'CON.png'),
        ('--filename', 'asset.png:evil'),
    ]
    for flag, value in cases:
        args = ['promote', str(metadata), '--project-root', str(project), '--asset-id', 'bg_test', '--renpy-name', 'bg test', '--approved', '--qa-report', str(qa)]
        idx = args.index(flag) if flag in args else None
        if idx is not None:
            args[idx + 1] = value
        else:
            args.extend([flag, value])
        proc = run_cli(*args)
        assert proc.returncode == 2, flag + value + proc.stdout + proc.stderr
        assert 'PROMOTE_REFUSED' in proc.stdout + proc.stderr


def test_promote_force_overwrite_creates_backup(tmp_path: Path):
    project = make_project(tmp_path)
    metadata, _, qa = make_candidate(project)
    dest = project / 'game/images/backgrounds/existing.png'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b'old')

    proc = run_cli('promote', str(metadata), '--project-root', str(project), '--asset-id', 'bg_existing', '--renpy-name', 'bg existing', '--filename', 'existing.png', '--approved', '--qa-report', str(qa), '--force-overwrite')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    backups = list((project / 'docs/production/promotions/backups').glob('existing*'))
    assert backups, 'expected overwritten production asset backup'
    assert backups[0].read_bytes() == b'old'


def test_manifest_schema_rejects_empty_asset_entries(tmp_path: Path):
    project = make_project(tmp_path)
    manifest = project / 'game/data/asset_manifest.json'
    write_json(manifest, {'version': '1.0.0', 'assets': [{}]})
    proc = run_cli('validate', '--project-root', str(project))
    assert proc.returncode != 0
    assert 'asset_manifest' in proc.stdout + proc.stderr or 'manifest' in proc.stdout + proc.stderr


def test_generation_runner_timeout_is_per_item_structured(tmp_path: Path):
    project = make_project(tmp_path)
    req = project / 'docs/production/asset_requests/scene.resolved_asset_requests.json'
    write_json(req, {
        'scene_id': 'scene',
        'resolved_asset_requests': [{
            'asset_id': 'bg_timeout',
            'asset_type': 'background',
            'decision': 'generate',
            'recommended_workflow_id': 'test_runner',
        }],
    })
    sleeper = tmp_path / 'sleep_runner.py'
    sleeper.write_text('import time\ntime.sleep(5)\n', encoding='utf-8')
    runner = f"{sys.executable} {sleeper}"
    out = project / 'docs/automation/generation_timeout.json'
    proc = run_cli('generate', '--project-root', str(project), '--resolved-glob', 'docs/production/asset_requests/*.json', '--runner', f'test_runner={runner}', '--runner-timeout', '1', '--out', str(out))
    assert proc.returncode == 1
    assert out.exists()
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['results'][0]['status'] == 'failed_runner_timeout'
    assert 'Traceback' not in proc.stdout + proc.stderr


def test_direct_smoke_runner_refuses_out_metadata_outside_project(tmp_path: Path):
    project = make_project(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'tools/run_scene_background_smoke.py'), '--project-root', str(project), '--prepare-only', '--out-metadata', str(tmp_path / 'outside_metadata.json')],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 2
    assert 'REFUSED' in proc.stdout + proc.stderr



def test_direct_smoke_runners_refuse_external_metadata_surfaces(tmp_path: Path):
    project = make_project(tmp_path)
    outside = tmp_path / 'outside_metadata.json'
    runners = [
        ('run_char_base_smoke.py', ['--prepare-only', '--out-metadata', str(outside)]),
        ('run_audio_sfx_mmaudio_smoke.py', ['--prepare-only', '--out-metadata', str(outside)]),
    ]
    for script, extra in runners:
        proc = subprocess.run(
            [sys.executable, str(ROOT / 'tools' / script), '--project-root', str(project), *extra],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 2, script + proc.stdout + proc.stderr
        assert 'REFUSED' in proc.stdout + proc.stderr


def test_scene_event_cg_refuses_external_char_base_metadata(tmp_path: Path):
    project = make_project(tmp_path)
    outside = tmp_path / 'outside_char_base_metadata.json'
    write_json(outside, {'asset_type': 'char_base'})
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'tools/run_scene_event_cg_smoke.py'), '--project-root', str(project), '--asset-id', 'cg_test', '--scene-id', 'scene_start', '--char-base-metadata', str(outside)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 2
    assert 'REFUSED' in proc.stdout + proc.stderr



def test_manifest_validation_rejects_unsafe_identity_and_paths(tmp_path: Path):
    project = make_project(tmp_path)
    manifest = project / 'game/data/asset_manifest.json'
    write_json(manifest, {'version': '1.0.0', 'assets': [{
        'asset_id': '../bad',
        'asset_type': 'background',
        'workflow_id': 'scene_background',
        'generated_path': 'docs/automation/generated_candidates/candidate.png',
        'promoted_path': 'images/backgrounds/good.png:evil',
        'qa_status': 'owner_approved_promoted',
        'renpy_name': 'bg bad\nname',
        'scene_usage': ['scene_start'],
        'metadata': {},
    }]})
    proc = run_cli('validate', '--project-root', str(project), '--skip-obsidian')
    assert proc.returncode == 1
    text = proc.stdout + proc.stderr
    assert 'unsafe asset_id' in text
    assert 'unsafe renpy_name' in text
    assert 'unsafe promoted_path' in text
