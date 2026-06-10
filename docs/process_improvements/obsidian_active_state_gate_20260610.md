# VN Automation Process Improvement — Obsidian Active-State Gate — 2026-06-10

## Problem Found

During the `sihanbu_villainess_badend` project, Ren'Py runtime/lint/contact-sheet gates passed, but title-scoped Obsidian notes still contained stale active context:

```text
- dashboard.md pointed to old scene016/scene043-era state.
- current_state_20260607 remained active even after Scene 001–068 TRUE END completion.
- scene055 hook map contained old shorthand next-hook names.
- character/canon notes stopped at earlier demo states.
```

Root cause: existing automation verified executable game artifacts well, but did not enforce semantic freshness of the Obsidian RAG layer.

## Implemented Fix

Added a new fail-closed CLI gate:

```bash
python -m vn_automation.cli obsidian-audit --project-root <project_root>
```

Implementation:

```text
tools/audit_obsidian_active_state.py
vn_automation/cli.py command: obsidian-audit
```

Regression tests:

```text
tests/test_obsidian_active_state_audit.py
```

The audit checks:

```text
- Obsidian project root exists.
- Exactly one frontmatter `type: automation_state` + `status: active` note exists.
- `Automation/dashboard.md` exists.
- Dashboard links the active current_state note.
- Dashboard does not point to known superseded `current_state_20260607` as active.
- Dashboard latest-QA lines do not look like stale early/mid-scene reports after final route work.
- Notes are not both `status: active` and textually marked superseded.
- Known stale scene055 next-hook names are absent.
```

## Test Evidence

RED first:

```text
pytest tests/test_obsidian_active_state_audit.py -q
3 failed because obsidian-audit was not a CLI command.
```

GREEN:

```text
pytest tests/test_obsidian_active_state_audit.py tests/test_vn_auto_cli.py -q
6 passed
```

Related regression subset:

```text
pytest tests/test_obsidian_active_state_audit.py tests/test_vn_auto_cli.py \
  tests/test_cross_game_portability_hardening.py::test_preflight_rejects_obsidian_root_outside_configured_vault \
  tests/test_cross_game_portability_hardening.py::test_init_defaults_obsidian_project_root_to_game_slug_namespace -q
8 passed
```

Real project verification:

```text
python -m vn_automation.cli obsidian-audit --project-root E:/workspace/renpy-project/sihanbu_villainess_badend
OBSIDIAN_ACTIVE_STATE_AUDIT_PASSED
```

Output report:

```text
E:/workspace/renpy-project/sihanbu_villainess_badend/docs/automation/obsidian_active_state_audit.json
```

## New Required Process

For future VN projects, after any major route/arc completion or active baseline change, the final signoff ladder should include:

```text
preflight
asset check
Ren'Py lint
validate-scene/contact-sheet QA
sync/queue if asset requests changed
obsidian-audit
```

A project is not ready for continuation handoff if `obsidian-audit` fails, even if Ren'Py lint and runtime capture pass.

## Limitations / Future Work

This first gate is intentionally conservative and heuristic. Future improvements:

```text
- Generate dashboard active block automatically between machine markers.
- Add label-based capture plans so script line-number drift cannot stale warp targets.
- Expand semantic audit to compare script labels against scene notes automatically.
- Include changed character/canon-note writeback requirements in a structured manifest.
```
