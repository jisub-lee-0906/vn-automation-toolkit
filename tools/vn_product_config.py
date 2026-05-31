from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_REL = Path('docs/automation/project_contract.json')
DEFAULT_MANIFEST_REL = Path('game/data/asset_manifest.json')
DEFAULT_GENERATION_RUNS_REL = Path('docs/automation/generation_runs')
DEFAULT_CANDIDATES_REL = Path('docs/automation/generated_candidates')
DEFAULT_PROMOTIONS_REL = Path('docs/production/promotions')


def resolve_project_root(raw: str | Path | None = None) -> Path:
    """Resolve a Ren'Py automation project root without hardcoding a title path.

    Priority:
    1. explicit CLI value
    2. VN_AUTOMATION_PROJECT_ROOT environment variable
    3. current repository root inferred from this tools/ directory
    """
    value = raw or os.environ.get('VN_AUTOMATION_PROJECT_ROOT')
    return Path(value).expanduser().resolve() if value else DEFAULT_PROJECT_ROOT.resolve()


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def contract_path(project_root: Path, raw: str | Path | None = None) -> Path:
    return Path(raw).expanduser().resolve() if raw else project_root / DEFAULT_CONTRACT_REL


def load_contract(project_root: Path, raw: str | Path | None = None) -> dict[str, Any]:
    return load_json(contract_path(project_root, raw), default={})


def path_from_contract(
    project_root: Path,
    contract: dict[str, Any],
    key: str,
    default_rel: str | Path,
) -> Path:
    raw = contract.get(key)
    if raw:
        return Path(raw).expanduser().resolve()
    return project_root / Path(default_rel)


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    contract: dict[str, Any]
    contract_file: Path
    game_dir: Path
    manifest: Path
    generation_runs_root: Path
    candidates_root: Path
    promotions_root: Path
    docs_automation: Path
    docs_production: Path


def build_project_paths(project_root: str | Path | None = None, contract: str | Path | None = None) -> ProjectPaths:
    root = resolve_project_root(project_root)
    cfile = contract_path(root, contract)
    data = load_json(cfile, default={})
    game_dir = Path(data.get('renpy_game_dir') or root / 'game').expanduser().resolve()
    return ProjectPaths(
        project_root=root,
        contract=data,
        contract_file=cfile,
        game_dir=game_dir,
        manifest=path_from_contract(root, data, 'manifest_path', DEFAULT_MANIFEST_REL),
        generation_runs_root=path_from_contract(root, data, 'generation_runs_root', DEFAULT_GENERATION_RUNS_REL),
        candidates_root=path_from_contract(root, data, 'generated_candidates_root', DEFAULT_CANDIDATES_REL),
        promotions_root=path_from_contract(root, data, 'promotion_log_root', DEFAULT_PROMOTIONS_REL),
        docs_automation=root / 'docs/automation',
        docs_production=root / 'docs/production',
    )


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--project-root', default=None, help='Ren\'Py/VN project root. Defaults to VN_AUTOMATION_PROJECT_ROOT or repo root.')
    parser.add_argument('--contract', help='Path to project_contract.json. Defaults to docs/automation/project_contract.json under project root.')


def require_under(child: Path, parent: Path, label: str = 'path') -> None:
    child_r = child.resolve()
    parent_r = parent.resolve()
    if parent_r != child_r and parent_r not in child_r.parents:
        raise ValueError(f'Unsafe {label} outside {parent}: {child}')
