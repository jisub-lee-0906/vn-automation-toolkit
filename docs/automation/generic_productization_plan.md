# Generic Ren'Py VN Automation Productization Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Convert the current title-specific supervised VN production loop into a reusable, project-configured automation toolkit for multiple Ren'Py projects.

**Architecture:** Keep the proven production spine unchanged: scene notes -> asset requests -> resolver -> generation queue -> QA -> owner approval -> promotion -> Ren'Py integration checks. Productization focuses on moving every title-specific path into `docs/automation/project_contract.json` and shared helpers, then adding generic project-root CLIs and tests.

**Tech Stack:** Python CLI tools, Ren'Py project files, JSON contracts/manifests, Obsidian Markdown scene notes, ComfyUI workflow pack.

---

## Productization levels

### Level P1: Configurable single-project toolkit

Status: implemented and tested at static/generic-project level.

Acceptance:
- Tools accept `--project-root` and/or `VN_AUTOMATION_PROJECT_ROOT`.
- No automation script defaults to `<renpy_project_root>`.
- Static checks and integration reports run against a temporary generic Ren'Py project in tests.

### Level P2: Bootstrap a new title

Status: implemented and tested at scaffold level.

Acceptance:
- `init_vn_automation_project.py` can create `docs/automation`, schemas, templates, `game/data/asset_manifest.json`, and a starter `project_contract.json` for a fresh Ren'Py title.
- Dry-run mode prints planned writes before creating files.
- Existing files are not overwritten without `--force`.

### Level P3: Cross-title smoke verification

Status: static temporary-project tests, CLI-level cross-title checks, a fresh-game bootstrap -> scene-note sync -> owner queue -> static verify lifecycle test, artifact audit tests, tokened Telegram approval loop tests, Telegram message_id-bound plain reply approval tests, and a separate-title runtime smoke pass. The 2026-05-31 smoke bootstrapped `moonlit_runtime_smoke_20260531_235807`, generated a real ComfyUI background candidate, sent it to Telegram, bound the returned message_id, consumed a plain `승인` reply through `telegram-approve-message`, promoted into the sample title, integrated the asset in Ren'Py, captured a Ren'Py runtime screenshot, and passed full ComfyUI/Ren'Py `vn-auto verify`.

Acceptance:
- A fixture project and the current title both pass static validation, asset-ref checks, resolver tests, and integration-gap reports.
- Runtime verification supports `--skip-comfyui` and `--skip-renpy-lint` for CI/static product tests.

### Level P4: Installable package / command surface

Status: implemented as an installable thin command wrapper.

Acceptance:
- A single command namespace exists: `vn-auto init`, `vn-auto sync`, `vn-auto resolve`, `vn-auto queue`, `vn-auto generate`, `vn-auto promote`, `vn-auto check`, `vn-auto gaps`, `vn-auto validate`, `vn-auto audit`, `vn-auto verify`.
- Scripts can still be run directly for backward compatibility.

### Level P5: Product documentation

Status: product README includes source-tree, editable install, command namespace, gates, and limitations. External distribution docs are still pending if this is published outside the project repository.

Acceptance:
- A README explains prerequisites, bootstrap, project contract fields, common workflows, and safety gates.
- The maturity model clearly says this is supervised production automation, not fully unattended game generation.

## Immediate task breakdown

### Task 1: Centralize project config resolution

**Objective:** Add one shared module for project paths and contract loading.

**Files:**
- Create: `tools/vn_product_config.py`
- Modify consumers as needed.
- Test: `tests/test_productized_project_config.py`

**Verification:**
Run `python -m pytest tests/test_productized_project_config.py -q`.

### Task 2: Remove hardcoded title roots from static tools

**Objective:** Make validators and Ren'Py static reports operate on any project root.

**Files:**
- Modify: `tools/validate_vn_automation_docs.py`
- Modify: `tools/check_renpy_asset_refs.py`
- Modify: `tools/report_renpy_integration_gaps.py`
- Modify: `tools/backfill_asset_manifest_from_renpy.py`

**Verification:**
Run:
```bash
python tools/check_renpy_asset_refs.py --project-root <renpy_project_root>
python tools/report_renpy_integration_gaps.py --project-root <renpy_project_root> --json-out docs/automation/integration_gap_report.json
python tools/validate_vn_automation_docs.py --project-root <renpy_project_root>
```

### Task 3: Make promotion and generation runners project-configurable

**Objective:** Ensure candidate promotion and generation runners use caller-provided project roots.

**Files:**
- Modify: `tools/promote_asset_candidate.py`
- Modify: `tools/run_*_smoke.py`
- Modify: `tools/run_generation_queue.py` if runner command defaults need command-level abstraction.

**Verification:**
Run unit tests and confirm runner `--help`/import does not contain a title-specific default path.

### Task 4: Add bootstrap CLI

**Objective:** Create a new-title bootstrap command.

**Files:**
- Create: `tools/init_vn_automation_project.py`
- Test: `tests/test_init_vn_automation_project.py`

**Verification:**
Use a temp directory fixture and assert all docs/templates/schema/manifest files are created without touching the current title.

### Task 5: Add product README and maturity gates

**Objective:** Document how to use the toolkit as a product.

**Files:**
- Create: `docs/automation/productization_readme.md`
- Update: `docs/automation/vn_automation_design.md` only if needed.

**Verification:**
Docs validator should pass and the README should include setup, safety gates, and limitations.
