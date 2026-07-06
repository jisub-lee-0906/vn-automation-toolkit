from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'

COMMANDS: dict[str, tuple[str, str]] = {
    'init': ('init_vn_automation_project.py', 'Bootstrap VN automation docs/config for a RenPy project.'),
    'new-title': ('bootstrap_new_vn_title.py', 'Create a title-scoped RenPy + Obsidian VN project for conversation-led Hermes automation.'),
    'check': ('check_renpy_asset_refs.py', 'Check literal RenPy image/audio refs under game/ exist.'),
    'gaps': ('report_renpy_integration_gaps.py', 'Report manifest-to-RenPy integration gaps.'),
    'validate': ('validate_vn_automation_docs.py', 'Validate automation docs, schemas, workflow index, and manifest.'),
    'normalize-lifecycle': ('normalize_asset_lifecycle.py', 'Normalize manifest assets to canonical lifecycle_stage values.'),
    'sync': ('sync_obsidian_scene_asset_requests.py', 'Extract and resolve Required Assets from Obsidian scene notes.'),
    'resolve': ('resolve_asset_requests.py', 'Resolve extracted asset requests against manifest/candidates/workflow routes.'),
    'queue': ('build_owner_review_queue.py', 'Build owner review queue from resolved scene asset requests.'),
    'generate': ('run_generation_queue.py', 'Run workflow generation for queued generate decisions.'),
    'promote': ('promote_asset_candidate.py', 'Promote an approved candidate into RenPy assets and manifest.'),
    'verify': ('verify_vn_automation_runtime.py', 'Run product/runtime verification gates.'),
    'preflight': ('preflight_vn_project.py', 'Run fail-closed cross-game project readiness checks.'),
    'polish-scene': ('polish_scene_harness.py', 'Run the safe post-patch scene vertical-polish guard/QA/state harness.'),
    'validate-scene': ('validate_scene.py', 'Run title-agnostic scene validation gates from a capture plan.'),
    'capture-scene': ('capture_scene_contact_sheet.py', 'Capture a RenPy scene contact sheet from a generic capture plan.'),
    'scene-guard': ('scene_patch_guard.py', 'Compare before/after RenPy scene slices and enforce deterministic patch invariants.'),
    'scene-intent': ('scene_intent_harness.py', 'Normalize an owner scene direction into an intent packet and prepared polish-scene run.'),
    'scene-state': ('scene_remaster_state.py', 'Write scene-local remaster state, patch manifest, and preview-only candidate pool files.'),
    'stack-doctor': ('automation_stack_doctor.py', 'Check the generic Hermes + ComfyUI + Obsidian automation stack.'),
    'audit': ('audit_vn_artifacts.py', 'Audit artifact/git categories and preview screenshot evidence.'),
    'obsidian-audit': ('audit_obsidian_active_state.py', 'Audit Obsidian active-state/dashboard/current-state semantic consistency.'),
    'obsidian-summarize': ('summarize_obsidian_readability_indexes.py', 'Generate reader-facing Obsidian timeline/seed/emotional-arc indexes.'),
    'director': ('vn_director_console.py', 'Director-facing UX console: dashboard, scene drafts, approval cards.'),
    'roadmap': ('validate_production_cockpit_roadmap.py', 'Validate the human-supervised VN production cockpit roadmap.'),
    'auto-approve': ('auto_approve_candidate.py', 'Evaluate policy-based delegated auto-approval for generated VN asset candidates.'),
    'gameplay-composition-qa': ('gameplay_composition_qa.py', 'Validate VN gameplay screenshot composition: sprite placement, scale, textbox overlap, and basic background harmony.'),
    'vision-composition-qa': ('vision_composition_qa.py', 'Validate structured vision composition scorecards for VN auto-approval.'),
    'scene-story-plan': ('scene_story_plan.py', 'Create a structured VN scene story plan with asset opportunities.'),
    'story-qa': ('story_qa.py', 'Validate VN story plan canon/voice/emotion/reward gates.'),
    'scene-enrichment-plan': ('scene_enrichment_plan.py', 'Convert a story plan into proactive asset candidate batches.'),
    'enrichment-queue': ('enrichment_queue.py', 'Create resolved generation queue and prompt slots from a scene enrichment plan.'),

}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='vn-auto',
        description='Supervised RenPy VN production automation command namespace.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Commands pass all remaining arguments through to the underlying tools/*.py script.',
    )
    parser.add_argument('--version', action='store_true', help='Print version and exit.')
    command_list = '\n'.join(f'  {name:<8} {description}' for name, (_, description) in COMMANDS.items())
    parser.add_argument('command', nargs='?', choices=sorted(COMMANDS), help=f'Command to run. Available:\n{command_list}')
    parser.add_argument('args', nargs=argparse.REMAINDER, help='Arguments passed to the selected command.')
    return parser


def dispatch(command: str, args: Sequence[str]) -> int:
    script_name, _ = COMMANDS[command]
    script = TOOLS / script_name
    if not script.exists():
        print(f'vn-auto: missing command script: {script}', file=sys.stderr)
        return 2
    # Preserve the caller's cwd so tools can use cwd-based project selection
    # when it contains docs/automation/project_contract.json.
    completed = subprocess.run([sys.executable, str(script), *args])
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    if ns.version:
        from vn_automation import __version__

        print(f'vn-auto {__version__}')
        return 0
    if not ns.command:
        parser.print_help()
        return 0
    forwarded = list(ns.args)
    if forwarded and forwarded[0] == '--':
        forwarded = forwarded[1:]
    return dispatch(ns.command, forwarded)


if __name__ == '__main__':
    raise SystemExit(main())
