# Generic VN Asset Generation Test Plan

Purpose: validate the reusable VN asset-generation pipeline across asset classes without depending on one title, one story, or one aesthetic. This plan defines **what kind of asset we intend to generate** and **what the human QA reviewer should judge**. It is not a promotion checklist; all outputs remain review candidates until a human approves an exact candidate + metadata path.

## Scope

This test plan is project-agnostic. A concrete title may bind the placeholders below to its own canon, but the validation target is the toolkit/workflow capability:

- Can the pipeline route a request to the correct workflow?
- Can prompt slots express the intended asset without hidden runner creativity?
- Can candidates be saved with enough metadata for review, reroll, prompt-change, or promotion?
- Can file QA and human semantic QA remain separate?
- Can lifecycle state remain unambiguous: generated, QA-pass, visual-review-pending, approved, promoted, verified, archived/superseded?
- Can the system avoid cross-game asset reuse while still allowing intentional same-game story reuse?

## Non-Goals

- Do not prove one specific game's art direction is final.
- Do not auto-promote generated candidates.
- Do not optimize every workflow to perfection in one pass.
- Do not use story-specific approved assets as required dependencies unless the test explicitly covers same-game input-image behavior.
- Do not reuse approved assets across different games/titles as production assets. Fresh generation is preferred for new projects or unrelated story contexts.

## Generic Placeholders

When executing this plan for a real project, replace these placeholders with title-local values:

| Placeholder | Meaning |
| --- | --- |
| `<project_root>` | Selected VN/Ren'Py project root with `docs/automation/project_contract.json` |
| `<title_style>` | Broad visual style, e.g. rofan gothic, school mystery, sci-fi, slice-of-life |
| `<main_character_a>` | A protagonist/heroine/lead character with stable visual anchors |
| `<main_character_b>` | A second lead/rival/antagonist with stable visual anchors |
| `<core_location>` | A recurring story location |
| `<private_location>` | A smaller emotional or secret location |
| `<key_prop>` | A story-relevant clue/object |
| `<system_ui_mood>` | UI mood such as fatal warning, gentle notification, romance choice, investigation alert |

## Required Metadata Per Candidate

Every generated candidate should record:

```json
{
  "asset_id": "generic_test_asset_id",
  "asset_type": "background|prop|event_cg|char_base|char_expression|char_alpha|ui|bgm|sfx",
  "workflow_id": "workflow_name",
  "project_root": "<project_root>",
  "visual_brief": "human-authored intent",
  "prompt_slots": {},
  "seed": 0,
  "candidate_copies": [],
  "qa_reports": [],
  "lifecycle_stage": "generated_file_pending_qa|file_qa_pass_pending_visual_review",
  "review_intent": "what the owner should judge"
}
```

## Test Matrix

| ID | Capability Axis | Workflow | Generic Asset ID | Candidate Count | Generation Intent | Human QA Focus |
| --- | --- | --- | --- | ---: | --- | --- |
| GAGT-01 | Location routing / simple T2I background | `scene_background` | `bg_core_location_day_test` | 3 | Generate a reusable 9:16 mobile portrait background for `<core_location>` in normal/day or baseline lighting. This proves the pipeline can create a recognizable VN location with no characters. | Location should be recognizable in 1–2 seconds. Must be sprite/textbox-safe. No humans, fake text, logos, modern artifacts unless title-appropriate. |
| GAGT-02 | Mood/time variant for same location | `scene_background` | `bg_core_location_mood_variant_test` | 3 | Generate the same `<core_location>` under a different time/weather/mood condition, e.g. night, rain, sunset, alarm state. This tests controlled variation without changing location class. | Should still read as the same class/location, not a different place. Mood shift should be visible. Avoid over-dark unusable results. |
| GAGT-03 | Secondary/private location | `scene_background` | `bg_private_location_test` | 3 | Generate a smaller private or transitional location such as corridor, bedroom, office, rooftop, alley, archive, garden path. This tests visual-variety coverage beyond the main stage. | Clear spatial class and depth. Should not collapse into generic room/ballroom/classroom. Needs empty staging area for sprites. |
| GAGT-04 | Single-object prop recognition | `scene_prop_cg` | `prop_single_key_object_test` | 4 | Generate a close-up cut-in of `<key_prop>` as one clear object. This tests whether prop CG can maintain single-object semantics. | One main focal object. Correct object class. No duplicate clutter, fake readable text, hands, or romance-symbol drift unless requested. |
| GAGT-05 | Evidence/document prop without fake text | `scene_prop_cg` | `prop_document_evidence_test` | 4 | Generate an abstract document/clue/certificate/letter-like prop where layout matters but readable text must not be baked in. This is a common VN evidence use case. | Should imply document/evidence via blocks, seals, folds, redactions, margins, etc. Reject legible gibberish, logos, or over-romantic love-letter framing if not intended. |
| GAGT-06 | Small object + scene-context prop | `scene_prop_cg` | `prop_contextual_clue_test` | 3 | Generate a clue object embedded in a minimal environmental context, e.g. broken ornament on floor, bloodless trace, torn ribbon, sealed envelope on desk. Tests prop + contextual readability. | Prop must remain the subject. Context should support story but not dominate. Avoid accidental gore/modern items unless title wants them. |
| GAGT-07 | Character base / identity anchor | `char_base` | `char_main_a_base_test` | 3 | Generate an opaque base/reference image for `<main_character_a>` with stable identity anchors: hair, eyes, silhouette, outfit, palette, stance. | Identity should be memorable and repeatable. Crop/headroom usable. Hands may be imperfect but should not ruin base. No unwanted background complexity. |
| GAGT-08 | Second character base / contrast | `char_base` | `char_main_b_base_test` | 3 | Generate a base/reference image for `<main_character_b>` with contrasting identity and role silhouette. Tests whether the character workflow is not overfit to one gender/style/default example. | Should read as the intended role/gender/age/temperament. Avoid defaulting to the same face/body/outfit as character A. Note any workflow bias. |
| GAGT-09 | Expression preservation | `char_expression` | `char_main_a_expression_test` | 2 | From an approved or test base image, generate one expression variant: smile, suspicion, fear, anger, forced calm, sadness, etc. Tests input-image expression edit. | Identity/outfit must stay close. Expression should be clear but not exaggerated. Check face mask seams, eye/mouth artifacts, and unintended outfit changes. |
| GAGT-10 | Alpha / transparent sprite readiness | `char_alpha` | `char_main_a_alpha_test` | 2 | Remove background from a character source to create a transparent sprite candidate. Tests sprite-production readiness. | Review on light, dark, and in-game backgrounds. Check hair halo, missing edges, cape/skirt cuts, transparent holes. Compare against source. |
| GAGT-11 | Event CG identity + action beat | `scene_event_cg` | `cg_main_a_action_beat_test` | 3 | Generate a 9:16 mobile portrait event CG with `<main_character_a>` in a story action/emotion beat. This tests identity anchoring, composition, and cinematic staging. | Character identity should survive. Pose/emotion/story beat should be readable. Background should support the action. Hands/anatomy and textbox-safe area matter. |
| GAGT-12 | Two-character or confrontation-like event CG | `scene_event_cg` | `cg_two_character_tension_test` | 3 | Generate a confrontation/relationship-pressure CG involving `<main_character_a>` and `<main_character_b>`, or a single-character substitute if the current workflow cannot reliably do two characters. Tests high-variance composition. | Judge identity drift, number of characters, staging clarity, romantic vs hostile tone, anatomy/hands, and whether the result is usable or only direction-probe evidence. |
| GAGT-13 | Textless UI frame/backdrop | `ui_system_alert_frame` | `ui_textless_notification_frame_test` | 3 source + optional cleanplate variants | Generate a textless UI frame/backdrop matching `<system_ui_mood>`. This validates UI route separation from prop CG and tests overlay readiness. | No baked text, fake UI words, logos, icons, central emblems, or blocking objects. Outer ornament and central text plate should be judged separately with live overlay preview. |
| GAGT-14 | BGM role contract | `audio_bgm_with_sfx` / `audio_bgm` | `bgm_scene_mood_bed_test` | 2 | Generate a 20–30s music bed for a generic scene mood: tension, romance, mystery, tragedy, calm, comedy, etc. Tests BGM prompt shape and role routing. | No vocals/speech unless requested. Should sit under dialogue. Loop/edit potential, tail cleanliness, and mood fit matter more than standalone song complexity. |
| GAGT-15 | SFX one-shot role contract | `audio_bgm_with_sfx` / `audio_sfx` | `sfx_short_action_cue_test` | 3 | Generate a short one-shot cue: paper, door, notification, stamp, magic pulse, impact, choice confirm. Tests SFX prompt shape and short duration control. | 1.5–2.5s preferred for one-shots. No melody/voice. Clear transient and material/timbre. Should not become BGM. |
| GAGT-16 | Fresh-generation policy / same-game reuse only | toolkit resolver + queue | `fresh_generation_policy_test` | n/a | Given a request that resembles an asset from another title, verify the production policy still creates fresh candidates for the current project. Reuse is allowed only when the current same-game story intentionally calls for the same established asset. | QA checks routing/policy result, not image quality. The system should not copy/import cross-game production assets just because they exist; same-game recurring locations/props/characters may be reused intentionally. |
| GAGT-17 | Archived/smoke request exclusion | toolkit queue | `archived_smoke_queue_test` | n/a | Given archived smoke/test requests, verify owner review queue excludes them from active review/generation while preserving evidence. | Active queue counts should remain clean. Archived evidence should remain discoverable. |
| GAGT-18 | Lifecycle normalization | toolkit lifecycle | `lifecycle_backfill_test` | n/a | Given legacy metadata with `qa_status`, `promotion_status`, or mixed `status`, normalize to canonical `lifecycle_stage`. | QA checks manifest/metadata state clarity, not art. Unknown lifecycle values should fail validation. |

## Recommended Generic Execution Order

1. **Routing and baseline T2I**: GAGT-01 to GAGT-06.
2. **Character source and input-image routes**: GAGT-07 to GAGT-10.
3. **High-variance cinematic routes**: GAGT-11 to GAGT-12.
4. **UI and audio edge routes**: GAGT-13 to GAGT-15.
5. **Toolkit production discipline**: GAGT-16 to GAGT-18.

GAGT-16 means **fresh generation by default across games**. It should not be interpreted as global asset reuse. Reuse is only correct inside the same game when the same story asset intentionally recurs.

This order starts with low-dependency workflows, then tests input-image workflows, then tests complex composition, then tests non-image workflows and state/routing discipline.

## Generic Visual Brief Template

Use this template before each generation:

```text
Asset ID: <asset_id>
Workflow: <workflow_id>
Asset type: <asset_type>
Title style: <title_style>
Subject/class: <what must be recognized immediately>
Narrative function: <why this asset exists in the scene>
Structure anchors: <geometry/objects/composition that prove the class>
Mood/time/weather: <mood and lighting>
Composition: <camera/framing/textbox/sprite safe area>
Style constraints: <palette, genre, no-text/no-human rules>
Failure modes: <what the model may confuse it with>
QA decision choices: approve exact candidate / reroll seed / prompt-change / reject
```

## Generic Audio Brief Template

```text
Asset ID: <asset_id>
Workflow role: audio_bgm | audio_sfx
Scene role: <what moment this supports>
Prompt intent: <instrumentation/form/mood for BGM OR short physical cue for SFX>
Duration target: <20-30s BGM or 1.5-2.5s SFX, etc.>
Must avoid: vocals, speech, melody, alarm, ambience, etc.
QA decision choices: approve exact candidate / reroll seed / prompt-change / reject
```

## Human QA Decision Labels

Use consistent labels after review:

| Label | Meaning |
| --- | --- |
| `approve_exact_candidate` | Candidate can proceed to explicit approval/promotion gate. |
| `hold_for_comparison` | Candidate is usable but should be compared against alternatives. |
| `reroll_seed` | Prompt intent is right; execution/composition/artifacts are weak. |
| `prompt_change` | Candidate is semantically wrong; revise visual anchors/prompt slots. |
| `reject_semantic_miss` | Wrong subject/story role. |
| `reject_artifact` | Correct intent but unacceptable artifacts/anatomy/text/watermark. |
| `route_limitation_evidence` | Workflow appears unsuitable or biased for this asset class without deeper changes. |

## Pass Criteria for the Pipeline

The generic asset-generation pipeline is considered healthy when:

- Each active workflow can produce at least one file-QA-pass candidate for its intended asset class.
- Metadata records prompt intent, seed, workflow, candidate paths, and lifecycle stage.
- Owner QA can decide without guessing what the candidate was supposed to be.
- Reuse/archived/lifecycle tests prevent queue confusion.
- Promotion remains approval-gated and bound to exact candidate metadata.

## Failure Interpretation

- **File QA fail**: investigate runner/output path/format first.
- **Repeated semantic miss in one workflow**: revise prompt slots; do not keep seed-churning indefinitely.
- **Identity drift in event CG**: verify character anchors/source metadata policy; may be workflow limitation.
- **UI central symbols/fake text**: reject or produce labeled cleanplate review variants; do not promote raw source.
- **SFX becomes BGM or BGM becomes stinger**: fix audio role prompt shape and duration/mode before more seeds.
- **Queue includes smoke/archive items**: lifecycle/queue classification bug, not art QA failure.
