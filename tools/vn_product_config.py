from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONTRACT_REL = Path('docs/automation/project_contract.json')
DEFAULT_MANIFEST_REL = Path('game/data/asset_manifest.json')
DEFAULT_GENERATION_RUNS_REL = Path('docs/automation/generation_runs')
DEFAULT_CANDIDATES_REL = Path('docs/automation/generated_candidates')
DEFAULT_PROMOTIONS_REL = Path('docs/production/promotions')


class ProjectSelectionError(RuntimeError):
    pass


def resolve_project_root(raw: str | Path | None = None) -> Path:
    """Resolve the active Ren'Py automation project root fail-closed.

    Priority:
    1. explicit CLI value
    2. VN_AUTOMATION_PROJECT_ROOT environment variable
    3. current working directory when it contains docs/automation/project_contract.json

    The toolkit repository is deliberately not an implicit project fallback.
    Multi-title safety depends on failing closed rather than silently checking the
    wrong title.
    """
    if raw:
        return Path(raw).expanduser().resolve()
    env_value = os.environ.get('VN_AUTOMATION_PROJECT_ROOT')
    cwd = Path.cwd().resolve()
    cwd_has_contract = (cwd / DEFAULT_CONTRACT_REL).exists()
    if env_value:
        env_root = Path(env_value).expanduser().resolve()
        if cwd_has_contract and env_root != cwd:
            raise ProjectSelectionError(
                f'PROJECT_SELECTION_CONFLICT: VN_AUTOMATION_PROJECT_ROOT={env_root} differs from cwd project {cwd}; pass --project-root explicitly'
            )
        return env_root
    if cwd_has_contract:
        return cwd
    raise ProjectSelectionError(
        'PROJECT_SELECTION_REQUIRED: pass --project-root, set VN_AUTOMATION_PROJECT_ROOT, '
        'or run from a RenPy project root containing docs/automation/project_contract.json'
    )


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
    path = Path(raw).expanduser().resolve() if raw else (project_root / DEFAULT_CONTRACT_REL).resolve()
    require_under(path, project_root, 'contract')
    return path


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
    try:
        root = resolve_project_root(project_root)
        cfile = contract_path(root, contract)
        if not cfile.exists():
            raise ValueError(f'project_contract.json missing: {cfile}')
        try:
            data = load_json(cfile)
        except json.JSONDecodeError as exc:
            raise ValueError(f'project_contract.json invalid JSON: {exc}') from exc
        contract_root_raw = data.get('renpy_project_root') or data.get('project_root')
        if contract_root_raw and Path(contract_root_raw).expanduser().resolve() != root:
            raise ValueError('renpy_project_root must match selected project_root')
        game_dir = Path(data.get('renpy_game_dir') or root / 'game').expanduser().resolve()
        manifest = path_from_contract(root, data, 'manifest_path', DEFAULT_MANIFEST_REL)
        generation_runs_root = path_from_contract(root, data, 'generation_runs_root', DEFAULT_GENERATION_RUNS_REL)
        candidates_root = path_from_contract(root, data, 'generated_candidates_root', DEFAULT_CANDIDATES_REL)
        promotions_root = path_from_contract(root, data, 'promotion_log_root', DEFAULT_PROMOTIONS_REL)
        for path, label in [
            (game_dir, 'renpy_game_dir'),
            (manifest, 'manifest_path'),
            (generation_runs_root, 'generation_runs_root'),
            (candidates_root, 'generated_candidates_root'),
            (promotions_root, 'promotion_log_root'),
        ]:
            require_under(path, root, label)
    except ProjectSelectionError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except ValueError as exc:
        print(f'PROJECT_CONTRACT_INVALID: {exc}', file=sys.stderr)
        raise SystemExit(2) from exc
    return ProjectPaths(
        project_root=root,
        contract=data,
        contract_file=cfile,
        game_dir=game_dir,
        manifest=manifest,
        generation_runs_root=generation_runs_root,
        candidates_root=candidates_root,
        promotions_root=promotions_root,
        docs_automation=root / 'docs/automation',
        docs_production=root / 'docs/production',
    )


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--project-root', default=None, help='Ren\'Py/VN project root. Defaults to VN_AUTOMATION_PROJECT_ROOT or cwd only when cwd has docs/automation/project_contract.json; otherwise fails closed.')
    parser.add_argument('--contract', help='Path to project_contract.json. Defaults to docs/automation/project_contract.json under project root.')


def require_under(child: Path, parent: Path, label: str = 'path') -> None:
    child_r = child.resolve()
    parent_r = parent.resolve()
    if parent_r != child_r and parent_r not in child_r.parents:
        raise ValueError(f'Unsafe {label} outside {parent}: {child}')


def resolve_project_path(project_root: Path, raw: str | Path, label: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    require_under(path, project_root, label)
    return path


def validate_project_glob(pattern: str, label: str = 'glob') -> None:
    normalized = str(pattern).replace('\\', '/')
    parts = normalized.split('/')
    if not pattern or Path(pattern).is_absolute() or normalized.startswith('/') or (parts and ':' in parts[0]):
        raise ValueError(f'{label} must be relative to project_root: {pattern}')
    if any(part == '..' for part in parts):
        raise ValueError(f'{label} must not contain parent traversal: {pattern}')
