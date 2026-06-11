# VN Automation New-Chat Readiness Handoff

Purpose: make VN automation safe to resume from a completely new chat without inheriting stale project assumptions, cross-game asset contamination, or old workflow-pack rules.

## Status

This document is the first file to read when starting a fresh chat for VN automation maintenance or asset-generation QA.

Pair it with:

```text
E:/workspace/vn-automation-toolkit/docs/asset_generation_generic_test_plan.md
E:/workspace/vn-automation-toolkit/docs/asset_generation_qa_execution_tracker.md
```

## Mandatory Skill Load Order for a New Chat

Load only the relevant skills for the task, but for VN automation use this minimum set:

1. `visual-novel-game-development` — Ren'Py project selection, playable verification, integration gates.
2. `advanced-vn-comfyui-asset-pipeline` — visual/audio asset direction, prompt slots, candidate review, approval-gated promotion.
3. `obsidian` — title-scoped RAG retrieval/write-back.
4. `windows-comfyui-platform-ops` only when ComfyUI process/endpoint/model/runtime health matters.
5. `hermes-skill-library-ops` / `hermes-agent-skill-authoring` only when editing skills or memory hygiene.

## Non-Negotiable Fresh-Chat Rules

### 1. Re-discover the active project

Do not assume the active game from memory or a previous chat. Resolve the project from the current request, cwd, or live contracts:

```bash
python - <<'PY'
from pathlib import Path
for p in Path('E:/workspace/renpy-project').glob('*/docs/automation/project_contract.json'):
    print(p)
PY
```

Then read the chosen `project_contract.json` and verify:

- `game_slug`
- `renpy_project_root` / `project_root`
- `renpy_game_dir`
- `renpy_sdk_exe`
- `obsidian_vault`
- `obsidian_project_root`
- `obsidian_scenes_glob`
- `workflow_pack_root`
- `comfyui_endpoint`

If multiple plausible projects remain, list candidates and ask before writing or generating.

### 2. Re-discover workflow-pack state

Do not assume a workflow path or endpoint from memory. Read:

```text
<workflow_pack_root>/WORKFLOW_INDEX.json
<workflow_pack_root>/<workflow_id>/README.md
```

Current expected pack in this environment is usually:

```text
E:/workspace/comfyui-game-asset-workflows
```

Current ComfyUI endpoint in this VN environment is usually:

```text
http://127.0.0.1:8000
```

But a fresh chat must verify the contract/live endpoint before generation.

### 3. Tag validation source

Current primary Danbooru tag validation source is the workflow-pack SQLite taxonomy helper:

```text
E:/workspace/comfyui-game-asset-workflows/danbooru-taxonomy.release.sqlite
E:/workspace/comfyui-game-asset-workflows/scripts/danbooru_tag_search.py
```

Use examples:

```bash
python scripts/danbooru_tag_search.py search "corridor"
python scripts/danbooru_tag_search.py check "solo, upper_body" --mode auto
```

Historical references may mention root `danbooru_tag.csv`. Treat those as old compatibility history unless explicitly testing a legacy fallback path. Do not resurrect mandatory root CSV use.

### 4. Cross-game asset reuse policy

Default policy: fresh generation across projects/games.

- Do not copy production art/audio from a previous title into a new title as shipped assets.
- Players can notice cross-game asset reuse.
- Same-game reuse is correct when story continuity intentionally repeats the same asset: recurring location, recurring prop, established character sprite, or repeated UI identity.
- Previous-title assets may be used as private visual references only when useful; do not import them as production files unless the user explicitly requests it.

### 5. Approval gate

The user performs semantic QA. The agent must not promote candidates automatically.

Allowed before approval:

- generate candidates;
- save metadata;
- run file QA;
- create contact sheets/previews;
- describe intent and candidate paths.

Requires explicit user approval bound to exact candidate + metadata path:

- promotion into `game/images` or `game/audio`;
- manifest entry as approved/promoted;
- permanent Ren'Py scene replacement.

### 6. Lifecycle vocabulary

Use canonical lifecycle fields rather than interpreting mixed legacy status strings directly.

Key stages:

```text
generated_file_pending_qa
file_qa_pass_pending_visual_review
file_qa_warn_pending_visual_review
visual_review_pending
visual_rejected
owner_approved_pending_promotion
promoted_integrated_pending_verification
promoted_integrated_verified
archived_smoke
superseded
```

Normalize manifest state with:

```bash
python -m vn_automation.cli normalize-lifecycle --project-root <project_root> --write
```

### 7. Obsidian/RAG boundary

Before writing, asset generation, or integration:

1. Resolve selected title root from project contract.
2. Search the title-scoped Obsidian root for current/adjacent scenes, characters, canon, timeline, locations, decisions, continuity, and asset decisions.
3. Summarize a working brief.
4. Only then generate/edit/integrate.

Never let shared/legacy Obsidian notes override the selected title contract.

## Current Generic Asset QA Documents

Generic plan:

```text
E:/workspace/vn-automation-toolkit/docs/asset_generation_generic_test_plan.md
```

Execution tracker:

```text
E:/workspace/vn-automation-toolkit/docs/asset_generation_qa_execution_tracker.md
```

The execution tracker is the durable progress ledger. In long chats, update it after each generated candidate batch and user QA decision.

## Skill Hygiene Notes

The active local VN-related skills have been patched so their active bodies say:

- use SQLite taxonomy helper as current tag source;
- treat old CSV references as historical/superseded unless testing fallback;
- avoid cross-game production asset reuse;
- integrate only same-title approved assets or placeholders/review candidates;
- prefer title-scoped project/Obsidian roots.

Historical `references/` files may still contain project-specific examples and old CSV wording. They are evidence, not active rules. Load them only when the filename matches the current issue, and prefer the active `SKILL.md` body and live project contract on conflict.

## Fresh-Chat Start Checklist

- [ ] Load relevant skills.
- [ ] Read this handoff.
- [ ] Discover project contract(s); select one active title.
- [ ] Verify workflow pack and ComfyUI endpoint.
- [ ] Read generic QA plan and tracker if asset-generation QA is the task.
- [ ] Search title-scoped Obsidian notes before any creative generation/integration.
- [ ] Generate fresh assets for new projects/contexts unless same-game reuse is explicitly intended.
- [ ] Record candidate intent, metadata, paths, file QA, and lifecycle.
- [ ] Ask user for semantic QA; do not promote without exact approval.
- [ ] After changes, run project validators and update the tracker/handoff docs if policy changed.
