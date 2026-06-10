from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from asset_lifecycle import apply_lifecycle  # noqa: E402
from qa_asset_file import inspect_asset  # noqa: E402
from vn_product_config import build_project_paths, require_under, resolve_project_path, validate_project_glob  # noqa: E402

DEFAULT_RUNNERS = {
    'audio_bgm_with_sfx': f'{sys.executable} {TOOLS / "run_audio_bgm_with_sfx_smoke.py"}',
    'char_base': f'{sys.executable} {TOOLS / "run_char_base_smoke.py"}',
    'scene_background': f'{sys.executable} {TOOLS / "run_scene_background_smoke.py"}',
    'scene_event_cg': f'{sys.executable} {TOOLS / "run_scene_event_cg_smoke.py"}',
    'scene_prop_cg': f'{sys.executable} {TOOLS / "run_scene_prop_cg_smoke.py"}',
}
PROMPT_SENSITIVE_WORKFLOWS = {'scene_background', 'scene_event_cg', 'scene_prop_cg', 'char_base', 'audio_bgm_with_sfx'}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parse_runner_overrides(values: list[str] | None) -> dict[str, str]:
    runners = DEFAULT_RUNNERS.copy()
    for raw in values or []:
        if '=' not in raw:
            raise ValueError(f'runner override must be workflow_id=command: {raw}')
        workflow_id, command = raw.split('=', 1)
        runners[workflow_id.strip()] = command.strip()
    return runners


def collect_generate_items(project_root: Path, resolved_glob: str) -> list[dict[str, Any]]:
    validate_project_glob(resolved_glob, 'resolved_glob')
    items = []
    for path in sorted(project_root.glob(resolved_glob)):
        require_under(path.resolve(), project_root, 'resolved asset request')
        data = load_json(path)
        scene_id = data.get('scene_id') or path.stem.replace('.resolved_asset_requests', '')
        for item in data.get('resolved_asset_requests', []) or []:
            if item.get('decision') != 'generate':
                continue
            items.append({
                'scene_id': scene_id,
                'source_resolved_path': str(path),
                'asset_id': item.get('asset_id'),
                'asset_type': item.get('asset_type'),
                'description': item.get('description', ''),
                'workflow_id': item.get('recommended_workflow_id'),
                'prompt_slots_path': item.get('prompt_slots_path'),
                'prompt_slots': item.get('prompt_slots'),
                'source_char_base_metadata': item.get('source_char_base_metadata') or item.get('char_base_metadata') or item.get('char_base_metadata_path'),
                'recommended_audio_role': item.get('recommended_audio_role'),
                'recommended_prompt_shape': item.get('recommended_prompt_shape'),
                'recommended_audio_mode': item.get('recommended_audio_mode'),
                'recommended_audio_duration': item.get('recommended_audio_duration'),
            })
    return items


def prompt_slots_path_for(project_root: Path, item: dict[str, Any]) -> Path | None:
    def slugify(value: str) -> str:
        out = ''.join(ch.lower() if ch.isalnum() else '_' for ch in value).strip('_')
        while '__' in out:
            out = out.replace('__', '_')
        return out

    root = (project_root / 'docs/production/prompt_slots').resolve()
    asset_id = slugify(str(item.get('asset_id') or ''))
    scene_id = slugify(str(item.get('scene_id') or ''))
    candidates = []
    raw = item.get('prompt_slots_path') or item.get('prompt_slots')
    if isinstance(raw, str) and raw.strip():
        candidates.append(Path(raw))
    if scene_id and asset_id:
        candidates.append(root / f'{scene_id}__{asset_id}.json')
    if asset_id:
        candidates.append(root / f'{asset_id}.json')
    for path in candidates:
        p = (path if path.is_absolute() else project_root / path).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            continue
        if p.exists() and p.is_file():
            return p
    return None


def metadata_path_from_stdout(stdout: str) -> Path | None:
    for line in stdout.splitlines():
        if line.startswith('METADATA '):
            return Path(line.split(' ', 1)[1].strip())
    return None


def confine_metadata_path(project_root: Path, metadata_path: Path) -> Path | None:
    root = (project_root / 'docs/automation/generation_runs').resolve()
    resolved = (metadata_path if metadata_path.is_absolute() else project_root / metadata_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved if resolved.exists() and resolved.is_file() else None


def qa_candidate_files(project_root: Path, metadata: dict[str, Any], asset_type: str | None, run_id: str) -> list[dict[str, Any]]:
    reports = []
    qa_dir = project_root / 'docs/automation/qa_reports'
    for idx, raw in enumerate(metadata.get('candidate_copies') or metadata.get('output_paths') or [], start=1):
        path = Path(raw)
        report = inspect_asset(path, asset_type)
        report_path = qa_dir / f'{run_id}_{idx}_file_qa.json'
        save_json(report_path, report)
        reports.append({
            'candidate_file': str(path),
            'path': str(report_path),
            'status': report.get('status'),
            'warnings': report.get('warnings', []),
            'errors': report.get('errors', []),
        })
    return reports


def run_one(project_root: Path, item: dict[str, Any], runner_command: str, runner_timeout: int = 900) -> dict[str, Any]:
    workflow_id = str(item.get('workflow_id') or '')
    prompt_slots_path = prompt_slots_path_for(project_root, item) if workflow_id in PROMPT_SENSITIVE_WORKFLOWS else None
    if workflow_id in PROMPT_SENSITIVE_WORKFLOWS and prompt_slots_path is None:
        return {
            **item,
            'status': 'failed_missing_prompt_slots',
            'reason': 'prompt_sensitive_workflow_requires_agent_authored_prompt_slots',
        }
    command = shlex.split(runner_command, posix=(os.name != 'nt')) + [
        '--project-root', str(project_root),
        '--asset-id', str(item.get('asset_id') or ''),
        '--description', str(item.get('description') or ''),
        '--scene-id', str(item.get('scene_id') or ''),
    ]
    if prompt_slots_path is not None:
        command += ['--prompt-slots', str(prompt_slots_path)]
    if workflow_id == 'audio_bgm_with_sfx' and item.get('asset_type'):
        command += ['--asset-type', str(item.get('asset_type'))]
    if workflow_id == 'scene_event_cg':
        source_char_base_metadata = item.get('source_char_base_metadata')
        if not source_char_base_metadata:
            return {
                **item,
                'status': 'failed_missing_source_char_base_metadata',
                'reason': 'scene_event_cg_requires_source_char_base_metadata',
            }
        command += ['--char-base-metadata', str(source_char_base_metadata)]
    try:
        proc = subprocess.run(command, cwd=project_root, text=True, capture_output=True, timeout=runner_timeout)
    except subprocess.TimeoutExpired as exc:
        return {**item, 'command': command, 'status': 'failed_runner_timeout', 'timeout_seconds': runner_timeout, 'stdout': exc.stdout or '', 'stderr': exc.stderr or ''}
    except FileNotFoundError as exc:
        return {**item, 'command': command, 'status': 'failed_runner_not_found', 'reason': str(exc)}
    result: dict[str, Any] = {
        **item,
        'command': command,
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
        'status': 'failed' if proc.returncode else 'generated',
    }
    raw_metadata_path = metadata_path_from_stdout(proc.stdout)
    metadata_path = confine_metadata_path(project_root, raw_metadata_path) if raw_metadata_path else None
    if raw_metadata_path:
        result['metadata_path'] = str(raw_metadata_path)
    if proc.returncode != 0:
        return result
    if raw_metadata_path and metadata_path is None:
        result['status'] = 'failed_untrusted_metadata_path'
        return result
    if not metadata_path:
        result['status'] = 'failed_missing_metadata'
        return result
    metadata = load_json(metadata_path)
    run_id = metadata.get('run_id') or metadata_path.parent.name
    result['run_id'] = run_id
    result['candidate_copies'] = metadata.get('candidate_copies', [])
    result['qa_reports'] = qa_candidate_files(project_root, metadata, item.get('asset_type'), run_id)
    if result['qa_reports']:
        metadata['qa_reports'] = result['qa_reports']
        first_pass = next((q for q in result['qa_reports'] if q.get('status') == 'pass'), None)
        if first_pass:
            metadata['qa_report'] = first_pass.get('path')
    if result['qa_reports'] and all(q['status'] == 'pass' for q in result['qa_reports']):
        metadata['qa_status'] = 'qa_pass_candidate_not_promoted'
    elif result['qa_reports']:
        metadata['qa_status'] = 'qa_warn_candidate_not_promoted'
    current_promotion = str(metadata.get('promotion_status') or '')
    if not current_promotion.startswith('promoted'):
        metadata['promotion_status'] = 'not_promoted_pending_owner_approval'
    apply_lifecycle(metadata)
    save_json(metadata_path, metadata)
    return result


def build_batch(project_root: Path, resolved_glob: str, runners: dict[str, str], limit: int | None = None, runner_timeout: int = 900) -> dict[str, Any]:
    items = collect_generate_items(project_root, resolved_glob)
    if limit is not None:
        items = items[:limit]
    results = []
    skipped = []
    for item in items:
        workflow_id = item.get('workflow_id')
        runner = runners.get(str(workflow_id)) if workflow_id else None
        if not runner:
            skipped.append({**item, 'reason': 'no_runner_for_workflow'})
            continue
        results.append(run_one(project_root, item, runner, runner_timeout=runner_timeout))
    counts = {
        'requested': len(items),
        'generated': sum(1 for r in results if r.get('status') == 'generated'),
        'failed': sum(1 for r in results if str(r.get('status', '')).startswith('failed')),
        'skipped': len(skipped),
    }
    return {
        'tool': 'run_generation_queue',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'project_root': str(project_root),
        'resolved_glob': resolved_glob,
        'counts': counts,
        'results': results,
        'skipped': skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run workflow generation for resolved asset requests with decision=generate.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--resolved-glob', default='docs/production/asset_requests/*.resolved_asset_requests.json')
    parser.add_argument('--runner', action='append', help='Override runner as workflow_id=command')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--out', default=None)
    parser.add_argument('--runner-timeout', type=int, default=900, help='Per-item runner timeout in seconds.')
    args = parser.parse_args(argv)

    paths = build_project_paths(args.project_root, args.contract)
    project_root = paths.project_root
    try:
        out_path = resolve_project_path(project_root, args.out, 'out') if args.out else (project_root / 'docs/automation/generation_queue_batch.json').resolve()
        runners = parse_runner_overrides(args.runner)
        data = build_batch(project_root, args.resolved_glob, runners, args.limit, runner_timeout=args.runner_timeout)
    except ValueError as exc:
        print(f'GENERATION_QUEUE_REFUSED: {exc}')
        return 2
    except Exception as exc:
        print(f'GENERATION_QUEUE_FAILED: {type(exc).__name__}: {exc}')
        return 1
    save_json(out_path, data)
    print('RUN_GENERATION_QUEUE')
    for key, value in data['counts'].items():
        print(key, value)
    for result in data['results']:
        print('asset', result.get('asset_id'), result.get('status'), result.get('run_id'))
    return 0 if data['counts']['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
