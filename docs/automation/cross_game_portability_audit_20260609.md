# Cross-Game Portability Hardening Audit — 2026-06-09

## Goal

Make the VN automation loop safe for future Ren'Py titles, not only the active `sihanbu_villainess_badend` project. The priority is fail-closed project selection, title-scoped Obsidian roots, generic validation commands, and tests that run on temporary fixture games.

## Changes Implemented

1. **Project selection fail-closed**
   - `tools/vn_product_config.py` no longer silently treats the toolkit checkout as a VN project when no project is selected.
   - Resolution order is now explicit `--project-root`, `VN_AUTOMATION_PROJECT_ROOT`, then current working directory only if it contains `docs/automation/project_contract.json`.
   - Otherwise tools stop with `PROJECT_SELECTION_REQUIRED`.

2. **Title-scoped Obsidian default**
   - `tools/init_vn_automation_project.py` now defaults `obsidian_project_root` to `<obsidian_vault>/<game_slug>/VN`.
   - This avoids flat shared `<vault>/VN` contamination across multiple games.

3. **Cross-game preflight command**
   - Added `tools/preflight_vn_project.py`.
   - Exposed as `vn-auto preflight`.
   - Checks contract, game dir, title-scoped Obsidian root, safe scene glob, manifest path, workflow pack/index, Ren'Py SDK configuration, and optional ComfyUI endpoint readiness.

4. **Generic scene validation skeleton**
   - Added `tools/validate_scene.py`.
   - Exposed as `vn-auto validate-scene`.
   - Consumes a project contract plus scene-specific capture plan JSON.
   - Static mode validates the capture plan, runs asset refs, writes `manifest.json` and `report.md`, and cleans runtime junk. Runtime mode calls the generic `capture-scene` engine.

5. **Regression tests**
   - Added `tests/test_cross_game_portability_hardening.py`.
   - Tests fail-closed behavior, cwd project detection, title-scoped Obsidian bootstrap, preflight, and generic validate-scene static phase against temporary fixture projects.

## Independent Review Fixes

A fresh code review found and the implementation fixed these portability blockers:

- `validate-scene --out-dir` now must stay under the selected project root and is checked before directory creation.
- `validate-scene --scene-id` now rejects path traversal and path separators via a safe slug regex.
- `vn-auto` now preserves the caller's current working directory when dispatching tools, so cwd-based project detection works through the installed CLI wrapper.
- `preflight` now validates title-scoped Obsidian roots while accepting both supported layouts: `<base vault>/<game_slug>/VN` and dedicated `<game_slug vault>/VN`.
- `preflight` now rejects `renpy_game_dir` values outside the selected project root, preventing cross-title game-dir contamination.


## Second-Pass Adversarial Hardening

After a second independent audit, the implementation added additional fail-closed gates:

- CLI-exposed project commands (`sync`, `queue`, `generate`) no longer default to the toolkit repository when no project is selected.
- `VN_AUTOMATION_PROJECT_ROOT` conflicts with a different cwd project are refused unless `--project-root` is explicit.
- `build_project_paths()` centrally refuses external contracts, mismatched `renpy_project_root`, and project-scoped sidecars outside the selected root.
- `preflight` checks `workflow_index` remains under `workflow_pack_root`.
- Capture plans now validate safe capture names, duplicate names, capture count, `.rpy` warp targets, positive line numbers, in-file line bounds, and bounded `wait_seconds`.
- `validate-scene` phases have explicit timeouts and structured timeout logs.
- `capture-scene` has `--runtime-timeout`, refuses unsupported runtime dependencies without traceback, validates screenshot output paths, and reports Ren'Py runtime error files.


## Third-Pass Strict Review Fixes

A strict follow-up review found and the implementation fixed additional blockers:

- `generate` now writes its default batch output under the active project instead of crashing when `--out` is omitted.
- `sync`, `queue`, `generate`, and `resolve` now reject sidecar output overrides outside the selected project root.
- `queue` and `generate` reject absolute or parent-traversing `--resolved-glob` values and require every matched resolved-request file to stay under the project root.
- `resolve` now requires both its output and source asset-request JSON to stay under the selected project root.
- Project commands now require an existing, valid `project_contract.json`; invalid/missing contracts fail as `PROJECT_CONTRACT_INVALID` rather than silently using defaults.


## Fourth-Pass Strict Review Fixes

A second strict follow-up review found and the implementation fixed the last reported escape paths:

- `resolve --manifest` and `resolve --generation-runs-root` now reject paths outside the selected project root.
- `resolve` now rejects source asset-request files outside the selected project root.
- `gaps --json-out` now rejects output paths outside the selected project root.


## Fifth-Pass Strict Review Fixes

A third strict follow-up review found and the implementation fixed the final reported CLI-exposed escape paths:

- `audit --json-out` now rejects output paths outside the selected project root.
- `init --renpy-game-dir` now rejects game directories outside `--project-root`.
- Direct `promote` now rejects metadata, candidate source files, and QA reports outside the selected project root.

## Remaining Deliberate Boundary

The new `capture-scene` command is a title-agnostic runtime contact-sheet engine that consumes the same capture plan. Runtime execution is available when `renpy_sdk_exe`, Pillow, and Windows window-capture dependencies are present; static validation remains available without launching Ren'Py.

## Verified Commands

```text
python -m pytest tests/test_cross_game_portability_hardening.py -q
python -m pytest tests/test_cross_game_portability_hardening.py tests/test_productized_project_config.py tests/test_init_vn_automation_project.py tests/test_vn_auto_cli.py -q
python -m pytest -q
python -m vn_automation.cli preflight --project-root E:/workspace/renpy-project/sihanbu_villainess_badend --skip-comfyui
python -m vn_automation.cli validate-scene --project-root E:/workspace/renpy-project/sihanbu_villainess_badend --scene-id scene_044_origin_interrogation_or_timestamp_trap --capture-plan E:/workspace/renpy-project/sihanbu_villainess_badend/docs/automation/capture_plans/scene_044_origin_interrogation_or_timestamp_trap.json --static-only --out-dir E:/workspace/renpy-project/sihanbu_villainess_badend/docs/validation/cross_game_validate_scene_scene044_20260609
python -m vn_automation.cli capture-scene --project-root E:/workspace/renpy-project/sihanbu_villainess_badend --scene-id scene_044_origin_interrogation_or_timestamp_trap --capture-plan E:/workspace/renpy-project/sihanbu_villainess_badend/docs/automation/capture_plans/scene_044_origin_interrogation_or_timestamp_trap.json --dry-run
```

Latest observed result during implementation:

```text
32 passed
92 passed
PREFLIGHT_PASSED
VALIDATE_SCENE_PASSED
CAPTURE_SCENE_CONTACT_SHEET
```


