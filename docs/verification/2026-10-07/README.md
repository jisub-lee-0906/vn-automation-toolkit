# 로컬 재현 점검 | 2026-10-07

## 대상과 실행 주체

- 대상 소스 커밋: `68be44ed8ff9b7e3c4c1be3d5207f44f2fe52ca7`
- 실행 주체: 사용자 요청에 따른 AI 에이전트. 사용자 본인의 직접 수행·독립적 숙련 검증과 구분합니다.
- 환경: Windows, Python 3.13.12, pytest 9.1.1, Pillow 12.3.0, pluggy 1.6.0
- 최종 실행 위치: 별도 복제본 및 전용 가상환경
- GPU·실제 Ren’Py·ComfyUI·Telegram API·운영 데이터: 사용하지 않음

## 결과

| 항목 | 명령 요약 | 결과 |
| --- | --- | --- |
| 설치 | 전용 venv에서 editable 설치 및 테스트 의존성 설치 | 종료 0 |
| CLI 도움말 | vn-auto --help | 종료 0 |
| CLI 버전 | vn-auto --version | 0.1.0, 종료 0 |
| 안전성 선택 테스트 | [5개 node ID](../../operations-walkthrough.md) | 5 passed, 종료 0 |
| 전체 테스트 | python -m pytest | 132 passed, 종료 0 |

선택 테스트는 전체 테스트의 부분집합입니다. 테스트 수를 137개로 합산하지 않습니다.

## 실행 중 발견한 환경 문제

초기 pip 실행은 상속된 `PIP_PREFIX`로 인해 의도한 venv 밖 공유 prefix를 대상으로 했습니다. 따라서 최초 선택 테스트는 `No module named pytest`, 종료 1로 실패했습니다. 해당 프로세스에서 설치 경로 변수를 제거한 뒤 전용 venv에 설치해 위 결과를 얻었습니다. 잘못 등록된 toolkit editable 설치는 공유 prefix에서 제거했습니다. 테스트 통과는 이 초기 설치 실패가 없었다는 의미가 아닙니다.

## 증거 파일

- [선택 테스트 stdout](selected-pytest.stdout.log)
- [전체 테스트 stdout](full-pytest.stdout.log)
- [CLI 버전](vn-auto-version.stdout.log)
- [런타임·의존성 버전](runtime-dependency-versions.log)

공개 로그의 로컬 절대 경로는 `<toolkit-checkout>`으로 치환했습니다. 테스트 결과와 집계는 변경하지 않았습니다.

## 한계

임시 fixture와 모의 실행을 포함한 도구 테스트입니다. 실제 게임 런타임, 외부 서비스, GPU 생성, 생성물 품질, 상용 운영 가용성, 모든 장애의 복구를 보증하지 않습니다. 이번 변경에서는 GitHub Actions를 신설하거나 원격 CI 통과를 주장하지 않습니다.
