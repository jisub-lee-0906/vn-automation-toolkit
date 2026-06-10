# Prompt Routing Structure Audit — 2026-06-01

## Why this audit happened

`bg_bus_interior_dawn` was requested as a dawn first-bus interior, but the first generation received a classroom prompt because the scene-background runner silently fell back to README example tags (`school`, `classroom`, `chalkboard`). This violated the intended VN automation boundary: the agent should make creative/contextual decisions from skills and scene context; code should execute, validate, and record those decisions.

## Classification

### Hidden creative routing / fixed

- `tools/run_scene_background_smoke.py`
  - Previous risk: `choose_background_tags()` interpreted natural language and fell back to classroom tags.
  - Fix: hidden routing now fail-closes with `UNROUTED_SCENE_BACKGROUND`; production generation requires an agent-authored prompt-slots JSON.

- `tools/run_scene_prop_cg_smoke.py`
  - Previous risk: `choose_prop_tags()` interpreted note/letter requests and added extra prompt/negative clauses by keyword.
  - Fix: hidden routing now fail-closes with `UNROUTED_SCENE_PROP_CG`; production generation requires agent-authored `item_form`, `material_detail`, `placement_background` slots, with optional explicit `positive_append` / `negative_append` in the prompt-slots file.

- `tools/run_scene_event_cg_smoke.py`
  - Previous risk: fixed character/outfit placeholder tags (`mature_female`, `school_uniform`, etc.) and fixed scene context (`auditorium`, `indoors`, `spotlight`) were always used.
  - Fix: production generation requires agent-authored `character_features`, `outfit_detail`, and `scene_context` prompt slots. The runner still preserves char-base seed reuse mechanics, but the creative scene setting is no longer fixed in code.

### Queue gate / fixed

- `tools/run_generation_queue.py`
  - Fix: `scene_background`, `scene_event_cg`, and `scene_prop_cg` are prompt-sensitive workflows. The queue refuses to run them without prompt slots and returns `failed_missing_prompt_slots` instead of letting a runner silently choose content.

### Candidate review / fixed

- `tools/resolve_asset_requests.py`
  - Previous risk: semantically rejected candidates could remain reviewable if their file QA passed.
  - Fix: rejected/semantic-rejected/visual-rejected/failed candidates are excluded from owner review.

### Additional prompt-sensitive helpers / fixed

- `tools/run_audio_bgm_with_sfx_smoke.py`
  - Previous risk: it built an audio prompt directly from the asset description, which was safer than hidden image routing but still left audio outside the explicit prompt-slot contract.
  - Fix: `audio_bgm_with_sfx` now requires an agent-authored prompt-slots JSON with `positive_prompt`; optional `negative_prompt` is recorded and applied. Generation queue treats audio as prompt-sensitive and fail-closes without prompt slots.

- `tools/run_char_base_smoke.py`
  - Previous risk: it was a legacy smoke-test/default character generator with fixed character/outfit placeholder tags such as `school_uniform`.
  - Fix: char_base now requires agent-authored `character_features` and `outfit_detail` prompt slots under `docs/production/prompt_slots/`, validates them against `danbooru_tag.csv`, supports prepare-only metadata, and keeps seed recording for downstream scene_event_cg reuse.

## New contract

For production prompt-sensitive generation, the agent must create a JSON file under:

```text
docs/production/prompt_slots/<asset_id>.json
```

or:

```text
docs/production/prompt_slots/<scene_id>__<asset_id>.json
```

The code may validate tags and apply the README workflow wrapper, but it must not infer creative prompt slots from the scene description.

## Verification performed

- `pytest tests/test_prompt_slots_fail_closed.py tests/test_level4_generation_orchestrator.py tests/test_scene_background_routing.py tests/test_resolve_asset_requests.py -q` → 10 passed
- `pytest -q` → 53 passed
- Real prepare-only prompt-slot check for `bg_bus_interior_dawn` wrote patched workflow and metadata successfully.
- Real current-project generation queue check after fix: requested 0 / generated 0 / failed 0 / skipped 0.
