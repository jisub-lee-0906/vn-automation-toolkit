from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import init_vn_automation_project  # noqa: E402

SAFE_SLUG_RE = re.compile(r'^[a-z][a-z0-9_]{1,63}$')
SLUG_RE = re.compile(r'[^a-z0-9_]+')
DEFAULT_SCENE_ID = 'scene_001_opening'
DEFAULT_PATCH_ID = 'bootstrap_placeholder_baseline'


def slugify(value: str) -> str:
    slug = SLUG_RE.sub('_', value.strip().lower().replace('-', '_')).strip('_')
    return slug


def project_rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def write_text(path: Path, content: str, written: list[str], *, force: bool = False) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    written.append(str(path))


def write_json(path: Path, data: dict[str, Any], written: list[str], *, force: bool = False) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n', written, force=force)


def require_under(child: Path, parent: Path, label: str) -> None:
    child_r = child.resolve()
    parent_r = parent.resolve()
    if child_r != parent_r and parent_r not in child_r.parents:
        raise ValueError(f'{label} must stay under {parent}: {child}')


def ensure_safe_slug(title: str, raw_slug: str | None) -> str:
    slug = raw_slug.strip().lower().replace('-', '_') if raw_slug else slugify(title)
    if not slug or slug == 'game':
        raise ValueError('GAME_SLUG_REQUIRED: provide --slug for non-ASCII or ambiguous titles')
    if not SAFE_SLUG_RE.fullmatch(slug):
        raise ValueError(f'GAME_SLUG_INVALID: slug must match {SAFE_SLUG_RE.pattern}: {slug}')
    return slug


def maybe_copy_renpy_template(project_root: Path, sdk_exe: str, written: list[str], force: bool) -> str:
    """Copy a complete Ren'Py template when available; otherwise write a minimal lintable-ish skeleton.

    The fallback is intentionally small and project-local. It is still followed by
    validation, and Ren'Py lint is only claimed when an SDK executable is present.
    """
    game_dir = project_root / 'game'
    sdk_path = Path(sdk_exe).expanduser() if sdk_exe else None
    template_game = sdk_path.parent / 'gui' / 'game' if sdk_path and sdk_path.exists() else None
    if template_game and template_game.exists() and not game_dir.exists():
        shutil.copytree(template_game, game_dir)
        written.append(str(game_dir))
        return 'copied_sdk_gui_template'
    game_dir.mkdir(parents=True, exist_ok=True)
    return 'minimal_generated_skeleton'


def write_renpy_baseline(project_root: Path, title: str, slug: str, written: list[str], *, force: bool, overwrite_gui: bool = True) -> None:
    game = project_root / 'game'
    script = f'''# Auto-generated supervised VN bootstrap baseline.
# Title: {title}

define narrator = Character(None)
define protagonist = Character("주인공")

default first_choice_signal = "undecided"

label start:
    jump scene_001_opening

label scene_001_opening:
    scene black
    with fade

    narrator "{title}"
    narrator "이 장면은 Hermes 감독형 VN 자동화가 생성한 검증용 첫 플레이어블 기준선입니다."
    narrator "아직 최종 원고나 승인된 자산이 아니라, 새 게임 제작 루프가 안전하게 작동하는지 확인하기 위한 placeholder입니다."

    menu:
        "첫 장면의 방향을 정한다":
            $ first_choice_signal = "story_direction"
            protagonist "좋아. 이 이야기가 어디로 향해야 하는지부터 정하자."
        "세계의 규칙을 확인한다":
            $ first_choice_signal = "world_rule"
            protagonist "먼저 이 세계가 어떤 규칙으로 움직이는지 확인해야 해."
        "관계의 균열을 본다":
            $ first_choice_signal = "relationship_hook"
            protagonist "누가 나를 믿고, 누가 나를 배신할지부터 봐야겠어."

    narrator "선택 신호: [first_choice_signal]"
    narrator "다음 단계는 Obsidian Scene 001 note를 기준으로 vertical polish를 진행하는 것입니다."
    return
'''
    options = f'''# Auto-generated options for {title}
define config.name = _("{title}")
define build.name = "{slug}"
define config.version = "0.0.1-bootstrap"
define config.save_directory = "{slug}-bootstrap"
'''
    gui = '''# Minimal GUI override placeholder.
# A full Ren'Py template may replace this when generated from the SDK.
'''
    write_text(game / 'script.rpy', script, written, force=force)
    write_text(game / 'options.rpy', options, written, force=force)
    if overwrite_gui:
        write_text(game / 'gui.rpy', gui, written, force=force)


def make_roadmap(title: str, slug: str, obs_scene_note: Path) -> dict[str, Any]:
    return {
        'schema_version': 1,
        'game_slug': slug,
        'target_level': 'level_3_human_supervised_vertical_polish_cockpit',
        'goal': 'Conversation-led Hermes VN production: ask only high-value creative/approval questions, automate folders/contracts/Obsidian/RenPy baseline/QA gates.',
        'non_goals': [
            'No auto_promote of candidates.',
            'No global_replacement of assets.',
            'No unapproved_production_replacement in game/images or game/audio.',
        ],
        'principles': [
            'title-scoped RenPy and Obsidian roots',
            'project-contract-driven automation',
            'scene-local vertical polish',
            'owner approval for irreversible creative/asset decisions',
            'real validation before claiming completion',
        ],
        'current_focus': {
            'scene_id': DEFAULT_SCENE_ID,
            'state_file': 'docs/automation/scene_remaster/current_state.json',
            'obsidian_scene_note': obs_scene_note.as_posix(),
            'status': 'bootstrap_baseline_ready',
            'next_safe_unit': 'human chooses only core direction/title-level decisions; agent proceeds with Scene 001 placeholder-to-polish loop',
        },
        'workstreams': [
            {
                'id': 'title_bootstrap_spine',
                'name': 'Title bootstrap spine',
                'status': 'done',
                'objective': 'Create title-scoped RenPy, Obsidian, contract, dashboard, and machine state roots.',
                'tasks': ['Create project folders', 'Write project_contract.json', 'Write Obsidian dashboard/current state/Scene 001 note'],
                'verification': ['vn-auto validate', 'vn-auto roadmap', 'vn-auto obsidian-audit', 'vn-auto scene-state --check-existing'],
                'evidence': ['docs/validation/bootstrap/baseline_report.md'],
                'outputs': ['docs/automation/project_contract.json', 'docs/automation/production_cockpit_roadmap.json'],
            },
            {
                'id': 'first_playable_placeholder',
                'name': 'First playable placeholder',
                'status': 'done',
                'objective': 'Create a minimal RenPy start label with a choice and safe placeholder copy.',
                'tasks': ['Write game/script.rpy', 'Write game/options.rpy', 'Preserve placeholder-only asset policy'],
                'verification': ['RenPy lint when SDK is available', 'scene-state --check-existing'],
                'evidence': ['docs/validation/bootstrap/baseline_report.md'],
                'outputs': ['game/script.rpy', 'game/options.rpy'],
            },
            {
                'id': 'conversation_director_loop',
                'name': 'Conversation director loop',
                'status': 'next',
                'objective': 'Ask the owner only important creative choices, then automate notes, patches, QA, and state writeback.',
                'tasks': ['Choose Scene 001 direction', 'Implement smallest vertical polish patch', 'Run guard/lint/capture', 'Update Obsidian/current_state'],
                'verification': ['scene-guard', 'validate-scene/capture-scene', 'obsidian-audit'],
                'evidence': ['docs/automation/scene_remaster/current_state.json'],
                'outputs': ['docs/validation/scene001_vertical_polish/'],
            },
        ],
    }


def bootstrap_scene_state(project_root: Path, obs_scene: Path, written: list[str], force: bool) -> None:
    now = datetime.now().isoformat(timespec='seconds')
    docs = project_root / 'docs/automation/scene_remaster'
    validation = project_root / 'docs/validation/bootstrap'
    validation.mkdir(parents=True, exist_ok=True)
    qa = validation / 'baseline_report.md'
    guard = validation / 'scene_patch_guard.json'
    write_text(qa, '# Bootstrap Baseline Report\n\n- status: placeholder baseline created\n- permanent_asset_changes: false\n- next: Scene 001 vertical polish after owner direction\n', written, force=force)
    write_json(guard, {'schema_version': 1, 'scene_id': DEFAULT_SCENE_ID, 'status': 'bootstrap_no_patch_guard_required'}, written, force=force)
    patch_rel = 'docs/automation/scene_remaster/patches/bootstrap_placeholder_baseline.json'
    pool_rel = f'docs/automation/scene_remaster/scene_pools/{DEFAULT_SCENE_ID}.json'
    state = {
        'schema_version': 1,
        'scene_id': DEFAULT_SCENE_ID,
        'updated_at': now,
        'status': 'owner_review_pending',
        'latest_patch_id': DEFAULT_PATCH_ID,
        'approval_status': 'pending',
        'asset_policy': 'scene_local_preview_only',
        'permanent_asset_changes': False,
        'changed_files': ['game/script.rpy', 'game/options.rpy', 'game/gui.rpy'],
        'latest_qa_report': 'docs/validation/bootstrap/baseline_report.md',
        'latest_guard_report': 'docs/validation/bootstrap/scene_patch_guard.json',
        'capture_sheets': [],
        'known_blockers': ['placeholder baseline needs owner-approved Scene 001 creative direction before production polish'],
        'next_recommended_patch': ['Ask only for core Scene 001 direction, then implement a minimal vertical polish patch with guard/lint/capture QA.'],
        'patch_manifest': patch_rel,
        'scene_pool': pool_rel,
        'candidate_count': 0,
        'supplemental_qa_reports': [],
    }
    patch_manifest = {
        'schema_version': 1,
        'scene_id': DEFAULT_SCENE_ID,
        'patch_id': DEFAULT_PATCH_ID,
        'status': 'owner_review_pending',
        'approval_status': 'pending',
        'asset_policy': 'scene_local_preview_only',
        'permanent_asset_changes': False,
        'changed_files': state['changed_files'],
        'qa_report': state['latest_qa_report'],
        'guard_report': state['latest_guard_report'],
        'supplemental_qa_reports': [],
        'obsidian_scene_note': obs_scene.as_posix(),
    }
    pool = {
        'schema_version': 1,
        'scene_id': DEFAULT_SCENE_ID,
        'policy': 'scene_local_preview_only',
        'global_replacement_allowed': False,
        'promotion_requires_owner_approval': True,
        'candidates': [],
        'updated_at': now,
    }
    write_json(docs / 'current_state.json', state, written, force=force)
    write_json(docs / 'states' / f'{DEFAULT_SCENE_ID}.json', state, written, force=force)
    write_json(project_root / patch_rel, patch_manifest, written, force=force)
    write_json(project_root / pool_rel, pool, written, force=force)
    write_text(docs / 'current_state.md', f'''# Scene Remaster State — {DEFAULT_SCENE_ID}

- updated_at: `{now}`
- status: `owner_review_pending`
- latest_patch_id: `{DEFAULT_PATCH_ID}`
- approval_status: `pending`
- asset_policy: `scene_local_preview_only`
- permanent_asset_changes: `False`
- latest_qa_report: `docs/validation/bootstrap/baseline_report.md`
- patch_manifest: `{patch_rel}`
- scene_pool: `{pool_rel}`

## Known Blockers
- placeholder baseline needs owner-approved Scene 001 creative direction before production polish

## Next Recommended Patch
- Ask only for core Scene 001 direction, then implement a minimal vertical polish patch with guard/lint/capture QA.
''', written, force=force)


def write_obsidian(obs_root: Path, title: str, slug: str, project_root: Path, written: list[str], *, force: bool) -> Path:
    scene = obs_root / 'Scenes' / 'scene_001_opening.md'
    write_text(obs_root / '00_Index.md', f'''# {title}

- Game slug: `{slug}`
- Active dashboard: [[Automation/dashboard]]
- Cold-start entrypoint: [[Automation/reader_entrypoint]]
- First scene: [[Scenes/scene_001_opening]]
''', written, force=force)
    write_text(obs_root / 'Automation' / 'dashboard.md', f'''---
type: automation_dashboard
game_slug: {slug}
status: active
updated_at: bootstrap
---

<!-- VN_AUTO_ACTIVE_STATE_START -->
## Active Resume / Machine Snapshot

- Current status: `owner_review_pending`.
- Bootstrap phase: `bootstrap_baseline_ready`.
- Current mode: `scene_by_scene_vertical_polish`.
- Active scene: [[scene_001_opening]].
- Compact active state: [[current_state_0001_bootstrap]].
- Machine state: `{(project_root / 'docs/automation/scene_remaster/current_state.json').as_posix()}`.
- Latest patch: `{DEFAULT_PATCH_ID}`.
- Latest QA: `docs/validation/bootstrap/baseline_report.md`
- Next recommended step: ask only for core Scene 001 direction, then run the vertical polish loop.
<!-- VN_AUTO_ACTIVE_STATE_END -->

# Automation Dashboard — {title}

## Read This First

1. Machine truth: `docs/automation/scene_remaster/current_state.json` in the Ren'Py project.
2. Human active brief: [[current_state_0001_bootstrap]].
3. Active scene note: [[scene_001_opening]].
4. Cold-start guide: [[reader_entrypoint]].

## Paths

- Ren'Py project: `{project_root.as_posix()}`
- Contract: `{(project_root / 'docs/automation/project_contract.json').as_posix()}`
- Obsidian title root: `{obs_root.as_posix()}`

## Conversation Policy

Ask the owner only for important creative/approval decisions: title/core direction, irreversible asset promotion, final scene approval, or major rewrite direction. Automate scaffolding, validation, QA reports, state writeback, and reversible placeholder work.

## Historical Logs

No historical production log exists yet. Keep this dashboard short; archive long logs under `Automation/archive/` and keep active truth in machine state plus the compact current-state note.
''', written, force=force)
    write_text(obs_root / 'Automation' / 'current_state_0001_bootstrap.md', f'''---
type: automation_state
game_slug: {slug}
status: active
source_status: owner_review_pending
bootstrap_phase: bootstrap_baseline_ready
latest_patch_id: {DEFAULT_PATCH_ID}
active_scene: {DEFAULT_SCENE_ID}
---

# Current State — Bootstrap Baseline

## Single Source of Truth

Machine truth is authoritative for operational status:

`{(project_root / 'docs/automation/scene_remaster/current_state.json').as_posix()}`

This note is the human-readable cockpit summary. If this note disagrees with machine state, update this note/dashboard before continuing.

## Current Playable State

- Playable range: `start` placeholder baseline.
- Latest implemented route node: [[scene_001_opening]].
- Current production mode: conversation-led supervised VN creation.

## Current Evidence

- `docs/validation/bootstrap/baseline_report.md`
- `docs/automation/scene_remaster/current_state.json`

## Next Safe Unit

Ask only for core Scene 001 creative direction, then implement a minimal vertical polish patch with real validation.

## Do Not Do Yet

- Do not generate or promote production assets from bootstrap alone.
- Do not treat placeholder prose as final writing.
- Do not make global replacements before a scene-local review loop exists.
''', written, force=force)
    write_text(obs_root / 'Automation' / 'reader_entrypoint.md', f'''---
type: readable_index
game_slug: {slug}
index_kind: reader_entrypoint
status: active
generated_at: bootstrap
---

# Reader Entrypoint — {slug}

Use this page when opening the vault cold. It points to the active cockpit and avoids turning the dashboard into a long production log.

## Active Production State

1. [[current_state_0001_bootstrap]] — current human cockpit.
2. [[dashboard]] — short active dashboard.
3. [[scene_001_opening]] — active Scene 001 note.
4. Machine state: `{(project_root / 'docs/automation/scene_remaster/current_state.json').as_posix()}`.

## Current Evidence

- QA report: `docs/validation/bootstrap/baseline_report.md`.
- Patch manifest: `docs/automation/scene_remaster/patches/bootstrap_placeholder_baseline.json`.
- Scene-local pool: `docs/automation/scene_remaster/scene_pools/scene_001_opening.json`.

## Canon / Decision Starting Points

1. [[core_direction]]
2. [[protagonist]]
3. [[decision_0001_title_bootstrap]]

## Rule

If this page disagrees with `docs/automation/scene_remaster/current_state.json`, trust machine state first and update this page/dashboard before continuing.
''', written, force=force)
    write_text(scene, f'''---
type: scene
game_slug: {slug}
scene_id: {DEFAULT_SCENE_ID}
renpy_label: {DEFAULT_SCENE_ID}
status: placeholder_baseline
route: common
chronology: opening
characters: [protagonist]
locations: []
related_assets: []
open_threads: [core_direction_pending]
---

# Scene 001 — Opening

## Purpose

First playable placeholder for `{title}`. This is not final prose and not production art; it verifies the game/project automation loop.

## Current Implementation

- Ren'Py label: `scene_001_opening` (entry `start` jumps here)
- Current policy: placeholder-only, scene-local preview, no permanent asset promotion without approval.

## Next Creative Decision Needed

Choose only the core opening direction: crisis/hook, protagonist pressure, and first meaningful choice.

## Automation State

- status: `owner_review_pending`
- latest_patch_id: `{DEFAULT_PATCH_ID}`
- asset_policy: `scene_local_preview_only`
- permanent_asset_changes: `false`
- machine_state: `{(project_root / 'docs/automation/scene_remaster/current_state.json').as_posix()}`
- latest_qa_report: `docs/validation/bootstrap/baseline_report.md`
''', written, force=force)
    write_text(obs_root / 'Characters' / 'protagonist.md', f'# Protagonist — {title}\n\nStatus: draft. Define only after core direction is chosen.\n', written, force=force)
    write_text(obs_root / 'Canon' / 'core_direction.md', f'# Core Direction — {title}\n\nStatus: pending owner direction.\n', written, force=force)
    write_text(obs_root / 'Decisions' / 'decision_0001_title_bootstrap.md', f'# Decision 0001 — Title Bootstrap\n\n- title: `{title}`\n- slug: `{slug}`\n- status: bootstrap created\n', written, force=force)
    return scene


def write_writeback_manifest(project_root: Path, written: list[str], *, force: bool) -> None:
    write_json(project_root / 'docs/automation/writeback_manifest.json', {
        'schema_version': 1,
        'purpose': 'Required Obsidian active-cockpit writebacks for a freshly bootstrapped VN title.',
        'required': [
            {'category': 'dashboard', 'path': 'Automation/dashboard.md'},
            {'category': 'active_current_state', 'path': 'Automation/current_state_0001_bootstrap.md'},
            {'category': 'reader_entrypoint', 'path': 'Automation/reader_entrypoint.md'},
            {'category': 'active_scene', 'path': 'Scenes/scene_001_opening.md'},
            {'category': 'core_direction', 'path': 'Canon/core_direction.md'},
            {'category': 'bootstrap_decision', 'path': 'Decisions/decision_0001_title_bootstrap.md'},
        ],
    }, written, force=force)


def run_tool(script: str, *args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(TOOLS / script), *args], cwd=ROOT, text=True, capture_output=True)
    return proc.returncode, proc.stdout + proc.stderr


def bootstrap(args: argparse.Namespace) -> int:
    try:
        slug = ensure_safe_slug(args.title, args.slug)
        renpy_root = Path(args.renpy_projects_root).expanduser().resolve()
        obsidian_vault = Path(args.obsidian_vault).expanduser().resolve()
        project_root = renpy_root / slug
        obs_root = obsidian_vault / slug / 'VN'
        require_under(project_root, renpy_root, 'project_root')
        require_under(obs_root, obsidian_vault, 'obsidian_project_root')
        if project_root.exists() and any(project_root.iterdir()) and not args.force:
            raise ValueError(f'NEW_TITLE_REFUSED: project already exists and is not empty: {project_root}')
        if obs_root.exists() and any(obs_root.iterdir()) and not args.force:
            raise ValueError(f'NEW_TITLE_REFUSED: obsidian title root already exists and is not empty: {obs_root}')
    except ValueError as exc:
        print(str(exc))
        return 2

    planned = [
        project_root / 'game/script.rpy',
        project_root / 'docs/automation/project_contract.json',
        project_root / 'docs/automation/production_cockpit_roadmap.json',
        obs_root / 'Automation/dashboard.md',
        obs_root / 'Scenes/scene_001_opening.md',
    ]
    if args.dry_run:
        print('NEW_TITLE_PLAN')
        print('title', args.title)
        print('slug', slug)
        print('project_root', project_root)
        print('obsidian_project_root', obs_root)
        print('dry_run True')
        print('planned', len(planned))
        for path in planned:
            print('would_write', path)
        return 0

    written: list[str] = []
    skeleton_source = maybe_copy_renpy_template(project_root, args.renpy_sdk_exe, written, args.force)
    write_renpy_baseline(project_root, args.title, slug, written, force=True, overwrite_gui=(skeleton_source != 'copied_sdk_gui_template'))

    init_argv = [
        '--project-root', str(project_root),
        '--game-title', args.title,
        '--game-slug', slug,
        '--obsidian-vault', str(obsidian_vault),
        '--obsidian-project-root', str(obs_root),
        '--obsidian-scenes-glob', 'Scenes/*.md',
        '--workflow-pack-root', args.workflow_pack_root,
        '--renpy-sdk-exe', args.renpy_sdk_exe,
        '--comfyui-endpoint', args.comfyui_endpoint,
        '--comfyui-input-root', args.comfyui_input_root,
        '--comfyui-output-root', args.comfyui_output_root,
    ]
    if args.force:
        init_argv.append('--force')
    init_rc = init_vn_automation_project.main(init_argv)
    if init_rc != 0:
        return init_rc

    obs_scene = write_obsidian(obs_root, args.title, slug, project_root, written, force=args.force)
    write_json(project_root / 'docs/automation/production_cockpit_roadmap.json', make_roadmap(args.title, slug, obs_scene), written, force=args.force)
    bootstrap_scene_state(project_root, obs_scene, written, args.force)
    write_writeback_manifest(project_root, written, force=args.force)

    validations: list[tuple[str, int, str]] = []
    for name, script, extra in [
        ('validate', 'validate_vn_automation_docs.py', ['--project-root', str(project_root)]),
        ('roadmap', 'validate_production_cockpit_roadmap.py', ['--project-root', str(project_root)]),
        ('scene-state', 'scene_remaster_state.py', ['--project-root', str(project_root), '--scene-id', DEFAULT_SCENE_ID, '--check-existing']),
        ('obsidian-audit', 'audit_obsidian_active_state.py', ['--project-root', str(project_root)]),
    ]:
        rc, out = run_tool(script, *extra)
        validations.append((name, rc, out))
        if rc != 0:
            print(f'NEW_TITLE_VALIDATION_FAILED {name}')
            print(out)
            return rc

    lint_rc: int | None = None
    lint_out = ''
    if args.renpy_sdk_exe and not args.skip_renpy_lint:
        sdk = Path(args.renpy_sdk_exe)
        if sdk.exists():
            proc = subprocess.run([str(sdk), str(project_root), 'lint'], text=True, capture_output=True, timeout=args.lint_timeout)
            lint_rc = proc.returncode
            lint_out = proc.stdout + proc.stderr
            if lint_rc != 0:
                print('NEW_TITLE_RENPY_LINT_FAILED')
                print(lint_out)
                return lint_rc

    print('NEW_TITLE_BOOTSTRAP_COMPLETE')
    print('title', args.title)
    print('slug', slug)
    print('project_root', project_root)
    print('obsidian_project_root', obs_root)
    print('skeleton_source', skeleton_source)
    print('written', len(written))
    for name, rc, _ in validations:
        print('validation', name, rc)
    if lint_rc is not None:
        print('renpy_lint', lint_rc)
    elif args.skip_renpy_lint:
        print('renpy_lint skipped_by_flag')
    else:
        print('renpy_lint skipped_no_sdk')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Create a title-scoped RenPy + Obsidian VN project ready for Hermes conversation-led automation.')
    parser.add_argument('--title', required=True, help='Human game title. Hermes should ask the owner for this or propose options.')
    parser.add_argument('--slug', default='', help='Stable ASCII slug. Required for non-ASCII titles.')
    parser.add_argument('--renpy-projects-root', default='E:/workspace/renpy-project')
    parser.add_argument('--obsidian-vault', default='E:/workspace/obsidian-vn')
    parser.add_argument('--workflow-pack-root', default='E:/workspace/comfyui-game-asset-workflows')
    parser.add_argument('--renpy-sdk-exe', default='C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe')
    parser.add_argument('--comfyui-endpoint', default='http://127.0.0.1:8000')
    parser.add_argument('--comfyui-input-root', default='C:/Users/Desktop/Documents/ComfyUI/input')
    parser.add_argument('--comfyui-output-root', default='C:/Users/Desktop/Documents/ComfyUI/output')
    parser.add_argument('--skip-renpy-lint', action='store_true', help='Skip RenPy lint. Use only for tests or when SDK is unavailable; other validators still run.')
    parser.add_argument('--lint-timeout', type=int, default=120)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)
    return bootstrap(args)


if __name__ == '__main__':
    raise SystemExit(main())
