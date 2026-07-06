import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'tools/scene_event_cg_policy.py'


def load_policy():
    spec = importlib.util.spec_from_file_location('scene_event_cg_policy_under_test', POLICY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_neutral_default_policy():
    policy = load_policy()
    resolved = policy.resolve_scene_event_cg_policy(emotion='neutral', framing='default')
    assert resolved['scene_event_route_mode'] == 'production_character'
    assert resolved['character_features_extra'] == ['expressionless', 'closed_mouth']
    assert resolved['scene_context_extra'] == ['upper_body', 'looking_at_viewer']


def test_resolve_sad_default_policy_is_front_route():
    policy = load_policy()
    resolved = policy.resolve_scene_event_cg_policy(emotion='sad', framing='default')
    assert resolved['scene_event_route_mode'] == 'production_character_front'
    assert resolved['character_features_extra'] == ['sad', 'tears', 'frown', 'closed_mouth']
    assert resolved['scene_context_extra'] == ['upper_body', 'looking_at_viewer', 'facing_viewer', 'straight_on']


def test_resolve_cutin_overrides_emotion_default_route():
    policy = load_policy()
    resolved = policy.resolve_scene_event_cg_policy(emotion='happy', framing='cutin')
    assert resolved['scene_event_route_mode'] == 'cut_in'
    assert resolved['character_features_extra'] == ['smile', 'open_mouth']
    assert resolved['scene_context_extra'] == ['portrait', 'close-up', 'headshot', 'solo_focus']


def test_build_prompt_slots_merges_base_tags_and_policy_without_duplicates():
    policy = load_policy()
    data = policy.build_scene_event_cg_prompt_slots(
        asset_id='event_auto_sad',
        emotion='sad',
        framing='default',
        base_character_features=['brown_eyes', 'tareme', 'brown_hair'],
        base_outfit_detail=['red_bow', 'brown_cardigan', 'white_shirt'],
        base_scene_context=['auditorium', 'spotlight', 'upper_body'],
    )
    assert data['workflow_id'] == 'scene_event_cg'
    assert data['asset_id'] == 'event_auto_sad'
    assert data['scene_event_route_mode'] == 'production_character_front'
    slots = data['prompt_slots']
    assert slots['character_features'] == ['brown_eyes', 'tareme', 'brown_hair', 'sad', 'tears', 'frown', 'closed_mouth']
    assert slots['outfit_detail'] == ['red_bow', 'brown_cardigan', 'white_shirt']
    assert slots['scene_context'] == ['auditorium', 'spotlight', 'upper_body', 'looking_at_viewer', 'facing_viewer', 'straight_on']


def test_unknown_emotion_fails_closed():
    policy = load_policy()
    try:
        policy.resolve_scene_event_cg_policy(emotion='angry', framing='default')
    except RuntimeError as exc:
        assert 'UNKNOWN_SCENE_EVENT_EMOTION' in str(exc)
    else:
        raise AssertionError('expected RuntimeError')
