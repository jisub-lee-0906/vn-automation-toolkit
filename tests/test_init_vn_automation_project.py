from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/init_vn_automation_project.py'


def test_init_vn_automation_project_dry_run_writes_nothing(tmp_path: Path):
    project = tmp_path / 'new_title'
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), '--project-root', str(project), '--dry-run'],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'dry_run True' in proc.stdout
    assert 'written 0' in proc.stdout
    assert not project.exists()


def test_init_vn_automation_project_creates_minimum_product_spine(tmp_path: Path):
    project = tmp_path / 'new_title'
    workflow_pack = tmp_path / 'workflow_pack'
    workflow_pack.mkdir()
    (workflow_pack / 'WORKFLOW_INDEX.json').write_text('{"workflows": []}', encoding='utf-8')
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            '--project-root', str(project),
            '--workflow-pack-root', str(workflow_pack),
            '--obsidian-vault', str(tmp_path / 'vault'),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (project / 'docs/automation/project_contract.json').exists()
    assert (project / 'docs/automation/templates/Scene_Note_Template.md').exists()
    assert (project / 'docs/automation/qa_checklist.md').exists()
    assert (project / 'docs/automation/schemas/asset_manifest.schema.json').exists()
    assert (project / 'game/data/asset_manifest.json').exists()
    manifest = json.loads((project / 'game/data/asset_manifest.json').read_text(encoding='utf-8'))
    assert manifest == {'version': '1.0.0', 'assets': []}
    contract = json.loads((project / 'docs/automation/project_contract.json').read_text(encoding='utf-8'))
    assert contract['renpy_project_root'] == project.resolve().as_posix()
    assert contract['manifest_path'].endswith('game/data/asset_manifest.json')
    assert contract['comfyui_output_root'].endswith('Documents/ComfyUI/output')
    assert contract['generated_candidates_root'].endswith('docs/automation/generated_candidates')
    assert contract['generation_runs_root'].endswith('docs/automation/generation_runs')
    assert contract['promotion_log_root'].endswith('docs/production/promotions')


def test_init_vn_automation_project_preserves_existing_without_force(tmp_path: Path):
    project = tmp_path / 'new_title'
    first = subprocess.run([sys.executable, str(SCRIPT), '--project-root', str(project)], cwd=ROOT, text=True, capture_output=True)
    assert first.returncode == 0
    scene_template = project / 'docs/automation/templates/Scene_Note_Template.md'
    scene_template.write_text('CUSTOM', encoding='utf-8')
    second = subprocess.run([sys.executable, str(SCRIPT), '--project-root', str(project)], cwd=ROOT, text=True, capture_output=True)
    assert second.returncode == 0
    assert scene_template.read_text(encoding='utf-8') == 'CUSTOM'
    forced = subprocess.run([sys.executable, str(SCRIPT), '--project-root', str(project), '--force'], cwd=ROOT, text=True, capture_output=True)
    assert forced.returncode == 0
    assert scene_template.read_text(encoding='utf-8') != 'CUSTOM'
