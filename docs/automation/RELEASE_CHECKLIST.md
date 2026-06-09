# Release Checklist

Use this checklist before treating `E:/workspace/vn-automation-toolkit` as a reusable release candidate.

## Scope hygiene

- [ ] `game/` is absent from the toolkit repository.
- [ ] `docs/production/` is absent from the toolkit repository.
- [ ] `docs/automation/project_contract.json` is absent from the toolkit repository.
- [ ] Generated candidates/runs/QA reports are absent except intentional test fixtures.
- [ ] `*.egg-info`, `.pytest_cache`, `__pycache__`, `*.pyc`, Ren'Py logs/cache/saves are absent.
- [ ] Search for active-title paths returns no matches.

## Package checks

```bash
cd E:/workspace/vn-automation-toolkit
python -m pytest -q
python -m pip install -e .
vn-auto --help
vn-auto --version
python - <<'PY'
import pathlib, vn_automation
print(pathlib.Path(vn_automation.__file__).resolve())
PY
```

## Cleanroom smoke

Run a new title outside the active game repo, with absolute paths:

```bash
PROJECT="E:/workspace/renpy-project-cleanroom/<smoke_title>"
SDK="C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe"
WORKFLOWS="E:/workspace/comfyui-game-asset-workflows"
VAULT="E:/workspace/renpy-project-cleanroom/<smoke_title>_vault"

vn-auto init \
  --project-root "$PROJECT" \
  --renpy-game-dir "$PROJECT/game" \
  --renpy-sdk-exe "$SDK" \
  --workflow-pack-root "$WORKFLOWS" \
  --workflow-index "$WORKFLOWS/WORKFLOW_INDEX.json" \
  --obsidian-vault "$VAULT"

vn-auto director new-scene \
  --project-root "$PROJECT" \
  --scene-id opening_smoke \
  --title "Opening Smoke" \
  --summary "Cleanroom release smoke scene." \
  --goal "Prove sidecars are written under the cleanroom title root." \
  --asset "background:bg_opening_smoke|simple no-character VN background" \
  --playable-placeholder

vn-auto sync --project-root "$PROJECT" --vault "$VAULT" --notes-glob "VN/Scenes/*.md"
vn-auto queue --project-root "$PROJECT"
vn-auto preflight --project-root "$PROJECT" --skip-comfyui
vn-auto validate --project-root "$PROJECT" --skip-obsidian
# Optional per-scene gate once a capture plan exists:
# vn-auto validate-scene --project-root "$PROJECT" --scene-id opening_smoke --capture-plan "$PROJECT/docs/automation/capture_plans/opening_smoke.json" --static-only
vn-auto verify --project-root "$PROJECT" --skip-comfyui --skip-renpy-lint
```

Acceptance: all generated sidecars are under `$PROJECT`, Obsidian notes default under `$VAULT/<game_slug>/VN`, and nothing is written under the toolkit source directory or another title.

## Live title regression

Run this against the active title you are using to validate the toolkit, but keep that title outside this toolkit repository:

```bash
LIVE="E:/workspace/renpy-project/<active_title>"
python -m pytest -q
vn-auto preflight --project-root "$LIVE" --skip-comfyui
vn-auto validate --project-root "$LIVE" --skip-obsidian
vn-auto check --project-root "$LIVE"
vn-auto verify --project-root "$LIVE" --skip-comfyui
vn-auto audit --project-root "$LIVE" --strict
```

Clean runtime junk (`game/cache`, `game/saves`, `log.txt`, `traceback.txt`, `*.rpyc`, `*.rpymc`, `.pytest_cache`) and rerun strict audit until it reports no runtime junk.

## Do not claim

- Do not claim whole-game completion from these checks.
- Do not claim unattended game generation.
- Do not publish generated candidates or live-title sidecars as toolkit source.
