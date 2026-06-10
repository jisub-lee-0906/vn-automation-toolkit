# VN Automation Process Improvement — Readable Obsidian Indexes — 2026-06-10

## Problem

A VN title can pass runtime/lint/contact-sheet gates and even Obsidian active-state semantic gates while still being hard for humans or future RAG sessions to read because key knowledge is spread across long production logs.

Observed weak spots:

- route_seed_tracker can become too long to scan quickly;
- scene notes can be correct but tactical/log-like rather than reader-facing;
- emotional arcs can be split across character notes and scene notes;
- a cold reader needs a clean entrypoint separate from automation logs.

## Implemented Solution

Added a new CLI command:

```bash
python -m vn_automation.cli obsidian-summarize --project-root <project> --write
```

It generates reader-facing Obsidian indexes under the title-scoped `obsidian_project_root`:

```text
Automation/reader_entrypoint.md
Timeline/common_act2_true_end_timeline.md
Canon/true_end_seed_payoff_map.md
Continuity/emotional_arc_serena_lucian_true_end.md
```

Added an audit gate:

```bash
python -m vn_automation.cli obsidian-audit \
  --project-root <project> \
  --require-writeback-manifest \
  --require-readable-indexes
```

This fails if the readable indexes are missing or do not reference the active current-state note and ending arc.

## Generated Index Roles

### `Automation/reader_entrypoint.md`

Cold-start reading order. Separates:

- current production state;
- story/readability maps;
- canon/character sources;
- implementation proof.

### `Timeline/common_act2_true_end_timeline.md`

Compresses the implemented route into readable blocks:

```text
Opening death-sentence contract
First investigation / source tracing
First public trap and survival contract closure
Act 2 route pressure escalation
Public confrontation / private cost / record duel
Source-handler chase and method reversal
TRUE END record reversal
```

### `Canon/true_end_seed_payoff_map.md`

Condenses route seeds into payoff rows:

```text
Contract Blade
Red Author
Villainess Crown
Lifespan Condition
Black Scribe
```

Each row tracks planted source, TRUE END payoff, current status, and future route potential.

### `Continuity/emotional_arc_serena_lucian_true_end.md`

Maps Serena/Lucian relationship development across route phases and captures the writing rule:

```text
Lucian is questioner / record partner, not savior.
Serena weaponizes records, reputation, and the false ending title into proof.
```

## Test Evidence

```bash
PYTHONPATH=. pytest tests/test_obsidian_readability_indexes.py -q
# 2 passed

PYTHONPATH=. pytest -q
# 123 passed
```

Regression coverage:

- `obsidian-summarize --write` creates all readable index notes;
- each note links active current-state and ending arc;
- `obsidian-audit --require-readable-indexes` fails before generation;
- the same audit passes after generation;
- formal assurance matrix includes the new command.

## Current Project Verification

Applied to:

```text
E:/workspace/renpy-project/sihanbu_villainess_badend
```

Generated notes:

```text
E:/workspace/obsidian-vn/sihanbu_villainess_badend/VN/Automation/reader_entrypoint.md
E:/workspace/obsidian-vn/sihanbu_villainess_badend/VN/Timeline/common_act2_true_end_timeline.md
E:/workspace/obsidian-vn/sihanbu_villainess_badend/VN/Canon/true_end_seed_payoff_map.md
E:/workspace/obsidian-vn/sihanbu_villainess_badend/VN/Continuity/emotional_arc_serena_lucian_true_end.md
```

Final audit:

```text
OBSIDIAN_ACTIVE_STATE_AUDIT_PASSED
writeback_manifest_audit: PASS, required_count: 13
readable_index_audit: PASS
```

## Updated Final Signoff Ladder

For baseline-changing VN work:

```bash
python -m vn_automation.cli obsidian-summarize --project-root <project> --write
python -m vn_automation.cli obsidian-audit \
  --project-root <project> \
  --update-dashboard-active-block \
  --latest-report docs/validation/<run>/final_report.md \
  --require-writeback-manifest \
  --require-readable-indexes
```

Then run the normal runtime gates:

```text
preflight
check
Ren'Py lint
validate-scene/contact-sheet QA
traceback check
```
