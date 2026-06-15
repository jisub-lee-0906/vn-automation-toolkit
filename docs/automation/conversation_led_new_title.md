# Conversation-Led New VN Automation

## Goal

When a user tells Hermes Agent they want to make a VN/game, Hermes should behave like a supervised VN director:

1. Ask only the important creative decisions.
2. Create title-scoped Ren'Py and Obsidian folders automatically.
3. Initialize machine-readable project contracts and automation state.
4. Create a first playable placeholder baseline.
5. Run real validation before claiming readiness.
6. Continue scene-by-scene with owner approval only for irreversible or high-impact decisions.

This document is a product contract for `vn-auto new-title` and for Hermes sessions using the VN skills.

## User Interaction Policy

Ask the owner for:

- final title or approval of a proposed title;
- ASCII slug when the title is non-English or ambiguous;
- one-sentence genre/tone/core hook;
- irreversible asset promotion or replacement;
- final scene approval;
- major rewrite direction.

Do not ask the owner for routine implementation details:

- exact project folder when defaults apply;
- whether to create `docs/automation/project_contract.json`;
- whether to create title-scoped Obsidian folders;
- whether to run validation/lint/audit after changes;
- whether to clean runtime junk;
- whether to update current_state/dashboard after validated work.

## Default Paths

```text
Ren'Py projects root: E:/workspace/renpy-project
Obsidian vault root: E:/workspace/obsidian-vn
Workflow pack: E:/workspace/comfyui-game-asset-workflows
Ren'Py SDK: C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe
ComfyUI endpoint: http://127.0.0.1:8000
```

Given slug `<slug>`, the command creates:

```text
E:/workspace/renpy-project/<slug>
E:/workspace/obsidian-vn/<slug>/VN
```

## Bootstrap Command

```bash
cd E:/workspace/vn-automation-toolkit
python -m vn_automation.cli new-title \
  --title "<human title>" \
  --slug <ascii_slug> \
  --renpy-projects-root E:/workspace/renpy-project \
  --obsidian-vault E:/workspace/obsidian-vn \
  --workflow-pack-root E:/workspace/comfyui-game-asset-workflows \
  --renpy-sdk-exe C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe
```

## Safety Rules

- Non-ASCII or ambiguous titles require explicit `--slug` and fail with `GAME_SLUG_REQUIRED` when missing.
- Project and Obsidian target roots must stay under the selected roots.
- Non-empty project or Obsidian roots are refused unless `--force` is explicitly supplied.
- Generated bootstrap uses `scene_local_preview_only`, `permanent_asset_changes=false`, and no approved candidates.
- Successful bootstrap requires `validate`, `roadmap`, `scene-state --check-existing`, and `obsidian-audit` to pass.
- Ren'Py lint is run when the SDK executable exists and `--skip-renpy-lint` is not supplied.

## Created Artifacts

Ren'Py/project side:

- `game/script.rpy` with `start -> scene_001_opening` placeholder baseline.
- `game/options.rpy` with title/version metadata.
- SDK GUI template copied when available.
- `docs/automation/project_contract.json`.
- `docs/automation/production_cockpit_roadmap.json`.
- `docs/automation/scene_remaster/current_state.json`.
- `docs/automation/scene_remaster/patches/bootstrap_placeholder_baseline.json`.
- `docs/automation/scene_remaster/scene_pools/scene_001_opening.json`.
- `docs/validation/bootstrap/baseline_report.md`.

Obsidian side:

- `00_Index.md`.
- `Automation/dashboard.md`.
- `Automation/current_state_0001_bootstrap.md`.
- `Scenes/scene_001_opening.md`.
- starter `Characters/`, `Canon/`, and `Decisions/` notes.

## Post-Bootstrap Loop

After `NEW_TITLE_BOOTSTRAP_COMPLETE`, Hermes should:

1. Report created paths and validation output.
2. Ask the owner only for the next Scene 001 creative direction.
3. Implement one minimal vertical polish patch.
4. Run scene guard, lint, capture/validate scene QA, scene-state check, and Obsidian audit.
5. Continue scene-by-scene.

## Verification Snapshot

The command is covered by:

```text
tests/test_new_title_bootstrap.py
tests/test_vn_auto_cli.py
tests/test_formal_assurance_invariants.py
tests/test_production_cockpit_roadmap.py
```

A live Windows smoke under `docs/validation/new_title_bootstrap_smoke_20260615/` produced:

```text
NEW_TITLE_BOOTSTRAP_COMPLETE
validation validate 0
validation roadmap 0
validation scene-state 0
validation obsidian-audit 0
renpy_lint 0
remaining rpyc/rpyb: 0 after cleanup
```
