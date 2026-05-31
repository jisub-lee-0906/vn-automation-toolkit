# VN Automation Product README

This toolkit turns a Ren'Py visual-novel project into a supervised production loop:

```text
Obsidian scene note
-> Required Assets extraction
-> asset request resolver
-> existing manifest reuse first
-> generation queue only for missing assets
-> file/visual/audio QA
-> explicit owner approval
-> promotion into game/
-> Ren'Py asset checks, integration gap report, lint/runtime verification
```

It is not an unattended whole-game generator. The safe product boundary is supervised scene-level production with explicit approval gates.

## 1. Install or run from source

From a source checkout, use the package module directly:

```bash
python -m vn_automation.cli --help
python -m vn_automation.cli --version
```

For editable local installation:

```bash
python -m pip install -e .
vn-auto --help
```

The installed command is only a thin namespace over the proven `tools/*.py` scripts. Direct script execution remains supported for backwards compatibility.

## 2. Bootstrap a new Ren'Py title

Installed command:

```bash
vn-auto init \
  --project-root E:/workspace/renpy-project/my_new_title \
  --renpy-sdk-exe C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe \
  --workflow-pack-root E:/workspace/comfyui-game-asset-workflows \
  --obsidian-vault "C:/Users/Desktop/Documents/Obsidian Vault"
```

Source-tree equivalent:

```bash
python -m vn_automation.cli init --project-root E:/workspace/renpy-project/my_new_title
```

Preview writes without creating files:

```bash
vn-auto init --project-root E:/workspace/renpy-project/my_new_title --dry-run
```

Existing scaffold files are preserved unless `--force` is supplied.

## 3. Project contract

The central config lives at:

```text
docs/automation/project_contract.json
```

Important fields:

```json
{
  "renpy_project_root": "E:/workspace/renpy-project/my_new_title",
  "renpy_game_dir": "E:/workspace/renpy-project/my_new_title/game",
  "manifest_path": "E:/workspace/renpy-project/my_new_title/game/data/asset_manifest.json",
  "renpy_sdk_exe": "C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe",
  "workflow_pack_root": "E:/workspace/comfyui-game-asset-workflows",
  "workflow_index": "E:/workspace/comfyui-game-asset-workflows/WORKFLOW_INDEX.json",
  "obsidian_vault": "C:/Users/Desktop/Documents/Obsidian Vault"
}
```

Tools resolve paths from `--project-root`, `--contract`, or `VN_AUTOMATION_PROJECT_ROOT`. Do not hardcode title paths inside scripts.

## 4. Static verification commands

Installed command namespace:

```bash
vn-auto validate --project-root .
vn-auto check --project-root .
vn-auto gaps --project-root . --json-out docs/automation/integration_gap_report.json
vn-auto audit --project-root . --strict
```

Source-tree equivalent:

```bash
python -m vn_automation.cli validate --project-root .
python -m vn_automation.cli check --project-root .
python -m vn_automation.cli gaps --project-root . --json-out docs/automation/integration_gap_report.json
python -m vn_automation.cli audit --project-root . --strict
```

Direct scripts still work:

```bash
python tools/validate_vn_automation_docs.py --project-root .
python tools/check_renpy_asset_refs.py --project-root .
python tools/report_renpy_integration_gaps.py --project-root . --json-out docs/automation/integration_gap_report.json
python tools/audit_vn_artifacts.py --project-root . --strict
```

Full runtime verification, including ComfyUI endpoint and Ren'Py lint:

```bash
vn-auto verify --project-root .
```

CI/static product verification without live ComfyUI/Ren'Py dependencies:

```bash
vn-auto verify --project-root . --skip-comfyui --skip-renpy-lint
```

## 5. Director UX console

The director-facing UX layer keeps the user in a producer/director role instead of exposing raw JSON, ComfyUI nodes, or manifest maintenance for routine scene work.

Dashboard:

```bash
vn-auto director status --project-root E:/workspace/renpy-project/moonlit_library
```

New scene card using a project-agnostic title such as `Moonlit Library`:

```bash
vn-auto director new-scene \
  --project-root E:/workspace/renpy-project/moonlit_library \
  --scene-id opening_night_library \
  --title "Opening Night Library" \
  --summary "The protagonist wakes after closing time while rain taps on the library windows." \
  --goal "Make the player wonder whether the quiet librarian can be trusted." \
  --choice "Who are you?" \
  --choice "Why do you know my name?" \
  --asset "background:bg_library_rainy_night|rainy night library interior, no characters" \
  --asset "character_base:char_librarian_base|memory-lost librarian, calm, black hair, faint smile" \
  --asset "character_expression:char_librarian_uneasy|same librarian looking uneasy" \
  --asset "sfx:sfx_rain_window|soft rain tapping on windows" \
  --playable-placeholder
```

This writes the scene note in the title's configured Obsidian vault, creates a safe text-only Ren'Py placeholder draft when requested, syncs/resolves Required Assets, refreshes the owner review queue, and writes a concise director card under `docs/production/director_cards/`.

Review candidates and build the static local dashboard:

```bash
vn-auto director review-assets --project-root E:/workspace/renpy-project/moonlit_library
```

This writes:

```text
docs/production/director_cards/asset_review.md
docs/production/director_dashboard.html
```

Register Ren'Py screenshot/playtest evidence so the dashboard has a preview section:

```bash
vn-auto director preview \
  --project-root E:/workspace/renpy-project/moonlit_library \
  --scene-id opening_night_library \
  --screenshot E:/workspace/renpy-project/moonlit_library/docs/production/screenshots/opening_night_library.png \
  --note "Placeholder flow is playable; asset mood still needs approval."
```

Promote an explicitly approved candidate from the review card:

```bash
vn-auto director approve-candidate \
  --project-root E:/workspace/renpy-project/moonlit_library \
  --metadata E:/workspace/renpy-project/moonlit_library/docs/automation/generation_runs/.../metadata.json \
  --asset-id bg_library_rainy_night \
  --asset-type background \
  --renpy-name "bg library_rainy_night" \
  --scene-usage opening_night_library \
  --approved
```

Approval promotion refreshes asset resolutions/owner queue, updates the local dashboard, and runs static verification with live ComfyUI/Ren'Py lint skipped.

Telegram-tokened approval loop for chat-based review:

```bash
vn-auto director telegram-review --project-root E:/workspace/renpy-project/moonlit_library
```

This writes:

```text
docs/production/telegram_approval_registry.json
docs/production/director_cards/telegram_asset_review.md
```

Each pending candidate receives a one-use token and exact approval phrase such as:

```text
승인 VN-1234ABCD90
```

To consume the tokened approval safely:

```bash
vn-auto director telegram-approve \
  --project-root E:/workspace/renpy-project/moonlit_library \
  --token VN-1234ABCD90 \
  --approved-text "승인 VN-1234ABCD90" \
  --message-id 1396 \
  --approved
```

For a smoother Telegram reply UX, bind the token to the actual candidate message_id after sending the native media/photo:

```bash
vn-auto director telegram-bind-message \
  --project-root E:/workspace/renpy-project/moonlit_library \
  --token VN-1234ABCD90 \
  --message-id 2001 \
  --chat-id 8757392807
```

Then a reply to that candidate message can be consumed with plain approval text:

```bash
vn-auto director telegram-approve-message \
  --project-root E:/workspace/renpy-project/moonlit_library \
  --reply-to-message-id 2001 \
  --approved-text "승인" \
  --approval-message-id 2002 \
  --approved
```

Safety behavior:

- unknown tokens are refused;
- non-exact token approval text is refused unless the approval is bound to a Telegram review message and the reply text is a plain approval such as `승인`;
- unbound reply message IDs are refused;
- duplicate pending bindings to the same message ID are refused;
- already-used tokens are refused;
- metadata outside the target project root is refused;
- successful approval promotes the candidate, refreshes queues/dashboard, runs static verify, and marks the token consumed.

## 6. Scene-note production loop

Installed command namespace:

```bash
vn-auto sync --project-root . --vault "C:/Users/Desktop/Documents/Obsidian Vault" --notes-glob "VN/Scenes/*.md"
vn-auto queue --project-root .
vn-auto generate --project-root .
```

Direct script equivalents:

```bash
python tools/sync_obsidian_scene_asset_requests.py --project-root . --vault "C:/Users/Desktop/Documents/Obsidian Vault" --notes-glob "VN/Scenes/*.md"
python tools/build_owner_review_queue.py --project-root .
python tools/run_generation_queue.py --project-root .
```

Only generated items with `decision=generate` are sent to runners. Manifest hits are reused first.

## 7. Promotion gate

Promotion requires explicit approval:

```bash
vn-auto promote path/to/metadata.json \
  --project-root . \
  --asset-id bg_example_room \
  --renpy-name "bg example_room" \
  --asset-type background \
  --approved \
  --qa-report docs/automation/qa_reports/example_file_qa.json
```

Promotion writes:

```text
game/images or game/audio
game/data/asset_manifest.json
docs/production/promotions/*.json
source generation-run metadata.json promotion status
```

## 8. Maturity gates

Current product maturity after this pass:

```text
P1 Configurable single-project toolkit: implemented and tested
P2 New-title bootstrap: implemented and tested at scaffold level
P3 Cross-title smoke verification: static CLI/product tests, fresh-game bootstrap/sync/queue/verify lifecycle, project-agnostic director UX console tests, candidate review dashboard, screenshot preview registration, approval/promotion UX tests, artifact audit gate, tokened Telegram approval loop tests, Telegram message_id-bound plain reply approval tests, and a real second-title runtime smoke with ComfyUI generation -> Telegram media send -> message_id binding -> plain `승인` reply approval -> promotion -> Ren'Py integration -> runtime screenshot -> full ComfyUI/Ren'Py verify have passed.
P4 Installable command namespace: implemented as thin `vn-auto` wrapper with editable package metadata
P5 Full product docs: packaging/CLI/director UX docs added; external distribution polish still pending
```

## 9. Preflight quickstart before real production validation

Before starting a real title/scene run, checkpoint the current tree and run the safety gates:

```bash
git status --short
python -m pytest tests/test_preflight_hardening.py -q
python -m pytest tests/test_director_remaining_ux.py tests/test_director_ux_console.py -q
vn-auto validate --project-root .
vn-auto audit --project-root . --strict
vn-auto verify --project-root . --skip-comfyui --skip-renpy-lint
```

Recommended manual checks:

```text
[ ] Working tree checkpoint/backup exists before real promotions.
[ ] Candidate files live under docs/automation/generated_candidates or another traceable staging area.
[ ] Promotion metadata lives under the same project root as the target game.
[ ] game/images and game/audio contain approved assets only.
[ ] owner_review_queue no longer lists already-promoted manifest hits.
[ ] director_dashboard.html points at the current project, not a previous title.
```

## 10. Safety rules

- Generate once, reuse many.
- Never promote without owner approval.
- Never patch `.rpy` blindly before asset refs and integration gaps are understood.
- Treat generated candidates as untrusted until file QA and visual/audio review pass.
- Keep project-specific runs, QA reports, manifests, and promotions under that title's project root.
- `director new-scene` refuses to overwrite an existing scene note or placeholder draft unless `--force` is supplied.
- `promote` refuses to overwrite an existing promoted file unless `--force-overwrite` is supplied.
- `promote` refuses to replace an existing manifest `asset_id` unless `--replace-existing` is supplied.
- `director approve-candidate` refuses generation metadata outside the target project root.
