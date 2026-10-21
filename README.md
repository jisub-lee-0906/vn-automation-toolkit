# VN Automation Toolkit | 파일 검증·반영 자동화

Ren’Py 제작에서 **후보 파일 검사 → 승인·QA 확인 → 백업·교체 → 상태 추적**을 다루는 Python 도구입니다. 반복 파일 처리의 오류 대응과 검증 근거를 살펴볼 수 있습니다.

[재현 예제](docs/operations-walkthrough.md) · [2026-10-07 검증 기록](docs/verification/2026-10-07/README.md) · [채용용 사례](https://github.com/jisub-lee-0906/engineering-portfolio/blob/main/cases/automation-toolkit.md)

## 프로젝트 개요

잘못된 경로, 중복 ID, 승인·QA 기록 누락, 의도치 않은 덮어쓰기를 파일 반영 전에 검사합니다. 최종 에셋의 채택과 제작 방향은 사용자가 결정하는 **AI 협업 개인 프로젝트**입니다.

| 항목 | 내용 |
| --- | --- |
| 형태 | 로컬 제작 자동화 CLI·재사용 스크립트 |
| 핵심 기술 | Python 3.11+, `vn-auto`, pytest |
| 주요 처리 | 경로·상태 검사, 선택적 백업, 임시 복사와 원자적 파일 교체 |
| 범위 | Ren’Py 제작 지원. 무인 게임 생성기·기업용 자산관리 제품은 아님 |

## 주요 내용

- **반영 전 검사:** 경로 이탈, 중복 ID, 승인 플래그와 QA 기록 확인
- **교체·기록:** 임시 파일 복사 후 `os.replace`, 선택적 백업, manifest·sidecar·lifecycle 갱신
- **제작 흐름:** 장면 노트에서 요청 추출, 기존 후보 재사용 검사, 누락 에셋 queue 구성
- **검토 지원:** director 상태·리뷰 카드·미리보기·통합 누락 보고
- **오류 대응:** 승인 누락·잘못된 입력·덮어쓰기 등 거부 조건을 테스트로 관리

승인 플래그 검사는 실제 사람의 독립적 승인과 구분합니다. QA 기록의 존재만으로 시각·청각 품질을 보장하지 않습니다.

## 구조와 기술

```text
장면 노트 → 필요한 에셋 추출 → 기존 후보 확인 → 누락 에셋 queue
        → QA 기록·사용자 승인 → game/ 반영 → manifest·sidecar 갱신
        → director 화면·Ren’Py 검증·산출물 감사
```

재사용할 툴킷 소스와 게임별 실행 데이터를 분리합니다.

| 위치 | 역할 |
| --- | --- |
| `vn_automation/` | 패키지 진입점·CLI dispatcher |
| `tools/` | 재사용 가능한 제작 스크립트 |
| `tests/` | 임시 프로젝트 기반 테스트·검증 조건 |
| `docs/automation/` | 제품 문서·스키마·템플릿·fixture |
| `pyproject.toml` | 설치 가능한 패키지 메타데이터 |

이 저장소에는 타이틀별 `game/`, `docs/production/`, `docs/automation/project_contract.json`, 생성 후보·실행·QA 보고서(명시적 테스트 fixture 제외), Ren’Py cache/save/log/compiled 파일을 넣지 않습니다. 개별 게임의 제작 문서·manifest·스크린샷·생성 후보·반영 기록은 **실제 Ren’Py 프로젝트 루트**에 보관합니다.

### Windows 콘솔

Director 상태 출력은 CP949 같은 기존 Windows 코드 페이지에서도 읽을 수 있도록 ASCII 표식을 사용합니다. 파일 내용과 승인 동작은 바꾸지 않습니다.

## 실행·사용 방법

저장소 루트에서 설치하고 CLI를 확인합니다. `pytest`는 개발 환경에 별도로 필요합니다.

```powershell
python -m pip install -e .
vn-auto --help
vn-auto --version
python -m pytest -q
```

실제 제작 명령에는 **존재하는 프로젝트·SDK·워크플로우·vault의 절대 경로**를 넣습니다. 프로젝트 계약을 찾지 못하면 툴킷 checkout을 제작 대상으로 자동 선택하지 않고 중단합니다.

<details>
<summary>타이틀 초기화와 경로 확인</summary>

초기화에는 절대 경로를 명시합니다. 타이틀에 `docs/automation/project_contract.json`이 있으면 그 프로젝트 루트에서 실행하고, 계약이 없으면 툴킷 checkout을 자동 선택하지 않고 중단합니다.

```bash
vn-auto init \
  --project-root "/path/to/my_title" \
  --renpy-game-dir "/path/to/my_title/game" \
  --renpy-sdk-exe "/path/to/renpy-sdk/renpy" \
  --workflow-pack-root "/path/to/workflow-pack" \
  --workflow-index "/path/to/workflow-pack/WORKFLOW_INDEX.json" \
  --obsidian-vault "/path/to/obsidian-vault"
```

계속하기 전에 `INIT_VN_AUTOMATION_PROJECT` 배너가 의도한 `project_root`를 출력하는지 확인합니다. `--obsidian-vault`만 주고 `--obsidian-project-root`를 생략하면 `<vault>/<game_slug>/VN`에 타이틀별 기본 경로를 만듭니다.

</details>

<details>
<summary>주요 제작·검증 명령 전체</summary>

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

검증 명령:

```bash
vn-auto validate --project-root "/path/to/my_title" --skip-obsidian
vn-auto check --project-root "/path/to/my_title"
vn-auto gaps --project-root "/path/to/my_title" --json-out "/path/to/my_title/docs/automation/integration_gap_report.json"
vn-auto verify --project-root "/path/to/my_title" --skip-comfyui
vn-auto validate-scene --project-root "/path/to/my_title" --scene-id opening --capture-plan "/path/to/my_title/docs/automation/capture_plans/opening.json" --static-only
vn-auto capture-scene --project-root "/path/to/my_title" --scene-id opening --capture-plan "/path/to/my_title/docs/automation/capture_plans/opening.json" --dry-run
vn-auto audit --project-root "/path/to/my_title" --strict
```

</details>

## 검증과 한계

| 기록 | 확인된 결과 | 확인하지 않은 범위 |
| --- | --- | --- |
| [2026-10-07 로컬 재현](docs/verification/2026-10-07/README.md) | AI 에이전트가 Windows / Python 3.13.12에서 전체 **132개 통과**. 선택 검사 5개는 전체에 포함 | Ren’Py·ComfyUI·GPU·외부 API의 실제 제작 |
| 2026-09-23 감사 | 132개 테스트 통과와 Windows 콘솔 회귀 검사 기록 | 같은 날짜 문서 정리 과정의 재실행을 의미하지 않음 |
| 구현·덮어쓰기 검사 | 원자적 교체 호출과 이전 내용 백업 확인 | 프로세스 중단·전원 차단·디스크 장애 주입 검증 |

이는 날짜별 로컬 검증 기록이며 원격 CI 통과나 현재 환경의 새 실행 결과로 표시하지 않습니다. GitHub Actions 워크플로·실행 기록은 기존 2026-09-23 기록에 없습니다. 깨끗한 새 타이틀의 전체 bootstrap, queue 실행, 승격 에셋과 Ren’Py lint/runtime E2E는 별도 확인이 필요합니다.

<details>
<summary>릴리스 준비 판정 기준</summary>

릴리스 준비 완료로 판단하기 전에 다음을 확인합니다.

1. 툴킷 저장소에 타이틀별 `game/`, `docs/production/`, `project_contract.json`이 없습니다.
2. 문서·스크립트에 현재 타이틀의 고정 경로가 없습니다.
3. 전체 테스트가 통과합니다.
4. editable install이 이 checkout을 가리킵니다.
5. `vn-auto --help`, `vn-auto --version`이 동작합니다.
6. 별도로 준비한 새 타이틀에서 `init -> preflight -> director new-scene -> sync/queue -> validate -> validate-scene -> verify`를 실행하고, sidecar가 해당 타이틀 루트 안에 생성됩니다.
7. 실행 중인 타이틀의 임시 산출물을 정리한 뒤에도 `pytest`, `validate`, `check`, `verify`, strict `audit`가 통과합니다.

제품 흐름과 Telegram 승인 UX는 [제품화 안내](docs/automation/productization_readme.md)를 참고합니다. 위 목록은 앞으로 확인할 판정 기준이며, 모두 새로 실행했다는 결과 보고가 아닙니다.

</details>

## 기여와 관련 문서

이지섭과 AI 도구의 협업 프로젝트입니다. 게임 제작이라는 원래 용도를 유지하며 파일 검증·실패 처리·교체·백업의 구현과 실행 근거를 소개합니다. 기업 운영 경력이나 독립적인 수작업 구현 전체를 주장하지 않습니다.

- [운영 관점의 재현 예제](docs/operations-walkthrough.md)
- [날짜·환경·출력 원문](docs/verification/2026-10-07/README.md)
- [제품화 흐름·Telegram 승인 UX](docs/automation/productization_readme.md)
- [보안 안내](SECURITY.md)
- [IT 운영 포트폴리오](https://github.com/jisub-lee-0906/engineering-portfolio)
