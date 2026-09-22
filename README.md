# VN Automation Toolkit

Supervised production automation for Ren'Py visual novels.

This toolkit is **not** a fully unattended game generator. It is a human-directed production loop that automates repetitive tracking, validation, review-card generation, candidate promotion, and verification while keeping story direction and final asset approval under human control.

## Public-readiness status (2026-09-23)

- **This environment:** documentation and command/configuration review only. No title project, Ren'Py runtime, ComfyUI backend, model, GPU, external API, or database was run.
- **Earlier records:** the 2026-09-23 repository audit recorded 132 passing tests for this toolkit, including Windows console encoding regression coverage. Those tests were not rerun during this documentation-only update and do not establish a Ren'Py runtime result.
- **Not verified:** cleanroom bootstrap, generation queue execution, promoted assets, and Ren'Py lint/runtime/end-to-end behavior.

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

From the repository root in any normal clone:

```bash
python -m pip install -e .
vn-auto --help
vn-auto --version
```

`pyproject.toml` defines the `vn-auto` entry point. The checkout-specific paths shown in older examples below are replaced with placeholders; supply paths that exist on your machine. Test execution is intentionally not claimed here because it was not rerun in this environment.

## Run tests

With `pytest` installed in the development environment, run `python -m pytest -q` from the repository root. This is a test command, not a claim of a fresh test run.

## Bootstrap a title

Use explicit absolute paths for bootstrap. After a title has `docs/automation/project_contract.json`, project tools may run from that project root, but otherwise fail closed instead of silently selecting the toolkit checkout.

```bash
vn-auto init \
  --project-root "/path/to/my_title" \
  --renpy-game-dir "/path/to/my_title/game" \
  --renpy-sdk-exe "/path/to/renpy-sdk/renpy" \
  --workflow-pack-root "/path/to/workflow-pack" \
  --workflow-index "/path/to/workflow-pack/WORKFLOW_INDEX.json" \
  --obsidian-vault "/path/to/obsidian-vault"
```

Confirm the `INIT_VN_AUTOMATION_PROJECT` banner prints the intended `project_root` before continuing. When `--obsidian-vault` is supplied without `--obsidian-project-root`, init now creates a title-scoped default at `<vault>/<game_slug>/VN`.

## Common commands

```bash
vn-auto preflight --project-root "/path/to/my_title" --skip-comfyui
vn-auto director status --project-root "/path/to/my_title"
vn-auto director new-scene --project-root "/path/to/my_title" --scene-id opening --title "Opening" --summary "..." --goal "..." --asset "background:bg_opening|description" --playable-placeholder
vn-auto sync --project-root "/path/to/my_title" --vault "/path/to/obsidian-vault" --notes-glob "VN/Scenes/*.md"
vn-auto queue --project-root "/path/to/my_title"
vn-auto director review-assets --project-root "/path/to/my_title"
vn-auto director preview --project-root "/path/to/my_title" --scene-id opening --screenshot "/path/to/my_title/docs/production/screenshots/opening.png" --note "Runtime preview."
vn-auto director approve-candidate --project-root "/path/to/my_title" --metadata ".../metadata.json" --asset-id bg_opening --asset-type background --renpy-name "bg opening" --scene-usage opening --approved
```

Verification gates:

```bash
vn-auto validate --project-root "/path/to/my_title" --skip-obsidian
vn-auto check --project-root "/path/to/my_title"
vn-auto gaps --project-root "/path/to/my_title" --json-out "/path/to/my_title/docs/automation/integration_gap_report.json"
vn-auto verify --project-root "/path/to/my_title" --skip-comfyui
vn-auto validate-scene --project-root "/path/to/my_title" --scene-id opening --capture-plan "/path/to/my_title/docs/automation/capture_plans/opening.json" --static-only
vn-auto capture-scene --project-root "/path/to/my_title" --scene-id opening --capture-plan "/path/to/my_title/docs/automation/capture_plans/opening.json" --dry-run
vn-auto audit --project-root "/path/to/my_title" --strict
```

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

## Windows console compatibility

Director console status output uses ASCII markers so the CLI also works in legacy Windows code pages such as CP949. This affects display only; project files and approval behavior are unchanged.

## Automated verification (2026-09-23)

No GitHub Actions workflows or runs are configured/recorded. The local test/build records above are not a remote CI pass.
