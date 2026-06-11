# VN Asset Generation QA Execution Tracker

Purpose: keep the asset-generation verification run durable even if the chat becomes long. This document is the running checklist for generic VN asset generation tests where the human owner performs semantic QA.

## Current Run Policy

- QA owner: human user.
- Agent role: prepare/generate candidates, preserve metadata, provide intent, file paths, and candidate lists; do **not** make final semantic QA calls.
- Promotion: disabled unless the user explicitly approves an exact candidate and metadata path.
- Cross-game reuse policy: **do not reuse approved assets from another game/title** just because they exist. Players may notice reused art/audio across games. For a new project or a different story context, regenerate fresh candidates.
- Same-game reuse policy: reuse is correct when the same game/story intentionally calls for the same asset again, e.g. recurring location, recurring prop, established character sprite, repeated UI identity.
- Candidate generation policy: generation cost is acceptable; prefer enough fresh candidates for good QA rather than over-reusing assets.

## Source Plan

New-chat readiness handoff:

```text
E:/workspace/vn-automation-toolkit/docs/vn_new_chat_readiness_handoff.md
```

Generic test plan:

```text
E:/workspace/vn-automation-toolkit/docs/asset_generation_generic_test_plan.md
```

A fresh chat should read the handoff first, then this tracker. This tracker should be updated as we execute the plan in order.

## Execution States

Use these status values:

| Status | Meaning |
| --- | --- |
| `not_started` | Not attempted yet. |
| `prepared` | Visual/audio brief and prompt slots prepared. |
| `generated` | Candidate files produced and metadata saved. |
| `file_qa_pass` | Mechanical/file QA passed; human semantic QA still pending. |
| `owner_reviewing` | Sent/listed for user QA. |
| `approved_exact_candidate` | User approved a specific candidate path + metadata path. |
| `reroll_seed` | User wants more seeds with same intent. |
| `prompt_change` | User says intent/semantics are wrong; revise prompt. |
| `rejected` | Candidate rejected. |
| `route_limitation_evidence` | Workflow limitation documented; do not keep seed-churning blindly. |
| `skipped` | Intentionally skipped for this run. |

## Ordered Test Queue

| Order | ID | Workflow / Axis | Generic Asset ID | Status | Intent Summary | Candidate/Metadata Paths | User QA Result / Notes |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | GAGT-01 | `scene_background` baseline location | `bg_core_location_day_test` | `owner_reviewing` | Generated fresh daylight noble archive/library core-location candidates for user semantic QA. | Summary: `E:/workspace/renpy-project/sihanbu_villainess_badend/docs/automation/generation_runs/gagt01_bg_core_location_day_test_summary_20260611_1319.json`; contact sheet: `E:/workspace/renpy-project/sihanbu_villainess_badend/docs/automation/review_contact_sheets/gagt01_bg_core_location_day_test_contact_sheet_20260611_1319.jpg` | Awaiting user QA: approve exact candidate / hold / reroll seed / prompt-change / reject / route limitation evidence. |
| 2 | GAGT-02 | `scene_background` mood variant | `bg_core_location_mood_variant_test` | `not_started` | Generate the same location class under a different mood/time/weather. |  |  |
| 3 | GAGT-03 | `scene_background` secondary/private location | `bg_private_location_test` | `not_started` | Generate a smaller/private/transitional location for visual variety. |  |  |
| 4 | GAGT-04 | `scene_prop_cg` single object | `prop_single_key_object_test` | `not_started` | Generate one clear key prop as a close-up cut-in. |  |  |
| 5 | GAGT-05 | `scene_prop_cg` document/evidence | `prop_document_evidence_test` | `not_started` | Generate document/evidence layout without readable fake text. |  |  |
| 6 | GAGT-06 | `scene_prop_cg` contextual clue | `prop_contextual_clue_test` | `not_started` | Generate a clue object with light environmental context. |  |  |
| 7 | GAGT-07 | `char_base` character A | `char_main_a_base_test` | `not_started` | Generate a fresh main character identity/base reference for the current project. |  |  |
| 8 | GAGT-08 | `char_base` character B | `char_main_b_base_test` | `not_started` | Generate a contrasting second character identity/base reference for the current project. |  |  |
| 9 | GAGT-09 | `char_expression` expression preservation | `char_main_a_expression_test` | `not_started` | Generate an expression variant from a project-local source character image. |  |  |
| 10 | GAGT-10 | `char_alpha` transparent sprite | `char_main_a_alpha_test` | `not_started` | Generate transparent sprite candidate from a project-local character source. |  |  |
| 11 | GAGT-11 | `scene_event_cg` single-character beat | `cg_main_a_action_beat_test` | `not_started` | Generate an event CG for one project-local character in an action/emotion beat. |  |  |
| 12 | GAGT-12 | `scene_event_cg` two-character/tension beat | `cg_two_character_tension_test` | `not_started` | Generate high-variance relationship/confrontation CG; document identity drift or workflow limits. |  |  |
| 13 | GAGT-13 | `ui_system_alert_frame` UI frame | `ui_textless_notification_frame_test` | `not_started` | Generate fresh title-local textless UI notification frame/backdrop. |  |  |
| 14 | GAGT-14 | `audio_bgm_with_sfx` BGM | `bgm_scene_mood_bed_test` | `not_started` | Generate a dialogue-safe music bed for a generic scene mood. |  |  |
| 15 | GAGT-15 | `audio_bgm_with_sfx` SFX | `sfx_short_action_cue_test` | `not_started` | Generate a short one-shot cue for action/UI/prop moments. |  |  |
| 16 | GAGT-16 | generation policy discipline | `fresh_generation_policy_test` | `not_started` | Verify policy chooses same-game intentional reuse only; otherwise fresh generation for different projects/contexts. |  |  |
| 17 | GAGT-17 | queue discipline | `archived_smoke_queue_test` | `not_started` | Verify archived/smoke requests stay out of active generation/review queue. |  |  |
| 18 | GAGT-18 | lifecycle discipline | `lifecycle_backfill_test` | `not_started` | Verify canonical lifecycle state remains clear from generated candidate to review/promotion. |  |  |

## Per-Test Brief Template

Before each generation, fill this section or add a dated subsection.

```text
Test ID:
Project / title:
Workflow:
Asset ID:
Fresh generation required? yes/no
Same-game reuse allowed? only if story explicitly needs same asset
Intent:
Subject/class:
Narrative function:
Structure anchors:
Mood/time/weather:
Composition / textbox-safe needs:
Style constraints:
Failure modes:
Candidate count:
Prepared prompt slots path:
Generated metadata paths:
Generated candidate paths:
File QA reports:
Owner QA decision:
Next action:
```

## Review Message Shape

When presenting candidates to the user for QA, use:

```text
VN asset QA: <asset_id>
Test ID: <GAGT-ID>
Workflow: <workflow_id>
Intent: <what we tried to generate>
Candidates:
1. <candidate path> | metadata: <metadata path> | seed: <seed>
2. ...
File QA: <pass/fail + report path>
Please QA for: <brief checklist>
Choices: approve exact candidate / hold / reroll seed / prompt-change / reject / route limitation evidence
```

## Notes

- If chat context gets long, resume from this file and the generic test plan.
- If a project-specific run is needed, create a project-local copy or execution report under that project's `docs/automation/` or `docs/validation/` directory, but keep the generic policy here.
- Do not silently import assets from previous titles into a new title. Use previous assets only as private visual references if explicitly useful, not as production files.
