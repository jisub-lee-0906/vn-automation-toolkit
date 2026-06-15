# VN Automation Formal Invariants

## Purpose

This document defines the proof-oriented assurance target for the reusable VN automation toolkit. It does **not** claim mathematical or permanent defect freedom for every future environment. It defines a closed set of safety invariants and the evidence used to show that current CLI-exposed project automation preserves those invariants.

## Definitions

- **Project root**: the selected Ren'Py/VN automation root, resolved by explicit `--project-root`, `VN_AUTOMATION_PROJECT_ROOT`, or current working directory only when it contains `docs/automation/project_contract.json`.
- **Project contract**: `docs/automation/project_contract.json` under the selected project root unless an explicit project-local `--contract` is supplied.
- **Project sidecar**: any automation output or production sidecar generated for the selected game, including asset request batches, queue files, generation batch records, validation reports, audit reports, screenshots, promotion logs, and resolved request files.
- **Intentional external dependency**: a path or endpoint that is allowed to live outside the project because it is explicitly configured as shared infrastructure: Obsidian vault/project root, ComfyUI endpoint, workflow pack root, Ren'Py SDK executable, Hermes Telegram/media cache.

## Invariant I1 — Project Selection Is Explicit

For every CLI-exposed project command, the selected project root is resolved fail-closed:

1. explicit `--project-root`; else
2. `VN_AUTOMATION_PROJECT_ROOT`; else
3. current working directory only if it contains `docs/automation/project_contract.json`; else
4. fail with `PROJECT_SELECTION_REQUIRED`.

If `VN_AUTOMATION_PROJECT_ROOT` and a cwd project both exist and differ, the command fails unless `--project-root` is explicit.

Evidence:

- `tests/test_cross_game_portability_hardening.py::test_project_tools_fail_closed_without_active_project`
- `tests/test_cross_game_portability_hardening.py::test_cli_project_commands_fail_closed_without_active_project`
- `tests/test_cross_game_portability_hardening.py::test_env_project_root_conflict_with_cwd_project_is_refused`

## Invariant I2 — Contract-Constrained Project Paths

If `build_project_paths(project_root, contract)` succeeds, then the following project-critical paths resolve under `project_root`:

- `renpy_game_dir`
- `manifest_path`
- `generation_runs_root`
- `generated_candidates_root`
- `promotion_log_root`
- the selected `project_contract.json`

A contract with a mismatched `renpy_project_root`, invalid JSON, missing file, or external project sidecar path fails closed as `PROJECT_CONTRACT_INVALID`.

Evidence:

- `tests/test_cross_game_portability_hardening.py::test_build_project_paths_requires_existing_valid_contract`
- `tests/test_cross_game_portability_hardening.py::test_preflight_rejects_cross_game_contract_roots_and_sidecars`
- `tests/test_formal_assurance_invariants.py::test_contract_path_fuzz_rejects_all_project_sidecar_escapes`

## Invariant I3 — CLI Project Outputs Stay Under Project Root

For project-scoped CLI commands, every automation sidecar output supplied by a user-controlled CLI option is resolved relative to the selected project root and rejected if it escapes the selected project.

Covered output options include:

- `sync --out-summary`
- `queue --out-md`
- `queue --out-json`
- `generate --out`
- `resolve --out`
- `gaps --json-out`
- `audit --json-out`
- `validate-scene --out-dir`
- `capture-scene --out-dir`
- promotion manifest/log outputs

Evidence:

- `tests/test_cross_game_portability_hardening.py::test_project_commands_reject_sidecar_outputs_outside_project`
- `tests/test_cross_game_portability_hardening.py::test_resolve_rejects_output_outside_project`
- `tests/test_cross_game_portability_hardening.py::test_gaps_rejects_json_outside_project`
- `tests/test_cross_game_portability_hardening.py::test_audit_rejects_json_outside_project`
- `tests/test_cross_game_portability_hardening.py::test_validate_scene_rejects_output_dir_outside_project`

## Invariant I4 — Project Inputs Cannot Cross Titles

Project-scoped inputs that can affect asset selection, promotion, validation, or integration are rejected if they escape the selected project root.

Covered inputs include:

- `resolve` source asset-request JSON
- `resolve --manifest`
- `resolve --generation-runs-root`
- `queue/generate --resolved-glob` matches
- `promote` metadata JSON
- `promote` candidate source file
- `promote` QA report JSON
- `validate-scene` capture plan
- `capture-scene` capture plan
- `init --renpy-game-dir`

Evidence:

- `tests/test_cross_game_portability_hardening.py::test_resolve_rejects_external_manifest_and_generation_runs_root`
- `tests/test_cross_game_portability_hardening.py::test_queue_and_generate_reject_resolved_glob_parent_traversal`
- `tests/test_cross_game_portability_hardening.py::test_promote_rejects_external_metadata_candidate_and_qa`
- `tests/test_cross_game_portability_hardening.py::test_init_rejects_renpy_game_dir_outside_project`
- `tests/test_formal_assurance_invariants.py::test_project_path_helpers_are_deterministically_fuzzed`

## Invariant I5 — Capture Plans Are Bounded And Project-Local

If a capture plan is accepted by `validate-scene` or `capture-scene`, then:

- `scene_id` is a safe slug, not a path;
- every capture name is a safe slug;
- capture names are unique;
- capture count is bounded;
- every warp target is a `.rpy` file under the selected project root;
- warp line numbers are positive integers and within the target file bounds;
- wait durations and pre-capture menu actions are bounded;
- optional expected menu choices are checked against the live script at the target warp;
- screenshot/contact-sheet outputs remain under the selected project root;
- runtime timeout produces structured failure, not an unbounded hang or traceback dump.

Evidence:

- `tests/test_cross_game_portability_hardening.py::test_capture_plan_rejects_unsafe_capture_name_and_wait`
- `tests/test_cross_game_portability_hardening.py::test_capture_plan_rejects_malformed_warp_and_too_many_captures`
- `tests/test_cross_game_portability_hardening.py::test_capture_scene_refuses_runtime_when_dependencies_missing_even_with_fake_renpy`
- `tests/test_cross_game_portability_hardening.py::test_validate_scene_runtime_failure_is_structured_without_traceback`


## Invariant I6 — Promotion And Generation Surfaces Are Identity-Safe

Promotion and direct generation-runner metadata surfaces now enforce additional production-safety constraints:

- `promote --asset-id` must be a safe manifest/log slug.
- `promote --renpy-name` must be a safe Ren'Py image name.
- `promote --filename` must be a single safe filename component and must reject traversal, alternate data streams, Windows reserved device names, and control characters.
- `promote --force-overwrite` must back up the overwritten production asset under `docs/production/promotions/backups/` before replacing it.
- direct smoke runner `--out-metadata` outputs are project-confined.
- `scene_event_cg --char-base-metadata` is project-confined.
- generation runner timeout/failure is recorded per item as structured batch output rather than aborting with an unstructured traceback.
- manifest validation rejects unsafe asset IDs, unsafe Ren'Py names, and unsafe promoted paths.

Evidence:

- `tests/test_assurance_completion_hardening.py::test_promote_rejects_unsafe_identity_and_filename_values`
- `tests/test_assurance_completion_hardening.py::test_promote_force_overwrite_creates_backup`
- `tests/test_assurance_completion_hardening.py::test_generation_runner_timeout_is_per_item_structured`
- `tests/test_assurance_completion_hardening.py::test_direct_smoke_runner_refuses_out_metadata_outside_project`
- `tests/test_assurance_completion_hardening.py::test_direct_smoke_runners_refuse_external_metadata_surfaces`
- `tests/test_assurance_completion_hardening.py::test_scene_event_cg_refuses_external_char_base_metadata`
- `tests/test_assurance_completion_hardening.py::test_manifest_validation_rejects_unsafe_identity_and_paths`

## Assurance Evidence Matrix

The machine-readable command classification lives in:

```text
docs/automation/formal_assurance_command_matrix.json
```

Every command exposed by `vn_automation.cli.COMMANDS` must be present in this matrix. Static tests enforce that project-class commands include an explicit scope-guard marker and that project-root globs are paired with traversal validation and per-match confinement checks.

Command coverage summary:

- `init` — bootstrap command with explicit project root and confined game dir.
- `new-title` — bootstrap command that creates a title-scoped Ren'Py + Obsidian project for conversation-led Hermes VN automation; refuses ambiguous/non-ASCII slugs without `--slug`, refuses non-empty target roots without `--force`, and runs core validation gates before success.
- `check` — project command via centralized project path builder.
- `gaps` — project command with confined report output.
- `validate` — project command via centralized project path builder.
- `normalize-lifecycle` — project command that canonicalizes manifest asset lifecycle stages through the contract-selected manifest.
- `sync` — project command with confined project sidecars and intentional Obsidian input.
- `resolve` — project command with confined source, manifest, generation runs, and output.
- `queue` — project command with confined resolved-glob matches and queue outputs.
- `generate` — project command with confined resolved-glob matches and batch output.
- `promote` — project command with confined metadata, candidate, QA, manifest, destination, and logs.
- `verify` — project command; configured external runtime dependencies are intentional.
- `preflight` — project command that verifies contract, sidecars, workflow index, and Obsidian scope.
- `polish-scene` — post-patch vertical-polish harness with project-confined before/after scripts and optional capture plan, deterministic `scene-guard`, `validate`, `obsidian-audit`, optional Ren'Py lint, optional `validate-scene`, QA report writeback, `scene-state`, and `scene-state --check-existing`.
- `validate-scene` — project command with capture-plan and validation output confinement.
- `capture-scene` — project command with capture-plan and screenshot output confinement.
- `scene-guard` — project command with confined before/after script inputs and guard report output for deterministic patch invariant checks.
- `scene-intent` — project command that normalizes owner scene direction into project-confined intent JSON/Markdown, pre-patch script backup, optional capture plan, and next `polish-scene` command without modifying game scripts/assets.
- `scene-state` — project command with confined scene remaster state/patch/pool outputs and a read-only `--check-existing` validation mode for current state links and preview-only safety flags.
- `stack-doctor` — non-project read-only readiness command for the shared Hermes + ComfyUI + Obsidian automation stack; it checks explicitly supplied/default shared infrastructure roots and endpoints.
- `audit` — project command with confined audit JSON output.
- `obsidian-audit` — project command with confined Obsidian active-state audit JSON output; verifies title-scoped dashboard/current_state semantic freshness, scene-label drift, writeback coverage, and optional readable-index coverage.
- `obsidian-summarize` — project command that generates title-scoped reader-facing Obsidian timeline/seed/emotional-arc indexes and a confined JSON summary.
- `director` — project command with explicit project root; Hermes media cache is intentional external delivery cache. Director is intentionally documented as a UX/orchestration command with targeted `require_under` checks rather than the uniform central `build_project_paths()` pattern used by most project commands.
- `roadmap` — project command that validates a project-confined human-supervised production cockpit roadmap, including explicit anti-auto-promote/non-global-replacement goals and existing evidence links.

## Out of Scope

These invariants deliberately do not claim any of the following:

- permanent absence of all bugs in future code;
- correctness of Ren'Py, Windows APIs, ComfyUI, Pillow, pywin32, filesystem drivers, or hardware;
- semantic/artistic quality of generated images/audio;
- correctness of operator-provided external generation runner commands;
- correctness of contents inside intentionally external shared infrastructure such as workflow packs, Obsidian vaults, or ComfyUI endpoints;
- immunity to future code changes that bypass the tested helpers and policy matrix.


## Latest Verification Snapshot

Observed during the proof-oriented assurance pass:

```text
python -m pytest tests/test_formal_assurance_invariants.py -q
6 passed
python -m pytest tests/test_cross_game_portability_hardening.py tests/test_formal_assurance_invariants.py -q
38 passed
python -m pytest -q
109 passed
python -m vn_automation.cli preflight --project-root E:/workspace/renpy-project/sihanbu_villainess_badend --skip-comfyui
PREFLIGHT_PASSED
python -m vn_automation.cli validate-scene --project-root E:/workspace/renpy-project/sihanbu_villainess_badend --scene-id scene_044_origin_interrogation_or_timestamp_trap --capture-plan E:/workspace/renpy-project/sihanbu_villainess_badend/docs/automation/capture_plans/scene_044_origin_interrogation_or_timestamp_trap.json --static-only --out-dir E:/workspace/renpy-project/sihanbu_villainess_badend/docs/validation/cross_game_validate_scene_scene044_20260609
VALIDATE_SCENE_PASSED
python -m vn_automation.cli capture-scene --project-root E:/workspace/renpy-project/sihanbu_villainess_badend --scene-id scene_044_origin_interrogation_or_timestamp_trap --capture-plan E:/workspace/renpy-project/sihanbu_villainess_badend/docs/automation/capture_plans/scene_044_origin_interrogation_or_timestamp_trap.json --dry-run
CAPTURE_SCENE_CONTACT_SHEET
```

## Maintenance Rule

Any new command added to `vn_automation.cli.COMMANDS` must update `formal_assurance_command_matrix.json`, must appear in this document, and must add or reuse tests proving the relevant path/project invariants. The formal assurance tests fail if the matrix and CLI command registry diverge.
