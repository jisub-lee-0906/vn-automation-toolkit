import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/extract_scene_asset_requests.py'


def test_extract_scene_asset_requests_from_required_assets_and_suggestions(tmp_path: Path):
    project = tmp_path / 'project'
    scene_root = tmp_path / 'vault' / 'VN' / 'Scenes'
    scene_root.mkdir(parents=True)
    project.mkdir()
    note = scene_root / 'scene_010_test.md'
    note.write_text(
        '''---
type: scene
game_slug: test_vn
scene_id: scene_010_test
characters: [serena, lucian]
locations: [ballroom]
status: draft
---
# Scene 010

## Visual / Audio Direction
- Mood: tense ballroom public trap.
- Future review-only candidate: `event_cg_public_trap_ballroom`
- Audio cue candidate: `sfx_glass_crack`

## Required Assets
- [ ] background: bg_ballroom_night | ornate ballroom, night, visual novel background, no humans
- [x] ui: ui_red_system_alert_r04 | already approved system alert
- [ ] event_cg: event_cg_public_trap_ballroom | Serena and Lucian in a tense public trap, sad, default framing
- [ ] bgm: bgm_public_trap_waltz | tense minor waltz, low strings, ballroom pressure
- [ ] sfx: sfx_glass_crack | short glass crack cue
''',
        encoding='utf-8',
    )
    out = project / 'docs/automation/asset_requests/scene_010_test_asset_requests.json'
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--scene-note', str(note), '--output', str(out)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['scene_id'] == 'scene_010_test'
    assert data['game_slug'] == 'test_vn'
    assert len(data['asset_requests']) == 5
    by_id = {item['asset_id']: item for item in data['asset_requests']}
    assert by_id['bg_ballroom_night']['asset_type'] == 'background'
    assert by_id['bg_ballroom_night']['workflow_id'] == 'scene_background'
    assert by_id['ui_red_system_alert_r04']['status'] == 'already_satisfied_or_approved'
    assert by_id['event_cg_public_trap_ballroom']['workflow_id'] == 'scene_event_cg'
    assert by_id['bgm_public_trap_waltz']['workflow_id'] == 'audio_bgm_with_sfx'
    assert by_id['sfx_glass_crack']['workflow_id'] == 'audio_bgm_with_sfx'
    assert any(s['asset_id'] == 'event_cg_public_trap_ballroom' for s in data['candidate_suggestions'])
    stdout = json.loads(result.stdout)
    assert stdout['output'] == str(out)
    assert stdout['asset_request_count'] == 5


def test_extract_scene_asset_requests_directory_mode_writes_index(tmp_path: Path):
    scenes = tmp_path / 'Scenes'
    scenes.mkdir()
    for idx in [1, 2]:
        (scenes / f'scene_{idx:03d}.md').write_text(
            f'''---\ngame_slug: test_vn\nscene_id: scene_{idx:03d}\nstatus: draft\n---\n# Scene {idx}\n\n## Required Assets\n- [ ] background: bg_scene_{idx:03d} | room {idx}\n''',
            encoding='utf-8',
        )
    out_dir = tmp_path / 'asset_requests'
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--scenes-root', str(scenes), '--output', str(out_dir)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    stdout = json.loads(result.stdout)
    index = json.loads((out_dir / 'asset_request_index.json').read_text(encoding='utf-8'))
    assert stdout['scene_count'] == 2
    assert index['scene_count'] == 2
    assert index['total_asset_requests'] == 2
    assert (out_dir / 'scene_001_asset_requests.json').exists()
    assert (out_dir / 'scene_002_asset_requests.json').exists()


def test_extract_scene_asset_requests_adds_review_only_inferred_suggestions(tmp_path: Path):
    note = tmp_path / 'scene_infer.md'
    note.write_text(
        '''---\ngame_slug: test_vn\nscene_id: scene_infer\ncharacters: [serena, lucian]\nlocations: [ballroom]\nstatus: draft\n---\n# Scene Infer\n\n## Visual / Audio Direction\n- Serena confronts Lucian in a tense ballroom.\n- A red system alert flashes as glass cracks in the distance.\n- Mood: slow minor waltz with low strings.\n''',
        encoding='utf-8',
    )
    out = tmp_path / 'scene_infer_asset_requests.json'
    subprocess.run(
        [sys.executable, str(SCRIPT), '--scene-note', str(note), '--output', str(out)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['asset_requests'] == []
    inferred = data['review_only_inferred_suggestions']
    workflows = {item['workflow_id'] for item in inferred}
    assert 'scene_event_cg' in workflows
    assert 'ui_system_alert_frame' in workflows
    assert 'audio_bgm_with_sfx' in workflows
    assert all(item['status'] == 'review_only_inferred_not_requested' for item in inferred)


def test_extract_scene_asset_requests_keeps_unknown_required_asset_kinds_unresolved(tmp_path: Path):
    scene = tmp_path / 'scene_unknown.md'
    scene.write_text(
        '''---
scene_id: scene_unknown
---

## Required Assets
- [ ] heroine_placeholder: serena_temp | placeholder reference, not executable workflow
- [ ] background: bg_valid | valid background
''',
        encoding='utf-8',
    )
    out = tmp_path / 'out.json'
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--scene-note', str(scene), '--output', str(out)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(out.read_text(encoding='utf-8'))
    assert [item['asset_id'] for item in data['asset_requests']] == ['bg_valid']
    unresolved = data['unresolved_required_asset_mentions']
    assert unresolved[0]['asset_type'] == 'heroine_placeholder'
    assert unresolved[0]['status'] == 'unresolved_required_asset_kind_not_executable'
