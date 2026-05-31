# VN Automation Level 2.5 Implementation Plan

> **For Hermes:** Execute this plan sequentially with strict verification after each phase. Use TDD for new tool behavior where practical. Do not run full ComfyUI generation unless the step explicitly requires it and the endpoint is verified.

**Goal:** Move the current reality-first production spine from Level 1.7 to Level 2.5 by proving one safe end-to-end promote path and adding the minimum QA and manifest tooling needed before scene-note automation.

**Architecture:** Keep generation, QA, promotion, Ren'Py integration, and verification as separate gates. Reuse existing manifest/candidates first, promote only with explicit approval, and prefer validation/reporting tools before automatic `.rpy` patching.

**Tech Stack:** Python stdlib, Ren'Py SDK, ComfyUI HTTP API, project JSON manifests, Windows-native paths through Git Bash/MSYS.

---

## Current Baseline

Already available:

- `tools/check_renpy_asset_refs.py`
- `tools/backfill_asset_manifest_from_renpy.py`
- `tools/promote_asset_candidate.py`
- `tools/validate_vn_automation_docs.py`
- `tools/verify_vn_automation_runtime.py`
- candidate runners for `scene_background`, `scene_prop_cg`, `char_base`, `scene_event_cg`
- `game/data/asset_manifest.json` with 7 existing first5 assets

Last verified commands:

```bash
python tools/check_renpy_asset_refs.py
python tools/validate_vn_automation_docs.py
python tools/verify_vn_automation_runtime.py
```

Expected baseline:

```text
ALL_RENPY_ASSET_REFS_EXIST
VALIDATION PASSED
VERIFY_PASSED
```

## Scope of the Next Step

This plan intentionally does NOT attempt full scene-note automation yet. The next realistic step is:

```text
QA file check
-> promote one approved candidate end-to-end
-> validate manifest and refs
-> add non-invasive Ren'Py integration report
-> only then implement thin scene-note Required Assets extraction
```

## Success Criteria

The project reaches Level 2.5 when all are true:

1. One generated candidate has been promoted with `--approved` into a production folder such as `game/images/cgs/` or `game/images/backgrounds/`.
2. `game/data/asset_manifest.json` contains the promoted asset with non-unknown `workflow_id`, source metadata, seed/prompt id when available, and a real promoted path.
3. `tools/qa_asset_file.py` can inspect at least PNG files and reject missing/invalid files before promote.
4. `tools/report_renpy_integration_gaps.py` reports whether manifest assets have Ren'Py declarations without modifying `.rpy` files.
5. `python tools/check_renpy_asset_refs.py`, `python tools/validate_vn_automation_docs.py`, and `python tools/verify_vn_automation_runtime.py` pass after the promoted asset is present.
6. A thin scene-note parser can extract explicit `Required Assets` into JSON without attempting full natural-language story understanding.

---

## Phase 0: Freeze Current Baseline

### Task 0.1: Record baseline status

**Objective:** Confirm the current system is green before adding new tools.

**Files:**
- Read: `tools/check_renpy_asset_refs.py`
- Read: `tools/validate_vn_automation_docs.py`
- Read: `tools/verify_vn_automation_runtime.py`

**Command:**

```bash
python tools/check_renpy_asset_refs.py && python tools/validate_vn_automation_docs.py && python tools/verify_vn_automation_runtime.py
```

**Expected:**

```text
ALL_RENPY_ASSET_REFS_EXIST
VALIDATION PASSED
VERIFY_PASSED
```

**Stop if:** any command fails. Fix the existing baseline before implementing anything else.

---

## Phase 1: Add Minimal Asset QA Tool

### Task 1.1: Create `tools/qa_asset_file.py`

**Objective:** Add a lightweight checker that validates candidate or promoted files before they can be trusted.

**Files:**
- Create: `tools/qa_asset_file.py`

**Required CLI:**

```bash
python tools/qa_asset_file.py PATH --asset-type event_cg --json-out docs/automation/tmp_qa.json
```

**Minimum behavior:**

- Verify file exists.
- Verify file size is greater than 0.
- For PNG/JPG/WebP:
  - parse width/height without requiring Pillow if possible.
  - report extension, size bytes, width, height, aspect ratio.
  - for PNG, detect color type and whether alpha is present.
- For audio files:
  - if `ffprobe` is available, report duration and codec.
  - if `ffprobe` is unavailable, warn but do not fail solely because of missing ffprobe.
- Return exit code 0 for valid file, 1 for invalid file.
- Write JSON report when `--json-out` is passed.

**TDD seed tests:**

Create simple test fixture files under `docs/automation/test_fixtures/` or generate them in a temp directory from the test script.

Test cases:

```text
missing file -> exit 1
empty file -> exit 1
valid existing PNG -> exit 0 and JSON includes width/height
PNG alpha detection returns true/false where detectable
```

**Verification command:**

```bash
python tools/qa_asset_file.py game/images/generated/event_cg/seoha_knee_bump.png --asset-type event_cg --json-out docs/automation/qa_reports/seoha_knee_bump_file_qa.json
```

**Expected:**

```text
QA_ASSET_FILE
status pass
```

### Task 1.2: Create QA reports directory convention

**Objective:** Keep automated QA output separate from generation run reports.

**Files:**
- Create dir: `docs/automation/qa_reports/`

**Rule:**

```text
Generated-run visual QA stays under docs/automation/generation_runs/<run_id>/qa_report.md.
Automated file QA goes under docs/automation/qa_reports/<asset_id>_file_qa.json.
```

---

## Phase 2: Harden Promotion Tool with QA Input

### Task 2.1: Add optional QA report gate to `promote_asset_candidate.py`

**Objective:** Make promote safer without making it cumbersome.

**Files:**
- Modify: `tools/promote_asset_candidate.py`

**New CLI option:**

```bash
--qa-report docs/automation/qa_reports/<asset_id>_file_qa.json
```

**Behavior:**

- If `--qa-report` is provided, load it.
- Refuse promote if report status is not `pass`.
- Record QA report path in manifest metadata.
- Keep existing `--approved` requirement mandatory.

**Do not:** require QA report unconditionally yet. That would block quick manual experiments. For production use, use both:

```bash
--approved --qa-report <path>
```

**Verification:**

```bash
python tools/promote_asset_candidate.py docs/automation/generation_runs/scene_event_cg_readme_positive_only_20260530_072325/metadata.json --asset-id dry_run_should_refuse --renpy-name dry_run_should_refuse
```

Expected:

```text
PROMOTE_REFUSED: missing --approved explicit approval flag
```

Then with a deliberately failing QA report, expected:

```text
PROMOTE_REFUSED: QA report status is not pass
```

---

## Phase 3: Run One Real End-to-End Promotion

### Task 3.1: Select a safe candidate

**Objective:** Pick one already generated candidate for a real promotion test without triggering new ComfyUI cost.

**Recommended candidate:**

```text
docs/automation/generation_runs/scene_event_cg_readme_positive_only_20260530_072325/metadata.json
```

Reason:

- Already generated.
- Has metadata.
- Uses known same char_base seed.
- Can be promoted as an alternate event CG without replacing existing `seoha_knee_bump`.

**Suggested asset id:**

```text
event_cg_seoha_auditorium_seed260529200_candidate01
```

**Suggested Ren'Py name:**

```text
event_cg_seoha_auditorium_seed260529200
```

**Suggested destination:**

```text
game/images/cgs/event_cg_seoha_auditorium_seed260529200.png
```

### Task 3.2: Run file QA on selected candidate

**Objective:** Prove the file is structurally valid before promote.

**Command:**

```bash
python tools/qa_asset_file.py docs/automation/generated_candidates/event_cg/scene_event_cg_readme_positive_only_20260530_072325/scene_event_cg_readme_positive_only_20260530_072325_school_uniform_seed260529200_00001_.png --asset-type event_cg --json-out docs/automation/qa_reports/event_cg_seoha_auditorium_seed260529200_candidate01_file_qa.json
```

**Expected:**

```text
QA_ASSET_FILE
status pass
```

### Task 3.3: Promote with explicit approval

**Objective:** Prove the production spine works end-to-end.

**Command:**

```bash
python tools/promote_asset_candidate.py docs/automation/generation_runs/scene_event_cg_readme_positive_only_20260530_072325/metadata.json \
  --asset-id event_cg_seoha_auditorium_seed260529200_candidate01 \
  --renpy-name event_cg_seoha_auditorium_seed260529200 \
  --asset-type event_cg \
  --dest-dir images/cgs \
  --filename event_cg_seoha_auditorium_seed260529200.png \
  --scene-usage first5_control_observer_slice \
  --approved \
  --qa-report docs/automation/qa_reports/event_cg_seoha_auditorium_seed260529200_candidate01_file_qa.json
```

**Expected:**

```text
PROMOTE_ASSET_CANDIDATE
action added
```

**Important:** This does not automatically insert the image into script. It only promotes and tracks it.

### Task 3.4: Verify after promotion

**Objective:** Confirm promotion did not break the project.

**Command:**

```bash
python tools/check_renpy_asset_refs.py && python tools/validate_vn_automation_docs.py && python tools/verify_vn_automation_runtime.py
```

**Expected:**

```text
ALL_RENPY_ASSET_REFS_EXIST
VALIDATION PASSED
VERIFY_PASSED
```

---

## Phase 4: Add Non-Invasive Ren'Py Integration Gap Report

### Task 4.1: Create `tools/report_renpy_integration_gaps.py`

**Objective:** Report which manifest assets are already declared in Ren'Py and which are promoted but unused.

**Files:**
- Create: `tools/report_renpy_integration_gaps.py`

**Behavior:**

- Load `game/data/asset_manifest.json`.
- Scan `.rpy` files for image declarations and asset file references.
- For each manifest asset, report:
  - `asset_id`
  - `renpy_name`
  - `promoted_path`
  - `file_exists`
  - `declared_by_renpy_name`
  - `referenced_by_path`
  - `status`: `integrated`, `file_only_not_declared`, or `missing_file`
- Output human-readable text by default.
- Support `--json-out docs/automation/renpy_integration_report.json`.

**Verification command:**

```bash
python tools/report_renpy_integration_gaps.py --json-out docs/automation/renpy_integration_report.json
```

**Expected after Phase 3:**

```text
existing first5 assets -> integrated
new promoted auditorium asset -> file_only_not_declared
```

This is expected. The point is to know the gap before patching `.rpy`.

---

## Phase 5: Optional Tiny Ren'Py Declaration Patch

### Task 5.1: Add a declaration only if the promoted candidate should be testable in-game

**Objective:** Make the new promoted asset addressable by Ren'Py without changing scene flow.

**Files:**
- Modify: `game/first5_control_observer.rpy`

**Patch pattern:**

Add near existing image declarations:

```renpy
image event_cg_seoha_auditorium_seed260529200 = Transform("images/cgs/event_cg_seoha_auditorium_seed260529200.png", xysize=(1920, 1080))
```

**Verification:**

```bash
python tools/check_renpy_asset_refs.py
"C:/Users/Desktop/Documents/Renpy/renpy-8.5.2-sdk/renpy.exe" "<renpy_project_root>" lint
```

**Expected:**

```text
ALL_RENPY_ASSET_REFS_EXIST
renpy_lint_exit 0
```

**Important:** Do not replace the currently integrated event CG until owner review approves the visual result in context.

---

## Phase 6: Thin Scene Note Parser

### Task 6.1: Create `tools/extract_asset_requests_from_scene_note.py`

**Objective:** Reach practical Level 2 by extracting only explicit Required Assets from a scene note.

**Files:**
- Create: `tools/extract_asset_requests_from_scene_note.py`
- Output dir: `docs/production/asset_requests/`

**Supported input:**

A Markdown scene note containing:

```markdown
## Required Assets
- id: bg_classroom_evening
  type: background
  description: classroom at sunset
  required: true
- id: event_cg_seoha_choice_pause
  type: event_cg
  description: Seoha hesitates before the first choice
  required: true
```

**Output JSON shape:**

```json
{
  "scene_id": "example_scene",
  "source_note": "...",
  "asset_requests": [
    {
      "asset_id": "bg_classroom_evening",
      "asset_type": "background",
      "description": "classroom at sunset",
      "required": true,
      "status": "needs_manifest_lookup"
    }
  ]
}
```

**Non-goals:**

- Do not infer assets from dialogue.
- Do not batch-generate automatically.
- Do not modify Ren'Py.

### Task 6.2: Add a sample scene note fixture

**Files:**
- Create: `docs/automation/test_fixtures/sample_scene_note.md`

**Verification command:**

```bash
python tools/extract_asset_requests_from_scene_note.py docs/automation/test_fixtures/sample_scene_note.md --scene-id sample_scene --out docs/production/asset_requests/sample_scene.asset_requests.json
```

**Expected:**

```text
EXTRACT_ASSET_REQUESTS
count 2
```

---

## Phase 7: Final Verification and Level Reassessment

### Task 7.1: Run all verification commands

**Command:**

```bash
python tools/check_renpy_asset_refs.py && python tools/validate_vn_automation_docs.py && python tools/report_renpy_integration_gaps.py --json-out docs/automation/renpy_integration_report.json && python tools/verify_vn_automation_runtime.py
```

**Expected:**

```text
ALL_RENPY_ASSET_REFS_EXIST
VALIDATION PASSED
VERIFY_PASSED
```

### Task 7.2: Update reality-first status doc

**Files:**
- Modify: `docs/automation/vn_automation_reality_first_plan.md`

**Add status section:**

```text
P0 complete
P1 complete for one promoted candidate
P2 minimal file QA complete
P3 not started
P4 thin Required Assets parser complete
Current level: 2.5
```

---

## Recommended Execution Order

Use this exact order:

```text
0. Baseline verify
1. qa_asset_file.py
2. promote_asset_candidate.py QA-report option
3. promote one already-generated candidate
4. report_renpy_integration_gaps.py
5. optional Ren'Py declaration patch
6. extract_asset_requests_from_scene_note.py
7. final verify
```

## What to Avoid Next

Do not implement these yet:

- full route/episode batch generation
- cron/nightly ComfyUI runs
- automatic dialogue-based CG inference
- automatic `.rpy` flow patching
- char_expression/char_alpha until source image selection and QA are stable

## Why This Is the Right Next Step

This plan raises the automation level without increasing creative risk. It proves that a generated candidate can safely travel through QA, approval, promotion, manifest tracking, and Ren'Py validation. Once this path is proven once, later generation tools and scene-note extraction can reuse the same spine instead of inventing separate flows.
