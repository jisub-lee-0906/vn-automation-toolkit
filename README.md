# VN Automation Toolkit

Supervised production automation for Ren'Py visual novels.

This toolkit is **not** a fully unattended game generator. It is a human-directed production loop that automates repetitive tracking, validation, review-card generation, candidate promotion, and verification while keeping story direction and final asset approval under human control.

## What it does

```text
Obsidian scene note
-> Required Assets extraction
-> manifest/candidate reuse check
-> generation queue for missing assets
-> file/visual/audio QA records
-> explicit owner approval
-> promotion into Ren'Py game/
-> manifest + sidecar refresh
-> director dashboard / preview cards
-> Ren'Py lint, runtime verify, artifact audit
```

## Repository boundaries

This repository should contain reusable toolkit source only:

- `vn_automation/` — package entry point and CLI dispatcher
- `tools/` — reusable production scripts
- `tests/` — temp-project tests and safety gates
- `docs/automation/` — product docs, schemas, templates, fixtures
- `pyproject.toml` — installable package metadata

It should **not** contain title-specific runtime state:

- `game/`
- `docs/production/`
- `docs/automation/project_contract.json`
- generated candidates/runs/QA reports except deliberate test fixtures
- Ren'Py cache/saves/logs/compiled files

Individual games keep their own `game/`, production docs, manifests, screenshots, generated candidates, and promotion records under the actual Ren'Py project root.

## Install from source

From `E:/workspace/vn-automation-toolkit`:

```bash
python -m pytest -q
python -m pip install -e .
vn-auto --help
vn-auto --version
```

If the active Python lacks pip, use the environment's package manager or bootstrap pip before installing. In this Hermes Windows/Git-Bash profile, the editable command is already available through the active Hermes venv.

## Bootstrap a title

Use explicit absolute paths for bootstrap. After a title has `docs/automation/project_contract.json`, project tools may run from that project root, but otherwise fail closed instead of silently selecting the toolkit checkout.

```bash
vn-auto init \
  --project-root "E:/workspace/renpy-project/my_title" \
  --renpy-game-dir "E:/workspace/renpy-project/my_title/game" \
  --renpy-sdk-exe "C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe" \
  --workflow-pack-root "E:/workspace/comfyui-game-asset-workflows" \
  --workflow-index "E:/workspace/comfyui-game-asset-workflows/WORKFLOW_INDEX.json" \
  --obsidian-vault "C:/Users/Desktop/Documents/Obsidian Vault"
```

Confirm the `INIT_VN_AUTOMATION_PROJECT` banner prints the intended `project_root` before continuing. When `--obsidian-vault` is supplied without `--obsidian-project-root`, init now creates a title-scoped default at `<vault>/<game_slug>/VN`.

## Common commands

```bash
vn-auto preflight --project-root "E:/workspace/renpy-project/my_title" --skip-comfyui
vn-auto director status --project-root "E:/workspace/renpy-project/my_title"
vn-auto director new-scene --project-root "E:/workspace/renpy-project/my_title" --scene-id opening --title "Opening" --summary "..." --goal "..." --asset "background:bg_opening|description" --playable-placeholder
vn-auto sync --project-root "E:/workspace/renpy-project/my_title" --vault "C:/Users/Desktop/Documents/Obsidian Vault" --notes-glob "VN/Scenes/*.md"
vn-auto queue --project-root "E:/workspace/renpy-project/my_title"
vn-auto director review-assets --project-root "E:/workspace/renpy-project/my_title"
vn-auto director preview --project-root "E:/workspace/renpy-project/my_title" --scene-id opening --screenshot "E:/workspace/renpy-project/my_title/docs/production/screenshots/opening.png" --note "Runtime preview."
vn-auto director approve-candidate --project-root "E:/workspace/renpy-project/my_title" --metadata ".../metadata.json" --asset-id bg_opening --asset-type background --renpy-name "bg opening" --scene-usage opening --approved
```

Verification gates:

```bash
vn-auto validate --project-root "E:/workspace/renpy-project/my_title" --skip-obsidian
vn-auto check --project-root "E:/workspace/renpy-project/my_title"
vn-auto gaps --project-root "E:/workspace/renpy-project/my_title" --json-out "E:/workspace/renpy-project/my_title/docs/automation/integration_gap_report.json"
vn-auto verify --project-root "E:/workspace/renpy-project/my_title" --skip-comfyui
vn-auto validate-scene --project-root "E:/workspace/renpy-project/my_title" --scene-id opening --capture-plan "E:/workspace/renpy-project/my_title/docs/automation/capture_plans/opening.json" --static-only
vn-auto capture-scene --project-root "E:/workspace/renpy-project/my_title" --scene-id opening --capture-plan "E:/workspace/renpy-project/my_title/docs/automation/capture_plans/opening.json" --dry-run
vn-auto stack-doctor --obsidian-root "E:/workspace/obsidian-vn" --comfy-endpoint "http://127.0.0.1:8000" --workflow-pack-root "E:/workspace/comfyui-game-asset-workflows"
vn-auto scene-guard --project-root "E:/workspace/renpy-project/my_title" --before docs/validation/<run>/script_before.rpy --after game/script.rpy --start-label start --end-label scene_002 --require-jump scene_002 --out docs/validation/<run>/scene_patch_guard.json
vn-auto scene-state --project-root "E:/workspace/renpy-project/my_title" --scene-id scene_001 --check-existing
vn-auto audit --project-root "E:/workspace/renpy-project/my_title" --strict
```

For scene-by-scene vertical polish, use `scene-guard` after script patches to compare the backed-up before slice with the live script and enforce labels/jumps/menu/variable invariants. Use `scene-state` to write the current scene-local remaster state and preview-only candidate pool; `scene-state --check-existing` validates the existing `current_state.json`, patch manifest, guard/QA report links, capture sheets, supplemental QA reports, and preview pool policy without modifying files. Use `--supplemental-qa-report` for follow-up QA evidence, such as a menu harness report, that should not replace the primary patch QA report.

`stack-doctor` is the generic Hermes + ComfyUI + Obsidian readiness gate: it checks Hermes CLI availability, ComfyUI API health, Obsidian roots, and optional workflow/output roots. Use it before long automated runs to catch missing vaults, dead endpoints, or multiple healthy ComfyUI endpoints that could cause history/output split-brain.

## Release-ready acceptance

Before calling a toolkit checkout release-ready:

1. Toolkit repo has no title-specific `game/`, `docs/production/`, or `project_contract.json`.
2. No docs/scripts hardcode an active title path.
3. Full test suite passes.
4. Editable install points to this checkout.
5. `vn-auto --help` and `vn-auto --version` work.
6. A cleanroom title can run `init -> preflight -> director new-scene -> sync/queue -> validate -> validate-scene -> verify` with sidecars under the cleanroom title root.
7. The live title still passes `pytest`, `validate`, `check`, `verify`, and strict `audit` after runtime junk cleanup.

See `docs/automation/productization_readme.md` for the extended product workflow and Telegram approval UX.
