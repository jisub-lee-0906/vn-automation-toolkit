# Installable VN Automation CLI Productization Plan

> **For Hermes:** Implement this directly with TDD; keep direct script compatibility while adding an installable command namespace.

**Goal:** Finish the next productization slice by adding a single `vn-auto` command surface, package metadata, packaging docs, and static cross-title verification.

**Architecture:** Do not move the existing production scripts yet. Add a thin Python package wrapper that dispatches subcommands to the proven `tools/*.py` scripts, preserving their arguments and behavior. Add `pyproject.toml` with a console entry point, then document both installed and source-tree usage.

**Tech Stack:** Python standard library, pytest, existing Ren'Py automation scripts, `pyproject.toml` console scripts.

---

## Reviewed unfinished items

### P3: Cross-title smoke verification

Current state: static temporary-project tests exist, but product verification is spread across individual tests and commands.

This slice will add a product-level static CLI test proving the command namespace can operate on a temporary generic title.

### P4: Installable package / command surface

Current state: no `pyproject.toml`, no package directory, no `vn-auto` command.

This slice will add:
- `vn_automation/__init__.py`
- `vn_automation/cli.py`
- `pyproject.toml`
- tests for `python -m vn_automation.cli ...`

### P5: Product documentation

Current state: initial README exists but lacks installable CLI instructions.

This slice will update:
- `docs/automation/productization_readme.md`
- `docs/automation/generic_productization_plan.md`

## Task 1: Add failing CLI namespace tests

**Objective:** Prove the desired command surface before implementation.

**Files:**
- Create: `tests/test_vn_auto_cli.py`

**Expected commands:**
```bash
python -m vn_automation.cli --help
python -m vn_automation.cli init --project-root <tmp>
python -m vn_automation.cli check --project-root <tmp>
python -m vn_automation.cli gaps --project-root <tmp> --json-out <tmp>/gap.json
```

## Task 2: Add package and dispatcher

**Objective:** Add the smallest wrapper around existing scripts.

**Files:**
- Create: `vn_automation/__init__.py`
- Create: `vn_automation/cli.py`

**Rules:**
- Dispatch to `tools/*.py` via `subprocess.run` with the current Python executable.
- Preserve remaining command args unchanged.
- Return the child process exit code.
- Keep scripts runnable directly.

## Task 3: Add package metadata

**Objective:** Make the command installable.

**Files:**
- Create: `pyproject.toml`

**Entry point:**
```toml
[project.scripts]
vn-auto = "vn_automation.cli:main"
```

## Task 4: Update docs and maturity model

**Objective:** Document both source-tree and installed command usage.

**Files:**
- Modify: `docs/automation/productization_readme.md`
- Modify: `docs/automation/generic_productization_plan.md`

## Task 5: Verify

Run:
```bash
python -m pytest tests/test_vn_auto_cli.py -q
python -m pytest tests/test_productized_project_config.py tests/test_init_vn_automation_project.py tests/test_vn_auto_cli.py -q
python -m vn_automation.cli --help
python -m vn_automation.cli verify --project-root . --skip-comfyui --skip-renpy-lint
```

Acceptance:
- CLI tests pass.
- Productization regression tests pass.
- Help lists the command namespace.
- Static runtime verifier passes without live ComfyUI/Ren'Py dependencies.
