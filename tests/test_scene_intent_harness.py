from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'vn_automation.cli', *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def write_workflow_pack(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    workflows = []
    for workflow_id in [
        'char_base',
        'char_expression',
        'char_alpha',
        'scene_background',
        'scene_prop_cg',
        'scene_event_cg',
        'audio_bgm_with_sfx',
    ]:
        (root / f'{workflow_id}.md').write_text(f'# {workflow_id}\n', encoding='utf-8')
        (root / f'{workflow_id}.json').write_text('{}\n', encoding='utf-8')
        workflows.append({
            'id': workflow_id,
            'readme': f'{workflow_id}.md',
            'api': f'{workflow_id}.json',
            'editable_fields': ['prompt'],
        })
    (root / 'WORKFLOW_INDEX.json').write_text(json.dumps({'workflows': workflows}), encoding='utf-8')


def bootstrap_project(tmp_path: Path) -> Path:
    workflow = tmp_path / 'workflow_pack'
    write_workflow_pack(workflow)
    renpy_root = tmp_path / 'renpy-project'
    proc = run_cli(
        'new-title',
        '--title', 'Intent Harness VN',
        '--slug', 'intent_harness_vn',
        '--renpy-projects-root', str(renpy_root),
        '--obsidian-vault', str(tmp_path / 'obsidian-vn'),
        '--workflow-pack-root', str(workflow),
        '--skip-renpy-lint',
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return renpy_root / 'intent_harness_vn'


def test_scene_intent_prepares_patch_run_without_touching_game_script(tmp_path: Path) -> None:
    project = bootstrap_project(tmp_path)
    before_script = (project / 'game/script.rpy').read_text(encoding='utf-8')

    proc = run_cli(
        'scene-intent',
        '--project-root', str(project),
        '--scene-id', 'scene_001_opening',
        '--intent-id', 'scene001_first_choice_direction',
        '--owner-text', '오프닝은 붉은 계약 경고와 첫 선택의 압박을 중심으로 간다.',
        '--objective', '첫 선택 전에 세계 규칙과 위험을 느끼게 한다.',
        '--choice', '계약 경고를 자세히 본다',
        '--choice', '일단 주변 인물을 의심한다',
        '--make-capture-plan',
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'SCENE_INTENT_READY' in proc.stdout
    assert 'polish-scene' in proc.stdout
    assert (project / 'game/script.rpy').read_text(encoding='utf-8') == before_script

    intent_path = project / 'docs/automation/scene_intents/scene_001_opening/scene001_first_choice_direction.json'
    assert intent_path.exists()
    intent = json.loads(intent_path.read_text(encoding='utf-8'))
    assert intent['scene_id'] == 'scene_001_opening'
    assert intent['intent_id'] == 'scene001_first_choice_direction'
    assert intent['status'] == 'pending_implementation'
    assert intent['asset_policy'] == 'scene_local_preview_only'
    assert intent['permanent_asset_changes'] is False
    assert intent['owner_text'].startswith('오프닝은')
    assert intent['choices'] == ['계약 경고를 자세히 본다', '일단 주변 인물을 의심한다']
    assert intent['prepared_run']['before_script'] == 'docs/validation/scene001_first_choice_direction/script_before.rpy'
    assert intent['prepared_run']['capture_plan'] == 'docs/validation/scene001_first_choice_direction/capture_plan.json'

    before = project / 'docs/validation/scene001_first_choice_direction/script_before.rpy'
    assert before.exists()
    assert before.read_text(encoding='utf-8') == before_script
    plan = json.loads((project / 'docs/validation/scene001_first_choice_direction/capture_plan.json').read_text(encoding='utf-8'))
    assert plan['scene_id'] == 'scene_001_opening'
    assert plan['captures'][0]['warp_label'] == 'scene_001_opening'
    assert plan['captures'][0]['expect_menu_choices'] == ['첫 장면의 방향을 정한다', '세계의 규칙을 확인한다', '관계의 균열을 본다']


def test_scene_intent_refuses_empty_owner_text_and_no_objective(tmp_path: Path) -> None:
    project = bootstrap_project(tmp_path)

    proc = run_cli(
        'scene-intent',
        '--project-root', str(project),
        '--scene-id', 'scene_001_opening',
        '--intent-id', 'empty_intent',
    )

    assert proc.returncode == 2
    assert 'SCENE_INTENT_REFUSED' in proc.stdout + proc.stderr
    assert not (project / 'docs/automation/scene_intents/scene_001_opening/empty_intent.json').exists()
