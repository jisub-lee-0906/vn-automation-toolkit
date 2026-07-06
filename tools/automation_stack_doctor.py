from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_COMFY_ENDPOINTS = [
    'http://127.0.0.1:8000',
    'http://127.0.0.1:8001',
    'http://127.0.0.1:8188',
]
DEFAULT_OBSIDIAN_ROOTS = [
    Path('E:/workspace/obsidian-vn'),
    Path.home() / 'Documents' / 'Obsidian Vault',
]


def check_url(base: str, path: str, timeout: float) -> dict[str, Any]:
    url = base.rstrip('/') + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {'path': path, 'ok': True, 'status': response.status}
    except Exception as exc:  # pragma: no cover - exact platform/network errors vary
        return {'path': path, 'ok': False, 'error': type(exc).__name__, 'detail': str(exc)[:240]}


def check_comfyui(endpoints: list[str], timeout: float, allow_multiple: bool) -> dict[str, Any]:
    endpoint_reports: list[dict[str, Any]] = []
    healthy: list[str] = []
    for endpoint in endpoints:
        checks = [check_url(endpoint, path, timeout) for path in ['/system_stats', '/queue', '/history']]
        ok = all(item.get('ok') for item in checks)
        if ok:
            healthy.append(endpoint)
        endpoint_reports.append({'endpoint': endpoint, 'ok': ok, 'checks': checks})

    errors: list[str] = []
    warnings: list[str] = []
    if not healthy:
        errors.append('no ComfyUI endpoint responded successfully to /system_stats, /queue, and /history')
    if len(healthy) > 1 and not allow_multiple:
        warnings.append(
            'multiple ComfyUI endpoints are healthy; lock one active endpoint/output root to avoid history/output split-brain: '
            + ', '.join(healthy)
        )
    return {'component': 'comfyui', 'ok': not errors, 'healthy_endpoints': healthy, 'endpoints': endpoint_reports, 'warnings': warnings, 'errors': errors}


def check_hermes(run_doctor: bool, timeout: int) -> dict[str, Any]:
    exe = shutil.which('hermes')
    warnings: list[str] = []
    errors: list[str] = []
    report: dict[str, Any] = {'component': 'hermes', 'ok': False, 'executable': exe, 'warnings': warnings, 'errors': errors}
    if not exe:
        errors.append('hermes CLI not found on PATH')
        return report

    try:
        version = subprocess.run([exe, '--version'], text=True, capture_output=True, timeout=timeout)
    except Exception as exc:  # pragma: no cover - process failures vary
        errors.append(f'hermes --version failed: {type(exc).__name__}: {exc}')
        return report
    report['version_returncode'] = version.returncode
    report['version_output'] = (version.stdout + version.stderr).strip()[:2000]
    if version.returncode != 0:
        errors.append('hermes --version returned non-zero')
        return report

    if run_doctor:
        try:
            doctor = subprocess.run([exe, 'doctor'], text=True, capture_output=True, timeout=max(timeout, 60))
        except Exception as exc:  # pragma: no cover
            warnings.append(f'hermes doctor could not complete: {type(exc).__name__}: {exc}')
        else:
            report['doctor_returncode'] = doctor.returncode
            text = (doctor.stdout + doctor.stderr).strip()
            report['doctor_excerpt'] = text[:6000]
            if doctor.returncode != 0:
                warnings.append('hermes doctor returned non-zero; inspect doctor_excerpt')
            if 'Found ' in text and ' issue(s)' in text:
                warnings.append('hermes doctor reported issues; inspect doctor_excerpt')
    report['ok'] = not errors
    return report


def default_obsidian_roots() -> list[Path]:
    roots: list[Path] = []
    env_value = os.environ.get('OBSIDIAN_VAULT_PATH')
    if env_value:
        roots.append(Path(env_value))
    roots.extend(DEFAULT_OBSIDIAN_ROOTS)
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            deduped.append(root)
    return deduped


def check_obsidian(roots: list[Path]) -> dict[str, Any]:
    root_reports: list[dict[str, Any]] = []
    existing: list[str] = []
    for root in roots:
        expanded = root.expanduser()
        exists = expanded.exists()
        md_count = 0
        if exists:
            try:
                md_count = sum(1 for _ in expanded.rglob('*.md'))
            except Exception:  # pragma: no cover - permission dependent
                md_count = -1
            existing.append(str(expanded))
        root_reports.append({'root': str(expanded), 'exists': exists, 'markdown_count': md_count})
    errors = [] if existing else ['no Obsidian root exists; pass --obsidian-root or set OBSIDIAN_VAULT_PATH']
    warnings = []
    empty_existing = [item['root'] for item in root_reports if item['exists'] and item['markdown_count'] == 0]
    if empty_existing:
        warnings.append('existing Obsidian root(s) have no markdown files: ' + ', '.join(empty_existing))
    return {'component': 'obsidian', 'ok': not errors, 'existing_roots': existing, 'roots': root_reports, 'warnings': warnings, 'errors': errors}


def check_path(raw: str | None, label: str) -> dict[str, Any] | None:
    if not raw:
        return None
    path = Path(raw).expanduser()
    return {'component': label, 'path': str(path), 'ok': path.exists(), 'errors': [] if path.exists() else [f'{label} path missing: {path}'], 'warnings': []}


def summarize(components: list[dict[str, Any]], strict: bool) -> tuple[str, int]:
    errors = [err for comp in components for err in comp.get('errors', [])]
    warnings = [warn for comp in components for warn in comp.get('warnings', [])]
    if errors:
        return 'FAIL', 1
    if warnings:
        return ('FAIL' if strict else 'WARN'), (1 if strict else 0)
    return 'PASS', 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Check the generic Hermes + ComfyUI + Obsidian automation stack without changing project files.')
    parser.add_argument('--comfy-endpoint', action='append', default=[], help='ComfyUI endpoint to probe. Repeatable. Defaults to common local ports.')
    parser.add_argument('--allow-multiple-comfy', action='store_true', help='Do not warn when more than one ComfyUI endpoint is healthy.')
    parser.add_argument('--comfy-output-root', default='', help='Optional ComfyUI output root that must exist.')
    parser.add_argument('--obsidian-root', action='append', default=[], help='Obsidian vault/root path to check. Repeatable. Defaults to OBSIDIAN_VAULT_PATH and common local roots.')
    parser.add_argument('--workflow-pack-root', default='', help='Optional ComfyUI workflow pack root that must exist.')
    parser.add_argument('--skip-hermes', action='store_true')
    parser.add_argument('--skip-comfyui', action='store_true')
    parser.add_argument('--skip-obsidian', action='store_true')
    parser.add_argument('--run-hermes-doctor', action='store_true')
    parser.add_argument('--timeout', type=float, default=2.0)
    parser.add_argument('--strict', action='store_true', help='Treat warnings as failures.')
    parser.add_argument('--json-out', default='')
    args = parser.parse_args(argv)

    components: list[dict[str, Any]] = []
    if not args.skip_hermes:
        components.append(check_hermes(args.run_hermes_doctor, timeout=max(5, int(args.timeout))))
    if not args.skip_comfyui:
        components.append(check_comfyui(args.comfy_endpoint or DEFAULT_COMFY_ENDPOINTS, args.timeout, args.allow_multiple_comfy))
    if not args.skip_obsidian:
        obs_roots = [Path(item) for item in args.obsidian_root] if args.obsidian_root else default_obsidian_roots()
        components.append(check_obsidian(obs_roots))
    for optional in [check_path(args.comfy_output_root, 'comfy_output_root'), check_path(args.workflow_pack_root, 'workflow_pack_root')]:
        if optional:
            components.append(optional)

    status, rc = summarize(components, args.strict)
    report = {
        'tool': 'automation_stack_doctor',
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'status': status,
        'strict': bool(args.strict),
        'components': components,
    }
    if args.json_out:
        out = Path(args.json_out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print('AUTOMATION_STACK_DOCTOR_' + status)
    for comp in components:
        print(f"[{comp.get('component')}] ok={comp.get('ok')}")
        for warning in comp.get('warnings', []):
            print('  WARN:', warning)
        for error in comp.get('errors', []):
            print('  ERROR:', error)
    if args.json_out:
        print('json_report', args.json_out)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
