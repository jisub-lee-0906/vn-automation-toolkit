from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from vn_product_config import build_project_paths, resolve_project_path, require_under  # noqa: E402
DEFAULT_CONTRACT = ROOT / 'docs/automation/project_contract.json'
DEFAULT_MANIFEST = ROOT / 'game/data/asset_manifest.json'
DEFAULT_CANDIDATES_ROOT = ROOT / 'docs/automation/generated_candidates'
DEFAULT_GENERATION_RUNS_ROOT = ROOT / 'docs/automation/generation_runs'

ASSET_TYPE_ALIASES = {
    'scene_background': 'background',
    'background': 'background',
    'scene_event_cg': 'event_cg',
    'event_cg': 'event_cg',
    'scene_prop_cg': 'prop_cg',
    'prop_cg': 'prop_cg',
    'character_base': 'character_base',
    'char_base': 'character_base',
    'character_expression': 'character_expression',
    'char_expression': 'character_expression',
    'transparent_sprite': 'transparent_sprite',
    'char_alpha': 'transparent_sprite',
    'bgm': 'bgm',
    'audio_bgm_ace': 'bgm',
    'sfx': 'sfx',
    'audio_sfx_mmaudio': 'sfx',
}

DEFAULT_WORKFLOW_ROUTES = {
    'character_base': 'char_base',
    'character_outfit_variant': 'char_base',
    'character_expression': 'char_expression',
    'transparent_sprite': 'char_alpha',
    'background': 'scene_background',
    'event_cg': 'scene_event_cg',
    'prop_cg': 'scene_prop_cg',
    'bgm': 'audio_bgm_ace',
    'sfx': 'audio_sfx_mmaudio',
}

TOKEN_RE = re.compile(r'[a-z0-9]+')
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
AUDIO_EXTS = {'.ogg', '.mp3', '.wav', '.flac'}
MIN_CANDIDATE_REVIEW_SCORE = 5
EXCLUDED_CANDIDATE_QA_STATUSES = {
    'rejected',
    'semantic_rejected',
    'semantic_rejected_prompt_routing',
    'visual_rejected',
    'failed',
    'fail',
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def normalize_type(asset_type: str | None) -> str:
    if not asset_type:
        return 'unknown'
    key = str(asset_type).strip().lower().replace('-', '_')
    return ASSET_TYPE_ALIASES.get(key, key)


def tokens(*parts: object) -> set[str]:
    text = ' '.join(str(p or '') for p in parts)
    return {t for t in TOKEN_RE.findall(text.lower()) if len(t) >= 3 and t not in {'the', 'and', 'with', 'for', 'asset', 'scene', 'seed'}}


def path_exists_for_manifest_asset(root: Path, asset: dict[str, Any]) -> bool:
    promoted = asset.get('promoted_path')
    if not promoted:
        return False
    p = Path(promoted)
    if not p.is_absolute():
        p = root / 'game' / p
    return p.exists()


def load_workflow_routes(contract_path: Path) -> dict[str, str]:
    routes = DEFAULT_WORKFLOW_ROUTES.copy()
    if contract_path.exists():
        contract = load_json(contract_path)
        routes.update(contract.get('workflow_routes') or {})
    return routes


def manifest_matches(root: Path, manifest: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    req_id = request.get('asset_id')
    req_type = normalize_type(request.get('asset_type'))
    matches = []
    for asset in manifest.get('assets', []) or []:
        asset_id = asset.get('asset_id')
        asset_type = normalize_type(asset.get('asset_type') or asset.get('workflow_id'))
        exact_id = bool(req_id and asset_id == req_id)
        renpy_name_match = bool(req_id and asset.get('renpy_name') == req_id)
        compatible_type = req_type == 'unknown' or asset_type == req_type
        if (exact_id or renpy_name_match) and compatible_type:
            matches.append({
                'asset_id': asset_id,
                'asset_type': asset.get('asset_type'),
                'workflow_id': asset.get('workflow_id'),
                'promoted_path': asset.get('promoted_path'),
                'renpy_name': asset.get('renpy_name'),
                'qa_status': asset.get('qa_status'),
                'file_exists': path_exists_for_manifest_asset(root, asset),
                'match_reason': 'exact_asset_id' if exact_id else 'renpy_name',
            })
    return matches


def candidate_files_from_metadata(metadata: dict[str, Any]) -> list[str]:
    out = []
    for key in ('candidate_copies', 'output_paths'):
        for raw in metadata.get(key, []) or []:
            p = Path(raw)
            if p.suffix.lower() in IMAGE_EXTS | AUDIO_EXTS:
                out.append(str(p))
    return out


def metadata_search_text(metadata_path: Path, metadata: dict[str, Any], files: list[str]) -> str:
    selected = {
        'run_id': metadata.get('run_id'),
        'asset_id': metadata.get('asset_id'),
        'asset_type': metadata.get('asset_type'),
        'workflow_id': metadata.get('workflow_id'),
        'positive_prompt': metadata.get('positive_prompt'),
        'taxonomy_placeholder_tags': metadata.get('taxonomy_placeholder_tags'),
        'taxonomy_negative_tags': metadata.get('taxonomy_negative_tags'),
        'taxonomy_source': metadata.get('taxonomy_source'),
        'csv_placeholder_tags': metadata.get('csv_placeholder_tags'),
        'character_features_placeholder': metadata.get('character_features_placeholder'),
        'outfit_detail_placeholder': metadata.get('outfit_detail_placeholder'),
        'qa_status': metadata.get('qa_status'),
        'promotion_status': metadata.get('promotion_status'),
        'path': str(metadata_path),
        'files': files,
    }
    return json.dumps(selected, ensure_ascii=False)


def score_candidate(request: dict[str, Any], metadata_path: Path, metadata: dict[str, Any]) -> dict[str, Any] | None:
    req_type = normalize_type(request.get('asset_type'))
    meta_type = normalize_type(metadata.get('asset_type') or metadata.get('workflow_id'))
    qa_status = str(metadata.get('qa_status') or '').strip().lower()
    promotion_status = str(metadata.get('promotion_status') or '').strip().lower()
    rejection_markers = ('failed', 'fail', 'rejected', 'semantic_rejected', 'visual_rejected')
    if (
        qa_status in EXCLUDED_CANDIDATE_QA_STATUSES
        or qa_status.startswith(rejection_markers)
        or promotion_status.startswith(rejection_markers)
        or 'semantic_reject' in promotion_status
        or 'visual_reject' in promotion_status
    ):
        return None
    if req_type != 'unknown' and meta_type != req_type:
        return None
    req_asset_id = str(request.get('asset_id') or '').strip().lower()
    meta_asset_id = str(metadata.get('asset_id') or '').strip().lower()
    if req_asset_id and meta_asset_id and req_asset_id != meta_asset_id:
        return None

    files = candidate_files_from_metadata(metadata)
    existing_files = [p for p in files if Path(p).exists()]
    if not existing_files:
        return None

    req_tokens = tokens(request.get('asset_id'), request.get('description'))
    search = metadata_search_text(metadata_path, metadata, existing_files)
    cand_tokens = tokens(search)
    overlap = sorted(req_tokens & cand_tokens)

    # Type-compatible candidates are useful as owner-review candidates even when text overlap is weak,
    # but exact/overlap matches should sort first.
    score = len(overlap)
    if request.get('asset_id') and str(request.get('asset_id')).lower() in search.lower():
        score += 10
    if request.get('description') and str(request.get('description')).lower() in search.lower():
        score += 5
    if metadata.get('promotion_status') == 'not_promoted_pending_owner_approval':
        score += 1

    return {
        'metadata_path': str(metadata_path),
        'run_id': metadata.get('run_id'),
        'asset_type': metadata.get('asset_type'),
        'workflow_id': metadata.get('workflow_id'),
        'seed': metadata.get('seed'),
        'qa_status': metadata.get('qa_status'),
        'qa_reports': metadata.get('qa_reports') or [],
        'qa_report': metadata.get('qa_report') or metadata.get('qa_report_path'),
        'promotion_status': metadata.get('promotion_status'),
        'candidate_files': existing_files,
        'score': score,
        'token_overlap': overlap,
    }


def candidate_matches(generation_runs_root: Path, request: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    matches = []
    if not generation_runs_root.exists():
        return matches
    for metadata_path in generation_runs_root.rglob('metadata.json'):
        try:
            metadata = load_json(metadata_path)
        except Exception:
            continue
        scored = score_candidate(request, metadata_path, metadata)
        if scored and scored.get('score', 0) >= MIN_CANDIDATE_REVIEW_SCORE:
            matches.append(scored)
    matches.sort(key=lambda item: (item['score'], item.get('run_id') or ''), reverse=True)
    return matches[:limit]


def resolve_request(root: Path, manifest: dict[str, Any], workflow_routes: dict[str, str], generation_runs_root: Path, request: dict[str, Any]) -> dict[str, Any]:
    req_type = normalize_type(request.get('asset_type'))
    manifest_hits = manifest_matches(root, manifest, request)
    if manifest_hits:
        missing_files = [m for m in manifest_hits if not m['file_exists']]
        if missing_files:
            decision = 'blocked_manifest_missing_file'
            status = 'blocked'
        else:
            decision = 'reuse_manifest'
            status = 'resolved'
        return {
            **request,
            'normalized_asset_type': req_type,
            'status': status,
            'decision': decision,
            'manifest_matches': manifest_hits,
            'candidate_matches': [],
            'recommended_workflow_id': workflow_routes.get(req_type),
        }

    candidates = candidate_matches(generation_runs_root, request)
    if candidates:
        return {
            **request,
            'normalized_asset_type': req_type,
            'status': 'needs_owner_review',
            'decision': 'review_existing_candidate',
            'manifest_matches': [],
            'candidate_matches': candidates,
            'recommended_workflow_id': workflow_routes.get(req_type),
        }

    workflow_id = workflow_routes.get(req_type)
    return {
        **request,
        'normalized_asset_type': req_type,
        'status': 'needs_generation' if workflow_id else 'needs_manual_route',
        'decision': 'generate' if workflow_id else 'manual_route_required',
        'manifest_matches': [],
        'candidate_matches': [],
        'recommended_workflow_id': workflow_id,
    }


def build_resolution(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve() if args.project_root else ROOT
    requests_path = Path(args.asset_requests).resolve()
    require_under(requests_path, root, 'asset_requests')
    manifest_path = resolve_project_path(root, args.manifest, 'manifest') if args.manifest else root / DEFAULT_MANIFEST.relative_to(ROOT)
    contract_path = resolve_project_path(root, args.contract, 'contract') if args.contract else root / DEFAULT_CONTRACT.relative_to(ROOT)
    generation_runs_root = resolve_project_path(root, args.generation_runs_root, 'generation-runs-root') if args.generation_runs_root else root / DEFAULT_GENERATION_RUNS_ROOT.relative_to(ROOT)

    requests_data = load_json(requests_path)
    manifest = load_json(manifest_path)
    routes = load_workflow_routes(contract_path)
    resolutions = [resolve_request(root, manifest, routes, generation_runs_root, req) for req in requests_data.get('asset_requests', [])]
    counts: dict[str, int] = {}
    for item in resolutions:
        counts[item['decision']] = counts.get(item['decision'], 0) + 1

    return {
        'tool': 'resolve_asset_requests',
        'resolved_at': datetime.now().isoformat(timespec='seconds'),
        'scene_id': requests_data.get('scene_id'),
        'source_asset_requests': str(requests_path),
        'manifest_path': str(manifest_path),
        'generation_runs_root': str(generation_runs_root),
        'counts': counts,
        'resolved_asset_requests': resolutions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Resolve extracted scene asset requests against manifest, existing candidates, or workflow routes.')
    parser.add_argument('asset_requests', help='asset_requests.json produced by extract_asset_requests_from_scene_note.py')
    parser.add_argument('--project-root', help='RenPy project root; defaults to script parent project root')
    parser.add_argument('--manifest', help='Manifest path; defaults to game/data/asset_manifest.json')
    parser.add_argument('--contract', help='Project contract path; defaults to docs/automation/project_contract.json')
    parser.add_argument('--generation-runs-root', help='Generation run metadata root; defaults to docs/automation/generation_runs')
    parser.add_argument('--out', required=True, help='Output resolution JSON path')
    args = parser.parse_args(argv)

    try:
        project_paths = build_project_paths(args.project_root, args.contract)
        args.project_root = str(project_paths.project_root)
        out_path = resolve_project_path(project_paths.project_root, args.out, 'out')
        data = build_resolution(args)
    except ValueError as exc:
        print(f'RESOLVE_REFUSED: {exc}')
        return 2
    except FileNotFoundError as exc:
        print(f'RESOLVE_FAILED: missing file: {exc.filename or exc}')
        return 1
    except json.JSONDecodeError as exc:
        print(f'RESOLVE_FAILED: invalid JSON: {exc}')
        return 1

    save_json(out_path, data)
    print('RESOLVE_ASSET_REQUESTS')
    print('scene_id', data.get('scene_id'))
    print('count', len(data['resolved_asset_requests']))
    for key, value in sorted(data['counts'].items()):
        print(key, value)
    for item in data['resolved_asset_requests']:
        print('asset', item.get('asset_id'), item.get('decision'), item.get('recommended_workflow_id'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
