# Polish Scene Harness Smoke — 2026-06-15

## Commands

```bash
python -m vn_automation.cli new-title \
  --title 'Polish Harness Smoke VN' \
  --slug polish_harness_smoke_20260615 \
  --renpy-projects-root E:/workspace/vn-automation-toolkit/docs/validation/polish_scene_harness_smoke_20260615/renpy-project \
  --obsidian-vault E:/workspace/vn-automation-toolkit/docs/validation/polish_scene_harness_smoke_20260615/obsidian-vn \
  --workflow-pack-root E:/workspace/comfyui-game-asset-workflows \
  --renpy-sdk-exe C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe \
  --lint-timeout 180

python -m vn_automation.cli polish-scene \
  --project-root <smoke-project> \
  --scene-id scene_001_opening \
  --patch-id scene001_polish_harness_smoke \
  --before docs/validation/scene001_polish_harness_smoke/script_before.rpy \
  --start-label scene_001_opening \
  --require-menu-choice '첫 장면의 방향을 정한다' \
  --changed-file game/script.rpy \
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

POLISH_SCENE_COMPLETE
scene_id scene_001_opening
patch_id scene001_polish_harness_smoke
gate scene-guard 0
gate validate 0
gate obsidian-audit 0
gate renpy-lint 0 skip_renpy_lint
gate scene-state 0
gate scene-state 0

SCENE_REMASTER_STATE_CHECK_PASSED
latest_patch_id scene001_polish_harness_smoke
asset_policy scene_local_preview_only
permanent_asset_changes false
errors []

remaining rpyc/rpyb: 0
```

The generated smoke project was removed after recording this report so the repository does not retain copied SDK GUI binary assets.
