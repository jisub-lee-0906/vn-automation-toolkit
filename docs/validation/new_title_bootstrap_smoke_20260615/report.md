# New Title Bootstrap Smoke — 2026-06-15

## Command

```bash
python -m vn_automation.cli new-title \
  --title 'Automation Smoke VN' \
  --slug automation_smoke_vn_20260615 \
  --renpy-projects-root E:/workspace/vn-automation-toolkit/docs/validation/new_title_bootstrap_smoke_20260615/renpy-project \
  --obsidian-vault E:/workspace/vn-automation-toolkit/docs/validation/new_title_bootstrap_smoke_20260615/obsidian-vn \
  --workflow-pack-root E:/workspace/comfyui-game-asset-workflows \
  --renpy-sdk-exe C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe \
  --lint-timeout 180
```

## Observed Result

```text
NEW_TITLE_BOOTSTRAP_COMPLETE
title Automation Smoke VN
slug automation_smoke_vn_20260615
skeleton_source copied_sdk_gui_template
validation validate 0
validation roadmap 0
validation scene-state 0
validation obsidian-audit 0
renpy_lint 0
```

Post-command explicit gates also passed:

```text
VALIDATION PASSED
PRODUCTION_COCKPIT_ROADMAP_PASSED
SCENE_REMASTER_STATE_CHECK_PASSED
OBSIDIAN_ACTIVE_STATE_AUDIT_PASSED
```

Runtime junk cleanup after lint:

```text
remaining rpyc/rpyb: 0
```

The generated smoke project itself was removed after recording this report so the repository does not retain copied SDK GUI binary assets.
