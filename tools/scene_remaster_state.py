from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, require_under, save_json  # noqa: E402

SAFE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,96}$')
ALLOWED_STATUS = {
    'draft_patch',
    'implemented_pending_qa',
    'qa_partial_pass',
    'owner_review_pending',
    'owner_approved',
    'integrated_baseline',
    'rejected_or_superseded',
}
ALLOWED_ASSET_POLICY = {
    'no_permanent_asset_changes',
    'scene_local_preview_only',
    'approved_promotion_only',
}


def split_values(values: list[str]) -> list[str]:
    out: list[str] = []
    for raw in values:
        for part in raw.split(','):
            part = part.strip()
            if part:
                out.append(part)
    return out


def resolve_project_rel(project_root: Path, raw: str | None, label: str) -> str | None:
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = project_root / p
    p = p.resolve()
    require_under(p, project_root, label)
    return p.relative_to(project_root).as_posix()


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def validate_existing_scene_state(paths: Any, scene_id: str) -> tuple[int, list[str], dict[str, Any]]:
    base = paths.docs_automation / 'scene_remaster'
    current_path = base / 'current_state.json'
    errors: list[str] = []
    summary: dict[str, Any] = {
        'current_state': current_path.relative_to(paths.project_root).as_posix(),
        'scene_id': scene_id,
    }

    if not current_path.exists():
        return 1, [f'missing current_state: {current_path}'], summary

    try:
        state = json.loads(current_path.read_text(encoding='utf-8'))
    except Exception as exc:
        return 1, [f'invalid current_state json: {exc}'], summary

    if state.get('scene_id') != scene_id:
        errors.append(f'current_state scene_id mismatch: {state.get("scene_id")} != {scene_id}')
    if state.get('asset_policy') != 'scene_local_preview_only':
        errors.append(f'current_state asset_policy is not scene_local_preview_only: {state.get("asset_policy")}')
    if bool(state.get('permanent_asset_changes')):
        errors.append('current_state permanent_asset_changes must be false for scene-local preview state')

    def require_project_rel(raw: str | None, label: str, required: bool = True) -> Path | None:
        if not raw:
            if required:
                errors.append(f'missing {label}')
            return None
        try:
            rel = resolve_project_rel(paths.project_root, raw, label)
        except Exception as exc:
            errors.append(f'invalid {label}: {exc}')
            return None
        p = paths.project_root / rel
        if not p.exists():
            errors.append(f'missing {label}: {rel}')
        return p

    qa_report = require_project_rel(state.get('latest_qa_report'), 'latest_qa_report')
    guard_report = require_project_rel(state.get('latest_guard_report'), 'latest_guard_report')
    patch_manifest_path = require_project_rel(state.get('patch_manifest'), 'patch_manifest')
    scene_pool_path = require_project_rel(state.get('scene_pool'), 'scene_pool')
    for idx, sheet in enumerate(state.get('capture_sheets') or []):
        require_project_rel(sheet, f'capture_sheet[{idx}]')

    patch_manifest: dict[str, Any] = {}
    if patch_manifest_path and patch_manifest_path.exists():
        try:
            patch_manifest = json.loads(patch_manifest_path.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append(f'invalid patch_manifest json: {exc}')
        else:
            if patch_manifest.get('scene_id') != scene_id:
                errors.append(f'patch_manifest scene_id mismatch: {patch_manifest.get("scene_id")} != {scene_id}')
            if patch_manifest.get('asset_policy') != state.get('asset_policy'):
                errors.append('patch_manifest asset_policy does not match current_state')
            if bool(patch_manifest.get('permanent_asset_changes')) != bool(state.get('permanent_asset_changes')):
                errors.append('patch_manifest permanent_asset_changes does not match current_state')
            if qa_report and patch_manifest.get('qa_report') != state.get('latest_qa_report'):
                errors.append('patch_manifest qa_report does not match current_state latest_qa_report')
            if guard_report and patch_manifest.get('guard_report') != state.get('latest_guard_report'):
                errors.append('patch_manifest guard_report does not match current_state latest_guard_report')

    pool: dict[str, Any] = {}
    if scene_pool_path and scene_pool_path.exists():
        try:
            pool = json.loads(scene_pool_path.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append(f'invalid scene_pool json: {exc}')
        else:
            if pool.get('scene_id') != scene_id:
                errors.append(f'scene_pool scene_id mismatch: {pool.get("scene_id")} != {scene_id}')
            if pool.get('policy') != 'scene_local_preview_only':
                errors.append(f'scene_pool policy is not scene_local_preview_only: {pool.get("policy")}')
            if pool.get('global_replacement_allowed') is not False:
                errors.append('scene_pool global_replacement_allowed must be false')
            if pool.get('promotion_requires_owner_approval') is not True:
                errors.append('scene_pool promotion_requires_owner_approval must be true')
            candidates = pool.get('candidates') or []
            if state.get('candidate_count') is not None and state.get('candidate_count') != len(candidates):
                errors.append(f'candidate_count mismatch: current_state={state.get("candidate_count")} pool={len(candidates)}')
            for idx, candidate in enumerate(candidates):
                cid = candidate.get('candidate_id') or f'index_{idx}'
                if candidate.get('approved') is not False:
                    errors.append(f'candidate {cid} approved must be false in preview pool')
                if candidate.get('promotion_allowed') is not False:
                    errors.append(f'candidate {cid} promotion_allowed must be false in preview pool')
                require_project_rel(candidate.get('path'), f'candidate {cid} path')

    summary.update({
        'status': state.get('status'),
        'latest_patch_id': state.get('latest_patch_id'),
        'approval_status': state.get('approval_status'),
        'asset_policy': state.get('asset_policy'),
        'permanent_asset_changes': bool(state.get('permanent_asset_changes')),
        'qa_report': state.get('latest_qa_report'),
        'guard_report': state.get('latest_guard_report'),
        'patch_manifest': state.get('patch_manifest'),
        'scene_pool': state.get('scene_pool'),
        'candidate_count': len(pool.get('candidates') or []) if pool else None,
        'errors': errors,
    })
    return (1 if errors else 0), errors, summary


def update_scene_pool(pool_path: Path, project_root: Path, scene_id: str, candidate_values: list[str]) -> dict[str, Any]:
    pool = load_json(pool_path, {
        'schema_version': 1,
        'scene_id': scene_id,
        'policy': 'scene_local_preview_only',
        'global_replacement_allowed': False,
        'promotion_requires_owner_approval': True,
        'candidates': [],
        'updated_at': None,
    })
    if pool.get('scene_id') != scene_id:
        raise ValueError(f'scene pool scene_id mismatch: {pool.get("scene_id")} != {scene_id}')
    existing = {item.get('candidate_id'): item for item in pool.get('candidates', []) if isinstance(item, dict)}
    for raw in candidate_values:
        # Format: candidate_id|asset_type|path|purpose. Only candidate_id is required.
        parts = [part.strip() for part in raw.split('|')]
        candidate_id = parts[0]
        if not SAFE_ID_RE.fullmatch(candidate_id):
            raise ValueError(f'unsafe candidate_id: {candidate_id}')
        asset_type = parts[1] if len(parts) > 1 and parts[1] else 'unknown'
        rel_path = resolve_project_rel(project_root, parts[2], f'candidate {candidate_id}') if len(parts) > 2 and parts[2] else None
        purpose = parts[3] if len(parts) > 3 else ''
        item = existing.get(candidate_id, {})
        item.update({
            'candidate_id': candidate_id,
            'asset_type': asset_type,
            'path': rel_path,
            'purpose': purpose,
            'status': item.get('status') or 'preview_reference_only',
            'approved': bool(item.get('approved', False)),
            'promotion_allowed': bool(item.get('promotion_allowed', False)),
            'updated_at': datetime.now().isoformat(timespec='seconds'),
        })
        existing[candidate_id] = item
    pool['candidates'] = sorted(existing.values(), key=lambda item: item.get('candidate_id', ''))
    pool['updated_at'] = datetime.now().isoformat(timespec='seconds')
    pool['global_replacement_allowed'] = False
    pool['promotion_requires_owner_approval'] = True
    pool['policy'] = 'scene_local_preview_only'
    save_json(pool_path, pool)
    return pool


def write_markdown_summary(path: Path, state: dict[str, Any]) -> None:
    lines = [
        f"# Scene Remaster State — {state['scene_id']}",
        '',
        f"- updated_at: `{state['updated_at']}`",
        f"- status: `{state['status']}`",
        f"- latest_patch_id: `{state.get('latest_patch_id') or ''}`",
        f"- approval_status: `{state['approval_status']}`",
        f"- asset_policy: `{state['asset_policy']}`",
        f"- permanent_asset_changes: `{state['permanent_asset_changes']}`",
        f"- latest_qa_report: `{state.get('latest_qa_report') or ''}`",
        f"- patch_manifest: `{state.get('patch_manifest') or ''}`",
        f"- scene_pool: `{state.get('scene_pool') or ''}`",
        '',
        '## Known Blockers',
    ]
    blockers = state.get('known_blockers') or []
    if blockers:
        lines.extend(f'- {item}' for item in blockers)
    else:
        lines.append('- none recorded')
    lines.extend(['', '## Next Recommended Patch'])
    next_steps = state.get('next_recommended_patch') or []
    if next_steps:
        lines.extend(f'- {item}' for item in next_steps)
    else:
        lines.append('- none recorded')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Write deterministic scene-local remaster state, patch manifest, and preview-only candidate pool files.')
    parser.add_argument('--project-root')
    parser.add_argument('--contract')
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--patch-id', default='')
    parser.add_argument('--status', choices=sorted(ALLOWED_STATUS))
    parser.add_argument('--approval-status', default='pending')
    parser.add_argument('--asset-policy', default='no_permanent_asset_changes', choices=sorted(ALLOWED_ASSET_POLICY))
    parser.add_argument('--permanent-asset-changes', action='store_true')
    parser.add_argument('--changed-file', action='append', default=[])
    parser.add_argument('--qa-report', default='')
    parser.add_argument('--guard-report', default='')
    parser.add_argument('--capture-sheet', action='append', default=[])
    parser.add_argument('--known-blocker', action='append', default=[])
    parser.add_argument('--next-step', action='append', default=[])
    parser.add_argument('--candidate', action='append', default=[], help='Scene-local preview candidate: candidate_id|asset_type|project/path|purpose')
    parser.add_argument('--check-existing', action='store_true', help='Validate existing current_state/patch/pool links without writing files.')
    args = parser.parse_args(argv)

    if not SAFE_ID_RE.fullmatch(args.scene_id):
        print(f'SCENE_REMASTER_STATE_REFUSED: unsafe scene_id: {args.scene_id}')
        return 2
    if args.patch_id and not SAFE_ID_RE.fullmatch(args.patch_id):
        print(f'SCENE_REMASTER_STATE_REFUSED: unsafe patch_id: {args.patch_id}')
        return 2
    if args.permanent_asset_changes and args.asset_policy != 'approved_promotion_only':
        print('SCENE_REMASTER_STATE_REFUSED: permanent asset changes require --asset-policy approved_promotion_only')
        return 2

    paths = build_project_paths(args.project_root, args.contract)
    if args.check_existing:
        rc, errors, summary = validate_existing_scene_state(paths, args.scene_id)
        print('SCENE_REMASTER_STATE_CHECK_' + ('PASSED' if rc == 0 else 'FAILED'))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        for error in errors:
            print('-', error)
        return rc
    if not args.status:
        print('SCENE_REMASTER_STATE_REFUSED: --status is required unless --check-existing is used')
        return 2

    base = paths.docs_automation / 'scene_remaster'
    states_dir = base / 'states'
    pools_dir = base / 'scene_pools'
    patches_dir = base / 'patches'
    pool_path = pools_dir / f'{args.scene_id}.json'
    patch_id = args.patch_id or f'{args.scene_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    patch_manifest_path = patches_dir / f'{patch_id}.json'

    try:
        changed_files = [resolve_project_rel(paths.project_root, raw, 'changed file') for raw in split_values(args.changed_file)]
        capture_sheets = [resolve_project_rel(paths.project_root, raw, 'capture sheet') for raw in split_values(args.capture_sheet)]
        qa_report = resolve_project_rel(paths.project_root, args.qa_report, 'qa report')
        guard_report = resolve_project_rel(paths.project_root, args.guard_report, 'guard report')
        pool = update_scene_pool(pool_path, paths.project_root, args.scene_id, split_values(args.candidate))
    except Exception as exc:
        print(f'SCENE_REMASTER_STATE_REFUSED: {exc}')
        return 2

    patch_manifest = {
        'schema_version': 1,
        'patch_id': patch_id,
        'scene_id': args.scene_id,
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'status': args.status,
        'approval_status': args.approval_status,
        'asset_policy': args.asset_policy,
        'permanent_asset_changes': bool(args.permanent_asset_changes),
        'changed_files': changed_files,
        'qa_report': qa_report,
        'guard_report': guard_report,
        'capture_sheets': capture_sheets,
        'known_blockers': split_values(args.known_blocker),
        'next_recommended_patch': split_values(args.next_step),
        'scene_pool': pool_path.relative_to(paths.project_root).as_posix(),
    }
    save_json(patch_manifest_path, patch_manifest)

    state = {
        'schema_version': 1,
        'scene_id': args.scene_id,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
        'status': args.status,
        'latest_patch_id': patch_id,
        'approval_status': args.approval_status,
        'asset_policy': args.asset_policy,
        'permanent_asset_changes': bool(args.permanent_asset_changes),
        'changed_files': changed_files,
        'latest_qa_report': qa_report,
        'latest_guard_report': guard_report,
        'capture_sheets': capture_sheets,
        'known_blockers': split_values(args.known_blocker),
        'next_recommended_patch': split_values(args.next_step),
        'patch_manifest': patch_manifest_path.relative_to(paths.project_root).as_posix(),
        'scene_pool': pool_path.relative_to(paths.project_root).as_posix(),
        'candidate_count': len(pool.get('candidates', [])),
    }
    state_path = states_dir / f'{args.scene_id}.json'
    save_json(state_path, state)
    save_json(base / 'current_state.json', state)
    write_markdown_summary(base / 'current_state.md', state)

    print('SCENE_REMASTER_STATE_WRITTEN')
    print('state', state_path)
    print('current_state', base / 'current_state.json')
    print('patch_manifest', patch_manifest_path)
    print('scene_pool', pool_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
