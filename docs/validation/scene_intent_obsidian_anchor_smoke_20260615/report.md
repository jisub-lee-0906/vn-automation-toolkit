# Scene Intent Obsidian Anchor Smoke — 2026-06-15

## Scope

Verified that `vn-auto scene-intent --update-scene-note` connects an owner scene direction to the title-scoped Obsidian scene note without modifying `game/script.rpy` or asset directories.

## Commands

```bash
python -m vn_automation.cli new-title \
  --title 'Scene Intent Obsidian Anchor Smoke VN' \
  --slug scene_intent_obsidian_anchor_smoke_20260615 \
  --renpy-projects-root E:/workspace/vn-automation-toolkit/docs/validation/scene_intent_obsidian_anchor_smoke_20260615/renpy-project \
  --obsidian-vault E:/workspace/vn-automation-toolkit/docs/validation/scene_intent_obsidian_anchor_smoke_20260615/obsidian-vn \
  --workflow-pack-root E:/workspace/comfyui-game-asset-workflows \
  --renpy-sdk-exe C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe \
  --lint-timeout 180

python -m vn_automation.cli scene-intent \
  --project-root <smoke-project> \
  --scene-id scene_001_opening \
  --intent-id scene001_obsidian_anchor_smoke \
  --owner-text '오프닝은 계약 경고와 선택 압박을 더 선명하게 잡는다.' \
  --objective 'Scene 001 vertical polish 전 자동화 intent를 Obsidian에 남긴다.' \
  --choice '계약 경고를 읽는다' \
  --make-capture-plan \
  --update-scene-note

python -m vn_automation.cli polish-scene \
  --project-root <smoke-project> \
  --scene-id scene_001_opening \
  --patch-id scene001_obsidian_anchor_smoke \
  --before docs/validation/scene001_obsidian_anchor_smoke/script_before.rpy \
  --start-label scene_001_opening \
  --capture-plan docs/validation/scene001_obsidian_anchor_smoke/capture_plan.json \
  --capture-static-only \
  --skip-renpy-lint
```

## Observed Result

```text
NEW_TITLE_BOOTSTRAP_COMPLETE
validation validate 0
validation roadmap 0
validation scene-state 0
validation obsidian-audit 0
renpy_lint 0

SCENE_INTENT_READY
scene_id scene_001_opening
intent_id scene001_obsidian_anchor_smoke
before_script docs/validation/scene001_obsidian_anchor_smoke/script_before.rpy
capture_plan docs/validation/scene001_obsidian_anchor_smoke/capture_plan.json
scene_note <obsidian-root>/Scenes/scene_001_opening.md
next_polish_scene_command printed

scene_note_exists True
intent_anchor_count 1
intent_id_present True
script_unchanged_marker True

POLISH_SCENE_COMPLETE
gate scene-guard 0
gate validate 0
gate obsidian-audit 0
gate renpy-lint 0 skip_renpy_lint
gate validate-scene 0
gate scene-state 0
gate scene-state 0

SCENE_REMASTER_STATE_CHECK_PASSED
latest_patch_id scene001_obsidian_anchor_smoke
asset_policy scene_local_preview_only
permanent_asset_changes false
supplemental_qa_reports [docs/validation/scene001_obsidian_anchor_smoke/scene_validation/report.md]
errors []
remaining rpyc/rpyb: 0
```

The generated smoke project was removed after recording this report so the repository does not retain copied SDK GUI binary assets.
