# 파일 반영 안전성 | 작은 재현 예제

## 무엇을 확인하나

실제 에셋이나 실행 중인 게임을 변경하지 않고, 기존 테스트가 만든 임시 fixture로 검사·거부·백업 동작을 확인합니다. AI 에이전트가 2026-10-07 실행한 결과는 [검증 기록](verification/2026-10-07/README.md)에 있습니다. 지원자 본인의 직접 재현과는 구분합니다.

## 준비

Python 3.11 이상이 필요합니다. 아래는 PowerShell 예시이며 저장소 루트에서 실행합니다. 별도 가상환경을 만들고, pip의 외부 설치 경로 설정을 비활성화한 현재 프로세스에서 설치합니다. 사용자·시스템 환경변수를 영구 변경하지 않습니다.

```powershell
python -m venv .venv
Remove-Item Env:PIP_PREFIX, Env:PIP_TARGET, Env:PIP_USER -ErrorAction SilentlyContinue
$env:PIP_CONFIG_FILE = 'NUL'
.\.venv\Scripts\python.exe -m pip install -e . pytest==9.1.1 Pillow==12.3.0
.\.venv\Scripts\vn-auto.exe --help
.\.venv\Scripts\vn-auto.exe --version
```

전체 테스트에는 Pillow가 필요합니다. 패키지의 최소 런타임 요구사항과 테스트 의존성은 구분합니다. 확인된 조합은 Windows / Python 3.13.12이며, 위 모든 Python 버전에서의 실행을 보장하지 않습니다.

## 핵심 테스트 5개

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_assurance_completion_hardening.py::test_promote_rejects_unsafe_identity_and_filename_values tests/test_preflight_hardening.py::test_promote_refuses_existing_manifest_asset_id_without_replace tests/test_assurance_completion_hardening.py::test_promote_force_overwrite_creates_backup tests/test_preflight_hardening.py::test_director_new_scene_refuses_to_overwrite_existing_scene_without_force tests/test_preflight_hardening.py::test_promote_refuses_existing_destination_file_without_force
```

| 시나리오 | 기대 결과 |
| --- | --- |
| 경로 이동·잘못된 식별자 | 반영 거부 |
| 기존 manifest의 중복 ID | 반영 거부, 기존 항목 유지 |
| 명시적 강제 덮어쓰기 | 이전 파일 내용의 백업 생성 |
| 이미 존재하는 장면 파일 | 덮어쓰기 거부, 기존 편집 내용 유지 |
| 이미 존재하는 대상 파일 | 덮어쓰기 거부, 기존 바이트 유지 |

실제 결과: **5 passed**, 종료 코드 0. 이 테스트들은 전체 132개에 포함됩니다.

## 전체 회귀 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest
```

이번 결과: **132 passed**, 종료 코드 0. 설치·CLI·테스트 결과는 로컬 실행이며 GitHub Actions 성공 배지가 아닙니다.

## 코드 읽기

- [반영 전 검사·파일 교체](../tools/promote_asset_candidate.py)
- [잘못된 식별자·백업 테스트](../tests/test_assurance_completion_hardening.py)
- [중복·덮어쓰기 거부와 파일 보존 테스트](../tests/test_preflight_hardening.py)

`os.replace` 호출과 백업 생성은 확인하지만, 전원 차단·디스크 손상·모든 동시성 상황의 복구를 검증하지는 않습니다. 이 데모는 실제 사람의 승인이나 생성물 품질을 판정하지 않습니다.
