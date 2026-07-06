# Scene Intent Harness Smoke — 2026-06-15

## Commands

```bash
python -m vn_automation.cli new-title \
  --title 'Scene Intent Harness Smoke VN' \
  --slug scene_intent_harness_smoke_20260615 \
  --renpy-projects-root E:/workspace/vn-automation-toolkit/docs/validation/scene_intent_harness_smoke_20260615/renpy-project \
  --obsidian-vault E:/workspace/vn-automation-toolkit/docs/validation/scene_intent_harness_smoke_20260615/obsidian-vn \
  --workflow-pack-root E:/workspace/comfyui-game-asset-workflows \
  --renpy-sdk-exe C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe \
  --lint-timeout 180

python -m vn_automation.cli scene-intent \
  --project-root <smoke-project> \
  --scene-id scene_001_opening \
  --intent-id scene001_intent_harness_smoke \
  --owner-text '오프닝은 계약 경고와 첫 선택 압박을 중심으로 간다.' \
  --objective '첫 선택 전 세계 규칙과 위험을 명확히 체감시킨다.' \
  --choice '계약 경고를 자세히 본다' \
  --choice '주변 인물을 먼저 의심한다' \
  --make-capture-plan

python -m vn_automation.cli polish-scene \
  --project-root <smoke-project> \
  --scene-id scene_001_opening \
  --patch-id scene001_intent_harness_smoke \
  --before docs/validation/scene001_intent_harness_smoke/script_before.rpy \
  --start-label scene_001_opening \
  --capture-plan docs/validation/scene001_intent_harness_smoke/capture_plan.json \
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
intent_id scene001_intent_harness_smoke
before_script docs/validation/scene001_intent_harness_smoke/script_before.rpy
capture_plan docs/validation/scene001_intent_harness_smoke/capture_plan.json
next_polish_scene_command printed

POLISH_SCENE_COMPLETE
gate scene-guard 0
gate validate 0
gate obsidian-audit 0
gate renpy-lint 0 skip_renpy_lint
gate validate-scene 0
gate scene-state 0
gate scene-state 0

SCENE_REMASTER_STATE_CHECK_PASSED
latest_patch_id scene001_intent_harness_smoke
asset_policy scene_local_preview_only
permanent_asset_changes false
supplemental_qa_reports [docs/validation/scene001_intent_harness_smoke/scene_validation/report.md]
errors []
remaining rpyc/rpyb: 0
```

This verifies the conversation orchestration handoff: owner text → scene intent packet → pre-patch script backup/capture plan → `polish-scene` static validation and scene-state linkage. The generated smoke project was removed after recording this report so the repository does not retain copied SDK GUI binary assets.
