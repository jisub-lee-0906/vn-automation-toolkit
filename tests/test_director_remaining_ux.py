from __future__ import annotations

import json
from pathlib import Path

from test_director_ux_console import bootstrap_moonlit_library, run_cli


def create_opening_scene(project: Path) -> None:
    proc = run_cli(
        'director', 'new-scene',
        '--project-root', str(project),
        '--scene-id', 'opening_night_library',
        '--title', 'Opening Night Library',
        '--summary', 'The protagonist wakes after closing time while rain taps on the library windows.',
        '--goal', 'Make the player wonder whether the quiet librarian can be trusted.',
        '--choice', 'Who are you?',
        '--choice', 'Why do you know my name?',
        '--asset', 'background:bg_library_rainy_night|rainy night library interior, no characters',
        '--playable-placeholder',
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def seed_candidate(project: Path, asset_id: str = 'bg_library_rainy_night') -> Path:
    candidate = project / 'docs/automation/generated_candidates/backgrounds' / f'{asset_id}_candidate_a.png'
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b'fake png candidate for director UX tests')
    run_dir = project / 'docs/automation/generation_runs' / f'scene_background_{asset_id}_demo'
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        'run_id': f'scene_background_{asset_id}_demo',
        'asset_id': asset_id,
        'asset_type': 'background',
        'workflow_id': 'scene_background',
        'positive_prompt': f'{asset_id} rainy night library interior no characters',
        'candidate_copies': [str(candidate)],
        'qa_status': 'qa_pass_candidate_not_promoted',
        'promotion_status': 'not_promoted_pending_owner_approval',
        'seed': 1234,
    }
    metadata_path = run_dir / 'metadata.json'
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    return metadata_path


def test_director_review_assets_builds_candidate_cards_and_local_dashboard(tmp_path: Path):
    project, vault = bootstrap_moonlit_library(tmp_path)
    create_opening_scene(project)
    metadata_path = seed_candidate(project)

    sync = run_cli('sync', '--project-root', str(project), '--vault', str(vault), '--notes-glob', 'VN/Scenes/*.md')
    assert sync.returncode == 0, sync.stdout + sync.stderr
    queue = run_cli('queue', '--project-root', str(project))
    assert queue.returncode == 0, queue.stdout + queue.stderr

    proc = run_cli('director', 'review-assets', '--project-root', str(project))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'Asset Review Console' in proc.stdout
    assert 'bg_library_rainy_night' in proc.stdout
    assert 'candidate 1' in proc.stdout
    assert 'approve command' in proc.stdout

    card = project / 'docs/production/director_cards/asset_review.md'
    dashboard = project / 'docs/production/director_dashboard.html'
    assert card.exists()
    assert dashboard.exists()
    card_text = card.read_text(encoding='utf-8')
    html = dashboard.read_text(encoding='utf-8')
    assert str(metadata_path) in card_text
    assert 'vn-auto director approve-candidate' in card_text
    assert 'Moonlit Library' in html
    assert 'Asset Review' in html
    assert 'bg_library_rainy_night' in html
    assert '<img' in html


def test_director_preview_and_approve_candidate_close_the_review_loop(tmp_path: Path):
    project, vault = bootstrap_moonlit_library(tmp_path)
    create_opening_scene(project)
    metadata_path = seed_candidate(project)
    run_cli('sync', '--project-root', str(project), '--vault', str(vault), '--notes-glob', 'VN/Scenes/*.md')
    run_cli('queue', '--project-root', str(project))

    screenshot = project / 'docs/production/screenshots/opening_night_library_placeholder.png'
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b'fake screenshot')
    preview = run_cli(
        'director', 'preview',
        '--project-root', str(project),
        '--scene-id', 'opening_night_library',
        '--screenshot', str(screenshot),
        '--note', 'Placeholder flow is playable; asset mood still needs approval.',
    )
    assert preview.returncode == 0, preview.stdout + preview.stderr
    assert 'Preview Registered' in preview.stdout
    preview_card = project / 'docs/production/director_cards/opening_night_library_preview.md'
    assert preview_card.exists()
    assert str(screenshot) in preview_card.read_text(encoding='utf-8')

    approve = run_cli(
        'director', 'approve-candidate',
        '--project-root', str(project),
        '--metadata', str(metadata_path),
        '--asset-id', 'bg_library_rainy_night',
        '--asset-type', 'background',
        '--renpy-name', 'bg library_rainy_night',
        '--scene-usage', 'opening_night_library',
        '--approved',
    )
    assert approve.returncode == 0, approve.stdout + approve.stderr
    assert 'Candidate Approved And Promoted' in approve.stdout
    assert 'VERIFY_PASSED' in approve.stdout

    manifest = json.loads((project / 'game/data/asset_manifest.json').read_text(encoding='utf-8'))
    entry = next(asset for asset in manifest['assets'] if asset['asset_id'] == 'bg_library_rainy_night')
    assert entry['qa_status'] == 'owner_approved_promoted'
    assert (project / 'game' / entry['promoted_path']).exists()

    status = run_cli('director', 'status', '--project-root', str(project))
    assert status.returncode == 0, status.stdout + status.stderr
    assert 'Approval pending asset items: 0' in status.stdout
