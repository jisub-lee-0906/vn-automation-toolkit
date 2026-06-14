import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BATCH_SCRIPT = ROOT / 'tools/run_scene_event_cg_batch.py'
SHEET_SCRIPT = ROOT / 'tools/make_event_cg_contact_sheet.py'


def test_scene_event_cg_batch_dry_run_creates_prompt_slots_and_summary(tmp_path: Path):
    project = tmp_path / 'game'
    (project / 'docs/production/prompt_slots').mkdir(parents=True)
    char_meta = project / 'docs/automation/generation_runs/char_base/metadata.json'
    char_meta.parent.mkdir(parents=True)
    char_meta.write_text(json.dumps({'run_id': 'char_base', 'asset_type': 'char_base', 'seed': 123}), encoding='utf-8')
    proc = subprocess.run(
        [
            sys.executable,
            str(BATCH_SCRIPT),
            '--project-root',
            str(project),
            '--asset-id-prefix',
            'event_auto_sad',
            '--emotion',
            'sad',
            '--framing',
            'default',
            '--seeds',
            '11,12',
            '--char-base-metadata',
            str(char_meta),
            '--character-features',
            'blue_eyes,blonde_hair,long_hair',
            '--outfit-detail',
            'red_dress,jewelry',
            '--scene-context',
            'ballroom,chandelier',
            '--dry-run',
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = project / 'docs/automation/batches/event_auto_sad_scene_event_cg_batch.json'
    data = json.loads(summary.read_text(encoding='utf-8'))
    assert data['dry_run'] is True
    assert [item['seed'] for item in data['items']] == [11, 12]
    assert data['items'][0]['scene_event_route_mode'] == 'production_character_front'
    for item in data['items']:
        assert Path(item['prompt_slots']).exists()
        assert '--prepare-only' in item['command']
        assert item['review_gate'] is None
        assert item['executable'] is True
        assert item['reference_conditioning']['status'] == 'not_requested'
        assert item['subjects'] == []


def test_scene_event_cg_batch_fails_without_project_specific_tags(tmp_path: Path):
    project = tmp_path / 'game'
    char_meta = project / 'docs/automation/generation_runs/char_base/metadata.json'
    char_meta.parent.mkdir(parents=True)
    char_meta.write_text(json.dumps({'run_id': 'char_base'}), encoding='utf-8')
    proc = subprocess.run(
        [sys.executable, str(BATCH_SCRIPT), '--project-root', str(project), '--asset-id-prefix', 'event_auto', '--emotion', 'sad', '--framing', 'default', '--seeds', '11', '--char-base-metadata', str(char_meta), '--dry-run'],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode != 0
    assert 'SCENE_EVENT_CG_CHARACTER_FEATURES_REQUIRED' in proc.stderr + proc.stdout


def test_scene_event_cg_batch_confines_asset_id_and_output_paths(tmp_path: Path):
    project = tmp_path / 'game'
    char_meta = project / 'docs/automation/generation_runs/char_base/metadata.json'
    char_meta.parent.mkdir(parents=True)
    char_meta.write_text(json.dumps({'run_id': 'char_base'}), encoding='utf-8')
    proc = subprocess.run(
        [
            sys.executable, str(BATCH_SCRIPT), '--project-root', str(project), '--asset-id-prefix', '../bad prefix',
            '--emotion', 'sad', '--framing', 'default', '--seeds', '11', '--char-base-metadata', str(char_meta),
            '--character-features', 'blue_eyes', '--outfit-detail', 'red_dress', '--scene-context', 'ballroom',
            '--output', str(tmp_path / 'outside.json'), '--dry-run'
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode != 0
    assert 'OUTPUT_MUST_BE_UNDER_PROJECT_ROOT' in proc.stderr + proc.stdout


def test_scene_event_cg_batch_writes_multichar_reference_preflight_prompt_slots(tmp_path: Path):
    project = tmp_path / 'game'
    char_meta = project / 'docs/automation/generation_runs/char_base/metadata.json'
    char_meta.parent.mkdir(parents=True)
    char_meta.write_text(json.dumps({'run_id': 'char_base', 'seed': 123}), encoding='utf-8')
    ref = project / 'images/characters/serena_ref.png'
    ref.parent.mkdir(parents=True)
    ref.write_bytes(b'not-a-real-image-for-preflight-path-only')
    proc = subprocess.run(
        [
            sys.executable, str(BATCH_SCRIPT), '--project-root', str(project), '--asset-id-prefix', 'event_pair',
            '--emotion', 'serious', '--framing', 'two_shot', '--subject-count', '2', '--subjects', 'serena,lucian',
            '--interaction', 'confrontation', '--reference-conditioning-mode', 'identity_reference',
            '--reference-assets', str(ref), '--reference-reason', 'identity lock preflight only',
            '--seeds', '11', '--char-base-metadata', str(char_meta),
            '--character-features', 'blue_eyes', '--outfit-detail', 'red_dress', '--scene-context', 'ballroom',
            '--dry-run'
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    prompt_slots = project / 'docs/production/prompt_slots/event_pair_s11.json'
    data = json.loads(prompt_slots.read_text(encoding='utf-8'))
    assert data['subject_count'] == 2
    assert data['subjects'] == ['serena', 'lucian']
    assert data['interaction'] == 'confrontation'
    assert data['executable'] is False
    assert data['review_gate'] == 'multi_character_reference_required'
    assert data['reference_conditioning']['mode'] == 'identity_reference'
    assert data['reference_conditioning']['approval_required'] is True
    summary = project / 'docs/automation/batches/event_pair_scene_event_cg_batch.json'
    summary_data = json.loads(summary.read_text(encoding='utf-8'))
    item = summary_data['items'][0]
    assert item['review_gate'] == 'multi_character_reference_required'
    assert item['executable'] is False
    assert item['reference_conditioning']['status'] == 'preflight_required_not_executable_by_default'
    assert item['subject_count'] == 2
    assert item['subjects'] == ['serena', 'lucian']
    assert item['interaction'] == 'confrontation'


def test_make_event_cg_contact_sheet_from_batch_summary(tmp_path: Path):
    project = tmp_path / 'game'
    img_dir = project / 'docs/automation/generated_candidates/event_cg/run_a'
    img_dir.mkdir(parents=True)
    img = img_dir / 'candidate_01.png'
    Image.new('RGB', (320, 180), (120, 80, 40)).save(img)
    batch_dir = project / 'docs/automation/batches'
    batch_dir.mkdir(parents=True)
    summary = batch_dir / 'batch.json'
    summary.write_text(json.dumps({
        'items': [{
            'asset_id': 'event_a',
            'seed': 11,
            'run_id': 'run_a',
            'candidate': str(img),
            'emotion': 'sad',
            'framing': 'default',
        }]
    }), encoding='utf-8')
    out = project / 'docs/automation/generated_candidates/event_cg/contact.jpg'
    proc = subprocess.run(
        [sys.executable, str(SHEET_SCRIPT), '--batch-summary', str(summary), '--output', str(out)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()
    assert (project / 'docs/automation/generated_candidates/event_cg/contact_face.jpg').exists()
    qa_summary = project / 'docs/automation/generated_candidates/event_cg/contact_qa_summary.json'
    assert qa_summary.exists()
    qa = json.loads(qa_summary.read_text(encoding='utf-8'))
    assert qa['image_count'] == 1
    assert qa['missing_candidate_count'] == 0
    assert qa['requires_owner_review'] is True
    assert qa['promotion_status'] == 'not_promoted_pending_owner_approval'


def test_make_event_cg_contact_sheet_flags_blank_black_and_low_variance(tmp_path: Path):
    project = tmp_path / 'game'
    img_dir = project / 'docs/automation/generated_candidates/event_cg/run_black'
    img_dir.mkdir(parents=True)
    black = img_dir / 'black.png'
    white = img_dir / 'white.png'
    flat = img_dir / 'flat.png'
    Image.new('RGB', (320, 180), (0, 0, 0)).save(black)
    Image.new('RGB', (320, 180), (255, 255, 255)).save(white)
    Image.new('RGB', (320, 180), (120, 120, 120)).save(flat)
    summary = project / 'docs/automation/batches/batch.json'
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({'items': [
        {'asset_id': 'black', 'candidate': str(black)},
        {'asset_id': 'white', 'candidate': str(white)},
        {'asset_id': 'flat', 'candidate': str(flat)},
    ]}), encoding='utf-8')
    out = project / 'docs/automation/generated_candidates/event_cg/contact.jpg'
    proc = subprocess.run(
        [sys.executable, str(SHEET_SCRIPT), '--batch-summary', str(summary), '--output', str(out)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    qa = json.loads((project / 'docs/automation/generated_candidates/event_cg/contact_qa_summary.json').read_text(encoding='utf-8'))
    warning_kinds = {warning['warning'] for warning in qa['warnings']}
    assert 'mostly_black' in warning_kinds
    assert 'mostly_blank_white' in warning_kinds
    assert 'low_detail_low_variance' in warning_kinds
