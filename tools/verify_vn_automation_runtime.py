from __future__ import annotations

import json
import argparse
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths  # noqa: E402


def check_port(port: int) -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(('127.0.0.1', port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def fetch_json(base: str, path: str, timeout: int = 10):
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify VN automation runtime for a project-configured title.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--skip-comfyui', action='store_true')
    parser.add_argument('--skip-renpy-lint', action='store_true')
    args = parser.parse_args()
    paths = build_project_paths(args.project_root, args.contract)
    project_root = paths.project_root
    contract_path = paths.contract_file
    errors: list[str] = []
    warnings: list[str] = []
    print('VN_AUTOMATION_RUNTIME_VERIFY')

    # 1. Static contract/doc validation. Use the toolkit validator, not a per-title copy.
    validator = TOOLS / 'validate_vn_automation_docs.py'
    proc = subprocess.run([sys.executable, str(validator), '--project-root', str(project_root), '--contract', str(contract_path)], cwd=project_root, text=True, capture_output=True)
    print('doc_validator_exit', proc.returncode)
    print(proc.stdout.strip())
    if proc.returncode != 0:
        errors.append('document validator failed')
        if proc.stderr:
            print(proc.stderr.strip())

    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    workflow_root = Path(contract['workflow_pack_root'])
    workflow_index = Path(contract['workflow_index'])
    idx = json.loads(workflow_index.read_text(encoding='utf-8'))

    # 2. Workflow dry-run: parse JSON and verify editable fields exist.
    print('\nWORKFLOW_DRY_RUN')
    for wf in idx.get('workflows', []):
        wid = wf['id']
        api = workflow_root / wf['api']
        data = json.loads(api.read_text(encoding='utf-8'))
        missing = []
        for field in wf.get('editable_fields', []):
            cur = data
            parts = field.split('.')
            ok = True
            for part in parts[:-1]:
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    ok = False
                    break
            if not (ok and isinstance(cur, dict) and parts[-1] in cur):
                missing.append(field)
        print(f'{wid}: nodes={len(data)} editable={len(wf.get("editable_fields", []))-len(missing)}/{len(wf.get("editable_fields", []))}')
        if missing:
            errors.append(f'{wid} missing editable fields: {missing}')

    # 3. ComfyUI endpoint readiness and node/model availability.
    print('\nCOMFY_ENDPOINTS')
    if args.skip_comfyui:
        print('comfyui_skipped true')
    else:
        candidates = contract.get('comfyui_endpoint_candidates') or [contract.get('comfyui_endpoint', 'http://127.0.0.1:8000')]
        live_base = None
        for base in candidates:
            port = int(base.rsplit(':', 1)[1])
            open_port = check_port(port)
            try:
                status, _ = fetch_json(base, '/system_stats', timeout=5)
                print(base, 'port_open=', open_port, 'system_stats=', status)
                if live_base is None:
                    live_base = base
            except Exception as e:
                print(base, 'port_open=', open_port, 'ERR', type(e).__name__, e)
        if not live_base:
            errors.append('no live ComfyUI endpoint found')
        else:
            _, object_info = fetch_json(live_base, '/object_info', timeout=20)
            available = set(object_info.keys())
            ckpts = set(object_info.get('CheckpointLoaderSimple', {}).get('input', {}).get('required', {}).get('ckpt_name', [[]])[0])
            loras = set(object_info.get('LoraLoader', {}).get('input', {}).get('required', {}).get('lora_name', [[]])[0])
            print('live_comfyui_endpoint', live_base)
            for wf in idx.get('workflows', []):
                data = json.loads((workflow_root / wf['api']).read_text(encoding='utf-8'))
                classes = sorted({node.get('class_type') for node in data.values() if isinstance(node, dict) and node.get('class_type')})
                missing_classes = [c for c in classes if c not in available]
                needed_ckpt = []
                needed_lora = []
                for node in data.values():
                    if isinstance(node, dict):
                        inp = node.get('inputs', {})
                        if 'ckpt_name' in inp:
                            needed_ckpt.append(inp['ckpt_name'])
                        if 'lora_name' in inp:
                            needed_lora.append(inp['lora_name'])
                missing_ckpt = [x for x in needed_ckpt if ckpts and x not in ckpts]
                missing_lora = [x for x in needed_lora if loras and x not in loras]
                print(f'{wf["id"]}: classes_missing={len(missing_classes)} ckpt_missing={missing_ckpt} lora_missing={missing_lora}')
                if missing_classes:
                    errors.append(f'{wf["id"]} missing node classes: {missing_classes}')
                if missing_ckpt:
                    errors.append(f'{wf["id"]} missing checkpoints: {missing_ckpt}')
                if missing_lora:
                    errors.append(f'{wf["id"]} missing loras: {missing_lora}')

    # 4. Ren'Py lint.
    if args.skip_renpy_lint:
        print('\nREN_PY_LINT')
        print('renpy_lint_skipped true')
    else:
        print('\nREN_PY_LINT')
        renpy = contract['renpy_sdk_exe']
        proc = subprocess.run([renpy, str(project_root), 'lint'], cwd=project_root, text=True, capture_output=True, timeout=240)
        print('renpy_lint_exit', proc.returncode)
        print(proc.stdout.strip())
        if proc.returncode != 0:
            errors.append('RenPy lint failed')
            if proc.stderr:
                print(proc.stderr.strip())

    if errors:
        print('\nVERIFY_FAILED')
        for e in errors:
            print('-', e)
        return 1
    print('\nVERIFY_PASSED')
    if warnings:
        print('WARNINGS')
        for w in warnings:
            print('-', w)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
