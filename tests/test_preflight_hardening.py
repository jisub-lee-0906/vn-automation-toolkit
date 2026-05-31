from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_director_remaining_ux import create_opening_scene, seed_candidate
from test_director_ux_console import ROOT, bootstrap_moonlit_library, run_cli

PROMOTE_SCRIPT = ROOT / 'tools/promote_asset_candidate.py'


def run_promote(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROMOTE_SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_director_new_scene_refuses_to_overwrite_existing_scene_without_force(tmp_path: Path):
    project, vault = bootstrap_moonlit_library(tmp_path)
    create_opening_scene(project)
    note = vault / 'VN/Scenes/opening_night_library.md'
    draft = project / 'game/scripts/opening_night_library.rpy'
    note.write_text('OWNER EDITED NOTE\n', encoding='utf-8')
    draft.write_text('label owner_edited:\n    return\n', encoding='utf-8')

    proc = run_cli(
        'director', 'new-scene',
        '--project-root', str(project),
        '--scene-id', 'opening_night_library',
        '--title', 'Opening Night Library Rewrite',
        '--summary', 'Should not overwrite owner edits.',
        '--goal', 'Protect existing work.',
        '--asset', 'background:bg_library_rainy_night|same asset',
        '--playable-placeholder',
    )

    assert proc.returncode == 2
    assert 'DIRECTOR_REFUSED' in proc.stdout
    assert 'already exists' in proc.stdout
    assert note.read_text(encoding='utf-8') == 'OWNER EDITED NOTE\n'
    assert draft.read_text(encoding='utf-8') == 'label owner_edited:\n    return\n'


def test_promote_refuses_existing_destination_file_without_force(tmp_path: Path):
    project, _vault = bootstrap_moonlit_library(tmp_path)
    metadata_path = seed_candidate(project)
    existing = project / 'game/images/backgrounds/bg_library_rainy_night_candidate_a.png'
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b'existing approved asset bytes')

    proc = run_promote(
        str(metadata_path),
        '--project-root', str(project),
        '--asset-id', 'bg_library_rainy_night',
        '--asset-type', 'background',
        '--renpy-name', 'bg library rainy night',
        '--approved',
    )

    assert proc.returncode == 2
    assert 'PROMOTE_REFUSED' in proc.stdout
    assert 'destination already exists' in proc.stdout
    assert existing.read_bytes() == b'existing approved asset bytes'


def test_promote_refuses_existing_manifest_asset_id_without_replace(tmp_path: Path):
    project, _vault = bootstrap_moonlit_library(tmp_path)
    metadata_path = seed_candidate(project)
    manifest_path = project / 'game/data/asset_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['assets'].append({
        'asset_id': 'bg_library_rainy_night',
        'asset_type': 'background',
        'workflow_id': 'manual',
        'generated_path': 'manual',
        'promoted_path': 'images/backgrounds/original.png',
        'qa_status': 'owner_approved_promoted',
        'renpy_name': 'bg original',
        'scene_usage': [],
        'metadata': {},
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    proc = run_promote(
        str(metadata_path),
        '--project-root', str(project),
        '--asset-id', 'bg_library_rainy_night',
        '--asset-type', 'background',
        '--renpy-name', 'bg library rainy night',
        '--filename', 'new_candidate.png',
        '--approved',
    )

    assert proc.returncode == 2
    assert 'PROMOTE_REFUSED' in proc.stdout
    assert 'manifest asset_id already exists' in proc.stdout
    saved = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert saved['assets'][0]['promoted_path'] == 'images/backgrounds/original.png'


def test_director_approve_refuses_metadata_outside_project_root(tmp_path: Path):
    project, _vault = bootstrap_moonlit_library(tmp_path)
    outside = tmp_path / 'outside_metadata.json'
    candidate = tmp_path / 'outside_candidate.png'
    candidate.write_bytes(b'outside candidate')
    outside.write_text(json.dumps({
        'run_id': 'outside',
        'asset_id': 'bg_outside',
        'asset_type': 'background',
        'workflow_id': 'scene_background',
        'candidate_copies': [str(candidate)],
        'qa_status': 'qa_pass_candidate_not_promoted',
        'promotion_status': 'not_promoted_pending_owner_approval',
    }), encoding='utf-8')

    proc = run_cli(
        'director', 'approve-candidate',
        '--project-root', str(project),
        '--metadata', str(outside),
        '--asset-id', 'bg_outside',
        '--asset-type', 'background',
        '--renpy-name', 'bg outside',
        '--approved',
    )

    assert proc.returncode == 2
    assert 'APPROVE_REFUSED' in proc.stdout
    assert 'metadata outside project root' in proc.stdout
