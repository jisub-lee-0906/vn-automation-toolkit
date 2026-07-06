import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'tools/scene_event_cg_policy.py'


def load_policy():
    spec = importlib.util.spec_from_file_location('scene_event_cg_policy', POLICY)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_multi_character_policy_is_review_only_and_has_safe_tokens():
    policy = load_policy()
    result = policy.resolve_scene_event_cg_policy(
        emotion='serious',
        framing='two_shot',
        subject_count=2,
        interaction='confrontation',
    )
    assert result['subject_count'] == 2
    assert result['interaction'] == 'confrontation'
    assert result['scene_event_route_mode'] == 'production_character_front'
    assert result['review_gate'] == 'multi_character_reference_required'
    assert result['executable'] is False
    assert '1girl' in result['scene_context_extra']
    assert '1boy' in result['scene_context_extra']
    assert 'confrontation' in result['scene_context_extra']


def test_build_multi_character_prompt_slots_records_subjects_without_claiming_identity_lock():
    policy = load_policy()
    slots = policy.build_scene_event_cg_prompt_slots(
        asset_id='event_cg_serena_lucian_confrontation',
        emotion='serious',
        framing='two_shot',
        subject_count=2,
        interaction='confrontation',
        subjects=['serena', 'lucian'],
        base_character_features=['brown_eyes'],
        base_outfit_detail=['school_uniform'],
        base_scene_context=['ballroom'],
    )
    assert slots['subject_count'] == 2
    assert slots['subjects'] == ['serena', 'lucian']
    assert slots['review_gate'] == 'multi_character_reference_required'
    assert slots['executable'] is False
    assert slots['reference_conditioning']['mode'] == 'none'
    assert slots['reference_conditioning']['status'] == 'not_requested'


def test_reference_conditioning_request_schema_is_preflight_only():
    policy = load_policy()
    ref = policy.build_reference_conditioning_request(
        mode='identity_reference',
        reference_assets=['images/characters/serena_dialogue_sprite_alpha_a01.png'],
        reason='identity lock probe',
    )
    assert ref['mode'] == 'identity_reference'
    assert ref['status'] == 'preflight_required_not_executable_by_default'
    assert ref['approval_required'] is True
    assert ref['reference_assets'][0].endswith('serena_dialogue_sprite_alpha_a01.png')
