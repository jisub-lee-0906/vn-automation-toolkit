# VN Automation Process Improvement — Active-State + Label Capture Hardening — 2026-06-10

## Scope

This supersedes the initial Obsidian active-state gate note by completing the remaining process-improvement candidates discovered during `sihanbu_villainess_badend`:

```text
1. Label-based capture plans to avoid script line-number drift.
2. Machine-managed dashboard active-state block.
3. script.rpy scene-label ↔ Obsidian scene-note drift audit.
4. Required writeback manifest gate for major baseline handoffs.
```

## Implemented Features

### 1. Label-based capture plans

Capture plans may now use stable labels instead of absolute script lines:

```json
{
  "name": "true_end_title_card",
  "warp_label": "scene_068_true_end_title_card_probe",
  "wait_seconds": 2.4
}
```

For post-label timing, plans may use an explicit relative offset:

```json
{
  "name": "act2_formal_pressure_gate",
  "warp_label": "scene_029_act2_formal_pressure_gate",
  "warp_offset_lines": 18,
  "wait_seconds": 1.2
}
```

The toolkit resolves this at runtime to Ren'Py's required `game/script.rpy:<line>` warp target. This preserves existing Ren'Py behavior while reducing stale absolute-line capture plans after script edits.

Implementation:

```text
tools/validate_scene.py: find_label_line / resolve_capture_warp
tools/capture_scene_contact_sheet.py: dry-run/runtime uses resolve_capture_warp
```

### 2. Machine dashboard active block

`obsidian-audit` now supports:

```bash
python -m vn_automation.cli obsidian-audit \
  --project-root <project> \
  --update-dashboard-active-block \
  --latest-report docs/validation/<run>/final_report.md
```

It writes/updates this block in `Automation/dashboard.md`:

```markdown
<!-- VN_AUTO_ACTIVE_STATE_START -->
## Active Resume / Machine Snapshot
...
<!-- VN_AUTO_ACTIVE_STATE_END -->
```

The historical dashboard body remains intact, but future sessions get a stable machine-managed active snapshot first.

### 3. Scene label ↔ Obsidian note drift audit

`obsidian-audit` now extracts Ren'Py labels from `game/**/*.rpy` and compares them against `Scenes/*.md` notes.

Failing condition:

```text
A scene note appears active/stale but has no matching script label, same scene number, range note, or live renpy_label frontmatter.
```

Warning condition:

```text
Script scene labels not covered by a note.
```

Warnings are non-fatal because branch/converge/probe labels often should not have one note each.

### 4. Writeback manifest gate

Major baseline handoffs can now require a project-local manifest:

```bash
python -m vn_automation.cli obsidian-audit \
  --project-root <project> \
  --require-writeback-manifest
```

Default required path:

```text
docs/automation/writeback_manifest.json
```

Example:

```json
{
  "required": [
    {"category": "dashboard", "path": "Automation/dashboard.md"},
    {"category": "current_state", "path": "Automation/current_state_20260610.md"},
    {"category": "scene_arc", "path": "Scenes/scene_056_to_068_true_end_arc.md"},
    {"category": "character_state", "path": "Characters/serena.md"},
    {"category": "canon", "path": "Canon/gameplay_direction.md"}
  ]
}
```

All referenced paths are confined under the title-scoped Obsidian root and must exist.

## Regression Tests

Added/expanded:

```text
tests/test_obsidian_active_state_audit.py
- consistent active notes pass
- stale dashboard current_state fails
- no active current_state fails
- machine dashboard block update works
- stale scene note without live label fails
- writeback manifest requirement fails closed then passes

tests/test_cross_game_portability_hardening.py
- capture plan accepts warp_label + warp_offset_lines and dry-run resolves current line
```

## Verification Evidence

Toolkit full suite:

```text
PYTHONPATH=. pytest -q
121 passed
```

Current project label-plan/runtime verification:

```text
validate-scene true_end_visual_cards_20260610: PASS
validate-scene full_route_playthrough_smoke_20260610: PASS
obsidian-audit --require-writeback-manifest: PASS
```

Current project final gate:

```text
preflight: PREFLIGHT_PASSED
asset refs: ALL_RENPY_ASSET_REFS_EXIST
Ren'Py lint: PASS
traceback: TRACEBACK_CLEAN
```

## Required Future Process

For any future VN/interactive fiction project, after major baseline-changing work:

```text
1. Prefer warp_label / warp_offset_lines in capture plans.
2. Run validate-scene/contact-sheet QA.
3. Update title-scoped Obsidian notes.
4. Create/update docs/automation/writeback_manifest.json for changed RAG nodes.
5. Run obsidian-audit --update-dashboard-active-block --require-writeback-manifest.
6. Only then report the project as safe for future continuation.
```
