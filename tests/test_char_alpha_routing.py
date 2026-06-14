from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/run_char_alpha_smoke.py'


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def make_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / 'alpha_project'
    game = project / 'game'
    game.mkdir(parents=True)
    workflow_pack = tmp_path / 'workflow_pack'
    workflow_pack.mkdir()
    comfy_input = tmp_path / 'ComfyUI' / 'input'
    comfy_output = tmp_path / 'ComfyUI' / 'output'
    comfy_input.mkdir(parents=True)
    comfy_output.mkdir(parents=True)
    write_json(project / 'docs/automation/project_contract.json', {
        'version': '1.0.0',
        'renpy_project_root': project.as_posix(),
        'renpy_game_dir': game.as_posix(),
        'workflow_pack_root': workflow_pack.as_posix(),
        'workflow_index': (workflow_pack / 'WORKFLOW_INDEX.json').as_posix(),
        'comfyui_input_root': comfy_input.as_posix(),
        'comfyui_output_root': comfy_output.as_posix(),
        'comfyui_endpoint': 'http://127.0.0.1:65535',
        'comfyui_endpoint_candidates': ['http://127.0.0.1:65535'],
    })
    write_json(workflow_pack / 'WORKFLOW_INDEX.json', {'workflows': []})
    write_json(workflow_pack / 'char_alpha/char_alpha_workflow_api.json', {
        '1': {'class_type': 'LoadImage', 'inputs': {'image': 'TEMPLATE_source_image.png'}},
        '2': {'class_type': 'BiRefNetRMBG', 'inputs': {'image': ['1', 0], 'model': 'BiRefNet_toonout'}},
        '3': {'class_type': 'SaveImage', 'inputs': {'images': ['2', 0], 'filename_prefix': 'old_prefix'}},
    })
    source = project / 'docs/automation/generated_candidates/characters/source_fixture.png'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'fake-png-fixture')
    return project, workflow_pack, source


def test_char_alpha_prepare_only_patches_source_image_and_metadata(tmp_path: Path):
    project, _, source = make_project(tmp_path)
    out_meta = project / 'docs/automation/generation_runs/alpha_prepare/metadata.json'

    proc = subprocess.run([
        sys.executable, str(SCRIPT),
        '--project-root', str(project),
        '--asset-id', 'alpha_fixture_sprite',
        '--source-image', str(source),
        '--prepare-only',
        '--out-metadata', str(out_meta),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out_meta.read_text(encoding='utf-8'))
    assert data['workflow_id'] == 'char_alpha'
    assert data['asset_type'] == 'transparent_sprite'
    assert data['source_image'] == str(source.resolve())
    assert data['prepare_only'] is True
    assert data['qa_status'] == 'prepare_only'
    assert data['promotion_status'] == 'not_promoted'
    staged = Path(data['staged_source_image'])
    assert staged.exists()
    assert staged.read_bytes() == source.read_bytes()
    patched = json.loads(Path(data['patched_workflow_path']).read_text(encoding='utf-8'))
    assert patched['1']['inputs']['image'] == staged.name
    assert patched['3']['inputs']['filename_prefix'].startswith('hermes_vn_char_alpha/')


def test_char_alpha_refuses_external_source_image(tmp_path: Path):
    project, _, _ = make_project(tmp_path)
    outside = tmp_path / 'outside.png'
    outside.write_bytes(b'outside')

    proc = subprocess.run([
        sys.executable, str(SCRIPT),
        '--project-root', str(project),
        '--asset-id', 'alpha_fixture_sprite',
        '--source-image', str(outside),
        '--prepare-only',
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 2
    assert 'CHAR_ALPHA_REFUSED' in proc.stdout + proc.stderr


def test_char_alpha_source_metadata_uses_first_candidate_copy(tmp_path: Path):
    project, _, source = make_project(tmp_path)
    source_meta = project / 'docs/automation/generation_runs/source_run/metadata.json'
    write_json(source_meta, {
        'run_id': 'source_run',
        'asset_id': 'source_char_base',
        'asset_type': 'character_base',
        'candidate_copies': [str(source)],
    })
    out_meta = project / 'docs/automation/generation_runs/alpha_from_meta/metadata.json'

    proc = subprocess.run([
        sys.executable, str(SCRIPT),
        '--project-root', str(project),
        '--asset-id', 'alpha_from_source_meta',
        '--source-metadata', str(source_meta),
        '--prepare-only',
        '--out-metadata', str(out_meta),
    ], cwd=ROOT, text=True, capture_output=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(out_meta.read_text(encoding='utf-8'))
    assert data['source_metadata'] == str(source_meta.resolve())
    assert data['source_run_id'] == 'source_run'
    assert data['source_image'] == str(source.resolve())
