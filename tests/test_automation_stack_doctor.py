from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_stack_doctor_checks_obsidian_root_without_external_services(tmp_path: Path) -> None:
    vault = tmp_path / 'vault'
    vault.mkdir()
    (vault / 'note.md').write_text('# Note\n', encoding='utf-8')
    report = tmp_path / 'stack_doctor.json'

    proc = run_cli(
        'stack-doctor',
        '--skip-hermes',
        '--skip-comfyui',
        '--obsidian-root',
        str(vault),
        '--json-out',
        str(report),
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'AUTOMATION_STACK_DOCTOR_PASS' in proc.stdout
    data = json.loads(report.read_text(encoding='utf-8'))
    assert data['status'] == 'PASS'
    assert data['components'][0]['component'] == 'obsidian'
    assert data['components'][0]['existing_roots'] == [str(vault)]


def test_stack_doctor_fails_when_required_obsidian_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / 'missing-vault'

    proc = run_cli(
        'stack-doctor',
        '--skip-hermes',
        '--skip-comfyui',
        '--obsidian-root',
        str(missing),
    )

    assert proc.returncode == 1
    assert 'AUTOMATION_STACK_DOCTOR_FAIL' in proc.stdout
    assert 'no Obsidian root exists' in proc.stdout


def test_stack_doctor_validates_optional_roots(tmp_path: Path) -> None:
    vault = tmp_path / 'vault'
    workflow_pack = tmp_path / 'workflow-pack'
    output_root = tmp_path / 'comfy-output'
    for path in [vault, workflow_pack, output_root]:
        path.mkdir()
    (vault / 'index.md').write_text('# Index\n', encoding='utf-8')

    proc = run_cli(
        'stack-doctor',
        '--skip-hermes',
        '--skip-comfyui',
        '--obsidian-root',
        str(vault),
        '--workflow-pack-root',
        str(workflow_pack),
        '--comfy-output-root',
        str(output_root),
        '--strict',
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert '[workflow_pack_root] ok=True' in proc.stdout
    assert '[comfy_output_root] ok=True' in proc.stdout
