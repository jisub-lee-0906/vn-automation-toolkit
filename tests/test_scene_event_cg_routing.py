from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
SCRIPT = TOOLS / 'run_scene_event_cg_smoke.py'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def load_runner():
    spec = importlib.util.spec_from_file_location('run_scene_event_cg_smoke', SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_scene_event_cg_detects_positive_negative_placeholder_conflict():
    runner = load_runner()
    negative = 'bad_anatomy, standing, facing_viewer, depth_of_field'
    try:
        runner.assert_no_positive_negative_conflicts(['indoors', 'standing', 'facing_viewer'], negative)
    except RuntimeError as exc:
        text = str(exc)
        assert 'SCENE_EVENT_CG_PROMPT_CONFLICT' in text
        assert 'standing' in text
        assert 'facing_viewer' in text
    else:
        raise AssertionError('expected prompt conflict RuntimeError')


def test_scene_event_cg_allows_non_conflicting_tags():
    runner = load_runner()
    runner.assert_no_positive_negative_conflicts(['indoors', 'auditorium'], 'bad_anatomy, classroom, close-up')


def test_scene_event_cg_detects_fixed_positive_negative_conflict():
    runner = load_runner()
    try:
        runner.assert_no_prompt_text_conflicts(
            'masterpiece, 1girl, depth_of_field, indoors',
            'bad_anatomy, depth_of_field, close-up',
            context='fixed_wrapper',
        )
    except RuntimeError as exc:
        text = str(exc)
        assert 'SCENE_EVENT_CG_PROMPT_CONFLICT' in text
        assert 'fixed_wrapper' in text
        assert 'depth_of_field' in text
    else:
        raise AssertionError('expected fixed prompt conflict RuntimeError')


def test_scene_event_cg_canonical_wrapper_has_no_negative_conflict():
    runner = load_runner()
    workflow = runner.load_json(Path('E:/workspace/comfyui-game-asset-workflows/scene_event_cg/scene_event_cg_workflow_api.json'))
    positive = runner.README_POSITIVE.format(
        character_features='medium_hair',
        outfit_detail='school_uniform',
        scene_context='indoors',
    )
    negative = workflow['10']['inputs']['text']
    runner.assert_no_prompt_text_conflicts(positive, negative, context='canonical_scene_event_cg')



def test_scene_event_cg_production_character_route_allows_upper_body_framing():
    runner = load_runner()
    negative = 'bad_anatomy, upper_body, looking_at_viewer, standing, close-up'
    adjusted = runner.apply_scene_event_route_policy(
        ['auditorium', 'spotlight', 'upper_body', 'looking_at_viewer'],
        negative,
        route_mode='production_character',
    )
    assert 'upper_body' not in runner.negative_prompt_tokens(adjusted)
    assert 'looking_at_viewer' not in runner.negative_prompt_tokens(adjusted)
    assert 'standing' in runner.negative_prompt_tokens(adjusted)
    runner.assert_no_positive_negative_conflicts(
        ['auditorium', 'spotlight', 'upper_body', 'looking_at_viewer'],
        adjusted,
    )


def test_scene_event_cg_production_character_route_keeps_unapproved_pose_conflicts():
    runner = load_runner()
    negative = 'bad_anatomy, upper_body, looking_at_viewer, standing, sitting'
    adjusted = runner.apply_scene_event_route_policy(
        ['auditorium', 'spotlight', 'standing'],
        negative,
        route_mode='production_character',
    )
    try:
        runner.assert_no_positive_negative_conflicts(['standing'], adjusted)
    except RuntimeError as exc:
        assert 'standing' in str(exc)
    else:
        raise AssertionError('expected standing to remain blocked in production_character route')


def test_scene_event_cg_cut_in_route_allows_portrait_closeup_tokens():
    runner = load_runner()
    negative = 'bad_anatomy, portrait, close-up, solo_focus, upper_body'
    adjusted = runner.apply_scene_event_route_policy(
        ['portrait', 'close-up', 'solo_focus'],
        negative,
        route_mode='cut_in',
    )
    tokens = runner.negative_prompt_tokens(adjusted)
    assert 'portrait' not in tokens
    assert 'close-up' not in tokens
    assert 'solo_focus' not in tokens
    assert 'upper_body' in tokens
    runner.assert_no_positive_negative_conflicts(['portrait', 'close-up', 'solo_focus'], adjusted)



def test_scene_event_cg_resolves_route_mode_from_prompt_slots_when_cli_omitted():
    runner = load_runner()
    prompt_slots_data = {'scene_event_route_mode': 'production_character'}
    assert runner.resolve_scene_event_route_mode(None, prompt_slots_data) == 'production_character'
    assert runner.resolve_scene_event_route_mode('cut_in', prompt_slots_data) == 'cut_in'
    assert runner.resolve_scene_event_route_mode(None, {}) == 'conservative'



def test_scene_event_cg_cowboy_route_allows_cowboy_shot_only_with_look():
    runner = load_runner()
    negative = 'bad_anatomy, cowboy_shot, looking_at_viewer, upper_body, close-up'
    adjusted = runner.apply_scene_event_route_policy(
        ['auditorium', 'cowboy_shot', 'looking_at_viewer'],
        negative,
        route_mode='production_character_cowboy',
    )
    tokens = runner.negative_prompt_tokens(adjusted)
    assert 'cowboy_shot' not in tokens
    assert 'looking_at_viewer' not in tokens
    assert 'upper_body' in tokens
    assert 'close_up' in tokens
    runner.assert_no_positive_negative_conflicts(['cowboy_shot', 'looking_at_viewer'], adjusted)


def test_scene_event_cg_cut_in_route_allows_headshot_token():
    runner = load_runner()
    negative = 'bad_anatomy, portrait, close-up, headshot, solo_focus, upper_body'
    adjusted = runner.apply_scene_event_route_policy(
        ['headshot', 'solo_focus'],
        negative,
        route_mode='cut_in',
    )
    tokens = runner.negative_prompt_tokens(adjusted)
    assert 'headshot' not in tokens
    assert 'solo_focus' not in tokens
    assert 'upper_body' in tokens
    runner.assert_no_positive_negative_conflicts(['headshot', 'solo_focus'], adjusted)


def test_scene_event_cg_negative_normalization_treats_hyphen_and_underscore_as_equivalent():
    runner = load_runner()
    negative = 'bad_anatomy, close_up, over_the_shoulder_shot'
    assert runner.normalize_prompt_token('close-up') == 'close_up'
    try:
        runner.assert_no_positive_negative_conflicts(['close-up'], negative)
    except RuntimeError as exc:
        assert 'close_up' in str(exc) or 'close-up' in str(exc)
    else:
        raise AssertionError('expected close-up/close_up conflict')
    adjusted = runner.apply_scene_event_route_policy(['close-up'], negative, route_mode='cut_in')
    runner.assert_no_positive_negative_conflicts(['close-up'], adjusted)


def test_scene_event_cg_review_gated_prompt_slots_block_execution_without_override():
    runner = load_runner()
    prompt_slots_data = {
        'asset_id': 'event_two_shot',
        'executable': False,
        'review_gate': 'multi_character_reference_required',
    }
    try:
        runner.assert_prompt_slots_executable(prompt_slots_data, allow_review_gated_execution=False)
    except RuntimeError as exc:
        text = str(exc)
        assert 'SCENE_EVENT_CG_REVIEW_GATED_NOT_EXECUTABLE' in text
        assert 'multi_character_reference_required' in text
    else:
        raise AssertionError('expected review-gated prompt slots to be blocked')


def test_scene_event_cg_review_gated_prompt_slots_can_be_explicitly_overridden():
    runner = load_runner()
    runner.assert_prompt_slots_executable(
        {'asset_id': 'event_two_shot', 'executable': False, 'review_gate': 'multi_character_reference_required'},
        allow_review_gated_execution=True,
    )


def test_scene_event_cg_blocks_reference_conditioning_approval_required_without_executable_flag():
    runner = load_runner()
    prompt_slots_data = {
        'asset_id': 'event_ref_preflight',
        'reference_conditioning': {
            'mode': 'identity_reference',
            'approval_required': True,
        },
    }
    try:
        runner.assert_prompt_slots_executable(prompt_slots_data, allow_review_gated_execution=False)
    except RuntimeError as exc:
        text = str(exc)
        assert 'SCENE_EVENT_CG_REVIEW_GATED_NOT_EXECUTABLE' in text
        assert 'reference_conditioning.approval_required' in text
    else:
        raise AssertionError('expected approval_required reference conditioning to be blocked')


def test_scene_event_cg_blocks_reference_conditioning_preflight_only_without_executable_flag():
    runner = load_runner()
    prompt_slots_data = {
        'asset_id': 'event_ref_preflight',
        'reference_conditioning': {
            'mode': 'identity_reference',
            'preflight_required_not_executable_by_default': True,
        },
    }
    try:
        runner.assert_prompt_slots_executable(prompt_slots_data, allow_review_gated_execution=False)
    except RuntimeError as exc:
        text = str(exc)
        assert 'SCENE_EVENT_CG_REVIEW_GATED_NOT_EXECUTABLE' in text
        assert 'reference_conditioning.preflight_required_not_executable_by_default' in text
    else:
        raise AssertionError('expected preflight-only reference conditioning to be blocked')


def test_scene_event_cg_blocks_reference_conditioning_status_preflight_without_executable_flag():
    runner = load_runner()
    prompt_slots_data = {
        'asset_id': 'event_ref_preflight',
        'reference_conditioning': {
            'mode': 'identity_reference',
            'status': 'preflight_required_not_executable_by_default',
        },
    }
    try:
        runner.assert_prompt_slots_executable(prompt_slots_data, allow_review_gated_execution=False)
    except RuntimeError as exc:
        text = str(exc)
        assert 'SCENE_EVENT_CG_REVIEW_GATED_NOT_EXECUTABLE' in text
        assert 'reference_conditioning.status=preflight_required_not_executable_by_default' in text
    else:
        raise AssertionError('expected preflight status reference conditioning to be blocked')


def test_scene_event_cg_reference_conditioning_can_be_explicitly_overridden():
    runner = load_runner()
    runner.assert_prompt_slots_executable(
        {
            'asset_id': 'event_ref_preflight',
            'reference_conditioning': {
                'mode': 'identity_reference',
                'approval_required': True,
                'preflight_required_not_executable_by_default': True,
            },
        },
        allow_review_gated_execution=True,
    )
