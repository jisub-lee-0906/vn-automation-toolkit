from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths  # noqa: E402

REQUIRED_CONTRACT_KEYS = [
    'obsidian_vault',
    'renpy_project_root',
    'renpy_game_dir',
    'renpy_sdk_exe',
    'workflow_pack_root',
    'workflow_index',
    'manifest_path',
]
REQUIRED_CONTRACT_METADATA_KEYS = [
    'game_title',
    'game_slug',
    'obsidian_project_root',
    'obsidian_scenes_glob',
]
EXPECTED_WORKFLOW_IDS = {
    'char_base',
    'char_expression',
    'char_alpha',
    'scene_background',
    'scene_prop_cg',
    'scene_event_cg',
    'audio_bgm_ace',
    'audio_sfx_mmaudio',
}
DESIGN_SECTIONS = [
    '## 1. 목표',
    '## 2. 고정 경로',
    '## 3. 역할 분담',
    '## 4. 데이터 흐름',
    '## 7. Workflow routing',
    '## 11. QA gates',
    '## 13. 첫 투입 milestone',
    '## 14. 금지 사항',
]
FORBIDDEN_DESIGN_TOKENS = ['/mnt/c', 'wsl.localhost', '172.28.', '/home/jisub-lee']
REQUIRED_PROJECT_RELS = [
    'docs/automation/templates/Scene_Note_Template.md',
    'docs/automation/templates/Character_Note_Template.md',
    'docs/automation/templates/Asset_Request_Template.md',
    'docs/automation/qa_checklist.md',
    'docs/automation/schemas/asset_manifest.schema.json',
    'docs/automation/schemas/character_asset.schema.json',
    'game/data/asset_manifest.json',
]
REQUIRED_OBSIDIAN_RELS = [
    '00_Index.md',
    'Automation/VN_Automation_Design.md',
    'Templates/Scene_Note_Template.md',
    'Templates/Character_Note_Template.md',
    'Templates/Asset_Request_Template.md',
]

SAFE_ASSET_ID_RE = re.compile(r'^[a-z][a-z0-9_]{1,80}$')
SAFE_RENPY_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*( [a-z0-9_]+)*$')


def is_safe_project_relative_path(value: str) -> bool:
    normalized = str(value).replace('\\', '/')
    parts = normalized.split('/')
    return bool(value) and not Path(value).is_absolute() and not normalized.startswith('/') and ':' not in normalized and '..' not in parts and not any(ord(ch) < 32 for ch in value)

REQUIRED_ASSET_KEYS = {
    'asset_id',
    'asset_type',
    'workflow_id',
    'generated_path',
    'promoted_path',
    'qa_status',
    'renpy_name',
    'scene_usage',
    'metadata',
}


def require(path: Path, label: str, errors: list[str]) -> Path:
    if not path.exists():
        errors.append(f'MISSING {label}: {path}')
    return path


def validate_contract(paths, errors: list[str]) -> None:
    contract_path = require(paths.contract_file, 'project_contract', errors)
    if not contract_path.exists():
        return
    contract = paths.contract
    for key in REQUIRED_CONTRACT_KEYS:
        if key not in contract:
            errors.append(f'CONTRACT missing key {key}')
        else:
            require(Path(contract[key]), key, errors)
    # Backward compatible normalization: older contracts did not store title-scoped
    # Obsidian metadata, but new init writes it. Validate the effective layout rather
    # than treating plain metadata values as filesystem paths.
    if not contract.get('game_title'):
        contract['game_title'] = Path(contract.get('renpy_project_root') or '').name.replace('_', ' ').replace('-', ' ').title()
    if not contract.get('game_slug'):
        contract['game_slug'] = Path(contract.get('renpy_project_root') or '').name.replace('-', '_').lower() or 'game'
    if not contract.get('obsidian_project_root') and contract.get('obsidian_vault'):
        contract['obsidian_project_root'] = str(Path(contract['obsidian_vault']) / 'VN')
    if not contract.get('obsidian_scenes_glob'):
        contract['obsidian_scenes_glob'] = 'Scenes/*.md' if contract.get('obsidian_project_root') else 'VN/Scenes/*.md'
    for key in REQUIRED_CONTRACT_METADATA_KEYS:
        if not contract.get(key):
            errors.append(f'CONTRACT missing key {key}')
    workflow_index = Path(contract.get('workflow_index', ''))
    workflow_root = Path(contract.get('workflow_pack_root', ''))
    if workflow_index.exists():
        data = json.loads(workflow_index.read_text(encoding='utf-8'))
        ids = []
        for wf in data.get('workflows', []):
            ids.append(wf.get('id'))
            for key in ['readme', 'api']:
                rel = wf.get(key)
                if rel and not (workflow_root / rel).exists():
                    errors.append(f'WORKFLOW {wf.get("id")} missing {key}: {rel}')
            if not wf.get('editable_fields'):
                errors.append(f'WORKFLOW {wf.get("id")} has no editable_fields')
        missing = EXPECTED_WORKFLOW_IDS - set(ids)
        if missing:
            errors.append(f'WORKFLOW_INDEX missing ids: {sorted(missing)}')


def validate_design(project_root: Path, errors: list[str]) -> None:
    doc = require(project_root / 'docs/automation/vn_automation_design.md', 'design_doc', errors)
    if not doc.exists():
        return
    text = doc.read_text(encoding='utf-8')
    for section in DESIGN_SECTIONS:
        if section not in text:
            errors.append(f'DESIGN missing section {section}')
    for token in FORBIDDEN_DESIGN_TOKENS:
        if token in text:
            errors.append(f'DESIGN contains stale path token {token}')


def validate_manifest(paths, errors: list[str]) -> None:
    manifest = paths.manifest
    if not manifest.exists():
        return
    data = json.loads(manifest.read_text(encoding='utf-8'))
    assets = data.get('assets')
    if not isinstance(assets, list):
        errors.append('asset_manifest.assets must be list')
        return
    seen = set()
    for idx, asset in enumerate(assets):
        if not isinstance(asset, dict):
            errors.append(f'asset_manifest.assets[{idx}] must be object')
            continue
        missing = REQUIRED_ASSET_KEYS - set(asset)
        if missing:
            errors.append(f'asset_manifest.assets[{idx}] missing keys: {sorted(missing)}')
        asset_id = asset.get('asset_id')
        if not isinstance(asset_id, str) or not SAFE_ASSET_ID_RE.fullmatch(asset_id):
            errors.append(f'asset_manifest.assets[{idx}] unsafe asset_id: {asset_id}')
        renpy_name = asset.get('renpy_name')
        if not isinstance(renpy_name, str) or not SAFE_RENPY_NAME_RE.fullmatch(renpy_name):
            errors.append(f'asset_manifest.assets[{idx}] unsafe renpy_name: {renpy_name!r}')
        if asset_id in seen:
            errors.append(f'asset_manifest duplicate asset_id: {asset_id}')
        seen.add(asset_id)
        promoted = asset.get('promoted_path')
        if promoted:
            if not isinstance(promoted, str) or not is_safe_project_relative_path(promoted):
                errors.append(f'asset_manifest.assets[{idx}] unsafe promoted_path: {promoted}')
                continue
            target = paths.game_dir / promoted
            if not target.exists():
                errors.append(f'asset_manifest promoted_path missing: {promoted}')


def validate_project(paths, validate_obsidian: bool = True) -> list[str]:
    errors: list[str] = []
    validate_contract(paths, errors)
    validate_design(paths.project_root, errors)
    for rel in REQUIRED_PROJECT_RELS:
        require(paths.project_root / rel, rel, errors)
    if validate_obsidian:
        obs_root_raw = paths.contract.get('obsidian_project_root') or paths.contract.get('obsidian_vault')
        if obs_root_raw:
            obs_root = Path(obs_root_raw)
            legacy_prefix = Path('VN') if not paths.contract.get('obsidian_project_root') else Path()
            for rel in REQUIRED_OBSIDIAN_RELS:
                require(obs_root / legacy_prefix / rel, 'obsidian:' + str(legacy_prefix / rel), errors)
        else:
            errors.append('CONTRACT missing obsidian_project_root/obsidian_vault for obsidian validation')
    validate_manifest(paths, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate VN automation project docs/contracts without hardcoded title paths.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--skip-obsidian', action='store_true')
    args = parser.parse_args(argv)
    paths = build_project_paths(args.project_root, args.contract)
    errors = validate_project(paths, validate_obsidian=not args.skip_obsidian)
    if errors:
        print('VALIDATION FAILED')
        for error in errors:
            print('-', error)
        return 1
    print('VALIDATION PASSED')
    print('project_root', paths.project_root)
    print('checked design, contract, workflow index, templates, schemas, manifest')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
