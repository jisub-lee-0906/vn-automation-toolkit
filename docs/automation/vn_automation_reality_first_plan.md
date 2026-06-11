# VN 자동화 현실형 재설계 v2

작성일: 2026-05-30
상태: 운영 기준 초안
목표: 생성 자동화보다 production 연결을 먼저 안정화해서, 비용/시간/실패율을 줄이고 실제 Ren'Py 플레이어블 산출물까지 이어지는 루프를 만든다.
범위: `E:/workspace/renpy-project`는 workspace container이고, 이 문서는 현재 Ren'Py project root / git repo인 `<renpy_project_root>`의 project-scoped automation spine이다. workspace-wide 공통화가 필요하면 이 구조를 각 title 프로젝트에 복제하거나 별도 상위 automation template으로 승격한다.

## 1. 핵심 판단

기존 설계는 최종 형태로는 맞지만, 지금 바로 Level 2~5 전체를 한 번에 구현하면 실패 지점이 너무 많다.

현실적인 병목은 ComfyUI 생성 능력이 아니라 다음 3개다.

1. 이미 게임에서 쓰는 asset을 기계가 모른다.
2. candidate와 production asset 사이의 promote 기준이 없다.
3. Ren'Py 참조와 manifest가 자동으로 검증되지 않는다.

따라서 재설계의 첫 목표는 "scene note 완전 자동화"가 아니라 "작은 변경도 항상 추적/검증/promotion 가능한 production spine"을 만드는 것이다.

## 2. 최적화 원칙

### 2.1 Human-in-the-loop 유지

완전 자동 승인은 금지한다. Hermes는 후보 생성/검증/정리를 자동화하고, 최종 승인 여부는 사용자 또는 명시된 approval flag가 결정한다.

### 2.2 Manifest first

모든 production asset은 `game/data/asset_manifest.json`에 등록한다. Ren'Py가 파일을 직접 참조하고 있어도 manifest에 없으면 자동화 관점에서는 추적 불능으로 본다.

### 2.3 Fresh per project, reuse within story

Cross-title asset reuse is avoided by default because players can recognize recycled art/audio across games. Search the selected title's own manifest and existing candidates only when the same game/story intentionally repeats an established location, prop, character sprite, or UI identity. For a new project or unrelated story context, generate fresh candidates.

### 2.4 Canonical workflow 불변

`E:/workspace/comfyui-game-asset-workflows`의 canonical workflow JSON은 수정하지 않는다. 실행마다 runtime copy만 만든다.

### 2.5 자동 patch보다 자동 검증 우선

Ren'Py `.rpy` 자동 수정은 위험하다. 먼저 참조 검증기와 manifest 검증기를 만들고, patch는 작은 단위로만 수행한다.

## 3. 새 운영 아키텍처

```text
1. Discover
   - Ren'Py image/audio refs scan
   - manifest scan
   - docs/assets sidecar scan

2. Decide
   - same-title established asset이 story상 반복되어야 하면 재사용
   - 다른 게임/다른 프로젝트/무관한 story context이면 fresh candidate 생성
   - 없으면 asset request 생성
   - workflow route 결정

3. Generate candidate
   - ComfyUI runtime payload only
   - output은 docs/automation/generated_candidates 아래 저장
   - metadata/qa_report 기록

4. QA gate
   - 파일 존재, 크기, alpha/audio stream 등 자동 검사
   - 시각/청각 판단은 사용자 승인 필요

5. Promote
   - 승인된 candidate만 game/images 또는 game/audio로 복사
   - manifest 업데이트
   - promotion log 기록

6. Integrate safely
   - 먼저 check_renpy_asset_refs.py로 참조 검증
   - 필요한 image declaration만 작은 patch로 추가
   - Ren'Py lint 실행
```

## 4. 우선순위 재설계

### P0: 현재 프로젝트를 추적 가능하게 만들기

목표: 이미 game에서 쓰는 asset을 manifest에 backfill하고, Ren'Py 참조 누락을 검출한다.

구현 대상:

- `tools/backfill_asset_manifest_from_renpy.py`
- `tools/check_renpy_asset_refs.py`
- `game/data/asset_manifest.json` backfill

완료 기준:

- manifest assets가 0개가 아니다.
- Ren'Py에서 참조하는 PNG가 모두 존재한다.
- `python tools/validate_vn_automation_docs.py` 통과
- Ren'Py lint 통과

### P1: Promotion spine 만들기

목표: 생성 후보를 production asset으로 승격하는 반복 작업을 표준화한다.

구현 대상:

- `tools/promote_asset_candidate.py`
- `docs/production/promotions/`
- `docs/automation/generated_candidates` metadata 기반 manifest append/update

완료 기준:

- 승인 flag 없는 candidate는 promote 거부
- promoted path가 project root 밖이면 거부
- manifest 중복 asset_id 방지
- promote 후 check/lint 통과

### P2: QA 자동화 최소 세트

목표: 사람이 봐야 하는 영역과 기계가 확인할 영역을 분리한다.

구현 대상:

- `tools/qa_asset_file.py`
- PNG: 존재/확장자/파일크기/dimensions/alpha 여부
- audio: ffprobe 가능 시 duration/codec 확인

완료 기준:

- qa_report skeleton 자동 생성
- 오류 후보는 promote 전에 차단

### P3: Character pipeline 보강

목표: 캐릭터 pipeline을 `char_base -> char_expression -> char_alpha`로 정리한다.

구현 대상:

- `tools/run_char_expression_smoke.py`
- `tools/run_char_alpha_smoke.py`
- `docs/assets/characters/*.asset.json` lookup

운영 규칙:

- scene_event_cg는 승인된 char_base seed를 재사용한다.
- char_expression/char_alpha는 source image가 명확하지 않으면 실행하지 않는다.

### P4: Scene note parser는 나중에 얇게 구현

목표: 자유로운 Obsidian 문서 전체를 이해하려 하지 않고, 템플릿 섹션의 명시적 `Required Assets`만 추출한다.

구현 대상:

- `tools/extract_asset_requests_from_scene_note.py`

비범위:

- dialogue 의미 분석으로 자동 CG 결정
- route 전체 batch 자동 생성
- cron 야간 생성

## 5. 효율성 극대화 규칙

1. 먼저 manifest에서 asset 재사용 가능 여부를 확인한다.
2. 같은 scene/event의 candidate가 이미 있으면 새 생성 전 QA/승인만 다시 한다.
3. ComfyUI full run 전에 `/object_info`와 workflow dry-run을 수행한다.
4. event CG는 가능한 한 승인된 char_base seed를 재사용한다.
5. audio는 후순위로 둔다. 시각 vertical slice가 안정화된 뒤 붙인다.
6. 자동 생성 script는 하드코딩을 줄이고 `project_contract.json`을 우선 읽는다.
7. 실패 시 canonical workflow를 고치지 말고 runtime payload와 metadata를 남긴다.

## 6. 중단 기준

다음 상황에서는 자동화를 멈추고 사용자 승인 또는 수동 검토로 전환한다.

- 후보가 character identity를 크게 벗어남
- event CG에 손/얼굴/시선 오류가 명확함
- 파일 path가 project root 밖으로 나감
- manifest와 실제 파일이 충돌함
- Ren'Py lint가 실패함
- workflow가 canonical JSON 변경을 요구함

## 7. 이번 단계의 구체 작업

1. 기존 integrated first5 asset을 manifest에 backfill한다.
2. Ren'Py image reference checker를 추가한다.
3. validation script가 manifest path 존재와 중복 asset_id를 검사하게 강화한다.
4. 전체 verifier를 실행해 실제 프로젝트 상태를 확인한다.

이후에 `promote_asset_candidate.py`를 구현하면 현재 생성 후보 자동화가 실제 production loop와 연결된다.

## 8. 2026-05-30 Level 2.5 진행 상태

현재 상태:

```text
P0 complete: 기존 first5 asset manifest backfill + Ren'Py 참조 검증 완료
P1 complete for one promoted candidate: scene_event_cg 후보 1개를 --approved + QA report로 promote 완료
P2 minimal file QA complete: tools/qa_asset_file.py가 PNG 구조/크기/alpha/JSON report 검증 수행
P3 not started: char_expression / char_alpha production chain은 아직 후순위
P4 thin Required Assets parser complete: tools/extract_asset_requests_from_scene_note.py가 명시적 Required Assets 섹션을 JSON으로 추출
Current practical level: 2.5
```

추가된 production spine 도구:

```text
tools/qa_asset_file.py
tools/report_renpy_integration_gaps.py
tools/extract_asset_requests_from_scene_note.py
```

실제 promote 검증 완료 asset:

```text
asset_id: event_cg_seoha_auditorium_seed260529200_candidate01
promoted_path: game/images/cgs/event_cg_seoha_auditorium_seed260529200.png
source_run: scene_event_cg_readme_positive_only_20260530_072325
seed: 260529200
```

주의:

```text
promoted asset은 manifest에 등록되어 있고 파일도 존재하지만, 현재 Ren'Py scene flow에는 자동 삽입하지 않았다.
report_renpy_integration_gaps.py 기준으로 이 asset은 file_only_not_declared 상태가 정상이다.
시각 owner review 후 필요한 경우 image declaration만 작게 추가한다.
```

## 9. 2026-05-30 Level 3 보완: Asset request resolver

부족했던 연결부인 `asset_requests.json -> reuse/review/generate decision` 단계를 추가했다.

추가된 도구:

```text
tools/resolve_asset_requests.py
```

역할:

```text
1. extract_asset_requests_from_scene_note.py가 만든 asset_requests.json을 읽는다.
2. game/data/asset_manifest.json에서 정확히 같은 asset_id 또는 renpy_name을 검색한다.
3. manifest hit가 있고 production file이 존재하면 reuse_manifest로 결정한다.
4. manifest hit가 있지만 파일이 없으면 blocked_manifest_missing_file로 차단한다.
5. manifest에 없으면 docs/automation/generation_runs/**/metadata.json과 candidate file을 검색한다.
6. type-compatible candidate가 있으면 review_existing_candidate로 owner review queue에 올린다.
7. candidate도 없으면 project_contract.json의 workflow_routes로 generate 결정을 낸다.
```

실제 sample_scene 보완 실행 결과:

```text
RESOLVE_ASSET_REQUESTS
scene_id sample_scene
count 2
review_existing_candidate 2
asset bg_classroom_evening review_existing_candidate scene_background
asset event_cg_seoha_choice_pause review_existing_candidate scene_event_cg
```

생성된 산출물:

```text
docs/production/asset_requests/sample_scene.resolved_asset_requests.json
```

테스트 추가:

```text
tests/test_resolve_asset_requests.py
```

검증 기준:

```text
reuse_manifest: manifest asset_id가 있고 promoted file이 존재할 때
blocked_manifest_missing_file: manifest에는 있으나 promoted file이 없을 때
review_existing_candidate: manifest에는 없지만 type-compatible candidate가 있을 때
generate: manifest/candidate가 없고 workflow route가 있을 때
manual_route_required: workflow route도 없을 때
```

이 보완으로 scene note parser 출력이 실제 production decision으로 이어지기 시작했으며, practical level은 2.5에서 3.0 초입으로 올라갔다. 단, 아직 자동 생성 실행/자동 promote/자동 .rpy patch는 하지 않는다. owner review와 명시적 approval gate는 유지한다.

## 10. 2026-05-30 Level 3.5 진행 상태: 실제 Obsidian note batch + owner review queue

추가된 도구:

```text
tools/sync_obsidian_scene_asset_requests.py
tools/build_owner_review_queue.py
```

보강된 도구:

```text
tools/extract_asset_requests_from_scene_note.py
```

역할:

```text
1. title-scoped Obsidian project root의 Scenes/*.md scene note를 스캔한다.
2. frontmatter scene_id가 있으면 우선 사용하고, 없으면 파일명 slug를 scene_id로 쓴다.
3. Required Assets 섹션에서 기존 key/value 형식과 Obsidian checklist shorthand를 모두 파싱한다.
   - [ ] background: bg_classroom_evening | description
   - [ ] event_cg: event_cg_seoha_choice_pause | description
4. scene별 asset_requests.json을 docs/production/asset_requests/에 생성한다.
5. 같은 scene에 대해 resolve_asset_requests.py를 즉시 실행해 reuse/review/generate decision을 만든다.
6. resolved_asset_requests.json들을 모아 owner review queue Markdown/JSON을 만든다.
7. owner review queue는 project docs와 title-scoped Obsidian Automation note 양쪽에 생성 가능하다.
```

현재 권장 Obsidian smoke note 위치:

```text
E:/workspace/obsidian-vn/<game_slug>/VN/Scenes/<scene_id>.md
```

기존 공용 vault의 `VN/Scenes/*.md` 예시는 legacy smoke 기록이며, 새 게임 기본값으로 사용하지 않는다.

실제 batch 실행 결과:

```text
SYNC_OBSIDIAN_SCENE_ASSET_REQUESTS
processed 1
skipped 0
scene seoha_choice_pause {'review_existing_candidate': 2, 'generate': 1}
```

생성된 산출물:

```text
docs/automation/obsidian_scene_asset_request_batch.json
docs/production/asset_requests/seoha_choice_pause.asset_requests.json
docs/production/asset_requests/seoha_choice_pause.resolved_asset_requests.json
docs/production/owner_review_queue.md
docs/production/owner_review_queue.json
E:/workspace/obsidian-vn/<game_slug>/VN/Automation/Owner_Review_Queue.md
```

현재 `seoha_choice_pause` decision:

```text
bg_classroom_evening -> review_existing_candidate -> scene_background
event_cg_seoha_choice_pause -> review_existing_candidate -> scene_event_cg
sfx_door_knock_soft -> generate -> audio_bgm_with_sfx
```

Practical level은 3.0 초입에서 3.5에 도달했다. 이제 “작가가 Obsidian에 scene note를 쓰면 Hermes가 필요한 asset 후보/부족분을 정리해서 owner review queue로 보여주는 수준”이다. 아직 자동 생성 실행/자동 promote/자동 .rpy patch는 하지 않는다. 다음 Level 4는 resolved queue의 `generate` 항목을 workflow runner로 넘기는 generation orchestrator다.

## 11. 2026-05-30 Level 4 진행 상태: generate queue -> ComfyUI runner -> QA -> review queue refresh

추가된 도구:

```text
tools/run_generation_queue.py
tools/run_audio_bgm_with_sfx_smoke.py
```

테스트:

```text
tests/test_level4_generation_orchestrator.py
```

역할:

```text
1. resolved_asset_requests.json에서 decision=generate 항목만 수집한다.
2. recommended_workflow_id별 runner를 선택한다.
3. runner를 asset_id / scene_id / description과 함께 실행한다.
4. runner metadata.json에서 candidate_copies를 읽는다.
5. qa_asset_file.py 로 candidate 파일 QA report를 생성한다.
6. metadata qa_status를 qa_pass_candidate_not_promoted 또는 qa_warn_candidate_not_promoted로 갱신한다.
7. Obsidian scene sync + owner review queue를 다시 빌드해 generate 항목을 review_existing_candidate로 전환한다.
```

실제 실행한 Level 4 item:

```text
scene_id: seoha_choice_pause
asset_id: sfx_door_knock_soft
workflow_id: audio_bgm_with_sfx
run_id: audio_bgm_with_sfx_sfx_door_knock_soft_20260530_221446
endpoint: http://127.0.0.1:8000
prompt_id: 1a7ca953-acd1-45bf-9eb0-df75b4046597
```

생성된 candidate:

```text
docs/automation/generated_candidates/audio/audio_bgm_with_sfx_sfx_door_knock_soft_20260530_221446/audio_bgm_with_sfx_sfx_door_knock_soft_20260530_221446_sfx_door_knock_soft_00001_.flac
```

QA 결과:

```text
status: pass
extension: .flac
codec: flac
duration_seconds: 8.010884
qa_report: docs/automation/qa_reports/audio_bgm_with_sfx_sfx_door_knock_soft_20260530_221446_1_file_qa.json
```

Level 4 실행 후 `seoha_choice_pause` decision:

```text
bg_classroom_evening -> review_existing_candidate -> scene_background
event_cg_seoha_choice_pause -> review_existing_candidate -> scene_event_cg
sfx_door_knock_soft -> review_existing_candidate -> audio_bgm_with_sfx
```

Owner review queue refresh 결과:

```text
review_items 5
generation_items 0
blocked_items 0
```

Practical level은 4.0에 도달했다. 이제 “Obsidian scene note의 부족 asset 중 generate 항목을 실제 ComfyUI runner로 실행하고, candidate/QA/metadata를 남긴 뒤 owner review queue로 되돌리는 수준”이다. 여전히 promote와 Ren'Py integration은 명시 승인 후 다음 gate에서만 수행한다.

## 12. 2026-05-30 Level 5 최종 마무리: approved promote -> manifest reuse -> Ren'Py integration

추가/보강된 부분:

```text
tests/test_level5_renpy_audio_integration.py
tools/check_renpy_asset_refs.py: image declarations뿐 아니라 play/queue/voice audio refs도 검증
tools/report_renpy_integration_gaps.py: manifest asset이 image declaration 또는 audio path ref로 통합됐는지 보고
```

실제 promote된 `seoha_choice_pause` production assets:

```text
bg_classroom_evening -> game/images/backgrounds/bg_classroom_evening.png
event_cg_seoha_choice_pause -> game/images/cgs/event_cg_seoha_choice_pause.png
sfx_door_knock_soft -> game/audio/sfx/sfx_door_knock_soft.flac
```

Ren'Py integration:

```text
game/first5_control_observer.rpy
- image bg classroom_evening declaration 추가
- image event_cg_seoha_choice_pause declaration 추가
- after_greeting_choice 구간을 bg classroom_evening으로 전환
- 선택지 직전 beat에 play sound "audio/sfx/sfx_door_knock_soft.flac" 추가
- 선택지 직전 event CG beat에 scene event_cg_seoha_choice_pause 추가 후 bg classroom_evening으로 복귀
```

Level 5 실행 후 `seoha_choice_pause` decision:

```text
bg_classroom_evening -> reuse_manifest
event_cg_seoha_choice_pause -> reuse_manifest
sfx_door_knock_soft -> reuse_manifest
```

검증 결과:

```text
pytest: 18 passed
Ren'Py asset refs: ALL_RENPY_ASSET_REFS_EXIST
Ren'Py integration report: integrated 10 / file_only_not_declared 1 / missing_file 0
validation: VALIDATION PASSED
runtime verify: VERIFY_PASSED
Ren'Py lint: exit 0
```

남은 `file_only_not_declared 1`은 이전에 promoted 되었지만 현재 scene flow에 의도적으로 연결하지 않은 `event_cg_seoha_auditorium_seed260529200_candidate01`이다. Level 5 기준 현재 scene note인 `seoha_choice_pause`의 required assets는 production asset으로 승격되고 Ren'Py에서 참조되는 상태까지 완료됐다.
