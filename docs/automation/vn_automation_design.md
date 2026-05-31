# VN Automation Design

## 1. 목표
새 Ren'Py 게임마다 재사용 가능한 supervised VN production automation spine을 제공한다.

## 2. 고정 경로
고정 경로는 코드에 두지 않고 `docs/automation/project_contract.json`과 `--project-root`에서 해석한다.

## 3. 역할 분담
Obsidian은 기획/장면 노트, project docs는 machine-readable sidecar, ComfyUI는 후보 생성, Ren'Py `game/`은 최종 playable artifact를 담당한다.

## 4. 데이터 흐름
scene note -> asset requests -> resolver -> owner review queue -> generation/QA -> approval -> promotion -> Ren'Py verification.

## 7. Workflow routing
`workflow_routes`는 asset type을 workflow id에 매핑한다. Manifest hit를 먼저 재사용하고 없을 때만 generation decision을 만든다.

## 11. QA gates
file QA, visual/audio QA, explicit owner approval, asset reference check, integration gap report, Ren'Py lint를 gate로 사용한다.

## 13. 첫 투입 milestone
새 게임의 첫 milestone은 scene note 1개, required assets 2개, owner queue 생성, static verify 통과다.

## 14. 금지 사항
승인 없는 promotion, blind `.rpy` patch, project root 밖 산출물 기록, 기존 파일 무단 overwrite를 금지한다.
