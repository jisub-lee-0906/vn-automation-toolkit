from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import re

SLUG_RE = re.compile(r'[^a-z0-9_]+')


def slugify(value: str) -> str:
    slug = SLUG_RE.sub('_', value.strip().lower().replace('-', '_')).strip('_')
    return slug or 'game'


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

SCENE_TEMPLATE = '''---
scene_id: example_scene
status: draft
---

# Scene: Example Scene

## Summary
One-paragraph summary of the scene intent.

## Required Assets
- [ ] background: bg_example_room | quiet room background, no characters, textbox-safe lower third
- [ ] sfx: sfx_example_soft_step | soft footstep sound, short, no speech

## Beats
1. Opening beat.
2. Choice or reveal beat.
'''

CHARACTER_TEMPLATE = '''---
character_id: example_character
status: draft
---

# Character: Example Character

## Canon
- Role:
- Visual anchors:
- Outfit rules:
- Voice / tone:

## Asset Notes
- Base sprite:
- Expressions:
- Event CG constraints:
'''

ASSET_REQUEST_TEMPLATE = '''# Asset Request

- asset_id:
- asset_type: background|event_cg|prop_cg|character_base|character_expression|transparent_sprite|bgm|sfx
- scene_id:
- description:
- acceptance_criteria:
  - must match canon
  - must pass file QA
  - must receive owner approval before promotion
'''

QA_CHECKLIST = '''# VN Asset QA Checklist

## File QA
- File exists and is non-empty.
- Image/audio extension matches asset type.
- Image dimensions suit target display or are transform-safe.
- Audio is playable and short/loopable as intended.

## Visual / Audio QA
- No unwanted readable text, watermark, logo, or UI artifact.
- No unwanted humans in background/prop-only assets.
- Character identity and outfit match canon.
- Prop is readable at VN display scale.

## Promotion Gate
- Candidate has a passing file QA report.
- Owner explicitly approved the candidate.
- Promotion updates manifest and source metadata.
- Ren'Py asset refs and lint pass after integration.
'''

DESIGN_DOC = '''# VN Automation Design

## 1. 목표
새 Ren'Py 게임마다 재사용 가능한 supervised VN production automation spine을 제공한다.

## 2. 고정 경로
고정 경로는 코드에 두지 않고 `docs/automation/project_contract.json`과 `--project-root`에서 해석한다.

## 3. 역할 분담
Obsidian은 기획/장면 노트, project docs는 machine-readable sidecar, ComfyUI는 후보 생성, Ren'Py `game/`은 최종 playable artifact를 담당한다.

## 4. 데이터 흐름
scene note -> asset requests -> resolver -> owner review queue -> generation/QA -> approval -> promotion -> Ren'Py verification.

## 7. Workflow routing
`workflow_routes`는 asset type을 workflow id에 매핑한다. Manifest hit를 먼저 재사용하고 없을 때만 generation decision을 만든다.

## 11. QA gates
file QA, visual/audio QA, explicit owner approval, asset reference check, integration gap report, Ren'Py lint를 gate로 사용한다.

## 13. 첫 투입 milestone
새 게임의 첫 milestone은 scene note 1개, required assets 2개, owner queue 생성, static verify 통과다.

## 14. 금지 사항
승인 없는 promotion, blind `.rpy` patch, project root 밖 산출물 기록, 기존 파일 무단 overwrite를 금지한다.
'''

ASSET_MANIFEST_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object',
    'required': ['version', 'assets'],
    'properties': {
        'version': {'type': 'string'},
        'assets': {'type': 'array'},
    },
}

CHARACTER_ASSET_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object',
    'required': ['character_id'],
    'properties': {'character_id': {'type': 'string'}},
}


def write_text(path: Path, content: str, force: bool, planned: list[str], written: list[str]) -> None:
    planned.append(str(path))
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    written.append(str(path))


def write_json(path: Path, data: dict[str, Any], force: bool, planned: list[str], written: list[str]) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n', force, planned, written)


def build_contract(args: argparse.Namespace, project_root: Path) -> dict[str, Any]:
    game_dir = Path(args.renpy_game_dir) if args.renpy_game_dir else project_root / 'game'
    workflow_index = Path(args.workflow_index) if args.workflow_index else (Path(args.workflow_pack_root) / 'WORKFLOW_INDEX.json' if args.workflow_pack_root else None)
    generation_runs_root = project_root / 'docs/automation/generation_runs'
    generated_candidates_root = project_root / 'docs/automation/generated_candidates'
    promotion_log_root = project_root / 'docs/production/promotions'
    comfyui_input_root = Path(args.comfyui_input_root)
    comfyui_output_root = Path(args.comfyui_output_root)
    game_title = args.game_title or project_root.name.replace('_', ' ').replace('-', ' ').title()
    game_slug = args.game_slug or slugify(project_root.name)
    obsidian_vault = Path(args.obsidian_vault).resolve() if args.obsidian_vault else None
    obsidian_project_root = Path(args.obsidian_project_root).resolve() if args.obsidian_project_root else (obsidian_vault / 'VN' if obsidian_vault else None)
    obsidian_scenes_glob = args.obsidian_scenes_glob or ('Scenes/*.md' if obsidian_project_root else '')
    return {
        'version': '1.0.0',
        'environment': args.environment,
        'game_title': game_title,
        'game_slug': game_slug,
        'obsidian_vault': obsidian_vault.as_posix() if obsidian_vault else '',
        'obsidian_project_root': obsidian_project_root.as_posix() if obsidian_project_root else '',
        'obsidian_scenes_glob': obsidian_scenes_glob,
        'renpy_project_root': project_root.as_posix(),
        'renpy_game_dir': game_dir.as_posix(),
        'renpy_sdk_exe': args.renpy_sdk_exe or '',
        'workflow_pack_root': args.workflow_pack_root or '',
        'workflow_index': workflow_index.as_posix() if workflow_index else '',
        'comfyui_endpoint': args.comfyui_endpoint,
        'comfyui_endpoint_candidates': args.comfyui_endpoint_candidates.split(','),
        'comfyui_input_root': comfyui_input_root.as_posix(),
        'comfyui_output_root': comfyui_output_root.as_posix(),
        'normal_generation_rules': [
            'do_not_modify_canonical_workflow_json',
            'patch_runtime_payload_only',
            'verify_outputs_from_history_or_filesystem',
            'promote_only_after_qa',
        ],
        'workflow_routes': DEFAULT_WORKFLOW_ROUTES,
        'manifest_path': (game_dir / 'data/asset_manifest.json').as_posix(),
        'generated_candidates_root': generated_candidates_root.as_posix(),
        'generation_runs_root': generation_runs_root.as_posix(),
        'promotion_log_root': promotion_log_root.as_posix(),
    }


def scaffold(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    game_dir = Path(args.renpy_game_dir).resolve() if args.renpy_game_dir else project_root / 'game'
    planned: list[str] = []
    written: list[str] = []
    contract = build_contract(args, project_root)
    files = [
        (project_root / 'docs/automation/project_contract.json', contract, 'json'),
        (project_root / 'docs/automation/templates/Scene_Note_Template.md', SCENE_TEMPLATE, 'text'),
        (project_root / 'docs/automation/templates/Character_Note_Template.md', CHARACTER_TEMPLATE, 'text'),
        (project_root / 'docs/automation/templates/Asset_Request_Template.md', ASSET_REQUEST_TEMPLATE, 'text'),
        (project_root / 'docs/automation/qa_checklist.md', QA_CHECKLIST, 'text'),
        (project_root / 'docs/automation/vn_automation_design.md', DESIGN_DOC, 'text'),
        (project_root / 'docs/automation/schemas/asset_manifest.schema.json', ASSET_MANIFEST_SCHEMA, 'json'),
        (project_root / 'docs/automation/schemas/character_asset.schema.json', CHARACTER_ASSET_SCHEMA, 'json'),
        (game_dir / 'data/asset_manifest.json', {'version': '1.0.0', 'assets': []}, 'json'),
        (project_root / 'docs/production/owner_review_queue.md', '# VN Owner Review Queue\n\n- None\n', 'text'),
        (project_root / 'docs/production/owner_review_queue.json', {'review_items': [], 'generation_items': [], 'blocked_items': []}, 'json'),
    ]
    obsidian_project_root_raw = contract.get('obsidian_project_root')
    if obsidian_project_root_raw:
        obs_root = Path(obsidian_project_root_raw).resolve()
        files.extend([
            (obs_root / '00_Index.md', f"# {contract.get('game_title', project_root.name)} VN Index\n\n- Game slug: `{contract.get('game_slug', project_root.name)}`\n- [[Automation/VN_Automation_Design]]\n", 'text'),
            (obs_root / 'Automation/VN_Automation_Design.md', DESIGN_DOC, 'text'),
            (obs_root / 'Templates/Scene_Note_Template.md', SCENE_TEMPLATE, 'text'),
            (obs_root / 'Templates/Character_Note_Template.md', CHARACTER_TEMPLATE, 'text'),
            (obs_root / 'Templates/Asset_Request_Template.md', ASSET_REQUEST_TEMPLATE, 'text'),
        ])
    for path, content, kind in files:
        if args.dry_run:
            planned.append(str(path))
            continue
        if kind == 'json':
            write_json(path, content, args.force, planned, written)  # type: ignore[arg-type]
        else:
            write_text(path, content, args.force, planned, written)  # type: ignore[arg-type]
    return {'project_root': str(project_root), 'planned': planned, 'written': written, 'dry_run': args.dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Bootstrap VN automation docs/config for a RenPy project.')
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--renpy-game-dir')
    parser.add_argument('--renpy-sdk-exe', default='')
    parser.add_argument('--workflow-pack-root', default='')
    parser.add_argument('--workflow-index', default='')
    parser.add_argument('--obsidian-vault', default='')
    parser.add_argument('--obsidian-project-root', default='', help='Title-specific Obsidian project root, normally <vault>/VN.')
    parser.add_argument('--obsidian-scenes-glob', default='', help='Scene-note glob relative to obsidian_project_root. Defaults to Scenes/*.md.')
    parser.add_argument('--game-title', default='', help='Human title stored in project_contract.json.')
    parser.add_argument('--game-slug', default='', help='Stable title slug stored in project_contract.json.')
    parser.add_argument('--environment', default='windows-native')
    parser.add_argument('--comfyui-endpoint', default='http://127.0.0.1:8000')
    parser.add_argument('--comfyui-endpoint-candidates', default='http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8188')
    parser.add_argument('--comfyui-input-root', default='C:/Users/Desktop/Documents/ComfyUI/input')
    parser.add_argument('--comfyui-output-root', default='C:/Users/Desktop/Documents/ComfyUI/output')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true', help='Overwrite existing scaffolded files.')
    args = parser.parse_args(argv)
    result = scaffold(args)
    print('INIT_VN_AUTOMATION_PROJECT')
    print('project_root', result['project_root'])
    print('dry_run', result['dry_run'])
    print('planned', len(result['planned']))
    print('written', len(result['written']))
    for path in result['written']:
        print('wrote', path)
    if not result['written'] and not args.dry_run:
        print('no_files_written_existing_files_preserved')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
