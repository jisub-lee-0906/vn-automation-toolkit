
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, require_under  # noqa: E402


def status_line(name: str, ok: bool, detail: str = '') -> None:
    print(f'{name} {"PASS" if ok else "FAIL"}{(" " + detail) if detail else ""}')


def warn_line(name: str, detail: str) -> None:
    print(f'{name} WARN {detail}')


def endpoint_live(base: str, timeout: int = 3) -> bool:
    try:
        with urllib.request.urlopen(base.rstrip('/') + '/system_stats', timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Fail-closed cross-game preflight for a VN automation project.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--skip-comfyui', action='store_true')
    args = parser.parse_args(argv)
    paths = build_project_paths(args.project_root, args.contract)
    contract = paths.contract
    errors: list[str] = []
    warnings: list[str] = []

    print('VN_AUTO_PREFLIGHT')
    status_line('project_root', paths.project_root.exists(), str(paths.project_root))
    if not paths.project_root.exists():
        errors.append('project root missing')
    status_line('game_dir', paths.game_dir.exists(), str(paths.game_dir))
    if not paths.game_dir.exists():
        errors.append('RenPy game dir missing')
    else:
        try:
            require_under(paths.game_dir, paths.project_root, 'RenPy game dir')
        except ValueError:
            errors.append('renpy_game_dir must be under project_root')
    status_line('contract', paths.contract_file.exists(), str(paths.contract_file))
    if not paths.contract_file.exists():
        errors.append('project_contract.json missing')

    slug = contract.get('game_slug') or paths.project_root.name
    obs_root_raw = contract.get('obsidian_project_root') or ''
    if obs_root_raw:
        obs_root = Path(obs_root_raw).resolve()
        vault_raw = contract.get('obsidian_vault') or ''
        safe = slug in obs_root.parts and obs_root.name == 'VN'
        if vault_raw:
            vault = Path(vault_raw).resolve()
            under_vault = vault == obs_root or vault in obs_root.parents
            base_vault_layout = obs_root == (vault / slug / 'VN').resolve()
            dedicated_title_vault_layout = vault.name == slug and obs_root == (vault / 'VN').resolve()
            accepted_layout = base_vault_layout or dedicated_title_vault_layout
            safe = safe and under_vault and accepted_layout
            if not under_vault:
                errors.append('obsidian_project_root must be under obsidian_vault')
            elif not accepted_layout:
                errors.append('obsidian_project_root must be <obsidian_vault>/<game_slug>/VN or <game_slug vault>/VN')
        status_line('obsidian_scope', safe, obs_root.as_posix())
        if not safe and not vault_raw:
            errors.append('obsidian_project_root is not title-scoped as <...>/<game_slug>/VN')
    else:
        status_line('obsidian_scope', False, 'missing obsidian_project_root')
        errors.append('obsidian_project_root missing')

    scenes_glob = contract.get('obsidian_scenes_glob') or ''
    glob_safe = bool(scenes_glob) and not Path(scenes_glob).is_absolute() and '..' not in Path(scenes_glob).parts
    status_line('obsidian_scenes_glob', glob_safe, scenes_glob or 'missing')
    if not glob_safe:
        errors.append('obsidian_scenes_glob is unsafe or missing')

    manifest_ok = paths.manifest.exists()
    status_line('manifest', manifest_ok, str(paths.manifest))
    if not manifest_ok:
        errors.append('manifest missing')

    wf_root = Path(contract.get('workflow_pack_root') or '')
    wf_index_raw = contract.get('workflow_index') or ''
    wf_index = Path(wf_index_raw) if wf_index_raw else (wf_root / 'WORKFLOW_INDEX.json')
    workflow_ok = bool(str(wf_root)) and wf_root.exists() and wf_index.exists() and wf_index.is_file()
    if workflow_ok:
        try:
            require_under(wf_index.resolve(), wf_root.resolve(), 'workflow_index')
        except ValueError:
            workflow_ok = False
            errors.append('workflow_index must be under workflow_pack_root')
    status_line('workflow_pack', workflow_ok, f'root={wf_root} index={wf_index}')
    if not workflow_ok and not any('workflow_index must be under workflow_pack_root' in e for e in errors):
        errors.append('workflow pack root/index missing')

    sdk = Path(contract.get('renpy_sdk_exe') or '') if contract.get('renpy_sdk_exe') else None
    if sdk:
        status_line('renpy_sdk', sdk.exists(), str(sdk))
        if not sdk.exists():
            warnings.append('renpy_sdk path configured but missing')
    else:
        warn_line('renpy_sdk', 'not configured; runtime lint/smoke gates will be skipped until set')

    if args.skip_comfyui:
        warn_line('comfyui', 'skipped by --skip-comfyui')
    else:
        endpoint = contract.get('comfyui_endpoint') or 'http://127.0.0.1:8000'
        live = endpoint_live(endpoint)
        status_line('comfyui_endpoint', live, endpoint)
        if not live:
            warnings.append('ComfyUI endpoint not live')

    try:
        require_under(paths.manifest, paths.project_root, 'manifest')
    except ValueError as exc:
        errors.append(str(exc))

    if errors:
        print('PREFLIGHT_FAILED')
        for e in errors:
            print('-', e)
        return 1
    if warnings:
        print('PREFLIGHT_WARNINGS')
        for w in warnings:
            print('-', w)
    print('PREFLIGHT_PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
