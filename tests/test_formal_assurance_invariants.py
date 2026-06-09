from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
FORMAL_DOC = ROOT / 'docs/automation/FORMAL_INVARIANTS.md'


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


def make_project(tmp_path: Path, name: str = 'formal_title') -> Path:
    project = tmp_path / name
    game = project / 'game'
    workflow = tmp_path / 'workflow_pack'
    game.mkdir(parents=True)
    workflow.mkdir(parents=True, exist_ok=True)
    (game / 'script.rpy').write_text('label start:\n    return\n', encoding='utf-8')
    write_json(game / 'data/asset_manifest.json', {'version': '1.0.0', 'assets': []})
    write_json(workflow / 'WORKFLOW_INDEX.json', {'workflows': []})
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
        'obsidian_vault': (tmp_path / 'obsidian').as_posix(),
        'obsidian_project_root': (tmp_path / 'obsidian' / name / 'VN').as_posix(),
        'obsidian_scenes_glob': 'Scenes/*.md',
        'renpy_sdk_exe': '',
    })
    return project


def test_formal_invariants_document_exists_and_declares_scope():
    assert FORMAL_DOC.exists()
    text = FORMAL_DOC.read_text(encoding='utf-8')
    required = [
        'Invariant I1 — Project Selection Is Explicit',
        'Invariant I2 — Contract-Constrained Project Paths',
        'Invariant I3 — CLI Project Outputs Stay Under Project Root',
        'Invariant I4 — Project Inputs Cannot Cross Titles',
        'Invariant I5 — Capture Plans Are Bounded And Project-Local',
        'Out of Scope',
        'Assurance Evidence Matrix',
    ]
    for item in required:
        assert item in text


def test_every_cli_command_has_formal_assurance_classification():
    from vn_automation.cli import COMMANDS

    text = FORMAL_DOC.read_text(encoding='utf-8')
    for command in COMMANDS:
        assert f'`{command}`' in text, f'{command} missing from formal assurance matrix'


def test_project_path_helpers_are_deterministically_fuzzed(tmp_path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location('vn_product_config_under_test', TOOLS / 'vn_product_config.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    project = make_project(tmp_path)
    allowed_relatives = [
        'docs/automation/out.json',
        './docs/automation/nested/../out.json',
        'game/data/asset_manifest.json',
    ]
    rejected_paths = [
        '../escape.json',
        tmp_path / 'outside.json',
        project.parent / f'{project.name}_sibling' / 'out.json',
        '/tmp/outside.json',
    ]
    for raw in allowed_relatives:
        resolved = module.resolve_project_path(project, raw, 'fuzz')
        assert resolved.resolve() == project.resolve() or project.resolve() in resolved.resolve().parents
    for raw in rejected_paths:
        try:
            module.resolve_project_path(project, raw, 'fuzz')
        except ValueError:
            pass
        else:
            raise AssertionError(f'expected rejection for {raw!r}')

    valid_globs = ['docs/production/*.json', 'docs/**/asset_requests/*.json']
    invalid_globs = ['../outside/*.json', '/tmp/*.json', 'C:/tmp/*.json', 'docs/../outside/*.json']
    for pattern in valid_globs:
        module.validate_project_glob(pattern, 'resolved_glob')
    for pattern in invalid_globs:
        try:
            module.validate_project_glob(pattern, 'resolved_glob')
        except ValueError:
            pass
        else:
            raise AssertionError(f'expected glob rejection for {pattern!r}')


def test_contract_path_fuzz_rejects_all_project_sidecar_escapes(tmp_path: Path):
    project = make_project(tmp_path)
    contract_path = project / 'docs/automation/project_contract.json'
    outside_targets = {
        'renpy_game_dir': tmp_path / 'outside_game' / 'game',
        'manifest_path': tmp_path / 'outside_manifest.json',
        'generation_runs_root': tmp_path / 'outside_runs',
        'generated_candidates_root': tmp_path / 'outside_candidates',
        'promotion_log_root': tmp_path / 'outside_promotions',
    }
    for key, outside in outside_targets.items():
        contract = json.loads(contract_path.read_text(encoding='utf-8'))
        contract[key] = outside.as_posix()
        contract_path.write_text(json.dumps(contract), encoding='utf-8')
        proc = run_cli('preflight', '--project-root', str(project), '--skip-comfyui')
        assert proc.returncode == 2, key + proc.stdout + proc.stderr
        assert key in proc.stdout + proc.stderr

        # Restore a clean project for the next independent mutation.
        project = make_project(tmp_path, f'formal_title_{key}')
        contract_path = project / 'docs/automation/project_contract.json'


def test_cli_exposed_project_commands_use_scope_guards_or_are_classified():
    from vn_automation.cli import COMMANDS

    classifications = json.loads((ROOT / 'docs/automation/formal_assurance_command_matrix.json').read_text(encoding='utf-8'))
    assert set(classifications) == set(COMMANDS)

    project_commands = {name for name, meta in classifications.items() if meta['class'] == 'project'}
    for name in project_commands:
        script = TOOLS / COMMANDS[name][0]
        source = script.read_text(encoding='utf-8')
        guard_markers = [
            'build_project_paths(',
            'resolve_project_path(',
            'require_under(',
            'INIT_REFUSED',
        ]
        assert any(marker in source for marker in guard_markers), f'{name} lacks scope guard marker'
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'glob':
                # User-controlled project-root glob patterns must be paired with traversal validation and per-match confinement.
                # Fixed internal cleanup/report glob() calls are allowed when the command already uses build_project_paths/require_under.
                if '--resolved-glob' in source:
                    assert 'validate_project_glob(' in source and 'require_under(' in source, f'{name} has unguarded resolved glob()'


def test_formal_assurance_static_policy_rejects_missing_matrix_entry():
    matrix = json.loads((ROOT / 'docs/automation/formal_assurance_command_matrix.json').read_text(encoding='utf-8'))
    required_fields = {'class', 'project_selection', 'path_policy', 'evidence'}
    for command, meta in matrix.items():
        assert required_fields <= set(meta), command
        assert meta['class'] in {'project', 'non_project', 'bootstrap'}
        assert isinstance(meta['evidence'], list) and meta['evidence'], command
