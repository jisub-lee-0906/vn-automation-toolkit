# VN Automation Toolkit

## 한국어 요약 | 파일 반영 전 검증과 안전한 교체

Ren’Py 비주얼 노벨 제작에서 후보 파일의 검사·반영·상태 추적을 자동화하는 **AI 협업 개인 프로젝트**입니다. 기업용 자산관리 솔루션이나 상용 운영 경력으로 소개하지 않습니다.

- **반영 전 검사:** 경로 이탈, 중복 ID, 승인 플래그 및 QA 기록 확인
- **교체·기록:** 임시 파일 복사 후 원자적 교체, 선택적 백업과 상태 기록
- **오류 대응:** 잘못된 입력·의도치 않은 덮어쓰기를 거부하는 테스트
- **재현 결과:** 2026-10-07 AI 에이전트가 Windows / Python 3.13.12에서 선택 테스트 5개와 전체 테스트 132개 통과를 확인했습니다. 선택 테스트는 전체 모음의 일부이며 합산하지 않습니다.

[작은 재현 예제와 명령](docs/operations-walkthrough.md) · [환경·커밋·출력 기록](docs/verification/2026-10-07/README.md) · [채용용 사례](https://github.com/jisub-lee-0906/engineering-portfolio/blob/main/cases/automation-toolkit.md)

원자적 교체 호출은 구현에서 확인했고, 강제 덮어쓰기 테스트는 이전 내용의 백업을 확인합니다. 프로세스 중단·디스크 장애까지 원자성을 검증했다는 뜻은 아닙니다. 승인 플래그 검사는 실제 사람의 독립적 승인과 구분합니다. Ren’Py·ComfyUI·GPU·외부 API의 실제 실행은 이번 범위가 아닙니다.

---


Supervised production automation for Ren'Py visual novels.

This toolkit is **not** a fully unattended game generator. It is a human-directed production loop that automates repetitive tracking, validation, review-card generation, candidate promotion, and verification while keeping story direction and final asset approval under human control.

## Historical public-readiness review (2026-09-23)

- **This environment:** documentation and command/configuration review only. No title project, Ren'Py runtime, ComfyUI backend, model, GPU, external API, or database was run.
- **Earlier records:** the 2026-09-23 repository audit recorded 132 passing tests for this toolkit, including Windows console encoding regression coverage. Those tests were not rerun during this documentation-only update and do not establish a Ren'Py runtime result.
- **Not verified:** cleanroom bootstrap, generation queue execution, promoted assets, and Ren'Py lint/runtime/end-to-end behavior.

## What it does

```text
Obsidian scene note
-> Required Assets extraction
-> manifest/candidate reuse check
-> generation queue for missing assets
-> file/visual/audio QA records
-> explicit owner approval
-> promotion into Ren'Py game/
-> manifest + sidecar refresh
-> director dashboard / preview cards
-> Ren'Py lint, runtime verify, artifact audit
```

## Repository boundaries

This repository should contain reusable toolkit source only:

- `vn_automation/` — package entry point and CLI dispatcher
- `tools/` — reusable production scripts
- `tests/` — temp-project tests and safety gates
- `docs/automation/` — product docs, schemas, templates, fixtures
- `pyproject.toml` — installable package metadata

It should **not** contain title-specific runtime state:

- `game/`
- `docs/production/`
- `docs/automation/project_contract.json`
- generated candidates/runs/QA reports except deliberate test fixtures
- Ren'Py cache/saves/logs/compiled files

Individual games keep their own `game/`, production docs, manifests, screenshots, generated candidates, and promotion records under the actual Ren'Py project root.

## Install from source

From the repository root in any normal clone:

```bash
python -m pip install -e .
vn-auto --help
vn-auto --version
```

`pyproject.toml` defines the `vn-auto` entry point. The checkout-specific paths shown in older examples below are replaced with placeholders; supply paths that exist on your machine. The 2026-09-23 review did not rerun tests. See the dated 2026-10-07 verification record above for the later agent-executed local run.

## Run tests

With `pytest` installed in the development environment, run `python -m pytest -q` from the repository root. This is a test command, not a claim of a fresh test run.

## Bootstrap a title

Use explicit absolute paths for bootstrap. After a title has `docs/automation/project_contract.json`, project tools may run from that project root, but otherwise fail closed instead of silently selecting the toolkit checkout.

```bash
vn-auto init \
  --project-root "/path/to/my_title" \
  --renpy-game-dir "/path/to/my_title/game" \
  --renpy-sdk-exe "/path/to/renpy-sdk/renpy" \
  --workflow-pack-root "/path/to/workflow-pack" \
  --workflow-index "/path/to/workflow-pack/WORKFLOW_INDEX.json" \
  --obsidian-vault "/path/to/obsidian-vault"
```

Confirm the `INIT_VN_AUTOMATION_PROJECT` banner prints the intended `project_root` before continuing. When `--obsidian-vault` is supplied without `--obsidian-project-root`, init now creates a title-scoped default at `<vault>/<game_slug>/VN`.

## Common commands

```bash
vn-auto preflight --project-root "/path/to/my_title" --skip-comfyui
vn-auto director status --project-root "/path/to/my_title"
vn-auto director new-scene --project-root "/path/to/my_title" --scene-id opening --title "Opening" --summary "..." --goal "..." --asset "background:bg_opening|description" --playable-placeholder
vn-auto sync --project-root "/path/to/my_title" --vault "/path/to/obsidian-vault" --notes-glob "VN/Scenes/*.md"
vn-auto queue --project-root "/path/to/my_title"
vn-auto director review-assets --project-root "/path/to/my_title"
vn-auto director preview --project-root "/path/to/my_title" --scene-id opening --screenshot "/path/to/my_title/docs/production/screenshots/opening.png" --note "Runtime preview."
vn-auto director approve-candidate --project-root "/path/to/my_title" --metadata ".../metadata.json" --asset-id bg_opening --asset-type background --renpy-name "bg opening" --scene-usage opening --approved
```

Verification gates:

```bash
vn-auto validate --project-root "/path/to/my_title" --skip-obsidian
vn-auto check --project-root "/path/to/my_title"
vn-auto gaps --project-root "/path/to/my_title" --json-out "/path/to/my_title/docs/automation/integration_gap_report.json"
vn-auto verify --project-root "/path/to/my_title" --skip-comfyui
vn-auto validate-scene --project-root "/path/to/my_title" --scene-id opening --capture-plan "/path/to/my_title/docs/automation/capture_plans/opening.json" --static-only
vn-auto capture-scene --project-root "/path/to/my_title" --scene-id opening --capture-plan "/path/to/my_title/docs/automation/capture_plans/opening.json" --dry-run
vn-auto audit --project-root "/path/to/my_title" --strict
```

## Release-ready acceptance

Before calling a toolkit checkout release-ready:

1. Toolkit repo has no title-specific `game/`, `docs/production/`, or `project_contract.json`.
2. No docs/scripts hardcode an active title path.
3. Full test suite passes.
4. Editable install points to this checkout.
5. `vn-auto --help` and `vn-auto --version` work.
6. A cleanroom title can run `init -> preflight -> director new-scene -> sync/queue -> validate -> validate-scene -> verify` with sidecars under the cleanroom title root.
7. The live title still passes `pytest`, `validate`, `check`, `verify`, and strict `audit` after runtime junk cleanup.

See `docs/automation/productization_readme.md` for the extended product workflow and Telegram approval UX.

## Windows console compatibility

Director console status output uses ASCII markers so the CLI also works in legacy Windows code pages such as CP949. This affects display only; project files and approval behavior are unchanged.

## Automated verification (2026-09-23)

No GitHub Actions workflows or runs are configured/recorded. The local test/build records above are not a remote CI pass.
